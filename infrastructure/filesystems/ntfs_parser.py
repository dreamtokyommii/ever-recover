"""NTFS file system parser with MFT parsing."""

import struct
import logging
from datetime import datetime, timezone
from typing import Iterator, List, Dict, Optional, Tuple, Any
from pathlib import Path
from dataclasses import dataclass
from enum import IntEnum

from core.interfaces.disk_reader import DiskReader
from core.interfaces.filesystem_parser import (
    FileSystemParser, FileSystemInfo, DirectoryEntry,
    FileSystemParserError, FileSystemCorruptedError, FileSystemType
)
from core.models.file_entry import FileEntry, FileStatus, FileCategory, RecoveryConfidence

logger = logging.getLogger(__name__)

# NTFS Constants
NTFS_SIGNATURE = b'NTFS    '
NTFS_BOOT_SECTOR_SIZE = 512
MFT_RECORD_SIZE = 1024  # Default, can be 4096
MFT_MIRROR_OFFSET = 0  # Relative to partition start

# Attribute Types
class AttributeType(IntEnum):
    """NTFS attribute types."""
    STANDARD_INFORMATION = 0x10
    ATTRIBUTE_LIST = 0x20
    FILE_NAME = 0x30
    OBJECT_ID = 0x40
    SECURITY_DESCRIPTOR = 0x50
    VOLUME_NAME = 0x60
    VOLUME_INFORMATION = 0x70
    DATA = 0x80
    INDEX_ROOT = 0x90
    INDEX_ALLOCATION = 0xA0
    BITMAP = 0xB0
    REPARSE_POINT = 0xC0
    EA_INFORMATION = 0xD0
    EA = 0xE0
    PROPERTY_SET = 0xF0
    LOGGED_UTILITY_STREAM = 0x100


@dataclass
class MFTRecord:
    """NTFS MFT record structure."""
    record_number: int
    sequence_number: int
    flags: int  # 0x01 = in use, 0x02 = is directory
    link_count: int
    attributes_offset: int
    first_attribute_offset: int
    base_record: int  # For file records
    attributes: Dict[str, Any]
    file_size: int
    allocated_size: int
    is_in_use: bool
    is_directory: bool
    is_deleted: bool
    parent_directory: int
    filename: str
    timestamps: Dict[str, datetime]


