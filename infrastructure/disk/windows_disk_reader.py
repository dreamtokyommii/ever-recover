"""Windows disk reader implementation using native APIs."""

import ctypes
import os
import sys
from ctypes import wintypes
from typing import List, Optional
from pathlib import Path
import logging
import struct

from core.interfaces.disk_reader import (
    DiskReader, DiskGeometry, PartitionInfo,
    DiskReaderError, AccessDeniedError, InvalidDeviceError, ReadError
)

logger = logging.getLogger(__name__)

# Windows API constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_RANDOM_ACCESS = 0x10000000
FILE_FLAG_NO_BUFFERING = 0x20000000

# IOCTL codes
IOCTL_DISK_GET_DRIVE_GEOMETRY_EX = 0x000700A0
IOCTL_DISK_GET_PARTITION_INFO_EX = 0x000700A4
IOCTL_DISK_GET_DRIVE_LAYOUT = 0x0007C008
IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400

# Partition styles
PARTITION_STYLE_MBR = 0
PARTITION_STYLE_GPT = 1

# Load Windows DLLs. Guarded so importing this module on a non-Windows
# platform doesn't crash - infrastructure/disk/__init__.py imports
# WindowsDiskReader unconditionally (used e.g. by factory.py's
# create_disk_reader for cross-platform code paths, and by the test
# suite). Actually attempting to use a WindowsDiskReader on a non-Windows
# platform will fail naturally and clearly the first time a Windows-only
# call is made, which is correct - it's only import-time that must not
# crash.
if os.name == 'nt' or sys.platform.startswith('win'):
    kernel32 = ctypes.windll.kernel32
else:
    kernel32 = None


class CREATE_FILE_PARAMETERS(ctypes.Structure):
    """Parameters for CreateFile."""
    pass


class DISK_GEOMETRY_EX(ctypes.Structure):
    """DISK_GEOMETRY_EX structure."""
    _fields_ = [
        ("Cylinders", ctypes.c_int64),
        ("MediaType", ctypes.c_uint),
        ("TracksPerCylinder", ctypes.c_uint),
        ("SectorsPerTrack", ctypes.c_uint),
        ("BytesPerSector", ctypes.c_uint),
        ("DiskSize", ctypes.c_int64),
        ("Data", ctypes.c_uint8),
    ]


class PARTITION_INFORMATION_MBR(ctypes.Structure):
    """MBR partition information."""
    _fields_ = [
        ("PartitionType", ctypes.c_uint8),
        ("BootIndicator", ctypes.c_uint8),
        ("RecognizedPartition", ctypes.c_uint8),
        ("HiddenSectors", ctypes.c_uint32),
        ("StartingOffset", ctypes.c_int64),
        ("PartitionSize", ctypes.c_int64),
        ("RewritePartition", ctypes.c_uint32),
    ]


class PARTITION_INFORMATION_GPT(ctypes.Structure):
    """GPT partition information."""
    _fields_ = [
        ("PartitionType", ctypes.c_uint8 * 16),
        ("PartitionNumber", ctypes.c_uint32),
        ("StartingOffset", ctypes.c_int64),
        ("PartitionSize", ctypes.c_int64),
        ("Attributes", ctypes.c_uint64),
        ("Name", ctypes.c_wchar * 36),
    ]


class PARTITION_INFORMATION_Union(ctypes.Union):
    """Partition information union."""
    _fields_ = [
        ("Mbr", PARTITION_INFORMATION_MBR),
        ("Gpt", PARTITION_INFORMATION_GPT),
    ]


class PARTITION_INFORMATION_EX(ctypes.Structure):
    """Extended partition information."""
    _fields_ = [
        ("PartitionStyle", ctypes.c_uint),
        ("_info", PARTITION_INFORMATION_Union),
        ("RewritePartition", ctypes.c_uint32),
    ]
    
    @property
    def info(self):
        """Get partition info based on style."""
        if self.PartitionStyle == PARTITION_STYLE_MBR:
            return self._info.Mbr
        elif self.PartitionStyle == PARTITION_STYLE_GPT:
            return self._info.Gpt
        return None


