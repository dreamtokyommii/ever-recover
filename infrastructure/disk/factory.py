"""Factory functions for creating disk readers."""

import platform
import logging
from typing import Optional, TYPE_CHECKING
from pathlib import Path

from .windows_disk_reader import WindowsDiskReader
from .disk_image_reader import DiskImageReader

# Only import Linux reader on Linux systems
if platform.system() == 'Linux':
    from .linux_disk_reader import LinuxDiskReader
else:
    LinuxDiskReader = None

if TYPE_CHECKING:
    from core.interfaces.disk_reader import DiskReader

logger = logging.getLogger(__name__)


def create_disk_reader(device_path: str, 
                       force_image: bool = False) -> 'DiskReader':
    """
    Factory function to create appropriate disk reader.
    
    Args:
        device_path: Path to device or image file
        force_image: Force treating path as disk image
        
    Returns:
        Appropriate DiskReader instance
        
    Raises:
        DiskReaderError: If device type cannot be determined
    """
    from core.interfaces.disk_reader import DiskReader, DiskReaderError
    
    # Check if it's a disk image file
    if force_image or _is_disk_image_file(device_path):
        logger.info(f"Creating disk image reader for: {device_path}")
        return DiskImageReader(device_path)
    
    # Create platform-specific reader
    system = platform.system()
    
    if system == 'Windows':
        logger.info(f"Creating Windows disk reader for: {device_path}")
        return WindowsDiskReader(device_path)
    
    elif system == 'Linux':
        logger.info(f"Creating Linux disk reader for: {device_path}")
        return LinuxDiskReader(device_path)
    
    elif system == 'Darwin':  # macOS
        logger.info(f"Creating Linux disk reader for macOS: {device_path}")
        return LinuxDiskReader(device_path)  # Similar to Linux
    
    else:
        raise DiskReaderError(f"Unsupported platform: {system}")


def _is_disk_image_file(path: str) -> bool:
    """Check if path is a disk image file."""
    supported_extensions = {
        '.e01', '.e02', '.e03', '.e04', '.e05', '.e06', '.e07', '.e08', '.e09',
        '.img', '.raw', '.dd', '.bin',
        '.aff', '.afd', '.afm',
        '.vmdk', '.vdi', '.vhd', '.vhdx', '.qcow2',
    }
    
    path_lower = Path(path).suffix.lower()
    return path_lower in supported_extensions


def get_platform_info() -> dict:
    """Get platform information."""
    return {
        'system': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'python_version': platform.python_version(),
        'architecture': platform.architecture()[0],
    }


def is_admin() -> bool:
    """Check if running with elevated privileges."""
    import os
    
    if platform.system() == 'Windows':
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False
    else:
        return os.geteuid() == 0