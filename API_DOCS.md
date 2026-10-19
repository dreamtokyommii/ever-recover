# 🔧 Ever Recover API Documentation

## Core Interfaces

### DiskReader

```python
from core.interfaces.disk_reader import DiskReader, DiskImageReader, VirtualDiskReader

# Abstract base class
class DiskReader(ABC):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def read(self, offset: int, size: int) -> bytes: ...
    @property
    def device_path(self) -> str: ...
    @property
    def total_size(self) -> int: ...
```

**Usage:**
```python
# Disk image
reader = DiskImageReader("evidence.e01")
reader.open()
data = reader.read(0, 512)  # Read first sector
reader.close()

# Virtual disk (testing)
reader = VirtualDiskReader(b'\x00' * 1024*1024, "test")
data = reader.read(0, 1024)
```

---

### FileSystemParser

```python
from core.interfaces.filesystem_parser import FileSystemParser

class FileSystemParser(ABC):
    def parse_file_system(self) -> Dict[str, Any]: ...
    def enumerate_files(self) -> Iterator[Dict[str, Any]]: ...
    def get_file_data(self, file_entry: Dict) -> bytes: ...
```

---

## Core Models

### FileEntry

```python
from core.models.file_entry import FileEntry, FileStatus, RecoveryConfidence, FileCategory

@dataclass
class FileEntry:
    file_id: str
    filename: str
    extension: str
    file_size: int
    file_category: FileCategory
    recovery_confidence: RecoveryConfidence
    status: FileStatus
    offset: Optional[int]
    created_time: Optional[datetime]
    modified_time: Optional[datetime]
    accessed_time: Optional[datetime]
    metadata: Dict[str, Any]
    
    @property
    def display_name(self) -> str: ...
    @property
    def is_recoverable(self) -> bool: ...
    def to_dict(self) -> Dict[str, Any]: ...
```

**Usage:**
```python
file_entry = FileEntry(
    file_id="file_001",
    filename="document.docx",
    extension="docx",
    file_size=50000,
    file_category=FileCategory.DOCUMENT,
    recovery_confidence=RecoveryConfidence.HIGH,
    status=FileStatus.DELETED,
    offset=0x1A0000,
)

print(file_entry.display_name)  # "document.docx"
print(file_entry.is_recoverable)  # True
```

---

### ScanResult

```python
from core.models.scan_result import ScanResult, ScanStatistics

@dataclass
class ScanResult:
    status: str
    device_path: str
    device_size: int
    files: List[FileEntry]
    statistics: ScanStatistics
    duration_seconds: float
    error_message: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]: ...
    def filter_by_category(self, category: FileCategory) -> List[FileEntry]: ...
    def filter_by_confidence(self, min_conf: RecoveryConfidence) -> List[FileEntry]: ...
```

---

## Services

### RecoveryEngine

```python
from core.services.recovery_engine import RecoveryEngine, RecoveryConfig, RecoveryProgress

@dataclass
class RecoveryConfig:
    scan_file_system: bool = True
    scan_carving: bool = True
    recover_deleted: bool = True
    min_confidence: RecoveryConfidence = RecoveryConfidence.LOW
    max_threads: int = 4
    chunk_size: int = 1024 * 1024
    categories: Optional[Set[FileCategory]] = None
    file_extensions: Optional[Set[str]] = None
    min_file_size: int = 0
    max_file_size: int = 0

class RecoveryEngine:
    def __init__(
        self,
        disk_reader: DiskReader,
        config: Optional[RecoveryConfig] = None,
        progress_callback: Optional[Callable[[RecoveryProgress], None]] = None,
    ): ...
    
    def scan(self) -> ScanResult: ...
    def cancel(self) -> None: ...
    @property
    def files(self) -> List[FileEntry]: ...
    @property
    def stats(self) -> ScanStatistics: ...
```

**Usage:**
```python
config = RecoveryConfig(
    scan_file_system=False,
    scan_carving=True,
    recover_deleted=True,
    min_confidence=RecoveryConfidence.HIGH,
    max_threads=8,
)

engine = RecoveryEngine(reader, config=config)
result = engine.scan()

print(f"Found {result.statistics.total_files} files")
```

---

### CarvingEngine

```python
from core.services.carving_engine import CarvingEngine, CarvedFile

class CarvingEngine:
    def __init__(
        self,
        disk_reader: DiskReader,
        signatures: Optional[List[FileSignature]] = None,
        min_file_size: int = 1024,
        chunk_size: int = 1024 * 1024,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ): ...
    
    def carve(self) -> List[CarvedFile]: ...
    def cancel(self) -> None: ...
```

---

### ReportGenerator

