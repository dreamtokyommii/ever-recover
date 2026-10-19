"""AI-powered file classification."""

import logging
import re
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum, auto
import math

from core.models.file_entry import FileEntry, FileCategory

logger = logging.getLogger(__name__)


class ContentType(Enum):
    """Content type detected by analysis."""
    TEXT = auto()
    BINARY = auto()
    ENCRYPTED = auto()
    COMPRESSED = auto()
    MIXED = auto()


@dataclass
class ClassificationResult:
    """Result of file classification."""
    predicted_category: FileCategory
    confidence: float  # 0-1
    content_type: ContentType
    is_corrupted: bool
    corruption_score: float  # 0-1
    language: Optional[str] = None  # For text files
    encoding: Optional[str] = None  # For text files
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class FileClassifier:
    """
    AI-powered file classifier.
    
    Uses content analysis, entropy calculation, and pattern matching
    to classify files beyond simple signature matching.
    """
    
    # Common text encodings markers
    ENCODING_MARKERS = {
        b'\xEF\xBB\xBF': 'UTF-8 BOM',
        b'\xFF\xFE': 'UTF-16 LE',
        b'\xFE\xFF': 'UTF-16 BE',
        b'\x00\x00\xFE\xFF': 'UTF-32 BE',
    }
    
    # Common file type patterns
    PATTERNS = {
        'xml': b'<\\?xml',
        'html': b'<!DOCTYPE html>|<html',
        'json': b'^\\s*[{\\[]',
        'csv': b'^[^\\n]+,[^\\n]+',
        'markdown': b'^# |^\\*\\*|^\\[',
        'email': b'^From: |^To: |^Subject: |^Date: ',
        'log': b'^\\d{4}-\\d{2}-\\d{2}|^\\[\\d{4}',
    }
    
    # Language keywords
    LANGUAGE_KEYWORDS = {
        'english': {b'the', b'and', b'for', b'with', b'that', b'have', b'this'},
        'spanish': {b'que', b'de', b'la', b'el', b'en', b'con', b'una'},
        'french': {b'le', b'de', b'et', b'un', b'il', b'est'},
        'german': {b'der', b'die', b'und', b'ist', b'in', b'den', b'von'},
        'chinese': {b'\xe7\x9a\x84', b'\xe4\xba\x86', b'\xe5\x9c\xa8'},  # UTF-8 encoded: 的，了，在
    }
    
    def __init__(self):
        self._compiled_patterns = {}
        for name, pattern in self.PATTERNS.items():
            self._compiled_patterns[name] = re.compile(pattern)
        
        logger.info("File classifier initialized")
    
    def classify(self, file_entry: FileEntry, sample_data: Optional[bytes] = None) -> ClassificationResult:
        """
        Classify a file.
        
        Args:
            file_entry: File entry to classify
            sample_data: Sample of file content (first 8KB recommended)
            
        Returns:
            Classification result
        """
        # If no sample data, use extension-based classification
        if not sample_data:
            return self._classify_by_extension(file_entry)
        
        # Analyze content
        content_type = self._analyze_content_type(sample_data)
        entropy = self._calculate_entropy(sample_data)
        
        # Check for corruption
        is_corrupted, corruption_score = self._detect_corruption(sample_data, file_entry)
        
        # Predict category
        predicted_category, confidence = self._predict_category(
            sample_data, file_entry, content_type, entropy
        )
        
        # Detect encoding and language for text files
        language = None
        encoding = None
        if content_type == ContentType.TEXT:
            encoding = self._detect_encoding(sample_data)
            language = self._detect_language(sample_data)
        
        return ClassificationResult(
            predicted_category=predicted_category,
            confidence=confidence,
            content_type=content_type,
            is_corrupted=is_corrupted,
            corruption_score=corruption_score,
            language=language,
            encoding=encoding,
            metadata={
                'entropy': entropy,
                'content_type': content_type.name,
            }
        )
    
    def _classify_by_extension(self, file_entry: FileEntry) -> ClassificationResult:
        """Classify based on extension and filename."""
        # Map extensions to categories
        extension_map = {
            'jpg': (FileCategory.IMAGE, 0.8),
            'jpeg': (FileCategory.IMAGE, 0.8),
            'png': (FileCategory.IMAGE, 0.9),
            'gif': (FileCategory.IMAGE, 0.8),
            'bmp': (FileCategory.IMAGE, 0.7),
            'mp4': (FileCategory.VIDEO, 0.9),
            'avi': (FileCategory.VIDEO, 0.8),
            'mkv': (FileCategory.VIDEO, 0.9),
            'mov': (FileCategory.VIDEO, 0.8),
            'mp3': (FileCategory.AUDIO, 0.9),
            'wav': (FileCategory.AUDIO, 0.8),
            'flac': (FileCategory.AUDIO, 0.9),
            'aac': (FileCategory.AUDIO, 0.8),
            'doc': (FileCategory.DOCUMENT, 0.8),
            'docx': (FileCategory.DOCUMENT, 0.9),
            'pdf': (FileCategory.DOCUMENT, 0.95),
            'txt': (FileCategory.DOCUMENT, 0.7),
            'rtf': (FileCategory.DOCUMENT, 0.8),
            'xls': (FileCategory.DOCUMENT, 0.8),
            'xlsx': (FileCategory.DOCUMENT, 0.9),
            'ppt': (FileCategory.DOCUMENT, 0.8),
            'pptx': (FileCategory.DOCUMENT, 0.9),
            'zip': (FileCategory.ARCHIVE, 0.95),
            'rar': (FileCategory.ARCHIVE, 0.95),
            '7z': (FileCategory.ARCHIVE, 0.95),
            'tar': (FileCategory.ARCHIVE, 0.9),
            'gz': (FileCategory.ARCHIVE, 0.9),
            'exe': (FileCategory.EXECUTABLE, 0.95),
            'dll': (FileCategory.EXECUTABLE, 0.95),
            'so': (FileCategory.EXECUTABLE, 0.9),
            'dylib': (FileCategory.EXECUTABLE, 0.9),
        }
        
        ext_lower = file_entry.extension.lower()
        category, confidence = extension_map.get(ext_lower, (FileCategory.OTHER, 0.5))
        
        return ClassificationResult(
            predicted_category=category,
            confidence=confidence,
            content_type=ContentType.BINARY,
            is_corrupted=False,
            corruption_score=0.0,
            metadata={'method': 'extension'}
        )
    
    def _analyze_content_type(self, data: bytes) -> ContentType:
        """Analyze content type (text, binary, encrypted, etc.)."""
        if not data:
            return ContentType.BINARY
        
        # Check for text indicators
        printable_ratio = sum(1 for b in data if 32 <= b <= 126 or b in (9, 10, 13)) / len(data)
        
        if printable_ratio > 0.9:
            return ContentType.TEXT
        elif printable_ratio > 0.7:
            return ContentType.MIXED
        
        # Check for compression/encryption indicators
        entropy = self._calculate_entropy(data)
        
        if entropy > 7.5:
            return ContentType.ENCRYPTED
        elif entropy > 6.5:
            return ContentType.COMPRESSED
        else:
            return ContentType.BINARY
    
    def _calculate_entropy(self, data: bytes) -> float:
        """
        Calculate Shannon entropy of data.
        
        Higher entropy = more random/encrypted/compressed
        Lower entropy = more structured/predictable
        
        Returns:
            Entropy in bits (0-8)
        """
        if not data:
            return 0.0
        
        # Count byte frequencies
        freq = [0] * 256
        for byte in data:
            freq[byte] += 1
        
        # Calculate entropy
        entropy = 0.0
        length = len(data)
        for count in freq:
            if count > 0:
                p = count / length
                entropy -= p * math.log2(p)
        
        return entropy
    
    def _detect_corruption(
        self,
        data: bytes,
        file_entry: FileEntry,
    ) -> Tuple[bool, float]:
        """
        Detect file corruption.
        
        Returns:
            (is_corrupted, corruption_score 0-1)
        """
        if not data or len(data) < 16:
            return True, 0.9
        
        corruption_indicators = 0
        total_checks = 0
        
        # Check 1: Too many null bytes in header
        if len(data) > 64:
            header = data[:64]
            null_ratio = header.count(0) / len(header)
            if null_ratio > 0.95:
                corruption_indicators += 1
            total_checks += 1
        
        # Check 2: High entropy in expected structured data
        if file_entry.extension.lower() in ['doc', 'docx', 'xls', 'xlsx', 'pdf']:
            entropy = self._calculate_entropy(data[:1024])
            if entropy > 7.8:  # Very high for document
                corruption_indicators += 1
            total_checks += 1
        
        # Check 3: Truncated files (all zeros at end)
        if len(data) > 512:
            tail = data[-512:]
            if tail == b'\x00' * 512:
                corruption_indicators += 1
            total_checks += 1
        
        # Check 4: Repeated patterns (data corruption)
        if len(data) > 1024:
            # Split into chunks and check for repetition
            chunk_size = 512
            chunks = [data[i:i+chunk_size] for i in range(0, min(4096, len(data)), chunk_size)]
            if len(chunks) >= 2:
                if chunks[0] == chunks[1] == chunks[2]:
                    corruption_indicators += 1
                total_checks += 1
        
        # Check 5: Invalid characters in text files
        if file_entry.extension.lower() in ['txt', 'log', 'csv', 'xml', 'json']:
            try:
                text = data[:1024].decode('utf-8')
                # Check for replacement characters
                if '\ufffd' in text:
                    corruption_indicators += 1
            except:
                pass
            total_checks += 1
        
        corruption_score = corruption_indicators / max(total_checks, 1)
        is_corrupted = corruption_score >= 0.4
        
        return is_corrupted, corruption_score
    
    def _predict_category(
        self,
        data: bytes,
        file_entry: FileEntry,
        content_type: ContentType,
        entropy: float,
    ) -> Tuple[FileCategory, float]:
        """Predict file category from content."""
        scores = {cat: 0.0 for cat in FileCategory}
        
        # Signature-based hints
        if data[:4] == b'%PDF':
            scores[FileCategory.DOCUMENT] += 0.9
        elif data[:2] == b'PK':
            scores[FileCategory.ARCHIVE] += 0.5
            scores[FileCategory.DOCUMENT] += 0.3  # Could be docx, xlsx, pptx
        elif data[:4] == b'\x89PNG':
            scores[FileCategory.IMAGE] += 0.95
        elif data[:3] == b'\xFF\xD8\xFF':
            scores[FileCategory.IMAGE] += 0.95
        elif data[:4] == b'RIFF':
            if b'WAVE' in data[:24]:
                scores[FileCategory.AUDIO] += 0.9
            elif b'AVI ' in data[:24]:
                scores[FileCategory.VIDEO] += 0.9
        elif data[:4] == b'fLaC':
            scores[FileCategory.AUDIO] += 0.95
        elif data[:4] == b'ID3':
            scores[FileCategory.AUDIO] += 0.9
        
        # Content analysis
        if content_type == ContentType.TEXT:
            # Check for specific text patterns
            text_sample = data[:1024]
            
            if b'<html' in text_sample.lower() or b'<!doctype' in text_sample.lower():
                scores[FileCategory.DOCUMENT] += 0.8
            elif b'{\\rtf' in text_sample:
                scores[FileCategory.DOCUMENT] += 0.9
            elif b'PK' in text_sample[:2]:
                scores[FileCategory.ARCHIVE] += 0.7
        
        elif content_type == ContentType.BINARY:
            # Check header patterns
            if entropy < 4.0:
                # Low entropy = likely structured data
                if file_entry.extension.lower() in ['db', 'sqlite', 'mdb']:
                    scores[FileCategory.DATA] += 0.8
            
            elif entropy > 7.0:
                # High entropy = compressed/encrypted
                scores[FileCategory.ARCHIVE] += 0.4
        
        # Extension agreement
        ext_category = self._classify_by_extension(file_entry).predicted_category
        if scores[ext_category] > 0:
            scores[ext_category] += 0.1  # Boost if extension agrees
        
        # Find best category
        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]
        
        # Normalize confidence to 0-1
        confidence = min(best_score, 1.0)
        
        return best_category, confidence
    
    def _detect_encoding(self, data: bytes) -> Optional[str]:
        """Detect text encoding."""
        for marker, encoding in self.ENCODING_MARKERS.items():
            if data.startswith(marker):
                return encoding
        return 'UTF-8'  # Default
    
    def _detect_language(self, data: bytes) -> Optional[str]:
        """Detect text language from keywords."""
        if len(data) < 100:
            return None
        
        # Convert to lowercase for matching
        sample = data[:2000].lower()
        
        scores = {}
        for language, keywords in self.LANGUAGE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in sample)
            scores[language] = score
        
        if not scores or max(scores.values()) == 0:
            return None
        
        best_language = max(scores, key=scores.get)
        if scores[best_language] >= 2:  # At least 2 keyword matches
            return best_language
        
        return None


