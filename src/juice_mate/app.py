"""Entry point: `python -m juice_mate` puts the panel on the taskbar; `--dump` prints every reading once.

Runs windowed (pythonw / PyInstaller --windowed): there is no console, so everything worth knowing
goes to %APPDATA%\\JuiceMate\\juice-mate.log (folders.py).
"""

import argparse
import ctypes
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from juice_mate import folders, quit
from juice_mate.core.alerts import NEWS, Alert, Alerts
from juice_mate.core.arrange import LEFT, RIGHT, SECOND_LEFT, SECOND_RIGHT, arrange, personalise
from juice_mate.core.card import Card
from juice_mate.core.card import card_for as build_card
from juice_mate.core.display import Item, items, metric_item
from juice_mate.core.history import History
from juice_mate.core.metric import Metric, Unit, short
from juice_mate.core.reading import Kind, Reading, level
from juice_mate.panel.menu import MenuEntry
from juice_mate.settings import Settings
from juice_mate.sources import Sensor, Source, news, poll_all
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


def recent_news() -> list[MenuEntry | None]:
    """The menu's last five told stories; a click opens the article."""
    entries: list[MenuEntry | None] = []
    for story in news.recent(5):
        label = story.text if len(story.text) <= 46 else story.text[:45].rstrip() + "…"
        url = story.url
        entries.append(MenuEntry(label, (lambda url=url: open_article(url)) if url else None, icon=ICONS["article"]))  # type: ignore[misc]
    return entries


def open_article(url: str) -> None:
    """Only https links to the news feeds' own sites: the answer of a language model must not be
    able to make Juice-Mate open whatever it writes."""
    safe = news.safe_url(url)
    if safe is None:
        log.warning("not opening %r: not a news site link", url)
        return
    threading.Thread(target=lambda: os.startfile(safe), name="open", daemon=True).start()  # noqa: S606


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
# The right-click menu's glyphs: Segoe Fluent Icons, written with chr() (literal Private Use Area
# characters have turned invisible in editors before).
ICONS = {
    "settings": chr(0xE713),
    "show": chr(0xE890),
    "sources": chr(0xE8F1),
    "refresh": chr(0xE72C),
    "claude": "✳",
    "keep": chr(0xE895),
    "startup": chr(0xE823),
    "quit": chr(0xE7E8),
    "update": chr(0xE896),
    "bluetooth": chr(0xE702),
    "hator": chr(0xE962),
    "news": chr(0xE789),  # a newspaper, roughly: the Fluent "Reading list"
    "article": chr(0xE8A7),  # open in a new window
}


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


HISTORY_KEEP = 2 * 24 * 3600  # two days of batteries and usage windows
HISTORY_STEP = 120  # one sample per two minutes
HISTORY_SAVE_EVERY = 600


def _history_path() -> Path:
    return folders.data() / "history.json"


def load_history(history: History) -> None:
    try:
        history.load(json.loads(_history_path().read_text(encoding="utf-8")), time.time())
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        log.exception("history unreadable, starting afresh")


def save_history(history: History) -> None:
    path = _history_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(history.dump()), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        log.exception("could not save the history")


