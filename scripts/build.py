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

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
ICON = BUILD / "icon.ico"
BOLT = chr(0xE945)  # Segoe Fluent Icons LightningBolt


def make_icon() -> None:
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(image)
    canvas.rounded_rectangle((8, 8, size - 8, size - 8), radius=56, fill=(46, 160, 67))
    try:
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype("SegoeIcons.ttf", 150)
        canvas.text((size / 2, size / 2), BOLT, font=font, fill="white", anchor="mm")
    except OSError:  # a build machine without the icon font: a plain bolt shape
        canvas.polygon([(150, 40), (80, 140), (125, 140), (105, 216), (180, 112), (135, 112)], fill="white")
    BUILD.mkdir(exist_ok=True)
    image.save(ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main() -> int:
    make_icon()
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
