# 🚀 Quick Start Guide

## 1-Minute Setup

### Windows

```powershell
# 1. Install Python 3.10+ from python.org
# 2. Open PowerShell in this folder
# 3. Run build script
.\build.bat

# 4. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 5. Run Ever Recover
python ever_recover.py
```

### Linux/macOS

```bash
# 1. Install dependencies
make install

# 2. Run GUI
make run-gui

# Or manually:
python3 -m pip install -r requirements.txt
python3 ever_recover.py
```

---

## First Recovery

### GUI Mode

1. **Launch**
   ```bash
   python ever_recover.py
   ```

2. **Select Device**
   - Click "Select Device"
   - Choose disk image (E01, IMG, RAW) or physical drive
   - Click "OK"

3. **Configure Scan**
   - Check "File System Parsing" (if drive intact)
   - Check "File Carving" (always recommended)
   - Select file categories (or leave all checked)
   - Set minimum confidence: HIGH or MEDIUM

4. **Start Scan**
   - Click "Start Scan"
   - Wait for scan to complete (progress bar shows status)

5. **Review Results**
   - Browse recovered files in center panel
   - Use filters on right panel to narrow results
   - Double-click files to preview

6. **Recover Files**
   - Select files to recover (Ctrl+Click for multiple)
   - Click "Recover Selected"
   - Choose output directory
   - Wait for recovery to complete

7. **Generate Report** (Optional)
   - Click "Generate Report"
   - Select format: PDF, HTML, CSV, or JSON
   - Enter case information
   - Save report

### CLI Mode

```bash
# Scan disk image
python ever_recover.py scan disk_image.e01 -o ./recovered

# Recover with filters
python ever_recover.py scan /path/to/disk.img -o ./output \
  --categories IMAGE,DOCUMENT \
  --min-confidence HIGH

# Full workflow
python ever_recover.py full disk_image.e01 -o ./output --all-reports
```

---

## Demo Mode

Try the built-in demo:

```bash
python ever_recover.py --demo
```

This will:
- Create a virtual disk with sample files
- Run a complete recovery scan
- Classify files with AI
- Generate forensic reports
- Show all output in console

---

## Verify Installation

```bash
# Check Python version (should be 3.10+)
python --version

# Test imports
python -c "from core.interfaces.disk_reader import DiskReader; print('OK')"

# Run demo
python ever_recover.py --demo
```

---

## Next Steps

- [ ] Read [USER_GUIDE.md](USER_GUIDE.md) for detailed instructions
- [ ] Check [API_DOCS.md](API_DOCS.md) for developer documentation
- [ ] Run [test_deployment.py](test_deployment.py) to verify installation
- [ ] Join Discord: https://discord.gg/ever-recover

---

**Need Help?**

- **Documentation:** https://ever-recover.readthedocs.io
- **Issues:** https://github.com/yourusername/ever-recover/issues
- **Email:** support@ever-recover.com

---

**Happy Recovering! 🎉**