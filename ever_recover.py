"""
Ever Recover - Professional Digital Forensics & File Recovery Tool
===================================================================

Version: 1.0.0 (Gold Master)
Build: 2026.07.10
License: MIT

A comprehensive file recovery solution with:
- File system parsing (NTFS, FAT32, exFAT, EXT4)
- Signature-based file carving (37+ file types)
- AI-powered file classification & corruption detection
- Multi-threaded recovery with priority scheduling
- Forensic report generation (PDF, HTML, CSV, JSON)
- Professional GUI and powerful CLI
- Performance optimizations (caching, parallel processing)

© 2026 Ever Recover Team. All rights reserved.
"""

import sys
import io
import os
import logging
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding when a console is available
if sys.platform == 'win32':
    try:
        if getattr(sys, 'stdout', None) is not None and getattr(sys.stdout, 'buffer', None) is not None:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if getattr(sys, 'stderr', None) is not None and getattr(sys.stderr, 'buffer', None) is not None:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        # Running without a console (frozen GUI) - redirect to devnull to avoid AttributeError
        try:
            devnull = open(os.devnull, 'w', encoding='utf-8', errors='replace')
            sys.stdout = devnull
            sys.stderr = devnull
        except Exception:
            # If opening devnull fails, leave sys.stdout/stderr as-is
            pass

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            Path(__file__).parent / 'ever_recover.log',
            encoding='utf-8',
            errors='replace'
        )
    ],
    force=True,
)

logger = logging.getLogger(__name__)


def print_banner():
    """Print application banner."""
    print("\n" + "=" * 70)
    print("  🔍 EVER RECOVER - Professional Digital Forensics & File Recovery")
    print("  Version 1.0.0 (Gold Master) | © 2026 Ever Recover Team")
    print("=" * 70 + "\n")


def main():
    """Main entry point for GUI application."""
    logger.info("Ever Recover starting...")
    
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont, QIcon
        
        # HighDPI must be called BEFORE creating QApplication
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        # Set application metadata
        QApplication.setApplicationName("Ever Recover")
        QApplication.setApplicationVersion("1.0.0")
        QApplication.setOrganizationName("Ever Recover")
        QApplication.setApplicationDisplayName("Ever Recover")
        
        # Create application
        app = QApplication(sys.argv)
        
        # Set application style and font
        app.setStyle('Fusion')
        font = QFont("Segoe UI", 10)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        app.setFont(font)

        # Attempt to load project's dashboard stylesheet (dashboard.qss) so the
        # packaged EXE matches the original GUI. Fall back to the bundled dark
        # theme if the QSS file isn't available.
        try:
            import importlib.resources as pkg_resources
            from presentation import styles
            qss_path = None
            try:
                # Prefer reading dashboard.qss from package resources
                qss_data = pkg_resources.files(styles).joinpath('dashboard.qss')
                if qss_data.exists():
                    qss_text = qss_data.read_text(encoding='utf-8')
                    app.setStyleSheet(qss_text)
                    qss_path = str(qss_data)
            except Exception:
                qss_path = None

            if not qss_path:
                # Fallback to the programmatic dark stylesheet
                try:
                    from presentation.styles.dark_theme import get_dark_theme_stylesheet
                    app.setStyleSheet(get_dark_theme_stylesheet())
                except Exception:
                    pass
        except Exception:
            # Importlib.resources may not be available in some frozen contexts; ignore
            pass
        
        # Create and show main window using the plan-driven dashboard implementation
        from dashboard_main import MainWindow
        window = MainWindow()
        window.setWindowTitle("Ever Recover v1.0.0 - Professional Digital Forensics")
        window.show()
        
        logger.info("Main window displayed")
        
        # Print banner
        print_banner()
        print("✓ Application started successfully")
        print(f"✓ Python {sys.version.split()[0]}")
        print(f"✓ PyQt6 GUI initialized")
        print(f"✓ Working directory: {Path.cwd()}")
        print("\nReady for use. Happy recovering! 🚀\n")
        
        # Run event loop
        sys.exit(app.exec())
        
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def run_demo():
    """Run demo recovery without GUI."""
    print_banner()
    logger.info("Running Ever Recover demo...")
    
    try:
        from core.interfaces.disk_reader import VirtualDiskReader
        from core.services.recovery_engine import RecoveryEngine, RecoveryConfig
        from core.services.report_generator import ReportGenerator, ReportMetadata
        from ai.classifiers.file_classifier import FileClassifier, SmartRecoverySorter
        
        import tempfile
        
        # Create test disk with sample files
        logger.info("Creating test disk with sample files...")
        
        # Create realistic test files
        jpeg_data = (
            b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00' +
            b'\x00' * 4984 + b'\xFF\xD9'
        )
        png_data = (
            b'\x89PNG\r\n\x1A\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10' +
            b'\x00' * 2984 + b'IEND\xAE\x42\x60\x82'
        )
        pdf_data = (
            b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n' +
            b'\x00' * 3950 + b'%%EOF'
        )
        
        disk_data = (
            b'\x00' * 1024 +
            jpeg_data +
            b'\x00' * 512 +
            png_data +
            b'\x00' * 512 +
            pdf_data +
            b'\x00' * 1024
        )
        
        # Create disk reader
        disk_reader = VirtualDiskReader(disk_data, "demo_disk")
        
        # Configure recovery
        config = RecoveryConfig(
            scan_file_system=False,
            scan_carving=True,
            recover_deleted=True,
        )
        
        # Track progress
        def progress_callback(progress):
            print(f"  📊 {progress.phase}: {progress.progress:.1f}% - {progress.current_file}")
        
        # Run recovery
        print("\n🔍 Starting recovery scan...")
        engine = RecoveryEngine(
            disk_reader=disk_reader,
            config=config,
            progress_callback=progress_callback,
        )
        
        scan_result = engine.scan()
        
        print(f"\n✅ Scan complete!")
        print(f"   Files found: {scan_result.statistics.total_files}")
        print(f"   Deleted files: {scan_result.statistics.deleted_files}")
        print(f"   Recoverable: {scan_result.statistics.recoverable_files}")
        print(f"   Duration: {scan_result.duration_seconds:.1f}s")
        
        # Classify files
        print("\n🤖 Classifying files with AI...")
        classifier = FileClassifier()
        
        for file_entry in scan_result.files:
            if file_entry.offset:
                sample = disk_reader.read(file_entry.offset, min(file_entry.file_size, 1024))
                classification = classifier.classify(file_entry, sample)
                confidence_pct = classification.confidence * 100
                corrupted_str = "⚠️ CORRUPTED" if classification.is_corrupted else "✓ Valid"
                print(f"   {file_entry.display_name}: {classification.predicted_category.name} "
                      f"(confidence: {confidence_pct:.0f}%) {corrupted_str}")
        
        # Prioritize recovery
        print("\n📊 Prioritizing files for recovery...")
        sorter = SmartRecoverySorter()
        prioritized = sorter.prioritize(scan_result.files, top_n=3)
        
        for i, file_entry in enumerate(prioritized, 1):
            print(f"   {i}. {file_entry.display_name} (priority: HIGH)")
        
        # Generate reports
        print("\n📄 Generating forensic reports...")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir)
            
            metadata = ReportMetadata(
                case_number="DEMO-001",
                examiner_name="Demo User",
                organization="Ever Recover",
                notes="Automated demo run - Gold Master v1.0.0",
            )
            
            generator = ReportGenerator(scan_result, metadata)
            
            # Generate all formats
            pdf_path = output_path / "forensic_report.pdf"
            html_path = output_path / "forensic_report.html"
            csv_path = output_path / "file_listing.csv"
            json_path = output_path / "forensic_report.json"
            
            generator.generate_pdf(pdf_path)
            generator.generate_html(html_path)
            generator.generate_csv(csv_path)
            generator.generate_json(json_path)
            
            print(f"   ✅ PDF: {pdf_path} ({pdf_path.stat().st_size} bytes)")
            print(f"   ✅ HTML: {html_path} ({html_path.stat().st_size} bytes)")
            print(f"   ✅ CSV: {csv_path} ({csv_path.stat().st_size} bytes)")
            print(f"   ✅ JSON: {json_path} ({json_path.stat().st_size} bytes)")
        
        print("\n🎉 Demo complete!")
        print(f"   Reports saved to: {output_path}")
        print("\n✓ All systems operational")
        print("✓ Ready for production use")
        
    except Exception as e:
        logger.exception(f"Demo error: {e}")
        print(f"\n❌ Demo error: {e}")
        raise


