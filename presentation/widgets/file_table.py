"""File results table widget."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QAbstractItemView,
    QHeaderView, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QLabel, QFrame, QFileDialog
)
from PyQt6.QtCore import Qt, QSortFilterProxyModel, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from typing import List, Optional, Dict, Any
import logging

from core.models.file_entry import FileEntry, FileCategory, RecoveryConfidence, FileStatus

logger = logging.getLogger(__name__)


class FileTableModel(QStandardItemModel):
    """Model for file table."""
    
    def __init__(self):
        super().__init__()
        self._headers = [
            "Status", "Filename", "Extension", "Size", 
            "Category", "Confidence", "Modified", "Path"
        ]
        self.setHorizontalHeaderLabels(self._headers)
    
    def load_files(self, files: List[FileEntry]) -> None:
        """Load files into model."""
        self.setRowCount(0)
        
        for file_entry in files:
            row = self.rowCount()
            self.insertRow(row)
            
            # Status icon
            status_item = QStandardItem(self._get_status_icon(file_entry.status))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, 0, status_item)
            
            # Filename
            self.setItem(row, 1, QStandardItem(file_entry.display_name))
            
            # Extension
            self.setItem(row, 2, QStandardItem(f".{file_entry.extension}"))
            
            # Size
            self.setItem(row, 3, QStandardItem(file_entry.display_size))
            
            # Category
            self.setItem(row, 4, QStandardItem(file_entry.file_category.name))
            
            # Confidence
            confidence_item = QStandardItem(f"{file_entry.confidence_percentage}%")
            confidence_item.setForeground(self._get_confidence_color(file_entry.confidence_percentage))
            self.setItem(row, 5, confidence_item)
            
            # Modified time
            modified = file_entry.modified_time.strftime("%Y-%m-%d %H:%M") if file_entry.modified_time else "N/A"
            self.setItem(row, 6, QStandardItem(modified))
            
            # Path
            self.setItem(row, 7, QStandardItem(file_entry.parent_directory or "/"))
            
            # Store file entry as data
            self.item(row, 0).setData(file_entry, Qt.ItemDataRole.UserRole)
    
    def _get_status_icon(self, status: FileStatus) -> str:
        """Get status icon."""
        if status == FileStatus.EXISTING:
            return "OK"
        elif status == FileStatus.DELETED:
            return "Deleted"
        elif status == FileStatus.FRAGMENTED:
            return "Fragmented"
        elif status == FileStatus.CORRUPTED:
            return "Corrupted"
        else:
            return "Unknown"
    
    def _get_confidence_color(self, confidence: int) -> Any:
        """Get color for confidence level."""
        # Would need QtGui.QColor here
        return None


class FileTableWidget(QWidget):
    """Widget displaying file results in a table."""
    
    file_selected = pyqtSignal(FileEntry)
    recover_selected = pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self._files: List[FileEntry] = []
        self._filtered_files: List[FileEntry] = []
        self._init_ui()
    
    def _init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("noBorder")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 12)
        
        # Search
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search files...")
        self.search_box.textChanged.connect(self._on_search_changed)
        toolbar_layout.addWidget(self.search_box, 1)
        
        # Category filter
        self.category_filter = QComboBox()
        self.category_filter.addItem("All Categories", None)
        self.category_filter.currentIndexChanged.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self.category_filter)
        
        # Confidence filter
        self.confidence_filter = QComboBox()
        self.confidence_filter.addItem("All Confidence", None)
        self.confidence_filter.addItem("High (80%+)", 80)
        self.confidence_filter.addItem("Medium (60%+)", 60)
        self.confidence_filter.addItem("Low (<60%)", 0)
        self.confidence_filter.currentIndexChanged.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self.confidence_filter)
        
        # Status filter
        self.status_filter = QCheckBox("Deleted Only")
        self.status_filter.stateChanged.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self.status_filter)
        
        layout.addWidget(toolbar)
        
        # Table view
        self.table_view = QTableView()
        self.table_model = FileTableModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.table_view.setModel(self.proxy_model)
        
        # Configure table
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_view.setSortingEnabled(True)
        # In PyQt6, use setEditTriggers with no flags to disable editing
        self.table_view.setEditTriggers(QAbstractItemView.EditTrigger(0))
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setShowGrid(True)
        
        # Set column widths
        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Status
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Filename
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Extension
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Size
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Category
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Confidence
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Modified
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Path
        
        self.table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table_view)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        select_all_btn = QPushButton("Select All")
        select_all_btn.setObjectName("secondary")
        select_all_btn.clicked.connect(self._on_select_all)
        btn_layout.addWidget(select_all_btn)
        
        btn_layout.addStretch()
        
        self.recover_btn = QPushButton("Recover Selected")
        self.recover_btn.setObjectName("success")
        self.recover_btn.setEnabled(False)
        self.recover_btn.clicked.connect(self._on_recover_clicked)
        btn_layout.addWidget(self.recover_btn)
        
        export_btn = QPushButton("Export Report")
        export_btn.setObjectName("secondary")
        export_btn.clicked.connect(self._on_export_clicked)
        btn_layout.addWidget(export_btn)
        
        layout.addLayout(btn_layout)
        
        # Status label
        self.status_label = QLabel("No files loaded")
        self.status_label.setObjectName("status")
        layout.addWidget(self.status_label)
    
    def load_files(self, files: List[FileEntry]) -> None:
        """Load files into table."""
        self._files = files
        self._filtered_files = files
        
        # Update category filter
        self.category_filter.clear()
        self.category_filter.addItem("All Categories", None)
        categories = set(f.file_category.name for f in files)
        for cat in sorted(categories):
            self.category_filter.addItem(cat, cat)
        
        # Load into model
        self.table_model.load_files(files)
        
        # Update status
        self.status_label.setText(f"{len(files)} files found")
    
    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self.proxy_model.setFilterFixedString(text)
        self.proxy_model.setFilterKeyColumn(1)  # Search filename
    
    def _on_filter_changed(self) -> None:
        """Handle filter change."""
        # Would implement filtering logic here
        pass
    
    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        selected = self.table_view.selectionModel().selectedRows()
        self.recover_btn.setEnabled(len(selected) > 0)
        
        if len(selected) == 1:
            row = selected[0].row()
            file_entry = self.table_model.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if file_entry:
                self.file_selected.emit(file_entry)
    
    def _on_select_all(self) -> None:
        """Select all files."""
        self.table_view.selectAll()
    
    def _on_recover_clicked(self) -> None:
        """Handle recover button click."""
        selected = self.table_view.selectionModel().selectedRows()
        files_to_recover = []
        
        for index in selected:
            row = index.row()
            file_entry = self.table_model.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if file_entry:
                files_to_recover.append(file_entry)
        
        if files_to_recover:
            self.recover_selected.emit(files_to_recover)
    
    def _on_export_clicked(self) -> None:
        """Handle export button click."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            "",
            "CSV Files (*.csv);;HTML Files (*.html);;All Files (*)"
        )
        
        if file_path:
            logger.info(f"Exporting report to: {file_path}")
            # Would implement export logic here