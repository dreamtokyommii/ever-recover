"""Presentation layer (GUI)."""

from .main_window import MainWindow
from .styles.dark_theme import get_dark_theme_stylesheet

__all__ = [
    'MainWindow',
    'get_dark_theme_stylesheet',
]