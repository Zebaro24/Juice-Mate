#!/usr/bin/env python3
"""Build the windowed app into dist/JuiceMate/ (docs/architecture.md §4). Run inside the Poetry env:

    poetry run python scripts/build.py

PyInstaller `--onedir --windowed`: no console window, ever. The icon is drawn here rather than kept
as a binary in git. Velopack then packs dist/JuiceMate/ into Setup.exe + update packages — in CI,
because `vpk` is a .NET tool (.github/workflows/release.yml).
"""

import shutil
import subprocess
import sys
from pathlib import Path

from juice_mate.logo import icon

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
ICON = BUILD / "icon.ico"


def main() -> int:
    icon(ICON)
    shutil.rmtree(ROOT / "dist" / "JuiceMate", ignore_errors=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "JuiceMate",
        "--icon",
        str(ICON),
        "--paths",
        str(ROOT / "src"),
        # windows-toasts reaches WinRT through namespace packages PyInstaller cannot see by import.
        "--collect-submodules",
        "winrt",
        "--collect-binaries",
        "winrt",
        # The settings page (ui/settings.html) is read as package data at run time.
        "--collect-data",
        "juice_mate",
        "--workpath",
        str(BUILD / "pyinstaller"),
        "--specpath",
        str(BUILD),
        "--distpath",
        str(ROOT / "dist"),
        str(ROOT / "src" / "juice_mate" / "__main__.py"),
    ]
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
