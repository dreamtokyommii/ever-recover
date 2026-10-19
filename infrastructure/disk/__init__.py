"""Disk access implementations."""

import platform
from .windows_disk_reader import WindowsDiskReader
from .disk_image_reader import DiskImageReader, ImageMetadata

# Only import Linux reader on Linux systems
if platform.system() == 'Linux':
    from .linux_disk_reader import LinuxDiskReader
else:
    LinuxDiskReader = None

__all__ = [
    'WindowsDiskReader',
    'DiskImageReader',
]

if LinuxDiskReader is not None:
    __all__.append('LinuxDiskReader')

__all__.append('ImageMetadata')