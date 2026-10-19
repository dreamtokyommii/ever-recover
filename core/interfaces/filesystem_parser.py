"""Abstract interface for file system parsing operations."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Iterator, Any, Set
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from enum import Enum, auto

from ..models.file_entry import FileEntry, FileStatus, FileCategory, RecoveryConfidence


class FileSystemType(Enum):
    """File system types (mirrors models.device for interface independence)."""
    NTFS = auto()
    FAT32 = auto()
    EXFAT = auto()
    EXT4 = auto()
    APFS = auto()
    HFS_PLUS = auto()
    UNKNOWN = auto()


@dataclass
class FileSystemInfo:
    """File system metadata and superblock information."""
    fs_type: FileSystemType
    volume_name: str
    volume_serial: Optional[str]
    total_clusters: int
    free_clusters: int
    cluster_size: int
    bytes_per_sector: int
    sectors_per_cluster: int
    mft_location: Optional[int]  # NTFS-specific
    root_directory_cluster: int
    flags: int
    created_time: Optional[datetime]
    last_mounted_time: Optional[datetime]
    unmounted_cleanly: bool
    additional_info: Dict[str, Any]


@dataclass
class DirectoryEntry:
    """Directory entry from file system metadata."""
    name: str
    parent_path: str
    full_path: str
    is_directory: bool
    is_deleted: bool
    file_size: int
    allocated_size: int
    attributes: Dict[str, Any]
    timestamps: Dict[str, datetime]
    metadata_reference: int  # MFT record, inode, etc.
    children: List['DirectoryEntry']


@dataclass
class MFTEntry:
    """NTFS Master File Table entry."""
    record_number: int
    sequence_number: int
    flags: int
    is_in_use: bool
    is_directory: bool
    is_deleted: bool
    file_size: int
    allocated_size: int
    timestamps: Dict[str, datetime]  # $STANDARD_INFORMATION
    filenames: List[str]  # $FILE_NAME attributes
    data_runs: List[tuple[int, int, int]]  # (vcn, lcn, length)
    security_descriptor: Optional[bytes]
    extended_attributes: Optional[bytes]


@dataclass
class InodeEntry:
    """EXT4 inode entry."""
    inode_number: int
    mode: int
    uid: int
    gid: int
    size: int
    atime: datetime
    ctime: datetime
    mtime: datetime
    dtime: datetime  # Deletion time
    block_pointers: List[int]
    flags: int
    links_count: int
    is_directory: bool
    is_deleted: bool
    file_type: int


class FileSystemParserError(Exception):
    """Base exception for file system parsing."""
    pass


class FileSystemCorruptedError(FileSystemParserError):
    """Raised when file system structure is corrupted."""
    pass


class FileSystemParser(ABC):
    """
    Abstract base class for file system parsers.
    
    This interface provides unified access to different file systems:
    - NTFS: MFT parsing, $MFT, $MFTMirr, $Bitmap
    - FAT32/exFAT: FAT table, directory entries
    - EXT4: Inode table, block groups, bitmaps
    - APFS/HFS+: Catalog files, extents
    
    Implementations:
    - NTFSParser
    - FAT32Parser
    - exFATParser
    - EXT4Parser
    - APFSParser
    - HFSPlusParser
    """
    
    def __init__(self, disk_reader: 'DiskReader', partition_offset: int = 0):
        """
        Initialize file system parser.
        
        Args:
            disk_reader: Disk reader instance for raw access
            partition_offset: Partition start offset (for logical volumes)
        """
        from .disk_reader import DiskReader
        self.disk_reader = disk_reader
        self.partition_offset = partition_offset
        self._is_initialized = False
        self._fs_info: Optional[FileSystemInfo] = None
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize parser and read file system metadata.
        
        Returns:
            True if initialization successful
            
        Raises:
            FileSystemCorruptedError: If file system is corrupted
            FileSystemParserError: For other initialization failures
        """
        pass
    
    @abstractmethod
    def get_filesystem_info(self) -> FileSystemInfo:
        """Get file system information and superblock data."""
        pass
    
    @abstractmethod
    def parse_metadata(self) -> None:
        """Parse all file system metadata structures."""
        pass
    
    @abstractmethod
    def enumerate_files(self) -> Iterator[FileEntry]:
        """
        Enumerate all files from file system metadata.
        
        Yields:
            FileEntry objects for all files (including deleted)
        """
        pass
    
    @abstractmethod
    def enumerate_directories(self) -> Iterator[DirectoryEntry]:
        """
        Enumerate directory structure.
        
        Yields:
            DirectoryEntry objects
        """
        pass
    
    @abstractmethod
    def get_file_entry(self, reference: int) -> Optional[FileEntry]:
        """
        Get file entry by metadata reference (MFT record, inode, etc.).
        
        Args:
            reference: Metadata reference number
            
        Returns:
            FileEntry or None if not found
        """
        pass
    
    @abstractmethod
    def get_file_data(self, file_entry: FileEntry) -> bytes:
        """
        Read file data from disk.
        
        Args:
            file_entry: File entry to read
            
        Returns:
            File content bytes
            
        Raises:
            FileSystemParserError: If data cannot be read
        """
        pass
    
    @abstractmethod
    def get_file_fragments(self, file_entry: FileEntry) -> List[tuple[int, int]]:
        """
        Get fragmentation information for a file.
        
        Args:
            file_entry: File entry to analyze
            
        Returns:
            List of (offset, size) tuples representing fragments
        """
        pass
    
    @abstractmethod
    def get_deleted_files(self) -> Iterator[FileEntry]:
        """
        Get all deleted files from file system metadata.
        
        Yields:
            FileEntry objects for deleted files only
        """
        pass
    
    @abstractmethod
    def get_deleted_directories(self) -> Iterator[DirectoryEntry]:
        """
        Get all deleted directories.
        
        Yields:
            DirectoryEntry objects for deleted directories
        """
        pass
    
    @abstractmethod
    def build_directory_tree(self) -> Dict[str, DirectoryEntry]:
        """
        Build complete directory tree structure.
        
        Returns:
            Dictionary mapping paths to DirectoryEntry objects
        """
        pass
    
    @abstractmethod
    def get_timeline_entries(self) -> Iterator[Dict[str, Any]]:
        """
        Extract all timestamps for timeline analysis.
        
        Yields:
            Timeline entry dictionaries with timestamp, type, path, etc.
        """
        pass
    
    @abstractmethod
    def verify_integrity(self) -> bool:
        """
        Verify file system structural integrity.
        
        Returns:
            True if file system appears structurally sound
        """
        pass
    
    def parse_file_system(self) -> FileSystemInfo:
        """
        Initialize the parser and parse the file system metadata.
        
        Returns:
            FileSystemInfo for the parsed file system.
        """
        if not self._is_initialized:
            self.initialize()
        self.parse_metadata()
        return self.get_filesystem_info()
    
    @property
    @abstractmethod
    def fs_type(self) -> FileSystemType:
        """Get file system type."""
        pass
    
    @property
    def is_initialized(self) -> bool:
        """Check if parser is initialized."""
        return self._is_initialized
    
    @property
    def partition_start(self) -> int:
        """Get partition start offset."""
        return self.partition_offset
    
    def get_path(self, file_entry: FileEntry) -> str:
        """Get full path for file entry."""
        if file_entry.parent_directory:
            return f"{file_entry.parent_directory}/{file_entry.filename}"
        return file_entry.filename
    
    def is_file_allocated(self, file_entry: FileEntry) -> bool:
        """Check if file is in allocated space."""
        return file_entry.status == FileStatus.EXISTING
    
    def is_file_deleted(self, file_entry: FileEntry) -> bool:
        """Check if file is deleted."""
        return file_entry.status == FileStatus.DELETED
    
    def calculate_recovery_confidence(self, file_entry: FileEntry) -> RecoveryConfidence:
        """
        Calculate recovery confidence based on file system metadata.
        
        Args:
            file_entry: File entry to assess
            
        Returns:
            RecoveryConfidence level
        """
        # Base implementation - override in subclasses
        if file_entry.is_fragmented:
            return RecoveryConfidence.MEDIUM
        if file_entry.status == FileStatus.EXISTING:
            return RecoveryConfidence.EXCELLENT
        if file_entry.status == FileStatus.DELETED:
            return RecoveryConfidence.HIGH
        return RecoveryConfidence.UNKNOWN
    
    def __enter__(self) -> 'FileSystemParser':
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self._is_initialized = False