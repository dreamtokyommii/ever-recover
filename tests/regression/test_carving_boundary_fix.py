"""Regression tests for the carving-engine chunk-boundary truncation bug.

Before the fix, files larger than the scan chunk_size (default 1MB) were
silently truncated because size/footer resolution only looked at the
in-memory chunk buffer that contained the header. These tests build a
synthetic disk image with files that are (a) larger than chunk_size and
(b) deliberately positioned so their headers straddle a chunk boundary,
then verify the carving engine recovers them byte-for-byte.
"""
import hashlib
import os
import struct

import pytest

from core.interfaces.disk_reader import DiskReader, DiskInfo, DeviceType
from core.services.carving_engine import CarvingEngine


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


def _make_riff_avi(payload_size: int) -> bytes:
    content = b"AVI " + os.urandom(payload_size - 4)
    return b"RIFF" + struct.pack('<I', len(content)) + content


def _make_mp4(payload_size: int) -> bytes:
    ftyp = struct.pack('>I', 24) + b'ftyp' + b'isom' + struct.pack('>I', 0) + b'isom' + b'mp41'
    mdat_payload = os.urandom(payload_size)
    mdat = struct.pack('>I', 8 + len(mdat_payload)) + b'mdat' + mdat_payload
    return ftyp + mdat


def _make_jpeg(payload_size: int) -> bytes:
    # Payload deliberately avoids the 0xFF byte entirely so it can never
    # coincidentally contain the FFD9 footer marker - this test is
    # regression-testing the chunk-boundary truncation fix, not the
    # separate, known footer-collision limitation of simple first-match
    # footer search (see synthetic_disk_image fixture docstring).
    payload = bytes(b & 0x7F for b in os.urandom(payload_size))
    return b"\xFF\xD8\xFF\xE0" + b"JFIF_stuff" + payload + b"\xFF\xD9"


@pytest.fixture
def synthetic_disk_image(tmp_path):
    """Build a 32MB image with three known files placed at known,
    deliberately non-chunk-aligned offsets (at least one straddling a 1MB
    chunk boundary in its header), surrounded by zero-filled filler.

    Filler is zero-filled rather than uniform random noise deliberately:
    uniform random bytes are an unrealistic, adversarial worst case for
    footer-marker carving (a 2-byte marker like JPEG's FFD9 has a real
    chance of appearing by pure chance in truly random filler before the
    genuine end-of-file marker, causing an early false match - this is a
    known, industry-wide limitation of simple first-match footer search,
    not something introduced or fixed by this patch). Zero-filled filler
    is far more representative of typical wiped/unallocated disk regions
    and keeps this test focused on what it's actually regression-testing:
    that file size/footer resolution is no longer bounded by chunk_size.
    """
    image_size = 32 * 1024 * 1024
    disk = bytearray(image_size)  # zero-filled
    placements = {}

    jpeg_data = _make_jpeg(50_000)
    off = 1 * 1024 * 1024
    disk[off:off + len(jpeg_data)] = jpeg_data
    placements['jpeg'] = (off, len(jpeg_data))

    avi_data = _make_riff_avi(3 * 1024 * 1024 + 777)
    off = 5 * 1024 * 1024 + 100
    disk[off:off + len(avi_data)] = avi_data
    placements['avi'] = (off, len(avi_data))

    mp4_data = _make_mp4(4 * 1024 * 1024 + 333)
    off = 10 * 1024 * 1024 - 20  # header straddles the 10MB chunk boundary
    disk[off:off + len(mp4_data)] = mp4_data
    placements['mp4'] = (off, len(mp4_data))

    image_path = tmp_path / "test_disk.img"
    image_path.write_bytes(bytes(disk))

    expected = {
        name: {
            'offset': offset,
            'size': size,
            'sha256': hashlib.sha256(bytes(disk[offset:offset + size])).hexdigest(),
        }
        for name, (offset, size) in placements.items()
    }
    return str(image_path), expected


