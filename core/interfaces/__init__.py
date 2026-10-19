"""Core interfaces module."""

from .disk_reader import DiskReader, DiskInfo, VirtualDiskReader, DiskImageReader
from .filesystem_parser import FileSystemParser

__all__ = [
    'DiskReader',
    'DiskInfo',
    'VirtualDiskReader',
    'DiskImageReader',
    'FileSystemParser',
]