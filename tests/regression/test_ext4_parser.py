"""Regression tests for the EXT4 parser (previously a stub that silently
reported success with zero files for every scan).

These tests build a REAL ext4 filesystem via mkfs.ext4 (not a hand-rolled
approximation) when the tool is available on the test machine, mounts it,
writes known files, and verifies the parser reads them back correctly -
including after deletion, where the test also documents the real,
verified ext4 behavior (size/blocks cleared on unlink) rather than
assuming it.

Requires: mkfs.ext4 (e2fsprogs) and root/mount privileges. Skipped
automatically if either is unavailable (e.g. in a restricted CI sandbox);
this is a real-filesystem integration test, not something that can be
faithfully faked with synthetic bytes.
"""
import hashlib
import os
import shutil
import subprocess

import pytest

from core.interfaces.disk_reader import DiskReader, DiskInfo, DeviceType
from infrastructure.filesystems.ext4_parser import EXT4Parser

pytestmark = pytest.mark.skipif(
    shutil.which("mkfs.ext4") is None or os.geteuid() != 0,
    reason="requires mkfs.ext4 and root privileges to build/mount a real ext4 image",
)


class _FileBackedReader(DiskReader):
    def __init__(self, path):
        size = os.path.getsize(path)
        super().__init__(DiskInfo(
            device_type=DeviceType.DISK_IMAGE, device_path=path,
            total_size=size, manufacturer="Test", model="TestImage",
        ))
        self._path = path
        self._f = None

    def open(self):
        self._f = open(self._path, 'rb')
        self._is_open = True

    def close(self):
        if self._f:
            self._f.close()
        self._is_open = False

    def read(self, offset, size):
        self._f.seek(offset)
        return self._f.read(size)


TEXT_CONTENT = b"hello ext4 world - this is a small text file for testing\n"


@pytest.fixture
def real_ext4_image(tmp_path):
    image_path = tmp_path / "ext4_test.img"
    mount_point = tmp_path / "mnt"
    mount_point.mkdir()

    subprocess.run(
        ["dd", "if=/dev/zero", f"of={image_path}", "bs=1M", "count=64"],
        check=True, capture_output=True,
    )
    subprocess.run(["mkfs.ext4", "-q", "-F", str(image_path)], check=True, capture_output=True)
    subprocess.run(["mount", "-o", "loop", str(image_path), str(mount_point)], check=True, capture_output=True)

    try:
        (mount_point / "docs").mkdir()
        (mount_point / "pics").mkdir()
        (mount_point / "docs" / "note.txt").write_bytes(TEXT_CONTENT)
        photo_data = os.urandom(500_000)
        (mount_point / "pics" / "photo.bin").write_bytes(photo_data)
        subprocess.run(["sync"], check=True)
    finally:
        subprocess.run(["umount", str(mount_point)], check=True, capture_output=True)

    return str(image_path), photo_data


def test_ext4_parser_reads_real_files(real_ext4_image):
    image_path, photo_data = real_ext4_image
    reader = _FileBackedReader(image_path)
    reader.open()
    parser = EXT4Parser(reader)

    assert parser.initialize() is True
    assert parser.verify_integrity() is True

    files = {f.filename: f for f in parser.enumerate_files()}
    assert 'note.txt' in files
    assert 'photo.bin' in files

    assert parser.get_file_data(files['note.txt']) == TEXT_CONTENT

    recovered_photo = parser.get_file_data(files['photo.bin'])
    assert hashlib.sha256(recovered_photo).hexdigest() == hashlib.sha256(photo_data).hexdigest()

    reader.close()


def test_ext4_deleted_file_honest_reporting(real_ext4_image):
    """Delete a real file on a real ext4 filesystem and verify the parser
    honestly reports what ext4 actually does on unlink, rather than
    claiming content recovery that cannot happen.

    Verified against a real mkfs.ext4 image during development: deletion
    clears the inode's size and block count (confirmed via debugfs), not
    just the extent pointers. The parser must not hide these entries or
    claim recoverable content it doesn't have.
    """
    image_path, _photo_data = real_ext4_image

    mount_point = os.path.join(os.path.dirname(image_path), "mnt2")
    os.makedirs(mount_point, exist_ok=True)
    subprocess.run(["mount", "-o", "loop", image_path, mount_point], check=True, capture_output=True)
    try:
        os.remove(os.path.join(mount_point, "pics", "photo.bin"))
        subprocess.run(["sync"], check=True)
    finally:
        subprocess.run(["umount", mount_point], check=True, capture_output=True)

    reader = _FileBackedReader(image_path)
    reader.open()
    parser = EXT4Parser(reader)
    parser.initialize()

    remaining = [f.filename for f in parser.enumerate_files()]
    assert 'photo.bin' not in remaining

    deleted = list(parser.get_deleted_files())
    assert len(deleted) >= 1, "deleted inode was not detected at all"

    entry = deleted[0]
    assert entry.deleted_time is not None, "dtime should have been captured"
    # Honest limitation, not a parser bug: ext4 cleared size/blocks on
    # unlink, so content/size cannot be recovered from metadata alone.
    assert entry.metadata.get('content_recoverable') is False
    assert entry.metadata.get('size_recoverable') is False

    reader.close()
