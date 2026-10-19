"""Windows privilege and elevation helpers for device-level recovery."""

from __future__ import annotations

import ctypes
import os
import sys
from typing import Optional


def is_windows() -> bool:
    return os.name == "nt" or sys.platform.startswith("win")


def is_elevated() -> bool:
    """Return True if the current process has administrator rights."""
    if not is_windows():
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def requires_admin_for_source(source: Optional[str]) -> bool:
    """Return True when a source path requires a privileged raw-device handle."""
    if not source:
        return False

    value = str(source).strip()
    if not value:
        return False

    lowered = value.lower()
    if lowered.startswith('\\\\.\\') or lowered.startswith('\\\\?\\'):
        return True

    if len(value) >= 2 and value[1] == ':':
        drive = value[:1].upper()
        if drive.isalpha() and len(value) == 2:
            return True
        if drive.isalpha() and value[2:3] in ('\\', '/') and value[2:].rstrip('\\/') == '':
            return True

    return False


def request_elevation() -> bool:
    """Use the Windows UAC prompt to relaunch the app as administrator."""
    if not is_windows():
        return False

    try:
        app_path = os.path.abspath(sys.argv[0]) if sys.argv else None
        if not app_path:
            return False

        params = ' '.join(f'"{arg}"' for arg in sys.argv[1:])
        target = f'"{app_path}" {params}'.strip()
        result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None,
            'runas',
            sys.executable,
            target,
            None,
            1,
        )
        return int(result) > 32
    except Exception:
        return False


def ensure_admin_for_source(source: Optional[str], *, reason: Optional[str] = None) -> bool:
    """If a raw source requires admin, raise clearly instead of silently failing."""
    if not requires_admin_for_source(source):
        return True

    if is_elevated():
        return True

    raise PermissionError(
        reason
        or 'This source is a raw disk or volume and requires Windows administrator privileges.'
    )


__all__ = [
    'is_windows',
    'is_elevated',
    'requires_admin_for_source',
    'request_elevation',
    'ensure_admin_for_source',
]
