"""Dark theme stylesheet for Ever Recover."""


def get_dark_theme_stylesheet() -> str:
    """
    Get complete dark theme stylesheet.
    
    Returns:
        CSS stylesheet string for PyQt6
    """
    return """
    /* ========== Global Styles ========== */
    QMainWindow, QWidget {
        background-color: #151617;
        color: #e6e6e6;
        font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        font-size: 13.5px;
        -webkit-font-smoothing: antialiased;
    }
    
    QToolTip {
        background-color: #2d2d2d;
        color: #e0e0e0;
        border: 1px solid #3e3e3e;
        padding: 4px 8px;
        border-radius: 4px;
    }
    
    /* ========== Buttons ========== */
    QPushButton {
        background-color: #1f6feb;
        color: white;
        border: none;
        padding: 8px 14px;
        border-radius: 8px;
        font-weight: 600;
        min-width: 90px;
    }
    
    QPushButton:hover {
        background-color: #1084d8;
    }
    
    QPushButton:pressed {
        background-color: #006cbe;
    }
    
    QPushButton:disabled {
        background-color: #3e3e3e;
        color: #888888;
    }
    
    QPushButton#secondary {
        background-color: #3e3e3e;
    }
    
    QPushButton#secondary:hover {
        background-color: #4e4e4e;
    }
    
    QPushButton#danger {
        background-color: #c50f1f;
    }
    
    QPushButton#danger:hover {
        background-color: #d61324;
    }
    
    QPushButton#success {
        background-color: #107c10;
    }
    
    QPushButton#success:hover {
        background-color: #148c14;
    }
    
    /* ========== Labels ========== */
    QLabel {
        color: #e0e0e0;
        background-color: transparent;
    }
    
    QLabel#heading {
        font-size: 22px;
        font-weight: 700;
        color: #ffffff;
        padding: 6px 0;
        letter-spacing: 0.2px;
    }
    
    QLabel#subheading {
        font-size: 16px;
        font-weight: 600;
        color: #e6e6e6;
        padding: 4px 0;
    }
    
    QLabel#status {
        font-size: 13px;
        color: #a0a0a0;
    }
    
    QLabel#large {
        font-size: 28px;
        font-weight: 300;
        color: #ffffff;
    }
    
    QLabel#warning {
        color: #ffaa00;
    }
    
    QLabel#error {
        color: #ff6666;
    }
    
    QLabel#success {
        color: #66ff66;
    }
    
    /* ========== Progress Bars ========== */
    QProgressBar {
        background-color: #222428;
        border: none;
        border-radius: 6px;
        height: 10px;
        text-align: center;
    }
    
    QProgressBar::chunk {
        background-color: #2a9df4;
        border-radius: 6px;
    }
    
    QProgressBar#low {
        background-color: #2d2d2d;
    }
    
    QProgressBar#low::chunk {
        background-color: #ffaa00;
    }
    
    QProgressBar#high::chunk {
        background-color: #107c10;
    }
    
    /* ========== Line Edits ========== */
    QLineEdit {
        background-color: #2d2d2d;
        border: 1px solid #3e3e3e;
        border-radius: 4px;
        padding: 6px 10px;
        color: #e0e0e0;
        selection-background-color: #0078d4;
    }
    
    QLineEdit:focus {
        border: 1px solid #0078d4;
    }
    
    QLineEdit:disabled {
        background-color: #1e1e1e;
        color: #666666;
    }
    
    /* ========== Combo Boxes ========== */
    QComboBox {
        background-color: #2d2d2d;
        border: 1px solid #3e3e3e;
        border-radius: 4px;
        padding: 6px 10px;
        color: #e0e0e0;
        min-width: 120px;
    }
    
    QComboBox:hover {
        border: 1px solid #0078d4;
    }
    
    QComboBox::drop-down {
        width: 20px;
        border: none;
    }
    
    QComboBox QAbstractItemView {
        background-color: #2d2d2d;
        border: 1px solid #3e3e3e;
        selection-background-color: #0078d4;
    }
    
    /* ========== Check Boxes ========== */
    QCheckBox {
        color: #e0e0e0;
        spacing: 8px;
    }
    
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid #3e3e3e;
        background-color: #2d2d2d;
    }
    
    QCheckBox::indicator:checked {
        background-color: #0078d4;
        border: 1px solid #0078d4;
    }
    
    QCheckBox::indicator:hover {
        border: 1px solid #0078d4;
    }
    
    /* ========== Group Boxes ========== */
    QGroupBox {
        background-color: #2d2d2d;
        border: 1px solid #3e3e3e;
        border-radius: 4px;
        margin-top: 12px;
        padding-top: 12px;
        font-weight: 600;
    }
    
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        top: 0px;
        padding: 0 8px;
        color: #ffffff;
    }
    
    /* ========== Scroll Areas ========== */
    QScrollArea {
        background-color: #1e1e1e;
        border: none;
    }
    
    QScrollBar:vertical {
        background-color: #1e1e1e;
        width: 12px;
        border-radius: 6px;
    }
    
    QScrollBar::handle:vertical {
        background-color: #3e3e3e;
        border-radius: 6px;
        min-height: 30px;
    }
    
    QScrollBar::handle:vertical:hover {
        background-color: #4e4e4e;
    }
    
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0px;
    }
    
    QScrollBar:horizontal {
        background-color: #1e1e1e;
        height: 12px;
        border-radius: 6px;
    }
    
    QScrollBar::handle:horizontal {
        background-color: #3e3e3e;
        border-radius: 6px;
        min-width: 30px;
    }
    
    QScrollBar::handle:horizontal:hover {
        background-color: #4e4e4e;
    }
    
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    
    /* ========== Tables ========== */
    QTableView {
        background-color: #1f2326;
        alternate-background-color: #222428;
        border: 1px solid #2f3336;
        border-radius: 8px;
        selection-background-color: #2a9df4;
        gridline-color: #2f3336;
    }
    
    QTableView::item {
        padding: 6px;
        border: none;
    }
    
    QTableView::item:selected {
        background-color: #0078d4;
        color: white;
    }
    
    QTableView::item:hover {
        background-color: #3e3e3e;
    }
    
    QHeaderView::section {
        background-color: #1b1d1e;
        color: #cfcfcf;
        padding: 10px;
        border: none;
        border-bottom: 1px solid #2f3336;
        font-weight: 700;
        letter-spacing: 0.3px;
    }
    
    /* ========== Tree Views ========== */
    QTreeView {
        background-color: #2d2d2d;
        border: 1px solid #3e3e3e;
        border-radius: 4px;
        selection-background-color: #0078d4;
    }
    
    QTreeView::item {
        padding: 6px;
        border: none;
    }
    
    QTreeView::item:selected {
        background-color: #0078d4;
        color: white;
    }
    
    QTreeView::item:hover {
        background-color: #3e3e3e;
    }
    
    QTreeView::branch:has-children:!has-siblings:closed,
    QTreeView::branch:closed:has-children:has-siblings {
        image: url(:/icons/branch_closed.png);
    }
    
    QTreeView::branch:open:has-children:!has-siblings,
    QTreeView::branch:open:has-children:has-siblings {
        image: url(:/icons/branch_open.png);
    }
    
    /* ========== Tabs ========== */
    QTabWidget::pane {
        background-color: #2d2d2d;
        border: 1px solid #3e3e3e;
        border-radius: 4px;
        top: -1px;
    }
    
    QTabBar::tab {
        background-color: #252525;
        color: #a0a0a0;
        padding: 8px 16px;
        border: none;
        border-bottom: 2px solid transparent;
    }
    
    QTabBar::tab:selected {
        background-color: #2d2d2d;
        color: #ffffff;
        border-bottom: 2px solid #0078d4;
    }
    
    QTabBar::tab:hover:!selected {
        background-color: #2d2d2d;
        color: #ffffff;
    }
    
    /* ========== Spin Boxes ========== */
    QSpinBox {
        background-color: #2d2d2d;
        border: 1px solid #3e3e3e;
        border-radius: 4px;
        padding: 6px 10px;
        color: #e0e0e0;
    }
    
    QSpinBox:focus {
        border: 1px solid #0078d4;
    }
    
    QSpinBox::up-button,
    QSpinBox::down-button {
        width: 16px;
        border: none;
        background-color: transparent;
    }
    
    QSpinBox::up-button:hover,
    QSpinBox::down-button:hover {
        background-color: #3e3e3e;
    }
    
    /* ========== Sliders ========== */
    QSlider::groove:horizontal {
        background-color: #3e3e3e;
        height: 4px;
        border-radius: 2px;
    }
    
    QSlider::handle:horizontal {
        background-color: #0078d4;
        width: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }
    
    QSlider::handle:horizontal:hover {
        background-color: #1084d8;
    }
    
    QSlider::sub-page:horizontal {
        background-color: #0078d4;
        border-radius: 2px;
    }
    
    /* ========== List Widgets ========== */
    QListWidget {
        background-color: #2d2d2d;
        border: 1px solid #3e3e3e;
        border-radius: 4px;
        outline: none;
    }
    
    QListWidget::item {
        padding: 8px;
        border: none;
        border-bottom: 1px solid #3e3e3e;
    }
    
    QListWidget::item:selected {
        background-color: #0078d4;
        color: white;
    }
    
    QListWidget::item:hover {
        background-color: #3e3e3e;
    }
    
    QListWidget::item:selected:active {
        background-color: #0078d4;
    }
    
    QListWidget::item:selected:!active {
        background-color: #3e3e3e;
    }
    
    /* ========== Menu Bar ========== */
    QMenuBar {
        background-color: #1e1e1e;
        border-bottom: 1px solid #3e3e3e;
        padding: 2px;
    }
    
    QMenuBar::item {
        padding: 6px 12px;
        background-color: transparent;
    }
    
    QMenuBar::item:selected {
        background-color: #3e3e3e;
        border-radius: 4px;
    }
    
    QMenuBar::item:pressed {
        background-color: #0078d4;
    }
    
    QMenu {
        background-color: #2d2d2d;
        border: 1px solid #3e3e3e;
        border-radius: 4px;
        padding: 4px;
    }
    
    QMenu::item {
        padding: 8px 32px 8px 16px;
        border: none;
        border-radius: 4px;
        margin: 2px 4px;
    }
    
    QMenu::item:selected {
        background-color: #0078d4;
    }
    
    QMenu::separator {
        height: 1px;
        background-color: #3e3e3e;
        margin: 4px 8px;
    }
    
    QMenu::indicator {
        width: 16px;
        height: 16px;
    }
    
    /* ========== Status Bar ========== */
    QStatusBar {
        background-color: #1e1e1e;
        border-top: 1px solid #3e3e3e;
        color: #a0a0a0;
    }
    
    QStatusBar::item {
        border: none;
        padding: 4px 8px;
    }
    
    /* ========== Tool Tips ========== */
    QToolTip {
        background-color: #2d2d2d;
        color: #e0e0e0;
        border: 1px solid #3e3e3e;
        border-radius: 4px;
        padding: 6px 10px;
    }
    
    /* ========== Splitter ========== */
    QSplitter::handle {
        background-color: #3e3e3e;
    }
    
    QSplitter::handle:horizontal {
        width: 2px;
    }
    
    QSplitter::handle:vertical {
        height: 2px;
    }
    
    QSplitter::handle:hover {
        background-color: #0078d4;
    }
    
    /* ========== Frame ========== */
    QFrame {
        border: 1px solid #3e3e3e;
        border-radius: 4px;
        background-color: #2d2d2d;
    }
    
    QFrame#noBorder {
        border: none;
        background-color: transparent;
    }
    
    QFrame#card {
        background-color: #202328;
        border: 1px solid #2b2f31;
        border-radius: 12px;
        padding: 16px;
        min-height: 120px;
    }
    
    /* ========== Size Policies ========== */
    QFrame#sidebar {
        background-color: #191b1c;
        border-right: 1px solid #2b2f31;
    }
    
    QFrame#header {
        background-color: #252525;
        border-bottom: 1px solid #3e3e3e;
        padding: 16px;
    }
    """