"""Recovery engine - orchestrates file system parsing and carving."""

import logging
import threading
import queue
import time
from typing import List, Dict, Optional, Callable, Any, Set
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

from core.interfaces.disk_reader import DiskReader
from core.interfaces.filesystem_parser import FileSystemParser
from core.models.file_entry import FileEntry, FileStatus, RecoveryConfidence, FileCategory
from core.models.scan_result import ScanResult, ScanStatistics
from core.models.device import DeviceInfo
from core.services.carving_engine import CarvingEngine, CarvedFile

logger = logging.getLogger(__name__)


@dataclass
class RecoveryProgress:
    """Recovery progress information."""
    phase: str  # "scanning", "carving", "complete"
    progress: float  # 0-100
    current_file: str
    files_found: int
    bytes_scanned: int
    estimated_time_remaining: Optional[int] = None  # seconds


@dataclass
class RecoveryConfig:
    """Recovery configuration."""
    scan_file_system: bool = True
    scan_carving: bool = True
    recover_deleted: bool = True
    recover_existing: bool = False
    min_confidence: RecoveryConfidence = RecoveryConfidence.LOW
    max_threads: int = 4
    chunk_size: int = 1024 * 1024  # 1MB
    categories: Optional[Set[FileCategory]] = None  # None = all
    file_extensions: Optional[Set[str]] = None  # None = all
    min_file_size: int = 0  # bytes
    max_file_size: int = 0  # 0 = unlimited


