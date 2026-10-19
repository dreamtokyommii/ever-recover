"""Command Line Interface for Ever Recover."""

import argparse
import sys
import json
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from core.interfaces.disk_reader import VirtualDiskReader, DiskImageReader
from infrastructure.disk.factory import create_disk_reader
from core.services.recovery_engine import RecoveryEngine, RecoveryConfig
from core.services.carving_engine import CarvingEngine
from core.services.report_generator import ReportGenerator, ReportMetadata
from core.models.file_entry import FileCategory, FileEntry, RecoveryConfidence
from ai.classifiers.file_classifier import FileClassifier, SmartRecoverySorter

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("Note: Install 'tqdm' for progress bars: pip install tqdm")

logger = logging.getLogger(__name__)


class CLIRecovery:
    """CLI-based recovery controller."""
    
    def __init__(
        self,
        device_path: str,
        output_dir: Path,
        config: Optional[RecoveryConfig] = None,
        verbose: bool = False,
        dry_run: bool = False,
    ):
        self.device_path = device_path
        self.output_dir = output_dir
        self.config = config or RecoveryConfig()
        self.verbose = verbose
        self.dry_run = dry_run
        
        self._disk_reader = None
        self._scan_result = None
        
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            stream=sys.stdout,
        )
    
    def scan(self) -> dict:
        """Perform scan."""
        print(f"\n🔍 Scanning: {self.device_path}")
        print("=" * 60)
        
        self._disk_reader = self._create_disk_reader()
        
        engine = RecoveryEngine(
            disk_reader=self._disk_reader,
            config=self.config,
            progress_callback=self._progress_callback if HAS_TQDM else self._simple_progress,
        )
        
        if HAS_TQDM:
            with tqdm(total=100, desc="Scanning", unit="%") as pbar:
                self._scan_result = engine.scan()
                pbar.update(100)
        else:
            self._scan_result = engine.scan()
        
        self._display_scan_results()
        
        return self._scan_result.to_dict() if hasattr(self._scan_result, 'to_dict') else {
            'status': self._scan_result.status,
            'total_files': self._scan_result.statistics.total_files,
            'deleted_files': self._scan_result.statistics.deleted_files,
            'recoverable_files': self._scan_result.statistics.recoverable_files,
        }
    
    def recover(self, files: Optional[List] = None) -> dict:
        """Recover files."""
        if not self._scan_result:
            raise RuntimeError("Must scan before recovering")
        
        if self.dry_run:
            print("\n🚫 Dry run - skipping recovery")
            return {'recovered': 0, 'skipped': len(self._scan_result.files)}
        
        print(f"\n💾 Recovering files to: {self.output_dir}")
        print("=" * 60)
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        files_to_recover = files or self._scan_result.files
        total = len(files_to_recover)
        
        recovered = 0
        failed = 0
        skipped = 0
        
        iterator = enumerate(files_to_recover)
        if HAS_TQDM:
            iterator = tqdm(iterator, total=total, desc="Recovering", unit="file")
        
        for i, file_entry in iterator:
            try:
                if file_entry.offset is None and not file_entry.fragments:
                    skipped += 1
                    continue
                
                data = self._read_file_entry_data(file_entry)
                
                if len(data) != file_entry.file_size:
                    failed += 1
                    if self.verbose:
                        print(f"  ⚠️  Size mismatch: {file_entry.display_name}")
                    continue
                
                output_path = self.output_dir / file_entry.display_name
                with open(output_path, 'wb') as f:
                    f.write(data)
                
                recovered += 1
                
                if self.verbose:
                    print(f"  ✅ {file_entry.display_name} ({self._format_size(file_entry.file_size)})")
                
            except Exception as e:
                failed += 1
                if self.verbose:
                    print(f"  ❌ {file_entry.display_name}: {e}")
        
        print(f"\n✅ Recovery complete!")
        print(f"   Recovered: {recovered}")
        print(f"   Failed: {failed}")
        print(f"   Skipped: {skipped}")
        
        return {
            'recovered': recovered,
            'failed': failed,
            'skipped': skipped,
            'output_dir': str(self.output_dir),
        }
    
    def generate_report(
        self,
        format: str = 'all',
        case_number: str = 'CLI-001',
        examiner: str = 'Unknown',
    ) -> dict:
        """Generate forensic report."""
        if not self._scan_result:
            raise RuntimeError("Must scan before generating report")
        
        print(f"\n📄 Generating {format} report...")
        print("=" * 60)
        
        metadata = ReportMetadata(
            case_number=case_number,
            examiner_name=examiner,
            organization="Ever Recover CLI",
        )
        
        generator = ReportGenerator(self._scan_result, metadata)
        
        reports = {}
        
        if format in ['pdf', 'all']:
            pdf_path = self.output_dir / "forensic_report.pdf"
            generator.generate_pdf(pdf_path)
            reports['pdf'] = str(pdf_path)
            print(f"  ✅ PDF: {pdf_path}")
        
        if format in ['html', 'all']:
            html_path = self.output_dir / "forensic_report.html"
            generator.generate_html(html_path)
            reports['html'] = str(html_path)
            print(f"  ✅ HTML: {html_path}")
        
        if format in ['csv', 'all']:
            csv_path = self.output_dir / "file_listing.csv"
            generator.generate_csv(csv_path)
            reports['csv'] = str(csv_path)
            print(f"  ✅ CSV: {csv_path}")
        
        if format in ['json', 'all']:
            json_path = self.output_dir / "forensic_report.json"
            generator.generate_json(json_path)
            reports['json'] = str(json_path)
            print(f"  ✅ JSON: {json_path}")
        
        return reports
    
    def _create_disk_reader(self):
        """Create appropriate disk reader."""
        path = Path(self.device_path)
        
        try:
            if path.exists() and path.is_file():
                print(f"📀 Opening disk image: {path}")
                return create_disk_reader(str(path), force_image=True)
            
            print(f"🔌 Opening device: {self.device_path}")
            return create_disk_reader(self.device_path)
        except Exception as exc:
            print(f"⚠️  Unable to open device/image directly: {exc}")
            print("⚠️  Falling back to virtual disk reader for testing only")
            test_data = b'\x00' * (10 * 1024 * 1024)
            return VirtualDiskReader(test_data, str(path))
    
    def _progress_callback(self, progress):
        """Progress callback with tqdm."""
        pass
    
    def _read_file_entry_data(self, file_entry: FileEntry) -> bytes:
        if file_entry.fragments:
            chunks = []
            for fragment_offset, fragment_size in file_entry.fragments:
                chunks.append(self._disk_reader.read(fragment_offset, fragment_size))
            return b"".join(chunks)
        
        return self._disk_reader.read(file_entry.offset, file_entry.file_size)
    
    def _simple_progress(self, progress):
        """Simple progress indicator."""
        print(f"  Progress: {progress.phase} - {progress.progress:.1f}%")
    
    def _display_scan_results(self):
        """Display scan results."""
        stats = self._scan_result.statistics
        
        print(f"\n✅ Scan Results:")
        print(f"   Status: {self._scan_result.status}")
        print(f"   Duration: {self._scan_result.duration_seconds:.1f}s")
        print(f"   Total files: {stats.total_files}")
        print(f"   Deleted files: {stats.deleted_files}")
        print(f"   Recoverable: {stats.recoverable_files}")
        print(f"   Total size: {self._format_size(stats.total_size)}")
        print(f"   Fragmented: {stats.fragmented_files}")
        
        if stats.files_by_category:
            print(f"\n   Top categories:")
            sorted_cats = sorted(stats.files_by_category.items(), key=lambda x: x[1], reverse=True)
            for cat, count in sorted_cats[:5]:
                print(f"      {cat}: {count}")
        
        if stats.files_by_confidence:
            print(f"\n   Confidence:")
            for conf, count in sorted(stats.files_by_confidence.items()):
                print(f"      {conf}: {count}")
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format size."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog='ever-recover',
        description='🔍 Ever Recover - Professional Digital Forensics & File Recovery Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument('--version', action='version', version='Ever Recover 1.0.0')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--dry-run', action='store_true', help='Scan only, don\'t recover')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    scan_parser = subparsers.add_parser('scan', help='Scan device or image')
    scan_parser.add_argument('device', help='Device path or disk image')
    scan_parser.add_argument('-o', '--output', type=Path, required=True, help='Output directory')
    scan_parser.add_argument('--categories', type=str, help='File categories (comma-separated)')
    scan_parser.add_argument('--min-confidence', type=str, default='LOW', 
                            choices=['LOW', 'MEDIUM', 'HIGH', 'EXCELLENT'],
                            help='Minimum confidence level')
    scan_parser.add_argument('--no-carving', action='store_true', help='Disable file carving')
    scan_parser.add_argument('--max-size', type=int, help='Maximum file size (MB)')
    
    recover_parser = subparsers.add_parser('recover', help='Recover files')
    recover_parser.add_argument('device', help='Device path or disk image')
    recover_parser.add_argument('-o', '--output', type=Path, required=True, help='Output directory')
    recover_parser.add_argument('--files', nargs='+', help='Specific files to recover')
    recover_parser.add_argument('--all', action='store_true', help='Recover all files')
    
    report_parser = subparsers.add_parser('report', help='Generate forensic report')
    report_parser.add_argument('device', help='Device path or disk image')
    report_parser.add_argument('-o', '--output', type=Path, required=True, help='Output directory')
    report_parser.add_argument('--format', type=str, default='all',
                              choices=['pdf', 'html', 'csv', 'json', 'all'],
                              help='Report format')
    report_parser.add_argument('--case', type=str, default='CLI-001', help='Case number')
    report_parser.add_argument('--examiner', type=str, default='Unknown', help='Examiner name')
    
    full_parser = subparsers.add_parser('full', help='Full recovery workflow')
    full_parser.add_argument('device', help='Device path or disk image')
    full_parser.add_argument('-o', '--output', type=Path, required=True, help='Output directory')
    full_parser.add_argument('--all-reports', action='store_true', help='Generate all report formats')
    full_parser.add_argument('--categories', type=str, help='File categories')
    
    return parser


