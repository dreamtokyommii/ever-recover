from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFrame, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QComboBox, QCheckBox, QRadioButton, QButtonGroup, QTextEdit, QFileDialog,
    QMessageBox, QSizePolicy, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer
import sys
import os
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import shutil

from core.services.recovery_engine import RecoveryEngine, RecoveryConfig
from core.services.recovery_engine import RecoveryOrchestrator
from core.services.report_generator import ReportGenerator, ReportMetadata
from core.services.filesystem_detector import FilesystemDetector
from core.models.file_entry import FileCategory, RecoveryConfidence, FileStatus
from infrastructure.disk.factory import create_disk_reader
from infrastructure.filesystems import NTFSParser, FAT32Parser
from core.services.privilege_manager import (
    ensure_admin_for_source, is_windows, is_elevated, request_elevation,
)
from core.services.recovery_service import classify_source, SourceType
from core.interfaces.disk_reader import AccessDeniedError

EXTENSION_FILE_CATEGORY_MAP = {
    'jpg': FileCategory.IMAGE,
    'jpeg': FileCategory.IMAGE,
    'png': FileCategory.IMAGE,
    'gif': FileCategory.IMAGE,
    'bmp': FileCategory.IMAGE,
    'tiff': FileCategory.IMAGE,
    'mp4': FileCategory.VIDEO,
    'mov': FileCategory.VIDEO,
    'avi': FileCategory.VIDEO,
    'mkv': FileCategory.VIDEO,
    'pdf': FileCategory.DOCUMENT,
    'doc': FileCategory.DOCUMENT,
    'docx': FileCategory.DOCUMENT,
    'xls': FileCategory.DOCUMENT,
    'xlsx': FileCategory.DOCUMENT,
    'ppt': FileCategory.DOCUMENT,
    'pptx': FileCategory.DOCUMENT,
    'txt': FileCategory.DOCUMENT,
    'csv': FileCategory.DOCUMENT,
    'zip': FileCategory.ARCHIVE,
    'rar': FileCategory.ARCHIVE,
    '7z': FileCategory.ARCHIVE,
    'iso': FileCategory.ARCHIVE,
    'db': FileCategory.DATABASE,
    'sql': FileCategory.DATA,
    'json': FileCategory.DATA,
    'xml': FileCategory.DATA,
    'py': FileCategory.SOURCE_CODE,
    'js': FileCategory.SOURCE_CODE,
    'html': FileCategory.SOURCE_CODE,
    'css': FileCategory.SOURCE_CODE,
    'exe': FileCategory.EXECUTABLE,
    'dll': FileCategory.EXECUTABLE,
    'sys': FileCategory.SYSTEM,
}

TEXT_PREVIEW_EXTENSIONS = {
    'txt', 'log', 'csv', 'json', 'xml', 'py', 'js', 'html', 'css', 'md', 'ini', 'cfg'
}


def resolve_output_layout(base_output: str) -> dict:
    default_base = os.path.join(os.path.expanduser("~"), "Desktop", "ever_recover")
    base_path = os.path.abspath(base_output or default_base)
    recovered_files_dir = os.path.join(base_path, "recovered_files")
    reports_dir = os.path.join(base_path, "reports")
    for path in [base_path, recovered_files_dir, reports_dir]:
        os.makedirs(path, exist_ok=True)
    return {
        "base": base_path,
        "recovered_files": recovered_files_dir,
        "reports": reports_dir,
    }


def categorize_extension(extension: str) -> FileCategory:
    return EXTENSION_FILE_CATEGORY_MAP.get(extension.lower().lstrip('.'), FileCategory.OTHER)


def build_file_preview(path: str) -> str:
    if not path or not os.path.exists(path) or not os.path.isfile(path):
        return "Preview unavailable for recovered file."

    ext = Path(path).suffix.lower().lstrip('.')
    if ext in TEXT_PREVIEW_EXTENSIONS:
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as handle:
                return handle.read(1024)
        except Exception:
            return "Text preview unavailable for this file."

    return f"Preview unavailable for binary file type: .{ext}."


