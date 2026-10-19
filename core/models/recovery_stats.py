"""Recovery statistics and audit tracking."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import List, Dict, Optional, Any
from pathlib import Path


class RecoveryStatus(Enum):
    """Status of file recovery operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
    VERIFICATION_FAILED = "verification_failed"


@dataclass
class RecoveryOperation:
    """Tracks a single file recovery operation."""
    file_id: str
    source_path: str
    destination_path: Path
    start_time: datetime
    status: RecoveryStatus
    bytes_recovered: int = 0
    bytes_expected: int = 0
    error_message: Optional[str] = None
    verification_passed: bool = False
    hash_matches: bool = False
    metadata_preserved: bool = False
    duration: float = 0.0
    
    @property
    def recovery_percentage(self) -> float:
        """Calculate recovery completion percentage."""
        if self.bytes_expected == 0:
            return 0.0
        return (self.bytes_recovered / self.bytes_expected) * 100
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'file_id': self.file_id,
            'source_path': self.source_path,
            'destination_path': str(self.destination_path),
            'start_time': self.start_time.isoformat(),
            'status': self.status.value,
            'bytes_recovered': self.bytes_recovered,
            'bytes_expected': self.bytes_expected,
            'recovery_percentage': self.recovery_percentage,
            'error_message': self.error_message,
            'verification_passed': self.verification_passed,
            'hash_matches': self.hash_matches,
            'metadata_preserved': self.metadata_preserved,
            'duration': self.duration,
        }


@dataclass
class RecoverySession:
    """
    Tracks a complete recovery session with audit information.
    
    Attributes:
        session_id: Unique session identifier
        scan_id: Associated scan ID
        output_directory: Destination directory for recovered files
        start_time: Session start timestamp
        end_time: Session end timestamp
        operations: Individual recovery operations
        total_bytes_expected: Total bytes to recover
        total_bytes_recovered: Total bytes actually recovered
        preserve_structure: Whether to maintain directory structure
        preserve_timestamps: Whether to preserve file timestamps
        calculate_hashes: Whether to calculate SHA-256 hashes
        verify_integrity: Whether to verify recovered files
        audit_log: Detailed audit trail
        user_notes: User-provided notes/case information
    """
    session_id: str
    scan_id: str
    output_directory: Path
    start_time: datetime
    operations: List[RecoveryOperation] = field(default_factory=list)
    end_time: Optional[datetime] = None
    total_bytes_expected: int = 0
    total_bytes_recovered: int = 0
    preserve_structure: bool = True
    preserve_timestamps: bool = True
    calculate_hashes: bool = True
    verify_integrity: bool = True
    audit_log: List[Dict[str, Any]] = field(default_factory=list)
    user_notes: Optional[str] = None
    
    @property
    def duration(self) -> float:
        """Get session duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now() - self.start_time).total_seconds()
    
    @property
    def success_count(self) -> int:
        """Count successful recoveries."""
        return sum(1 for op in self.operations if op.status == RecoveryStatus.SUCCESS)
    
    @property
    def failed_count(self) -> int:
        """Count failed recoveries."""
        return sum(1 for op in self.operations if op.status in [RecoveryStatus.FAILED, RecoveryStatus.VERIFICATION_FAILED])
    
    @property
    def partial_count(self) -> int:
        """Count partial recoveries."""
        return sum(1 for op in self.operations if op.status == RecoveryStatus.PARTIAL)
    
    @property
    def overall_success_rate(self) -> float:
        """Calculate overall success rate."""
        if not self.operations:
            return 0.0
        return (self.success_count / len(self.operations)) * 100
    
    @property
    def data_recovery_rate(self) -> float:
        """Calculate data recovery rate by bytes."""
        if self.total_bytes_expected == 0:
            return 0.0
        return (self.total_bytes_recovered / self.total_bytes_expected) * 100
    
    def add_operation(self, operation: RecoveryOperation) -> None:
        """Add recovery operation and update totals."""
        self.operations.append(operation)
        self.total_bytes_expected += operation.bytes_expected
        self.total_bytes_recovered += operation.bytes_recovered
    
    def add_audit_entry(self, event_type: str, details: Dict[str, Any]) -> None:
        """Add entry to audit log."""
        self.audit_log.append({
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'details': details,
        })
    
    def to_report_dict(self) -> dict:
        """Generate report dictionary."""
        return {
            'session_id': self.session_id,
            'scan_id': self.scan_id,
            'output_directory': str(self.output_directory),
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': self.duration,
            'total_files': len(self.operations),
            'successful_recoveries': self.success_count,
            'failed_recoveries': self.failed_count,
            'partial_recoveries': self.partial_count,
            'total_bytes_expected': self.total_bytes_expected,
            'total_bytes_recovered': self.total_bytes_recovered,
            'overall_success_rate': self.overall_success_rate,
            'data_recovery_rate': self.data_recovery_rate,
            'operations': [op.to_dict() for op in self.operations],
            'audit_log': self.audit_log,
            'user_notes': self.user_notes,
        }