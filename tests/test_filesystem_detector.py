from core.interfaces.disk_reader import VirtualDiskReader
from core.services.filesystem_detector import FilesystemDetector


def test_detects_ntfs_from_boot_sector():
    disk = bytearray(4096)
    disk[3:11] = b"NTFS    "
    disk[510:512] = b"\x55\xAA"
    result = FilesystemDetector.detect(VirtualDiskReader(bytes(disk)))
    assert result == "NTFS"


def test_detects_fat32_from_boot_sector():
    disk = bytearray(4096)
    disk[3:11] = b"MSDOS5.1"
    disk[510:512] = b"\x55\xAA"
    result = FilesystemDetector.detect(VirtualDiskReader(bytes(disk)))
    assert result == "FAT32"


def test_detects_exfat_from_volume_label():
    disk = bytearray(4096)
    disk[82:90] = b"EXFAT   "
    disk[510:512] = b"\x55\xAA"
    result = FilesystemDetector.detect(VirtualDiskReader(bytes(disk)))
    assert result == "exFAT"
