# 📦 Installation Guide

## Quick Install

### Windows

```powershell
# Method 1: Using Python directly (if pip is blocked)
python -m pip install -r requirements.txt

# Method 2: Disable App Control temporarily
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -r requirements.txt

# Method 3: Install one by one
python -m pip install PyQt6
python -m pip install reportlab
python -m pip install numpy
```

### Linux/macOS

```bash
# Standard installation
pip install -r requirements.txt

# Or using python -m
python3 -m pip install -r requirements.txt
```

---

## Detailed Installation

### Prerequisites

1. **Python 3.10 or higher**
   - Download from: https://www.python.org/downloads/
   - Verify: `python --version`

2. **Git** (optional, for cloning)
   - Download from: https://git-scm.com/

### Step 1: Clone or Download

```bash
# Clone repository
git clone https://github.com/yourusername/ever-recover.git
cd ever-recover

# OR download ZIP and extract
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv .venv

# Activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1

# Windows CMD:
.venv\Scripts\activate.bat

# Linux/macOS:
source .venv/bin/activate
```

### Step 3: Install Dependencies

```bash
# If pip works normally:
pip install -r requirements.txt

# If pip is blocked by policy:
python -m pip install -r requirements.txt

# If still blocked, install individually:
python -m pip install PyQt6
python -m pip install reportlab
python -m pip install numpy
python -m pip install tqdm
python -m pip install psutil
```

### Step 4: Verify Installation

```bash
# Run demo
python ever_recover.py --demo

# Or run GUI
python ever_recover.py
```

---

## Troubleshooting

### "pip.exe blocked by App Control"

**Solution 1:** Use python -m pip
```bash
python -m pip install -r requirements.txt
```

**Solution 2:** Temporarily allow pip
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**Solution 3:** Install individually
```bash
python -m pip install --upgrade pip
python -m pip install PyQt6 reportlab numpy tqdm psutil
```

### "ModuleNotFoundError: No module named 'PyQt6'"

```bash
# Reinstall PyQt6
python -m pip install --force-reinstall PyQt6

# Or use pip with --user flag
python -m pip install --user PyQt6
```

### "Permission denied" errors

**Windows:**
```bash
# Run as Administrator
# Or use --user flag
python -m pip install --user -r requirements.txt
```

**Linux/macOS:**
```bash
# Don't use sudo, use --user instead
python3 -m pip install --user -r requirements.txt
```

### "No matching distribution found"

```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Then install
python -m pip install -r requirements.txt
```

---

## Minimal Installation

Only need GUI? Install minimal dependencies:

```bash
python -m pip install PyQt6 reportlab numpy
```

Only need CLI? Install minimal dependencies:

```bash
python -m pip install numpy tqdm psutil
```

---

## Verify Installation

Run these commands to verify:

```bash
# Check Python version (should be 3.10+)
python --version

# Check if packages are installed
python -c "import PyQt6; print('PyQt6 OK')"
python -c "import reportlab; print('ReportLab OK')"
python -c "import numpy; print('NumPy OK')"
python -c "import tqdm; print('Tqdm OK')"

# Run demo
python ever_recover.py --demo
```

---

## Development Installation

For contributors:

```bash
# Install in editable mode
python -m pip install -e .

# Install dev tools
python -m pip install black flake8 mypy pytest

# Run tests
pytest tests/ -v

# Run linter
flake8 ever_recover/
```

---

## Uninstall

```bash
# Remove package
python -m pip uninstall ever-recover

# Remove virtual environment
rm -rf .venv  # Linux/macOS
rmdir /s .venv  # Windows
```

---

## Next Steps

- [ ] Read [USER_GUIDE.md](USER_GUIDE.md) for usage instructions
- [ ] Check [API_DOCS.md](API_DOCS.md) for developer documentation
- [ ] Run the demo: `python ever_recover.py --demo`

---

**Need Help?**

- **Documentation:** https://ever-recover.readthedocs.io
- **Issues:** https://github.com/yourusername/ever-recover/issues