"""Abstract interface for file carving operations."""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Iterator, Tuple, Set
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from ..models.file_entry import FileEntry, FileCategory, RecoveryConfidence


@dataclass
class FileSignature:
    """File signature (magic bytes) definition."""
    name: str
    extension: str
    category: FileCategory
    offset: int  # Offset in file where signature appears
    signature: bytes  # Magic bytes
    signature_mask: Optional[bytes]  # Mask for variable bytes (optional)
    min_size: int  # Minimum file size
    max_size: int  # Maximum file size (0 = unlimited)
    footer_signature: Optional[bytes]  # End-of-file signature (optional)
    footer_offset_relative: bool  # Whether footer offset is from end or start
    validation_rules: Dict[str, any]  # Additional validation rules
    priority: int  # Match priority (higher = check first)


@dataclass
class CarvingResult:
    """Result of file carving operation."""
    file_entry: FileEntry
    offset: int
    size: int
    confidence: RecoveryConfidence
    validation_passed: bool
    fragmentation_detected: bool
    fragments: List[Tuple[int, int]]
    notes: str


class CarvingEngineError(Exception):
    """Base exception for carving operations."""
    pass


class SignatureNotFoundError(CarvingEngineError):
    """Raised when file signature is not found."""
    pass


class CarvingEngine(ABC):
    """
    Abstract base class for file carving engine.
    
    This interface performs signature-based file recovery:
    - Scans raw disk for known file signatures
    - Extracts files based on headers/footers
    - Validates recovered file structure
    - Detects fragmentation
    - Estimates recovery confidence
    
    Implementations:
    - BasicCarvingEngine: Simple header/footer carving
    - AdvancedCarvingEngine: With fragmentation detection
    - AICarvingEngine: ML-enhanced carving with corruption detection
    """
    
    def __init__(self, disk_reader: 'DiskReader'):
        """
        Initialize carving engine.
        
        Args:
            disk_reader: Disk reader for raw access
        """
        from .disk_reader import DiskReader
        self.disk_reader = disk_reader
        self._signatures: List[FileSignature] = []
        self._signature_index: Dict[str, FileSignature] = {}
    
    @abstractmethod
    def load_signatures(self, signature_file: Path) -> int:
        """
        Load file signatures from database.
        
        Args:
            signature_file: Path to signature database file
            
        Returns:
            Number of signatures loaded
        """
        pass
    
    @abstractmethod
    def add_signature(self, signature: FileSignature) -> None:
        """Add single signature to database."""
        pass
    
    @abstractmethod
    def get_signatures(self) -> List[FileSignature]:
        """Get all loaded signatures."""
        pass
    
    @abstractmethod
    def get_signatures_by_extension(self, extension: str) -> List[FileSignature]:
        """Get signatures for specific extension."""
        pass
    
    @abstractmethod
    def get_signatures_by_category(self, category: FileCategory) -> List[FileSignature]:
        """Get signatures for specific category."""
        pass
    
    @abstractmethod
    def scan_for_signatures(self, 
                           start_offset: int = 0,
                           end_offset: int = None,
                           extensions: Optional[Set[str]] = None,
                           categories: Optional[Set[FileCategory]] = None) -> List[CarvingResult]:
        """
        Scan disk for file signatures.
        
        Args:
            start_offset: Start scanning offset
            end_offset: End scanning offset (None = end of device)
            extensions: Filter by extensions (None = all)
            categories: Filter by categories (None = all)
            
        Returns:
            List of carving results
        """
        pass
    
    @abstractmethod
    def find_signature_at(self, offset: int) -> Optional[FileSignature]:
        """
        Check if signature exists at specific offset.
        
        Args:
            offset: Offset to check
            
        Returns:
            Matching signature or None
        """
        pass
    
    @abstractmethod
    def extract_file(self, signature: FileSignature, 
                     start_offset: int, 
                     max_size: int = None) -> CarvingResult:
        """
        Extract file starting at offset based on signature.
        
        Args:
            signature: File signature
            start_offset: Start offset of file
            max_size: Maximum size to extract (None = use signature max)
            
        Returns:
            CarvingResult with extracted file
        """
        pass
    
    @abstractmethod
    def validate_file_structure(self, data: bytes, 
                                signature: FileSignature) -> bool:
        """
        Validate extracted file structure.
        
        Args:
            data: File content
            signature: File signature
            
        Returns:
            True if file structure appears valid
        """
        pass
    
    @abstractmethod
    def detect_fragmentation(self, signature: FileSignature,
                            start_offset: int,
                            expected_size: int) -> List[Tuple[int, int]]:
        """
        Detect file fragmentation.
        
        Args:
            signature: File signature
            start_offset: Start offset
            expected_size: Expected file size
            
        Returns:
            List of (offset, size) tuples for fragments
        """
        pass
    
    @abstractmethod
    def calculate_confidence(self, result: CarvingResult) -> RecoveryConfidence:
        """
        Calculate recovery confidence for carving result.
        
        Args:
            result: Carving result
            
        Returns:
            Recovery confidence level
        """
        pass
    
    @abstractmethod
    def carve_all(self, 
                   progress_callback: callable = None) -> Iterator[CarvingResult]:
        """
        Perform comprehensive carving of entire device.
        
        Args:
            progress_callback: Callback(offset, total_size) for progress
            
        Yields:
            CarvingResult objects for all found files
        """
        pass
    
    @abstractmethod
    def carve_by_type(self, extension: str,
                      progress_callback: callable = None) -> Iterator[CarvingResult]:
        """
        Carve files of specific type.
        
        Args:
            extension: File extension to carve
            progress_callback: Progress callback
            
        Yields:
            CarvingResult objects
        """
        pass
    
    @property
    def signature_count(self) -> int:
        """Get number of loaded signatures."""
        return len(self._signatures)
    
    @property
    def supported_extensions(self) -> Set[str]:
        """Get set of supported file extensions."""
        return {sig.extension for sig in self._signatures}
    
    @property
    def supported_categories(self) -> Set[FileCategory]:
        """Get set of supported file categories."""
        return {sig.category for sig in self._signatures}
    
    def _read_chunk(self, offset: int, size: int) -> bytes:
        """Read chunk from disk (helper method)."""
        return self.disk_reader.read(offset, size)
    
    def _find_pattern(self, pattern: bytes, data: bytes, 
                      start: int = 0) -> List[int]:
        """Find all occurrences of pattern in data."""
        matches = []
        pos = start
        while True:
            idx = data.find(pattern, pos)
            if idx == -1:
                break
            matches.append(idx)
            pos = idx + 1
        return matches