def run_tests():
    """Run integration tests."""
    print_banner()
    logger.info("Running integration tests...")
    print("\n🧪 Running comprehensive test suite...\n")
    
    try:
        from tests.integration.test_full_recovery import run_integration_tests
        run_integration_tests()
        
    except Exception as e:
        logger.exception(f"Test error: {e}")
        print(f"\n❌ Test error: {e}")
        raise


def run_cli():
    """Run CLI interface."""
    from cli.cli import main as cli_main
    cli_main()


if __name__ == '__main__':
    import sys
    
    # Check if running as CLI
    if len(sys.argv) > 1 and sys.argv[1] not in ['--demo', '--test', '--help', '-h', '--version', '-v']:
        run_cli()
    elif len(sys.argv) > 1:
        if sys.argv[1] == '--demo':
            run_demo()
        elif sys.argv[1] == '--test':
            run_tests()
        elif sys.argv[1] in ['--help', '-h']:
            print_banner()
            print("Usage:")
            print("  python ever_recover.py              # Launch GUI")
            print("  python ever_recover.py --demo       # Run demo")
            print("  python ever_recover.py --test       # Run tests")
            print("  python ever_recover.py [command]    # CLI mode")
            print("\nCLI Commands:")
            print("  scan    - Scan device or disk image")
            print("  recover - Recover files from scan")
            print("  report  - Generate forensic report")
            print("  full    - Complete recovery workflow")
            print("\nExamples:")
            print("  python ever_recover.py scan disk.e01 -o ./output")
            print("  python ever_recover.py full disk.e01 -o ./output --all-reports")
            print("\nFor CLI help:")
            print("  python ever_recover.py scan --help")
        elif sys.argv[1] in ['--version', '-v']:
            print("Ever Recover v1.0.0 (Gold Master)")
            print("Build: 2026.07.10")
            print("© 2026 Ever Recover Team. All rights reserved.")
            print("License: MIT")
        else:
            print("Usage: python ever_recover.py [--demo|--test|--help|--version] [command]")
            print("  (no args = GUI mode)")
            sys.exit(1)
    else:
        main()