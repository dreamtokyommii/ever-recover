"""Integration tests for full recovery workflow."""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime
import struct

from core.interfaces.disk_reader import DiskReader, VirtualDiskReader
from core.interfaces.filesystem_parser import FileSystemParser
from core.models.file_entry import FileEntry, FileStatus, RecoveryConfidence, FileCategory
from core.models.scan_result import ScanResult, ScanStatistics
from core.models.device import DeviceInfo, DeviceType, FileSystemType
from core.services.carving_engine import CarvingEngine
from core.services.recovery_engine import RecoveryEngine, RecoveryConfig
from core.services.report_generator import ReportGenerator, ReportMetadata
from ai.classifiers.file_classifier import FileClassifier, SmartRecoverySorter


class TestCarvingEngineIntegration:
    """Test carving engine with real data."""
    
    def test_carve_jpeg_file(self, tmp_path):
        """Test carving a JPEG file from raw data."""
        jpeg_data = (
            b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01' +
            b'\x00\x00\x01\x00\x01\x00\x00' +
            b'\xFF\xDB\x00C\x00' + b'\x08' * 64 +
            # COM (comment) marker segment used purely to pad this
            # synthetic JPEG above the signature database's own
            # configured min_size=1024 for JPEG (a real 144-byte JPEG is
            # smaller than the app's own minimum recoverable-file
            # threshold and would correctly be rejected as too small to
            # confidently distinguish from a false-positive header match).
            b'\xFF\xFE\x03\x70' + b'\x00' * 878 +
            b'\xFF\xC0\x00\x0B\x08\x00\x01\x00\x01\x01\x01\x11\x00' +
            b'\xFF\xC4\x00\x1F\x00\x00\x01\x05\x01\x01\x01\x01\x01' +
            b'\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08' +
            b'\xFF\xDA\x00\x08\x01\x01\x00\x00?\x00\x7F\xFF\xD9'
        )
        
        disk_data = (
            b'\x00' * 1024 +
            jpeg_data +
            b'\x00' * 1024
        )
        
        disk_reader = VirtualDiskReader(disk_data, "test_disk")
        disk_reader.open()
        engine = CarvingEngine(disk_reader, min_file_size=100)
        
        carved_files = engine.carve()
        
        assert len(carved_files) >= 1, "Should find at least one file"
        
        jpeg_carved = None
        for carved in carved_files:
            if carved.signature.extension == 'jpg':
                jpeg_carved = carved
                break
        
        assert jpeg_carved is not None, "Should carve JPEG file"
        assert jpeg_carved.confidence.value >= RecoveryConfidence.MEDIUM.value
    
    def test_carve_multiple_files(self, tmp_path):
        """Test carving multiple file types."""
        # Padded above the signature database's configured min_size=1024
        # for JPEG/PNG (see test_carve_jpeg_file for full justification).
        jpeg_data = b'\xFF\xD8\xFF\xE0' + b'\x00' * 1050 + b'\xFF\xD9'
        png_data = b'\x89PNG\r\n\x1A\n' + b'\x00' * 1050 + b'IEND\xAE\x42\x60\x82'
        pdf_data = b'%PDF-1.4' + b'\x00' * 1050 + b'%%EOF'
        
        disk_data = (
            b'\x00' * 512 +
            jpeg_data +
            b'\x00' * 512 +
            png_data +
            b'\x00' * 512 +
            pdf_data +
            b'\x00' * 512
        )
        
        disk_reader = VirtualDiskReader(disk_data, "test_disk")
        engine = CarvingEngine(disk_reader, min_file_size=100)
        
        carved_files = engine.carve()
        
        assert len(carved_files) >= 3, f"Should find 3+ files, found {len(carved_files)}"
        
        extensions = [c.signature.extension for c in carved_files]
        assert 'jpg' in extensions, "Should find JPEG"
        assert 'png' in extensions, "Should find PNG"
        assert 'pdf' in extensions, "Should find PDF"


