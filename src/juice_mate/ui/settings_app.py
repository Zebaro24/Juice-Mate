"""The settings window — a process of its own: `JuiceMate.exe --settings` (docs/architecture.md §6a).

Drawn by WebView2 (built into Windows 11) as a page in the style of Windows' own Settings app
(settings.html). A separate process, so a window waiting on the user never touches the taskbar's
thread, and a crash here never takes the panel with it.

The page talks to `Api` below. Every change reloads settings.json, changes one field and saves: the
panel process notices the new file within a tick (`Settings.reload_if_changed`). What can be on the
panel comes from items.json, which the panel process writes (`write_items`).
"""

import ctypes
import json
import logging
import os
import sys
import winreg
from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from juice_mate import folders, quit
from juice_mate.core.arrange import PLACES, default_place
from juice_mate.core.display import GLYPHS, SENSOR_GLYPHS
from juice_mate.core.reading import Kind
from juice_mate.settings import DEFAULT_PROMPT, NEWS_TOPICS, Settings

log = logging.getLogger(__name__)

TITLE = "Juice-Mate settings"
MUTEX = "Local\\JuiceMateSettings"
_ERROR_ALREADY_EXISTS = 183
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_ROUND = 33, 2  # Windows 11
_DWMWA_BORDER_COLOR = 34
NIGHT, LINE = "#0a0a19", "#23234a"  # settings.html's --night and --line
_WM_SETICON, _ICON_SMALL, _ICON_BIG = 0x0080, 0, 1
_IMAGE_ICON, _LR_LOADFROMFILE = 1, 0x0010
APP_ID = "Zebaro.JuiceMate.Settings"  # its own taskbar button, not pythonw's
PROJECT_URL = "https://github.com/Zebaro24/Juice-Mate"


@dataclass(frozen=True)
class Entry:
    """One thing that can be on the panel, as the panel process last saw it."""

    key: str
    name: str  # as the source found it
    group: str  # "usage", "device" or "sensor"
    kind: str | None = None  # a device's kind as found, a `Kind` value


def items_path() -> Path:
    return folders.data() / "items.json"


