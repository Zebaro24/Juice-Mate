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

from juice_mate.core.alerts import Alert, Alerts
from juice_mate.core.display import items, metric_item
from juice_mate.core.metric import Unit, short
from juice_mate.core.reading import Reading, level
from juice_mate.sources import Sensor, Source, poll_all
from juice_mate.sources.bluetooth import Bluetooth
from juice_mate.sources.claude import Claude
from juice_mate.sources.claude_run import ClaudeRun
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

TICK_SECONDS = 2  # system sensors, like TrafficMonitor's one-second-ish refresh
BATTERY_SECONDS = 30  # batteries move slowly; Bluetooth enumeration is not free
_ERROR_ALREADY_EXISTS = 183

# Where a left click on an item takes you, by the item key's source.
CLICK_TARGETS = {
    "claude": "https://claude.ai/settings/usage",
    "bluetooth": "ms-settings:bluetooth",
    "hator": "ms-settings:bluetooth",
    "system": "taskmgr",
}


def battery_sources() -> list[Source]:
    return [Claude(), Bluetooth(), Hator()]


def sensors() -> list[Sensor]:
    """Every sensor there is, in menu order; settings.sensors picks the ones on the panel."""
    return [
        NetworkSpeed("up"),
        NetworkSpeed("down"),
        CpuLoad(),
        GpuLoad(),
        GpuTemperature(),
        MemoryLoad(),
        DiskUsage("C:\\"),
        DiskSpeed("read"),
        DiskSpeed("write"),
    ]


def open_target(key: str) -> None:
    """Open what belongs to a clicked item, off the panel thread: ShellExecute may take a moment."""
    target = CLICK_TARGETS.get(key.split(":", 1)[0])
    if target is None:
        return

    def go() -> None:
        try:
            os.startfile(target)  # noqa: S606 — fixed targets from the table above, no user input
        except OSError:
            log.exception("could not open %s", target)

    threading.Thread(target=go, name="open", daemon=True).start()


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


def run() -> None:
    from juice_mate.panel.window import MenuEntry, Panel
    from juice_mate.settings import Settings
    from juice_mate.tray.toasts import Toasts
    from juice_mate.update import autostart
    from juice_mate.update.updater import Updater

    stop, wake, refresh = threading.Event(), threading.Event(), threading.Event()
    updater = Updater()
    settings = Settings.load()
    catalog = sensors()
    claude_run = ClaudeRun(lambda: settings.claude_prompt)
    sources: list[Source] = [
        Claude(run=claude_run, keep_window=lambda: settings.keep_claude_window),
        Bluetooth(),
        Hator(),
    ]

    def quit_app() -> None:
        stop.set()
        wake.set()

    def toggle_autostart() -> None:
        try:
            autostart.set_enabled(not autostart.is_enabled())
        except OSError:
            log.exception("could not change autostart")

    def refresh_now() -> None:
        refresh.set()
        wake.set()

    def toggle_sensor(sensor: str) -> None:
        settings.toggle_sensor(sensor)
        settings.save()
        wake.set()

    def toggle_keep_window() -> None:
        settings.keep_claude_window = not settings.keep_claude_window
        settings.save()

    def menu() -> list[MenuEntry | None]:
        ready = updater.ready
        update = [MenuEntry(f"Restart to update to {ready}", updater.restart_now), None] if ready else []
        shown: list[MenuEntry | None] = [
            MenuEntry(s.name, lambda s=s: toggle_sensor(s.sensor), checked=s.sensor in settings.sensors)  # type: ignore[misc]
            for s in catalog
        ]
        return [
            *update,
            MenuEntry("Show", children=shown),
            MenuEntry("Refresh now", refresh_now),
            MenuEntry("Keep Claude's 5-hour window running", toggle_keep_window, checked=settings.keep_claude_window),
            MenuEntry("Start with Windows", toggle_autostart, checked=autostart.is_enabled()),
            None,
            MenuEntry("Quit Juice-Mate", quit_app),
        ]

    panel = Panel(menu, on_click=open_target)
    if not panel.start():
        log.warning("the taskbar panel could not attach; falling back to tray icons")
        from juice_mate.tray.icons import TrayIcons

        TrayIcons(sources).run()
        return
    log.info("panel attached")
    updater.start()
    alerts, toasts = Alerts(), Toasts()
    readings: list[Reading] = []
    batteries_due = 0.0
    while not stop.is_set():
        now = time.monotonic()
        if now >= batteries_due or refresh.is_set():
            refresh.clear()
            readings = poll_all(sources)
            batteries_due = now + BATTERY_SECONDS
            for alert in alerts.check(readings):
                toasts.show(alert)
        reply = claude_run.take_reply()
        if reply:
            toasts.show(Alert("claude:run", "Claude", reply))
        moment = datetime.now()
        shown = [metric_item(s.read(), moment) for s in catalog if s.sensor in settings.sensors]
        panel.show(items(readings, moment), shown)
        wake.wait(TICK_SECONDS)
        wake.clear()
    updater.stop()
    panel.stop()
    log.info("quit")


def main() -> None:
    from juice_mate.update.updater import startup

    # First, before argparse: Velopack runs the exe with its own hook arguments and expects it to exit.
    startup()
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
    run()
