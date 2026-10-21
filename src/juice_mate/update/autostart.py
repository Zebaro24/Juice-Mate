"""Start with Windows — a per-user `Run` entry, no admin (docs/architecture.md §4).

The installed build (PyInstaller) starts its own exe. A dev checkout starts `pythonw -m juice_mate`
from the same environment, so the owner can try the toggle before there is an installer.
"""

import contextlib
import sys
import winreg
from pathlib import Path

RUN_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"
NAME = "JuiceMate"


def command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" -m juice_mate'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, NAME)
    except OSError:
        return False
    return bool(value)


def set_enabled(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, NAME)
