"""The owner's choices that outlive a restart — %APPDATA%\\JuiceMate\\settings.json (folders.py).

Everything the menu and the settings window change lives here (docs/architecture.md §6a). A missing
or broken file means the defaults; a broken field means that field's default — the app must start on
a clean PC (the second one) without anyone writing a config, and one bad value must not cost the rest.

The object is shared: the poll loop reads it every tick, the menu changes it. The settings window is
another process (ui/settings_app.py) that writes the same file; the poll loop picks that up with
`reload_if_changed()`. Fields are replaced whole, never mutated in place, so a reader sees one value
or the other.
"""

import contextlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from juice_mate import folders
from juice_mate.core.alerts import KINDS as ALERT_KINDS
from juice_mate.core.arrange import PLACES, DevicePref
from juice_mate.core.reading import Kind

log = logging.getLogger(__name__)

# What TrafficMonitor showed on the owner's taskbar (config.ini, 2026-10-20), minus CPU temperature.
DEFAULT_SENSORS = ["net.up", "net.down", "cpu.load", "gpu.load"]
SOURCES = ("claude", "bluetooth", "hator")
# What the invisible Claude Code run asks (sources/claude_run.py); its answer becomes a notification.
# `{news}` becomes the last day's tech headlines (sources/news.py). An empty string: the run still
# renews the token and starts the window, silently. The owner wants the day's tech news (2026-10-22),
# in Russian, the owner's language.
NEWS_PROMPT = (
    "Tech news headlines from the last 24 hours:\n{news}\n\n"
    "Pick the two that matter most to an ordinary tech user: a new device and what it can do, a new AI "
    "model, a major launch, release or deal. Skip politics, lawsuits, deals of the day and opinion "
    "pieces. For each, one line in Russian, at most 20 words: what happened and why it is interesting. "
    "Start each line with an emoji. No intro, no links, nothing else."
)
DEFAULT_PROMPT = NEWS_PROMPT


def _path() -> Path:
    return folders.data() / "settings.json"


