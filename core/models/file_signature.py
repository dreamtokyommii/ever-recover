"""File signature definitions for carving."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, ClassVar
from enum import Enum, auto


class FileCategory(Enum):
    """File category enumeration."""
    IMAGE = auto()
    VIDEO = auto()
    AUDIO = auto()
    DOCUMENT = auto()
    ARCHIVE = auto()
    EXECUTABLE = auto()
    DATA = auto()
    OTHER = auto()


@dataclass
class FileSignature:
    """
    File signature definition for carving.
    
    Attributes:
        name: Human-readable name (e.g., "JPEG Image")
        extension: File extension (e.g., "jpg")
        category: File category
        signature: Magic bytes at file start
        offset: Offset where signature appears (usually 0)
        footer: Optional footer/end marker
        min_size: Minimum file size in bytes
        max_size: Maximum file size in bytes
        header_size: Size of header to parse for file size
        size_offset: Offset in header where size is stored
        size_format: Struct format for parsing size
        endian: Endianness for size parsing ('big' or 'little')
    """
    name: str
    extension: str
    category: FileCategory
    signature: bytes
    offset: int = 0
    footer: Optional[bytes] = None
    min_size: int = 0
    max_size: int = 0
    header_size: int = 0
    size_offset: int = 0
    size_format: str = ""
    endian: str = "big"
    header: Optional[bytes] = None
    header_pattern: Optional[bytes] = None
    fixed_size: int = 0
    size_length: int = 0

    def __post_init__(self) -> None:
        """Normalize header-related fields to support legacy carving code."""
        if self.header is None and self.signature:
            self.header = self.signature
        if self.header_pattern is None and self.header:
            self.header_pattern = self.header

    @property
    def signature_hex(self) -> str:
        """Get hex representation of signature."""
        return self.signature.hex().upper()
    
    def matches(self, data: bytes, offset: int = 0) -> bool:
        """
        Check if data matches signature at offset.
        
        Args:
            data: Data buffer
            offset: Offset to check in data
            
        Returns:
            True if signature matches
        """
        if len(data) < offset + len(self.signature):
            return False
        return data[offset:offset + len(self.signature)] == self.signature


# Common file signatures database
COMMON_SIGNATURES = [
    # Images
    FileSignature(
        name="JPEG Image",
        extension="jpg",
        category=FileCategory.IMAGE,
        signature=b'\xFF\xD8\xFF',
        footer=b'\xFF\xD9',
        min_size=1024,
    ),
    FileSignature(
        name="PNG Image",
        extension="png",
        category=FileCategory.IMAGE,
        signature=b'\x89PNG\r\n\x1A\n',
        footer=b'IEND\xAE\x42\x60\x82',
        min_size=1024,
    ),
    FileSignature(
        name="GIF Image",
        extension="gif",
        category=FileCategory.IMAGE,
        signature=b'GIF87a' if False else b'GIF89a',
        min_size=1024,
    ),
    FileSignature(
        name="BMP Image",
        extension="bmp",
        category=FileCategory.IMAGE,
        signature=b'BM',
        header_size=14,
        size_offset=2,
        size_format='I',
        endian='little',
        min_size=54,
    ),
    FileSignature(
        name="TIFF Image (Little Endian)",
        extension="tif",
        category=FileCategory.IMAGE,
        signature=b'II\x2A\x00',
        min_size=1024,
    ),
    FileSignature(
        name="TIFF Image (Big Endian)",
        extension="tif",
        category=FileCategory.IMAGE,
        signature=b'MM\x00\x2A',
        min_size=1024,
    ),
    FileSignature(
        name="WebP Image",
        extension="webp",
        category=FileCategory.IMAGE,
        signature=b'RIFF',
        offset=0,
        min_size=1024,
    ),
    
    # Documents
    FileSignature(
        name="PDF Document",
        extension="pdf",
        category=FileCategory.DOCUMENT,
        signature=b'%PDF',
        footer=b'%%EOF',
        min_size=1024,
    ),
    FileSignature(
        name="Microsoft Word (DOCX)",
        extension="docx",
        category=FileCategory.DOCUMENT,
        signature=b'PK\x03\x04',  # ZIP format
        min_size=1024,
    ),
    FileSignature(
        name="Microsoft Excel (XLSX)",
        extension="xlsx",
        category=FileCategory.DOCUMENT,
        signature=b'PK\x03\x04',
        min_size=1024,
    ),
    FileSignature(
        name="Microsoft PowerPoint (PPTX)",
        extension="pptx",
        category=FileCategory.DOCUMENT,
        signature=b'PK\x03\x04',
        min_size=1024,
    ),
    FileSignature(
        name="Old Word Document (DOC)",
        extension="doc",
        category=FileCategory.DOCUMENT,
        signature=b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1',
        min_size=1024,
    ),
    FileSignature(
        name="Old Excel Spreadsheet (XLS)",
        extension="xls",
        category=FileCategory.DOCUMENT,
        signature=b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1',
        min_size=1024,
    ),
    FileSignature(
        name="RTF Document",
        extension="rtf",
        category=FileCategory.DOCUMENT,
        signature=b'{\\rtf',
        min_size=1024,
    ),
    
    # Archives
    FileSignature(
        name="ZIP Archive",
        extension="zip",
        category=FileCategory.ARCHIVE,
        signature=b'PK\x03\x04',
        min_size=1024,
    ),
    FileSignature(
        name="RAR Archive",
        extension="rar",
        category=FileCategory.ARCHIVE,
        signature=b'Rar!\x1A\x07',
        min_size=1024,
    ),
    FileSignature(
        name="7-Zip Archive",
        extension="7z",
        category=FileCategory.ARCHIVE,
        signature=b'7z\xBC\xAF\x27\x1C',
        min_size=1024,
    ),
    FileSignature(
        name="GZIP Archive",
        extension="gz",
        category=FileCategory.ARCHIVE,
        signature=b'\x1F\x8B\x08',
        min_size=1024,
    ),
    FileSignature(
        name="TAR Archive",
        extension="tar",
        category=FileCategory.ARCHIVE,
        signature=b'ustar',
        offset=257,
        min_size=512,
    ),
    
    # Audio
    FileSignature(
        name="MP3 Audio",
        extension="mp3",
        category=FileCategory.AUDIO,
        signature=b'ID3',
        min_size=1024,
    ),
    FileSignature(
        name="MP3 Audio (no ID3)",
        extension="mp3",
        category=FileCategory.AUDIO,
        signature=b'\xFF\xFB',
        min_size=1024,
    ),
    FileSignature(
        name="WAV Audio",
        extension="wav",
        category=FileCategory.AUDIO,
        signature=b'RIFF',
        min_size=1024,
    ),
    FileSignature(
        name="FLAC Audio",
        extension="flac",
        category=FileCategory.AUDIO,
        signature=b'fLaC',
        min_size=1024,
    ),
    FileSignature(
        name="AAC Audio",
        extension="aac",
        category=FileCategory.AUDIO,
        signature=b'\xFF\xF1',
        min_size=1024,
    ),
    FileSignature(
        name="MIDI Audio",
        extension="mid",
        category=FileCategory.AUDIO,
        signature=b'MThd',
        min_size=1024,
    ),
    
    # Video
    FileSignature(
        name="MP4 Video",
        extension="mp4",
        category=FileCategory.VIDEO,
        signature=b'\x00\x00\x00\x18ftyp',
        min_size=1024,
    ),
    FileSignature(
        name="AVI Video",
        extension="avi",
        category=FileCategory.VIDEO,
        signature=b'RIFF',
        min_size=1024,
    ),
    FileSignature(
        name="MKV Video",
        extension="mkv",
        category=FileCategory.VIDEO,
        signature=b'\x1A\x45\xDF\xA3',
        min_size=1024,
    ),
    FileSignature(
        name="FLV Video",
        extension="flv",
        category=FileCategory.VIDEO,
        signature=b'FLV',
        min_size=1024,
    ),
    FileSignature(
        name="MOV Video",
        extension="mov",
        category=FileCategory.VIDEO,
        signature=b'\x00\x00\x00\x14ftyp',
        min_size=1024,
    ),
    FileSignature(
        name="WebM Video",
        extension="webm",
        category=FileCategory.VIDEO,
        signature=b'\x1A\x45\xDF\xA3',
        min_size=1024,
    ),
    
    # Executables
    FileSignature(
        name="Windows Executable",
        extension="exe",
        category=FileCategory.EXECUTABLE,
        signature=b'MZ',
        min_size=1024,
    ),
    FileSignature(
        name="ELF Executable",
        extension="elf",
        category=FileCategory.EXECUTABLE,
        signature=b'\x7FELF',
        min_size=1024,
    ),
    FileSignature(
        name="Mach-O Executable",
        extension="macho",
        category=FileCategory.EXECUTABLE,
        signature=b'\xFE\xED\xFA\xCE',
        min_size=1024,
    ),
    
    # Data
    FileSignature(
        name="Outlook PST",
        extension="pst",
        category=FileCategory.DATA,
        signature=b'!BDN',
        min_size=1024,
    ),
    FileSignature(
        name="SQLite Database",
        extension="db",
        category=FileCategory.DATA,
        signature=b'SQLite format 3\x00',
        min_size=1024,
    ),
    FileSignature(
        name="Windows Registry Hive",
        extension="reg",
        category=FileCategory.DATA,
        signature=b'reg',
        offset=0,
        min_size=1024,
    ),
]


class SignatureDatabase:
    """Lightweight compatibility wrapper for the built-in signature catalog."""

    _builtin_signatures: ClassVar[List[FileSignature]] = COMMON_SIGNATURES

    def __init__(self, signatures: Optional[List[FileSignature]] = None) -> None:
        self._signatures = list(signatures or self._builtin_signatures)

    @classmethod
    def get_all_signatures(cls) -> List[FileSignature]:
        """Return a copy of the built-in signatures."""
        return list(cls._builtin_signatures)

    def get_signatures_by_extension(self, extension: str) -> List[FileSignature]:
        """Get signatures matching the requested extension."""
        ext_lower = extension.lower()
        return [sig for sig in self._signatures if sig.extension.lower() == ext_lower]

    def get_signatures_by_category(self, category: FileCategory) -> List[FileSignature]:
        """Get signatures matching the requested category."""
        return [sig for sig in self._signatures if sig.category == category]


def get_signature_by_extension(extension: str) -> Optional[FileSignature]:
    """Get signature by file extension."""
    ext_lower = extension.lower()
    for sig in COMMON_SIGNATURES:
        if sig.extension.lower() == ext_lower:
            return sig
    return None


def get_signatures_by_category(category: FileCategory) -> List[FileSignature]:
    """Get all signatures for a category."""
    return [sig for sig in COMMON_SIGNATURES if sig.category == category]


def find_matching_signature(data: bytes) -> Optional[FileSignature]:
    """
    Find first matching signature in data.
    
    Args:
        data: Data buffer to check
        
    Returns:
        First matching signature or None
    """
    for sig in COMMON_SIGNATURES:
        if sig.matches(data, sig.offset):
            return sig
    return None