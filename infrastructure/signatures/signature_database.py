"""File signature database for file carving operations."""

import json
from pathlib import Path
from typing import List, Dict, Set, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

from core.models.file_entry import FileCategory
from core.interfaces.carving_engine import FileSignature

logger = logging.getLogger(__name__)


@dataclass
class SignatureEntry:
    """Internal signature entry format."""
    name: str
    extension: str
    category: str
    offset: int
    signature: str  # Hex string
    signature_mask: Optional[str] = None  # Hex mask for variable bytes
    min_size: int = 0
    max_size: int = 0  # 0 = unlimited
    footer_signature: Optional[str] = None  # Hex string
    footer_offset_relative: bool = True  # From end of file
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    priority: int = 50  # 0-100, higher = check first
    description: str = ""
    references: List[str] = field(default_factory=list)


class SignatureDatabase:
    """
    File signature database manager.
    
    Provides:
    - Built-in signatures for common file types
    - Load/save custom signature databases
    - Signature validation and indexing
    - Fast signature lookup
    
    File Format (JSON):
    {
        "version": "1.0",
        "signatures": [
            {
                "name": "JPEG Image",
                "extension": "jpg",
                "category": "IMAGE",
                "offset": 0,
                "signature": "FFD8FF",
                "min_size": 1024,
                "max_size": 0,
                "footer_signature": "FFD9",
                "priority": 80,
                "description": "JPEG image file"
            }
        ]
    }
    """
    
    BUILTIN_SIGNATURES = [
        # ========== IMAGES ==========
        SignatureEntry(
            name="JPEG Image",
            extension="jpg",
            category="IMAGE",
            offset=0,
            signature="FFD8FF",
            min_size=1024,
            max_size=0,
            footer_signature="FFD9",
            footer_offset_relative=True,
            priority=90,
            description="Joint Photographic Experts Group image",
            references=["https://www.file-recovery.com/jpg-format.htm"]
        ),
        SignatureEntry(
            name="JPEG Image (JIF)",
            extension="jpg",
            category="IMAGE",
            offset=0,
            signature="FFD8FFE0",
            min_size=1024,
            max_size=0,
            footer_signature="FFD9",
            priority=90,
            description="JPEG Image Interchange Format"
        ),
        SignatureEntry(
            name="JPEG Image (EXIF)",
            extension="jpg",
            category="IMAGE",
            offset=0,
            signature="FFD8FFE1",
            min_size=1024,
            max_size=0,
            footer_signature="FFD9",
            priority=90,
            description="JPEG with EXIF metadata"
        ),
        SignatureEntry(
            name="PNG Image",
            extension="png",
            category="IMAGE",
            offset=0,
            signature="89504E470D0A1A0A",
            min_size=1024,
            max_size=0,
            footer_signature="49454E44AE426082",
            priority=95,
            description="Portable Network Graphics image",
            validation_rules={"has_ihdr": True, "has_idat": True}
        ),
    ]
    
    def __init__(self, custom_db_path: Optional[Path] = None):
        """Initialize signature database."""
        self.signatures: Dict[str, List[FileSignature]] = {}
        self.extension_index: Dict[str, List[FileSignature]] = {}
        self.category_index: Dict[str, List[FileSignature]] = {}
        
        # Load built-in signatures
        self._load_builtin_signatures()
        
        # Load custom signatures if provided
        if custom_db_path and custom_db_path.exists():
            self.load_from_file(custom_db_path)
    
    def _load_builtin_signatures(self) -> None:
        """Load built-in file signatures."""
        for entry in self.BUILTIN_SIGNATURES:
            self._add_signature_from_entry(entry)
    
    def _add_signature_from_entry(self, entry: SignatureEntry) -> None:
        """Add a signature to the database."""
        file_sig = FileSignature(
            name=entry.name,
            extension=entry.extension,
            category=entry.category,
            offset=entry.offset,
            signature_hex=entry.signature,
            signature_mask=entry.signature_mask,
            min_size=entry.min_size,
            max_size=entry.max_size,
            footer_signature=entry.footer_signature,
            priority=entry.priority,
            description=entry.description
        )
        
        # Add to main signatures dict
        if entry.name not in self.signatures:
            self.signatures[entry.name] = []
        self.signatures[entry.name].append(file_sig)
        
        # Add to extension index
        if entry.extension not in self.extension_index:
            self.extension_index[entry.extension] = []
        self.extension_index[entry.extension].append(file_sig)
        
        # Add to category index
        if entry.category not in self.category_index:
            self.category_index[entry.category] = []
        self.category_index[entry.category].append(file_sig)
    
    def load_from_file(self, file_path: Path) -> None:
        """Load signatures from JSON file."""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            for sig_data in data.get('signatures', []):
                entry = SignatureEntry(**sig_data)
                self._add_signature_from_entry(entry)
            
            logger.info(f"Loaded {len(data.get('signatures', []))} custom signatures from {file_path}")
        except Exception as e:
            logger.error(f"Failed to load signatures from {file_path}: {e}")
    
    def save_to_file(self, file_path: Path) -> None:
        """Save signatures to JSON file."""
        try:
            all_signatures = []
            seen = set()
            
            for sig_list in self.signatures.values():
                for sig in sig_list:
                    sig_id = (sig.signature_hex, sig.extension)
                    if sig_id not in seen:
                        seen.add(sig_id)
                        all_signatures.append({
                            'name': sig.name,
                            'extension': sig.extension,
                            'category': sig.category,
                            'offset': sig.offset,
                            'signature': sig.signature_hex,
                            'min_size': sig.min_size,
                            'max_size': sig.max_size,
                            'footer_signature': sig.footer_signature,
                            'priority': sig.priority,
                            'description': sig.description
                        })
            
            data = {'version': '1.0', 'signatures': all_signatures}
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved {len(all_signatures)} signatures to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save signatures to {file_path}: {e}")
    
    def get_signatures_by_extension(self, ext: str) -> List[FileSignature]:
        """Get all signatures for a file extension."""
        return self.extension_index.get(ext.lower(), [])
    
    def get_signatures_by_category(self, category: str) -> List[FileSignature]:
        """Get all signatures for a category."""
        return self.category_index.get(category.upper(), [])
    
    def get_all_signatures(self) -> List[FileSignature]:
        """Get all signatures sorted by priority."""
        all_sigs = []
        seen = set()
        for sig_list in self.signatures.values():
            for sig in sig_list:
                sig_id = id(sig)
                if sig_id not in seen:
                    seen.add(sig_id)
                    all_sigs.append(sig)
        return sorted(all_sigs, key=lambda x: x.priority, reverse=True)
