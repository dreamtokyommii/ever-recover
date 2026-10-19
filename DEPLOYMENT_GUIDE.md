# 🚀 Deployment Guide

This guide covers deploying Ever Recover to various platforms.

---

## PyPI Deployment

### Prerequisites

```bash
# Install twine
python -m pip install twine

# Create PyPI account at https://pypi.org
```

### Build Package

```bash
# Install build tools
python -m pip install build wheel

# Build source and wheel distributions
python -m build

# This creates:
# - dist/ever_recover-1.0.0.tar.gz (source)
# - dist/ever_recover-1.0.0-py3-none-any.whl (wheel)
```

### Upload to TestPyPI

```bash
# Test first with TestPyPI
python -m twine upload --repository testpypi dist/*

# Enter your TestPyPI credentials
# Username: your-username
# Password: your-password
```

### Verify Installation

```bash
# Install from TestPyPI
python -m pip install --index-url https://test.pypi.org/simple/ ever-recover

# Test it
ever-recover --help
```

### Upload to PyPI

```bash
# Upload to real PyPI
python -m twine upload dist/*

# Enter your PyPI credentials
```

### Verify on PyPI

Visit: https://pypi.org/project/ever-recover/

---

## GitHub Release

### Create Release

1. Go to: https://github.com/yourusername/ever-recover/releases
2. Click "Create a new release"
3. Tag version: `v1.0.0`
4. Release title: "Ever Recover v1.0.0 - Initial Release"
5. Description: Use CHANGELOG.md content
6. Attach ZIP file: `dist/ever_recover_v1.0.0.zip`
7. Check "This is a pre-release" (optional)
8. Click "Publish release"

### Release Notes Template

```markdown
## 🎉 Ever Recover v1.0.0 - Initial Release

### What's New

- ✅ Complete digital forensics and file recovery tool
- ✅ 37+ file signature support (JPEG, PNG, PDF, DOCX, etc.)
- ✅ AI-powered file classification and corruption detection
- ✅ Professional GUI and full-featured CLI
- ✅ Forensic report generation (PDF, HTML, CSV, JSON)
- ✅ Multi-threaded recovery engine
- ✅ Comprehensive documentation

### Installation

#### Windows

```powershell
# Download ZIP and extract
cd ever_recover
.\build.bat
.\.venv\Scripts\Activate.ps1
python ever_recover.py
```

#### Linux/macOS

```bash
# Using pip
pip install ever-recover

# Or from source
git clone https://github.com/yourusername/ever-recover.git
cd ever_recover
make install
make run-gui
```

### Quick Start

```bash
# GUI mode
python ever_recover.py

# CLI mode
ever-recover scan disk.e01 -o ./recovered

# Demo mode
python ever_recover.py --demo
```

### Downloads

- [ever_recover_v1.0.0.zip](link-to-zip) - Full source distribution
- [ever_recover-1.0.0.tar.gz](link-to-tar) - Source tarball
- [ever_recover-1.0.0-py3-none-any.whl](link-to-whl) - Python wheel

### Known Issues

- Windows App Control may block pip (use `python -m pip` workaround)
- Physical disk access requires Administrator privileges

### What's Next

See [ROADMAP.md](ROADMAP.md) for upcoming features in v1.1.0

***

**Full Changelog:** https://github.com/yourusername/ever-recover/compare/v0.0.0...v1.0.0
```

---

## Docker Deployment

Create `Dockerfile`:

```dockerfile
# Ever Recover Docker Image
FROM python:3.11-slim

LABEL maintainer="Ever Recover Team <support@ever-recover.com>"
LABEL version="1.0.0"
LABEL description="Professional Digital Forensics & File Recovery Tool"

# Install dependencies
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create output directory
RUN mkdir -p /output

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV EVER_RECOVER_OUTPUT=/output

# Expose port for web interface (future feature)
EXPOSE 8080

# Default command
CMD ["python", "ever_recover.py", "--help"]
```

### Build Docker Image

```bash
docker build -t ever-recover:1.0.0 .
```

