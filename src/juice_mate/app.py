"""Entry point: `python -m juice_mate` puts the panel on the taskbar; `--dump` prints every reading once.

Runs windowed (pythonw / PyInstaller --windowed): there is no console, so everything worth knowing
goes to %APPDATA%\\JuiceMate\\juice-mate.log (folders.py).
"""

import argparse
import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

from juice_mate import folders, quit
from juice_mate.core.alerts import NEWS, Alert, Alerts
from juice_mate.core.arrange import LEFT, RIGHT, SECOND_LEFT, SECOND_RIGHT, arrange, personalise
from juice_mate.core.display import Item, items, metric_item
from juice_mate.core.metric import Metric, Unit, short
from juice_mate.core.reading import Kind, Reading, level
from juice_mate.settings import Settings
from juice_mate.sources import Sensor, Source, poll_all
from juice_mate.sources.bluetooth import Bluetooth
from juice_mate.sources.claude import Claude
from juice_mate.sources.claude_run import ClaudeRun, find_claude
from juice_mate.sources.hator import Hator
from juice_mate.sources.system import (
    CpuLoad,
    DiskSpeed,
    DiskUsage,
    GpuLoad,
    GpuTemperature,
    MemoryLoad,
    MemoryUsed,
    NetworkSpeed,
    Ping,
    VideoMemoryUsed,
)

log = logging.getLogger("juice_mate")

TICK_SECONDS = 2  # system sensors, like TrafficMonitor's one-second-ish refresh
BATTERY_SECONDS = 30  # batteries move slowly; Bluetooth enumeration is not free
_ERROR_ALREADY_EXISTS = 183
_DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

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
        MemoryUsed(),
        VideoMemoryUsed(),
        Ping(),
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
        unit = "" if m.unit in (Unit.CELSIUS, Unit.BYTES, Unit.MILLISECONDS) else m.unit  # short() writes "52°", "8G"
        print(f"  {m.name:<32} {short(m):>6} {unit:<3}  {m.error or ''}")


def _log_to_file(name: str = "juice-mate.log") -> None:
    folder = folders.data()
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / name, maxBytes=512_000, backupCount=1, encoding="utf-8")
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


SOURCE_NAMES = {"claude": "Claude usage", "bluetooth": "Bluetooth devices", "hator": "HATOR mouse"}


def panel_items(
    readings: list[Reading], metrics: list[Metric], settings: Settings, now: datetime
) -> dict[str, list[Item]]:
    """Readings and sensor values → items per place, with the owner's names, icons, thresholds, order."""
    shown = items(
        personalise(readings, settings.device_prefs()),
        now,
        settings.battery_low,
        settings.usage_high,
        settings.claude_reset_time,
        settings.claude_left,
    )
    shown += [metric_item(m, now, settings.busy_percent, settings.hot_celsius) for m in metrics]
    return arrange(shown, settings.order, settings.placement)


