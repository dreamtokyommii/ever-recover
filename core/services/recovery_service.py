"""Application service selecting safe copy-only or NTFS undelete mode."""

import logging
import os
import platform
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from infrastructure.disk.factory import create_disk_reader
from .ntfs_recovery_engine import NTFSRecoveryEngine, RecoveryItem, RecoveryStatus
from .recovery_report import RecoveryReport

logger = logging.getLogger(__name__)


class SourceType(str, Enum):
    FOLDER = "folder"
    NTFS_IMAGE = "ntfs_image"
    RAW_DEVICE = "raw_device"
    UNSUPPORTED = "unsupported"


def classify_source(source_path: str) -> SourceType:
    path = Path(source_path)
    if path.is_dir():
        return SourceType.FOLDER
    if platform.system() == "Windows" and source_path.lower().startswith("\\\\.\\"):
        return SourceType.RAW_DEVICE
    if path.is_file():
        return SourceType.NTFS_IMAGE
    return SourceType.UNSUPPORTED


class RecoveryService:
    def __init__(self, software_version: str = "1.0.0"):
        self.software_version = software_version

    def run(self, source_path: str, output_path: str,
            progress: Optional[Callable] = None) -> RecoveryReport:
        source_type = classify_source(source_path)
        start = datetime.now().astimezone()
        output = Path(output_path)
        errors: List[str] = []
        if source_type == SourceType.FOLDER:
            items = self._copy_folder(source_path, output)
            mode = "copy_only"
        elif source_type in {SourceType.NTFS_IMAGE, SourceType.RAW_DEVICE}:
            items = []
            mode = "ntfs_undelete"
            reader = create_disk_reader(source_path, force_image=source_type == SourceType.NTFS_IMAGE)
            try:
                reader.open()
                items = NTFSRecoveryEngine(reader).recover(output, progress)
            except Exception as exc:
                errors.append(str(exc))
                logger.exception("Recovery job failed")
            finally:
                reader.close()
        else:
            items = []
            mode = "unsupported"
            errors.append("Unsupported source; no data was read")
        report = RecoveryReport(source_path, str(output), mode, start, items,
                    self.software_version, errors)
        report_dir = output / "reports"
        report.write_json(report_dir / "recovery_report.json")
        report.write_csv(report_dir / "recovery_items.csv")
        return report

    def _copy_folder(self, source_path: str, output: Path) -> List[RecoveryItem]:
        destination = output / "copied_files"
        destination.mkdir(parents=True, exist_ok=True)
        items = []
        for root, _, names in os.walk(source_path):
            for name in names:
                source = Path(root) / name
                relative = source.relative_to(source_path)
                target = destination / relative
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    size = source.stat().st_size
                    items.append(RecoveryItem("folder", "copy_only", None, name, str(relative),
                        source.suffix.lstrip("."), size, False, RecoveryStatus.COPY_ONLY.value,
                        size, size, str(target)))
                except OSError as exc:
                    items.append(RecoveryItem("folder", "copy_only", None, name, str(relative),
                        source.suffix.lstrip("."), 0, False, RecoveryStatus.UNRECOVERABLE.value,
                        0, 0, error_message=str(exc)))
        return items