class NTFSParser(FileSystemParser):
    """
    NTFS file system parser.
    
    Features:
    - Boot sector parsing
    - MFT parsing ($MFT, $MFTMirr)
    - File and directory enumeration
    - Deleted file recovery
    - Timestamp extraction (SI, FN)
    - Data run parsing for fragmented files
    
    References:
    - NTFS Documentation: https://flatcap.org/linux-ntfs/ntfs/
    - MFT Structure: https://www.dfrws.org/ntfs-mft.php
    """
    
    def __init__(self, disk_reader: DiskReader, partition_offset: int = 0):
        """
        Initialize NTFS parser.
        
        Args:
            disk_reader: Disk reader for raw access
            partition_offset: Partition start offset
        """
        super().__init__(disk_reader, partition_offset)
        self._bytes_per_sector = 512
        self._sectors_per_cluster = 0
        self._bytes_per_cluster = 0
        self._mft_start_lcn = 0
        self._mft_record_size = MFT_RECORD_SIZE
        self._mft_size = 0
        self._cluster_size = 0
        self._volume_serial = None
        self._volume_name = ""
        self._mft_records: Dict[int, MFTRecord] = {}
        self._directory_tree: Dict[int, DirectoryEntry] = {}
    
    def initialize(self) -> bool:
        """Initialize parser and read boot sector."""
        try:
            # Read boot sector
            boot_sector = self._read_boot_sector()
            
            # Validate NTFS signature
            if boot_sector[3:11] != NTFS_SIGNATURE:
                raise FileSystemCorruptedError("Invalid NTFS signature")
            
            # Parse boot sector
            self._parse_boot_sector(boot_sector)
            
            # Read MFT
            self._read_mft()
            
            self._fs_info = self._create_filesystem_info()
            self._is_initialized = True
            
            logger.info(f"NTFS initialized: {self._volume_name} ({self._mft_size} records)")
            return True
            
        except Exception as e:
            raise FileSystemParserError(f"Failed to initialize NTFS: {e}")
    
    def get_filesystem_info(self) -> FileSystemInfo:
        """Get file system information."""
        if not self._is_initialized:
            raise FileSystemParserError("NTFS not initialized")
        return self._fs_info

    def parse_file_system(self) -> FileSystemInfo:
        """Initialize and parse MFT metadata for the common parser interface."""
        if not self._is_initialized:
            self.initialize()
        self.parse_metadata()
        return self._fs_info
    
    def parse_metadata(self) -> None:
        """Parse all MFT records."""
        if not self._is_initialized:
            raise FileSystemParserError("NTFS not initialized")
        
        logger.info(f"Parsing {self._mft_size} MFT records...")
        
        for i in range(self._mft_size):
            try:
                record = self._read_mft_record(i)
                if record:
                    self._mft_records[i] = record
            except Exception as e:
                logger.warning(f"Failed to parse MFT record {i}: {e}")
        
        logger.info(f"Parsed {len(self._mft_records)} MFT records")
    
    def enumerate_files(self) -> Iterator[FileEntry]:
        """Enumerate all files from MFT."""
        if not self._is_initialized:
            raise FileSystemParserError("NTFS not initialized")
        
        for record_num, record in self._mft_records.items():
            if not record.is_in_use:
                continue  # Skip unused records
            
            try:
                file_entry = self._mft_record_to_file_entry(record)
                if file_entry:
                    yield file_entry
            except Exception as e:
                logger.warning(f"Failed to convert MFT record {record_num}: {e}")
    
    def enumerate_directories(self) -> Iterator[DirectoryEntry]:
        """Enumerate directories."""
        if not self._is_initialized:
            raise FileSystemParserError("NTFS not initialized")
        
        for record_num, record in self._mft_records.items():
            if not record.is_directory:
                continue
            
            try:
                dir_entry = self._mft_record_to_directory_entry(record)
                if dir_entry:
                    yield dir_entry
            except Exception as e:
                logger.warning(f"Failed to convert directory {record_num}: {e}")
    
    def get_file_entry(self, reference: int) -> Optional[FileEntry]:
        """Get file by MFT record number."""
        if reference not in self._mft_records:
            return None
        
        record = self._mft_records[reference]
        return self._mft_record_to_file_entry(record)
    
    def get_file_data(self, file_entry: FileEntry) -> bytes:
        """Read file data from disk."""
        # Get MFT record
        mft_record = file_entry.metadata.get('mft_record')
        if mft_record is None:
            raise FileSystemParserError("MFT record not available")
        
        record = self._mft_records.get(mft_record)
        if not record:
            raise FileSystemParserError(f"MFT record {mft_record} not found")
        
        # Get data runs
        data_runs = record.attributes.get('data_runs', [])
        resident_data = record.attributes.get('resident_data', b'')
        if resident_data:
            return resident_data[:file_entry.file_size]
        if not data_runs:
            return b''
        
        # Read file data
        data = b''
        for vcn, lcn, length in data_runs:
            offset = self.partition_offset + (lcn * self._bytes_per_cluster)
            chunk = self.disk_reader.read(offset, length * self._bytes_per_cluster)
            data += chunk
        
        return data[:file_entry.file_size]
    
    def get_file_fragments(self, file_entry: FileEntry) -> List[Tuple[int, int]]:
        """Get fragmentation info."""
        mft_record = file_entry.metadata.get('mft_record')
        if mft_record is None:
            return []
        
        record = self._mft_records.get(mft_record)
        if not record:
            return []
        
        data_runs = record.attributes.get('data_runs', [])
        fragments = []
        
        for vcn, lcn, length in data_runs:
            offset = self.partition_offset + (lcn * self._bytes_per_cluster)
            size = length * self._bytes_per_cluster
            fragments.append((offset, size))
        
        return fragments
    
    def get_deleted_files(self) -> Iterator[FileEntry]:
        """Get deleted files from MFT."""
        if not self._is_initialized:
            raise FileSystemParserError("NTFS not initialized")
        
        for record_num, record in self._mft_records.items():
            if record.is_in_use:
                continue  # Skip allocated files
            
            try:
                file_entry = self._mft_record_to_file_entry(record)
                if file_entry:
                    yield file_entry
            except Exception as e:
                logger.warning(f"Failed to process deleted file {record_num}: {e}")
    
    def get_deleted_directories(self) -> Iterator[DirectoryEntry]:
        """Get deleted directories."""
        if not self._is_initialized:
            raise FileSystemParserError("NTFS not initialized")
        
        for record_num, record in self._mft_records.items():
            if not record.is_directory or record.is_in_use:
                continue
            
            try:
                dir_entry = self._mft_record_to_directory_entry(record)
                if dir_entry:
                    yield dir_entry
            except Exception as e:
                logger.warning(f"Failed to process deleted directory {record_num}: {e}")
    
    def build_directory_tree(self) -> Dict[str, DirectoryEntry]:
        """Build directory tree structure."""
        if not self._is_initialized:
            raise FileSystemParserError("NTFS not initialized")
        
        # Build tree by parent references
        tree = {}
        
        for record_num, record in self._mft_records.items():
            if not record.is_directory:
                continue
            
            dir_entry = self._mft_record_to_directory_entry(record)
            if dir_entry:
                tree[dir_entry.full_path] = dir_entry
        
        return tree
    
    def get_timeline_entries(self) -> Iterator[Dict[str, Any]]:
        """Extract timestamps for timeline analysis."""
        if not self._is_initialized:
            raise FileSystemParserError("NTFS not initialized")
        
        for record_num, record in self._mft_records.items():
            for timestamp_name, timestamp in record.timestamps.items():
                if not timestamp:
                    continue
                
                yield {
                    'timestamp': timestamp,
                    'type': timestamp_name,
                    'path': record.filename,
                    'record_number': record_num,
                    'is_deleted': record.is_deleted,
                    'is_directory': record.is_directory,
                }
    
    def verify_integrity(self) -> bool:
        """Verify NTFS structural integrity."""
        if not self._is_initialized:
            return False
        
        # Check boot sector
        try:
            boot_sector = self._read_boot_sector()
            if boot_sector[3:11] != NTFS_SIGNATURE:
                return False
        except:
            return False
        
        # Check MFT
        if len(self._mft_records) == 0:
            return False
        
        return True
    
    @property
    def fs_type(self) -> FileSystemType:
        """Get file system type."""
        return FileSystemType.NTFS
    
    def _read_boot_sector(self) -> bytes:
        """Read and validate boot sector."""
        offset = self.partition_offset
        boot_sector = self.disk_reader.read(offset, NTFS_BOOT_SECTOR_SIZE)
        
        if len(boot_sector) < NTFS_BOOT_SECTOR_SIZE:
            raise FileSystemCorruptedError("Boot sector too small")
        
        return boot_sector
    
    def _parse_boot_sector(self, boot_sector: bytes) -> None:
        """Parse boot sector parameters."""
        # Bytes per sector
        self._bytes_per_sector = struct.unpack('<H', boot_sector[11:13])[0]
        
        # Sectors per cluster
        self._sectors_per_cluster = boot_sector[13]
        self._bytes_per_cluster = self._bytes_per_sector * self._sectors_per_cluster
        
        # MFT start cluster
        self._mft_start_lcn = struct.unpack('<Q', boot_sector[48:56])[0]
        
        # MFT record size (negative = multiplier, positive = bytes)
        mft_record_size_byte = boot_sector[64]
        if mft_record_size_byte < 128:
            self._mft_record_size = mft_record_size_byte
        else:
            self._mft_record_size = 1 << (256 - mft_record_size_byte)
        
        # MFT size (in records)
        mft_size_clusters = struct.unpack('<Q', boot_sector[56:64])[0]
        self._mft_size = (mft_size_clusters * self._bytes_per_cluster) // self._mft_record_size
        
        # Volume serial
        self._volume_serial = struct.unpack('<Q', boot_sector[72:80])[0]
        
        logger.info(f"NTFS boot sector parsed: {self._bytes_per_sector} B/sector, {self._bytes_per_cluster} B/cluster")
    
    def _create_filesystem_info(self) -> FileSystemInfo:
        """Create file system info object."""
        return FileSystemInfo(
            fs_type=FileSystemType.NTFS,
            volume_name=self._volume_name,
            volume_serial=str(self._volume_serial),
            total_clusters=self._mft_size,
            free_clusters=0,  # Would need to parse $Bitmap
            cluster_size=self._bytes_per_cluster,
            bytes_per_sector=self._bytes_per_sector,
            sectors_per_cluster=self._sectors_per_cluster,
            mft_location=self._mft_start_lcn,
            root_directory_cluster=5,  # MFT record 5 is root
            flags=0,
            created_time=None,
            last_mounted_time=None,
            unmounted_cleanly=True,
            additional_info={
                'mft_record_size': self._mft_record_size,
            }
        )
    
    def _read_mft(self) -> None:
        """Read MFT records."""
        # MFT starts at cluster specified in boot sector
        mft_offset = self.partition_offset + (self._mft_start_lcn * self._bytes_per_cluster)

        # The boot sector does not contain the MFT length. Until record 0 is
        # decoded, use the readable image extent as a conservative bound.
        remaining = max(0, self.disk_reader.total_size - mft_offset)
        self._mft_size = min(1024 * 1024, remaining // self._mft_record_size)
        if self._mft_size == 0:
            raise FileSystemCorruptedError("MFT is outside the readable source")
        mft_data = self.disk_reader.read(
            mft_offset, min(self._mft_record_size, remaining)
        )
        
        logger.info(f"Read MFT at offset {mft_offset:#x}, {len(mft_data)} bytes")
    
    def _read_mft_record(self, record_number: int) -> Optional[MFTRecord]:
        """Read single MFT record."""
        mft_offset = self.partition_offset + (self._mft_start_lcn * self._bytes_per_cluster)
        record_offset = mft_offset + (record_number * self._mft_record_size)
        
        record_data = self.disk_reader.read(record_offset, self._mft_record_size)
        
        if len(record_data) < 42:
            return None
        
        # Parse MFT record header
        signature = record_data[0:4]
        if signature != b'FILE':
            return None  # Not a valid MFT record
        
        # Parse fields
        update_sequence = struct.unpack('<H', record_data[4:6])[0]
        sequence_number = struct.unpack('<H', record_data[6:8])[0]
        link_count = struct.unpack('<H', record_data[16:18])[0]
        attributes_offset = struct.unpack('<H', record_data[18:20])[0]
        total_size = struct.unpack('<I', record_data[20:24])[0]
        first_attribute_offset = struct.unpack('<H', record_data[24:26])[0]
        record_flags = struct.unpack('<H', record_data[22:24])[0]
        base_record = struct.unpack('<Q', record_data[26:34])[0]
        
        is_in_use = bool(record_flags & 0x01)
        is_directory = bool(record_flags & 0x02)
        is_deleted = not is_in_use
        
        # Parse attributes
        attributes = {}
        offset = attributes_offset
        file_size = 0
        allocated_size = 0
        parent_directory = 0
        filename = ""
        timestamps = {}
        data_runs = []
        resident_data = b''
        
        while offset < self._mft_record_size - 4:
            attr_type = struct.unpack('<I', record_data[offset:offset+4])[0]
            if attr_type == 0xFFFFFFFF:
                break
            
            attr_length = struct.unpack('<I', record_data[offset+4:offset+8])[0]
            if attr_length == 0 or offset + attr_length > len(record_data):
                break
            
            # Parse attribute
            non_resident = bool(record_data[offset + 8])
            attr_name_length = record_data[offset + 9]
            attr_name_offset = struct.unpack('<H', record_data[offset+10:offset+12])[0]
            attribute_flags = struct.unpack('<H', record_data[offset+12:offset+14])[0]
            attr_instance = struct.unpack('<H', record_data[offset+14:offset+16])[0]
            
            # Get attribute content
            content_offset = offset + struct.unpack('<H', record_data[offset+16:offset+18])[0]
            content_length = attr_length - struct.unpack('<H', record_data[offset+16:offset+18])[0]
            
            # Parse specific attribute types
            if attr_type == AttributeType.STANDARD_INFORMATION:
                timestamps = self._parse_standard_information(record_data, content_offset, content_length)
            
            elif attr_type == AttributeType.FILE_NAME:
                fn_info = self._parse_file_name(record_data, content_offset, content_length)
                if fn_info:
                    filename = fn_info['filename']
                    parent_directory = fn_info['parent_directory']
            
            elif attr_type == AttributeType.DATA:
                if non_resident:
                    data_runs = self._parse_data_runs(record_data, content_offset, content_length)
                    allocated_size = struct.unpack('<Q', record_data[content_offset+32:content_offset+40])[0]
                    file_size = struct.unpack('<Q', record_data[content_offset+40:content_offset+48])[0]
                else:
                    value_length = struct.unpack('<I', record_data[offset+16:offset+20])[0]
                    file_size = value_length
                    allocated_size = value_length
                    resident_data = record_data[content_offset:content_offset+value_length]
            
            offset += attr_length
        
        return MFTRecord(
            record_number=record_number,
            sequence_number=sequence_number,
            flags=record_flags,
            link_count=link_count,
            attributes_offset=attributes_offset,
            first_attribute_offset=first_attribute_offset,
            base_record=base_record,
            attributes={
                'timestamps': timestamps,
                'data_runs': data_runs,
                'resident_data': resident_data,
            },
            file_size=file_size,
            allocated_size=allocated_size,
            is_in_use=bool(record_flags & 0x01),
            is_directory=bool(record_flags & 0x02),
            is_deleted=is_deleted,
            parent_directory=parent_directory,
            filename=filename,
            timestamps=timestamps,
        )
    
    def _parse_standard_information(self, data: bytes, offset: int, length: int) -> Dict[str, datetime]:
        """Parse $STANDARD_INFORMATION attribute."""
        timestamps = {}
        
        try:
            # Creation time
            timestamps['created'] = self._parse_filetime(data[offset:offset+8])
            # Modified time
            timestamps['modified'] = self._parse_filetime(data[offset+8:offset+16])
            # Record change time
            timestamps['changed'] = self._parse_filetime(data[offset+16:offset+24])
            # Last access time
            timestamps['accessed'] = self._parse_filetime(data[offset+24:offset+32])
        except:
            pass
        
        return timestamps
    
    def _parse_file_name(self, data: bytes, offset: int, length: int) -> Optional[Dict[str, Any]]:
        """Parse $FILE_NAME attribute."""
        try:
            parent_directory = struct.unpack('<Q', data[offset:offset+8])[0]
            parent_directory &= 0x0000FFFFFFFFFFFF  # Mask sequence number
            
            name_length = data[offset + 64]
            name_type = data[offset + 65]
            name = data[offset+66:offset+66+name_length].decode('utf-16-le', errors='ignore')
            
            # Namespace: 0=POSIX, 1=Win32, 2=DOS 8.3, 3=Win32+DOS
            
            return {
                'parent_directory': parent_directory,
                'filename': name,
                'name_type': name_type,
            }
        except:
            return None
    
    def _parse_data_runs(self, data: bytes, offset: int, length: int) -> List[Tuple[int, int, int]]:
        """Parse data runs (non-resident data)."""
        runs = []
        
        try:
            starting_vcn = struct.unpack('<Q', data[offset:offset+8])[0]
            data_runs_offset = struct.unpack('<H', data[offset+16:offset+18])[0]
            pos = offset + data_runs_offset
            current_lcn = 0
            current_vcn = starting_vcn
            end = offset + length
            
            while pos < end:
                run_header = data[pos]
                pos += 1
                if run_header == 0:
                    break
                
                length_size = run_header & 0x0F
                offset_size = (run_header >> 4) & 0x0F
                
                if length_size == 0:
                    break
                
                run_length = int.from_bytes(data[pos:pos+length_size], 'little')
                pos += length_size
                
                run_offset_raw = data[pos:pos+offset_size]
                pos += offset_size
                run_offset = int.from_bytes(run_offset_raw, 'little', signed=True)
                current_lcn += run_offset
                
                runs.append((current_vcn, current_lcn, run_length))
                current_vcn += run_length
        except Exception:
            pass
        
        return runs
    
    def _parse_filetime(self, data: bytes) -> Optional[datetime]:
        """Parse Windows FILETIME to datetime."""
        try:
            filetime = struct.unpack('<Q', data)[0]
            if filetime == 0:
                return None
            
            # Convert to seconds since epoch
            seconds = (filetime - 116444736000000000) / 10000000
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except:
            return None
    
    def _mft_record_to_file_entry(self, record: MFTRecord) -> Optional[FileEntry]:
        """Convert MFT record to FileEntry."""
        from ...core.models.file_entry import FileCategory
        
        # Determine category from extension
        ext = Path(record.filename).suffix.lower() if record.filename else ''
        category = self._extension_to_category(ext)
        
        status = FileStatus.DELETED if record.is_deleted else FileStatus.EXISTING
        confidence = RecoveryConfidence.EXCELLENT if record.is_in_use else RecoveryConfidence.HIGH
        
        data_runs = record.attributes.get('data_runs', []) or []
        fragments = []
        first_offset = None
        
        for _, lcn, run_length in data_runs:
            if lcn is None:
                continue
            offset = self.partition_offset + (lcn * self._bytes_per_cluster)
            size = run_length * self._bytes_per_cluster
            fragments.append((offset, size))
            if first_offset is None:
                first_offset = offset
        
        return FileEntry(
            file_id=f"mft_{record.record_number}",
            filename=record.filename or f"[Deleted]_{record.record_number}",
            extension=Path(record.filename).suffix.lstrip('.') if record.filename else '',
            file_size=record.file_size,
            file_category=category,
            recovery_confidence=confidence,
            status=status,
            file_signature=None,
            offset=first_offset,
            fragments=fragments,
            created_time=record.timestamps.get('created'),
            modified_time=record.timestamps.get('modified'),
            accessed_time=record.timestamps.get('accessed'),
            metadata={
                'mft_record': record.record_number,
                'parent_directory': record.parent_directory,
                'is_directory': record.is_directory,
                'data_runs': data_runs,
            },
        )
    
    def _mft_record_to_directory_entry(self, record: MFTRecord) -> Optional[DirectoryEntry]:
        """Convert MFT record to DirectoryEntry."""
        if not record.is_directory:
            return None
        
        return DirectoryEntry(
            name=record.filename or f"[Deleted]_{record.record_number}",
            parent_path="",  # Would need to resolve parent
            full_path=f"/{record.filename}",
            is_directory=True,
            is_deleted=record.is_deleted,
            file_size=record.file_size,
            allocated_size=record.allocated_size,
            attributes={'mft_record': record.record_number},
            timestamps=record.timestamps,
            metadata_reference=record.record_number,
            children=[],
        )
    
    def _extension_to_category(self, extension: str) -> FileCategory:
        """Map extension to category."""
        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic', '.raw', '.cr2', '.nef', '.arw'}
        video_exts = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.mpeg', '.mpg'}
        document_exts = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.rtf', '.txt'}
        archive_exts = {'.zip', '.rar', '.7z', '.gz', '.tar', '.bz2'}
        audio_exts = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma'}
        
        extension = extension.lower()
        
        if extension in image_exts:
            return FileCategory.IMAGE
        elif extension in video_exts:
            return FileCategory.VIDEO
        elif extension in document_exts:
            return FileCategory.DOCUMENT
        elif extension in archive_exts:
            return FileCategory.ARCHIVE
        elif extension in audio_exts:
            return FileCategory.AUDIO
        else:
            return FileCategory.OTHER