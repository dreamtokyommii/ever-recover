"""Linux disk reader implementation using device files."""

import os
import struct
import fcntl
import logging
from typing import List, Optional
from pathlib import Path

from core.interfaces.disk_reader import (
    DiskReader, DiskGeometry, PartitionInfo,
    DiskReaderError, AccessDeniedError, InvalidDeviceError, ReadError
)

logger = logging.getLogger(__name__)

# IOCTL commands for Linux
HDIO_GETGEO = 0x0301  # Get device geometry
BLKGETSIZE = 0x1260  # Get device size in sectors
BLKSSZGET = 0x1268  # Get sector size
BLKBSZGET = 0x80081270  # Get block size
BLKDISCARD = 0x1277  # Check if TRIM/DISCARD is supported

# Partition types
PROC_PARTITIONS_PATH = "/proc/partitions"
SYS_BLOCK_PATH = "/sys/block"


class LinuxDiskReader(DiskReader):
    """
    Linux disk reader using device files.
    
    Features:
    - Read-only access via /dev/ device files
    - Physical drives: /dev/sda, /dev/nvme0n1, etc.
    - Logical volumes: /dev/sda1, /dev/mapper/*, etc.
    - Disk images: raw, E01, AFF
    - TRIM detection for SSDs
    """
    
    def __init__(self, device_path: str):
        """
        Initialize Linux disk reader.
        
        Args:
            device_path: Device path (/dev/sda, /dev/sda1, etc.)
        """
        super().__init__(device_path)
        self._file = None
        self._is_image_file = False
        self._geometry: Optional[DiskGeometry] = None
        self._partitions: List[PartitionInfo] = []
        self._is_ssd: bool = False
        self._is_trim_enabled: bool = False
    
    def open(self) -> bool:
        """Open device for read-only access."""
        if self._is_open:
            return True
        
        try:
            # Check if image file
            if self._is_valid_file_path(self.device_path):
                return self._open_image_file()
            
            # Normalize device path
            device_path = self._normalize_device_path(self.device_path)
            
            # Check if device exists
            if not os.path.exists(device_path):
                raise InvalidDeviceError(f"Device not found: {device_path}")
            
            # Open device read-only
            self._file = open(device_path, 'rb')
            
            # Get device size
            self._file.seek(0, os.SEEK_END)
            self._total_size = self._file.tell()
            self._file.seek(0)
            
            # Get geometry
            self._geometry = self._get_geometry()
            
            # Get partitions
            self._partitions = self._get_partitions()
            
            # Check if SSD and TRIM
            self._is_ssd = self._detect_ssd()
            self._is_trim_enabled = self._detect_trim()
            
            self._is_open = True
            logger.info(f"Opened device: {self.device_path} ({self.display_size})")
            return True
            
        except (AccessDeniedError, InvalidDeviceError, DiskReaderError):
            raise
        except Exception as e:
            raise DiskReaderError(f"Failed to open device: {e}")
    
    def close(self) -> None:
        """Close device file."""
        if self._file:
            self._file.close()
            self._file = None
            self._is_open = False
            logger.info(f"Closed device: {self.device_path}")
    
    def read(self, offset: int, size: int) -> bytes:
        """Read data from device."""
        if not self._is_open:
            raise ReadError("Device not open")
        
        if offset < 0:
            raise ValueError(f"Invalid offset: {offset}")
        
        if offset + size > self._total_size:
            raise EOFError(f"Read beyond end of device: {offset + size} > {self._total_size}")
        
        try:
            self._file.seek(offset)
            return self._file.read(size)
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
            return 512  # Default
        return self._geometry.bytes_per_sector
    
    @property
    def is_ssd(self) -> bool:
        """Check if device is SSD."""
        return self._is_ssd
    
    @property
    def is_trim_enabled(self) -> bool:
        """Check if TRIM is enabled."""
        return self._is_trim_enabled
    
    @staticmethod
    def _detect_physical_drive(device_path: str) -> bool:
        """Detect if physical drive."""
        path = device_path.lower()
        return (path.startswith('/dev/sd') or 
                path.startswith('/dev/nvme') or
                path.startswith('/dev/hd') or
                path.startswith('/dev/vd'))
    
    def _normalize_device_path(self, device_path: str) -> str:
        """Normalize device path."""
        path = device_path.strip()
        
        if path.startswith('/dev/'):
            return path
        
        # Add /dev/ prefix
        return f"/dev/{path}"
    
    def _is_valid_file_path(self, path: str) -> bool:
        """Check if valid file path."""
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
            self._file = open(self.device_path, 'rb')
            self._file.seek(0, os.SEEK_END)
            self._total_size = self._file.tell()
            self._file.seek(0)
            
            self._is_open = True
            logger.info(f"Opened image file: {self.device_path} ({self.display_size})")
            return True
        except PermissionError:
            raise AccessDeniedError(f"Permission denied: {self.device_path}")
        except Exception as e:
            raise DiskReaderError(f"Failed to open image file: {e}")
    
    def _get_geometry(self) -> DiskGeometry:
        """Get disk geometry."""
        try:
            if self._is_image_file:
                return DiskGeometry(
                    bytes_per_sector=512,
                    sectors_per_track=63,
                    tracks_per_cylinder=255,
                    total_sectors=self._total_size // 512,
                    cylinder_size=0,
                    total_size=self._total_size
                )
            
            # Try to get sector size
            sector_size = 512
            try:
                sector_size = self._ioctl_int(BLKSSZGET)
            except:
                pass
            
            return DiskGeometry(
                bytes_per_sector=sector_size,
                sectors_per_track=63,
                tracks_per_cylinder=255,
                total_sectors=self._total_size // sector_size,
                cylinder_size=0,
                total_size=self._total_size
            )
        except Exception as e:
            logger.warning(f"Failed to get geometry: {e}")
            return DiskGeometry(
                bytes_per_sector=512,
                sectors_per_track=63,
                tracks_per_cylinder=255,
                total_sectors=self._total_size // 512,
                cylinder_size=0,
                total_size=self._total_size
            )
    
    def _get_partitions(self) -> List[PartitionInfo]:
        """Get partitions from /proc/partitions."""
        partitions = []
        
        try:
            # Get device name (e.g., sda from /dev/sda)
            device_name = os.path.basename(self.device_path)
            
            if not os.path.exists(PROC_PARTITIONS_PATH):
                return partitions
            
            with open(PROC_PARTITIONS_PATH, 'r') as f:
                lines = f.readlines()[2:]  # Skip header
                
                for line in lines:
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    
                    major = int(parts[0])
                    minor = int(parts[1])
                    blocks = int(parts[2])
                    name = parts[3]
                    
                    # Check if partition belongs to this device
                    if name.startswith(device_name) and name != device_name:
                        # Determine if it's a partition
                        partition_num = int(name[len(device_name):]) if name[len(device_name):].isdigit() else 0
                        
                        # Get partition type info from sysfs
                        partition_type = "Unknown"
                        is_active = False
                        is_bootable = False
                        
                        sysfs_path = f"{SYS_BLOCK_PATH}/{device_name}/{name}"
                        if os.path.exists(sysfs_path):
                            try:
                                with open(f"{sysfs_path}/partition", 'r') as pf:
                                    partition_type = f"Partition {pf.read().strip()}"
                            except:
                                pass
                        
                        partitions.append(PartitionInfo(
                            partition_number=partition_num,
                            start_sector=0,  # Would need fdisk to get actual start
                            end_sector=blocks,
                            start_offset=0,
                            size=blocks * 512,
                            partition_type=partition_type,
                            is_active=is_active,
                            bootable=is_bootable
                        ))
        
        except Exception as e:
            logger.warning(f"Failed to get partitions: {e}")
        
        return partitions
    
    def _detect_ssd(self) -> bool:
        """Detect if device is SSD."""
        try:
            device_name = os.path.basename(self.device_path)
            
            # Check /sys/block/*/queue/rotational
            rotational_path = f"{SYS_BLOCK_PATH}/{device_name}/queue/rotational"
            if os.path.exists(rotational_path):
                with open(rotational_path, 'r') as f:
                    return f.read().strip() == '0'
        except:
            pass
        
        return False
    
    def _detect_trim(self) -> bool:
        """Detect if TRIM is enabled."""
        try:
            # Check discard_max_bytes
            device_name = os.path.basename(self.device_path)
            discard_path = f"{SYS_BLOCK_PATH}/{device_name}/queue/discard_max_bytes"
            
            if os.path.exists(discard_path):
                with open(discard_path, 'r') as f:
                    max_discard = int(f.read().strip())
                    return max_discard > 0
        except:
            pass
        
        return False
    
    def _ioctl_int(self, command: int) -> int:
        """Perform ioctl returning integer."""
        result = fcntl.ioctl(self._file.fileno(), command)
        if isinstance(result, bytes):
            return struct.unpack('I', result)[0]
        return result
    
    @staticmethod
    def enumerate_block_devices() -> List[str]:
        """Enumerate all block devices."""
        devices = []
        
        try:
            if os.path.exists(PROC_PARTITIONS_PATH):
                with open(PROC_PARTITIONS_PATH, 'r') as f:
                    lines = f.readlines()[2:]
                    
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 4:
                            name = parts[3]
                            devices.append(f"/dev/{name}")
        except:
            pass
        
        return devices
    
    @staticmethod
    def get_device_info(device_path: str) -> dict:
        """Get device information."""
        info = {
            'path': device_path,
            'exists': os.path.exists(device_path),
            'is_block': os.path.exists(device_path) and os.path.isfile(device_path),
            'readable': os.access(device_path, os.R_OK) if os.path.exists(device_path) else False,
        }
        
        # Get size
        if info['exists']:
            try:
                with open(device_path, 'rb') as f:
                    f.seek(0, os.SEEK_END)
                    info['size'] = f.tell()
            except:
                info['size'] = 0
        
        # Check if SSD
        device_name = os.path.basename(device_path)
        rotational_path = f"{SYS_BLOCK_PATH}/{device_name}/queue/rotational"
        if os.path.exists(rotational_path):
            with open(rotational_path, 'r') as f:
                info['is_ssd'] = f.read().strip() == '0'
        
        # Check TRIM
        discard_path = f"{SYS_BLOCK_PATH}/{device_name}/queue/discard_max_bytes"
        if os.path.exists(discard_path):
            with open(discard_path, 'r') as f:
                info['trim_enabled'] = int(f.read().strip()) > 0
        
        return info