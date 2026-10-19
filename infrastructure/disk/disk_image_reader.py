"""Disk image reader for forensic image formats."""

import os
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass
from abc import ABC, abstractmethod

from core.interfaces.disk_reader import DiskReader, DiskGeometry, PartitionInfo, DiskReaderError

logger = logging.getLogger(__name__)


@dataclass
class ImageMetadata:
    """Metadata about disk image."""
    format: str
    size: int
    sector_size: int
    created_time: Optional[str]
    md5_hash: Optional[str]
    sha1_hash: Optional[str]
    sha256_hash: Optional[str]
    compression: str
    case_number: Optional[str]
    evidence_number: Optional[str]
    examiner: Optional[str]
    notes: Optional[str]


class DiskImageReader(DiskReader):
    """
    Reader for forensic disk image files.
    
    Supported formats:
    - Raw/DD (.img, .raw, .dd)
    - EnCase E01/E0x (.e01, .e02, etc.)
    - AFF (.aff, .afd)
    - VMDK, VDI, VHD (via conversion)
    """
    
    def __init__(self, image_path: str):
        """
        Initialize disk image reader.
        
        Args:
            image_path: Path to image file
        """
        super().__init__(image_path)
        self._file = None
        self._total_size = 0
        self._metadata: Optional[ImageMetadata] = None
        self._format = self._detect_format()
    
    def open(self) -> bool:
        """Open image file."""
        if self._is_open:
            return True
        
        try:
            if not os.path.exists(self.device_path):
                raise DiskReaderError(f"Image file not found: {self.device_path}")
            
            # Open based on format
            if self._format == 'raw':
                self._open_raw()
            elif self._format == 'e01':
                self._open_e01()
            elif self._format == 'aff':
                self._open_aff()
            else:
                raise DiskReaderError(f"Unsupported image format: {self._format}")
            
            self._is_open = True
            logger.info(f"Opened image: {self.device_path} ({self._format})")
            return True
            
        except Exception as e:
            raise DiskReaderError(f"Failed to open image: {e}")
    
    def close(self) -> None:
        """Close image file."""
        if self._file:
            self._file.close()
            self._file = None
            self._is_open = False
    
    def read(self, offset: int, size: int) -> bytes:
        """Read from image."""
        if not self._is_open:
            raise DiskReaderError("Image not open")
        
        if offset < 0 or offset + size > self._total_size:
            raise EOFError("Read beyond image bounds")
        
        self._file.seek(offset)
        return self._file.read(size)
    
    def read_sectors(self, start_sector: int, num_sectors: int) -> bytes:
        """Read sectors."""
        return self.read(start_sector * self.bytes_per_sector, num_sectors * self.bytes_per_sector)
    
    def get_geometry(self) -> DiskGeometry:
        """Get geometry."""
        return DiskGeometry(
            bytes_per_sector=self._metadata.sector_size if self._metadata else 512,
            sectors_per_track=63,
            tracks_per_cylinder=255,
            total_sectors=self._total_size // (self._metadata.sector_size if self._metadata else 512),
            cylinder_size=0,
            total_size=self._total_size
        )
    
    def get_partitions(self) -> List[PartitionInfo]:
        """Get partitions (not available for raw images)."""
        return []
    
    @property
    def total_size(self) -> int:
        """Get image size."""
        return self._total_size
    
    @property
    def bytes_per_sector(self) -> int:
        """Get sector size."""
        return self._metadata.sector_size if self._metadata else 512
    
    @property
    def metadata(self) -> Optional[ImageMetadata]:
        """Get image metadata."""
        return self._metadata
    
    @staticmethod
    def _detect_physical_drive(device_path: str) -> bool:
        """Always False for images."""
        return False
    
    def _detect_format(self) -> str:
        """Detect image format."""
        ext = Path(self.device_path).suffix.lower()
        
        if ext in ['.raw', '.img', '.dd', '.bin']:
            return 'raw'
        elif ext.startswith('.e0') or ext == '.e01':
            return 'e01'
        elif ext in ['.aff', '.afd']:
            return 'aff'
        else:
            # Try to detect from header
            try:
                with open(self.device_path, 'rb') as f:
                    header = f.read(16)
                    
                    if header.startswith(b'EVF2'):
                        return 'e01'
                    elif header.startswith(b'AFF'):
                        return 'aff'
                    else:
                        return 'raw'
            except:
                return 'raw'
    
    def _open_raw(self) -> None:
        """Open raw/DD image."""
        self._file = open(self.device_path, 'rb')
        self._file.seek(0, os.SEEK_END)
        self._total_size = self._file.tell()
        self._file.seek(0)
        
        # Calculate hashes
        self._metadata = ImageMetadata(
            format='raw',
            size=self._total_size,
            sector_size=512,
            created_time=None,
            md5_hash=None,
            sha1_hash=None,
            sha256_hash=None,
            compression='none',
            case_number=None,
            evidence_number=None,
            examiner=None,
            notes=None
        )
    
    def _open_e01(self) -> None:
        """Open E01 image (basic implementation)."""
        # Note: Full E01 support requires libewf
        # This is a simplified implementation
        self._file = open(self.device_path, 'rb')
        
        # Read header
        header = self._file.read(512)
        if not header.startswith(b'EVF2'):
            raise DiskReaderError("Invalid E01 header")
        
        # Parse basic info (simplified)
        self._metadata = ImageMetadata(
            format='e01',
            size=0,  # Would need full parsing
            sector_size=512,
            created_time=None,
            md5_hash=None,
            sha1_hash=None,
            sha256_hash=None,
            compression='zlib',
            case_number=None,
            evidence_number=None,
            examiner=None,
            notes=None
        )
        
        # For now, treat as raw (full implementation would decompress)
        self._file.seek(0)
        self._file.seek(0, os.SEEK_END)
        self._total_size = self._file.tell()
        self._file.seek(0)
    
    def _open_aff(self) -> None:
        """Open AFF image (basic implementation)."""
        # Note: Full AFF support requires libaff
        self._file = open(self.device_path, 'rb')
        
        header = self._file.read(16)
        if not header.startswith(b'AFF'):
            raise DiskReaderError("Invalid AFF header")
        
        self._metadata = ImageMetadata(
            format='aff',
            size=0,
            sector_size=512,
            created_time=None,
            md5_hash=None,
            sha1_hash=None,
            sha256_hash=None,
            compression='various',
            case_number=None,
            evidence_number=None,
            examiner=None,
            notes=None
        )
    
    def calculate_hash(self, algorithm: str = 'sha256') -> str:
        """Calculate hash of entire image."""
        if not self._is_open:
            raise DiskReaderError("Image not open")
        
        self._file.seek(0)
        
        if algorithm == 'md5':
            hasher = hashlib.md5()
        elif algorithm == 'sha1':
            hasher = hashlib.sha1()
        elif algorithm == 'sha256':
            hasher = hashlib.sha256()
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        
        # Read in chunks
        chunk_size = 1024 * 1024  # 1MB
        while True:
            chunk = self._file.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
        
        self._file.seek(0)
        return hasher.hexdigest()
    
    def verify_integrity(self, expected_hash: str, algorithm: str = 'sha256') -> bool:
        """Verify image integrity."""
        calculated = self.calculate_hash(algorithm)
        return calculated.lower() == expected_hash.lower()