### Run Docker Container

```bash
# CLI mode
docker run -v /path/to/evidence:/evidence -v /path/to/output:/output \
  ever-recover:1.0.0 \
  python ever_recover.py scan /evidence/disk.e01 -o /output

# Interactive mode
docker run -it ever-recover:1.0.0 bash
```

---

## Chocolatey Deployment (Windows)

Create `ever-recover.nuspec`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd">
  <metadata>
    <id>ever-recover</id>
    <version>1.0.0</version>
    <title>Ever Recover</title>
    <authors>Ever Recover Team</authors>
    <owners>Ever Recover Team</owners>
    <licenseUrl>https://github.com/yourusername/ever-recover/blob/main/LICENSE</licenseUrl>
    <projectUrl>https://github.com/yourusername/ever-recover</projectUrl>
    <iconUrl>https://raw.githubusercontent.com/yourusername/ever-recover/main/icon.png</iconUrl>
    <requireLicenseAcceptance>false</requireLicenseAcceptance>
    <description>Professional Digital Forensics & File Recovery Tool</description>
    <releaseNotes>See https://github.com/yourusername/ever-recover/releases</releaseNotes>
    <copyright>2026 Ever Recover Team</copyright>
    <tags>forensics data-recovery file-recovery</tags>
    <dependencies>
      <dependency id="python3" version="[3.10,4.0)" />
    </dependencies>
  </metadata>
  <files>
    <file src="tools\**" target="tools" />
  </files>
</package>
```

Create `tools\chocolateyinstall.ps1`:

```powershell
$ErrorActionPreference = 'Stop'

$packageName = 'ever-recover'
$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Install from PyPI
python -m pip install ever-recover

# Create start menu shortcut
$shortcutPath = Join-Path $toolsDir "ever-recover.lnk"
$targetPath = (Get-Command python).Source
$arguments = "-m ever_recover"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $toolsDir
$shortcut.Save()

Write-Host "Ever Recover installed successfully!"
Write-Host "Run: ever-recover --help"
```

---

## Homebrew Deployment (macOS)

Create `ever-recover.rb`:

```ruby
class EverRecover < Formula
  desc "Professional Digital Forensics & File Recovery Tool"
  homepage "https://github.com/yourusername/ever-recover"
  url "https://files.pythonhosted.org/packages/source/e/ever-recover/ever-recover-1.0.0.tar.gz"
  sha256 "your-sha256-hash"
  license "MIT"

  depends_on "python@3.11"

  def install
    system "python3", "-m", "pip", "install", "--verbose", ".", "--prefix=#{prefix}"
  end

  test do
    system "ever-recover", "--help"
  end
end
```

---

## Verification Checklist

### ✅ Pre-Release

- [ ] All tests pass (`python test_deployment.py`)
- [ ] Documentation complete
- [ ] Version number updated in all files
- [ ] CHANGELOG.md updated
- [ ] Git tags created
- [ ] Distribution ZIP created
- [ ] Docker image built and tested
- [ ] Security scan passed

### ✅ Release

- [ ] PyPI package uploaded
- [ ] GitHub release created
- [ ] Docker image pushed to registry
- [ ] Chocolatey package submitted
- [ ] Homebrew formula submitted
- [ ] Documentation website updated
- [ ] Release announcement posted

### ✅ Post-Release

- [ ] Monitor GitHub issues
- [ ] Respond to user feedback
- [ ] Track download statistics
- [ ] Plan v1.1.0 features
- [ ] Update roadmap

---

## Download Links

- **PyPI:** https://pypi.org/project/ever-recover/
- **GitHub:** https://github.com/yourusername/ever-recover/releases
- **Docker:** https://hub.docker.com/r/yourusername/ever-recover
- **Documentation:** https://ever-recover.readthedocs.io

---

## Support

- **Issues:** https://github.com/yourusername/ever-recover/issues
- **Discord:** https://discord.gg/ever-recover
- **Email:** support@ever-recover.com

---

**Last Updated:** July 2026  
**Version:** 1.0.0