class RecoveryEngine:
    """
    Main recovery engine.
    
    Coordinates file system parsing, carving, and recovery operations.
    """
    
    def __init__(
        self,
        disk_reader: DiskReader,
        filesystem_parser: Optional[FileSystemParser] = None,
        config: Optional[RecoveryConfig] = None,
        progress_callback: Optional[Callable[[RecoveryProgress], None]] = None,
    ):
        """
        Initialize recovery engine.
        
        Args:
            disk_reader: Disk reader interface
            filesystem_parser: File system parser (optional)
            config: Recovery configuration
            progress_callback: Callback for progress updates
        """
        self.disk_reader = disk_reader
        self.filesystem_parser = filesystem_parser
        self.config = config or RecoveryConfig()
        self.progress_callback = progress_callback
        
        self._lock = threading.Lock()
        self._files: List[FileEntry] = []
        self._stats = ScanStatistics()
        self._is_cancelled = False
        self._start_time: Optional[datetime] = None
        self.scan_id = f"scan_{int(datetime.now().timestamp())}"
        
        # Create a basic device info object
        from core.models.device import DeviceType, FileSystemType
        self._device_info = DeviceInfo(
            device_id=disk_reader.device_path,
            path=disk_reader.device_path,
            label="Storage Device",
            device_type=DeviceType.UNKNOWN,
            file_system=FileSystemType.UNKNOWN,
            total_size=disk_reader.total_size,
            free_space=0,
            is_removable=False,
        )
        
        logger.info("Recovery engine initialized")
    
    @property
    def files(self) -> List[FileEntry]:
        """Get list of found files."""
        return self._files.copy()
    
    @property
    def stats(self) -> ScanStatistics:
        """Get scan statistics."""
        with self._lock:
            return self._stats.copy()
    
    @property
    def is_cancelled(self) -> bool:
        """Check if scan was cancelled."""
        return self._is_cancelled
    
    def cancel(self) -> None:
        """Cancel ongoing scan."""
        self._is_cancelled = True
        logger.info("Scan cancelled by user")
    
    def scan(self) -> ScanResult:
        """
        Perform full recovery scan.
        
        Returns:
            Scan result with all found files
        """
        logger.info("Starting recovery scan...")
        self._start_time = datetime.now()
        self._files.clear()
        self._is_cancelled = False
        
        try:
            # Phase 1: File system parsing
            if self.config.scan_file_system and self.filesystem_parser:
                self._scan_filesystem()
            
            if self._is_cancelled:
                return self._create_result("cancelled")
            
            # Phase 2: File carving
            if self.config.scan_carving:
                self._scan_carving()
            
            if self._is_cancelled:
                return self._create_result("cancelled")
            
            # Phase 3: Post-processing
            self._post_process()
            
            return self._create_result("complete")
            
        except Exception as e:
            logger.exception(f"Scan error: {e}")
            return self._create_result("error", str(e))
    
    def _scan_filesystem(self) -> None:
        """Scan file system for files."""
        logger.info("Phase 1: Scanning file system...")
        
        self._report_progress(
            phase="file_system",
            progress=0,
            current_file="Initializing file system scan..."
        )
        
        try:
            # Parse file system
            fs_info = self.filesystem_parser.parse_file_system()
            
            # Enumerate files and optionally deleted files
            entries = list(self.filesystem_parser.enumerate_files())
            if self.config.recover_deleted:
                try:
                    deleted_entries = list(self.filesystem_parser.get_deleted_files())
                    entries.extend(deleted_entries)
                except Exception:
                    logger.warning("Filesystem parser does not support deleted file enumeration")
            
            total = len(entries)
            for i, entry in enumerate(entries):
                if self._is_cancelled:
                    break
                
                # Use parser-provided FileEntry objects when available
                if isinstance(entry, FileEntry):
                    file_entry = entry
                else:
                    file_entry = self._convert_directory_entry(entry)
                
                # Apply filters
                if self._should_include_file(file_entry):
                    with self._lock:
                        self._files.append(file_entry)
                        self._update_stats(file_entry)
                
                # Report progress
                if i % 100 == 0:
                    progress = (i / total) * 100 if total > 0 else 0
                    self._report_progress(
                        phase="file_system",
                        progress=progress,
                        current_file=file_entry.display_name,
                        files_found=len(self._files)
                    )
            
            logger.info(f"File system scan complete: {len(self._files)} files found")
            
        except Exception as e:
            logger.exception(f"File system scan error: {e}")
            self._stats.scan_errors += 1
    
    def _scan_carving(self) -> None:
        """Perform file carving."""
        logger.info("Phase 2: File carving...")
        
        self._report_progress(
            phase="carving",
            progress=0,
            current_file="Initializing carving engine..."
        )
        
        try:
            # Create carving engine
            carving_engine = CarvingEngine(
                disk_reader=self.disk_reader,
                min_file_size=self.config.min_file_size,
                max_file_size=self.config.max_file_size,
                chunk_size=self.config.chunk_size,
                progress_callback=lambda progress, current: self._report_progress(
                    phase="carving",
                    progress=progress,
                    current_file=current,
                )
            )
            
            # Perform carving
            carved_files = carving_engine.carve()
            
            # Convert to FileEntry
            for i, carved in enumerate(carved_files):
                if self._is_cancelled:
                    break
                
                file_entry = carved.to_file_entry(i)
                
                # Apply filters
                if self._should_include_file(file_entry):
                    with self._lock:
                        self._files.append(file_entry)
                        self._update_stats(file_entry)
            
            # Update stats
            self._stats.fragmented_files += len([f for f in carved_files if f.fragmented])
            
            logger.info(f"Carving complete: {len(carved_files)} files found")
            
        except Exception as e:
            logger.exception(f"Carving error: {e}")
            self._stats.scan_errors += 1
    
    def _post_process(self) -> None:
        """Post-process scan results."""
        logger.info("Phase 3: Post-processing...")
        
        # Remove duplicates
        self._remove_duplicates()
        
        # Sort files
        self._files.sort(key=lambda f: (f.file_category.name, f.display_name))
        
        # Update total stats
        self._stats.total_files = len(self._files)
        self._stats.total_size = sum(f.file_size for f in self._files)
        self._stats.deleted_files = len([f for f in self._files if f.status == FileStatus.DELETED])
        self._stats.recoverable_files = len([
            f for f in self._files
            if f.status == FileStatus.DELETED and
            f.recovery_confidence.value >= self.config.min_confidence.value
        ])
        
        self._report_progress(
            phase="complete",
            progress=100,
            current_file="Scan complete",
            files_found=len(self._files)
        )
    
    def _convert_directory_entry(self, entry) -> FileEntry:
        """Convert directory entry to FileEntry."""
        return FileEntry(
            file_id=f"fs_{entry.record_number}" if hasattr(entry, 'record_number') else "fs_0",
            filename=entry.name if hasattr(entry, 'name') else "unknown",
            extension=entry.name.split('.')[-1] if hasattr(entry, 'name') and '.' in entry.name else "",
            file_size=entry.file_size if hasattr(entry, 'file_size') else 0,
            file_category=FileCategory.OTHER,
            recovery_confidence=RecoveryConfidence.HIGH,
            status=FileStatus.DELETED if entry.is_deleted else FileStatus.EXISTING,
            created_time=entry.created_time if hasattr(entry, 'created_time') else None,
            modified_time=entry.modified_time if hasattr(entry, 'modified_time') else None,
            accessed_time=entry.accessed_time if hasattr(entry, 'accessed_time') else None,
            metadata={'source': 'filesystem'}
        )
    
    def _should_include_file(self, file_entry: FileEntry) -> bool:
        """Check if file should be included based on filters."""
        if file_entry.status == FileStatus.DELETED and not self.config.recover_deleted:
            return False
        if file_entry.status == FileStatus.EXISTING and not self.config.recover_existing:
            return False
        
        if file_entry.recovery_confidence.value < self.config.min_confidence.value:
            return False
        
        if self.config.categories and file_entry.file_category not in self.config.categories:
            return False
        
        if self.config.file_extensions and file_entry.extension not in self.config.file_extensions:
            return False
        
        if self.config.min_file_size and file_entry.file_size < self.config.min_file_size:
            return False
        if self.config.max_file_size and file_entry.file_size > self.config.max_file_size:
            return False
        
        return True
    
    def _update_stats(self, file_entry: FileEntry) -> None:
        """Update statistics with new file."""
        self._stats.total_files += 1
        self._stats.total_size += file_entry.file_size
        
        if file_entry.status == FileStatus.DELETED:
            self._stats.deleted_files += 1
        
        cat = file_entry.file_category.name
        self._stats.files_by_category[cat] = self._stats.files_by_category.get(cat, 0) + 1
        
        conf = file_entry.recovery_confidence.name
        self._stats.files_by_confidence[conf] = self._stats.files_by_confidence.get(conf, 0) + 1
    
    def _remove_duplicates(self) -> None:
        """Remove duplicate files."""
        seen = set()
        unique_files = []
        
        for file_entry in self._files:
            key = (file_entry.display_name, file_entry.file_size, file_entry.offset)
            
            if key not in seen:
                seen.add(key)
                unique_files.append(file_entry)
        
        self._files = unique_files
        logger.info(f"Removed {len(self._files) - len(unique_files)} duplicates")
    
    def _create_result(self, status: str, error: Optional[str] = None) -> ScanResult:
        """Create scan result."""
        end_time = datetime.now()
        duration = (end_time - self._start_time).total_seconds() if self._start_time else 0
        
        result = ScanResult(
            scan_id=self.scan_id,
            device=self._device_info,
            start_time=self._start_time or datetime.now(),
            files=self._files,
            statistics=self._stats,
            status=status,
            is_complete=status == "complete",
            error_message=error,
        )
        result.end_time = end_time
        return result
    
    def _report_progress(
        self,
        phase: str,
        progress: float,
        current_file: str,
        files_found: int = 0,
        bytes_scanned: int = 0,
    ) -> None:
        """Report progress via callback."""
        if self.progress_callback:
            progress_info = RecoveryProgress(
                phase=phase,
                progress=progress,
                current_file=current_file,
                files_found=files_found or len(self._files),
                bytes_scanned=bytes_scanned or self._stats.total_size,
            )
            self.progress_callback(progress_info)