class RecoveryScanner(QObject):
    scan_progress = pyqtSignal(int)
    scan_status = pyqtSignal(str)
    scan_completed = pyqtSignal(object, list, dict)
    scan_failed = pyqtSignal(str)
    scan_requires_elevation = pyqtSignal(str, str)  # (source_path, reason)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: Optional[threading.Thread] = None
        self._settings: Dict[str, Any] = {}
        self._is_running = False

    def start_scan(self, settings: dict):
        if self._is_running:
            return

        self._settings = settings.copy()
        self._thread = threading.Thread(target=self._run_scan, args=(self._settings,), daemon=True)
        self._thread.start()

    def _run_scan(self, settings: dict):
        self._is_running = True
        self.scan_status.emit("Preparing scan environment…")
        self.scan_progress.emit(0)

        try:
            source_path = settings.get("source_path", "").strip()
            if not source_path:
                raise ValueError("Source path must be set before scanning.")

            if os.path.isdir(source_path):
                self.scan_status.emit("Copy-only mode")
                scan_result, records, summary = self._scan_folder(source_path, settings)
            else:
                if classify_source(source_path) in {SourceType.NTFS_IMAGE, SourceType.RAW_DEVICE}:
                    self.scan_status.emit("NTFS recovery mode; source is read-only")
                scan_result, records, summary = self._scan_image_or_device(source_path, settings)

            self.scan_progress.emit(100)
            self.scan_status.emit("Scan complete")
            self.scan_completed.emit(scan_result, records, summary)

        except (PermissionError, AccessDeniedError) as exc:
            # Raw disk/volume access requires elevation. Surface this as a
            # distinct signal so the UI can offer to relaunch as admin,
            # instead of leaving the user with a dead-end error dialog.
            source_path = settings.get("source_path", "").strip()
            self.scan_status.emit("Administrator privileges required")
            self.scan_requires_elevation.emit(source_path, str(exc))
        except Exception as exc:
            self.scan_failed.emit(str(exc))
            self.scan_status.emit(f"Scan failed: {exc}")
        finally:
            self._is_running = False

    def _scan_folder(self, source_path: str, settings: dict):
        self.scan_status.emit("Scanning local folder…")
        records = []
        total_size = 0
        file_paths = []

        for root, _, filenames in os.walk(source_path):
            for filename in filenames:
                file_paths.append(os.path.join(root, filename))

        total_files = len(file_paths)
        scanned_files = 0
        last_progress = -1

        for full_path in file_paths:
            scanned_files += 1
            try:
                stat = os.stat(full_path)
            except OSError:
                continue

            size = stat.st_size
            total_size += size
            filename = os.path.basename(full_path)
            extension = Path(filename).suffix.lower().lstrip('.')
            record = {
                "name": filename,
                "type": extension.upper() if extension else "FILE",
                "size": size,
                "status": "Copy-only",
                "recovery_status": "copy_only",
                "mode": "copy_only",
                "path": full_path,
                "category": categorize_extension(extension).name.title(),
                "preview": "Preview available on selection.",
            }
            if settings.get("timeline_scan", False):
                record["modified"] = datetime.fromtimestamp(stat.st_mtime)
                record["accessed"] = datetime.fromtimestamp(stat.st_atime)
            records.append(record)

            if total_files > 0 and scanned_files % 25 == 0:
                progress = min(int((scanned_files / total_files) * 100), 100)
                if progress >= last_progress + 5 or progress == 100:
                    self.scan_progress.emit(progress)
                    last_progress = progress

        timeline_entries = []
        if settings.get("timeline_scan", False):
            for record in records:
                if "modified" in record and "accessed" in record:
                    timeline_entries.append({
                        "path": record["path"],
                        "modified": record["modified"],
                        "accessed": record["accessed"],
                    })

        summary = {
            "duration": 0,
            "total_files": len(records),
            "recoverable_files": 0,
            "copied_files": len(records),
            "recovery_status": "copy_only",
            "deleted_files": 0,
            "scan_mode": settings.get("scan_mode", "Quick Scan"),
            "scan_profile": settings.get("scan_profile", "Forensic Analysis"),
            "filesystem": "Local Folder",
            "timeline_scan": settings.get("timeline_scan", False),
            "timeline_entries": len(timeline_entries),
        }

        from core.models.scan_result import ScanResult, ScanStatistics
        from core.models.file_entry import FileEntry, FileStatus
        from core.models.device import DeviceInfo, DeviceType, FileSystemType

        file_entries = []
        for record in records:
            file_entries.append(FileEntry(
                file_id=f"local_{len(file_entries):06d}",
                filename=record["name"],
                extension=Path(record["name"]).suffix.lower().lstrip('.'),
                file_size=record["size"],
                file_category=FileCategory[record["category"].upper()] if record["category"].upper() in FileCategory.__members__ else FileCategory.OTHER,
                recovery_confidence=RecoveryConfidence.EXCELLENT,
                status=FileStatus.EXISTING,
                parent_directory=os.path.dirname(record["path"]),
                metadata={"path": record["path"]},
                preview_available=Path(record["path"]).suffix.lower().lstrip('.') in TEXT_PREVIEW_EXTENSIONS,
            ))

        scan_result = ScanResult(
            scan_id=f"folder_{int(time.time())}",
            device=DeviceInfo(
                device_id=source_path,
                path=source_path,
                label=os.path.basename(source_path) or source_path,
                device_type=DeviceType.VIRTUAL,
                file_system=FileSystemType.UNKNOWN,
                total_size=total_size,
                free_space=0,
                is_removable=False,
            ),
            start_time=datetime.now(),
            files=file_entries,
            statistics=ScanStatistics(
                total_files=len(records),
                deleted_files=0,
                existing_files=len(records),
                total_size=total_size,
                recoverable_files=len(records),
                files_by_category={r['category']: sum(1 for x in records if x['category'] == r['category']) for r in records},
            ),
            is_complete=True,
        )

        return scan_result, records, summary

    def _scan_image_or_device(self, source_path: str, settings: dict):
        self.scan_status.emit("Opening evidence source…")
        disk_reader = None
        scan_result = None
        records = []
        summary = {}

        try:
            ensure_admin_for_source(source_path, reason="This evidence source is a raw disk or volume; please run the app as Administrator.")

            if os.path.isfile(source_path):
                disk_reader = create_disk_reader(source_path, force_image=True)
            else:
                disk_reader = create_disk_reader(source_path)

            disk_reader.open()
            config = self._build_config(settings)
            parser = self._create_parser(settings, disk_reader) if config.scan_file_system else None
            engine = RecoveryEngine(
                disk_reader=disk_reader,
                filesystem_parser=parser,
                config=config,
                progress_callback=self._on_recovery_progress,
            )

            scan_result = engine.scan()
            if scan_result.error_message:
                raise RuntimeError(scan_result.error_message)

            records = self._file_entries_to_records(scan_result.files)
            summary = self._build_summary(scan_result, settings)

            return scan_result, records, summary

        finally:
            if disk_reader:
                disk_reader.close()

    def _build_config(self, settings: dict) -> RecoveryConfig:
        config = RecoveryConfig()
        scan_type = settings.get("scan_type", "Hybrid")
        scan_mode = settings.get("scan_mode", "Quick Scan")
        profile = settings.get("scan_profile", "Forensic Analysis")

        config.scan_file_system = scan_type != "File Carving Only"
        config.scan_carving = scan_type != "File System Only"

        if scan_mode == "Quick Scan":
            config.scan_carving = False
        elif scan_mode == "Timeline Scan":
            config.scan_carving = False
            config.scan_file_system = True

        if profile == "Deleted File Recovery":
            config.recover_deleted = True
            config.recover_existing = False
            config.min_confidence = RecoveryConfidence.LOW
        elif profile == "Rapid Restore":
            config.recover_deleted = False
            config.recover_existing = True
            config.min_confidence = RecoveryConfidence.HIGH
        elif profile == "Deep Carving":
            config.scan_carving = True
            config.min_confidence = RecoveryConfidence.LOW
            config.max_threads = 8

        return config

    def _create_parser(self, settings: dict, disk_reader):
        filesystem = settings.get("filesystem", "Auto Detect")

        if filesystem == "Auto Detect":
            detected = self._detect_filesystem(disk_reader)
            if detected:
                filesystem = detected
                self.scan_status.emit(f"Auto-detected filesystem: {filesystem}")
            else:
                if settings.get('scan_type', 'Hybrid') in {"File Carving Only", "Hybrid"}:
                    self.scan_status.emit("Auto-detect failed; proceeding with carving-only.")
                    return None
                raise RuntimeError("Unable to detect filesystem automatically. Select a filesystem or enable carving-only mode.")

        # Map filesystem names to parser implementations where available
        parser = None
        try:
            if filesystem == "NTFS":
                parser = NTFSParser(disk_reader)
            elif filesystem in {"FAT32", "exFAT"}:
                parser = FAT32Parser(disk_reader)
            elif filesystem in {"EXT4", "EXT3/EXT2"}:
                from infrastructure.filesystems.ext4_parser import EXT4Parser
                parser = EXT4Parser(disk_reader)
            elif filesystem == "APFS":
                from infrastructure.filesystems.apfs_parser import APFSParser
                parser = APFSParser(disk_reader)
            elif filesystem in {"HFS+", "HFS"}:
                from infrastructure.filesystems.hfs_parser import HFSPlusParser
                parser = HFSPlusParser(disk_reader)
            else:
                if settings.get('scan_type', 'Hybrid') in {"File Carving Only", "Hybrid"}:
                    self.scan_status.emit(f"No parser for {filesystem}; proceeding with carving-only.")
                    return None
                raise RuntimeError(f"Unsupported filesystem for scanning: {filesystem}")
        except Exception as exc:
            if settings.get('scan_type', 'Hybrid') in {"File Carving Only", "Hybrid"}:
                self.scan_status.emit(f"Parser initialization failed ({exc}); switching to carving-only.")
                return None
            raise RuntimeError(f"Failed to initialize filesystem parser: {exc}")

        try:
            parser.initialize()
            parser.parse_metadata()
            return parser
        except Exception as exc:
            # Initialization/metadata parsing can fail for reasons that
            # aren't constructor-time problems: an unsupported filesystem
            # honestly declining to fake support (e.g. APFS/HFS+ in this
            # build), a corrupted boot sector/superblock, etc. Degrade to
            # carving-only when the scan configuration allows it, rather
            # than crashing the whole scan or silently reporting zero
            # files as a false success.
            if settings.get('scan_type', 'Hybrid') in {"File Carving Only", "Hybrid"}:
                self.scan_status.emit(
                    f"Filesystem parsing unavailable ({exc}); switching to carving-only."
                )
                return None
            raise RuntimeError(f"Failed to parse filesystem metadata: {exc}")

    def _detect_filesystem(self, disk_reader):
        return FilesystemDetector.detect(disk_reader)

    def _on_recovery_progress(self, progress):
        if hasattr(progress, 'progress'):
            percent = min(max(int(progress.progress), 0), 100)
            self.scan_progress.emit(percent)
        if hasattr(progress, 'phase') and hasattr(progress, 'current_file'):
            label = f"{progress.phase.title()}: {progress.current_file}"
            self.scan_status.emit(label)

    def _file_entries_to_records(self, file_entries):
        records = []
        for entry in file_entries:
            path = entry.parent_directory or entry.metadata.get('path', '') or ''
            if path and entry.filename and not path.endswith(entry.filename):
                path = os.path.join(path, entry.filename)

            records.append({
                "name": entry.display_name,
                "type": entry.extension.upper() if entry.extension else "FILE",
                "size": entry.file_size,
                "status": entry.status.name.title(),
                "recovery_status": "copy_only" if entry.status == FileStatus.EXISTING else entry.status.value,
                "mode": "copy_only" if entry.status == FileStatus.EXISTING and path else "ntfs_undelete",
                "path": path or "<disk>",
                "category": entry.file_category.name.title(),
                "preview": entry.metadata.get('preview', "Preview unavailable."),
                "confidence": entry.recovery_confidence.name,
                "entry": entry,
            })
        return records

    def _build_summary(self, scan_result, settings: dict):
        return {
            "duration": int(scan_result.duration),
            "total_files": scan_result.statistics.total_files,
            "recoverable_files": scan_result.statistics.recoverable_files,
            "deleted_files": scan_result.statistics.deleted_files,
            "scan_mode": settings.get("scan_mode", "Quick Scan"),
            "scan_profile": settings.get("scan_profile", "Forensic Analysis"),
            "filesystem": settings.get("filesystem", "Auto Detect"),
            "timeline_scan": settings.get("timeline_scan", False),
        }


class ReportWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, scan_result, metadata, file_format: str, output_path: str):
        super().__init__()
        self.scan_result = scan_result
        self.metadata = metadata
        self.file_format = file_format
        self.output_path = output_path

    def run(self):
        try:
            generator = ReportGenerator(self.scan_result, self.metadata)
            if self.file_format == "pdf":
                generator.generate_pdf(Path(self.output_path))
            elif self.file_format == "html":
                generator.generate_html(Path(self.output_path))
            elif self.file_format == "csv":
                generator.generate_csv(Path(self.output_path))
            elif self.file_format == "json":
                generator.generate_json(Path(self.output_path))
            else:
                raise ValueError("Unsupported format")

            self.finished.emit(self.output_path)
        except Exception as exc:
            self.error.emit(str(exc))


class RecoveryWorker(QObject):
    completed = pyqtSignal(dict)
    error = pyqtSignal(str)
    status = pyqtSignal(str)
    requires_elevation = pyqtSignal(str, str)  # (source_path, reason)

    def __init__(self, files: list, output_folder: str, scan_result):
        super().__init__()
        self.files = files
        self.output_folder = output_folder
        self.scan_result = scan_result

    def run(self):
        results = {"copied": 0, "recovered": 0, "failed": 0}
        image_entries = [f for f in self.files if f.get("entry")]
        local_files = [f for f in self.files if not f.get("entry")]

        try:
            output_layout = resolve_output_layout(self.output_folder)
            recovered_dir = output_layout["recovered_files"]
            os.makedirs(recovered_dir, exist_ok=True)

            for rec in local_files:
                try:
                    src = rec.get("path")
                    if not src or not os.path.isfile(src):
                        results["failed"] += 1
                        continue
                    dst = os.path.join(recovered_dir, os.path.basename(src))
                    shutil.copy2(src, dst)
                    results["copied"] += 1
                except Exception:
                    results["failed"] += 1

            for rec in image_entries:
                entry = rec.get("entry")
                if not entry:
                    continue

                source_path = None
                metadata = getattr(entry, "metadata", {}) or {}
                if isinstance(metadata, dict):
                    source_path = metadata.get("path") or metadata.get("source_path")
                if (source_path and os.path.isfile(source_path)
                    and entry.status == FileStatus.EXISTING):
                    target_path = os.path.join(recovered_dir, os.path.basename(source_path))
                    shutil.copy2(source_path, target_path)
                    results["copied"] += 1
                    continue

                if self.scan_result:
                    disk_path = self.scan_result.device.path
                    try:
                        from core.services.privilege_manager import ensure_admin_for_source
                        ensure_admin_for_source(disk_path, reason="Administrator privileges are required to read raw disk media for recovery.")
                        disk_reader = create_disk_reader(disk_path, force_image=not os.path.isdir(disk_path))
                        disk_reader.open()
                    except (PermissionError, AccessDeniedError) as exc:
                        results["failed"] += 1
                        self.requires_elevation.emit(disk_path, str(exc))
                        self.status.emit(f"Administrator privileges required: {exc}")
                        continue
                    except Exception as exc:
                        results["failed"] += 1
                        self.status.emit(f"Unable to open evidence source for image recovery: {exc}")
                        continue
                    else:
                        try:
                            orchestrator = RecoveryOrchestrator()
                            recover_result = orchestrator.recover_files(disk_reader, [entry], Path(recovered_dir))
                            results["recovered"] += recover_result.get("success", 0)
                            results["failed"] += recover_result.get("failed", 0)
                        finally:
                            try:
                                disk_reader.close()
                            except Exception:
                                pass
                else:
                    results["failed"] += 1

            self.completed.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