def write_items(entries: list[Entry]) -> None:
    """The panel process's side: what the settings window may list."""
    path = items_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps([asdict(e) for e in entries], ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        log.exception("could not write items.json")


def read_items() -> list[Entry]:
    try:
        raw = json.loads(items_path().read_text(encoding="utf-8"))
        return [Entry(**e) for e in raw if isinstance(e, dict)]
    except (OSError, ValueError, TypeError):
        return []


def accent() -> str:
    """Windows' accent colour as #rrggbb (the DWM key stores it as 0xAABBGGRR)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as key:
            value, _kind = winreg.QueryValueEx(key, "AccentColor")
        return f"#{value & 0xFF:02x}{(value >> 8) & 0xFF:02x}{(value >> 16) & 0xFF:02x}"
    except OSError:
        return "#0067c0"  # Windows 11's default blue


def _glyph(entry: Entry) -> str:
    if entry.group == "usage":
        return GLYPHS[Kind.CLAUDE]
    if entry.group == "sensor":
        sensor = entry.key.removeprefix("system:")
        prefix = max((p for p in SENSOR_GLYPHS if sensor == p or sensor.startswith(p + ".")), key=len, default="cpu")
        return SENSOR_GLYPHS[prefix]
    return GLYPHS.get(Kind(entry.kind) if entry.kind in {k.value for k in Kind} else Kind.OTHER, GLYPHS[Kind.OTHER])


class Api:
    """Called from the page's JavaScript (`pywebview.api.*`); returns plain JSON-able values.
    Private attributes are not exposed to the page."""

    def __init__(self) -> None:
        self._window: Any = None  # the pywebview window, set once it exists

    def state(self) -> dict[str, Any]:
        from juice_mate.update import autostart, updater

        settings = Settings.load()
        entries = read_items()
        return {
            "settings": {f: getattr(settings, f) for f in settings.__dataclass_fields__},
            "entries": [{**asdict(e), "glyph": _glyph(e), "place": default_place(e.key)} for e in entries],
            "kinds": {k.value: GLYPHS[k] for k in Kind if k is not Kind.CLAUDE},
            "places": list(PLACES),
            "autostart": autostart.is_enabled(),
            "accent": accent(),
            "version": updater.version(),
            "default_prompt": DEFAULT_PROMPT,
            "topics": NEWS_TOPICS,
        }

    # Every change: the file as it is now (strict: an unreadable file is not "defaults"), one field or
    # one entry changed, saved. Whole maps and lists are never sent from the page: they would undo
    # what the panel's menu changed since the page loaded. True only when the file was written.

    def _edit(self, edit: Callable[[Settings], bool]) -> bool:
        try:
            settings = Settings.load(strict=True)
        except (OSError, ValueError):
            log.warning("settings unreadable for now; change not saved")
            return False
        return edit(settings) and settings.save()

    def assign(self, name: str, value: Any) -> bool:
        if name in ("sources", "alerts", "placement", "sensors", "devices"):
            return False  # entries go through set_in / sensor / device
        return self._edit(lambda s: s.assign(name, value))

    def set_in(self, name: str, key: str, value: Any) -> bool:
        if name not in ("sources", "alerts", "placement"):
            return False
        return self._edit(lambda s: s.set_in(name, key, value))

    def sensor(self, sensor: str, on: bool) -> bool:
        def edit(s: Settings) -> bool:
            if (sensor in s.sensors) != bool(on):
                s.toggle_sensor(sensor)
            return True

        return self._edit(edit)

    def device(self, key: str, changes: dict[str, Any]) -> bool:
        allowed = {k: v for k, v in changes.items() if k in ("name", "kind", "hidden")}

        def edit(s: Settings) -> bool:
            s.set_device(key, **allowed)
            return True

        return self._edit(edit)

    def open_url(self, url: str) -> None:
        """Only the project's own page: the page must not become a way to launch anything."""
        if url == PROJECT_URL:
            os.startfile(url)  # noqa: S606 — a fixed URL, checked above

    def minimize(self) -> None:
        if self._window is not None:
            self._window.minimize()

    def close(self) -> None:
        """This window only; the panel keeps running."""
        if self._window is not None:
            self._window.destroy()

    def quit_all(self) -> None:
        """Juice-Mate entirely: the panel process first, then this window."""
        if not quit.request():
            log.info("no panel running to quit")
        self.close()

    def autostart(self, on: bool) -> bool:
        from juice_mate.update import autostart

        try:
            autostart.set_enabled(bool(on))
        except OSError:
            log.exception("could not change autostart")
        return autostart.is_enabled()


def _style_frame(title: str) -> None:
    """No Windows frame — the page draws its own title bar — but Windows 11's rounded corners and a
    hairline border in the page's colours, and the logo as the window's and taskbar button's icon."""
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if not hwnd:
        return
    dwm = ctypes.windll.dwmapi
    for attribute, value in (
        (_DWMWA_USE_IMMERSIVE_DARK_MODE, 1),
        (_DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_ROUND),
        (_DWMWA_BORDER_COLOR, _colorref(LINE)),
    ):
        data = ctypes.c_int(value)
        dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
    _set_icon(hwnd)


def _set_icon(hwnd: int) -> None:
    """WM_SETICON from an .ico drawn once into the data folder (logo.py); pythonw's own icon otherwise."""
    path = folders.data() / "icon.ico"
    try:
        if not path.exists():
            from juice_mate.logo import icon

            icon(path)
    except OSError:
        log.exception("could not draw the window icon")
        return
    user32 = ctypes.windll.user32
    user32.LoadImageW.restype = ctypes.c_void_p
    for which, size in ((_ICON_BIG, 32), (_ICON_SMALL, 16)):
        handle = user32.LoadImageW(None, str(path), _IMAGE_ICON, size, size, _LR_LOADFROMFILE)
        if handle:
            user32.SendMessageW(hwnd, _WM_SETICON, which, ctypes.c_void_p(handle))


def _colorref(hex_colour: str) -> int:
    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return r | g << 8 | b << 16


def _bring_forward() -> None:
    hwnd = ctypes.windll.user32.FindWindowW(None, TITLE)
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)


def run() -> None:
    """The process: one window; a second `--settings` brings the first one forward and exits."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX)
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        _bring_forward()
        return
    import webview

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(APP_ID))
    page = resources.files("juice_mate.ui").joinpath("settings.html").read_text(encoding="utf-8")
    api = Api()
    window = webview.create_window(
        TITLE,
        html=page,
        js_api=api,
        width=980,
        height=720,
        frameless=True,
        easy_drag=False,  # only the page's title bar drags the window
        background_color=NIGHT,
    )
    if window is None:
        return
    api._window = window
    window.events.shown += lambda: _style_frame(TITLE)
    webview.start(debug="--debug" in sys.argv)
    kernel32.CloseHandle(handle)
