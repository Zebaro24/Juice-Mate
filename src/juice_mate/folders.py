"""Where Juice-Mate keeps its own files: %APPDATA%\\JuiceMate — settings, the log, and the working
folder of the Claude Code run.

Not %LOCALAPPDATA%\\JuiceMate: that is Velopack's install folder. A settings file there made Setup
believe the app was already installed (2026-10-22), and an uninstall deletes the folder whole.
"""

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

NAME = "JuiceMate"


def data() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / NAME


def _old() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / NAME


def migrate(new: Path | None = None, old: Path | None = None) -> None:
    """Carry settings.json over from where versions up to 0.3.0 kept it, once."""
    new, old = new or data(), old or _old()
    source, target = old / "settings.json", new / "settings.json"
    if target.exists() or not source.is_file():
        return
    try:
        new.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    except OSError:
        log.exception("could not carry the settings over")
