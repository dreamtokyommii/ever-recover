"""
Device model representing storage devices for forensic analysis.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Optional
from pathlib import Path


class DeviceType(Enum):
    """Type of storage device."""
    HDD = auto()
    SSD = auto()
    USB_DRIVE = auto()
    SD_CARD = auto()
    EXTERNAL_DRIVE = auto()
    DISK_IMAGE = auto()
    VIRTUAL = auto()
    UNKNOWN = auto()


class FileSystemType(Enum):
    """Supported file system types."""
    NTFS = "NTFS"
    FAT32 = "FAT32"
    EXFAT = "exFAT"
    EXT4 = "EXT4"
    APFS = "APFS"
    HFS_PLUS = "HFS+"
    UNKNOWN = "Unknown"
    UNSUPPORTED = "Unsupported"


@dataclass
class DeviceInfo:
    """
    Represents a storage device available for forensic analysis.
    """

    device_id: str
    path: str
    label: str
    device_type: DeviceType
    file_system: FileSystemType

    total_size: int
    free_space: int

    is_removable: bool
    is_read_only: bool = False

    serial_number: Optional[str] = None
    model: Optional[str] = None

    is_trim_enabled: Optional[bool] = None

    mount_point: Optional[Path] = None
    last_scanned: Optional[datetime] = None

    health_status: Optional[int] = None

    partition_table: Optional[str] = None
    sector_size: Optional[int] = None
    encryption_status: Optional[str] = None
    smart_status: Optional[str] = None


    def __post_init__(self):
        """Validate device information."""

        if self.total_size < 0:
            raise ValueError(
                "Total size cannot be negative"
            )

        if self.free_space < 0:
            raise ValueError(
                "Free space cannot be negative"
            )

        if self.free_space > self.total_size:
            raise ValueError(
                "Free space cannot exceed total size"
            )

        if self.health_status is not None:
            if not 0 <= self.health_status <= 100:
                raise ValueError(
                    "Health status must be between 0 and 100"
                )


    @property
    def used_space(self) -> int:
        """Calculate used storage space."""
        return self.total_size - self.free_space


    @property
    def usage_percentage(self) -> float:
        """Calculate percentage of storage used."""

        if self.total_size == 0:
            return 0.0

        return round(
            (self.used_space / self.total_size) * 100,
            2
        )


    @property
    def display_size(self) -> str:
        """Return human-readable storage size."""

        return self._format_bytes(
            self.total_size
        )


    @property
    def has_trim_warning(self) -> bool:
        """
        Check whether SSD TRIM may reduce recovery chances.
        """

        return (
            self.device_type == DeviceType.SSD
            and self.is_trim_enabled is True
        )


    @property
    def recovery_risk(self) -> str:
        """
        Estimate recovery difficulty.
        """

        if self.has_trim_warning:
            return "HIGH"

        if self.health_status is not None:
            if self.health_status < 50:
                return "MEDIUM"

        if self.is_read_only:
            return "LOW"

        return "LOW"


    @property
    def can_create_image(self) -> bool:
        """
        Determine if forensic imaging is possible.
        """

        return True


    @staticmethod
    def _format_bytes(size_bytes: int) -> str:
        """
        Convert bytes into readable format.
        """

        size = float(size_bytes)

        for unit in [
            "B",
            "KB",
            "MB",
            "GB",
            "TB"
        ]:
            if size < 1024:
                return f"{size:.2f} {unit}"

            size /= 1024

        return f"{size:.2f} PB"


    def to_dict(self) -> dict:
        """
        Convert device object into dictionary.
        """

        return {
            "device_id": self.device_id,
            "path": self.path,
            "label": self.label,

            "device_type": self.device_type.name,
            "file_system": self.file_system.value,

            "total_size": self.total_size,
            "free_space": self.free_space,

            "is_removable": self.is_removable,
            "is_read_only": self.is_read_only,

            "serial_number": self.serial_number,
            "model": self.model,

            "is_trim_enabled": self.is_trim_enabled,

            "mount_point": (
                str(self.mount_point)
                if self.mount_point else None
            ),

            "last_scanned": (
                self.last_scanned.isoformat()
                if self.last_scanned else None
            ),

            "health_status": self.health_status,

            "partition_table": self.partition_table,
            "sector_size": self.sector_size,
            "encryption_status": self.encryption_status,
            "smart_status": self.smart_status
        }


    @classmethod
    def from_dict(cls, data: dict):
        """
        Create DeviceInfo object from dictionary.
        """

        return cls(

            device_id=data["device_id"],
            path=data["path"],
            label=data["label"],

            device_type=DeviceType[
                data["device_type"]
            ],

            file_system=FileSystemType(
                data["file_system"]
            ),

            total_size=data["total_size"],
            free_space=data["free_space"],

            is_removable=data["is_removable"],

            is_read_only=data.get(
                "is_read_only",
                False
            ),

            serial_number=data.get(
                "serial_number"
            ),

            model=data.get(
                "model"
            ),

            is_trim_enabled=data.get(
                "is_trim_enabled"
            ),

            mount_point=(
                Path(data["mount_point"])
                if data.get("mount_point")
                else None
            ),

            last_scanned=(
                datetime.fromisoformat(
                    data["last_scanned"]
                )
                if data.get("last_scanned")
                else None
            ),

            health_status=data.get(
                "health_status"
            ),

            partition_table=data.get(
                "partition_table"
            ),

            sector_size=data.get(
                "sector_size"
            ),

            encryption_status=data.get(
                "encryption_status"
            ),

            smart_status=data.get(
                "smart_status"
            )
        )