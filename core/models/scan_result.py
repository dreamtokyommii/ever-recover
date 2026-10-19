"""Scan result model aggregating all files found during a scan session."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Set
from pathlib import Path
from .device import DeviceInfo
from .file_entry import FileEntry, FileCategory, RecoveryConfidence


@dataclass
class ScanStatistics:
    """Statistics about a scan session."""
    total_files: int = 0
    deleted_files: int = 0
    existing_files: int = 0
    carved_files: int = 0
    fragmented_files: int = 0
    total_size: int = 0
    recoverable_size: int = 0
    recoverable_files: int = 0
    files_by_category: Dict[str, int] = field(default_factory=dict)
    files_by_confidence: Dict[str, int] = field(default_factory=dict)
    files_by_extension: Dict[str, int] = field(default_factory=dict)
    scan_errors: int = 0
    bad_sectors: int = 0
    
    def add_file(self, file_entry: FileEntry) -> None:
        """Update statistics with a file entry."""
        self.total_files += 1
        self.total_size += file_entry.file_size
        
        if file_entry.status.value == "deleted":
            self.deleted_files += 1
        elif file_entry.status.value == "existing":
            self.existing_files += 1
        
        if file_entry.is_carved:
            self.carved_files += 1
        
        if file_entry.is_fragmented:
            self.fragmented_files += 1
        
        if file_entry.recovery_confidence.value >= 60:
            self.recoverable_size += file_entry.file_size
            self.recoverable_files += 1
        
        # Category counts
        category_name = file_entry.file_category.name
        self.files_by_category[category_name] = self.files_by_category.get(category_name, 0) + 1
        
        # Confidence counts
        confidence_name = file_entry.recovery_confidence.name
        self.files_by_confidence[confidence_name] = self.files_by_confidence.get(confidence_name, 0) + 1
        
        # Extension counts
        ext = f".{file_entry.extension}"
        self.files_by_extension[ext] = self.files_by_extension.get(ext, 0) + 1


@dataclass
class ScanResult:
    """
    Complete results from a forensic scan session.
    
    Attributes:
        scan_id: Unique scan identifier
        device: Scanned device information
        start_time: Scan start timestamp
        end_time: Scan end timestamp
        files: All discovered file entries
        statistics: Aggregated scan statistics
        file_signature: File signature/carving metadata
        is_complete: Whether scan completed successfully
        error_message: Error message if scan failed
        resume_offset: Offset to resume from (for interrupted scans)
        timeline_events: Timeline events extracted from file timestamps
    """
    scan_id: str
    device: DeviceInfo
    start_time: datetime
    files: List[FileEntry] = field(default_factory=list)
    statistics: ScanStatistics = field(default_factory=ScanStatistics)
    status: str = "unknown"
    file_signature: Optional[str] = None
    is_complete: bool = False
    error_message: Optional[str] = None
    resume_offset: Optional[int] = None
    timeline_events: List[Dict] = field(default_factory=list)
    
    @property
    def duration(self) -> float:
        """Get scan duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def duration_seconds(self) -> float:
        """Compatibility alias used by demo and CLI entry points."""
        return self.duration
    
    @property
    def end_time(self) -> Optional[datetime]:
        """Get scan end time."""
        return getattr(self, '_end_time', None)
    
    @end_time.setter
    def end_time(self, value: Optional[datetime]) -> None:
        """Set scan end time."""
        self._end_time = value
    
    @property
    def recoverable_files(self) -> List[FileEntry]:
        """Get files with good recovery confidence."""
        return [f for f in self.files if f.recovery_confidence.value >= 60]
    
    @property
    def high_confidence_files(self) -> List[FileEntry]:
        """Get files with high/excellent confidence."""
        return [f for f in self.files 
                if f.recovery_confidence in [RecoveryConfidence.EXCELLENT, RecoveryConfidence.HIGH]]
    
    @property
    def categories(self) -> Set[str]:
        """Get unique file categories in results."""
        return {f.file_category.name for f in self.files}
    
    @property
    def extensions(self) -> Set[str]:
        """Get unique file extensions in results."""
        return {f.extension for f in self.files}
    
    def add_file(self, file_entry: FileEntry) -> None:
        """Add file and update statistics."""
        self.files.append(file_entry)
        self.statistics.add_file(file_entry)
    
    def get_files_by_category(self, category: FileCategory) -> List[FileEntry]:
        """Filter files by category."""
        return [f for f in self.files if f.file_category == category]
    
    def get_files_by_confidence(self, min_confidence: RecoveryConfidence) -> List[FileEntry]:
        """Filter files by minimum confidence level."""
        return [f for f in self.files if f.recovery_confidence.value >= min_confidence.value]
    
    def get_files_by_extension(self, extension: str) -> List[FileEntry]:
        """Filter files by extension."""
        return [f for f in self.files if f.extension.lower() == extension.lower()]
    
    def get_files_by_date_range(self, start: datetime, end: datetime) -> List[FileEntry]:
        """Filter files by modified date range."""
        return [f for f in self.files 
                if f.modified_time and start <= f.modified_time <= end]
    
    def search_files(self, query: str) -> List[FileEntry]:
        """Search files by filename."""
        query_lower = query.lower()
        return [f for f in self.files if query_lower in f.filename.lower()]
    
    def to_summary_dict(self) -> dict:
        """Create summary dictionary for UI display."""
        return {
            'scan_id': self.scan_id,
            'device_path': self.device.path,
            'device_label': self.device.label,
            'file_system': self.device.file_system.value,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': self.duration,
            'total_files': self.statistics.total_files,
            'deleted_files': self.statistics.deleted_files,
            'recoverable_files': len(self.recoverable_files),
            'total_size': self.statistics.total_size,
            'recoverable_size': self.statistics.recoverable_size,
            'is_complete': self.is_complete,
        }