class TestRecoveryEngineIntegration:
    """Test recovery engine end-to-end."""
    
    def test_full_scan_workflow(self, tmp_path):
        """Test complete scan workflow."""
        disk_data = (
            b'\x00' * 1024 +
            b'\xFF\xD8\xFF' + b'\x00' * 2000 + b'\xFF\xD9' +
            b'\x00' * 1024 +
            b'%PDF-1.4' + b'\x00' * 3000 + b'%%EOF' +
            b'\x00' * 1024
        )
        
        disk_reader = VirtualDiskReader(disk_data, "test_disk")
        
        config = RecoveryConfig(
            scan_file_system=False,
            scan_carving=True,
            recover_deleted=True,
            min_confidence=RecoveryConfidence.LOW,
        )
        
        progress_calls = []
        def progress_callback(progress):
            progress_calls.append(progress)
        
        engine = RecoveryEngine(
            disk_reader=disk_reader,
            config=config,
            progress_callback=progress_callback,
        )
        
        result = engine.scan()
        
        assert result.status == "complete", f"Scan should complete, got {result.status}"
        assert len(result.files) >= 2, f"Should find 2+ files, found {len(result.files)}"
        assert result.statistics.total_files >= 2
        assert len(progress_calls) > 0, "Should report progress"
    
    def test_scan_with_filters(self, tmp_path):
        """Test scan with file filters."""
        disk_data = (
            b'\x00' * 512 +
            b'\xFF\xD8\xFF\xE0' + b'\x00' * 1050 + b'\xFF\xD9' +
            b'\x00' * 512 +
            b'\x89PNG\r\n\x1A\n' + b'\x00' * 2000 + b'IEND\xAE\x42\x60\x82' +
            b'\x00' * 512
        )
        
        disk_reader = VirtualDiskReader(disk_data, "test_disk")
        
        config = RecoveryConfig(
            scan_file_system=False,
            scan_carving=True,
            file_extensions={'jpg'},
            min_file_size=500,
        )
        
        engine = RecoveryEngine(disk_reader=disk_reader, config=config)
        result = engine.scan()
        
        assert len(result.files) >= 1
        
        for file_entry in result.files:
            assert file_entry.extension == 'jpg', "Should only return JPEG files"


class TestAIIntegration:
    """Test AI features integration."""
    
    def test_file_classification(self):
        """Test file classification on carved files."""
        classifier = FileClassifier()
        
        jpeg_data = b'\xFF\xD8\xFF\xE0\x00\x10JFIF' + b'\x00' * 100
        jpeg_entry = FileEntry(
            file_id="test_001",
            filename="test.jpg",
            extension="jpg",
            file_size=len(jpeg_data),
            file_category=FileCategory.IMAGE,
            recovery_confidence=RecoveryConfidence.HIGH,
            status=FileStatus.DELETED,
        )
        
        result = classifier.classify(jpeg_entry, jpeg_data)
        
        assert result.predicted_category == FileCategory.IMAGE
        assert result.confidence > 0.8
        assert not result.is_corrupted
    
    def test_corruption_detection(self):
        """Test corruption detection."""
        classifier = FileClassifier()
        
        corrupted_data = b'\x00' * 1024
        corrupted_entry = FileEntry(
            file_id="test_002",
            filename="corrupted.jpg",
            extension="jpg",
            file_size=1024,
            file_category=FileCategory.IMAGE,
            recovery_confidence=RecoveryConfidence.LOW,
            status=FileStatus.DELETED,
        )
        
        result = classifier.classify(corrupted_entry, corrupted_data)
        
        assert result.is_corrupted, "Should detect corruption"
        assert result.corruption_score > 0.3
    
    def test_recovery_prioritization(self):
        """Test smart recovery prioritization."""
        sorter = SmartRecoverySorter()
        
        files = [
            FileEntry(
                file_id=f"file_{i}",
                filename=f"document_{i}.docx",
                extension="docx",
                file_size=100000 * (i + 1),
                file_category=FileCategory.DOCUMENT,
                recovery_confidence=RecoveryConfidence.HIGH if i % 2 == 0 else RecoveryConfidence.LOW,
                status=FileStatus.DELETED,
                modified_time=datetime.now(),
            )
            for i in range(10)
        ]
        
        prioritized = sorter.prioritize(files, top_n=5)
        
        assert len(prioritized) == 5
        assert prioritized[0].recovery_confidence == RecoveryConfidence.HIGH


