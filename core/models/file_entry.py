"""File entry model representing recoverable files found during scanning."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional, List, Dict, Any
import hashlib


class FileCategory(Enum):
    """High-level file categories for classification."""
    IMAGE = auto()
    VIDEO = auto()
    DOCUMENT = auto()
    ARCHIVE = auto()
    DATABASE = auto()
    DATA = auto()
    VM_IMAGE = auto()
    SOURCE_CODE = auto()
    AUDIO = auto()
    EXECUTABLE = auto()
    SYSTEM = auto()
    OTHER = auto()


class RecoveryConfidence(Enum):
    """Confidence level in successful file recovery."""
    EXCELLENT = 95      # Complete file, verified structure
    HIGH = 80           # Likely complete, minor issues
    MEDIUM = 60         # Partial recovery possible
    LOW = 40            # Fragmented, may be corrupted
    POOR = 20           # Heavily fragmented, uncertain
    UNKNOWN = 0         # Not yet assessed


class FileStatus(Enum):
    """Status of file in recovery process."""
    DELETED = "deleted"
    EXISTING = "existing"
    OVERWRITTEN = "overwritten"
    FRAGMENTED = "fragmented"
    CORRUPTED = "corrupted"
    RECOVERED = "recovered"
    RECOVERY_FAILED = "recovery_failed"


@dataclass
class FileEntry:
    """
    Represents a file entry found during forensic scanning.
    
    Attributes:
        file_id: Unique identifier
        filename: Original filename (if available)
        extension: File extension
        file_path: Full path in original filesystem (if available)
        file_size: Size in bytes
        file_category: High-level category
        recovery_confidence: Confidence in recovery success
        status: Current file status
        file_signature: Detected file signature/magic bytes
        offset: Offset on disk where file starts
        fragments: List of (offset, size) tuples for fragmented files
        created_time: Original creation timestamp
        modified_time: Original modification timestamp
        accessed_time: Original access timestamp
        deleted_time: Estimated deletion time
        attributes: File attributes (read-only, hidden, system, etc.)
        owner: File owner (if available from filesystem)
        sha256_hash: SHA-256 hash of recovered content
        metadata: Additional filesystem-specific metadata
        preview_available: Whether preview can be generated
        thumbnail_data: Base64-encoded thumbnail (for images/videos)
        is_carved: Whether file was recovered via carving vs metadata
        parent_directory: Parent directory entry
        mft_record: MFT record number (NTFS-specific)
        inode: Inode number (EXT4-specific)
    """
    file_id: str
    filename: str
    extension: str
    file_size: int
    file_category: FileCategory
    recovery_confidence: RecoveryConfidence
    status: FileStatus
    file_signature: Optional[bytes] = None
    offset: Optional[int] = None
    fragments: List[tuple[int, int]] = field(default_factory=list)
    created_time: Optional[datetime] = None
    modified_time: Optional[datetime] = None
    accessed_time: Optional[datetime] = None
    deleted_time: Optional[datetime] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    owner: Optional[str] = None
    sha256_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    preview_available: bool = False
    thumbnail_data: Optional[str] = None
    is_carved: bool = False
    parent_directory: Optional[str] = None
    mft_record: Optional[int] = None
    inode: Optional[int] = None
    
    @property
    def display_name(self) -> str:
        """Get display name, handling deleted files."""
        if not self.filename:
            return f"[Unknown]_{self.file_id}.{self.extension}"
        return self.filename
    
    @property
    def display_size(self) -> str:
        """Return human-readable size."""
        return self._format_bytes(self.file_size)
    
    @property
    def is_fragmented(self) -> bool:
        """Check if file is fragmented."""
        return len(self.fragments) > 1
    
    @property
    def confidence_percentage(self) -> int:
        """Get confidence as percentage."""
        return self.recovery_confidence.value
    
    @property
    def timeline_timestamps(self) -> List[tuple[str, datetime]]:
        """Extract all timestamps for timeline view."""
        timestamps = []
        if self.created_time:
            timestamps.append(("Created", self.created_time))
        if self.modified_time:
            timestamps.append(("Modified", self.modified_time))
        if self.accessed_time:
            timestamps.append(("Accessed", self.accessed_time))
        if self.deleted_time:
            timestamps.append(("Deleted", self.deleted_time))
        return timestamps
    
    def calculate_hash(self, data: bytes) -> str:
        """Calculate and store SHA-256 hash."""
        self.sha256_hash = hashlib.sha256(data).hexdigest()
        return self.sha256_hash
    
    def verify_integrity(self, data: bytes) -> bool:
        """Verify file integrity against stored hash."""
        if not self.sha256_hash:
            return False
        return hashlib.sha256(data).hexdigest() == self.sha256_hash
    
    def matches_extension(self, signature_based_extension: str) -> bool:
        """Check if file extension matches signature-based detection."""
        return self.extension.lower() == signature_based_extension.lower()
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'file_id': self.file_id,
            'filename': self.filename,
            'extension': self.extension,
            'file_size': self.file_size,
            'file_category': self.file_category.name,
            'recovery_confidence': self.recovery_confidence.name,
            'status': self.status.value,
            'offset': self.offset,
            'fragments': self.fragments,
            'created_time': self.created_time.isoformat() if self.created_time else None,
            'modified_time': self.modified_time.isoformat() if self.modified_time else None,
            'accessed_time': self.accessed_time.isoformat() if self.accessed_time else None,
            'deleted_time': self.deleted_time.isoformat() if self.deleted_time else None,
            'sha256_hash': self.sha256_hash,
            'is_carved': self.is_carved,
            'parent_directory': self.parent_directory,
        }
    
    @staticmethod
    def _format_bytes(size_bytes: int) -> str:
        """Convert bytes to human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"