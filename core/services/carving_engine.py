"""File carving engine with signature detection.

IMPORTANT - history of a serious bug fixed here:
Earlier versions of this engine scanned the disk in independent,
non-overlapping fixed-size chunks (default 1MB) and computed both the
candidate file's size AND searched for its footer using only the bytes of
that single in-memory chunk (`len(chunk) - header_offset`). Any file larger
than the remaining bytes in that chunk - which in practice meant almost
every video, and most documents/archives above ~1MB - was silently
truncated to whatever was left in the chunk, then reported as "recovered"
(or "fragmented") with the wrong size. Header signatures that happened to
straddle a chunk boundary were missed entirely, since neither chunk on its
own contained the full header.

This version fixes both problems:
  1. Chunks are read with a small overlap (the longest signature header
     length) so a header split across a chunk boundary is still visible in
     one of the two overlapping reads. Duplicate detections from the
     overlapping region are filtered by absolute on-disk offset.
  2. Once a header is found, file size/footer/structure resolution reads
     forward directly from the disk reader (streamed, in bounded windows),
     never bounded by the size of the single chunk that happened to contain
     the header. This is still fully streaming - it never loads an entire
     candidate file (let alone the whole disk) into memory at once.
"""

import logging
import struct
import threading
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass

from core.interfaces.disk_reader import DiskReader
from core.models.file_signature import FileSignature, SignatureDatabase
from core.models.file_entry import FileEntry, FileStatus, RecoveryConfidence, FileCategory

logger = logging.getLogger(__name__)


def _safe_min_file_size(signature: FileSignature) -> int:
    return max(signature.min_size, 64)


# Conservative maximum candidate size per category, used when a container's
# true size cannot be determined structurally and we must cap a scan. These
# are upper bounds only - real size is used whenever it can be determined
# (RIFF size field, MP4/MOV atom walk, EBML segment size, explicit footer).
_CATEGORY_MAX_SIZE = {
    "jpg": 64 * 1024 * 1024, "jpeg": 64 * 1024 * 1024, "png": 64 * 1024 * 1024,
    "gif": 64 * 1024 * 1024, "bmp": 64 * 1024 * 1024, "tif": 64 * 1024 * 1024,
    "tiff": 64 * 1024 * 1024, "webp": 64 * 1024 * 1024,
    "pdf": 256 * 1024 * 1024, "txt": 128 * 1024 * 1024, "doc": 128 * 1024 * 1024,
    "docx": 256 * 1024 * 1024, "xls": 128 * 1024 * 1024, "xlsx": 256 * 1024 * 1024,
    "ppt": 128 * 1024 * 1024, "pptx": 256 * 1024 * 1024, "zip": 2 * 1024 * 1024 * 1024,
    "rar": 2 * 1024 * 1024 * 1024, "7z": 2 * 1024 * 1024 * 1024, "mp3": 256 * 1024 * 1024,
    "wav": 2 * 1024 * 1024 * 1024,
    "mp4": 8 * 1024 * 1024 * 1024, "mov": 8 * 1024 * 1024 * 1024,
    "avi": 8 * 1024 * 1024 * 1024, "mkv": 8 * 1024 * 1024 * 1024,
    "webm": 8 * 1024 * 1024 * 1024, "flv": 4 * 1024 * 1024 * 1024,
    "mpeg": 8 * 1024 * 1024 * 1024, "mpg": 8 * 1024 * 1024 * 1024,
}
_DEFAULT_MAX_SIZE = 32 * 1024 * 1024

# Read window used when streaming forward from disk to search for a footer
# or walk a container structure. Kept well above typical chunk_size so long
# searches don't require an excessive number of read() calls.
_STREAM_WINDOW = 8 * 1024 * 1024


