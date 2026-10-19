"""Read-only NTFS undelete engine."""

import hashlib
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from core.models.file_entry import FileEntry
from infrastructure.filesystems.ntfs_parser import NTFSParser

logger = logging.getLogger(__name__)


class RecoveryStatus(str, Enum):
    FULLY_RECOVERED = "fully_recovered"
    PARTIALLY_RECOVERED = "partially_recovered"
    UNRECOVERABLE = "unrecoverable"
    COPY_ONLY = "copy_only"


@dataclass
class RecoveryItem:
    source_type: str
    mode: str
    record_number: Optional[int]
    filename: str
    original_path: str
    extension: str
    size: int
    deleted: bool
    recovery_status: str
    bytes_recovered: int
    bytes_expected: int
    output_path: Optional[str] = None
    timestamp_created: Optional[str] = None
    timestamp_modified: Optional[str] = None
    error_message: Optional[str] = None
    sha256: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _timestamp(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


class NTFSRecoveryEngine:
    """Recover deleted NTFS files using MFT metadata and raw cluster reads."""

    def __init__(self, disk_reader, partition_offset: int = 0):
        self.disk_reader = disk_reader
        self.parser = NTFSParser(disk_reader, partition_offset)

    def discover_deleted(self) -> List[FileEntry]:
        self.parser.initialize()
        self.parser.parse_metadata()
        return list(self.parser.get_deleted_files())

    def recover(self, output_dir: Path, progress=None) -> List[RecoveryItem]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        entries = self.discover_deleted()
        items = []
        for index, entry in enumerate(entries):
            items.append(self._recover_entry(entry, output_dir))
            if progress:
                progress(index + 1, len(entries), entry.filename)
        return items

    def _recover_entry(self, entry: FileEntry, output_dir: Path) -> RecoveryItem:
        record_number = entry.metadata.get("mft_record")
        base = dict(source_type="ntfs_image_or_volume", mode="ntfs_undelete",
                    record_number=record_number, filename=entry.filename,
                    original_path=entry.metadata.get("original_path") or f"/{entry.filename}",
                    extension=entry.extension, size=entry.file_size, deleted=True,
                    bytes_expected=entry.file_size,
                    timestamp_created=_timestamp(entry.created_time),
                    timestamp_modified=_timestamp(entry.modified_time))
        try:
            data = self.parser.get_file_data(entry)
            recovered = min(len(data), entry.file_size)
            if entry.file_size and not data:
                raise IOError("No data remained in resident attribute or data runs")
            status = (RecoveryStatus.FULLY_RECOVERED if recovered == entry.file_size
                      else RecoveryStatus.PARTIALLY_RECOVERED)
            target = output_dir / self._safe_name(entry.filename, record_number)
            target.write_bytes(data[:entry.file_size])
            return RecoveryItem(**base, recovery_status=status.value, bytes_recovered=recovered,
                                output_path=str(target),
                                sha256=hashlib.sha256(data[:entry.file_size]).hexdigest())
        except Exception as exc:
            logger.warning("Unable to recover MFT record %s: %s", record_number, exc)
            return RecoveryItem(**base, recovery_status=RecoveryStatus.UNRECOVERABLE.value,
                                bytes_recovered=0, error_message=str(exc))

    @staticmethod
    def _safe_name(filename: str, record_number: Optional[int]) -> str:
        name = Path(filename or "unknown").name
        if name in {"", ".", ".."}:
            name = "unknown"
        return f"{record_number}_{name}" if record_number is not None else name