"""Entry point: `python -m juice_mate` puts the panel on the taskbar; `--dump` prints every reading once.

Runs windowed (pythonw / PyInstaller --windowed): there is no console, so everything worth knowing
goes to %LOCALAPPDATA%\\JuiceMate\\juice-mate.log.
"""

import argparse
import ctypes
import logging
import os
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from juice_mate.core.display import items
from juice_mate.core.metric import Unit, short
from juice_mate.core.reading import level
from juice_mate.sources import Sensor, Source, poll_all
from juice_mate.sources.bluetooth import Bluetooth
from juice_mate.sources.hator import Hator
from juice_mate.sources.system import (
    CpuLoad,
    DiskSpeed,
    DiskUsage,
    GpuLoad,
    GpuTemperature,
    MemoryLoad,
    NetworkSpeed,
)

log = logging.getLogger("juice_mate")

POLL_SECONDS = 30
_ERROR_ALREADY_EXISTS = 183


def battery_sources() -> list[Source]:
    return [Bluetooth(), Hator()]


def sensors() -> list[Sensor]:
    """Every sensor there is. Which ones the panel shows is decided at step 08."""
    return [
        NetworkSpeed("up"),
        NetworkSpeed("down"),
        CpuLoad(),
        MemoryLoad(),
        GpuLoad(),
        GpuTemperature(),
        DiskUsage("C:\\"),
        DiskSpeed("read"),
        DiskSpeed("write"),
    ]


def dump() -> None:
    print("Batteries")
    readings = poll_all(battery_sources())
    for r in readings:
        state = r.error or ("connected" if r.connected else "disconnected — % is cached")
        percent = r.percent if r.percent is not None else "–"
        print(f"  {r.name:<32} {r.kind:<9} {percent:>4}  {level(r):<9} {state}")
    if not readings:
        print("  (no device reports a battery)")
    print("System")
    all_sensors = sensors()
    time.sleep(1)  # rates and loads need an interval
    for m in (s.read() for s in all_sensors):
        unit = "" if m.unit is Unit.CELSIUS else m.unit  # short() already writes "52°"
        print(f"  {m.name:<32} {short(m):>6} {unit:<3}  {m.error or ''}")


def _log_to_file() -> None:
    folder = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "JuiceMate"
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "juice-mate.log", maxBytes=512_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    sys.excepthook = lambda kind, value, tb: log.critical("unhandled", exc_info=(kind, value, tb))
    threading.excepthook = lambda args: log.critical("unhandled in %s", args.thread, exc_info=args.exc_value)


def _first_instance() -> bool:
    """A second copy would put a second panel on the taskbar."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _first_instance.handle = kernel32.CreateMutexW(None, False, "Local\\JuiceMate")  # type: ignore[attr-defined]
    return ctypes.get_last_error() != _ERROR_ALREADY_EXISTS


def run(sources: list[Source]) -> None:
    from juice_mate.panel.window import Panel

    stop, wake = threading.Event(), threading.Event()

    def quit_app() -> None:
        stop.set()
        wake.set()

    panel = Panel(on_refresh=wake.set, on_quit=quit_app)
    if not panel.start():
        log.warning("the taskbar panel could not attach; falling back to tray icons")
        from juice_mate.tray.icons import TrayIcons

        TrayIcons(sources).run()
        return
    log.info("panel attached")
    while not stop.is_set():
        panel.show(items(poll_all(sources), datetime.now()))
        wake.wait(POLL_SECONDS)
        wake.clear()
    panel.stop()
    log.info("quit")


def main() -> None:
    parser = argparse.ArgumentParser(prog="juice_mate")
    parser.add_argument("--dump", action="store_true", help="print every reading once and exit")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        # A windowed build (pythonw, PyInstaller --windowed) has no console: the streams are None.
        if stream is not None:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if args.dump:
        dump()
        return
    _log_to_file()
    if not _first_instance():
        log.info("already running")
        return
    run(battery_sources())