@dataclass
class CarvedFile:
    """Carved file information."""
    file_id: str
    offset: int
    size: int
    signature: FileSignature
    confidence: RecoveryConfidence
    data: Optional[bytes] = None
    fragmented: bool = False
    fragments: List[Tuple[int, int]] = None
    size_verified: bool = False  # True if size came from real structure/footer, not a cap
    carve_method: str = "signature"  # "header_size", "riff_size", "mp4_atoms", "ebml_segment", "flv_tags", "footer", "cap"

    def __post_init__(self):
        if self.fragments is None:
            self.fragments = [(self.offset, self.size)]

    def to_file_entry(self, index: int = 0) -> FileEntry:
        """Convert to FileEntry."""
        file_category = self.signature.category
        if hasattr(file_category, 'name'):
            try:
                file_category = FileCategory[file_category.name]
            except KeyError:
                file_category = FileCategory.OTHER

        confidence = self.confidence
        if not self.size_verified and confidence.value > RecoveryConfidence.MEDIUM.value:
            # Never report high/excellent confidence for a size we had to
            # cap/guess rather than determine from real structure or footer.
            confidence = RecoveryConfidence.MEDIUM

        return FileEntry(
            file_id=f"carved_{index:06d}",
            filename=f"file_{index:06d}.{self.signature.extension}",
            extension=self.signature.extension,
            file_size=self.size,
            file_category=file_category,
            recovery_confidence=confidence,
            status=FileStatus.DELETED,
            offset=self.offset,
            fragments=self.fragments,
            is_carved=True,
            metadata={
                'carve_method': self.carve_method,
                'size_verified': self.size_verified,
                'fragmented': self.fragmented,
            },
        )


