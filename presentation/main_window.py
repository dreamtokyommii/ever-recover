"""Main application window for Ever Recover.

This file implements a polished dashboard layout tuned to match the
provided mockup: narrow navigator on the left, large central cards,
file results table and a prominent preview pane on the right.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QLabel, QPushButton, QListWidget, QListWidgetItem, QStackedWidget,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QLineEdit,
    QComboBox, QProgressBar, QSplitter, QStatusBar, QMessageBox, QFileDialog,
    QSizePolicy, QScrollArea, QToolButton
)
from PyQt6.QtGui import QAction, QPixmap, QIcon
import os
import csv
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize

import logging
import platform
import random
from datetime import datetime

from .styles.dark_theme import get_dark_theme_stylesheet
from presentation.widgets.dashboard import DashboardWidget
from presentation.widgets.circular_progress import CircularProgress
from pathlib import Path

logger = logging.getLogger(__name__)


class StatCard(QFrame):
    """Compact stat card for the dashboard's top summary row."""

    def __init__(self, title: str, value: str = "0", subtext: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setProperty("class", "Card")
        self.setFixedWidth(160)
        self.setMinimumHeight(110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("StatTitle")
        layout.addWidget(title_label)

        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("StatValue")
        layout.addWidget(self.value_label)

        self.subtext_label = QLabel(subtext)
        self.subtext_label.setObjectName("StatSubtext")
        if subtext:
            layout.addWidget(self.subtext_label)
        layout.addStretch(1)

    def set_value(self, value: str):
        self.value_label.setText(str(value))

    def set_subtext(self, subtext: str):
        self.subtext_label.setText(str(subtext))
        self.subtext_label.setVisible(bool(subtext))


class ModuleCard(QFrame):
    """Compact module card for the right-hand architecture panel."""

    def __init__(self, title: str, description: str, icon_text: str = "•", status: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("ModuleCard")
        self.setProperty("class", "Card")
        self.setFixedHeight(92)

        icon_label = QLabel(icon_text)
        icon_label.setObjectName("ModuleIcon")
        icon_label.setFixedSize(34, 34)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background-color: #1f2a3b; color: white; border-radius: 8px; font-size: 16px;")

        title_label = QLabel(title)
        title_label.setObjectName("ModuleTitle")

        description_label = QLabel(description)
        description_label.setObjectName("ModuleDescription")
        description_label.setWordWrap(True)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)
        top_row.addWidget(icon_label)
        top_row.addWidget(title_label)
        top_row.addStretch(1)
        if status:
            status_label = QLabel(status)
            status_label.setObjectName("StatusChip")
            status_label.setProperty("state", "success")
            top_row.addWidget(status_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addLayout(top_row)
        layout.addWidget(description_label)
        layout.addStretch(1)


class RoadmapCard(QFrame):
    """Fixed-width roadmap card for the bottom launch pipeline panel."""

    def __init__(self, step: int, title: str, text: str, icon_text: str = "↗", parent=None):
        super().__init__(parent)
        self.setObjectName("RoadmapCard")
        self.setProperty("class", "RoadmapCard")
        self.setFixedWidth(170)
        self.setMinimumHeight(128)

        step_label = QLabel(str(step))
        step_label.setObjectName("StepNumber")
        step_label.setProperty("role", "stepNumber")

        title_label = QLabel(title)
        title_label.setObjectName("StepTitle")
        title_label.setProperty("role", "stepTitle")

        text_label = QLabel(text)
        text_label.setObjectName("StepText")
        text_label.setProperty("role", "stepText")
        text_label.setWordWrap(True)

        icon_label = QLabel(icon_text)
        icon_label.setObjectName("RoadmapIcon")
        icon_label.setStyleSheet("color: #4db3ff; font-size: 12px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(step_label)
        layout.addWidget(title_label)
        layout.addWidget(text_label)
        layout.addStretch(1)
        layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignRight)


# ============== Device Selector Widget ==============

class DeviceSelectorWidget(QWidget):
    """Left navigator: compact device list with quick actions."""

    device_selected = pyqtSignal(dict)
    scan_requested = pyqtSignal(dict)
    refresh_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._selected_device = None
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        
        header = QLabel("Devices")
        header.setObjectName("heading")
        layout.addWidget(header)

        self.device_list = QListWidget()
        self.device_list.setAlternatingRowColors(True)
        self.device_list.itemClicked.connect(self._on_device_clicked)
        self.device_list.itemDoubleClicked.connect(self._on_scan_clicked)
        self.device_list.setStyleSheet("""
            QListWidget { background-color: transparent; border: none; }
            QListWidget::item { padding: 10px 8px; border-radius: 8px; }
            QListWidget::item:selected { background-color: #0a66c2; color: white; }
        """)
        self.device_list.setFixedWidth(320)
        layout.addWidget(self.device_list)
        
        self.warning_label = QLabel("TRIM: may reduce recoverability")
        self.warning_label.setObjectName("warning")
        self.warning_label.hide()
        layout.addWidget(self.warning_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("secondary")
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        btn_layout.addWidget(self.refresh_btn)

        btn_layout.addStretch()

        self.scan_btn = QPushButton("Start Scan")
        self.scan_btn.setObjectName("success")
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self._on_scan_clicked)
        btn_layout.addWidget(self.scan_btn)
        
        layout.addLayout(btn_layout)
    
    def _normalize_device(self, device):
        if isinstance(device, dict):
            normalized = {
                'display_name': device.get('display_name') or device.get('device_name') or 'Unknown device',
                'capacity': device.get('capacity', ''),
                'device_type': device.get('device_type', 'Unknown'),
            }
            normalized.update(device)
            return normalized

        text = str(device)
        return {
            'display_name': text,
            'capacity': '',
            'device_type': 'Unknown',
        }

    def load_devices(self, devices):
        self.device_list.clear()
        for device in devices:
            normalized = self._normalize_device(device)
            display = f"{normalized.get('display_name', '')}\n{normalized.get('capacity','')}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, normalized)
            self.device_list.addItem(item)
    
    def _on_device_clicked(self, item):
        device = self._normalize_device(item.data(Qt.ItemDataRole.UserRole))
        self._selected_device = device
        self.scan_btn.setEnabled(True)
        self.device_selected.emit(device)
    
    def _on_scan_clicked(self):
        if self._selected_device:
            self.device_selected.emit(self._normalize_device(self._selected_device))
    
    def _on_refresh_clicked(self):
        self.refresh_requested.emit()


# DashboardWidget is implemented in presentation/widgets/dashboard.py


# ============== File Table Widget ==============

class FileTableWidget(QWidget):
    """Recovered files table with search, filter, and selection support."""

    file_selected = pyqtSignal(dict)
    recover_selected = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._all_rows = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search files...")
        self.search_box.textChanged.connect(self._filter_rows)
        controls.addWidget(self.search_box, 2)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Recovered", "Deleted", "Carved", "Image", "Document", "Archive"])
        self.filter_combo.currentTextChanged.connect(self._filter_rows)
        controls.addWidget(self.filter_combo, 1)
        layout.addLayout(controls)

        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(7)
        self.table_widget.setHorizontalHeaderLabels([
            "Name", "Path", "Type", "Size", "Modified Date", "Confidence", "Preview"
        ])
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_widget.setSortingEnabled(True)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setShowGrid(False)
        self.table_widget.setStyleSheet("""
            QTableWidget {
                background-color: #0b1420;
                alternate-background-color: #0f1a2b;
                border: 1px solid #25354a;
                border-radius: 10px;
                gridline-color: #223145;
                selection-background-color: #17314f;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #101c2c;
                color: #9eb0c6;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #25354a;
                font-weight: 600;
            }
        """)
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table_widget.setColumnWidth(6, 70)
        self.table_widget.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table_widget)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        self.recover_btn = QPushButton("Recover Selected")
        self.recover_btn.setProperty('variant', 'primary')
        self.recover_btn.setEnabled(False)
        self.recover_btn.clicked.connect(self._on_recover_clicked)
        btn_layout.addWidget(self.recover_btn)

        export_btn = QPushButton("Export Report")
        export_btn.clicked.connect(self._on_export_clicked)
        btn_layout.addWidget(export_btn)
        btn_layout.addStretch()

        self.status_label = QLabel("No files loaded")
        self.status_label.setObjectName('SectionSubtle')
        layout.addWidget(self.status_label)
        layout.addLayout(btn_layout)

    def load_files(self, files):
        self._all_rows = list(files)
        self._refresh_table()

    def add_file(self, f: dict):
        self._all_rows.append(f)
        self._refresh_table()

    def _refresh_table(self):
        self.table_widget.setSortingEnabled(False)
        self.table_widget.setRowCount(0)
        query = self.search_box.text().strip().lower()
        filter_value = self.filter_combo.currentText()

        visible_rows = []
        for item in self._all_rows:
            filename = str(item.get('filename', ''))
            category = str(item.get('category', '')).upper()
            status = str(item.get('status', 'Recovered'))
            if query and query not in filename.lower():
                continue
            if filter_value == 'Recovered' and status != 'Recovered':
                continue
            if filter_value == 'Deleted' and status != 'Deleted':
                continue
            if filter_value == 'Carved' and status != 'Carved':
                continue
            if filter_value == 'Image' and category != 'IMAGE':
                continue
            if filter_value == 'Document' and category != 'DOCUMENT':
                continue
            if filter_value == 'Archive' and category != 'ARCHIVE':
                continue
            visible_rows.append(item)

        for f in visible_rows:
            row = self.table_widget.rowCount()
            self.table_widget.insertRow(row)
            self.table_widget.setItem(row, 0, QTableWidgetItem(str(f.get('filename', 'Unknown'))))
            self.table_widget.setItem(row, 1, QTableWidgetItem(str(f.get('path', ''))))
            self.table_widget.setItem(row, 2, QTableWidgetItem(str(f.get('category', 'OTHER'))))
            self.table_widget.setItem(row, 3, QTableWidgetItem(str(f.get('size', '0 B'))))
            self.table_widget.setItem(row, 4, QTableWidgetItem(str(f.get('modified', datetime.now().strftime('%Y-%m-%d')))))
            self.table_widget.setItem(row, 5, QTableWidgetItem(str(f.get('confidence', '0%'))))
            self.table_widget.setItem(row, 6, QTableWidgetItem('▶'))

        self.table_widget.setSortingEnabled(True)
        self.status_label.setText(f"{len(visible_rows)} files found")
        self.recover_btn.setEnabled(len(visible_rows) > 0)

    def _filter_rows(self):
        self._refresh_table()

    def _on_recover_clicked(self):
        selected_rows = []
        for index in self.table_widget.selectionModel().selectedRows():
            selected_rows.append(index.row())

        if not selected_rows:
            QMessageBox.information(self, "Recover", "No files selected")
            return

        files_to_recover = []
        for row in selected_rows:
            filename = self.table_widget.item(row, 0).text() if self.table_widget.item(row, 0) else f"file_{row}"
            size = self.table_widget.item(row, 3).text() if self.table_widget.item(row, 3) else ''
            files_to_recover.append((filename, size))

        self.recover_selected.emit(files_to_recover)

    def _on_export_clicked(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Report", "", "CSV Files (*.csv);;All Files (*)")
        if not file_path:
            return
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                headers = [self.table_widget.horizontalHeaderItem(i).text() for i in range(self.table_widget.columnCount())]
                writer.writerow(headers)
                for row in range(self.table_widget.rowCount()):
                    writer.writerow([self.table_widget.item(row, col).text() if self.table_widget.item(row, col) else '' for col in range(self.table_widget.columnCount())])
            QMessageBox.information(self, "Export", f"Report exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", f"Failed to export report: {e}")

    def _on_selection_changed(self):
        current_row = self.table_widget.currentRow()
        if current_row < 0:
            return
        file_info = {
            'status': self.table_widget.item(current_row, 0).text() if self.table_widget.item(current_row, 0) else '',
            'filename': self.table_widget.item(current_row, 0).text() if self.table_widget.item(current_row, 0) else '',
            'path': self.table_widget.item(current_row, 1).text() if self.table_widget.item(current_row, 1) else '',
            'category': self.table_widget.item(current_row, 2).text() if self.table_widget.item(current_row, 2) else '',
            'size': self.table_widget.item(current_row, 3).text() if self.table_widget.item(current_row, 3) else '',
            'modified': self.table_widget.item(current_row, 4).text() if self.table_widget.item(current_row, 4) else '',
            'confidence': self.table_widget.item(current_row, 5).text() if self.table_widget.item(current_row, 5) else '',
        }
        self.file_selected.emit(file_info)


class PreviewWidget(QFrame):
    """Preview card with image region, detail/hex view toggle, and metadata."""

    def __init__(self):
        super().__init__()
        self.setObjectName('PreviewCard')
        self.setProperty('class', 'Card')
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel('Preview')
        title.setObjectName('SectionTitle')
        layout.addWidget(title)

        self.preview_label = QLabel('No preview available')
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet('background-color:#0b1420; border:1px solid #25354a; border-radius:10px;')
        self.preview_label.setMinimumHeight(220)
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        controls = QHBoxLayout()
        self.details_btn = QPushButton('Details')
        self.details_btn.setProperty('variant', 'primary')
        self.details_btn.clicked.connect(lambda: self._show_view('details'))
        controls.addWidget(self.details_btn)
        self.hex_btn = QPushButton('Hex View')
        self.hex_btn.clicked.connect(lambda: self._show_view('hex'))
        controls.addWidget(self.hex_btn)
        controls.addStretch()
        layout.addLayout(controls)

        self.view_stack = QStackedWidget(self)
        self.details_text = QLabel('Select a file to preview')
        self.details_text.setWordWrap(True)
        self.details_text.setObjectName('SectionSubtle')
        self.view_stack.addWidget(self.details_text)
        self.hex_text = QLabel('Hex preview is not available for this demo file.')
        self.hex_text.setWordWrap(True)
        self.hex_text.setObjectName('SectionSubtle')
        self.view_stack.addWidget(self.hex_text)
        layout.addWidget(self.view_stack)

        self.metadata = QLabel('Metadata')
        self.metadata.setObjectName('SectionSubtle')
        self.metadata.setWordWrap(True)
        layout.addWidget(self.metadata)

    def _show_view(self, view: str):
        if view == 'hex':
            self.view_stack.setCurrentIndex(1)
            self.hex_btn.setProperty('variant', 'primary')
            self.details_btn.setProperty('variant', '')
        else:
            self.view_stack.setCurrentIndex(0)
            self.details_btn.setProperty('variant', 'primary')
            self.hex_btn.setProperty('variant', '')
        self.details_btn.style().unpolish(self.details_btn)
        self.details_btn.style().polish(self.details_btn)
        self.hex_btn.style().unpolish(self.hex_btn)
        self.hex_btn.style().polish(self.hex_btn)

    def show_file(self, info: dict):
        fname = str(info.get('filename', ''))
        if any(fname.lower().endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.bmp')):
            try:
                pix = QPixmap('build/placeholder_preview.png')
                if not pix.isNull():
                    self.preview_label.setPixmap(pix.scaled(320, 220, Qt.AspectRatioMode.KeepAspectRatio))
                    self.preview_label.setText('')
                else:
                    self.preview_label.setText('Preview image unavailable')
                    self.preview_label.setStyleSheet('background-color:#223344; border:1px solid #25354a; border-radius:10px;')
            except Exception:
                self.preview_label.setText('Preview image unavailable')
                self.preview_label.setStyleSheet('background-color:#223344; border:1px solid #25354a; border-radius:10px;')
        else:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(f"Preview for\n{fname or 'selected file'}")
            self.preview_label.setStyleSheet('background-color:#223344; border:1px solid #25354a; border-radius:10px;')

        self.details_text.setText(
            f"Filename: {info.get('filename', '')}\n"
            f"Path: {info.get('path', '')}\n"
            f"Type: {info.get('category', '')}\n"
            f"Size: {info.get('size', '')}\n"
            f"Confidence: {info.get('confidence', '')}"
        )
        self.hex_text.setText(f"Hex preview for {info.get('filename', 'selected file')}\n\n00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F")
        self.metadata.setText(
            f"Modified: {info.get('modified', 'Unknown')}\n"
            f"Confidence: {info.get('confidence', 'Unknown')}"
        )


class FileResultsPanel(QWidget):
    """Composite panel combining file table and preview."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = FileTableWidget()
        layout.addWidget(self.table, 3)

        self.preview = PreviewWidget()
        layout.addWidget(self.preview, 1)

        # Wire selection
        self.table.file_selected.connect(self.preview.show_file)

    def load_files(self, files):
        self.table.load_files(files)


# ============== Main Window ==============

class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Ever Recover - Professional Digital Forensics Tool")
        self.setMinimumSize(1400, 900)
        self._apply_dashboard_stylesheet()
        
        self._current_device = None
        self._is_scanning = False
        
        self._build_ui()
        self._init_menu()
        self._init_status_bar()
        
        # Load demo devices
        self._load_demo_devices()
        
        logger.info("Main window initialized")
    
    def _apply_dashboard_stylesheet(self):
        stylesheet_path = Path(__file__).resolve().parent / "styles" / "dashboard.qss"
        if stylesheet_path.exists():
            with stylesheet_path.open("r", encoding="utf-8") as handle:
                self.setStyleSheet(handle.read())
            return
        self.setStyleSheet(get_dark_theme_stylesheet())

    def _build_ui(self):
        self.central_scroll = QScrollArea()
        self.central_scroll.setObjectName('MainScrollArea')
        self.central_scroll.setWidgetResizable(True)
        self.central_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.central_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.central_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setCentralWidget(self.central_scroll)

        self.main_content = QWidget()
        self.main_content.setObjectName('MainContent')
        self.main_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.central_scroll.setWidget(self.main_content)

        self.app_shell = QVBoxLayout(self.main_content)
        self.app_shell.setContentsMargins(18, 18, 18, 18)
        self.app_shell.setSpacing(16)

        self._build_header()
        self._build_workspace()
        self._build_roadmap()

    def _build_header(self):
        self.top_header = QFrame(self.main_content)
        self.top_header.setObjectName('TopHeaderPanel')
        self.top_header.setProperty('class', 'Panel')
        self.top_header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_layout = QHBoxLayout(self.top_header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(16)

        brand_block = QFrame(self.top_header)
        brand_block.setObjectName('BrandBlock')
        brand_block.setProperty('class', 'Card')
        brand_layout = QHBoxLayout(brand_block)
        brand_layout.setContentsMargins(12, 10, 12, 10)
        brand_layout.setSpacing(10)

        logo = QLabel('ER')
        logo.setObjectName('LogoIcon')
        logo.setProperty('role', 'icon')
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet('background-color:#1f6feb; color:white; border-radius:18px; font-size:18px; font-weight:700; min-width:36px; min-height:36px;')
        brand_layout.addWidget(logo)

        title_box = QVBoxLayout()
        title_label = QLabel('EVER RECOVER')
        title_label.setObjectName('BrandTitle')
        title_box.addWidget(title_label)
        subtitle = QLabel('Professional Digital Forensics & Deleted File Recovery')
        subtitle.setObjectName('BrandSubtitle')
        title_box.addWidget(subtitle)
        brand_layout.addLayout(title_box)
        header_layout.addWidget(brand_block, 2)

        feature_badges = [
            ('Multi-Filesystem', 'NTFS/FAT32/EXT4', '⬢', 'success'),
            ('File Carving', 'Signature scan', '✚', 'success'),
            ('AI Analysis', 'Smart triage', '✦', 'warning'),
            ('Forensic Imaging', 'Disk-safe capture', '◉', 'warning'),
            ('Detailed Reporting', 'CSV/HTML/PDF', '▤', 'success'),
            ('Safe Access', 'Read-only mode', '✓', 'success'),
        ]
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        for title, caption, icon, state in feature_badges:
            badge = QFrame(self.top_header)
            badge.setObjectName('FeatureBadge')
            badge.setProperty('role', 'badge')
            badge.setProperty('class', 'Badge')
            badge_layout = QHBoxLayout(badge)
            badge_layout.setContentsMargins(8, 8, 8, 8)
            badge_layout.setSpacing(6)
            icon_label = QLabel(icon)
            icon_label.setObjectName('BrandAccent')
            icon_label.setProperty('state', state)
            icon_label.setStyleSheet('font-size:12px; font-weight:700;')
            badge_layout.addWidget(icon_label)
            text_layout = QVBoxLayout()
            title_label = QLabel(title)
            title_label.setObjectName('BadgeTitle')
            title_label.setProperty('role', 'badgeTitle')
            text_layout.addWidget(title_label)
            caption_label = QLabel(caption)
            caption_label.setObjectName('BadgeText')
            caption_label.setProperty('role', 'badgeText')
            text_layout.addWidget(caption_label)
            badge_layout.addLayout(text_layout)
            badge_row.addWidget(badge)
        header_layout.addLayout(badge_row, 4)

        utility_area = QVBoxLayout()
        utility_area.setObjectName('UtilityArea')
        utility_buttons = QHBoxLayout()
        theme_button = QToolButton(self.top_header)
        theme_button.setText('☀')
        theme_button.setToolTip('Toggle theme')
        theme_button.setObjectName('UtilityButton')
        utility_buttons.addWidget(theme_button)

        settings_button = QToolButton(self.top_header)
        settings_button.setText('⚙')
        settings_button.setToolTip('Settings')
        settings_button.setObjectName('SettingsButton')
        settings_button.setProperty('variant', 'secondary')
        utility_buttons.addWidget(settings_button)

        utility_area.addLayout(utility_buttons)
        utility_area.addStretch(1)
        status_label = QLabel(f"{platform.system()} {platform.release()}")
        status_label.setObjectName('StatusChip')
        utility_area.addWidget(status_label, alignment=Qt.AlignmentFlag.AlignRight)
        header_layout.addLayout(utility_area)

        self.app_shell.addWidget(self.top_header)

    def _build_workspace(self):
        self.workspace = QFrame(self.main_content)
        self.workspace.setObjectName('WorkspacePanel')
        self.workspace.setProperty('class', 'Panel')
        row = QHBoxLayout(self.workspace)
        row.setSpacing(14)

        self.left_nav = self._make_left_nav()
        self.center_workspace = self._make_center_workspace()
        self.right_panel = self._make_right_panel()

        row.addWidget(self.left_nav, 2)
        row.addWidget(self.center_workspace, 7)
        row.addWidget(self.right_panel, 3)

        self.app_shell.addWidget(self.workspace, 1)

    def _build_roadmap(self):
        self.roadmap = QFrame(self.main_content)
        self.roadmap.setObjectName('BottomRoadmapPanel')
        self.roadmap.setProperty('class', 'Panel')
        roadmap_layout = QVBoxLayout(self.roadmap)
        roadmap_layout.setContentsMargins(14, 14, 14, 14)
        roadmap_layout.setSpacing(10)

        title_row = QHBoxLayout()
        roadmap_title = QLabel('Roadmap')
        roadmap_title.setObjectName('SectionTitle')
        title_row.addWidget(roadmap_title)
        title_row.addStretch(1)
        roadmap_layout.addLayout(title_row)

        self.roadmap_scroll = QScrollArea(self.roadmap)
        self.roadmap_scroll.setObjectName('RoadmapScrollArea')
        self.roadmap_scroll.setWidgetResizable(True)
        self.roadmap_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.roadmap_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.roadmap_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.roadmap_scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')

        self.roadmap_content = QWidget()
        self.roadmap_content.setObjectName('RoadmapContent')
        self.roadmap_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.roadmap_scroll.setWidget(self.roadmap_content)

        self.roadmap_row = QHBoxLayout(self.roadmap_content)
        self.roadmap_row.setObjectName('RoadmapRow')
        self.roadmap_row.setContentsMargins(0, 0, 0, 0)
        self.roadmap_row.setSpacing(12)

        roadmap_steps = [
            (1, "Device Scan", "Discover drives and start imaging"),
            (2, "Metadata Extraction", "Gather timestamps, hashes, and structure"),
            (3, "Recovery Heuristics", "Score recoverable evidence and fragments"),
            (4, "Report Generation", "Export findings to CSV, HTML, and PDF"),
            (5, "CLI Interface", "Support advanced scripted workflows"),
            (6, "Settings Panel", "Tune scanning parameters and profiles"),
            (7, "Test Suite", "Validate recovery and parsing behavior"),
        ]
        for step, title, text in roadmap_steps:
            card = RoadmapCard(step, title, text, self.roadmap_content)
            self.roadmap_row.addWidget(card)

        self.roadmap_row.addStretch(1)
        roadmap_layout.addWidget(self.roadmap_scroll)
        self.app_shell.addWidget(self.roadmap)

    def _make_left_nav(self):
        panel = QFrame(self.main_content)
        panel.setObjectName('LeftNavPanel')
        panel.setMinimumWidth(240)
        panel.setMaximumWidth(260)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        nav_title = QLabel('Navigation')
        nav_title.setObjectName('NavTitle')
        layout.addWidget(nav_title)

        self.nav_list = QListWidget(panel)
        self.nav_list.setObjectName('NavList')
        nav_items = [
            ('Dashboard', 'NavItem_Dashboard'), ('Scan', 'NavItem_Scan'), ('Recovered Files', 'NavItem_Files'),
            ('File Preview', 'NavItem_Preview'), ('Reports', 'NavItem_Reports'), ('Disk Image', 'NavItem_DiskImage'),
            ('Logs', 'NavItem_Logs'), ('Settings', 'NavItem_Settings'), ('Help', 'NavItem_Help')
        ]
        self.nav_list.addItems([label for label, _ in nav_items])
        for index, (_, item_name) in enumerate(nav_items):
            item = self.nav_list.item(index)
            if item is not None:
                item.setData(Qt.ItemDataRole.UserRole, item_name)
        self.nav_list.setCurrentRow(0)
        layout.addWidget(self.nav_list)

        self.device_selector = DeviceSelectorWidget()
        self.device_selector.device_selected.connect(self._on_device_selected)
        layout.addWidget(self.device_selector)
        return panel

    def _make_center_workspace(self):
        panel = QFrame(self.main_content)
        panel.setObjectName('CenterWorkspace')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.top_stats_row = QHBoxLayout()
        self.top_stats_row.setObjectName('TopStatsRow')
        self.top_stats_row.setSpacing(10)
        self.stat_cards = {}
        stat_definitions = [
            ("Files Found", "0", "Recovered items"),
            ("Recoverable", "0", "Ready to restore"),
            ("High Confidence", "0", "Strong matches"),
            ("Medium Confidence", "0", "Needs review"),
            ("Low Confidence", "0", "Uncertain results"),
            ("Carved Files", "0", "Recovered fragments"),
        ]
        for title, value, subtext in stat_definitions:
            card = StatCard(title, value, subtext, panel)
            card.setObjectName(f"StatCard_{title.replace(' ', '')}")
            self.stat_cards[title.lower().replace(' ', '_')] = card
            self.top_stats_row.addWidget(card)
        layout.addLayout(self.top_stats_row)

        self.info_cards_row = QGridLayout()
        self.info_cards_row.setObjectName('InfoCardsRow')
        self.info_cards_row.setSpacing(12)
        self.scan_progress_card = self._build_scan_progress_card(panel)
        self.device_info_card = self._build_device_info_card(panel)
        self.recovery_stats_card = self._build_recovery_stats_card(panel)
        self.info_cards_row.addWidget(self.scan_progress_card, 0, 0, 1, 1)
        self.info_cards_row.addWidget(self.device_info_card, 0, 1, 1, 1)
        self.info_cards_row.addWidget(self.recovery_stats_card, 0, 2, 1, 1)
        self.info_cards_row.setColumnStretch(0, 3)
        self.info_cards_row.setColumnStretch(1, 2)
        self.info_cards_row.setColumnStretch(2, 2)
        layout.addLayout(self.info_cards_row)

        self.middle_content_row = QHBoxLayout()
        self.middle_content_row.setObjectName('MiddleContentRow')
        self.middle_content_row.setSpacing(12)
        self.files_table_card = QFrame(panel)
        self.files_table_card.setObjectName('FilesTableCard')
        self.files_table_card.setProperty('class', 'Card')
        files_layout = QVBoxLayout(self.files_table_card)
        files_layout.setContentsMargins(12, 12, 12, 12)
        title = QLabel('Recovered Files')
        title.setObjectName('SectionTitle')
        files_layout.addWidget(title)
        self.files_table = FileTableWidget()
        self.files_table.recover_selected.connect(self._on_recover_selected)
        files_layout.addWidget(self.files_table, 1)
        self.preview_card = QFrame(panel)
        self.preview_card.setObjectName('PreviewCard')
        self.preview_card.setProperty('class', 'Card')
        preview_layout = QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        self.preview = PreviewWidget()
        preview_layout.addWidget(self.preview)
        self.middle_content_row.addWidget(self.files_table_card, 3)
        self.middle_content_row.addWidget(self.preview_card, 2)
        layout.addLayout(self.middle_content_row, 1)

        self.files_table.file_selected.connect(self.preview.show_file)

        self.status_strip = QFrame(panel)
        self.status_strip.setObjectName('BottomStatusStrip')
        self.status_strip.setProperty('class', 'Card')
        status_layout = QHBoxLayout(self.status_strip)
        status_layout.setContentsMargins(10, 8, 10, 8)
        self.thread_label = QLabel('Threads: 8')
        self.speed_label = QLabel('Speed: 0 MB/s')
        self.total_label = QLabel('Files: 0')
        for label in (self.thread_label, self.speed_label, self.total_label):
            label.setObjectName('SectionSubtle')
            status_layout.addWidget(label)
        status_layout.addStretch()
        layout.addWidget(self.status_strip)

        self.dashboard = DashboardWidget()
        self.dashboard.hide()
        return panel

    def _build_scan_progress_card(self, parent):
        card = QFrame(parent)
        card.setObjectName('ScanProgressCard')
        card.setProperty('class', 'Card')
        layout = QGridLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        progress_widget = CircularProgress(card)
        progress_widget.setFixedSize(120, 120)
        progress_widget.setValue(0)
        layout.addWidget(progress_widget, 0, 0, 3, 1)

        title = QLabel('Scan Progress')
        title.setObjectName('SectionTitle')
        layout.addWidget(title, 0, 1, 1, 2)

        self.progress_detail_labels = {}
        self.progress_circle = progress_widget
        row = 1
        for label_text, attr_name in [
            ('Scan Type', 'scan_type'),
            ('Device', 'device'),
            ('File System', 'filesystem'),
            ('Start Time', 'start_time'),
            ('Elapsed Time', 'elapsed'),
            ('Estimated Time', 'eta'),
        ]:
            key = QLabel(label_text)
            key.setObjectName('SectionSubtle')
            value = QLabel('—')
            value.setObjectName('StatLabel')
            self.progress_detail_labels[attr_name] = value
            layout.addWidget(key, row, 1)
            layout.addWidget(value, row, 2)
            row += 1
        return card

    def _build_device_info_card(self, parent):
        card = QFrame(parent)
        card.setObjectName('DeviceInfoCard')
        card.setProperty('class', 'Card')
        layout = QGridLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel('Device Info')
        title.setObjectName('SectionTitle')
        layout.addWidget(title, 0, 0, 1, 2)

        self.device_row_labels = {}
        row = 1
        for label_text, attr_name in [
            ('Device', 'device'),
            ('Serial', 'serial'),
            ('Capacity', 'capacity'),
            ('Interface', 'interface'),
            ('Health', 'health'),
            ('TRIM', 'trim'),
            ('Read-only', 'readonly'),
        ]:
            key = QLabel(label_text)
            key.setObjectName('SectionSubtle')
            value = QLabel('—')
            value.setObjectName('StatLabel')
            self.device_row_labels[attr_name] = value
            layout.addWidget(key, row, 0)
            layout.addWidget(value, row, 1)
            row += 1

        health_chip = QLabel('Healthy')
        health_chip.setObjectName('StatusChip')
        health_chip.setProperty('state', 'success')
        layout.addWidget(health_chip, row, 0, 1, 2)
        return card

    def _build_recovery_stats_card(self, parent):
        card = QFrame(parent)
        card.setObjectName('RecoveryStatsCard')
        card.setProperty('class', 'Card')
        layout = QGridLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel('Recovery Stats')
        title.setObjectName('SectionTitle')
        layout.addWidget(title, 0, 0, 1, 2)

        self.recovery_stat_labels = {}
        row = 1
        for label_text, attr_name in [
            ('Files found', 'files_found'),
            ('Recoverable', 'recoverable'),
            ('High confidence', 'high_confidence'),
            ('Medium confidence', 'medium_confidence'),
            ('Low confidence', 'low_confidence'),
            ('Carved files', 'carved_files'),
        ]:
            key = QLabel(label_text)
            key.setObjectName('SectionSubtle')
            value = QLabel('0')
            value.setObjectName('StatValue')
            self.recovery_stat_labels[attr_name] = value
            layout.addWidget(key, row, 0)
            layout.addWidget(value, row, 1)
            row += 1
        return card

    def _make_right_panel(self):
        panel = QFrame(self.main_content)
        panel.setObjectName('RightInsightsPanel')
        panel.setMinimumWidth(280)
        panel.setMaximumWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        modules_title = QLabel('System Modules')
        modules_title.setObjectName('ModuleTitle')
        layout.addWidget(modules_title)

        module_stack = QVBoxLayout()
        module_stack.setObjectName('ModuleCardStack')
        layout.addLayout(module_stack)

        module_items = [
            ("Signature Parser", "Scans file signatures and classification rules.", "✦", "Signature Parser"),
            ("Carving Engine", "Recovers deleted or fragmented file data.", "◉", "Carving Engine"),
            ("Structure Analyzer", "Rebuilds filesystem and container structure.", "▣", "Structure Analyzer"),
            ("Metadata Extractor", "Pulls timestamps, hashes, and provenance.", "⌘", "Metadata Extractor"),
            ("Filesystem Heuristics", "Tracks suspicious or orphaned file patterns.", "⟡", "Filesystem Heuristics"),
            ("Report Writer", "Exports findings to printable evidence reports.", "☰", "Report Writer"),
            ("Heuristics Engine", "Scores evidence quality and recovery confidence.", "⚑", "Heuristics Engine"),
        ]
        for index, (title_text, description, icon_text, status_text) in enumerate(module_items):
            card = ModuleCard(title_text, description, icon_text, status_text, panel)
            if index == 0:
                card.setObjectName('ModuleCard_Gui')
            module_stack.addWidget(card)

        layout.addStretch()
        return panel

    def _card(self):
        frame = QFrame(self.main_content)
        frame.setObjectName('Card')
        frame.setProperty('class', 'Card')
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return frame
    
    def _init_menu(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("&File")
        
        open_action = QAction("Open Disk Image...", self)
        open_action.triggered.connect(self._on_open_image)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
    
    def _init_status_bar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.status_label = QLabel("Ready")
        self.statusbar.addWidget(self.status_label)

    def _update_device_card(self, device):
        if not hasattr(self, 'device_row_labels'):
            return
        info = device or {}
        self.device_row_labels.get('device', QLabel()).setText(info.get('display_name') or info.get('device_name') or 'Unknown')
        self.device_row_labels.get('serial', QLabel()).setText(info.get('serial_number') or info.get('serial') or 'N/A')
        self.device_row_labels.get('capacity', QLabel()).setText(str(info.get('capacity') or 'N/A'))
        self.device_row_labels.get('interface', QLabel()).setText(str(info.get('interface') or info.get('device_type') or 'Unknown'))
        self.device_row_labels.get('health', QLabel()).setText(str(info.get('health') or 'Healthy'))
        self.device_row_labels.get('trim', QLabel()).setText('Enabled' if str(info.get('trim', 'Off')).lower() in {'enabled', 'on', 'true', 'yes'} else 'Disabled')
        self.device_row_labels.get('readonly', QLabel()).setText('Yes' if str(info.get('read_only', 'No')).lower() in {'yes', 'true', 'on'} else 'No')

    def _update_progress_card_details(self, device_name, scan_type, filesystem, start_time, elapsed='—', eta='—'):
        if not hasattr(self, 'progress_detail_labels'):
            return
        self.progress_detail_labels.get('scan_type', QLabel()).setText(scan_type)
        self.progress_detail_labels.get('device', QLabel()).setText(device_name)
        self.progress_detail_labels.get('filesystem', QLabel()).setText(filesystem)
        self.progress_detail_labels.get('start_time', QLabel()).setText(start_time)
        self.progress_detail_labels.get('elapsed', QLabel()).setText(elapsed)
        self.progress_detail_labels.get('eta', QLabel()).setText(eta)

    def _update_recovery_stats(self, demo_files):
        if not hasattr(self, 'recovery_stat_labels'):
            return
        total = len(demo_files)
        recoverable = sum(1 for f in demo_files if str(f.get('status', '')).lower() in {'recovered', 'carved'})
        high = sum(1 for f in demo_files if str(f.get('confidence', '0%')).rstrip('%') >= '95')
        medium = sum(1 for f in demo_files if '90' <= str(f.get('confidence', '0%')).rstrip('%') < '95')
        low = total - high - medium
        carved = sum(1 for f in demo_files if str(f.get('status', '')).lower() == 'carved')
        self.recovery_stat_labels.get('files_found', QLabel()).setText(str(total))
        self.recovery_stat_labels.get('recoverable', QLabel()).setText(str(recoverable))
        self.recovery_stat_labels.get('high_confidence', QLabel()).setText(str(high))
        self.recovery_stat_labels.get('medium_confidence', QLabel()).setText(str(medium))
        self.recovery_stat_labels.get('low_confidence', QLabel()).setText(str(low))
        self.recovery_stat_labels.get('carved_files', QLabel()).setText(str(carved))

        if hasattr(self, 'stat_cards'):
            self.stat_cards.get('files_found', QLabel()).set_value(str(total))
            self.stat_cards.get('recoverable', QLabel()).set_value(str(recoverable))
            self.stat_cards.get('high_confidence', QLabel()).set_value(str(high))
            self.stat_cards.get('medium_confidence', QLabel()).set_value(str(medium))
            self.stat_cards.get('low_confidence', QLabel()).set_value(str(low))
            self.stat_cards.get('carved_files', QLabel()).set_value(str(carved))

    def _create_stat_card(self, title, value, variant='Info'):
        subtext = "Ready" if variant == 'Primary' else "Updated"
        return StatCard(title, value, subtext)
    
    def _load_demo_devices(self):
        """Load demo devices."""
        devices = [
            "Samsung SSD 970 EVO 1TB (NTFS) - TRIM",
            "WD Blue 2TB (NTFS)",
            "SanDisk Ultra USB 3.0 64GB (FAT32)",
            "Case_2026-07-09.e01 (Disk Image)",
        ]
        self.device_selector.load_devices(devices)
    
    def _on_device_selected(self, device):
        self._current_device = device
        if isinstance(device, dict):
            name = device.get('device_name') or device.get('display_name')
            self._update_device_card(device)
        else:
            name = str(device)
            self._update_device_card({'display_name': name, 'serial_number': 'N/A', 'capacity': 'N/A', 'device_type': 'Unknown'})
        self.status_label.setText(f"Selected: {name}")
        self._update_progress_card_details(name, 'Live Scan', 'Unknown', datetime.now().strftime('%H:%M:%S'))
        self._start_scan()
    
    def _start_scan(self):
        self._is_scanning = True
        self._scan_progress = 0
        self._scan_start_time = datetime.now()
        self._scan_timer = QTimer()
        self._scan_timer.timeout.connect(self._update_scan_progress)
        self._scan_timer.start(100)
        self._update_progress_card_details(
            self._current_device.get('display_name') if isinstance(self._current_device, dict) else str(self._current_device),
            'Live Scan',
            'Unknown',
            self._scan_start_time.strftime('%H:%M:%S')
        )
        logger.info(f"Started scan on {self._current_device}")
    
    def _update_scan_progress(self):
        self._scan_progress += 1
        if self._scan_progress <= 100:
            self.dashboard.update_progress(self._scan_progress, f"Scanning sector {self._scan_progress * 1000}...")
            elapsed = datetime.now() - self._scan_start_time
            eta = datetime.now() + (elapsed / max(self._scan_progress, 1) * (100 - self._scan_progress))
            self._update_progress_card_details(
                self._current_device.get('display_name') if isinstance(self._current_device, dict) else str(self._current_device),
                'Live Scan',
                self._current_device.get('device_type', 'Unknown') if isinstance(self._current_device, dict) else 'Unknown',
                self._scan_start_time.strftime('%H:%M:%S'),
                str(elapsed).split('.')[0],
                eta.strftime('%H:%M:%S')
            )
            if hasattr(self, 'progress_circle'):
                self.progress_circle.setValue(self._scan_progress)
        else:
            self._scan_timer.stop()
            self._on_scan_complete()
    
    def _on_scan_complete(self):
        self._is_scanning = False
        self.dashboard.update_progress(100, "Scan complete")
        self.status_label.setText("Scan complete")

        demo_files = self._generate_demo_files()
        self.files_table.load_files(demo_files)
        self._update_recovery_stats(demo_files)
        self._update_progress_card_details(
            self._current_device.get('display_name') if isinstance(self._current_device, dict) else str(self._current_device),
            'Completed Scan',
            self._current_device.get('device_type', 'Unknown') if isinstance(self._current_device, dict) else 'Unknown',
            self._scan_start_time.strftime('%H:%M:%S'),
            '00:00',
            'Ready'
        )
        if hasattr(self, 'progress_circle'):
            self.progress_circle.setValue(100)
        logger.info(f"Scan completed - found {len(demo_files)} files")
    
    def _generate_demo_files(self):
        """Generate demo files."""
        filenames = [
            ("Pictures/vacation_photo.jpg", "IMAGE"),
            ("Documents/report_2026.docx", "DOCUMENT"),
            ("Spreadsheets/budget.xlsx", "DOCUMENT"),
            ("Presentations/presentation.pptx", "DOCUMENT"),
            ("Videos/family_video.mp4", "VIDEO"),
            ("Backups/backup.zip", "ARCHIVE"),
            ("Notes/notes.txt", "DOCUMENT"),
            ("Invoices/invoice.pdf", "DOCUMENT"),
            ("Desktop/screenshot.png", "IMAGE"),
            ("Music/track01.mp3", "AUDIO"),
            ("DB/database.sql", "DATA"),
            ("Config/config.json", "DATA"),
            ("Resume/resume.pdf", "DOCUMENT"),
            ("Archives/wedding_photos.zip", "ARCHIVE"),
            ("Projects/project.7z", "ARCHIVE"),
        ]
        
        statuses = ['Recovered', 'Deleted', 'Carved']
        confidences = ['99%', '95%', '90%', '82%', '76%', '65%', '48%']
        
        files = []
        for i, (filename, category) in enumerate(filenames):
            # Create multiple versions with varied sizes and nested paths
            base, ext = ('.'.join(filename.split('.')[:-1]), filename.split('.')[-1]) if '.' in filename else (filename, '')
            for j in range(random.randint(1, 4)):
                size = random.randint(512, 200_000_000)
                if size > 5_000_000:
                    size_str = f"{size / (1024**2):.1f} MB"
                else:
                    size_str = f"{size / 1024:.1f} KB"

                # Occasionally add a sequence or copy indicator
                name = f"{base}_{j}.{ext}" if j > 0 else f"{base}.{ext}"
                # Randomly prefix with a folder to simulate deeper structure
                if random.random() < 0.4 and '/' not in filename:
                    name = f"folder_{random.randint(1,6)}/{name}"

                files.append({
                    'status': random.choices(statuses, weights=(60,30,10))[0],
                    'filename': name,
                    'size': size_str,
                    'category': category,
                    'confidence': random.choice(confidences),
                })
        
        # Add more random files
        for i in range(50):
            k = random.randint(1, 1200000)
            size_str = f"{k / 1024:.1f} KB" if k < 2_000_000 else f"{k / (1024**2):.1f} MB"
            files.append({
                'status': random.choices(statuses, weights=(65,25,10))[0],
                'filename': f"misc/file_{i:03d}.dat",
                'size': size_str,
                'category': 'DATA',
                'confidence': random.choice(confidences),
            })
        
        random.shuffle(files)
        return files[:75]  # Limit to 75 files

    def run_demo_scan(self, app=None, delay=0.02):
        """Synchronous demo scan useful for offscreen rendering.

        Args:
            app: QApplication instance to process events.
            delay: seconds between progress steps.
        """
        import time
        self._demo_files_full = self._generate_demo_files()
        self._demo_index = 0
        total = len(self._demo_files_full)
        for i in range(0, 101):
            # add files gradually
            target = int((i/100.0) * total)
            while self._demo_index < target:
                f = self._demo_files_full[self._demo_index]
                # add to table
                self.files_table.add_file(f)
                self._demo_index += 1
            # update dashboard
            deleted = len([f for f in self._demo_files_full[:self._demo_index] if f.get('status') == 'Deleted'])
            size_sum = 0
            # approximate total size string
            self.dashboard.update_stats(self._demo_index, deleted, self._demo_index, f"{(self._demo_index*2.3):.1f} MB")
            self.dashboard.update_progress(i, f"Scanning sector {i}")
            if app:
                app.processEvents()
            time.sleep(delay)
        # complete
        self.dashboard.update_progress(100, "Scan complete")
    
    def _on_recover_selected(self, files):
        dest = QFileDialog.getExistingDirectory(self, "Select Recovery Destination")
        if dest:
            QMessageBox.information(self, "Recovery", f"Recovering {len(files)} files to:\n{dest}")
    
    def _on_open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Disk Image", "",
            "Disk Images (*.e01 *.img *.raw *.dd);;All Files (*)"
        )
        if file_path:
            QMessageBox.information(self, "Open", f"Opened: {file_path}")
    
    def _on_about(self):
        QMessageBox.about(
            self, "About Ever Recover",
            "Ever Recover v1.0.0\n\n"
            "Professional Digital Forensics & File Recovery Tool\n\n"
            "Build 2026.07\n\n"
            "Features:\n"
            "• NTFS, FAT32, exFAT, EXT4 support\n"
            "• File carving with signature database\n"
            "• Forensic disk imaging\n"
            "• SHA-256 integrity verification\n\n"
            "© 2026 Ever Recover"
        )
    
    def closeEvent(self, event):
        if self._is_scanning:
            reply = QMessageBox.question(
                self, "Scan in Progress",
                "A scan is currently in progress. Exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()