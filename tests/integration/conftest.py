"""Pytest configuration and fixtures."""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def sample_jpeg():
    """Sample JPEG data."""
    return (
        b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01' +
        b'\x00\x00\x01\x00\x01\x00\x00' +
        b'\xFF\xDB\x00C\x00' + b'\x08' * 64 +
        b'\xFF\xC0\x00\x0B\x08\x00\x01\x00\x01\x01\x01\x11\x00' +
        b'\xFF\xC4\x00\x1F\x00\x00\x01\x05\x01\x01\x01\x01\x01' +
        b'\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08' +
        b'\xFF\xDA\x00\x08\x01\x01\x00\x00?\x00\x7F\xFF\xD9'
    )


@pytest.fixture
def sample_png():
    """Sample PNG data."""
    return (
        b'\x89PNG\r\n\x1A\n' +
        b'\x00' * 100 +
        b'IEND\xAE\x42\x60\x82'
    )


@pytest.fixture
def sample_pdf():
    """Sample PDF data."""
    return b'%PDF-1.4\n' + b'\x00' * 100 + b'%%EOF\n'