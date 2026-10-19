"""Signature file loader and validator."""

import json
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
import logging
from dataclasses import dataclass

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from core.models.file_entry import FileCategory
from core.interfaces.carving_engine import FileSignature
from .signature_database import SignatureDatabase

logger = logging.getLogger(__name__)


@dataclass
class SignatureLoadResult:
    """Result of loading signatures from file."""
    total_loaded: int
    valid_count: int
    invalid_count: int
    duplicate_count: int
    warnings: List[str]
    errors: List[str]


class SignatureLoader:
    """
    Loads and validates signature databases from various formats.
    
    Supported formats:
    - JSON (.json)
    - YAML (.yaml, .yml)
    - SigTool format (.sig)
    - File signature list (.txt)
    """
    
    def __init__(self, target_database: SignatureDatabase):
        """
        Initialize loader.
        
        Args:
            target_database: Database to load signatures into
        """
        self.database = target_database
        self._existing_signatures: Set[str] = set()
    
    def load_file(self, path: Path, format_hint: Optional[str] = None) -> SignatureLoadResult:
        """
        Load signatures from file.
        
        Args:
            path: Path to signature file
            format_hint: Optional format hint
            
        Returns:
            Load result with statistics
        """
        if not path.exists():
            return SignatureLoadResult(
                total_loaded=0,
                valid_count=0,
                invalid_count=0,
                duplicate_count=0,
                warnings=[],
                errors=[f"File not found: {path}"]
            )
        
        try:
            # Determine format
            if format_hint:
                file_format = format_hint.lower()
            else:
                file_format = path.suffix.lower()
            
            # Load based on format
            if file_format in ['.json']:
                signatures = self._load_from_json(path)
            elif file_format in ['.yaml', '.yml']:
                signatures = self._load_from_yaml(path)
            elif file_format in ['.sig']:
                signatures = self._load_from_sigtool(path)
            elif file_format in ['.txt']:
                signatures = self._load_from_text_list(path)
            else:
                # Try JSON first, then YAML
                try:
                    signatures = self._load_from_json(path)
                except:
                    signatures = self._load_from_yaml(path)
            
            # Validate and add signatures
            warnings = []
            errors = []
            valid_count = 0
            invalid_count = 0
            duplicate_count = 0
            
            for sig in signatures:
                # Validate
                if not self._validate_signature(sig, warnings, errors):
                    invalid_count += 1
                    continue
                
                # Check for duplicates
                sig_key = f"{sig.extension}:{sig.signature.hex()}"
                if sig_key in self._existing_signatures:
                    duplicate_count += 1
                    warnings.append(f"Duplicate signature: {sig.name}")
                    continue
                
                # Add to database
                self.database._add_signature_internal(sig)
                self._existing_signatures.add(sig_key)
                valid_count += 1
            
            return SignatureLoadResult(
                total_loaded=len(signatures),
                valid_count=valid_count,
                invalid_count=invalid_count,
                duplicate_count=duplicate_count,
                warnings=warnings,
                errors=errors
            )
            
        except Exception as e:
            logger.error(f"Failed to load signatures from {path}: {e}")
            return SignatureLoadResult(
                total_loaded=0,
                valid_count=0,
                invalid_count=0,
                duplicate_count=0,
                warnings=[],
                errors=[str(e)]
            )
    
    def _load_from_json(self, path: Path) -> List[FileSignature]:
        """Load from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        
        signatures = []
        sig_list = data.get('signatures', [data] if 'signature' in data else [])
        
        for sig_data in sig_list:
            sig = self._parse_signature_dict(sig_data)
            if sig:
                signatures.append(sig)
        
        return signatures
    
    def _load_from_yaml(self, path: Path) -> List[FileSignature]:
        """Load from YAML file."""
        if not HAS_YAML:
            logger.warning("PyYAML not installed, falling back to JSON parsing for %s", path)
            return self._load_from_json(path)
        
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        signatures = []
        sig_list = data.get('signatures', [data] if 'signature' in data else [])
        
        for sig_data in sig_list:
            sig = self._parse_signature_dict(sig_data)
            if sig:
                signatures.append(sig)
        
        return signatures
    
    def _load_from_sigtool(self, path: Path) -> List[FileSignature]:
        """Load from SigTool format (custom binary signature format)."""
        signatures = []
        
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split('|')
                if len(parts) >= 3:
                    try:
                        name = parts[0]
                        extension = parts[1]
                        signature_hex = parts[2]
                        offset = int(parts[3]) if len(parts) > 3 else 0
                        
                        sig = FileSignature(
                            name=name,
                            extension=extension,
                            category=FileCategory.OTHER,
                            offset=offset,
                            signature=bytes.fromhex(signature_hex.replace(' ', '').replace('-', '')),
                            min_size=0,
                            max_size=0,
                        )
                        signatures.append(sig)
                    except Exception as e:
                        logger.warning(f"Failed to parse SigTool line: {line} - {e}")
        
        return signatures
    
    def _load_from_text_list(self, path: Path) -> List[FileSignature]:
        """Load from simple text list (extension:hex_signature)."""
        signatures = []
        
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split(':')
                if len(parts) >= 2:
                    try:
                        extension = parts[0].strip()
                        signature_hex = parts[1].strip()
                        
                        sig = FileSignature(
                            name=f"Custom {extension.upper()}",
                            extension=extension,
                            category=FileCategory.OTHER,
                            offset=0,
                            signature=bytes.fromhex(signature_hex.replace(' ', '')),
                            min_size=0,
                            max_size=0,
                        )
                        signatures.append(sig)
                    except Exception as e:
                        logger.warning(f"Failed to parse text line: {line} - {e}")
        
        return signatures
    
    def _parse_signature_dict(self, data: dict) -> Optional[FileSignature]:
        """Parse signature from dictionary."""
        try:
            # Map category
            category_str = data.get('category', 'OTHER')
            try:
                category = FileCategory[category_str]
            except KeyError:
                category = FileCategory.OTHER
            
            # Parse signature
            sig_hex = data['signature'].replace(' ', '').replace('-', '')
            signature = bytes.fromhex(sig_hex)
            
            # Parse optional mask
            mask = None
            if data.get('signature_mask'):
                mask_hex = data['signature_mask'].replace(' ', '').replace('-', '')
                mask = bytes.fromhex(mask_hex)
            
            # Parse optional footer
            footer = None
            if data.get('footer_signature'):
                footer_hex = data['footer_signature'].replace(' ', '').replace('-', '')
                footer = bytes.fromhex(footer_hex)
            
            return FileSignature(
                name=data.get('name', f"Signature {data['extension']}"),
                extension=data['extension'],
                category=category,
                offset=data.get('offset', 0),
                signature=signature,
                signature_mask=mask,
                min_size=data.get('min_size', 0),
                max_size=data.get('max_size', 0),
                footer_signature=footer,
                footer_offset_relative=data.get('footer_offset_relative', True),
                validation_rules=data.get('validation_rules', {}),
                priority=data.get('priority', 50),
            )
            
        except Exception as e:
            logger.warning(f"Failed to parse signature dict: {e}")
            return None
    
    def _validate_signature(self, sig: FileSignature, 
                           warnings: List[str], 
                           errors: List[str]) -> bool:
        """
        Validate signature.
        
        Returns:
            True if valid
        """
        is_valid = True
        
        # Check required fields
        if not sig.name:
            errors.append("Missing signature name")
            is_valid = False
        
        if not sig.extension:
            errors.append("Missing file extension")
            is_valid = False
        
        if not sig.signature:
            errors.append(f"Missing signature bytes for {sig.name}")
            is_valid = False
        
        # Check signature length
        if len(sig.signature) < 3:
            warnings.append(f"Signature {sig.name} is very short (may produce false positives)")
        
        # Check size constraints
        if sig.max_size > 0 and sig.max_size < sig.min_size:
            errors.append(f"Invalid size range for {sig.name}: max < min")
            is_valid = False
        
        # Check offset
        if sig.offset < 0:
            errors.append(f"Negative offset for {sig.name}")
            is_valid = False
        
        return is_valid
    
    def export_signatures(self, path: Path, 
                         format: str = 'json',
                         filter_extensions: Optional[Set[str]] = None,
                         filter_categories: Optional[Set[FileCategory]] = None) -> int:
        """
        Export signatures to file.
        
        Args:
            path: Output path
            format: Output format (json/yaml)
            filter_extensions: Optional extension filter
            filter_categories: Optional category filter
            
        Returns:
            Number of signatures exported
        """
        signatures = self.database.get_all_signatures()
        
        # Apply filters
        if filter_extensions:
            signatures = [s for s in signatures if s.extension.lower() in filter_extensions]
        
        if filter_categories:
            signatures = [s for s in signatures if s.category in filter_categories]
        
        # Prepare data
        data = {
            'version': '1.0',
            'signatures': [self.database._serialize_signature(s) for s in signatures]
        }
        
        # Write file
        with open(path, 'w') as f:
            if format.lower() == 'yaml':
                if HAS_YAML:
                    yaml.dump(data, f, default_flow_style=False)
                else:
                    logger.warning("PyYAML not installed, saving as JSON instead")
                    json.dump(data, f, indent=2)
            else:
                json.dump(data, f, indent=2)
        
        logger.info(f"Exported {len(signatures)} signatures to {path}")
        return len(signatures)