class DRIVE_LAYOUT_EX(ctypes.Structure):
    """Drive layout information."""
    _fields_ = [
        ("PartitionStyle", ctypes.c_uint),
        ("PartitionCount", ctypes.c_uint),
        ("PartitionInfo", PARTITION_INFORMATION_EX * 128),
    ]


class WindowsDiskReader(DiskReader):
    """
    Windows disk reader using native APIs.
    
    Features:
    - Read-only access enforced
    - Physical drive and logical volume support
    - MBR and GPT partition table support
    - Direct disk access (no file system buffering)
    - Support for disk images (E01, raw, etc.)
    
    Device paths:
    - Physical drives: \\\\.\\PhysicalDrive0, \\\\.\\PhysicalDrive1, etc.
    - Logical volumes: \\\\.\\C:, \\\\.\\D:, etc.
    - Disk images: C:\\path\\to\\image.e01
    """
    
    def __init__(self, device_path: str):
        """
        Initialize Windows disk reader.
        
        Args:
            device_path: Device path (\\\\.\\PhysicalDriveX, \\\\.\\X:, or file path)
        """
        super().__init__(device_path)
        self._handle = None
        self._is_image_file = False
        self._geometry: Optional[DiskGeometry] = None
        self._partitions: List[PartitionInfo] = []
    
    def open(self) -> bool:
        """Open device for read-only access."""
        if self._is_open:
            return True

        if self.device_path and self.device_path.lower().startswith("\\\\.\\"):
            from core.services.privilege_manager import is_elevated
            if not is_elevated():
                raise AccessDeniedError(
                    f"Administrator privileges are required to open raw disk access path '{self.device_path}'. "
                    "Please launch EverRecover as Administrator."
                )

        try:
            # Check if it's an image file
            if self._is_valid_file_path(self.device_path):
                return self._open_image_file()
            
            # Normalize device path
            device_path = self._normalize_device_path(self.device_path)
            
            # Open device with read-only access
            self._handle = kernel32.CreateFileW(
                device_path,
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                FILE_FLAG_RANDOM_ACCESS | FILE_FLAG_NO_BUFFERING,
                None
            )
            
            if self._handle == -1 or self._handle is None:
                error_code = kernel32.GetLastError()
                if error_code == 5:  # ERROR_ACCESS_DENIED
                    raise AccessDeniedError(f"Access denied to {self.device_path}. Run as administrator.")
                elif error_code == 2:  # ERROR_FILE_NOT_FOUND
                    raise InvalidDeviceError(f"Device not found: {self.device_path}")
                else:
                    raise DiskReaderError(f"Failed to open device (error {error_code})")
            
            # Get disk geometry
            self._geometry = self._get_geometry()
            self._total_size = self._geometry.total_size
            
            # Get partitions
            self._partitions = self._get_partitions()
            
            self._is_open = True
            logger.info(f"Opened device: {self.device_path} ({self.display_size})")
            return True
            
        except (AccessDeniedError, InvalidDeviceError, DiskReaderError):
            raise
        except Exception as e:
            raise DiskReaderError(f"Failed to open device: {e}")
    
    def close(self) -> None:
        """Close device handle."""
        if self._handle and self._handle != -1:
            kernel32.CloseHandle(self._handle)
            self._handle = None
            self._is_open = False
            logger.info(f"Closed device: {self.device_path}")
    
    def read(self, offset: int, size: int) -> bytes:
        """Read data from device at offset."""
        if not self._is_open:
            raise ReadError("Device not open")
        
        if offset < 0:
            raise ValueError(f"Invalid offset: {offset}")
        
        if offset + size > self._total_size:
            raise EOFError(f"Read beyond end of device: {offset + size} > {self._total_size}")
        
        try:
            # Set file position
            result = kernel32.SetFilePointer(
                self._handle,
                offset & 0xFFFFFFFF,
                ctypes.byref(ctypes.c_int64(offset >> 32)),
                0  # FILE_BEGIN
            )
            
            if result == -1:
                raise ReadError(f"Failed to seek to offset {offset}")
            
            # Read data
            buffer = ctypes.create_string_buffer(size)
            bytes_read = wintypes.DWORD()
            
            if not kernel32.ReadFile(self._handle, buffer, size, ctypes.byref(bytes_read), None):
                error_code = kernel32.GetLastError()
                raise ReadError(f"Read failed at offset {offset} (error {error_code})")
            
            return buffer.raw[:bytes_read.value]
            
        except (ReadError, EOFError):
            raise
        except Exception as e:
            raise ReadError(f"Read failed at offset {offset}: {e}")
    
    def read_sectors(self, start_sector: int, num_sectors: int) -> bytes:
        """Read complete sectors."""
        offset = start_sector * self.bytes_per_sector
        size = num_sectors * self.bytes_per_sector
        return self.read(offset, size)
    
    def get_geometry(self) -> DiskGeometry:
        """Get disk geometry."""
        if not self._geometry:
            raise DiskReaderError("Device not opened")
        return self._geometry
    
    def get_partitions(self) -> List[PartitionInfo]:
        """Get partition information."""
        if not self._is_open:
            raise DiskReaderError("Device not opened")
        return self._partitions.copy()
    
    @property
    def total_size(self) -> int:
        """Get total device size."""
        if not self._is_open:
            raise DiskReaderError("Device not opened")
        return self._total_size
    
    @property
    def bytes_per_sector(self) -> int:
        """Get bytes per sector."""
        if not self._geometry:
            raise DiskReaderError("Device not opened")
        return self._geometry.bytes_per_sector
    
    @property
    def display_size(self) -> str:
        """Get human-readable size."""
        return self._format_bytes(self.total_size) if self._is_open else "Unknown"
    
    @staticmethod
    def _detect_physical_drive(device_path: str) -> bool:
        """Detect if path is a physical drive."""
        # NOTE: real Windows device-namespace paths use a SINGLE backslash
        # after the dot (\\.\PhysicalDrive0), not two. A previous version of
        # this check used r'\\.\\physicaldrive' (two backslashes after the
        # dot), which never matches a real path and silently broke physical
        # drive detection.
        return device_path.lower().startswith('\\\\.\\physicaldrive')

    def _normalize_device_path(self, device_path: str) -> str:
        """Normalize device path to Windows format."""
        path = device_path.strip()
        
        # Already normalized (e.g. \\.\PhysicalDrive0, \\.\C:)
        if path.startswith('\\\\.\\') or path.startswith('\\\\?\\'):
            return path
        
        # Physical drive
        if path.lower().startswith('physicaldrive'):
            return f"\\\\.\\{path}"
        
        # Drive letter
        if len(path) == 1 or (len(path) == 2 and path[1] == ':'):
            drive_letter = path[0].upper()
            return f"\\\\.\\{drive_letter}:"
        
        # File path
        if ':' in path or path.startswith('~'):
            return path
        
        # Assume physical drive number
        if path.isdigit():
            return f"\\\\.\\PhysicalDrive{path}"
        
        raise InvalidDeviceError(f"Cannot parse device path: {device_path}")
    
    def _is_valid_file_path(self, path: str) -> bool:
        """Check if path is a valid file path."""
        try:
            p = Path(path)
            if p.exists() and p.is_file():
                self._is_image_file = True
                return True
        except:
            pass
        return False
    
    def _open_image_file(self) -> bool:
        """Open disk image file."""
        try:
            self._handle = kernel32.CreateFileW(
                self.device_path,
                GENERIC_READ,
                FILE_SHARE_READ,
                None,
                OPEN_EXISTING,
                FILE_FLAG_RANDOM_ACCESS,
                None
            )
            
            if self._handle == -1 or self._handle is None:
                error_code = kernel32.GetLastError()
                raise DiskReaderError(f"Failed to open image file (error {error_code})")
            
            # Get file size
            size_low = kernel32.GetFileSize(self._handle, None)
            self._total_size = size_low
            
            self._is_open = True
            logger.info(f"Opened image file: {self.device_path} ({self.display_size})")
            return True
            
        except Exception as e:
            raise DiskReaderError(f"Failed to open image file: {e}")
    
    def _get_geometry(self) -> DiskGeometry:
        """Get disk geometry using IOCTL."""
        try:
            if self._is_image_file:
                # For image files, use file size
                return DiskGeometry(
                    bytes_per_sector=512,
                    sectors_per_track=63,
                    tracks_per_cylinder=255,
                    total_sectors=self._total_size // 512,
                    cylinder_size=0,
                    total_size=self._total_size
                )
            
            # Get geometry using IOCTL
            geometry = DISK_GEOMETRY_EX()
            bytes_returned = wintypes.DWORD()
            
            if not kernel32.DeviceIoControl(
                self._handle,
                IOCTL_DISK_GET_DRIVE_GEOMETRY_EX,
                None,
                0,
                ctypes.byref(geometry),
                ctypes.sizeof(geometry),
                ctypes.byref(bytes_returned),
                None
            ):
                # Fallback to basic geometry
                return self._get_basic_geometry()
            
            return DiskGeometry(
                bytes_per_sector=geometry.BytesPerSector,
                sectors_per_track=geometry.SectorsPerTrack,
                tracks_per_cylinder=geometry.TracksPerCylinder,
                total_sectors=geometry.DiskSize // geometry.BytesPerSector,
                cylinder_size=geometry.TracksPerCylinder * geometry.SectorsPerTrack * geometry.BytesPerSector,
                total_size=geometry.DiskSize
            )
            
        except Exception as e:
            logger.warning(f"Failed to get geometry: {e}")
            return self._get_basic_geometry()
    
    def _get_basic_geometry(self) -> DiskGeometry:
        """Get basic geometry using legacy IOCTL."""
        # Simplified fallback
        return DiskGeometry(
            bytes_per_sector=512,
            sectors_per_track=63,
            tracks_per_cylinder=255,
            total_sectors=self._total_size // 512,
            cylinder_size=0,
            total_size=self._total_size
        )
    
    def _get_partitions(self) -> List[PartitionInfo]:
        """Get partition information."""
        partitions = []
        
        try:
            if self._is_image_file:
                # Can't get partitions from image file directly
                return partitions
            
            # Get partition layout
            layout = DRIVE_LAYOUT_EX()
            bytes_returned = wintypes.DWORD()
            
            result = kernel32.DeviceIoControl(
                self._handle,
                IOCTL_DISK_GET_PARTITION_INFO_EX,
                None,
                0,
                ctypes.byref(layout),
                ctypes.sizeof(layout),
                ctypes.byref(bytes_returned),
                None
            )
            
            if result and layout.PartitionCount > 0:
                for i in range(layout.PartitionCount):
                    part_info = layout.PartitionInfo[i]
                    
                    if part_info.PartitionStyle == PARTITION_STYLE_MBR:
                        mbr = part_info.info
                        partition_type = self._get_partition_type_name(mbr.PartitionType)
                        
                        partitions.append(PartitionInfo(
                            partition_number=i + 1,
                            start_sector=mbr.HiddenSectors,
                            end_sector=mbr.HiddenSectors + (mbr.PartitionSize // self.bytes_per_sector),
                            start_offset=mbr.StartingOffset,
                            size=mbr.PartitionSize,
                            partition_type=partition_type,
                            is_active=bool(mbr.BootIndicator),
                            bootable=bool(mbr.RecognizedPartition)
                        ))
                    
                    elif part_info.PartitionStyle == PARTITION_STYLE_GPT:
                        gpt = part_info.info
                        
                        partitions.append(PartitionInfo(
                            partition_number=gpt.PartitionNumber,
                            start_sector=gpt.StartingOffset // self.bytes_per_sector,
                            end_sector=(gpt.StartingOffset + gpt.PartitionSize) // self.bytes_per_sector,
                            start_offset=gpt.StartingOffset,
                            size=gpt.PartitionSize,
                            partition_type=str(gpt.PartitionType),
                            is_active=bool(gpt.Attributes & 0x1),
                            bootable=bool(gpt.Attributes & 0x8000000000000001)
                        ))
        
        except Exception as e:
            logger.warning(f"Failed to get partitions: {e}")
        
        return partitions
    
    def _get_partition_type_name(self, partition_type: int) -> str:
        """Get partition type name from MBR type code."""
        type_map = {
            0x00: "Empty",
            0x01: "FAT12",
            0x04: "FAT16",
            0x05: "Extended",
            0x06: "FAT16B",
            0x07: "NTFS/exFAT",
            0x0B: "FAT32",
            0x0C: "FAT32X",
            0x0E: "FAT16X",
            0x0F: "ExtendedX",
            0x82: "Linux Swap",
            0x83: "Linux",
            0x8E: "Linux LVM",
            0xA5: "FreeBSD",
            0xA8: "macOS",
            0xAB: "macOS Boot",
            0xAF: "HFS+",
            0xEE: "GPT Protective",
        }
        return type_map.get(partition_type, f"Unknown (0x{partition_type:02X})")
    
    @staticmethod
    def _format_bytes(size: int) -> str:
        """Format bytes to human-readable string."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"
    
    @staticmethod
    def get_device_removable_status(physical_drive_path: str) -> Optional[bool]:
        """Query whether a physical drive is removable media (USB/SD/etc.)
        via IOCTL_STORAGE_QUERY_PROPERTY (StorageDeviceProperty).

        Returns True/False when the query succeeds, or None if it fails
        (e.g. unsupported device, transient error) - callers must treat
        None as "unknown", never silently assume "fixed", since that
        assumption is exactly what this method exists to avoid.

        No open-for-read access is required for this query (desired
        access 0 is sufficient, matching enumerate_physical_drives()
        above), so this can be called even before elevation for display
        purposes in the device picker.
        """
        if kernel32 is None:
            return None
        handle = kernel32.CreateFileW(
            physical_drive_path,
            0,  # no read/write access needed for a property query
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle in (None, -1, 0xFFFFFFFF):
            return None
        try:
            # STORAGE_PROPERTY_QUERY: PropertyId=0 (StorageDeviceProperty),
            # QueryType=0 (PropertyStandardQuery), AdditionalParameters[1].
            # Padded to 12 bytes to satisfy typical struct alignment; the
            # kernel only reads what the query actually needs.
            query = struct.pack('<IIB', 0, 0, 0).ljust(12, b'\x00')
            out_buf = ctypes.create_string_buffer(1024)
            bytes_returned = wintypes.DWORD(0)

            ok = kernel32.DeviceIoControl(
                handle,
                IOCTL_STORAGE_QUERY_PROPERTY,
                query, len(query),
                out_buf, len(out_buf),
                ctypes.byref(bytes_returned),
                None,
            )
            if not ok:
                return None

            data = out_buf.raw
            # STORAGE_DEVICE_DESCRIPTOR: Version(4) Size(4) DeviceType(1)
            # DeviceTypeModifier(1) RemovableMedia(1) ...
            if len(data) < 11:
                return None
            return bool(data[10])
        except Exception:
            return None
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def get_logical_drive_type(drive_letter: str) -> Optional[bool]:
        """Query whether a logical drive (e.g. 'E:') is removable media via
        GetDriveTypeW. This needs no elevated privileges at all. Returns
        True/False, or None if the type can't be determined.
        """
        if kernel32 is None:
            return None
        try:
            root_path = f"{drive_letter.rstrip(chr(92))}\\"
            drive_type = kernel32.GetDriveTypeW(root_path)
            # DRIVE_REMOVABLE = 2, DRIVE_FIXED = 3, DRIVE_REMOTE = 4,
            # DRIVE_CDROM = 5, DRIVE_RAMDISK = 6, DRIVE_UNKNOWN = 0,
            # DRIVE_NO_ROOT_DIR = 1
            if drive_type == 2:
                return True
            if drive_type in (3, 4, 5, 6):
                return False
            return None
        except Exception:
            return None

    @staticmethod
    def enumerate_physical_drives() -> List[str]:
        """Enumerate all physical drives on system."""
        drives = []
        
        for i in range(32):  # Max 32 physical drives
            path = f"\\\\.\\PhysicalDrive{i}"
            try:
                handle = kernel32.CreateFileW(
                    path,
                    0,  # No access needed for enumeration
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    None,
                    OPEN_EXISTING,
                    0,
                    None
                )
                
                if handle != -1 and handle is not None:
                    drives.append(path)
                    kernel32.CloseHandle(handle)
            
            except:
                break
        
        return drives
    
    @staticmethod
    def enumerate_logical_drives() -> List[str]:
        """Enumerate all logical drives (drive letters)."""
        drives = []
        bitmask = kernel32.GetLogicalDrives()
        
        for i in range(26):
            if bitmask & (1 << i):
                drive_letter = chr(ord('A') + i)
                drives.append(f"{drive_letter}:")
        
        return drives