# 🤝 Contributing to Ever Recover

Thank you for your interest in contributing! This guide will help you get started.

## Quick Links

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Testing](#testing)

---

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Welcome newcomers and help them learn
- Keep discussions professional and on-topic

---

## Getting Started

### 1. Fork the Repository

Click "Fork" on GitHub, then clone:

```bash
git clone https://github.com/YOUR_USERNAME/ever-recover.git
cd ever-recover
```

### 2. Set Up Development Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate
# Windows:
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
python -m pip install -r requirements.txt

# Install dev tools
python -m pip install black flake8 mypy pytest
```

### 3. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

---

## Making Changes

### Code Style

- Follow **PEP 8** guidelines
- Use **type hints** for all functions
- Write **docstrings** for public APIs
- Keep functions focused (max 30 lines ideal)

**Example:**
```python
from typing import List, Optional
from pathlib import Path


def recover_files(
    files: List[FileEntry],
    output_dir: Path,
    verify: bool = True,
) -> List[Path]:
    """
    Recover files to output directory.
    
    Args:
        files: List of files to recover
        output_dir: Directory to save files
        verify: Verify file integrity after recovery
        
    Returns:
        List of recovered file paths
    """
    recovered = []
    for file in files:
        # ... implementation
        pass
    return recovered
```

### Commit Messages

Use clear, descriptive commit messages:

```bash
# Good
git commit -m "Add NTFS file system parser"
git commit -m "Fix Unicode encoding error on Windows"
git commit -m "Improve carving performance by 40%"

# Bad
git commit -m "fix stuff"
git commit -m "update"
```

---

## Pull Request Guidelines

### Before Submitting

1. **Test your changes**
   ```bash
   pytest tests/ -v
   python ever_recover.py --demo
   ```

2. **Run linters**
   ```bash
   flake8 ever_recover/
   black --check ever_recover/
   ```

3. **Update documentation**
   - Update README.md if adding features
   - Add docstrings to new functions
   - Update API_DOCS.md for new APIs

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests pass
- [ ] Demo runs successfully
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings
```

---

## Testing

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Test

```bash
pytest tests/integration/test_full_recovery.py -v
```

### Write Tests

```python
def test_new_feature():
    """Test new feature."""
    # Given
    setup_data = create_test_data()
    
    # When
    result = new_feature(setup_data)
    
    # Then
    assert result == expected_value
    assert result.is_valid
```

---

## Areas We Need Help

### High Priority

- [ ] **APFS/HFS+ Support** - Apple file systems
- [ ] **BitLocker Decryption** - Encrypted volume support
- [ ] **Cloud Integration** - OneDrive, Google Drive, Dropbox
- [ ] **Network Shares** - SMB/CIFS scanning
- [ ] **Mobile Devices** - Android/iOS support

### Nice to Have

- [ ] **Dark Mode** - UI theme
- [ ] **Multi-language** - i18n support
- [ ] **Docker** - Container support
- [ ] **Plugin System** - Custom extensions
- [ ] **REST API** - Remote control

---

## Reporting Issues

### Bug Report Template

```markdown
**Describe the bug**
Clear description of what's wrong

**To Reproduce**
Steps to reproduce:
1. Go to '...'
2. Click on '...'
3. See error

**Expected behavior**
What should happen

**Screenshots**
If applicable

**Environment**
- OS: Windows 11
- Python: 3.11
- Version: 1.0.0

**Additional context**
Any other details
```

### Feature Request Template

```markdown
**Is your feature request related to a problem?**
Describe the problem

**Describe the solution you'd like**
What you want to happen

**Describe alternatives you've considered**
Other solutions you've thought about

**Additional context**
Any other details
```

---

## Architecture Overview
