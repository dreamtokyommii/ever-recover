"""Device enumeration and information gathering."""

import platform
import logging
from typing import List, Optional
from pathlib import Path

from infrastructure.disk import create_disk_reader, WindowsDiskReader, LinuxDiskReader
from core.models.device import DeviceInfo, DeviceType, FileSystemType

logger = logging.getLogger(__name__)


class DeviceScanner:
    """Enumerates and gathers information about storage devices."""
    
    def __init__(self):
        """Initialize device scanner."""
        self._devices: List[DeviceInfo] = []
    
    def scan_devices(self) -> List[DeviceInfo]:
        """
        Scan for all available storage devices.
        
        Returns:
            List of DeviceInfo objects
        """
        self._devices.clear()
        
        system = platform.system()
        
        if system == 'Windows':
            self._scan_windows()
        else:
            self._scan_linux()
        
        logger.info(f"Found {len(self._devices)} devices")
        return self._devices.copy()
    
    def _scan_windows(self) -> None:
        """Scan Windows devices."""
        # Physical drives
        for drive_path in WindowsDiskReader.enumerate_physical_drives():
            try:
                logger.info(f"Opening physical drive: {drive_path}")
                with create_disk_reader(drive_path) as reader:
                    geometry = reader.get_geometry()
                    partitions = reader.get_partitions()
                    
                    device = DeviceInfo(
                        device_id=f"physical_{drive_path.split('\\')[-1]}",
                        path=drive_path,
                        label=f"PhysicalDrive {drive_path.split('\\')[-1]}",
                        device_type=DeviceType.HDD,  # Would need SMART to detect SSD
                        file_system=FileSystemType.UNKNOWN,
                        total_size=geometry.total_size,
                        free_space=0,  # Not applicable for physical drives
                        is_removable=False,
                        is_read_only=True,
                        model=geometry.cylinder_size,  # Placeholder
                    )
                    
                    self._devices.append(device)
                    logger.info(f"  Found: {device.label} ({device.display_size})")
            
            except Exception as e:
                logger.warning(f"Failed to scan {drive_path}: {e}")
        
        # Logical drives
        for drive_letter in WindowsDiskReader.enumerate_logical_drives():
            device_path = f"\\\\.\\{drive_letter}"
            try:
                logger.info(f"Opening logical drive: {device_path}")
                with create_disk_reader(device_path) as reader:
                    # Get volume info
                    device = DeviceInfo(
                        device_id=f"logical_{drive_letter}",
                        path=device_path,
                        label=drive_letter,
                        device_type=DeviceType.UNKNOWN,
                        file_system=FileSystemType.UNKNOWN,  # Would need to detect
                        total_size=reader.total_size,
                        free_space=0,  # Would need GetDiskFreeSpaceEx
                        is_removable=False,
                        is_read_only=True,
                    )
                    
                    self._devices.append(device)
                    logger.info(f"  Found: {device.label} ({device.display_size})")
            
            except Exception as e:
                logger.warning(f"Failed to scan {device_path}: {e}")
    
    def _scan_linux(self) -> None:
        """Scan Linux devices."""
        for device_path in LinuxDiskReader.enumerate_block_devices():
            try:
                logger.info(f"Opening device: {device_path}")
                with create_disk_reader(device_path) as reader:
                    geometry = reader.get_geometry()
                    partitions = reader.get_partitions()
                    
                    # Determine device type
                    device_type = DeviceType.HDD
                    if reader.is_ssd:
                        device_type = DeviceType.SSD
                    
                    device = DeviceInfo(
                        device_id=f"block_{Path(device_path).name}",
                        path=device_path,
                        label=Path(device_path).name,
                        device_type=device_type,
                        file_system=FileSystemType.UNKNOWN,
                        total_size=geometry.total_size,
                        free_space=0,
                        is_removable=False,
                        is_read_only=True,
                        is_trim_enabled=reader.is_trim_enabled,
                    )
                    
                    self._devices.append(device)
                    logger.info(f"  Found: {device.label} ({device.display_size})")
                    
                    # Add SSD/TRIM warning
                    if device.is_trim_enabled:
                        logger.warning(f"  ⚠️  TRIM enabled on {device_path} - may affect recoverability")
            
            except Exception as e:
                logger.warning(f"Failed to scan {device_path}: {e}")
    
    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """Get device by ID."""
        for device in self._devices:
            if device.device_id == device_id:
                return device
        return None
    
    def get_devices_by_type(self, device_type: DeviceType) -> List[DeviceInfo]:
        """Get devices by type."""
        return [d for d in self._devices if d.device_type == device_type]