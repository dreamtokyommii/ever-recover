"""Disk reader interface and implementations."""

import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

from core.models.device import DeviceInfo, DeviceType

logger = logging.getLogger(__name__)


@dataclass
class DiskGeometry:
    """Physical disk geometry information."""
    bytes_per_sector: int
    sectors_per_track: int
    tracks_per_cylinder: int
    total_sectors: int
    cylinder_size: int
    total_size: int


@dataclass
class PartitionInfo:
    """Partition information."""
    partition_type: str
    start_offset: int
    size: int
    bootable: bool = False
    guid: Optional[str] = None


class DiskReaderError(Exception):
    """Generic disk reader error."""
    pass


class AccessDeniedError(DiskReaderError):
    """Raised when opening a device without permissions."""
    pass


class InvalidDeviceError(DiskReaderError):
    """Raised when device path is invalid or not found."""
    pass


class ReadError(DiskReaderError):
    """Raised when a disk read operation fails."""
    pass


@dataclass
class DiskInfo:
    """Disk information."""
    device_type: DeviceType
    device_path: str
    total_size: int
    manufacturer: str
    model: str
    block_size: int = 512
    is_removable: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'device_type': self.device_type.name,
            'device_path': self.device_path,
            'total_size': self.total_size,
            'total_size_gb': self.total_size / (1024**3),
            'manufacturer': self.manufacturer,
            'model': self.model,
            'block_size': self.block_size,
            'is_removable': self.is_removable,
        }


class DiskReader(ABC):
    """Abstract base class for disk readers."""
    
    def __init__(self, disk_info):
        if isinstance(disk_info, (str, Path)):
            disk_info = DiskInfo(device_type=DeviceType.VIRTUAL, device_path=str(disk_info),
                                 total_size=0, manufacturer="", model="")
        self._disk_info = disk_info
        self._is_open = False
    
    @property
    def device_path(self) -> str:
        """Get device path."""
        return self._disk_info.device_path
    
    @property
    def total_size(self) -> int:
        """Get total size in bytes."""
        return self._disk_info.total_size
    
    @property
    def block_size(self) -> int:
        """Get block size."""
        return self._disk_info.block_size
    
    @property
    def is_open(self) -> bool:
        """Check if disk is open."""
        return self._is_open
    
    @property
    def disk_info(self) -> DiskInfo:
        """Get disk information."""
        return self._disk_info
    
    @abstractmethod
    def open(self) -> None:
        """Open disk for reading."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close disk."""
        pass
    
    @abstractmethod
    def read(self, offset: int, size: int) -> bytes:
        """Read data from disk."""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self._disk_info.to_dict()


class VirtualDiskReader(DiskReader):
    """Virtual disk for testing."""
    
    def __init__(self, disk_data: bytes, device_path: str = "virtual"):
        super().__init__(DiskInfo(
            device_type=DeviceType.VIRTUAL,
            device_path=device_path,
            total_size=len(disk_data),
            manufacturer="Virtual",
            model="Test Disk",
        ))
        self._disk_data = disk_data
        self._is_open = True  # Start as open
    
    def open(self) -> None:
        """Open virtual disk."""
        self._is_open = True
        logger.info(f"Virtual disk opened: {self.device_path}")
    
    def close(self) -> None:
        """Close virtual disk."""
        self._is_open = False
        logger.info(f"Virtual disk closed: {self.device_path}")
    
    def read(self, offset: int, size: int) -> bytes:
        """Read data from virtual disk."""
        if not self._is_open:
            self.open()
        
        if offset < 0 or offset >= len(self._disk_data):
            raise ValueError(f"Invalid offset: {offset}")
        
        end = min(offset + size, len(self._disk_data))
        return self._disk_data[offset:end]


class DiskImageReader(DiskReader):
    """Read from disk image file (E01, IMG, RAW, etc.)."""
    
    def __init__(self, image_path: str):
        path = Path(image_path)
        size = path.stat().st_size if path.exists() else 0
        
        super().__init__(DiskInfo(
            device_type=DeviceType.DISK_IMAGE,
            device_path=str(path),
            total_size=size,
            manufacturer="File",
            model=f"{path.suffix.upper()} Image",
            block_size=4096,
        ))
        
        self._image_path = image_path
        self._file = None
    
    def open(self) -> None:
        """Open disk image file."""
        self._file = open(self._image_path, 'rb')
        self._is_open = True
        logger.info(f"Disk image opened: {self._image_path} ({self.total_size / (1024**3):.1f} GB)")
    
    def close(self) -> None:
        """Close disk image file."""
        if self._file:
            self._file.close()
            self._file = None
        self._is_open = False
        logger.info(f"Disk image closed: {self._image_path}")
    
    def read(self, offset: int, size: int) -> bytes:
        """Read data from disk image file."""
        if not self._is_open or not self._file:
            raise RuntimeError("Disk image not open")
        
        self._file.seek(offset)
        return self._file.read(size)


__all__ = [
    'DiskReader',
    'DiskInfo',
    'DeviceType',
    'VirtualDiskReader',
    'DiskImageReader',
]