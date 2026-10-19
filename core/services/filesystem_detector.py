"""Filesystem auto-detection for raw devices and disk images."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class FilesystemDetector:
    """Detect the filesystem type for a storage device or image."""

    @staticmethod
    def detect(disk_reader, partition_offset: int = 0) -> Optional[str]:
        """Return a filesystem label such as NTFS, FAT32, exFAT, EXT4, APFS, or HFS+."""
        try:
            if hasattr(disk_reader, "is_open") and not disk_reader.is_open:
                disk_reader.open()

            boot_sector = disk_reader.read(partition_offset, 512)
            if len(boot_sector) < 512:
                return None

            if boot_sector[3:11] == b"NTFS    ":
                return "NTFS"

            if boot_sector[510:512] == b"\x55\xAA":
                oem = boot_sector[3:11].decode("ascii", errors="ignore").upper()
                if "FAT32" in oem or "FAT16" in oem or "MSDOS" in oem or "FAT" in oem:
                    return "FAT32"

                if boot_sector[82:90] == b"EXFAT   ":
                    return "exFAT"

            if boot_sector[:4] in {b"NXSB", b"APSB", b"NSX"}:
                return "APFS"

            try:
                superblock = disk_reader.read(partition_offset + 1024, 1024)
            except Exception:
                superblock = b""

            if len(superblock) >= 1024:
                if superblock[:2] in {b"H+", b"HX"}:
                    return "HFS+"

                magic = int.from_bytes(superblock[0x38:0x3A], "little")
                if magic == 0xEF53:
                    features = int.from_bytes(superblock[0x5C:0x60], "little")
                    if features & 0x40 or features & 0x80:
                        return "EXT4"
                    return "EXT3/EXT2"

            return None
        except Exception as exc:  # pragma: no cover - safety guard for unreadable media.
            logger.debug("Filesystem detection failed: %s", exc)
            return None
