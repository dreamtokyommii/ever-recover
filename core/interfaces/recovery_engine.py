"""Abstract interface for recovery orchestration."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Iterator, Callable, Set
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from enum import Enum, auto

from ..models.file_entry import FileEntry
from ..models.scan_result import ScanResult
from ..models.recovery_stats import RecoverySession, RecoveryOperation, RecoveryStatus


@dataclass
class RecoveryOptions:
    """Configuration options for recovery operation."""
    output_directory: Path
    preserve_directory_structure: bool = True
    preserve_timestamps: bool = True
    calculate_hashes: bool = True
    verify_integrity: bool = True
    skip_existing: bool = False
    max_concurrent_operations: int = 4
    recovery_timeout: int = 300  # seconds
    log_level: str = "INFO"
    recovery_notes: Optional[str] = None


@dataclass
class RecoveryProgress:
    """Real-time recovery progress information."""
    session_id: str
    current_file: str
    files_processed: int
    files_total: int
    bytes_recovered: int
    bytes_expected: int
    current_speed: float  # bytes/second
    eta_seconds: float
    errors: int
    warnings: int
    status: str
    timestamp: datetime


class RecoveryEngineError(Exception):
    """Base exception for recovery operations."""
    pass


class InsufficientSpaceError(RecoveryEngineError):
    """Raised when output location has insufficient space."""
    pass


class RecoveryCancelledError(RecoveryEngineError):
    """Raised when recovery is cancelled by user."""
    pass


class RecoveryEngine(ABC):
    """
    Abstract base class for recovery orchestration.
    
    This interface coordinates the complete recovery workflow:
    - Validates recovery destination
    - Manages multi-threaded recovery
    - Preserves metadata and timestamps
    - Calculates and verifies hashes
    - Maintains audit logs
    - Handles errors and retries
    
    Implementations:
    - BasicRecoveryEngine: Single-threaded recovery
    - ParallelRecoveryEngine: Multi-threaded recovery
    - ForensicRecoveryEngine: With enhanced audit logging
    """
    
    def __init__(self, scan_result: ScanResult):
        """
        Initialize recovery engine.
        
        Args:
            scan_result: Scan result containing files to recover
        """
        self.scan_result = scan_result
        self._current_session: Optional[RecoverySession] = None
        self._is_cancelled = False
    
    @abstractmethod
    def validate_destination(self, output_path: Path, 
                            required_space: int) -> bool:
        """
        Validate recovery destination has sufficient space.
        
        Args:
            output_path: Destination directory
            required_space: Required space in bytes
            
        Returns:
            True if destination is valid
            
        Raises:
            InsufficientSpaceError: If insufficient space
        """
        pass
    
    @abstractmethod
    def start_recovery_session(self, output_path: Path,
                               options: RecoveryOptions) -> str:
        """
        Start a new recovery session.
        
        Args:
            output_path: Recovery destination
            options: Recovery options
            
        Returns:
            Session ID
        """
        pass
    
    @abstractmethod
    def end_recovery_session(self, session_id: str) -> RecoverySession:
        """
        End recovery session and return statistics.
        
        Args:
            session_id: Session ID to end
            
        Returns:
            Completed recovery session
        """
        pass
    
    @abstractmethod
    def recover_file(self, file_entry: FileEntry, 
                     destination: Path,
                     options: RecoveryOptions) -> RecoveryOperation:
        """
        Recover single file.
        
        Args:
            file_entry: File to recover
            destination: Destination path
            options: Recovery options
            
        Returns:
            RecoveryOperation with result
        """
        pass
    
    @abstractmethod
    def recover_files(self, files: List[FileEntry],
                      options: RecoveryOptions,
                      progress_callback: Callable[[RecoveryProgress], None] = None) -> RecoverySession:
        """
        Recover multiple files.
        
        Args:
            files: Files to recover
            options: Recovery options
            progress_callback: Progress callback
            
        Returns:
            Completed recovery session
        """
        pass
    
    @abstractmethod
    def recover_all(self, options: RecoveryOptions,
                    progress_callback: Callable[[RecoveryProgress], None] = None) -> RecoverySession:
        """
        Recover all files from scan.
        
        Args:
            options: Recovery options
            progress_callback: Progress callback
            
        Returns:
            Completed recovery session
        """
        pass
    
    @abstractmethod
    def recover_by_category(self, category: str,
                            options: RecoveryOptions,
                            progress_callback: Callable[[RecoveryProgress], None] = None) -> RecoverySession:
        """
        Recover files by category.
        
        Args:
            category: File category
            options: Recovery options
            progress_callback: Progress callback
        """
        pass
    
    @abstractmethod
    def recover_by_confidence(self, min_confidence: int,
                              options: RecoveryOptions,
                              progress_callback: Callable[[RecoveryProgress], None] = None) -> RecoverySession:
        """
        Recover files by minimum confidence level.
        
        Args:
            min_confidence: Minimum confidence (0-100)
            options: Recovery options
            progress_callback: Progress callback
        """
        pass
    
    @abstractmethod
    def cancel_recovery(self) -> None:
        """Cancel ongoing recovery operation."""
        pass
    
    @abstractmethod
    def get_progress(self) -> RecoveryProgress:
        """Get current recovery progress."""
        pass
    
    @abstractmethod
    def verify_recovered_file(self, file_entry: FileEntry,
                              recovered_path: Path) -> bool:
        """
        Verify integrity of recovered file.
        
        Args:
            file_entry: Original file entry
            recovered_path: Path to recovered file
            
        Returns:
            True if verification passed
        """
        pass
    
    @abstractmethod
    def preserve_metadata(self, file_entry: FileEntry,
                          recovered_path: Path) -> bool:
        """
        Preserve original file metadata.
        
        Args:
            file_entry: Original file entry
            recovered_path: Path to recovered file
            
        Returns:
            True if metadata preserved successfully
        """
        pass
    
    @abstractmethod
    def generate_manifest(self, session: RecoverySession) -> str:
        """
        Generate recovery manifest/receipt.
        
        Args:
            session: Recovery session
            
        Returns:
            Manifest content (JSON/CSV/XML)
        """
        pass
    
    @property
    def current_session(self) -> Optional[RecoverySession]:
        """Get current recovery session."""
        return self._current_session
    
    @property
    def is_recovery_active(self) -> bool:
        """Check if recovery is in progress."""
        return self._current_session is not None and not self._current_session.end_time
    
    @property
    def is_cancelled(self) -> bool:
        """Check if recovery was cancelled."""
        return self._is_cancelled
    
    def recover_selected(self, file_ids: Set[str],
                         options: RecoveryOptions,
                         progress_callback: Callable[[RecoveryProgress], None] = None) -> RecoverySession:
        """
        Recover selected files by ID.
        
        Args:
            file_ids: Set of file IDs to recover
            options: Recovery options
            progress_callback: Progress callback
            
        Returns:
            Completed recovery session
        """
        files = [f for f in self.scan_result.files if f.file_id in file_ids]
        return self.recover_files(files, options, progress_callback)
    
    def estimate_recovery_time(self, files: List[FileEntry],
                               avg_speed: float = 10 * 1024 * 1024) -> float:
        """
        Estimate recovery time.
        
        Args:
            files: Files to recover
            avg_speed: Average recovery speed (bytes/sec, default 10MB/s)
            
        Returns:
            Estimated time in seconds
        """
        total_size = sum(f.file_size for f in files)
        return total_size / avg_speed