# 🔍 Ever Recover - Professional Digital Forensics & File Recovery Tool

**Version:** 1.0.0  
**Build Date:** July 2026  
**License:** MIT

---

## 📋 Overview

Ever Recover is a comprehensive digital forensics and file recovery solution designed for:
- **Data Recovery Professionals** - Recover deleted files from damaged or formatted drives
- **Digital Forensics Investigators** - Generate court-admissible forensic reports
- **IT Security Teams** - Analyze disk images and extract evidence
- **General Users** - Recover accidentally deleted files

### ✨ Key Features

- 🗂️ **File System Parsing** - NTFS, FAT32, exFAT, EXT4 support
- 🔎 **Signature-Based Carving** - 37+ file types (JPEG, PNG, PDF, DOCX, etc.)
- 🤖 **AI-Powered Classification** - Automatic file type detection and corruption analysis
- 📊 **Forensic Reports** - PDF, HTML, CSV, JSON export
- ⚡ **Multi-threaded Recovery** - Up to 8x faster with parallel processing
- 🖥️ **Dual Interface** - Professional GUI and powerful CLI
- 📈 **Smart Prioritization** - AI-driven recovery queue management
- 🔒 **Chain of Custody** - Built-in evidence tracking

---

## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/ever-recover.git
cd ever-recover

# Install dependencies
pip install -r requirements.txt

# Optional: Install for better CLI experience
pip install tqdm
```

### Requirements

- **Python:** 3.10+
- **PyQt6:** GUI interface
- **ReportLab:** PDF generation
- **NumPy:** AI classification
- **Tqdm:** Progress bars (optional)

---

## 📖 Usage

### GUI Mode

```bash
python ever_recover.py
```

**Steps:**
1. Select device or disk image (E01, IMG, RAW)
2. Configure scan options (file types, confidence filters)
3. Start scan and review results
4. Recover files with one click
5. Generate forensic reports

### CLI Mode

```bash
# Scan disk image
python ever_recover.py scan disk_image.e01 -o ./recovered

# Recover with filters
python ever_recover.py scan /dev/sdb1 -o ./output \
  --categories IMAGE,DOCUMENT \
  --min-confidence HIGH

# Full workflow
python ever_recover.py full disk_image.e01 -o ./output --all-reports

# Generate report only
python ever_recover.py report disk_image.e01 -o ./report --format pdf --case "CASE-2026-001"
```

### Demo Mode

```bash
# Run built-in demo
python ever_recover.py --demo
```

---

## 📁 Project Structure