def _carve(image_path):
    reader = _FileBackedReader(image_path)
    reader.open()
    try:
        engine = CarvingEngine(reader, chunk_size=1024 * 1024)  # the historically buggy default
        return engine.carve(), reader
    finally:
        pass  # reader closed by caller after using it for verification reads


def test_large_files_recovered_byte_exact(synthetic_disk_image):
    image_path, expected = synthetic_disk_image
    carved, reader = _carve(image_path)

    ext_map = {'jpeg': 'jpg', 'avi': 'avi', 'mp4': 'mp4'}
    by_ext = {}
    for c in carved:
        by_ext.setdefault(c.signature.extension, []).append(c)

    for name, exp in expected.items():
        ext = ext_map[name]
        matches = [c for c in by_ext.get(ext, []) if c.offset == exp['offset']]
        assert matches, f"{name}: not found at expected offset {exp['offset']}"
        carved_file = matches[0]

        # This is the core regression check: before the fix, size was
        # capped by whatever remained in the 1MB chunk that contained the
        # header, so this would fail for the ~3MB AVI and ~4MB MP4.
        assert carved_file.size == exp['size'], (
            f"{name}: recovered size {carved_file.size} != expected "
            f"{exp['size']} (this is exactly the historical truncation bug "
            f"if the recovered size is capped near 1MB)"
        )
        assert carved_file.size_verified, f"{name}: size should be structurally verified"

        data = reader.read(carved_file.offset, carved_file.size)
        assert hashlib.sha256(data).hexdigest() == exp['sha256'], (
            f"{name}: recovered content does not match original bytes"
        )

    reader.close()


def test_header_straddling_chunk_boundary_is_detected(synthetic_disk_image):
    """The MP4 header in the fixture is placed 20 bytes before a 1MB chunk
    boundary, so its 8-byte ftyp-box-size header spans two chunks. Before
    overlapping-chunk reads were added, this header could be missed
    entirely."""
    image_path, expected = synthetic_disk_image
    carved, reader = _carve(image_path)
    reader.close()

    mp4_offset = expected['mp4']['offset']
    found = [c for c in carved if c.signature.extension == 'mp4' and c.offset == mp4_offset]
    assert found, "MP4 header straddling a chunk boundary was not detected"


def test_ooxml_subtypes_are_correctly_distinguished(tmp_path):
    """docx/xlsx/pptx share the identical PK\\x03\\x04 ZIP signature.
    Without checking the type-specific internal folder (word/, xl/,
    ppt/), whichever of the three happens to be first in the signature
    database would silently claim every OOXML file regardless of its
    real type."""
    import zipfile
    import io as _io

    def _make_xlsx():
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('[Content_Types].xml', '<Types/>' + 'A' * 1200)
            z.writestr('xl/workbook.xml', '<workbook/>')
        return buf.getvalue()

    def _make_docx():
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('[Content_Types].xml', '<Types/>')
            z.writestr('word/document.xml', '<document>' + 'A' * 1200 + '</document>')
        return buf.getvalue()

    xlsx_bytes = _make_xlsx()
    docx_bytes = _make_docx()

    disk = bytearray(1024 * 1024)
    off_xlsx, off_docx = 10_000, 500_000
    disk[off_xlsx:off_xlsx + len(xlsx_bytes)] = xlsx_bytes
    disk[off_docx:off_docx + len(docx_bytes)] = docx_bytes

    image_path = tmp_path / "ooxml_test.img"
    image_path.write_bytes(bytes(disk))

    reader = _FileBackedReader(str(image_path))
    reader.open()
    engine = CarvingEngine(reader, chunk_size=1024 * 1024)
    carved = engine.carve()
    reader.close()

    by_offset = {c.offset: c for c in carved}
    assert off_xlsx in by_offset and by_offset[off_xlsx].signature.extension == 'xlsx'
    assert off_docx in by_offset and by_offset[off_docx].signature.extension == 'docx'
