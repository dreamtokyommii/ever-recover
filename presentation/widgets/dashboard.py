"""Dashboard widget showing scan progress and statistics."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QFrame, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer
from presentation.widgets.circular_progress import CircularProgress
from typing import Optional, Dict, Any
import logging

from core.models.scan_result import ScanResult, ScanStatistics

logger = logging.getLogger(__name__)


class DashboardWidget(QWidget):
    """Dashboard showing scan progress and statistics."""
    
    def __init__(self):
        super().__init__()
        self._scan_result: Optional[ScanResult] = None
        self._is_scanning = False
        self._progress = 0
        self._current_file = ""
        self._init_ui()
    
    def _init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("Scan Dashboard")
        header.setObjectName("heading")
        layout.addWidget(header)
        
        # Main stats grid
        self.stats_frame = QFrame()
        self.stats_frame.setObjectName("card")
        stats_layout = QGridLayout(self.stats_frame)
        stats_layout.setSpacing(16)
        
        # Total files
        self._create_stat_widget(
            stats_layout, 0, 0, "Total Files", "0", "total_files", ""
        )
        
        # Deleted files
        self._create_stat_widget(
            stats_layout, 0, 1, "Deleted Files", "0", "deleted_files", ""
        )
        
        # Recoverable
        self._create_stat_widget(
            stats_layout, 1, 0, "Recoverable", "0", "recoverable", ""
        )
        
        # Total size
        self._create_stat_widget(
            stats_layout, 1, 1, "Total Size", "0 B", "total_size", ""
        )
        
        layout.addWidget(self.stats_frame)
        
        # Progress section
        self.progress_frame = QFrame()
        self.progress_frame.setObjectName("card")
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setSpacing(12)
        
        # Progress label
        self.progress_label = QLabel("Ready to scan")
        self.progress_label.setObjectName("subheading")
        progress_layout.addWidget(self.progress_label)
        
        # Circular progress
        self.circular = CircularProgress()
        progress_layout.addWidget(self.circular)
        
        # Current file
        self.current_file_label = QLabel("No file in progress")
        self.current_file_label.setObjectName("status")
        self.current_file_label.setWordWrap(True)
        progress_layout.addWidget(self.current_file_label)
        
        layout.addWidget(self.progress_frame)
        
        # Additional stats
        self.extra_stats = QFrame()
        self.extra_stats.setObjectName("card")
        extra_layout = QGridLayout(self.extra_stats)
        extra_layout.setSpacing(16)
        
        self._create_stat_widget(
            extra_layout, 0, 0, "By Category", "0", "by_category", ""
        )
        self._create_stat_widget(
            extra_layout, 0, 1, "By Confidence", "0", "by_confidence", ""
        )
        self._create_stat_widget(
            extra_layout, 1, 0, "Fragmented", "0", "fragmented", ""
        )
        self._create_stat_widget(
            extra_layout, 1, 1, "Scan Errors", "0", "errors", ""
        )
        
        layout.addWidget(self.extra_stats)
        
        # Add stretch to push everything up
        layout.addStretch()
    
    def _create_stat_widget(self, layout: QGridLayout, row: int, col: int,
                           title: str, value: str, obj_name: str, icon: str) -> QLabel:
        """Create a statistic widget."""
        # Title
        title_label = QLabel(f"{icon} {title}")
        title_label.setObjectName("status")
        layout.addWidget(title_label, row, col, 1, 1, Qt.AlignmentFlag.AlignTop)
        
        # Value
        value_label = QLabel(value)
        value_label.setObjectName("large")
        value_label.setObjectName(f"stat_{obj_name}")
        layout.addWidget(value_label, row + 1, col, 1, 1, Qt.AlignmentFlag.AlignLeft)
        
        return value_label
    
    def update_progress(self, progress: float, current_file: str = "") -> None:
        """
        Update scan progress.
        
        Args:
            progress: Progress percentage (0-100)
            current_file: Currently processing file
        """
        self._progress = progress
        self._current_file = current_file
        
        # update circular widget
        self.circular.setValue(int(progress))
        if progress < 100:
            self.progress_label.setText(f"Scanning... {progress:.1f}%")
        else:
            self.progress_label.setText("Scan Complete")
        
        self.current_file_label.setText(current_file if current_file else "No file in progress")
        
        # Update stylesheet
        self.circular.update()
    
    def update_statistics(self, stats: ScanStatistics) -> None:
        """Update statistics display."""
        # Update stat widgets
        self._update_stat_value("total_files", str(stats.total_files))
        self._update_stat_value("deleted_files", str(stats.deleted_files))
        self._update_stat_value("recoverable", str(len([f for f in [] if True])))  # Placeholder
        
        # Format size
        size_gb = stats.total_size / (1024 ** 3)
        self._update_stat_value("total_size", f"{size_gb:.2f} GB")
        
        # Update extra stats
        self._update_stat_value("by_category", str(len(stats.files_by_category)))
        self._update_stat_value("by_confidence", str(len(stats.files_by_confidence)))
        self._update_stat_value("fragmented", str(stats.fragmented_files))
        self._update_stat_value("errors", str(stats.scan_errors))

    # Backwards-compatible alias used by MainWindow
    def update_stats(self, total_files=None, deleted_files=None, recoverable=None, total_size=None):
        class _S:
            pass
        s = _S()
        s.total_files = total_files or 0
        s.deleted_files = deleted_files or 0
        s.total_size = 0
        s.files_by_category = {}
        s.files_by_confidence = {}
        s.fragmented_files = 0
        s.scan_errors = 0
        # If total_size provided as string, attempt to parse numeric part
        try:
            if isinstance(total_size, str):
                # leave sizing to MainWindow (string)
                self._update_stat_value('total_size', total_size)
            elif total_size is not None:
                self._update_stat_value('total_size', str(total_size))
        except Exception:
            pass
        self._update_stat_value('total_files', str(total_files or 0))
        self._update_stat_value('deleted_files', str(deleted_files or 0))
        self._update_stat_value('recoverable', str(recoverable or 0))
    
    def _update_stat_value(self, obj_name: str, value: str) -> None:
        """Update a statistic value."""
        for i in range(self.stats_frame.layout().count()):
            widget = self.stats_frame.layout().itemAt(i).widget()
            if widget and hasattr(widget, 'objectName'):
                if f"stat_{obj_name}" in widget.objectName() or widget.objectName() == obj_name:
                    widget.setText(value)
                    break
    
    def set_scanning(self, is_scanning: bool) -> None:
        """Set scanning state."""
        self._is_scanning = is_scanning
        if is_scanning:
            self.progress_label.setText("Scanning...")
            self.progress_bar.setFormat("%p%")
        else:
            self.progress_label.setText("Ready")
            self.progress_bar.setFormat("")
    
    def reset(self) -> None:
        """Reset dashboard to initial state."""
        self._scan_result = None
        self._is_scanning = False
        self._progress = 0
        self._current_file = ""
        
        self.progress_bar.setValue(0)
        self.progress_label.setText("Ready to scan")
        self.current_file_label.setText("No file in progress")
        
        # Reset stats
        self._update_stat_value("total_files", "0")
        self._update_stat_value("deleted_files", "0")
        self._update_stat_value("recoverable", "0")
        self._update_stat_value("total_size", "0 B")