class CarvingEngine:
    """
    File carving engine using signature detection.

    Scans disk for file signatures and extracts files. File extent
    (size/footer/structure) resolution always reads directly from the disk
    reader rather than relying on the bounds of the chunk that contained the
    header, so recovered file size is never silently capped by chunk_size.
    """

    def __init__(
        self,
        disk_reader: DiskReader,
        signatures: Optional[List[FileSignature]] = None,
        min_file_size: int = 1024,
        max_file_size: int = 0,  # 0 = unlimited (use per-type defaults)
        chunk_size: int = 1024 * 1024,  # 1MB
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ):
        self.disk_reader = disk_reader
        self.signatures = signatures or SignatureDatabase.get_all_signatures()
        self.min_file_size = min_file_size
        self.max_file_size = max_file_size
        self.chunk_size = max(chunk_size, 64 * 1024)
        self.progress_callback = progress_callback

        self._lock = threading.Lock()
        self._carved_files: List[CarvedFile] = []
        self._seen_offsets: set = set()
        self._is_cancelled = False

        # Longest header pattern across all signatures, used to size the
        # overlap window between consecutive chunk reads so a header that
        # straddles a chunk boundary is still fully visible at least once.
        self._max_header_len = max(
            (len(s.header or s.signature or b"") for s in self.signatures),
            default=0,
        )
        self._overlap = min(max(self._max_header_len, 16), 4096)

        logger.info(
            f"Carving engine initialized: {len(self.signatures)} signatures, "
            f"chunk_size={self.chunk_size}, overlap={self._overlap}"
        )

    @property
    def carved_files(self) -> List[CarvedFile]:
        return self._carved_files.copy()

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def cancel(self) -> None:
        self._is_cancelled = True
        logger.info("Carving cancelled by user")

    def carve(self) -> List[CarvedFile]:
        """Perform file carving across the full device, streaming."""
        logger.info("Starting carving scan...")

        self._carved_files = []
        self._seen_offsets = set()
        self._is_cancelled = False

        total_size = self.disk_reader.total_size
        total_chunks = (total_size + self.chunk_size - 1) // self.chunk_size

        prev_tail = b""

        try:
            for offset in range(0, total_size, self.chunk_size):
                if self._is_cancelled:
                    break

                try:
                    chunk = self.disk_reader.read(offset, self.chunk_size)
                except Exception as e:
                    logger.warning(f"Error reading at offset {offset}: {e}")
                    prev_tail = b""
                    continue

                if not chunk:
                    prev_tail = b""
                    continue

                # Prepend the tail of the previous chunk so headers that
                # straddle the boundary are still detected.
                search_buffer = prev_tail + chunk
                search_base_offset = offset - len(prev_tail)

                found = self._scan_chunk(search_buffer, search_base_offset)

                for carved in found:
                    if carved.offset in self._seen_offsets:
                        continue
                    self._seen_offsets.add(carved.offset)
                    self._carved_files.append(carved)

                prev_tail = chunk[-self._overlap:] if self._overlap else b""

                current_chunk = offset // self.chunk_size
                progress = (current_chunk / total_chunks) * 100 if total_chunks > 0 else 0
                mb_scanned = offset / (1024 * 1024)
                self._report_progress(
                    progress=progress,
                    current=f"Scanning... {mb_scanned:.1f} MB ({len(self._carved_files)} found)"
                )

            logger.info(f"Carving complete: {len(self._carved_files)} files found")
            return self._carved_files

        except Exception as e:
            logger.exception(f"Carving error: {e}")
            return self._carved_files

    def _scan_chunk(self, chunk: bytes, chunk_offset: int) -> List[CarvedFile]:
        """Scan a chunk (which may include an overlap prefix) for headers."""
        found_files = []

        for signature in self.signatures:
            header = signature.header or signature.signature
            if not header:
                continue

            for header_offset in self._find_signature(chunk, header):
                if not self._validate_header(chunk, header_offset, signature):
                    continue

                file_offset = chunk_offset + header_offset
                if file_offset < 0:
                    continue

                carved = self._resolve_extent(chunk, header_offset, file_offset, signature)
                if carved is None:
                    continue

                found_files.append(carved)
                logger.debug(f"Found {signature.extension} at offset {file_offset}")

        return found_files

    # ------------------------------------------------------------------
    # Extent resolution: everything below reads directly from disk at the
    # file's real absolute offset, never from the bounded chunk buffer.
    # ------------------------------------------------------------------

    def _resolve_extent(self, chunk: bytes, header_offset: int, file_offset: int, signature: FileSignature) -> Optional[CarvedFile]:
        min_size = max(self.min_file_size, _safe_min_file_size(signature))
        max_size = self._max_size_for(signature)

        available = self.disk_reader.total_size - file_offset
        if available < min_size:
            return None
        max_size = min(max_size, available)

        ext = signature.extension.lower()

        # 1. Fixed / header-declared size (e.g. BMP).
        if signature.fixed_size:
            size = signature.fixed_size
            return self._make_carved(file_offset, size, signature, True, "header_size")

        if signature.size_offset and signature.size_length:
            try:
                size_bytes = self.disk_reader.read(
                    file_offset + signature.size_offset, signature.size_length
                )
                size = int.from_bytes(size_bytes, byteorder='big')
                if min_size <= size <= max_size:
                    return self._make_carved(file_offset, size, signature, True, "header_size")
            except Exception:
                pass

        # 2. Structure-aware resolution for containers, using the file's
        #    own declared layout rather than blindly searching for bytes.
        try:
            if ext in {"mp4", "mov"}:
                result = self._resolve_mp4_extent(file_offset, max_size)
                if result:
                    size, verified = result
                    return self._make_carved(file_offset, size, signature, verified, "mp4_atoms")

            if ext in {"mkv", "webm"}:
                result = self._resolve_ebml_extent(file_offset, max_size, ext)
                if result:
                    size, verified = result
                    return self._make_carved(file_offset, size, signature, verified, "ebml_segment")

            if ext in {"avi", "wav", "webp"}:
                result = self._resolve_riff_extent(file_offset, max_size, ext)
                if result:
                    size, verified = result
                    return self._make_carved(file_offset, size, signature, verified, "riff_size")

            if ext == "flv":
                result = self._resolve_flv_extent(file_offset, max_size)
                if result:
                    size, verified = result
                    return self._make_carved(file_offset, size, signature, verified, "flv_tags")

            if ext in {"zip", "docx", "xlsx", "pptx"}:
                result = self._resolve_zip_extent(file_offset, max_size)
                if result:
                    size, verified = result
                    if ext in {"docx", "xlsx", "pptx"}:
                        # docx/xlsx/pptx are all OOXML-in-ZIP and share the
                        # identical PK\x03\x04 signature byte-for-byte -
                        # without checking for type-specific internal
                        # paths, whichever of the three happens to be
                        # first in the signature database would silently
                        # claim every OOXML file regardless of its real
                        # type. "zip" itself has no such requirement,
                        # since it's the correct generic fallback when no
                        # OOXML markers are present.
                        detected = self._detect_ooxml_subtype(file_offset, min(size, 65536))
                        if detected != ext:
                            return None
                    return self._make_carved(file_offset, size, signature, verified, "zip_eocd")
        except Exception as e:
            logger.debug(f"Structural size resolution failed for {ext} at {file_offset}: {e}")

        # 3. Explicit footer marker (JPEG/PNG/etc.).
        if signature.footer:
            footer_end = self._stream_find_footer(file_offset, max_size, signature.footer, min_size)
            if footer_end is not None:
                size = footer_end - file_offset
                return self._make_carved(file_offset, size, signature, True, "footer")
            # Footer not found within the bounded window: this is now a
            # blind/unverified guess, so it gets the same false-positive
            # sanity check as the no-structure-at-all path below, rather
            # than being accepted purely on the strength of a short header
            # match.
            if not self._looks_like_valid_container(chunk, header_offset, signature):
                return None
            return self._make_carved(file_offset, max_size, signature, False, "footer", fragmented=True)

        # 4. No footer, no structural parser available for this type (or it
        #    failed to confirm anything): this is a blind guess bounded
        #    only by a size cap, so it's the one path where we still need
        #    the container-signature sanity check to filter out obvious
        #    false positives from coincidental header-byte matches in
        #    random data.
        if not self._looks_like_valid_container(chunk, header_offset, signature):
            return None
        return self._make_carved(file_offset, max_size, signature, False, "cap", fragmented=True)

    def _make_carved(
        self, file_offset: int, size: int, signature: FileSignature,
        verified: bool, method: str, fragmented: bool = False,
    ) -> Optional[CarvedFile]:
        min_size = max(self.min_file_size, _safe_min_file_size(signature))
        if size < min_size:
            return None
        confidence = self._calculate_confidence(verified, signature)
        return CarvedFile(
            file_id=f"carved_{file_offset:08x}",
            offset=file_offset,
            size=size,
            signature=signature,
            confidence=confidence,
            fragmented=fragmented,
            size_verified=verified,
            carve_method=method,
        )

    def _max_size_for(self, signature: FileSignature) -> int:
        if self.max_file_size:
            return self.max_file_size
        if signature.max_size:
            return signature.max_size
        return _CATEGORY_MAX_SIZE.get(signature.extension.lower(), _DEFAULT_MAX_SIZE)

    def _stream_find_footer(
        self, file_offset: int, max_size: int, footer: bytes, min_size: int,
    ) -> Optional[int]:
        """Search forward from disk in bounded windows for a footer.

        Returns the absolute offset immediately AFTER the footer bytes, or
        None if not found within max_size. Uses overlapping windows so a
        footer split across a window boundary is not missed.
        """
        window = _STREAM_WINDOW
        overlap = len(footer) - 1
        pos = 0
        end_limit = max_size

        while pos < end_limit:
            read_start = max(0, pos - overlap)
            read_size = min(window, end_limit - read_start)
            if read_size <= 0:
                break
            try:
                data = self.disk_reader.read(file_offset + read_start, read_size)
            except Exception:
                break
            if not data:
                break

            idx = data.find(footer)
            if idx != -1:
                return file_offset + read_start + idx + len(footer)

            pos = read_start + read_size

        return None

    _RIFF_FORM_TYPE = {"avi": b"AVI ", "wav": b"WAVE", "webp": b"WEBP"}

    def _resolve_riff_extent(self, file_offset: int, max_size: int, extension: str = "") -> Optional[Tuple[int, bool]]:
        """RIFF containers (AVI/WAV/WebP) declare their own total size.

        AVI, WAV, and WebP all share the same raw 'RIFF' magic bytes in
        the signature database, distinguished only by the 4-byte form-type
        FourCC at offset 8 (e.g. 'AVI ', 'WAVE', 'WEBP'). This must be
        checked here - without it, whichever of the three signatures
        happens to be tried first in iteration order would silently claim
        every RIFF-header match regardless of its real type, since they'd
        all resolve to a plausible size and the engine's offset-based
        duplicate filter would then discard the other two even when they
        were the actually-correct type for that file.
        """
        header = self.disk_reader.read(file_offset, 12)
        if len(header) < 12 or header[0:4] != b"RIFF":
            return None
        expected_form = self._RIFF_FORM_TYPE.get(extension)
        if expected_form and header[8:12] != expected_form:
            return None
        riff_size = struct.unpack('<I', header[4:8])[0]
        total_size = riff_size + 8  # RIFF chunk size excludes the 'RIFF'+size fields themselves
        if total_size < 12:
            return None
        return (min(total_size, max_size), total_size <= max_size)

    def _resolve_mp4_extent(self, file_offset: int, max_size: int) -> Optional[Tuple[int, bool]]:
        """Walk top-level ISO-BMFF (MP4/MOV) atoms/boxes to find the real end.

        Each box starts with a 4-byte big-endian size followed by a 4-byte
        type. size==1 means a 64-bit extended size follows; size==0 means
        "extends to end of file" (only valid for the last box, typically
        'mdat').
        """
        pos = 0
        atom_count = 0
        while pos < max_size and atom_count < 100000:
            hdr = self.disk_reader.read(file_offset + pos, 16)
            if len(hdr) < 8:
                break
            box_size = struct.unpack('>I', hdr[0:4])[0]
            box_type = hdr[4:8]

            if not box_type.isalnum() and box_type not in (b'ftyp', b'moov', b'mdat', b'free', b'skip', b'wide'):
                # Not a plausible box type - stop here, treat what we've
                # walked so far as the (possibly truncated) file extent.
                break

            if box_size == 0:
                # Extends to end of file / end of available data.
                pos = max_size
                break
            elif box_size == 1:
                if len(hdr) < 16:
                    break
                box_size = struct.unpack('>Q', hdr[8:16])[0]

            if box_size < 8:
                break

            pos += box_size
            atom_count += 1

        if pos <= 0:
            return None
        verified = pos <= max_size and atom_count > 0
        return (min(pos, max_size), verified)

    def _resolve_ebml_extent(self, file_offset: int, max_size: int, extension: str = "") -> Optional[Tuple[int, bool]]:
        """Determine MKV/WebM size from the EBML header + Segment element.

        MKV and WebM share the exact same EBML container magic bytes
        (WebM is technically a constrained Matroska profile) - they are
        only distinguished by the DocType string ('matroska' vs 'webm')
        stored as a child element inside the EBML header. That is checked
        here so the two don't mislabel each other's extension; without it,
        whichever signature happens to be tried first in iteration order
        would claim every Matroska-family file regardless of its real
        DocType.

        If the Segment's size field uses the reserved "unknown size"
        pattern (common in live-muxed/streamed files), the true end cannot
        be determined structurally; the caller falls back to a capped,
        unverified size in that case.
        """
        head = self.disk_reader.read(file_offset, 256)
        if len(head) < 8 or head[0:4] != b"\x1A\x45\xDF\xA3":
            return None

        # Parse the EBML header element's own size (vint) to find where it ends.
        ebml_header_len, ebml_size = self._read_ebml_vint(head, 4)
        if ebml_header_len is None:
            return None
        header_body_start = 4 + ebml_header_len
        segment_id_pos = header_body_start + ebml_size

        expected_doctype = {"mkv": b"matroska", "webm": b"webm"}.get(extension)
        if expected_doctype:
            doctype = self._find_ebml_doctype(file_offset, header_body_start, ebml_size)
            if doctype is not None and doctype != expected_doctype:
                return None
            # If DocType couldn't be determined (truncated/unusual
            # header), fall through rather than rejecting outright - we
            # still have a legitimate EBML/Segment match.

        seg_hdr = self.disk_reader.read(file_offset + segment_id_pos, 16)
        if len(seg_hdr) < 4 or seg_hdr[0:4] != b"\x18\x53\x80\x67":  # Segment element ID
            return None

        size_len, seg_size = self._read_ebml_vint(seg_hdr, 4)
        if size_len is None:
            return None

        segment_data_start = segment_id_pos + 4 + size_len
        unknown_size_marker = (1 << (7 * size_len)) - 1  # all-1s value = "unknown size" per EBML spec
        if seg_size == unknown_size_marker:
            # Cannot determine true end from the Segment header alone.
            return (max_size, False)

        total_size = segment_data_start + seg_size
        return (min(total_size, max_size), total_size <= max_size)

    def _find_ebml_doctype(self, file_offset: int, body_start: int, body_size: int) -> Optional[bytes]:
        """Look for the DocType element (ID 0x4282) within the EBML header body."""
        try:
            body = self.disk_reader.read(file_offset + body_start, min(body_size, 512))
        except Exception:
            return None
        pos = 0
        while pos + 2 <= len(body):
            if body[pos:pos + 2] == b"\x42\x82":
                size_len, size = self._read_ebml_vint(body, pos + 2)
                if size_len is None:
                    return None
                value_start = pos + 2 + size_len
                value = body[value_start:value_start + size]
                return value.rstrip(b"\x00")
            pos += 1
        return None

    @staticmethod
    def _read_ebml_vint(data: bytes, offset: int) -> Tuple[Optional[int], Optional[int]]:
        """Read an EBML variable-length size integer starting at offset.

        Returns (encoded_length, value) with the length-marker bit
        stripped from the value, or (None, None) if not decodable.
        """
        if offset >= len(data):
            return None, None
        first = data[offset]
        if first == 0:
            return None, None
        length = 1
        mask = 0x80
        while mask and not (first & mask):
            mask >>= 1
            length += 1
        if offset + length > len(data):
            return None, None
        value = first & (mask - 1)
        for i in range(1, length):
            value = (value << 8) | data[offset + i]
        return length, value

    def _resolve_flv_extent(self, file_offset: int, max_size: int) -> Optional[Tuple[int, bool]]:
        """Walk FLV tags (PreviousTagSize + Tag) to find the real end."""
        head = self.disk_reader.read(file_offset, 9)
        if len(head) < 9 or head[0:3] != b"FLV":
            return None
        data_offset = struct.unpack('>I', b"\x00" + head[5:8])[0]
        pos = data_offset
        tag_count = 0

        while pos + 4 <= max_size and tag_count < 500000:
            prev_size_and_tag_hdr = self.disk_reader.read(file_offset + pos, 15)
            if len(prev_size_and_tag_hdr) < 15:
                break
            # 4 bytes PreviousTagSize, then 11-byte tag header
            tag_type = prev_size_and_tag_hdr[4]
            if tag_type not in (8, 9, 18):  # audio, video, script data
                break
            data_size = struct.unpack('>I', b"\x00" + prev_size_and_tag_hdr[5:8])[0]
            pos += 4 + 11 + data_size
            tag_count += 1

        if tag_count == 0:
            return None
        # Account for the final PreviousTagSize field after the last tag.
        total = min(pos + 4, max_size)
        return (total, pos <= max_size)

    def _resolve_zip_extent(self, file_offset: int, max_size: int) -> Optional[Tuple[int, bool]]:
        """ZIP-based containers (ZIP/DOCX/XLSX/PPTX) end with an End Of
        Central Directory (EOCD) record: signature PK\\x05\\x06 followed by
        an 18-byte fixed structure and an optional comment (length given
        by the last 2 bytes of that fixed structure).

        We scan for the LAST EOCD signature within max_size, not the
        first, since deflated file data inside the archive can
        coincidentally contain the same 4 bytes; the true EOCD is always
        the final one before the archive's real end.
        """
        eocd_sig = b'PK\x05\x06'
        window = _STREAM_WINDOW
        overlap = len(eocd_sig) - 1
        pos = 0
        last_match = None

        while pos < max_size:
            read_size = min(window, max_size - pos)
            if read_size <= 0:
                break
            try:
                data = self.disk_reader.read(file_offset + pos, read_size)
            except Exception:
                break
            if not data:
                break

            search_from = 0
            while True:
                idx = data.find(eocd_sig, search_from)
                if idx == -1:
                    break
                last_match = pos + idx
                search_from = idx + 1

            if read_size < window:
                break
            pos += read_size - overlap

        if last_match is None:
            return None

        eocd_fixed = self.disk_reader.read(file_offset + last_match, 22)
        if len(eocd_fixed) < 22:
            return (min(last_match + 4, max_size), False)

        comment_len = struct.unpack('<H', eocd_fixed[20:22])[0]
        total_size = last_match + 22 + comment_len
        return (min(total_size, max_size), total_size <= max_size)

    _OOXML_MARKERS = (
        (b"word/", "docx"),
        (b"xl/", "xlsx"),
        (b"ppt/", "pptx"),
    )

    def _detect_ooxml_subtype(self, file_offset: int, scan_size: int) -> str:
        """Distinguish docx/xlsx/pptx by scanning early ZIP local-file-header
        entry names for the type-specific top-level folder each OOXML
        format uses internally (word/, xl/, ppt/). Falls back to "zip" if
        none of the three markers are found (a genuine generic archive, or
        one where the markers happen to fall outside the scanned window).
        """
        try:
            data = self.disk_reader.read(file_offset, min(scan_size, 65536))
        except Exception:
            return "zip"
        for marker, subtype in self._OOXML_MARKERS:
            if marker in data:
                return subtype
        return "zip"

    def _find_signature(self, data: bytes, signature: bytes) -> List[int]:
        offsets = []
        start = 0
        while True:
            pos = data.find(signature, start)
            if pos == -1:
                break
            offsets.append(pos)
            start = pos + 1
        return offsets

    def _validate_header(self, data: bytes, offset: int, signature: FileSignature) -> bool:
        pattern = signature.header_pattern or signature.header or signature.signature
        if not pattern:
            return True
        if offset + len(pattern) > len(data):
            return False
        for index, pattern_byte in enumerate(pattern):
            if pattern_byte == ord('.'):
                continue
            if data[offset + index] != pattern_byte:
                return False
        return True

    def _looks_like_valid_container(self, data: bytes, offset: int, signature: FileSignature) -> bool:
        """Reject obvious false positives from random data."""
        ext = signature.extension.lower()
        if ext in {"jpg", "jpeg"}:
            return data[offset:offset + 4] in (b"\xFF\xD8\xFF\xE0", b"\xFF\xD8\xFF\xDB", b"\xFF\xD8\xFF\xE1")
        if ext == "png":
            return data[offset:offset + 8] == b"\x89PNG\r\n\x1a\n"
        if ext == "pdf":
            return data[offset:offset + 5] == b"%PDF-"
        if ext in {"zip", "docx", "xlsx", "pptx"}:
            return data[offset:offset + 4] == b"PK\x03\x04"
        if ext in {"mp4", "mov"}:
            return data[offset:offset + 8].startswith(b"\x00\x00\x00") and b"ftyp" in data[offset:offset + 64]
        if ext in {"mkv", "webm"}:
            return data[offset:offset + 4] == b"\x1A\x45\xDF\xA3"
        if ext == "avi":
            return data[offset:offset + 12].startswith(b"RIFF") and b"AVI " in data[offset + 8:offset + 32]
        if ext == "wav":
            return data[offset:offset + 12].startswith(b"RIFF") and b"WAVE" in data[offset + 8:offset + 32]
        if ext == "webp":
            return data[offset:offset + 12].startswith(b"RIFF") and b"WEBP" in data[offset + 8:offset + 32]
        if ext == "flv":
            return data[offset:offset + 4] == b"FLV\x01"
        return True

    def _calculate_confidence(self, size_verified: bool, signature: FileSignature) -> RecoveryConfidence:
        score = 0.5  # header match
        if size_verified:
            score += 0.3
        if signature.name != "Unknown":
            score += 0.2
        if score >= 0.8:
            return RecoveryConfidence.EXCELLENT
        elif score >= 0.6:
            return RecoveryConfidence.HIGH
        elif score >= 0.4:
            return RecoveryConfidence.MEDIUM
        return RecoveryConfidence.LOW

    def _report_progress(self, progress: float, current: str) -> None:
        if self.progress_callback:
            self.progress_callback(progress, current)
