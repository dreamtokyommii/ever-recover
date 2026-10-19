"""Device selector widget for choosing storage devices."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QListWidget, QListWidgetItem, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Optional, List
import logging

from core.models.device import DeviceInfo, DeviceType

logger = logging.getLogger(__name__)


class DeviceSelectorWidget(QWidget):
    """Widget for selecting storage devices to scan."""
    
    device_selected = pyqtSignal(DeviceInfo)
    refresh_requested = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self._devices: List[DeviceInfo] = []
        self._selected_device: Optional[DeviceInfo] = None
        self._init_ui()
    
    def _init_ui(self):
        """Initialize user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header
        header = QLabel("Select Storage Device")
        header.setObjectName("heading")
        layout.addWidget(header)
        
        subtitle = QLabel("Choose a drive, USB, or disk image to analyze")
        subtitle.setObjectName("status")
        layout.addWidget(subtitle)
        
        # Device list
        self.device_list = QListWidget()
        self.device_list.setAlternatingRowColors(True)
        self.device_list.itemClicked.connect(self._on_device_clicked)
        self.device_list.itemDoubleClicked.connect(self._on_scan_clicked)
        layout.addWidget(self.device_list)
        
        # Warning label for SSD/TRIM
        self.warning_label = QLabel()
        self.warning_label.setObjectName("warning")
        self.warning_label.setWordWrap(True)
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
    
    def load_devices(self, devices: List[DeviceInfo]) -> None:
        """
        Load device list.
        
        Args:
            devices: List of available devices
        """
        self._devices = devices
        self.device_list.clear()
        
        for device in devices:
            item = self._create_device_item(device)
            self.device_list.addItem(item)
        
        logger.info(f"Loaded {len(devices)} devices into selector")
    
    def _create_device_item(self, device: DeviceInfo) -> QListWidgetItem:
        """Create list item for device."""
        # Determine icon based on device type
        icon = ""
        if device.device_type == DeviceType.SSD:
            icon = "[SSD]"
        elif device.device_type == DeviceType.HDD:
            icon = "[HDD]"
        elif device.device_type == DeviceType.USB_DRIVE:
            icon = "[USB]"
        elif device.device_type == DeviceType.SD_CARD:
            icon = "[SD]"
        elif device.device_type == DeviceType.DISK_IMAGE:
            icon = "[Image]"

        # Create item text
        text = f"{icon} {device.label} - {device.display_size}" if icon else f"{device.label} - {device.display_size}"
        if device.file_system.value != "Unknown":
            text += f" ({device.file_system.value})"
        
        # Add warning indicators
        if device.has_trim_warning:
            text += " (TRIM)"
        
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, device)
        
        # Set font for main text
        font = QFont()
        font.setPointSize(13)
        item.setFont(font)
        
        return item
    
    def _on_device_clicked(self, item: QListWidgetItem) -> None:
        """Handle device selection."""
        device = item.data(Qt.ItemDataRole.UserRole)
        self._selected_device = device
        
        # Enable scan button
        self.scan_btn.setEnabled(True)
        
        # Show TRIM warning if applicable
        if device.has_trim_warning:
            self.warning_label.setText(
                "Warning: This appears to be an SSD with TRIM enabled. "
                "Deleted files may have been permanently erased. "
                "Recovery success rate may be significantly reduced."
            )
            self.warning_label.show()
        else:
            self.warning_label.hide()
        
        self.device_selected.emit(device)
    
    def _on_scan_clicked(self) -> None:
        """Handle scan button click."""
        if self._selected_device:
            self.device_selected.emit(self._selected_device)
    
    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        self.refresh_requested.emit()
    
    def get_selected_device(self) -> Optional[DeviceInfo]:
        """Get currently selected device."""
        return self._selected_device
    
    def clear(self) -> None:
        """Clear device list."""
        self._devices.clear()
        self._selected_device = None
        self.device_list.clear()
        self.scan_btn.setEnabled(False)
        self.warning_label.hide()