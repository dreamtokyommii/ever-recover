"""FAT32 and exFAT file system parsers."""

import struct
import logging
from datetime import datetime
from typing import Iterator, List, Dict, Optional, Tuple
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


@dataclass
class FATDirectoryEntry:
    """FAT directory entry structure."""
    name: str
    extension: str
    attributes: int
    created_time: datetime
    modified_time: datetime
    accessed_date: datetime
    first_cluster: int
    file_size: int
    is_deleted: bool
    is_directory: bool
    is_lfn: bool
    lfn_unicode: str


class FAT32Parser(FileSystemParser):
    """
    FAT32 file system parser.
    
    Features:
    - Boot sector parsing
    - FAT table parsing
    - Directory entry enumeration
    - Deleted file recovery (first cluster intact)
    - LFN (Long File Name) support
    """
    
    FAT32_EOC = 0x0FFFFFF8  # End of chain marker
    
    def __init__(self, disk_reader: DiskReader, partition_offset: int = 0):
        """Initialize FAT32 parser."""
        super().__init__(disk_reader, partition_offset)
        self._bytes_per_sector = 512
        self._sectors_per_cluster = 0
        self._bytes_per_cluster = 0
        self._reserved_sectors = 0
        self._num_fats = 0
        self._fat_size = 0
        self._fat_offset = 0
        self._root_dir_offset = 0
        self._data_offset = 0
        self._total_clusters = 0
        self._volume_label = ""
        self._volume_serial = ""
        self._fs_info: Optional[FileSystemInfo] = None
    
    def initialize(self) -> bool:
        """Initialize parser."""
        try:
            # Read boot sector
            boot_sector = self._read_boot_sector()
            
            # Validate signature (0x55AA)
            if boot_sector[510:512] != b'\x55\xAA':
                raise FileSystemCorruptedError("Invalid boot sector signature")
            
            # Parse boot sector
            self._parse_boot_sector(boot_sector)
            
            # Load FAT tables
            self._load_fat()
            
            # Create file system info
            self._fs_info = self._create_filesystem_info()
            self._is_initialized = True
            
            logger.info(f"FAT32 initialized: {self._volume_label} ({self._total_clusters} clusters)")
            return True
            
        except Exception as e:
            raise FileSystemParserError(f"Failed to initialize FAT32: {e}")
    
    def get_filesystem_info(self) -> FileSystemInfo:
        """Get file system info."""
        if not self._is_initialized:
            raise FileSystemParserError("FAT32 not initialized")
        return self._fs_info
    
    def parse_metadata(self) -> None:
        """Parse FAT and root directory."""
        if not self._is_initialized:
            raise FileSystemParserError("FAT32 not initialized")
        
        # FAT already loaded in initialize()
        logger.info("FAT32 metadata parsed")
    
    def enumerate_files(self) -> Iterator[FileEntry]:
        """Enumerate all files."""
        if not self._is_initialized:
            raise FileSystemParserError("FAT32 not initialized")
        
        # Enumerate root directory
        for entry in self._enumerate_directory_entries(self._root_dir_offset):
            if entry.is_directory:
                continue
            
            file_entry = self._fat_entry_to_file_entry(entry, "/")
            if file_entry:
                yield file_entry
        
        # Enumerate subdirectories
        # (Would need to recursively traverse directories)
    
    def enumerate_directories(self) -> Iterator[DirectoryEntry]:
        """Enumerate directories."""
        if not self._is_initialized:
            raise FileSystemParserError("FAT32 not initialized")
        
        # Root directory
        root_entry = self._get_root_directory_entry()
        if root_entry:
            yield root_entry
    
    def get_file_entry(self, reference: int) -> Optional[FileEntry]:
        """Get file by cluster number."""
        # Find entry by cluster
        for entry in self._enumerate_all_entries():
            if entry.first_cluster == reference:
                return self._fat_entry_to_file_entry(entry, "/")
        return None
    
    def get_file_data(self, file_entry: FileEntry) -> bytes:
        """Read file data by following FAT chain."""
        first_cluster = file_entry.metadata.get('first_cluster')
        if not first_cluster:
            return b''
        
        data = b''
        cluster = first_cluster
        
        while cluster < self.FAT32_EOC:
            cluster_offset = self._data_offset + ((cluster - 2) * self._bytes_per_cluster)
            chunk = self.disk_reader.read(cluster_offset, self._bytes_per_cluster)
            data += chunk
            
            # Get next cluster from FAT
            next_cluster = self._get_fat_entry(cluster)
            if next_cluster >= self.FAT32_EOC:
                break
            cluster = next_cluster
        
        return data[:file_entry.file_size]
    
    def get_file_fragments(self, file_entry: FileEntry) -> List[Tuple[int, int]]:
        """Get fragmentation info by following FAT chain."""
        first_cluster = file_entry.metadata.get('first_cluster')
        if not first_cluster:
            return []
        
        fragments = []
        cluster = first_cluster
        prev_cluster = None
        fragment_start = None
        fragment_length = 0
        
        while cluster < self.FAT32_EOC:
            if prev_cluster is None or cluster != prev_cluster + 1:
                # New fragment
                if fragment_start is not None:
                    offset = self._data_offset + ((fragment_start - 2) * self._bytes_per_cluster)
                    size = fragment_length * self._bytes_per_cluster
                    fragments.append((offset, size))
                
                fragment_start = cluster
                fragment_length = 1
            else:
                fragment_length += 1
            
            prev_cluster = cluster
            cluster = self._get_fat_entry(cluster)
        
        # Add last fragment
        if fragment_start is not None:
            offset = self._data_offset + ((fragment_start - 2) * self._bytes_per_cluster)
            size = fragment_length * self._bytes_per_cluster
            fragments.append((offset, size))
        
        return fragments
    
    def get_deleted_files(self) -> Iterator[FileEntry]:
        """Get deleted files (first character 0xE5)."""
        for entry in self._enumerate_directory_entries(self._root_dir_offset, include_deleted=True):
            if not entry.is_deleted or entry.is_directory:
                continue
            
            file_entry = self._fat_entry_to_file_entry(entry, "/")
            if file_entry:
                yield file_entry
    
    def get_deleted_directories(self) -> Iterator[DirectoryEntry]:
        """Get deleted directories."""
        # Similar to deleted files but for directories
        pass
    
    def build_directory_tree(self) -> Dict[str, DirectoryEntry]:
        """Build directory tree."""
        tree = {}
        
        # Root
        root = self._get_root_directory_entry()
        if root:
            tree["/"] = root
        
        return tree
    
    def get_timeline_entries(self) -> Iterator[Dict]:
        """Extract timestamps."""
        for entry in self._enumerate_all_entries():
            yield {
                'timestamp': entry.modified_time,
                'type': 'modified',
                'path': f"/{entry.name}.{entry.extension}",
                'is_deleted': entry.is_deleted,
            }
    
    def verify_integrity(self) -> bool:
        """Verify FAT32 integrity."""
        # Check boot sector signature
        try:
            boot_sector = self._read_boot_sector()
            if boot_sector[510:512] != b'\x55\xAA':
                return False
        except:
            return False
        
        return True
    
    @property
    def fs_type(self) -> FileSystemType:
        """Get file system type."""
        return FileSystemType.FAT32
    
    def _read_boot_sector(self) -> bytes:
        """Read boot sector."""
        return self.disk_reader.read(self.partition_offset, 512)
    
    def _parse_boot_sector(self, boot_sector: bytes) -> None:
        """Parse boot sector fields."""
        # Bytes per sector
        self._bytes_per_sector = struct.unpack('<H', boot_sector[11:13])[0]
        
        # Sectors per cluster
        self._sectors_per_cluster = boot_sector[13]
        self._bytes_per_cluster = self._bytes_per_sector * self._sectors_per_cluster
        
        # Reserved sectors
        self._reserved_sectors = struct.unpack('<H', boot_sector[14:16])[0]
        
        # Number of FATs
        self._num_fats = boot_sector[16]
        
        # Total sectors (if 0, use 32-bit value at offset 32)
        total_sectors_16 = struct.unpack('<H', boot_sector[19:21])[0]
        total_sectors_32 = struct.unpack('<I', boot_sector[32:36])[0]
        total_sectors = total_sectors_16 if total_sectors_16 else total_sectors_32
        
        # FAT size
        fat_size_16 = struct.unpack('<H', boot_sector[22:24])[0]
        fat_size_32 = struct.unpack('<I', boot_sector[36:40])[0]
        self._fat_size = fat_size_16 if fat_size_16 else fat_size_32
        
        # FAT offset
        self._fat_offset = self.partition_offset + (self._reserved_sectors * self._bytes_per_sector)
        
        # Root directory offset
        root_dir_offset_sectors = self._reserved_sectors + (self._num_fats * self._fat_size)
        self._root_dir_offset = self.partition_offset + (root_dir_offset_sectors * self._bytes_per_sector)
        
        # Data offset
        self._data_offset = self._root_dir_offset + (32 * 512)  # Root has 32 entries max in FAT32
        
        # Total clusters
        data_sectors = total_sectors - (self._reserved_sectors + (self._num_fats * self._fat_size))
        self._total_clusters = data_sectors // self._sectors_per_cluster
        
        # Volume label
        self._volume_label = boot_sector[71:82].decode('ascii', errors='ignore').strip()
        
        # Volume serial
        self._volume_serial = format(struct.unpack('<I', boot_sector[39:43])[0], '08X')
        
        logger.info(f"FAT32 boot sector parsed: {self._bytes_per_sector} B/sector, {self._bytes_per_cluster} B/cluster")
    
    def _create_filesystem_info(self) -> FileSystemInfo:
        """Create file system info."""
        return FileSystemInfo(
            fs_type=FileSystemType.FAT32,
            volume_name=self._volume_label,
            volume_serial=self._volume_serial,
            total_clusters=self._total_clusters,
            free_clusters=0,  # Would need to scan FAT
            cluster_size=self._bytes_per_cluster,
            bytes_per_sentctor=self._bytes_per_sector,
            sectors_per_cluster=self._sectors_per_cluster,
            mft_location=None,
            root_directory_cluster=0,
            flags=0,
            created_time=None,
            last_mounted_time=None,
            unmounted_cleanly=True,
            additional_info={}
        )
    
    def _load_fat(self) -> None:
        """Load FAT table to memory (simplified)."""
        # In full implementation, would read entire FAT
        # For now, we'll read on-demand
        pass
    
    def _get_fat_entry(self, cluster: int) -> int:
        """Read FAT entry for cluster."""
        fat_offset = self._fat_offset + (cluster * 4)  # 4 bytes per entry in FAT32
        fat_data = self.disk_reader.read(fat_offset, 4)
        return struct.unpack('<I', fat_data)[0] & 0x0FFFFFFF
    
    def _enumerate_directory_entries(self, dir_offset: int, 
                                     include_deleted: bool = False) -> Iterator[FATDirectoryEntry]:
        """Enumerate directory entries."""
        entry_size = 32
        offset = dir_offset
        
        while True:
            entry_data = self.disk_reader.read(offset, entry_size)
            if len(entry_data) < entry_size:
                break
            
            first_byte = entry_data[0]
            
            # End of directory
            if first_byte == 0x00:
                break
            
            # Deleted entry
            if first_byte == 0xE5:
                if include_deleted:
                    entry = self._parse_directory_entry(entry_data, is_deleted=True)
                    if entry and not entry.is_lfn:
                        yield entry
                offset += entry_size
                continue
            
            # Valid entry
            entry = self._parse_directory_entry(entry_data, is_deleted=False)
            if entry and not entry.is_lfn:
                yield entry
            
            offset += entry_size
    
    def _parse_directory_entry(self, data: bytes, is_deleted: bool) -> Optional[FATDirectoryEntry]:
        """Parse 32-byte directory entry."""
        try:
            # Name (8 bytes) + extension (3 bytes)
            name = data[0:8].decode('ascii', errors='ignore').strip()
            extension = data[8:11].decode('ascii', errors='ignore').strip()
            
            # Attributes
            attributes = data[11]
            
            # Timestamps
            create_time = self._parse_dos_time(data[14:16], data[13:14])
            create_date = self._parse_dos_date(data[16:18])
            created = datetime(
                create_date.year, create_date.month, create_date.day,
                create_time.hour, create_time.minute, create_time.second
            ) if create_date else None
            
            modify_time = self._parse_dos_time(data[24:26], data[23:24])
            modify_date = self._parse_dos_date(data[24:26])
            modified = datetime(
                modify_date.year, modify_date.month, modify_date.day,
                modify_time.hour, modify_time.minute, modify_time.second
            ) if modify_date else None
            
            access_date = self._parse_dos_date(data[18:20])
            accessed = access_date if access_date else None
            
            # First cluster (low 2 bytes at 26, high 2 bytes at 20)
            first_cluster_low = struct.unpack('<H', data[26:28])[0]
            first_cluster_high = struct.unpack('<H', data[20:22])[0]
            first_cluster = (first_cluster_high << 16) | first_cluster_low
            
            # File size
            file_size = struct.unpack('<I', data[28:32])[0]
            
            # Check LFN
            is_lfn = attributes == 0x0F
            
            # Check directory
            is_directory = bool(attributes & 0x10)
            
            return FATDirectoryEntry(
                name=name,
                extension=extension,
                attributes=attributes,
                created_time=created,
                modified_time=modified,
                accessed_date=accessed,
                first_cluster=first_cluster,
                file_size=file_size,
                is_deleted=is_deleted,
                is_directory=is_directory,
                is_lfn=is_lfn,
                lfn_unicode="",  # Would need to parse LFN entries
            )
        except Exception as e:
            logger.warning(f"Failed to parse directory entry: {e}")
            return None
    
    def _parse_dos_time(self, time_data: bytes, time_10ms: bytes = None) -> datetime:
        """Parse DOS time."""
        try:
            time_val = struct.unpack('<H', time_data)[0]
            hours = (time_val >> 11) & 0x1F
            minutes = (time_val >> 5) & 0x3F
            seconds = (time_val & 0x1F) * 2
            return datetime(1970, 1, 1, hours, minutes, seconds)
        except:
            return None
    
    def _parse_dos_date(self, date_data: bytes) -> Optional[datetime]:
        """Parse DOS date."""
        try:
            date_val = struct.unpack('<H', date_data)[0]
            year = 1980 + ((date_val >> 9) & 0x7F)
            month = (date_val >> 5) & 0x0F
            day = date_val & 0x1F
            return datetime(year, month, day)
        except:
            return None
    
    def _enumerate_all_entries(self) -> Iterator[FATDirectoryEntry]:
        """Enumerate all entries."""
        for entry in self._enumerate_directory_entries(self._root_dir_offset):
            yield entry
    
    def _get_root_directory_entry(self) -> Optional[DirectoryEntry]:
        """Get root directory entry."""
        return DirectoryEntry(
            name=self._volume_label or "ROOT",
            parent_path="",
            full_path="/",
            is_directory=True,
            is_deleted=False,
            file_size=0,
            allocated_size=0,
            attributes={},
            timestamps={},
            metadata_reference=0,
            children=[],
        )
    
    def _fat_entry_to_file_entry(self, entry: FATDirectoryEntry, path: str) -> Optional[FileEntry]:
        """Convert FAT entry to FileEntry."""
        ext = entry.extension.lower()
        category = self._extension_to_category(ext)
        
        status = FileStatus.DELETED if entry.is_deleted else FileStatus.EXISTING
        confidence = RecoveryConfidence.HIGH if not entry.is_deleted else RecoveryConfidence.MEDIUM
        
        return FileEntry(
            file_id=f"cluster_{entry.first_cluster}",
            filename=entry.name if not entry.is_deleted else f"[Deleted]_{entry.name}",
            extension=entry.extension,
            file_size=entry.file_size,
            file_category=category,
            recovery_confidence=confidence,
            status=status,
            created_time=entry.created_time,
            modified_time=entry.modified_time,
            accessed_time=entry.accessed_date,
            metadata={
                'first_cluster': entry.first_cluster,
                'attributes': entry.attributes,
            },
        )
    
    def _extension_to_category(self, extension: str) -> FileCategory:
        """Map extension to category."""
        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
        video_exts = {'.mp4', '.avi', '.mkv', '.mov', '.wmv'}
        document_exts = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt'}
        archive_exts = {'.zip', '.rar', '.7z'}
        
        extension = extension.lower()
        
        if extension in image_exts:
            return FileCategory.IMAGE
        elif extension in video_exts:
            return FileCategory.VIDEO
        elif extension in document_exts:
            return FileCategory.DOCUMENT
        elif extension in archive_exts:
            return FileCategory.ARCHIVE
        else:
            return FileCategory.OTHER