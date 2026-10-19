import os
import sys

import pytest
from PyQt6.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QScrollArea, QHBoxLayout, QVBoxLayout, QLayout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    from presentation.main_window import MainWindow

    win = MainWindow()
    yield win
    win.close()
    app.processEvents()


def test_dashboard_cards_use_grid_layouts_and_module_details(window):
    scan_card = window.findChild(QFrame, "ScanProgressCard")
    device_card = window.findChild(QFrame, "DeviceInfoCard")
    stats_card = window.findChild(QFrame, "RecoveryStatsCard")
    assert scan_card is not None
    assert device_card is not None
    assert stats_card is not None

    assert isinstance(scan_card.layout(), QGridLayout)
    assert isinstance(device_card.layout(), QGridLayout)
    assert isinstance(stats_card.layout(), QGridLayout)

    module_card = window.findChild(QFrame, "ModuleCard_Gui")
    assert module_card is not None
    assert any(isinstance(child, QLabel) for child in module_card.findChildren(QLabel))


def test_roadmap_panel_uses_scrollable_horizontal_card_row(window):
    roadmap_panel = window.findChild(QFrame, "BottomRoadmapPanel")
    assert roadmap_panel is not None

    roadmap_scroll = window.findChild(QScrollArea, "RoadmapScrollArea")
    assert roadmap_scroll is not None
    assert isinstance(roadmap_scroll.widget().layout(), QHBoxLayout)

    roadmap_cards = window.findChildren(QFrame, "RoadmapCard")
    assert len(roadmap_cards) >= 7


def test_main_window_shell_uses_scrollable_content_widget(window):
    central_widget = window.centralWidget()
    assert isinstance(central_widget, QScrollArea)
    assert central_widget.objectName() == "MainScrollArea"

    main_content = central_widget.widget()
    assert main_content is not None
    assert main_content.objectName() == "MainContent"
    assert isinstance(main_content.layout(), QVBoxLayout)

    top_header = window.findChild(QFrame, "TopHeaderPanel")
    workspace = window.findChild(QFrame, "WorkspacePanel")
    roadmap = window.findChild(QFrame, "BottomRoadmapPanel")

    assert top_header is not None
    assert workspace is not None
    assert roadmap is not None
    assert top_header.property("class") == "Panel"
    assert workspace.property("class") == "Panel"
    assert roadmap.property("class") == "Panel"


def test_center_workspace_uses_grid_for_primary_cards(window):
    center = window.findChild(QFrame, "CenterWorkspace")
    assert center is not None

    info_row = center.findChild(QLayout, "InfoCardsRow")
    assert info_row is not None
    assert isinstance(info_row, QGridLayout)

    assert window.findChild(QFrame, "FilesTableCard") is not None
    assert window.findChild(QFrame, "PreviewCard") is not None
    assert window.findChild(QFrame, "BottomStatusStrip") is not None