class TestReportGenerationIntegration:
    """Test report generation integration."""
    
    def test_generate_all_formats(self, tmp_path):
        """Test generating all report formats."""
        files = [
            FileEntry(
                file_id=f"file_{i}",
                filename=f"recovered_file_{i}.jpg",
                extension="jpg",
                file_size=10000 + i * 1000,
                file_category=FileCategory.IMAGE,
                recovery_confidence=RecoveryConfidence.HIGH,
                status=FileStatus.DELETED,
                offset=i * 10000,
            )
            for i in range(10)
        ]
        
        stats = ScanStatistics(
            total_files=len(files),
            deleted_files=len(files),
            recoverable_files=len(files),
            total_size=sum(f.file_size for f in files),
            fragmented_files=2,
            scan_errors=0,
            files_by_category={'IMAGE': len(files)},
            files_by_confidence={'HIGH': len(files)},
        )
        
        scan_result = ScanResult(
            scan_id="test-scan",
            device=DeviceInfo(
                device_id="test_device",
                path="test_device",
                label="test_device",
                device_type=DeviceType.VIRTUAL,
                file_system=FileSystemType.UNKNOWN,
                total_size=1024 * 1024 * 100,
                free_space=0,
                is_removable=False,
            ),
            start_time=datetime.now(),
            files=files,
            statistics=stats,
            status="complete",
        )
        
        metadata = ReportMetadata(
            case_number="TEST-001",
            examiner_name="Test Examiner",
            organization="Test Organization",
            notes="Integration test",
        )
        
        generator = ReportGenerator(scan_result, metadata)
        
        pdf_path = tmp_path / "report.pdf"
        generator.generate_pdf(pdf_path)
        assert pdf_path.exists(), "PDF should be generated"
        assert pdf_path.stat().st_size > 0, "PDF should not be empty"
        
        html_path = tmp_path / "report.html"
        generator.generate_html(html_path)
        assert html_path.exists(), "HTML should be generated"
        assert html_path.stat().st_size > 1000, "HTML should have content"
        
        csv_path = tmp_path / "report.csv"
        generator.generate_csv(csv_path)
        assert csv_path.exists(), "CSV should be generated"
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert 'Ever Recover' in content, "CSV should have header"
            assert 'Filename' in content, "CSV should have column headers"
        
        json_path = tmp_path / "report.json"
        generator.generate_json(json_path)
        assert json_path.exists(), "JSON should be generated"
        
        import json
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert 'metadata' in data, "JSON should have metadata"
            assert 'scan_result' in data, "JSON should have scan result"


