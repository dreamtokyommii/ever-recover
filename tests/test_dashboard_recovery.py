import os
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication

from dashboard_main import PreviewPage, RecoveryWorker, resolve_output_layout
from core.models.file_entry import FileEntry, FileStatus, RecoveryConfidence, FileCategory
from core.services.recovery_engine import RecoveryOrchestrator


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_preview_page_shows_entry_metadata(tmp_path):
    app = QApplication.instance() or QApplication([])

    file_path = tmp_path / "sample.txt"
    file_path.write_text("recovered content", encoding="utf-8")

    entry = FileEntry(
        file_id="entry-1",
        filename="sample.txt",
        extension="txt",
        file_size=file_path.stat().st_size,
        file_category=FileCategory.DOCUMENT,
        recovery_confidence=RecoveryConfidence.HIGH,
        status=FileStatus.DELETED,
        metadata={"path": str(file_path)},
    )

    page = PreviewPage()
    page.show_file(
        {
            "name": entry.filename,
            "type": "TXT",
            "size": entry.file_size,
            "status": entry.status.name.title(),
            "category": entry.file_category.name.title(),
            "path": str(file_path),
            "entry": entry,
            "preview": "Preview available on selection.",
        }
    )

    metadata_text = page.metadata_area.toPlainText()
    assert "Confidence: HIGH" in metadata_text
    assert "Deleted" in metadata_text


def test_output_layout_creates_recovered_and_reports_folders(tmp_path):
    base_output = tmp_path / "output"

    layout = resolve_output_layout(str(base_output))

    assert layout["base"] == str(base_output)
    assert layout["recovered_files"] == str(base_output / "recovered_files")
    assert layout["reports"] == str(base_output / "reports")
    assert os.path.isdir(layout["recovered_files"])
    assert os.path.isdir(layout["reports"])


def test_recovery_worker_handles_unavailable_image_reader(tmp_path):
    app = QApplication.instance() or QApplication([])

    local_path = tmp_path / "local.txt"
    local_path.write_text("local", encoding="utf-8")

    image_entry = FileEntry(
        file_id="entry-2",
        filename="image.bin",
        extension="bin",
        file_size=16,
        file_category=FileCategory.OTHER,
        recovery_confidence=RecoveryConfidence.LOW,
        status=FileStatus.DELETED,
        offset=0,
        metadata={"path": "image.bin"},
    )

    scan_result = SimpleNamespace(device=SimpleNamespace(path="\\\\.\\BadDevice"))
    output_dir = tmp_path / "recovered"

    results = {}

    def handle_completed(payload):
        results["payload"] = payload

    worker = RecoveryWorker(
        [
            {"name": local_path.name, "path": str(local_path), "entry": None},
            {"name": image_entry.filename, "path": "", "entry": image_entry},
        ],
        str(output_dir),
        scan_result,
    )
    worker.completed.connect(handle_completed)
    worker.run()

    assert results["payload"]["copied"] == 1
    assert results["payload"]["failed"] >= 1
    assert output_dir.joinpath("recovered_files", local_path.name).exists()


def test_recovery_orchestrator_recovers_files_from_offset_zero(tmp_path):
    class StubDiskReader:
        device_path = "stub-image"
        total_size = 1024

        def read(self, offset, size):
            assert offset == 0
            assert size == 4
            return b"data"

        def close(self):
            return None

    output_dir = tmp_path / "recovered"
    file_entry = FileEntry(
        file_id="entry-3",
        filename="start.bin",
        extension="bin",
        file_size=4,
        file_category=FileCategory.OTHER,
        recovery_confidence=RecoveryConfidence.HIGH,
        status=FileStatus.DELETED,
        offset=0,
    )

    orchestrator = RecoveryOrchestrator()
    result = orchestrator.recover_files(StubDiskReader(), [file_entry], output_dir)

    assert result["success"] == 1
    assert output_dir.joinpath("start.bin").exists()


def test_recovery_orchestrator_recovers_fragmented_file(tmp_path):
    class StubDiskReader:
        device_path = "stub-image"
        total_size = 1024

        def read(self, offset, size):
            if offset == 0 and size == 4:
                return b"part"
            if offset == 4 and size == 4:
                return b"ial."
            raise ValueError(f"Invalid read {offset}:{size}")

        def close(self):
            return None

    output_dir = tmp_path / "recovered"
    file_entry = FileEntry(
        file_id="entry-5",
        filename="fragmented.txt",
        extension="txt",
        file_size=8,
        file_category=FileCategory.DOCUMENT,
        recovery_confidence=RecoveryConfidence.HIGH,
        status=FileStatus.DELETED,
        offset=None,
        fragments=[(0, 4), (4, 4)],
    )

    orchestrator = RecoveryOrchestrator()
    result = orchestrator.recover_files(StubDiskReader(), [file_entry], output_dir)

    assert result["success"] == 1
    recovered_path = output_dir / "fragmented.txt"
    assert recovered_path.exists()
    assert recovered_path.read_bytes() == b"partial."


def test_recovery_worker_falls_back_to_copying_existing_source_paths(tmp_path):
    app = QApplication.instance() or QApplication([])

    source_file = tmp_path / "fallback.txt"
    source_file.write_text("fallback", encoding="utf-8")

    entry = FileEntry(
        file_id="entry-4",
        filename="fallback.txt",
        extension="txt",
        file_size=source_file.stat().st_size,
        file_category=FileCategory.DOCUMENT,
        recovery_confidence=RecoveryConfidence.HIGH,
        status=FileStatus.DELETED,
        offset=None,
        metadata={"path": str(source_file)},
    )

    output_dir = tmp_path / "recovered"
    worker = RecoveryWorker(
        [{"name": entry.filename, "path": "", "entry": entry}],
        str(output_dir),
        SimpleNamespace(device=SimpleNamespace(path="\\\\.\\BadDevice")),
    )

    results = {}
    worker.completed.connect(lambda payload: results.setdefault("payload", payload))
    worker.run()

    assert results["payload"]["copied"] == 1
    assert output_dir.joinpath("recovered_files", "fallback.txt").exists()