def main():
    """CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    categories = None
    if hasattr(args, 'categories') and args.categories:
        try:
            categories = {FileCategory[c.strip().upper()] for c in args.categories.split(',')}
        except KeyError as e:
            print(f"❌ Invalid category: {e}")
            sys.exit(1)
    
    config = RecoveryConfig(
        scan_file_system=not hasattr(args, 'no_carving') or not args.no_carving,
        scan_carving=not hasattr(args, 'no_carving') or not args.no_carving,
        recover_deleted=True,
        min_confidence=getattr(RecoveryConfidence, getattr(args, 'min_confidence', 'LOW'), RecoveryConfidence.LOW),
        categories=categories,
        max_file_size=(getattr(args, 'max_size', 0) or 0) * 1024 * 1024,
    )
    
    try:
        if args.command == 'scan':
            recovery = CLIRecovery(
                device_path=args.device,
                output_dir=args.output,
                config=config,
                verbose=args.verbose,
                dry_run=args.dry_run,
            )
            result = recovery.scan()
            
            if args.json:
                print(json.dumps(result, indent=2, default=str))
        
        elif args.command == 'recover':
            recovery = CLIRecovery(
                device_path=args.device,
                output_dir=args.output,
                config=config,
                verbose=args.verbose,
            )
            recovery.scan()
            result = recovery.recover()
            
            if args.json:
                print(json.dumps(result, indent=2, default=str))
        
        elif args.command == 'report':
            recovery = CLIRecovery(
                device_path=args.device,
                output_dir=args.output,
                config=config,
                verbose=args.verbose,
            )
            recovery.scan()
            result = recovery.generate_report(
                format=args.format,
                case_number=args.case,
                examiner=args.examiner,
            )
            
            if args.json:
                print(json.dumps(result, indent=2, default=str))
        
        elif args.command == 'full':
            print("🚀 Starting full recovery workflow...")
            
            recovery = CLIRecovery(
                device_path=args.device,
                output_dir=args.output,
                config=config,
                verbose=args.verbose,
            )
            
            recovery.scan()
            recovery.recover()
            
            if args.all_reports:
                recovery.generate_report(format='all', case_number=args.case if hasattr(args, 'case') else 'FULL-001')
            else:
                recovery.generate_report(format='json')
            
            print("\n🎉 Full workflow complete!")
        
        else:
            parser.print_help()
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()