class SmartRecoverySorter:
    """Smart file recovery prioritization."""
    
    def __init__(self, classifier: Optional[FileClassifier] = None):
        self.classifier = classifier or FileClassifier()
        logger.info("Smart recovery sorter initialized")
    
    def prioritize(
        self,
        files: List[FileEntry],
        top_n: Optional[int] = None,
    ) -> List[FileEntry]:
        """
        Prioritize files for recovery.
        
        Args:
            files: Files to prioritize
            top_n: Return only top N files
            
        Returns:
            Files sorted by priority
        """
        # Score each file
        scored_files = []
        for file_entry in files:
            score = self._score_file(file_entry)
            scored_files.append((score, file_entry))
        
        # Sort by score (descending)
        scored_files.sort(key=lambda x: x[0], reverse=True)
        
        # Extract files
        prioritized = [f for _, f in scored_files]
        
        if top_n:
            return prioritized[:top_n]
        
        return prioritized
    
    def _score_file(self, file_entry: FileEntry) -> float:
        """Score file for recovery priority."""
        score = 0.0
        
        # Factor 1: Confidence (0-40 points)
        conf_map = {
            'EXCELLENT': 40,
            'HIGH': 30,
            'MEDIUM': 20,
            'LOW': 10,
        }
        score += conf_map.get(file_entry.recovery_confidence.name, 0)
        
        # Factor 2: File type (0-20 points)
        type_priority = {
            FileCategory.DOCUMENT: 20,
            FileCategory.IMAGE: 18,
            FileCategory.VIDEO: 16,
            FileCategory.AUDIO: 14,
            FileCategory.ARCHIVE: 12,
            FileCategory.DATA: 10,
            FileCategory.EXECUTABLE: 8,
            FileCategory.OTHER: 5,
        }
        score += type_priority.get(file_entry.file_category, 5)
        
        # Factor 3: File size (0-15 points)
        # Prefer medium-sized files (not too small, not too large)
        size_mb = file_entry.file_size / (1024 * 1024)
        if 0.1 <= size_mb <= 100:
            score += 15
        elif 0.01 <= size_mb <= 500:
            score += 10
        else:
            score += 5
        
        # Factor 4: Deletion status (0-15 points)
        # Prioritize deleted files
        from core.models.file_entry import FileStatus
        if file_entry.status == FileStatus.DELETED:
            score += 15
        
        # Factor 5: Timestamp recency (0-10 points)
        if file_entry.modified_time:
            import datetime
            now = datetime.datetime.now()
            days_old = (now - file_entry.modified_time).days
            if days_old < 7:
                score += 10
            elif days_old < 30:
                score += 7
            elif days_old < 365:
                score += 4
        
        return score