def local_clock(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M")


def run() -> None:
    from juice_mate.panel.window import Panel
    from juice_mate.tray.toasts import Toasts
    from juice_mate.ui.settings_app import Entry, write_items
    from juice_mate.update import autostart
    from juice_mate.update.updater import Updater

    stop, wake, refresh = threading.Event(), threading.Event(), threading.Event()
    updater = Updater()
    settings = Settings.load()
    catalog = sensors()
    claude_run = ClaudeRun(lambda: settings.claude_prompt, topics=lambda: settings.topic_words())
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

    # Menu changes go through settings.change(): it reads what the settings window may have just
    # written before editing, so a click never saves a stale copy over it.
    def toggle_sensor(sensor: str) -> None:
        settings.change(lambda s: s.toggle_sensor(sensor))
        wake.set()

    def toggle_source(source: str) -> None:
        settings.change(lambda s: s.toggle_source(source))
        refresh_now()

    def toggle_keep_window() -> None:
        settings.change(lambda s: setattr(s, "keep_claude_window", not s.keep_claude_window))

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
        update: list[MenuEntry | None] = (
            [
                MenuEntry(f"Restart to update to {ready}", updater.restart_now, icon=ICONS["update"], style="accent"),
                None,
            ]
            if ready
            else []
        )
        shown: list[MenuEntry | None] = [
            MenuEntry(
                s.name,
                lambda s=s: toggle_sensor(s.sensor),  # type: ignore[misc]
                checked=s.sensor in settings.sensors,
                icon=metric_item(Metric(s.sensor, s.name, None, Unit.PERCENT), datetime.now()).glyph,
            )
            for s in catalog
        ]
        on: list[MenuEntry | None] = [
            MenuEntry(
                SOURCE_NAMES[name],
                lambda name=name: toggle_source(name),  # type: ignore[misc]
                checked=settings.source_on(name),
                icon=ICONS[name],
            )
            for name in named
        ]
        claude = settings.source_on("claude")
        return [
            *update,
            MenuEntry("Settings…", open_settings, icon=ICONS["settings"]),
            None,
            MenuEntry("Show", children=shown, icon=ICONS["show"]),
            MenuEntry("Sources", children=on, icon=ICONS["sources"]),
            *([MenuEntry("Recent news", children=recent_news(), icon=ICONS["news"])] if news.recent(1) else []),
            MenuEntry("Refresh now", refresh_now, icon=ICONS["refresh"]),
            *([MenuEntry("Ask Claude now", ask_now, icon=ICONS["claude"])] if claude and find_claude() else []),
            *(
                [
                    MenuEntry(
                        "Keep the 5-hour window",
                        toggle_keep_window,
                        checked=settings.keep_claude_window,
                        icon=ICONS["keep"],
                    )
                ]
                if claude
                else []
            ),
            MenuEntry("Start with Windows", toggle_autostart, checked=autostart.is_enabled(), icon=ICONS["startup"]),
            None,
            MenuEntry("Quit Juice-Mate", quit_app, icon=ICONS["quit"], style="danger"),
        ]

    # What the hover card needs: two histories and the latest of everything, by item key.
    batteries = History(keep=HISTORY_KEEP, step=HISTORY_STEP)  # batteries and usage windows, on disk
    sensed = History(keep=3600, step=TICK_SECONDS)  # sensors, the last hour, memory only
    load_history(batteries)
    # Replaced whole each tick, never cleared in place: the panel thread reads it at any moment.
    latest: list[dict[str, tuple[Item, Reading | None, Metric | None]]] = [{}]

    def card_for(key: str) -> Card | None:
        """On the panel thread: only what is already in memory."""
        found = latest[0].get(key)
        if found is None:
            return None
        shown, reading, metric = found
        samples = (sensed if metric is not None else batteries).series(key)
        return build_card(shown, reading, metric, samples, time.time(), local_clock)

    panel = Panel(menu, on_click=open_target, card_for=card_for)
    if not panel.start():
        log.warning("the taskbar panel could not attach; falling back to tray icons")
        from juice_mate.tray.icons import TrayIcons

        TrayIcons(sources).run()
        return
    log.info("panel attached")
    quit.listen(quit_app)  # the settings window's power button
    updater.start()
    alerts, toasts = Alerts(), Toasts()
    history_saved = time.time()
    readings: list[Reading] = []
    batteries_due = 0.0
    while not stop.is_set():
        now = time.monotonic()
        if now >= batteries_due or refresh.is_set():
            refresh.clear()
            readings = poll_all([source for name, source in named.items() if settings.source_on(name)])
            remember(readings)
            stamp = time.time()
            for r in readings:
                if r.connected and r.percent is not None and r.error is None:
                    batteries.add(f"{r.source}:{r.device_id}", stamp, float(r.percent), bool(r.charging))
            if stamp - history_saved >= HISTORY_SAVE_EVERY:
                save_history(batteries)
                history_saved = stamp
            batteries_due = now + BATTERY_SECONDS
            # As the panel shows them: a hidden device stays quiet, a renamed one alerts by its new name.
            for alert in alerts.check(personalise(readings, settings.device_prefs()), settings.battery_alert):
                if settings.alert_on(alert.kind):
                    toasts.show(alert)
        reply = claude_run.take_reply()
        if reply is not None and reply.news:
            news.remember(reply.stories, time.time())
        if reply is not None and settings.alert_on(NEWS):
            if reply.news:
                toasts.show_news(reply.stories)
            else:
                toasts.show(Alert("claude:run", "Claude", reply.text, NEWS))
        if settings.reload_if_changed():  # the settings window saved something
            batteries_due = 0.0
            continue
        moment = datetime.now()
        metrics = [s.read() for s in catalog if s.sensor in settings.sensors]
        stamp = time.time()
        for m in metrics:
            if m.value is not None:
                sensed.add(f"system:{m.sensor}", stamp, m.value)
        places = panel_items(readings, metrics, settings, moment)
        by_key = {f"{r.source}:{r.device_id}": r for r in personalise(readings, settings.device_prefs())}
        by_sensor = {f"system:{m.sensor}": m for m in metrics}
        latest[0] = {
            it.key: (it, by_key.get(it.key), by_sensor.get(it.key)) for items_ in places.values() for it in items_
        }
        panel.show(places[RIGHT], places[LEFT], places[SECOND_RIGHT], places[SECOND_LEFT])
        wake.wait(TICK_SECONDS)
        wake.clear()
    save_history(batteries)
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