class RecoveryOrchestrator:
    """High-level recovery orchestrator."""
    
    def __init__(self):
        self._current_engine: Optional[RecoveryEngine] = None
        self._current_scan: Optional[ScanResult] = None
        self._lock = threading.Lock()
        
        logger.info("Recovery orchestrator initialized")
    
    def start_scan(
        self,
        disk_reader: DiskReader,
        filesystem_parser: Optional[FileSystemParser] = None,
        config: Optional[RecoveryConfig] = None,
        progress_callback: Optional[Callable[[RecoveryProgress], None]] = None,
    ) -> ScanResult:
        """Start recovery scan."""
        with self._lock:
            self._current_engine = RecoveryEngine(
                disk_reader=disk_reader,
                filesystem_parser=filesystem_parser,
                config=config,
                progress_callback=progress_callback,
            )
            
            self._current_scan = self._current_engine.scan()
            
            return self._current_scan
    
    def cancel_scan(self) -> None:
        """Cancel ongoing scan."""
        with self._lock:
            if self._current_engine:
                self._current_engine.cancel()
    
    def get_current_scan(self) -> Optional[ScanResult]:
        """Get current scan result."""
        return self._current_scan
    
    def recover_files(
        self,
        disk_reader: DiskReader,
        files: List[FileEntry],
        output_dir: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        """Recover files to output directory."""
        logger.info(f"Recovering {len(files)} files to {output_dir}")
        
        results = {
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'errors': [],
            'files': [],
        }
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        def read_file_bytes(entry: FileEntry) -> bytes:
            if entry.fragments:
                data_parts = []
                for fragment_offset, fragment_size in entry.fragments:
                    chunk = disk_reader.read(fragment_offset, fragment_size)
                    data_parts.append(chunk)
                return b"".join(data_parts)

            if entry.offset is None:
                raise ValueError(f"File entry has no offset or fragments: {entry.display_name}")

            return disk_reader.read(entry.offset, entry.file_size)
        
        for i, file_entry in enumerate(files):
            try:
                if progress_callback:
                    progress_callback(i, len(files), file_entry.display_name)
                
                if file_entry.offset is None and not file_entry.fragments:
                    results['skipped'] += 1
                    results['errors'].append(f"No offset or fragments for {file_entry.display_name}")
                    continue
                
                data = read_file_bytes(file_entry)
                
                if not data:
                    results['failed'] += 1
                    results['errors'].append(f"No data recovered for {file_entry.display_name}")
                    continue
                
                output_path = output_dir / file_entry.display_name
                with open(output_path, 'wb') as f:
                    f.write(data)
                
                recovered_size = len(data)
                expected_size = file_entry.file_size or recovered_size
                verified = recovered_size == expected_size
                
                if not verified:
                    results['errors'].append(
                        f"Partial recovery for {file_entry.display_name}: expected {expected_size}, got {recovered_size}"
                    )
                
                results['success'] += 1
                results['files'].append({
                    'name': file_entry.display_name,
                    'path': str(output_path),
                    'size': recovered_size,
                    'verified': verified,
                })
                
                logger.debug(f"Recovered: {file_entry.display_name} ({recovered_size} bytes)")
                
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{file_entry.display_name}: {e}")
                logger.exception(f"Error recovering {file_entry.display_name}: {e}")
        
        logger.info(f"Recovery complete: {results['success']} success, {results['failed']} failed")
        return results