class TestEndToEndRecovery:
    """End-to-end recovery test."""
    
    def test_complete_recovery_pipeline(self, tmp_path):
        """Test complete recovery from disk to report."""
        jpeg1 = b'\xFF\xD8\xFF' + b'A' * 5000 + b'\xFF\xD9'
        jpeg2 = b'\xFF\xD8\xFF' + b'B' * 3000 + b'\xFF\xD9'
        png1 = b'\x89PNG\r\n\x1A\n' + b'C' * 4000 + b'IEND\xAE\x42\x60\x82'
        pdf1 = b'%PDF-1.4' + b'D' * 6000 + b'%%EOF'
        
        disk_data = (
            b'\x00' * 1024 +
            jpeg1 +
            b'\x00' * 512 +
            png1 +
            b'\x00' * 512 +
            jpeg2 +
            b'\x00' * 512 +
            pdf1 +
            b'\x00' * 1024
        )
        
        disk_reader = VirtualDiskReader(disk_data, "evidence_disk")
        
        config = RecoveryConfig(
            scan_file_system=False,
            scan_carving=True,
            recover_deleted=True,
        )
        
        engine = RecoveryEngine(disk_reader=disk_reader, config=config)
        scan_result = engine.scan()
        
        assert scan_result.status == "complete"
        assert len(scan_result.files) >= 4, f"Should find 4+ files, found {len(scan_result.files)}"
        
        classifier = FileClassifier()
        for file_entry in scan_result.files:
            if file_entry.offset:
                file_data = disk_reader.read(file_entry.offset, min(file_entry.file_size, 1024))
                classification = classifier.classify(file_entry, file_data)
                assert classification.predicted_category == file_entry.file_category
        
        sorter = SmartRecoverySorter()
        prioritized = sorter.prioritize(scan_result.files, top_n=3)
        assert len(prioritized) == 3, "Should prioritize top 3 files"
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        metadata = ReportMetadata(
            case_number="E2E-TEST-001",
            examiner_name="Automated Test",
            organization="Ever Recover",
        )
        
        generator = ReportGenerator(scan_result, metadata)
        
        generator.generate_pdf(output_dir / "forensic_report.pdf")
        generator.generate_html(output_dir / "forensic_report.html")
        generator.generate_csv(output_dir / "file_listing.csv")
        generator.generate_json(output_dir / "forensic_report.json")
        
        assert (output_dir / "forensic_report.pdf").exists()
        assert (output_dir / "forensic_report.html").exists()
        assert (output_dir / "file_listing.csv").exists()
        assert (output_dir / "forensic_report.json").exists()
        
        recovery_dir = output_dir / "recovered"
        recovery_dir.mkdir()
        
        recovered_count = 0
        for file_entry in scan_result.files[:5]:
            if file_entry.offset:
                data = disk_reader.read(file_entry.offset, file_entry.file_size)
                output_path = recovery_dir / file_entry.display_name
                
                with open(output_path, 'wb') as f:
                    f.write(data)
                
                recovered_count += 1
        
        assert recovered_count >= 4, f"Should recover 4+ files, recovered {recovered_count}"
        
        for file_path in recovery_dir.glob("*.jpg"):
            assert file_path.stat().st_size > 100, "Recovered JPEG should have content"
        
        print(f"✅ End-to-end test passed: {len(scan_result.files)} files found, {recovered_count} recovered")


def run_integration_tests():
    """Run integration tests."""
    import sys
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        test_carving = TestCarvingEngineIntegration()
        test_recovery = TestRecoveryEngineIntegration()
        test_ai = TestAIIntegration()
        test_reports = TestReportGenerationIntegration()
        test_e2e = TestEndToEndRecovery()
        
        print("Running carving tests...")
        test_carving.test_carve_jpeg_file(tmp_path)
        test_carving.test_carve_multiple_files(tmp_path)
        print("✅ Carving tests passed")
        
        print("Running recovery tests...")
        test_recovery.test_full_scan_workflow(tmp_path)
        test_recovery.test_scan_with_filters(tmp_path)
        print("✅ Recovery tests passed")
        
        print("Running AI tests...")
        test_ai.test_file_classification()
        test_ai.test_corruption_detection()
        test_ai.test_recovery_prioritization()
        print("✅ AI tests passed")
        
        print("Running report tests...")
        test_reports.test_generate_all_formats(tmp_path)
        print("✅ Report tests passed")
        
        print("Running end-to-end test...")
        test_e2e.test_complete_recovery_pipeline(tmp_path)
        print("✅ End-to-end test passed")
        
        print("\n🎉 All integration tests passed!")


if __name__ == '__main__':
    run_integration_tests()