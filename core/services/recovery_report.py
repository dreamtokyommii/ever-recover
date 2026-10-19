"""Audit and result reports for recovery jobs."""

import csv
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from .ntfs_recovery_engine import RecoveryItem, RecoveryStatus


class RecoveryReport:
    def __init__(self, source_path: str, output_path: str, mode: str,
                 start_time: datetime, items: Iterable[RecoveryItem],
                 software_version: str = "1.0.0", errors: Optional[List[str]] = None,
                 end_time: Optional[datetime] = None):
        self.source_path = source_path
        self.output_path = output_path
        self.mode = mode
        self.start_time = start_time
        self.end_time = end_time or datetime.now().astimezone()
        self.software_version = software_version
        self.items = list(items)
        self.errors = list(errors or [])

    def document(self) -> dict:
        counts = {status.value: 0 for status in RecoveryStatus}
        for item in self.items:
            counts[item.recovery_status] = counts.get(item.recovery_status, 0) + 1
        return {"source": {"path": self.source_path, "read_only": True},
                "output_path": self.output_path, "mode": self.mode,
                "software_version": self.software_version, "host": platform.node(),
                "start_timestamp": self.start_time.isoformat(),
                "end_timestamp": self.end_time.isoformat(), "errors": self.errors,
                "counts": counts, "items": [item.to_dict() for item in self.items]}

    def write_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.document(), indent=2), encoding="utf-8")
        return path

    def write_csv(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = list(RecoveryItem.__dataclass_fields__)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(item.to_dict() for item in self.items)
        return path