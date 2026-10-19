# 📘 Ever Recover User Guide

## Table of Contents

1. [Getting Started](#getting-started)
2. [GUI Walkthrough](#gui-walkthrough)
3. [CLI Reference](#cli-reference)
4. [Advanced Features](#advanced-features)
5. [Troubleshooting](#troubleshooting)

---

## Getting Started

### First Run

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Launch Application**
   ```bash
   python ever_recover.py
   ```

3. **Select Device**
   - Click "Select Device" button
   - Choose from physical drives or disk images
   - Click "Start Scan"

### Understanding Results

- **Green** = High confidence, recoverable
- **Yellow** = Medium confidence, may be fragmented
- **Red** = Low confidence, likely corrupted

---

## GUI Walkthrough

### Main Window

**Device Panel (Left)**
- Lists all detected drives
- Shows disk images (E01, IMG, RAW)
- Displays device info (size, type, status)

**File List (Center)**
- Displays recovered files
- Sortable by name, size, date, confidence
- Preview on double-click

**Actions Panel (Right)**
- Filter by category
- Set confidence threshold
- Recover selected/all files
- Generate reports

### Step-by-Step Recovery

1. **Select Device**
   - Click "Select Device"
   - Browse to disk image or select physical drive
   - Click "OK"

2. **Configure Scan**
   - Check "File System Parsing" (if drive is intact)
   - Check "File Carving" (always recommended)
   - Select file categories to recover
   - Set minimum confidence level

3. **Start Scan**
   - Click "Start Scan"
   - Monitor progress bar
   - View real-time file discovery

4. **Review Results**
   - Browse recovered files
   - Use filters to narrow results
   - Preview files before recovery

5. **Recover Files**
   - Select files to recover
   - Click "Recover Selected"
   - Choose output directory
   - Wait for completion

6. **Generate Report**
   - Click "Generate Report"
   - Select format (PDF, HTML, CSV, JSON)
   - Enter case information
   - Save report

---

## CLI Reference

### Commands

#### `scan` - Scan Device

```bash
python ever_recover.py scan <device> -o <output_dir> [options]
```

**Options:**
- `-h, --help` - Show help
- `-o, --output PATH` - Output directory (required)
- `--categories LIST` - File categories (comma-separated)
- `--min-confidence LEVEL` - LOW|MEDIUM|HIGH|EXCELLENT
- `--no-carving` - Disable file carving
- `--max-size MB` - Maximum file size
- `-v, --verbose` - Verbose output
- `--json` - JSON output

**Examples:**
```bash
# Basic scan
python ever_recover.py scan disk.e01 -o ./recovered

# Scan with filters
python ever_recover.py scan /dev/sdb1 -o ./output \
  --categories IMAGE,DOCUMENT,VIDEO \
  --min-confidence HIGH

# JSON output for scripting
python ever_recover.py scan disk.e01 -o ./output --json > results.json
```

#### `recover` - Recover Files

```bash
python ever_recover.py recover <device> -o <output_dir> [options]
```

**Options:**
- `--files FILE1 FILE2` - Specific files to recover
- `--all` - Recover all files
- `-v, --verbose` - Verbose output
- `--json` - JSON output

**Examples:**
```bash
# Recover all files
python ever_recover.py recover disk.e01 -o ./recovered --all

# Recover specific files
python ever_recover.py recover disk.e01 -o ./recovered \
  --files "document1.docx" "photo1.jpg" "video1.mp4"
```

#### `report` - Generate Report

```bash
python ever_recover.py report <device> -o <output_dir> [options]
```

**Options:**
- `--format FORMAT` - pdf|html|csv|json|all
- `--case CASE_NUM` - Case number
- `--examiner NAME` - Examiner name
- `-v, --verbose` - Verbose output

**Examples:**
```bash
# PDF report
python ever_recover.py report disk.e01 -o ./report \
  --format pdf --case "CASE-2026-001" --examiner "John Doe"

# All formats
python ever_recover.py report disk.e01 -o ./report --format all
```

#### `full` - Complete Workflow

```bash
python ever_recover.py full <device> -o <output_dir> [options]
```

**Options:**
- `--all-reports` - Generate all report formats
- `--categories LIST` - File categories
- `-v, --verbose` - Verbose output

**Example:**
```bash
python ever_recover.py full disk.e01 -o ./output --all-reports
```

---

## Advanced Features

### Custom File Signatures

```python
from core.models.file_signature import FileSignature, SignatureDatabase

# Create custom signature
custom_sig = FileSignature(
    name="Custom Database",
    extension="db",
    header=b'\x00\x00\x00\x01SQLite format 3',
    category=FileCategory.DATABASE,
    min_size=4096,
)

# Add to database
SignatureDatabase.add_signature(custom_sig)
```

### Multi-threaded Recovery

```python
from core.optimization.thread_manager import ParallelProcessor

processor = ParallelProcessor(
    max_workers=8,
    batch_size=100,
    progress_callback=lambda done, total: print(f"{done}/{total}"),
)

# Process files in parallel
results = processor.process(
    items=file_list,
    func=lambda f: recover_file(f),
)
```

### Caching

```python
from core.optimization.cache_manager import ChunkCache

cache = ChunkCache(max_size_mb=500)

# Read with caching
data = cache.get_or_read(
    key=f"offset_{offset}",
    read_func=lambda: disk_reader.read(offset, size),
)
```

### AI Classification

```python
from ai.classifiers.file_classifier import FileClassifier

classifier = FileClassifier()

# Classify multiple files
for file_entry in scan_result.files:
    sample = disk_reader.read(file_entry.offset, 1024)
    result = classifier.classify(file_entry, sample)
    
    # Check if file is corrupted
    if result.is_corrupted:
        print(f"⚠️  {file_entry.display_name} is corrupted "
              f"(score: {result.corruption_score:.0%})")
```

---

## Troubleshooting

### Common Issues

**Issue:** No files found after scan  
**Solution:**
- Verify disk image is not corrupted
- Lower minimum confidence to LOW
- Enable both file system and carving
- Increase scan chunk size

**Issue:** Slow scan performance  
**Solution:**
- Increase `max_threads` in config
- Use larger `chunk_size` (1MB recommended)
- Disable file system parsing if not needed
- Filter by specific categories

**Issue:** "Disk access denied" error  
**Solution:**
- Run as Administrator (Windows)
- Use `sudo` (Linux/macOS)
- Create disk image first: `dd if=/dev/sdX of=disk.img`

**Issue:** Out of memory  
**Solution:**
- Reduce `max_threads` to 2-4
- Decrease cache size
- Scan in smaller chunks
- Use 64-bit Python

---

## Best Practices

1. **Always work on disk images**, not original evidence
2. **Document everything** - use case numbers and notes
3. **Verify recovered files** - check integrity after recovery
4. **Keep originals** - don't delete source until verified
5. **Use high confidence** for critical files, lower for everything else
6. **Generate reports immediately** - document chain of custody

---

## Support

- **Documentation:** https://ever-recover.readthedocs.io
- **Issues:** https://github.com/yourusername/ever-recover/issues
- **Email:** support@ever-recover.com

---

**Last Updated:** July 2026  
**Version:** 1.0.0