class StatCard(QFrame):
    def __init__(self, title: str, value: str = "0", color: str = "#ffffff", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("class", "Card")
        self.setFixedHeight(110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("StatTitle")
        layout.addWidget(title_label)

        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("StatValue")
        self.value_label.setStyleSheet(f"font-size: 24px; font-weight: 700; color: {color};")
        layout.addWidget(self.value_label)
        layout.addStretch(1)

    def set_value(self, value: str):
        self.value_label.setText(str(value))


class DashboardPage(QWidget):
    scan_requested = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._settings = {}
        self._last_logged_progress = -1
        self._last_status_message = None
        self.stats_label = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QLabel("ever_recover | Scan Overview")
        header.setObjectName("SectionTitle")
        layout.addWidget(header)

        # Top stats grid
        stats_grid = QGridLayout()
        stats_grid.setSpacing(12)

        self.total_card = StatCard("Files Found", color="#4db3ff")
        self.recoverable_card = StatCard("Recoverable", color="#7ed321")
        self.high_card = StatCard("High Confidence", color="#70e000")
        self.medium_card = StatCard("Medium Confidence", color="#f5a623")
        self.low_card = StatCard("Low Confidence", color="#ff6f61")
        self.carved_card = StatCard("Carved Files", color="#a26cff")

        stats_grid.addWidget(self.total_card, 0, 0)
        stats_grid.addWidget(self.recoverable_card, 0, 1)
        stats_grid.addWidget(self.high_card, 0, 2)
        stats_grid.addWidget(self.medium_card, 0, 3)
        stats_grid.addWidget(self.low_card, 0, 4)
        stats_grid.addWidget(self.carved_card, 0, 5)

        layout.addLayout(stats_grid)

        # Main scan area: left (progress), center (scan details), right (device + recovery stats)
        main_row = QHBoxLayout()
        main_row.setSpacing(12)

        # Scan progress card
        self.scan_card = QFrame()
        self.scan_card.setObjectName("ScanProgressCard")
        self.scan_card.setProperty("class", "Card")
        scan_layout = QVBoxLayout(self.scan_card)
        scan_layout.setContentsMargins(12, 12, 12, 12)

        self.progress_circle = QLabel("0%")
        self.progress_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_circle.setStyleSheet("font-size:36px;font-weight:700;padding:24px;")
        scan_layout.addWidget(self.progress_circle, alignment=Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        scan_layout.addWidget(self.progress_bar)

        self.start_button = QPushButton("Start Scan")
        self.start_button.setProperty("variant", "primary")
        self.start_button.setFixedHeight(40)
        self.start_button.clicked.connect(self._on_start_scan)
        scan_layout.addWidget(self.start_button, alignment=Qt.AlignmentFlag.AlignLeft)

        main_row.addWidget(self.scan_card, 2)

        # Scan detail card
        self.detail_card = QFrame()
        self.detail_card.setObjectName("ScanDetailsCard")
        self.detail_card.setProperty("class", "Card")
        detail_layout = QGridLayout(self.detail_card)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_layout.setHorizontalSpacing(14)
        detail_layout.setVerticalSpacing(8)

        detail_layout.addWidget(QLabel("Scan Type:"), 0, 0)
        self.detail_scan_type = QLabel("-")
        detail_layout.addWidget(self.detail_scan_type, 0, 1)

        detail_layout.addWidget(QLabel("Device:"), 1, 0)
        self.detail_device = QLabel("-")
        detail_layout.addWidget(self.detail_device, 1, 1)

        detail_layout.addWidget(QLabel("File System:"), 2, 0)
        self.detail_fs = QLabel("-")
        detail_layout.addWidget(self.detail_fs, 2, 1)

        detail_layout.addWidget(QLabel("Start Time:"), 3, 0)
        self.detail_start = QLabel("-")
        detail_layout.addWidget(self.detail_start, 3, 1)

        detail_layout.addWidget(QLabel("Elapsed Time:"), 4, 0)
        self.detail_elapsed = QLabel("-")
        detail_layout.addWidget(self.detail_elapsed, 4, 1)

        detail_layout.addWidget(QLabel("Estimated Time:"), 5, 0)
        self.detail_est = QLabel("-")
        detail_layout.addWidget(self.detail_est, 5, 1)

        # Right column: device info + scan result panel
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        self.device_card = QFrame()
        self.device_card.setObjectName("DeviceInfoCard")
        self.device_card.setProperty("class", "Card")
        device_layout = QGridLayout(self.device_card)
        device_layout.setContentsMargins(12, 12, 12, 12)

        device_layout.addWidget(QLabel("Device"), 0, 0)
        self.dev_device = QLabel("-")
        device_layout.addWidget(self.dev_device, 0, 1)

        device_layout.addWidget(QLabel("Serial"), 1, 0)
        self.dev_serial = QLabel("-")
        device_layout.addWidget(self.dev_serial, 1, 1)

        device_layout.addWidget(QLabel("Capacity"), 2, 0)
        self.dev_capacity = QLabel("-")
        device_layout.addWidget(self.dev_capacity, 2, 1)

        device_layout.addWidget(QLabel("Interface"), 3, 0)
        self.dev_interface = QLabel("-")
        device_layout.addWidget(self.dev_interface, 3, 1)

        device_layout.addWidget(QLabel("Health"), 4, 0)
        self.dev_health = QLabel("Healthy")
        self.dev_health.setObjectName("StatusChip")
        device_layout.addWidget(self.dev_health, 4, 1)

        right_col.addWidget(self.device_card)

        self.result_card = QFrame()
        self.result_card.setObjectName("ScanResultsCard")
        self.result_card.setProperty("class", "Card")
        result_layout = QVBoxLayout(self.result_card)
        result_layout.setContentsMargins(12, 12, 12, 12)

        result_title = QLabel("Scan Results")
        result_title.setObjectName("SectionTitle")
        result_layout.addWidget(result_title)

        self.stats_label = QLabel()
        self.stats_label.setTextFormat(Qt.TextFormat.RichText)
        self.stats_label.setWordWrap(True)
        self.stats_label.setText(
            "<span style='color:#4db3ff;'>Files found: 0</span><br>"
            "<span style='#7ed321;'>Recoverable: 0</span><br>"
            "<span style='color:#70e000;'>High confidence: 0</span><br>"
            "<span style='color:#f5a623;'>Medium confidence: 0</span><br>"
            "<span style='color:#ff6f61;'>Low confidence: 0</span><br>"
            "<span style='color:#a26cff;'>Carved files: 0</span>"
        )
        result_layout.addWidget(self.stats_label)

        right_col.addWidget(self.result_card)
        right_col.addStretch(1)

        main_row.addLayout(right_col, 2)

        layout.addLayout(main_row)

        # Log view
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(180)
        layout.addWidget(self.log_view)

    def _on_start_scan(self):
        self.scan_requested.emit(self._settings)

    def update_progress(self, percent: int):
        try:
            self.progress_bar.setValue(percent)
            self.progress_circle.setText(f"{percent}%")
        except Exception:
            pass

        if percent == 100 or percent - self._last_logged_progress >= 10:
            self._append_log(f"Progress: {percent}%")
            self._last_logged_progress = percent

    def set_status(self, message: str):
        if message != self._last_status_message:
            self._append_log(message)
            self._last_status_message = message
        # reflect in details
        self.detail_scan_type.setText(self._settings.get('scan_type', '-') if hasattr(self, '_settings') else '-')
        self.detail_fs.setText(self._settings.get('filesystem', '-'))

    def update_stats(self, total: int, recoverable: int, deleted: int, elapsed: int,
                     high: int = 0, medium: int = 0, low: int = 0, carved: int = 0):
        self.total_card.set_value(str(total))
        self.recoverable_card.set_value(str(recoverable))
        self.high_card.set_value(str(high))
        self.medium_card.set_value(str(medium))
        self.low_card.set_value(str(low))
        self.carved_card.set_value(str(carved))
        self.detail_elapsed.setText(f"{elapsed}s")
        stats_html = (
            "<span style='color:#4db3ff;'>Files found: {}</span><br>"
            "<span style='color:#7ed321;'>Recoverable: {}</span><br>"
            "<span style='color:#70e000;'>High confidence: {}</span><br>"
            "<span style='color:#f5a623;'>Medium confidence: {}</span><br>"
            "<span style='color:#ff6f61;'>Low confidence: {}</span><br>"
            "<span style='color:#a26cff;'>Carved files: {}</span>"
        ).format(total, recoverable, high, medium, low, carved)
        if self.stats_label is not None:
            self.stats_label.setText(stats_html)
        if hasattr(self, 'right_files_found'):
            self.right_files_found.setText(f"<span style='color:#4db3ff;'>Files found: {total}</span>")
            self.right_recoverable.setText(f"<span style='color:#7ed321;'>Recoverable: {recoverable}</span>")
            self.right_high_confidence.setText(f"<span style='color:#70e000;'>High confidence: {high}</span>")
            self.right_medium_confidence.setText(f"<span style='color:#f5a623;'>Medium confidence: {medium}</span>")
            self.right_low_confidence.setText(f"<span style='color:#ff6f61;'>Low confidence: {low}</span>")
            self.right_carved.setText(f"<span style='color:#a26cff;'>Carved files: {carved}</span>")
        self._append_log("Scan results loaded into Files and Report pages.")

    def set_settings(self, settings: dict):
        self._settings = settings.copy()
        source = settings.get("source_path", "Not set")
        self._append_log(f"Configured source: {source}")
        # update detail view and device info
        self.detail_scan_type.setText(settings.get('scan_type', '-'))
        self.detail_fs.setText(settings.get('filesystem', '-'))
        self.detail_device.setText(settings.get('source_path', '-'))

    def _append_log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.log_view.append(f"[{timestamp}] {message}")


class SettingsPage(QWidget):
    settings_changed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(18, 18, 18, 18)

        header = QLabel("Application Settings")
        header.setObjectName("SectionTitle")
        layout.addWidget(header)

        form_layout = QGridLayout()
        form_layout.setHorizontalSpacing(14)
        form_layout.setVerticalSpacing(12)

        form_layout.addWidget(QLabel("Source Path:"), 0, 0)
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText(
            "Folder, disk image file, or a detected device (use 'Detect Devices')"
        )
        form_layout.addWidget(self.source_input, 0, 1)
        source_button = QPushButton("Browse")
        source_button.clicked.connect(self._choose_source)
        form_layout.addWidget(source_button, 0, 2)
        devices_button = QPushButton("Detect Devices")
        devices_button.clicked.connect(self._choose_device)
        form_layout.addWidget(devices_button, 0, 3)

        form_layout.addWidget(QLabel("Output Folder:"), 1, 0)
        self.output_input = QLineEdit()
        form_layout.addWidget(self.output_input, 1, 1)
        output_button = QPushButton("Browse")
        output_button.clicked.connect(self._choose_output)
        form_layout.addWidget(output_button, 1, 2)

        form_layout.addWidget(QLabel("Filesystem:"), 2, 0)
        self.filesystem_input = QComboBox()
        self.filesystem_input.addItems([
            "Auto Detect",
            "NTFS",
            "FAT32",
            "exFAT",
            "EXT4",
            "EXT3/EXT2",
            "APFS",
            "HFS+",
        ])
        form_layout.addWidget(self.filesystem_input, 2, 1, 1, 2)

        form_layout.addWidget(QLabel("Scan Mode:"), 3, 0)
        self.scan_mode_input = QComboBox()
        self.scan_mode_input.addItems(["Quick Scan", "Full Scan", "Timeline Scan"])
        form_layout.addWidget(self.scan_mode_input, 3, 1, 1, 2)

        self.timeline_checkbox = QCheckBox("Enable timeline scanning")
        form_layout.addWidget(self.timeline_checkbox, 4, 0, 1, 3)

        form_layout.addWidget(QLabel("Scan Type:"), 5, 0)
        scan_type_container = QWidget()
        scan_type_layout = QHBoxLayout(scan_type_container)
        scan_type_layout.setSpacing(12)
        scan_type_layout.setContentsMargins(0, 0, 0, 0)
        self.scan_type_group = QButtonGroup(self)
        for label in ["File System Only", "File Carving Only", "Hybrid"]:
            radio = QRadioButton(label)
            self.scan_type_group.addButton(radio)
            scan_type_layout.addWidget(radio)
        self.scan_type_group.buttons()[2].setChecked(True)
        form_layout.addWidget(scan_type_container, 5, 1, 1, 2)

        form_layout.addWidget(QLabel("Scan Profile:"), 6, 0)
        self.profile_input = QComboBox()
        self.profile_input.addItems([
            "Forensic Analysis",
            "Deleted File Recovery",
            "Rapid Restore",
            "Deep Carving",
        ])
        form_layout.addWidget(self.profile_input, 6, 1, 1, 2)

        layout.addLayout(form_layout)

        self.apply_button = QPushButton("Apply Settings")
        self.apply_button.setProperty("variant", "primary")
        self.apply_button.clicked.connect(self._on_apply_settings)
        self.apply_button.setFixedHeight(40)
        layout.addWidget(self.apply_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

    def _choose_device(self):
        """Detect real storage devices (physical drives, volumes) and let
        the user pick one as the scan source, showing the information the
        recovery tool needs to distinguish them safely: device path,
        physical-disk-vs-volume, capacity, removable/fixed status, and
        filesystem where determinable.
        """
        devices, error = self._detect_devices()

        if error:
            QMessageBox.warning(
                self, "Device Detection",
                f"Could not enumerate storage devices: {error}\n\n"
                "You can still type a device path manually (e.g. "
                "\\\\.\\PhysicalDrive1 on Windows) or use Browse for a "
                "folder/image file."
            )
            return

        if not devices:
            QMessageBox.information(
                self, "Device Detection",
                "No additional physical drives or volumes were detected "
                "(besides the system drive, which is intentionally "
                "excluded to reduce the risk of accidentally scanning it "
                "as if it were removable media)."
            )
            return

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Select Storage Device")
        dialog.setText("Detected storage devices:")
        dialog.setIcon(QMessageBox.Icon.NoIcon)

        # Present as a simple numbered list with a text-entry fallback,
        # since QMessageBox has no native list widget; this keeps the
        # change minimal rather than introducing a new dialog class.
        lines = []
        for i, dev in enumerate(devices, 1):
            lines.append(
                f"{i}. {dev['label']}  [{dev['kind']}]  "
                f"{dev['display_size']}  "
                f"{'Removable' if dev['is_removable'] else 'Fixed'}  "
                f"path={dev['path']}"
            )
        dialog.setInformativeText(
            "\n".join(lines) + "\n\nType the number of the device to use, then click OK."
        )
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        from PyQt6.QtWidgets import QInputDialog
        choice, ok = QInputDialog.getInt(
            self, "Select Storage Device",
            "Detected devices:\n\n" + "\n".join(lines) + "\n\nEnter device number:",
            1, 1, len(devices), 1,
        )
        if not ok:
            return

        selected = devices[choice - 1]
        self.source_input.setText(selected['path'])
        if selected['is_removable']:
            QMessageBox.information(
                self, "Removable Device Selected",
                f"Selected {selected['label']} ({selected['display_size']}, removable).\n\n"
                "Raw device access to a physical drive typically requires "
                "Administrator privileges on Windows; you will be prompted "
                "to elevate automatically if needed when the scan starts."
            )

    @staticmethod
    def _detect_devices() -> tuple:
        """Enumerate real storage devices for the picker.

        Returns (devices, error_message). devices is a list of dicts with
        path/label/kind/display_size/is_removable/file_system, distinguishing
        physical disks from logical volumes as required for safe, correct
        device selection.
        """
        import platform

        try:
            if platform.system() == 'Windows':
                from infrastructure.disk.windows_disk_reader import WindowsDiskReader
                from infrastructure.disk.factory import create_disk_reader

                devices = []
                for path in WindowsDiskReader.enumerate_physical_drives():
                    try:
                        with create_disk_reader(path) as reader:
                            geometry = reader.get_geometry()
                            size = geometry.total_size
                    except Exception:
                        size = 0
                    removable = WindowsDiskReader.get_device_removable_status(path)
                    devices.append({
                        'path': path,
                        'label': f"Physical Disk {path.split(chr(92))[-1]}",
                        'kind': 'Physical Drive',
                        'display_size': WindowsDiskReader._format_bytes(size) if size else "Unknown size",
                        'is_removable': bool(removable),  # None (query failed) is treated as not-removable for display purposes only; the elevation prompt still applies uniformly regardless
                        'file_system': 'Unknown',
                    })

                for drive_letter in WindowsDiskReader.enumerate_logical_drives():
                    path = f"\\\\.\\{drive_letter}"
                    try:
                        with create_disk_reader(path) as reader:
                            size = reader.total_size
                    except Exception:
                        size = 0
                    removable = WindowsDiskReader.get_logical_drive_type(drive_letter)
                    devices.append({
                        'path': path,
                        'label': f"Volume {drive_letter}",
                        'kind': 'Logical Volume',
                        'display_size': WindowsDiskReader._format_bytes(size) if size else "Unknown size",
                        'is_removable': bool(removable),
                        'file_system': 'Unknown',
                    })
                return devices, None

            else:
                # Linux/macOS: enumerate block devices via /sys/block, which
                # requires no extra privileges to list (only to open for
                # raw reading, which is handled at scan time).
                devices = []
                sys_block = "/sys/block"
                if os.path.isdir(sys_block):
                    for name in sorted(os.listdir(sys_block)):
                        if name.startswith(('loop', 'ram', 'zram')):
                            continue
                        removable_path = os.path.join(sys_block, name, "removable")
                        size_path = os.path.join(sys_block, name, "size")
                        is_removable = False
                        size_bytes = 0
                        try:
                            with open(removable_path) as f:
                                is_removable = f.read().strip() == "1"
                        except Exception:
                            pass
                        try:
                            with open(size_path) as f:
                                size_bytes = int(f.read().strip()) * 512  # size is in 512-byte sectors
                        except Exception:
                            pass
                        devices.append({
                            'path': f"/dev/{name}",
                            'label': name,
                            'kind': 'Block Device',
                            'display_size': f"{size_bytes / (1024**3):.2f} GB" if size_bytes else "Unknown size",
                            'is_removable': is_removable,
                            'file_system': 'Unknown',
                        })
                return devices, None

        except Exception as e:
            return [], str(e)

    def _choose_source(self):
        selected = QFileDialog.getExistingDirectory(self, "Select source device or folder")
        if selected:
            self.source_input.setText(selected)
            return

        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select evidence image",
            os.path.expanduser("~"),
            "Disk Images (*.img *.raw *.dd *.bin *.e01 *.aff *.vmdk *.vdi *.vhd *.vhdx *.qcow2);;All Files (*)"
        )
        if selected_file:
            self.source_input.setText(selected_file)

    def _choose_output(self):
        selected = QFileDialog.getExistingDirectory(self, "Select output folder")
        if selected:
            self.output_input.setText(selected)

    def _on_apply_settings(self):
        settings = self.get_settings()
        self.settings_changed.emit(settings)
        QMessageBox.information(self, "Settings Saved", "Scanning settings have been updated.")

    def get_settings(self) -> dict:
        scan_type = next(
            (btn.text() for btn in self.scan_type_group.buttons() if btn.isChecked()),
            "Hybrid",
        )
        return {
            "source_path": self.source_input.text().strip() or os.path.expanduser("~"),
            "output_folder": self.output_input.text().strip() or os.path.join(os.path.expanduser("~"), "Desktop", "ever_recover"),
            "filesystem": self.filesystem_input.currentText(),
            "scan_mode": self.scan_mode_input.currentText(),
            "timeline_scan": self.timeline_checkbox.isChecked(),
            "scan_type": scan_type,
            "scan_profile": self.profile_input.currentText(),
        }

    def set_settings(self, settings: dict):
        self.source_input.setText(settings.get("source_path", ""))
        self.output_input.setText(settings.get("output_folder", ""))
        self.filesystem_input.setCurrentText(settings.get("filesystem", "NTFS"))
        self.scan_mode_input.setCurrentText(settings.get("scan_mode", "Quick Scan"))
        self.timeline_checkbox.setChecked(bool(settings.get("timeline_scan", False)))
        self.profile_input.setCurrentText(settings.get("scan_profile", "Forensic Analysis"))
        scan_type = settings.get("scan_type", "Hybrid")
        for button in self.scan_type_group.buttons():
            button.setChecked(button.text() == scan_type)


class FilesPage(QWidget):
    file_selected = pyqtSignal(dict)
    recover_requested = pyqtSignal(list)
    recover_all_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._files = []
        self._filtered_files = []
        self._max_display_rows = 200
        self._search_timer = None
        self._last_status_message = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(18, 18, 18, 18)

        header = QLabel("Recovered Files")
        header.setObjectName("SectionTitle")
        layout.addWidget(header)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search recovered files…")
        self.search_input.textChanged.connect(self._queue_refresh_table)
        filter_layout.addWidget(self.search_input)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All Statuses", "Existing", "Deleted"])
        self.status_filter.currentTextChanged.connect(self._queue_refresh_table)
        filter_layout.addWidget(self.status_filter)

        layout.addLayout(filter_layout)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Status", "Path"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        self.table_note = QLabel("")
        self.table_note.setStyleSheet("color: #9eb0c6; font-size: 11px;")
        layout.addWidget(self.table_note)

        # Recovery actions
        actions_layout = QHBoxLayout()
        self.recover_selected_button = QPushButton("Recover Selected")
        self.recover_selected_button.setFixedHeight(36)
        self.recover_selected_button.clicked.connect(self._on_recover_selected)
        actions_layout.addWidget(self.recover_selected_button)

        self.recover_all_button = QPushButton("Recover All")
        self.recover_all_button.setFixedHeight(36)
        self.recover_all_button.clicked.connect(self._on_recover_all)
        actions_layout.addWidget(self.recover_all_button)

        layout.addLayout(actions_layout)

        layout.addStretch(1)

    def load_files(self, files: list):
        self._files = files.copy()
        self._filtered_files = self._files.copy()
        self.table.setUpdatesEnabled(False)
        self.table.clearContents()
        self._refresh_table()
        self.table.setUpdatesEnabled(True)

    def _queue_refresh_table(self):
        if self._search_timer is None:
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(self._refresh_table)
        self._search_timer.start(250)

    def _refresh_table(self):
        query = self.search_input.text().strip().lower()
        status_filter = self.status_filter.currentText()
        filtered = []

        for file_record in self._files:
            if status_filter != "All Statuses" and file_record["status"] != status_filter:
                continue
            if query and query not in file_record["name"].lower() and query not in file_record["path"].lower():
                continue
            filtered.append(file_record)

        self._filtered_files = filtered
        display_count = min(len(filtered), self._max_display_rows)
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(display_count)

        for row, file_record in enumerate(filtered[:display_count]):
            row_items = [
                QTableWidgetItem(file_record["name"]),
                QTableWidgetItem(file_record["type"]),
                QTableWidgetItem(f'{file_record["size"]:,} bytes'),
                QTableWidgetItem(file_record["status"]),
                QTableWidgetItem(file_record["path"]),
            ]
            for col, item in enumerate(row_items):
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)

        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)

        if len(filtered) > display_count:
            self.table_note.setText(f"Showing {display_count} of {len(filtered)} files. Narrow search to view more.")
        else:
            self.table_note.setText(f"{len(filtered)} files displayed.")

    def _on_selection_changed(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if row < 0 or row >= len(self._filtered_files):
            return
        current_file = self._filtered_files[row]
        self.file_selected.emit(current_file)

    def _on_recover_selected(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        files = []
        for sel in selected_rows:
            row = sel.row()
            if 0 <= row < len(self._filtered_files):
                files.append(self._filtered_files[row])
        if files:
            self.recover_requested.emit(files)

    def _on_recover_all(self):
        self.recover_all_requested.emit()


class PreviewPage(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(18, 18, 18, 18)

        header = QLabel("Preview & Metadata")
        header.setObjectName("SectionTitle")
        layout.addWidget(header)

        self.metadata_area = QTextEdit()
        self.metadata_area.setReadOnly(True)
        self.metadata_area.setFixedHeight(210)
        layout.addWidget(self.metadata_area)

        self.preview_area = QTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setPlaceholderText("Select a recovered file in the Files page to view metadata and preview content.")
        layout.addWidget(self.preview_area)
        layout.addStretch(1)

    def show_file(self, file_record: dict):
        entry = file_record.get("entry")
        metadata = (
            f"Name: {file_record['name']}\n"
            f"Type: {file_record['type']}\n"
            f"Size: {file_record['size']:,} bytes\n"
            f"Status: {file_record['status']}\n"
            f"Category: {file_record.get('category', 'Unknown')}\n"
            f"Confidence: {file_record.get('confidence', getattr(entry, 'recovery_confidence', None).name if entry else 'Unknown')}\n"
            f"Path: {file_record['path']}\n"
        )
        self.metadata_area.setPlainText(metadata)
        preview_text = file_record.get("preview", "No preview available.")
        if preview_text == "Preview available on selection.":
            preview_text = build_file_preview(file_record.get("path", ""))
        self.preview_area.setPlainText(preview_text)

    def clear(self):
        self.metadata_area.clear()
        self.preview_area.clear()


class ReportPage(QWidget):
    request_generate = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._scan_summary = None
        self._scan_files = []
        self._output_path = ""
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(18, 18, 18, 18)

        header = QLabel("Report Center")
        header.setObjectName("SectionTitle")
        layout.addWidget(header)

        self.summary_label = QLabel("No scan data available. Run a scan to prepare reports.")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        self.pdf_button = QPushButton("Export PDF")
        self.html_button = QPushButton("Export HTML")
        self.csv_button = QPushButton("Export CSV")
        self.json_button = QPushButton("Export JSON")

        self.pdf_button.clicked.connect(lambda: self.request_generate.emit("pdf"))
        self.html_button.clicked.connect(lambda: self.request_generate.emit("html"))
        self.csv_button.clicked.connect(lambda: self.request_generate.emit("csv"))
        self.json_button.clicked.connect(lambda: self.request_generate.emit("json"))

        for button in [self.pdf_button, self.html_button, self.csv_button, self.json_button]:
            button.setFixedHeight(38)
            button_layout.addWidget(button)

        layout.addLayout(button_layout)

        self.output_label = QLabel("Output folder: unset")
        layout.addWidget(self.output_label)

        self.report_log = QTextEdit()
        self.report_log.setReadOnly(True)
        self.report_log.setFixedHeight(180)
        layout.addWidget(self.report_log)
        layout.addStretch(1)

    def set_scan_data(self, summary: dict, files: list):
        self._scan_summary = summary
        self._scan_files = files.copy()
        if not summary:
            self.summary_label.setText("No scan summary available.")
            return

        self.summary_label.setText(
            f"{summary['total_files']} recovered files, "
            f"{summary['recoverable_files']} recoverable, "
            f"{summary['deleted_files']} deleted. "
            f"Scan profile: {summary['scan_profile']}, filesystem: {summary['filesystem']}.")

    def set_output_folder(self, path: str):
        self._output_path = path or os.path.join(os.path.expanduser("~"), "Desktop", "ever_recover")
        self.output_label.setText(f"Output folder: {self._output_path}")

    def log(self, text: str):
        self.report_log.append(text)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ever_recover")
        self.setMinimumSize(1200, 780)

        self._scan_controller = RecoveryScanner()
        self._scan_result = None
        self._worker_threads: List[QThread] = []
        self._dashboard_page = DashboardPage()
        self._settings_page = SettingsPage()
        self._files_page = FilesPage()
        self._preview_page = PreviewPage()
        self._report_page = ReportPage()

        self._page_index = {
            "Dashboard": 0,
            "Files": 1,
            "Preview": 2,
            "Report": 3,
            "Settings": 4,
        }

        self._build_ui()
        self._connect_signals()
        self._apply_default_settings()
        self._load_stylesheet()
        self.showMaximized()

    def _build_ui(self):
        root = QWidget()
        root_v = QVBoxLayout(root)
        root_v.setSpacing(12)
        root_v.setContentsMargins(12, 12, 12, 12)

        # Top header
        header_frame = QFrame()
        header_frame.setObjectName("TopHeaderPanel")
        header_frame.setProperty("class", "Panel")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(16)

        brand_box = QFrame()
        brand_layout = QVBoxLayout(brand_box)
        brand_label = QLabel("ER")
        brand_label.setObjectName("BrandAccent")
        brand_label.setStyleSheet("font-size:28px; font-weight:800; background:#1f6feb; color:#fff; padding: 10px 18px; border-radius:10px;")
        title_label = QLabel("EVER RECOVER")
        title_label.setObjectName("BrandTitle")
        subtitle = QLabel("Professional Digital Forensics & Deleted File Recovery")
        subtitle.setObjectName("BrandSubtitle")
        brand_layout.addWidget(brand_label, alignment=Qt.AlignmentFlag.AlignLeft)
        brand_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignLeft)
        brand_layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(brand_box, 2)

        # Top badges (features)
        badges_frame = QFrame()
        badges_layout = QHBoxLayout(badges_frame)
        badges_layout.setContentsMargins(0, 0, 0, 0)
        badges_layout.setSpacing(10)
        for text in ["Multi-Filesystem", "File Carving", "AI Analysis", "Forensic Imaging", "Detailed Reports"]:
            b = QFrame()
            b.setProperty("class", "Badge")
            bl = QVBoxLayout(b)
            lab = QLabel(text)
            lab.setProperty("role", "badgeTitle")
            bl.addWidget(lab, alignment=Qt.AlignmentFlag.AlignCenter)
            badges_layout.addWidget(b)

        header_layout.addWidget(badges_frame, 3)

        root_v.addWidget(header_frame)

        # Main area
        root_layout = QHBoxLayout()
        root_layout.setSpacing(16)
        root_layout.setContentsMargins(0, 0, 0, 0)

        nav_panel = QFrame()
        nav_panel.setObjectName("LeftNavPanel")
        nav_panel.setProperty("class", "Panel")
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(16, 16, 16, 16)
        nav_layout.setSpacing(18)

        brand_label = QLabel("ever_recover")
        brand_label.setObjectName("BrandTitle")
        nav_layout.addWidget(brand_label)

        sub_title = QLabel("Digital Forensics Dashboard")
        sub_title.setObjectName("BrandSubtitle")
        nav_layout.addWidget(sub_title)

        self._nav_buttons = {}
        for label in ["Dashboard", "Files", "Preview", "Report", "Settings"]:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setFixedHeight(44)
            button.clicked.connect(lambda checked, page=label: self.select_page(page))
            nav_layout.addWidget(button)
            self._nav_buttons[label] = button

        nav_layout.addStretch(1)
        nav_panel.setFixedWidth(260)
        root_layout.addWidget(nav_panel)

        center_frame = QFrame()
        center_frame.setObjectName("CenterWorkspace")
        center_frame.setProperty("class", "Panel")
        center_layout = QVBoxLayout(center_frame)
        center_layout.setContentsMargins(8, 8, 8, 8)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._dashboard_page)
        self._pages.addWidget(self._files_page)
        self._pages.addWidget(self._preview_page)
        self._pages.addWidget(self._report_page)
        self._pages.addWidget(self._settings_page)

        center_layout.addWidget(self._pages)
        root_layout.addWidget(center_frame, 1)

        # Right insights panel

        root_v.addLayout(root_layout)

        self.setCentralWidget(root)
        self.select_page("Dashboard")

    def _connect_signals(self):
        self._dashboard_page.scan_requested.connect(self.start_scan)
        self._settings_page.settings_changed.connect(self._on_settings_changed)
        self._scan_controller.scan_progress.connect(self._dashboard_page.update_progress)
        self._scan_controller.scan_status.connect(self._dashboard_page.set_status)
        self._scan_controller.scan_completed.connect(self._on_scan_completed)
        self._scan_controller.scan_failed.connect(self._on_scan_failed)
        self._scan_controller.scan_requires_elevation.connect(self._on_requires_elevation)
        self._files_page.file_selected.connect(self._preview_page.show_file)
        self._files_page.file_selected.connect(lambda _: self.select_page("Preview"))
        self._files_page.recover_requested.connect(self._recover_files)
        self._files_page.recover_all_requested.connect(lambda: self._recover_files(self._files_page._files))
        self._report_page.request_generate.connect(self._create_report)

    def select_page(self, page_name: str):
        if page_name not in self._page_index:
            return
        self._pages.setCurrentIndex(self._page_index[page_name])
        for name, button in self._nav_buttons.items():
            button.setChecked(name == page_name)

    def _apply_default_settings(self):
        default_settings = {
            "source_path": os.path.join(os.path.expanduser("~"), "Desktop"),
            "output_folder": os.path.join(os.path.expanduser("~"), "Desktop", "ever_recover"),
            "filesystem": "Auto Detect",
            "scan_mode": "Quick Scan",
            "timeline_scan": False,
            "scan_type": "Hybrid",
            "scan_profile": "Forensic Analysis",
        }
        resolve_output_layout(default_settings["output_folder"])
        self._settings_page.set_settings(default_settings)
        self._on_settings_changed(default_settings)

    def _on_settings_changed(self, settings: dict):
        self._dashboard_page.set_settings(settings)
        output_folder = settings.get("output_folder", "")
        resolve_output_layout(output_folder)
        self._report_page.set_output_folder(output_folder)

    def start_scan(self, settings: dict):
        self._scan_controller.start_scan(settings)
        self.select_page("Dashboard")

    def _on_scan_completed(self, scan_result, files: list, summary: dict):
        self._scan_result = scan_result
        levels = [str(r.get("confidence", "")).upper() for r in files]
        carved = sum(1 for r in files if getattr(r.get("entry"), "is_carved", False))
        self._dashboard_page.update_stats(
            total=summary["total_files"],
            recoverable=summary["recoverable_files"],
            deleted=summary["deleted_files"],
            elapsed=summary["duration"],
            high=sum(1 for c in levels if c in ("EXCELLENT", "HIGH")),
            medium=sum(1 for c in levels if c == "MEDIUM"),
            low=sum(1 for c in levels if c in ("LOW", "POOR")),
            carved=carved,
        )
        self._files_page.load_files(files)
        self._report_page.set_scan_data(summary, files)
        self._report_page.log("Scan completed successfully.")

    def _on_scan_failed(self, error: str):
        self._dashboard_page.set_status(f"Scan failed: {error}")
        QMessageBox.critical(self, "Scan Failed", error)

    def _on_requires_elevation(self, source_path: str, reason: str):
        """Handle a raw-disk access failure caused by missing admin rights.

        This device/volume requires Windows administrator privileges to
        open for raw access. Offer to relaunch the application elevated via
        the standard UAC prompt rather than leaving the user with a dead
        end. Only offered on Windows, since raw device access on other
        platforms uses different (non-UAC) privilege models.
        """
        self._dashboard_page.set_status("Administrator privileges required.")

        if not is_windows():
            QMessageBox.critical(
                self, "Administrator Privileges Required",
                f"{reason}\n\nRaw device access requires elevated privileges "
                "on this platform. Please restart the application with "
                "elevated/root permissions (e.g. `sudo`) and try again."
            )
            return

        if is_elevated():
            # Already elevated but access still failed - this is a genuine
            # access problem (locked device, in-use volume, etc.), not a
            # privilege gap. Don't offer to "elevate" again.
            QMessageBox.critical(
                self, "Access Denied",
                f"{reason}\n\nThe application is already running as "
                "Administrator, but access to this device was still denied. "
                "The device may be locked, in use by another process, or "
                "unavailable."
            )
            return

        choice = QMessageBox.question(
            self, "Administrator Privileges Required",
            f"{reason}\n\n"
            f"Reading raw disk/volume data from '{source_path}' requires "
            "Windows administrator privileges.\n\n"
            "Restart ever_recover as Administrator now? Your current "
            "settings will need to be re-entered after the restart.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if choice != QMessageBox.StandardButton.Yes:
            return

        if request_elevation():
            # A new elevated process has been launched via UAC. Exit this
            # unprivileged instance so only one process holds the device.
            QApplication.quit()
        else:
            QMessageBox.warning(
                self, "Elevation Cancelled",
                "The elevation request was cancelled or failed. The "
                "application will continue running without administrator "
                "privileges, and raw disk/volume sources will remain "
                "inaccessible."
            )

    def _create_report(self, file_format: str):
        if not self._report_page._scan_files or not self._scan_result:
            QMessageBox.warning(self, "No Data", "Run a scan first to generate a report.")
            return

        output_dir = self._report_page._output_path
        output_layout = resolve_output_layout(output_dir)
        reports_dir = output_layout["reports"]
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ever_recover_report_{timestamp}.{file_format}"
        path = os.path.join(reports_dir, filename)

        metadata = ReportMetadata(
            case_number=f"UI-{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            examiner_name="Ever Recover User",
            organization="Ever Recover",
            notes=f"Scan profile: {self._report_page._scan_summary.get('scan_profile', 'N/A')}"
        )

        self._report_page.log(f"Starting {file_format.upper()} report generation...")

        worker = ReportWorker(self._scan_result, metadata, file_format, path)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(lambda output_path: self._on_report_finished(output_path, thread, worker))
        worker.error.connect(lambda err: self._on_report_error(err, thread, worker))
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._worker_threads.remove(thread) if thread in self._worker_threads else None)

        self._worker_threads.append(thread)
        thread.start()

    def _on_report_finished(self, path: str, thread: QThread, worker: QObject):
        self._report_page.log(f"Report created: {path}")
        QMessageBox.information(self, "Report Generated", f"Report written to:\n{path}")

    def _on_report_error(self, error: str, thread: QThread, worker: QObject):
        self._report_page.log(f"Report generation failed: {error}")
        QMessageBox.critical(self, "Report Error", f"Unable to write report: {error}")

    def _recover_files(self, files: List[dict]):
        if not files:
            QMessageBox.information(self, "No Files", "No files selected for recovery.")
            return

        settings = self._settings_page.get_settings()
        output = settings.get('output_folder') or os.path.join(os.path.expanduser('~'), 'Desktop', 'ever_recover')

        self._dashboard_page.set_status("Starting recovery operation...")
        self._report_page.log(f"Recovery started for {len(files)} file(s) into {output}.")

        worker = RecoveryWorker(files, output, self._scan_result)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.completed.connect(lambda result: self._on_recovery_completed(result, thread, worker))
        worker.error.connect(lambda err: self._on_recovery_error(err, thread, worker))
        worker.requires_elevation.connect(self._on_requires_elevation)
        worker.completed.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        worker.completed.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(lambda: self._worker_threads.remove(thread) if thread in self._worker_threads else None)

        self._worker_threads.append(thread)
        thread.start()

    def _on_recovery_completed(self, results: dict, thread: QThread, worker: QObject):
        self._dashboard_page.set_status("Recovery completed successfully.")
        self._report_page.log(f"Recovery completed: copied={results['copied']}, recovered={results['recovered']}, failed={results['failed']}")
        QMessageBox.information(self, "Recovery Completed", f"Results: copied={results['copied']}, recovered={results['recovered']}, failed={results['failed']}")
        self.select_page("Report")

    def _on_recovery_error(self, error: str, thread: QThread, worker: QObject):
        self._dashboard_page.set_status("Recovery failed.")
        self._report_page.log(f"Recovery failed: {error}")
        QMessageBox.critical(self, "Recovery Error", f"Failed to recover files: {error}")

    def _write_text_report(self, path: str, headline: str):
        lines = [headline, "ever_recover forensic report", "", "Scan Summary"]
        lines += [f"{key}: {value}" for key, value in self._report_page._scan_summary.items()]
        lines.append("")
        lines.append("Recovered files:")
        for file_record in self._report_page._scan_files:
            lines.append(f"- {file_record['name']} ({file_record['status']}) - {file_record['path']}")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

    def _write_html_report(self, path: str):
        html_parts = [
            "<html><head><meta charset='utf-8'><title>ever_recover Report</title></head><body>",
            "<h1>ever_recover Report</h1>",
            "<h2>Scan Summary</h2>",
            "<ul>",
        ]
        for key, value in self._report_page._scan_summary.items():
            html_parts.append(f"<li><strong>{key}</strong>: {value}</li>")
        html_parts.append("</ul>")
        html_parts.append("<h2>Recovered Files</h2>")
        html_parts.append("<table border='1' cellpadding='6'><tr><th>Name</th><th>Status</th><th>Type</th><th>Path</th></tr>")
        for file_record in self._report_page._scan_files:
            html_parts.append(
                "<tr>"
                f"<td>{file_record['name']}</td>"
                f"<td>{file_record['status']}</td>"
                f"<td>{file_record['type']}</td>"
                f"<td>{file_record['path']}</td>"
                "</tr>"
            )
        html_parts.append("</table></body></html>")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(html_parts))

    def _write_csv_report(self, path: str):
        import csv
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Name", "Type", "Size", "Status", "Path"])
            for file_record in self._report_page._scan_files:
                writer.writerow([
                    file_record["name"],
                    file_record["type"],
                    file_record["size"],
                    file_record["status"],
                    file_record["path"],
                ])

    def _write_json_report(self, path: str):
        import json
        payload = {
            "summary": self._report_page._scan_summary,
            "files": self._report_page._scan_files,
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _load_stylesheet(self):
        qss_path = Path(__file__).parent / "dashboard.qss"
        if qss_path.exists():
            with qss_path.open("r", encoding="utf-8") as handle:
                self.setStyleSheet(handle.read())


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ever_recover")
    app.setOrganizationName("ever_recover")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