def run() -> None:
    from juice_mate.panel.window import MenuEntry, Panel
    from juice_mate.tray.toasts import Toasts
    from juice_mate.ui.settings_app import Entry, write_items
    from juice_mate.update import autostart
    from juice_mate.update.updater import Updater

    stop, wake, refresh = threading.Event(), threading.Event(), threading.Event()
    updater = Updater()
    settings = Settings.load()
    catalog = sensors()
    claude_run = ClaudeRun(lambda: settings.claude_prompt)
    # By the names of settings.SOURCES: a source switched off is not polled at all.
    named: dict[str, Source] = {
        "claude": Claude(run=claude_run, keep_window=lambda: settings.keep_claude_window),
        "bluetooth": Bluetooth(),
        "hator": Hator(),
    }
    sources = list(named.values())

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

    def toggle_source(source: str) -> None:
        settings.toggle_source(source)
        settings.save()
        refresh_now()

    def toggle_keep_window() -> None:
        settings.keep_claude_window = not settings.keep_claude_window
        settings.save()

    seen: dict[str, Entry] = {}  # everything that ever reported, for the settings window's list

    def remember(readings: list[Reading]) -> None:
        """New devices go to items.json, the settings window's list of what can be on the panel."""
        before = dict(seen)
        for r in readings:
            group = "usage" if r.kind is Kind.CLAUDE else "device"
            seen[f"{r.source}:{r.device_id}"] = Entry(f"{r.source}:{r.device_id}", r.name, group, r.kind.value)
        if seen != before:
            write_items([*seen.values(), *(Entry(f"system:{s.sensor}", s.name, "sensor") for s in catalog)])

    def open_settings() -> None:
        """The window is a process of its own (ui/settings_app.py); it returns at once."""
        try:
            subprocess.Popen([*autostart.launch(), "--settings"], creationflags=_DETACHED)  # noqa: S603
        except OSError:
            log.exception("could not open the settings window")

    def ask_now() -> None:
        claude_run.request("asked from the menu", now_please=True)  # a thread of its own: returns at once

    def menu() -> list[MenuEntry | None]:
        ready = updater.ready
        update = [MenuEntry(f"Restart to update to {ready}", updater.restart_now), None] if ready else []
        shown: list[MenuEntry | None] = [
            MenuEntry(s.name, lambda s=s: toggle_sensor(s.sensor), checked=s.sensor in settings.sensors)  # type: ignore[misc]
            for s in catalog
        ]
        on: list[MenuEntry | None] = [
            MenuEntry(SOURCE_NAMES[name], lambda name=name: toggle_source(name), checked=settings.source_on(name))  # type: ignore[misc]
            for name in named
        ]
        claude = settings.source_on("claude")
        return [
            *update,
            MenuEntry("Settings…", open_settings),
            None,
            MenuEntry("Show", children=shown),
            MenuEntry("Sources", children=on),
            MenuEntry("Refresh now", refresh_now),
            *([MenuEntry("Ask Claude now", ask_now)] if claude and find_claude() else []),
            *(
                [
                    MenuEntry(
                        "Keep Claude's 5-hour window running", toggle_keep_window, checked=settings.keep_claude_window
                    )
                ]
                if claude
                else []
            ),
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
    quit.listen(quit_app)  # the settings window's power button
    updater.start()
    alerts, toasts = Alerts(), Toasts()
    readings: list[Reading] = []
    batteries_due = 0.0
    while not stop.is_set():
        now = time.monotonic()
        if now >= batteries_due or refresh.is_set():
            refresh.clear()
            readings = poll_all([source for name, source in named.items() if settings.source_on(name)])
            remember(readings)
            batteries_due = now + BATTERY_SECONDS
            for alert in alerts.check(readings, settings.battery_alert):
                if settings.alert_on(alert.kind):
                    toasts.show(alert)
        reply = claude_run.take_reply()
        if reply and settings.alert_on(NEWS):
            toasts.show(Alert("claude:run", "Claude", reply, NEWS))
        if settings.reload_if_changed():  # the settings window saved something
            batteries_due = 0.0
            continue
        moment = datetime.now()
        metrics = [s.read() for s in catalog if s.sensor in settings.sensors]
        places = panel_items(readings, metrics, settings, moment)
        panel.show(places[RIGHT] + places[SECOND_RIGHT], places[LEFT] + places[SECOND_LEFT])
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
    parser.add_argument("--settings", action="store_true", help="open the settings window")
    parser.add_argument("--debug", action="store_true", help="with --settings: the page's developer tools")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        # A windowed build (pythonw, PyInstaller --windowed) has no console: the streams are None.
        if stream is not None:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if args.dump:
        dump()
        return
    if args.settings:
        from juice_mate.ui import settings_app

        _log_to_file("settings.log")  # its own file: two processes must not rotate one log
        settings_app.run()
        return
    _log_to_file()
    folders.migrate()
    if not _first_instance():
        log.info("already running")
        return
    run()