```python
from core.services.report_generator import ReportGenerator, ReportMetadata

@dataclass
class ReportMetadata:
    case_number: str
    examiner_name: str
    organization: str
    notes: str
    evidence_items: List[str] = None
    scan_start: datetime = None
    scan_end: datetime = None

class ReportGenerator:
    def __init__(
        self,
        scan_result: ScanResult,
        metadata: ReportMetadata,
    ): ...
    
    def generate_pdf(self, output_path: Path) -> None: ...
    def generate_html(self, output_path: Path) -> None: ...
    def generate_csv(self, output_path: Path) -> None: ...
    def generate_json(self, output_path: Path) -> None: ...
```

---

## AI Features

### FileClassifier

```python
from ai.classifiers.file_classifier import FileClassifier, ClassificationResult

@dataclass
class ClassificationResult:
    predicted_category: FileCategory
    confidence: float
    is_corrupted: bool
    corruption_score: float
    alternative_categories: List[Tuple[FileCategory, float]]

class FileClassifier:
    def __init__(self, model_path: Optional[str] = None): ...
    
    def classify(
        self,
        file_entry: FileEntry,
        file_sample: bytes,
    ) -> ClassificationResult: ...
```

**Usage:**
```python
classifier = FileClassifier()

sample = reader.read(file_entry.offset, 1024)
result = classifier.classify(file_entry, sample)

print(f"Category: {result.predicted_category.name}")
print(f"Confidence: {result.confidence:.0%}")
print(f"Corrupted: {result.is_corrupted}")
```

---

### SmartRecoverySorter

```python
from ai.classifiers.file_classifier import SmartRecoverySorter

class SmartRecoverySorter:
    def __init__(self): ...
    
    def prioritize(
        self,
        files: List[FileEntry],
        top_n: int = 10,
    ) -> List[FileEntry]: ...
```

---

## Optimization

### ParallelProcessor

```python
from core.optimization.thread_manager import ParallelProcessor

class ParallelProcessor:
    def __init__(
        self,
        max_workers: int = 8,
        batch_size: int = 100,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ): ...
    
    def process(
        self,
        items: List[Any],
        func: Callable[[Any], Any],
        on_error: Optional[Callable[[Exception, Any], None]] = None,
    ) -> List[Any]: ...
    
    def process_with_retries(
        self,
        items: List[Any],
        func: Callable[[Any], Any],
        max_retries: int = 3,
    ) -> List[Any]: ...
```

---

### ChunkCache

```python
from core.optimization.cache_manager import ChunkCache

class ChunkCache:
    def __init__(
        self,
        max_size_bytes: int = 100 * 1024 * 1024,
        ttl_seconds: int = 300,
    ): ...
    
    def get(self, key: str) -> Optional[bytes]: ...
    def put(self, key: str, value: bytes, priority: int = 0) -> None: ...
    def get_or_read(
        self,
        key: str,
        read_func: Callable[[], bytes],
    ) -> bytes: ...
    def clear(self) -> None: ...
    def get_stats(self) -> Dict[str, Any]: ...
```

---

## Examples

### Complete Recovery Workflow

```python
from pathlib import Path
from core.interfaces.disk_reader import DiskImageReader
from core.services.recovery_engine import RecoveryEngine, RecoveryConfig
from core.services.report_generator import ReportGenerator, ReportMetadata
from ai.classifiers.file_classifier import FileClassifier

# 1. Open disk image
reader = DiskImageReader("evidence.e01")
reader.open()

# 2. Configure recovery
config = RecoveryConfig(
    scan_file_system=False,
    scan_carving=True,
    recover_deleted=True,
    min_confidence=RecoveryConfidence.MEDIUM,
    max_threads=8,
)

# 3. Run scan
engine = RecoveryEngine(reader, config=config)
result = engine.scan()

# 4. Classify files
classifier = FileClassifier()
for file_entry in result.files:
    if file_entry.offset:
        sample = reader.read(file_entry.offset, 1024)
        classification = classifier.classify(file_entry, sample)
        file_entry.metadata['classification'] = classification

# 5. Recover files
output_dir = Path("./recovered")
output_dir.mkdir()

for file_entry in result.files[:100]:  # Top 100
    if file_entry.offset:
        data = reader.read(file_entry.offset, file_entry.file_size)
        output_path = output_dir / file_entry.display_name
        with open(output_path, 'wb') as f:
            f.write(data)

# 6. Generate report
metadata = ReportMetadata(
    case_number="CASE-2026-001",
    examiner_name="John Doe",
    organization="Forensics Lab",
)

generator = ReportGenerator(result, metadata)
generator.generate_pdf("forensic_report.pdf")

reader.close()
```

---

**Last Updated:** July 2026  
**Version:** 1.0.0