@dataclass
class Settings:
    sensors: list[str] = field(default_factory=lambda: list(DEFAULT_SENSORS))
    # Whole sources: a PC without Claude Code, or without the Hator dongle, switches them off.
    sources: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(SOURCES, True))
    # Per item key (`bluetooth:…`, `hator:…`): {"name": str, "kind": Kind value, "hidden": bool}.
    devices: dict[str, dict[str, Any]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)  # item keys the owner put in order
    placement: dict[str, str] = field(default_factory=dict)  # item key → a place of core.arrange.PLACES
    battery_low: int = 20  # red below
    battery_alert: int = 15  # a notification below
    usage_high: int = 80  # Claude red from
    busy_percent: int = 95  # a sensor's load red from
    hot_celsius: int = 85  # GPU temperature red from
    alerts: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(ALERT_KINDS, True))
    claude_reset_time: bool = True  # `5h 45% →16:00`
    claude_left: bool = False  # show what is left instead of what is used
    # Run Claude Code when the 5-hour window is not running. Off until ticked in the menu: it spends
    # the account's quota, and the second PC's user never asked for it.
    keep_claude_window: bool = False
    claude_prompt: str = DEFAULT_PROMPT

    def __post_init__(self) -> None:
        self._lock = threading.RLock()  # the poll loop reloads, the menu changes: one at a time
        self._mtime: int | None = None  # the file as last read or written by this process

    # ── reading ────────────────────────────────────────────────────────────

    def source_on(self, source: str) -> bool:
        return self.sources.get(source, True)

    def alert_on(self, kind: str) -> bool:
        return self.alerts.get(kind, True)

    def device_prefs(self) -> dict[str, DevicePref]:
        prefs = {}
        for item_key, raw in self.devices.items():
            kind = raw.get("kind")
            name = raw.get("name")
            prefs[item_key] = DevicePref(
                name=name if isinstance(name, str) and name else None,
                kind=Kind(kind) if isinstance(kind, str) and kind in {k.value for k in Kind} else None,
                hidden=bool(raw.get("hidden", False)),
            )
        return prefs

    # ── changing (menu, settings window) ───────────────────────────────────

    def toggle_sensor(self, sensor: str) -> None:
        self.sensors = [s for s in self.sensors if s != sensor] if sensor in self.sensors else [*self.sensors, sensor]

    def toggle_source(self, source: str) -> None:
        self.sources = {**self.sources, source: not self.source_on(source)}

    def set_device(self, item_key: str, **changes: Any) -> None:
        """`name=`, `kind=`, `hidden=`; an empty name or a `None` kind goes back to what was found."""
        entry = {**self.devices.get(item_key, {}), **changes}
        entry = {k: v for k, v in entry.items() if v not in (None, "", False)}
        self.devices = {
            **{k: v for k, v in self.devices.items() if k != item_key},
            **({item_key: entry} if entry else {}),
        }

    def set_in(self, name: str, key: str, value: Any) -> bool:
        """One entry of a map field (`sources`, `alerts`, `placement`); `None` removes it."""
        current = getattr(self, name, None)
        if not isinstance(current, dict):
            return False
        changed = {k: v for k, v in current.items() if k != key}
        if value is not None:
            changed[key] = value
        return self.assign(name, changed)

    def change(self, edit: Callable[["Settings"], object], path: Path | None = None) -> bool:
        """Read what another process may have written, edit, save — as one step, so a menu click never
        saves this process's stale copy over the settings window's change."""
        with self._lock:
            self.reload_if_changed(path)
            edit(self)
            return self.save(path)

    def assign(self, name: str, value: Any) -> bool:
        """Set one field from outside — the settings window — only if the value has the field's shape."""
        if name not in {f.name for f in fields(Settings)}:
            return False
        default = getattr(Settings(), name)
        if not _fits(default, value):
            return False
        setattr(self, name, _merged(default, value))
        self._clean()
        return True

    # ── the file ───────────────────────────────────────────────────────────

    @staticmethod
    def load(path: Path | None = None, strict: bool = False) -> "Settings":
        """A missing file is the defaults. An unreadable one (locked for a moment by the other process
        or an antivirus, half-written) is the defaults too — unless `strict`, which raises instead, so
        a caller about to save never writes defaults over everything the owner set."""
        path = path or _path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Settings()
        except (OSError, ValueError):
            if strict:
                raise
            log.exception("settings unreadable, using defaults")
            return Settings()
        settings = Settings()
        if not isinstance(raw, dict):
            return settings
        for f in fields(Settings):
            if f.name in raw and _fits(getattr(settings, f.name), raw[f.name]):
                setattr(settings, f.name, _merged(getattr(settings, f.name), raw[f.name]))
            elif f.name in raw:
                log.warning("settings: %s ignored, not a %s", f.name, type(getattr(settings, f.name)).__name__)
        settings._clean()
        with contextlib.suppress(OSError):
            settings._mtime = path.stat().st_mtime_ns
        return settings

    def _clean(self) -> None:
        self.placement = {k: v for k, v in self.placement.items() if v in PLACES}
        self.devices = {k: v for k, v in self.devices.items() if isinstance(v, dict)}

    def reload_if_changed(self, path: Path | None = None) -> bool:
        """Take what another process (the settings window) wrote; True when anything was read."""
        path = path or _path()
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            return False
        if mtime == self._mtime:
            return False
        with self._lock:
            try:
                fresh = Settings.load(path, strict=True)
            except (OSError, ValueError):
                log.warning("settings changed but unreadable for now; keeping the current ones")
                return False  # _mtime unchanged: the next tick tries again
            for f in fields(Settings):
                setattr(self, f.name, getattr(fresh, f.name))
            self._mtime = mtime
        return True

    def save(self, path: Path | None = None) -> bool:
        """True when the file now holds these settings. A temp file of this process's own (two
        processes write here), then an atomic replace, retried briefly while the other side has the
        file open."""
        path = path or _path()
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f"settings.{os.getpid()}.tmp")
                temporary.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
                for attempt in range(5):
                    try:
                        temporary.replace(path)  # atomic: a crash mid-write never leaves half a file
                        break
                    except PermissionError:
                        if attempt == 4:
                            raise
                        time.sleep(0.05)
                self._mtime = path.stat().st_mtime_ns  # our own write is not news to reload
                return True
            except OSError:
                log.exception("could not save settings")
                return False


def _fits(default: Any, value: Any) -> bool:
    """The file's value has the default's shape: bool is not an int here, lists hold strings, dicts
    map strings to the default's value type."""
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(default, bool) and isinstance(value, bool)
    if isinstance(default, list):
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if isinstance(default, dict):
        if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
            return False
        sample = next(iter(default.values()), None)
        return sample is None or all(_fits(sample, v) for v in value.values())
    return isinstance(value, type(default))


def _merged(default: Any, value: Any) -> Any:
    """Switch maps keep the defaults for keys the file does not name: a new source or alert kind added
    in an update starts on, not missing."""
    if isinstance(default, dict) and isinstance(next(iter(default.values()), None), bool):
        return {**default, **value}
    return value
