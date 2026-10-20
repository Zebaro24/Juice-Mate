"""One tray icon per device, kept in step with the readings (docs/architecture.md §6).

pystray on Windows runs every detached icon in its own thread with its own message loop, so icons
come and go independently. When no device is found, one grey placeholder keeps the menu reachable.

**Only the thread in `run()` touches the icons.** Menu callbacks run on the icons' own threads; they
only set events, so two refreshes can never race to create the same icon twice.
"""

import threading
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

import pystray

from juice_mate.core.reading import Level, Reading, label, level
from juice_mate.sources import Source
from juice_mate.tray.drawing import draw

POLL_SECONDS = 30
_PLACEHOLDER = "__placeholder__"


def tooltip(reading: Reading, now: datetime) -> str:
    lvl = level(reading)
    if reading.error:
        state = f"unavailable: {reading.error}"
    elif lvl is Level.OFFLINE:
        state = "disconnected"
    else:
        state = f"{reading.percent}%" + (" · charging" if lvl is Level.CHARGING else "")
    # Windows cuts tray tooltips at 127 characters.
    return f"{reading.name} — {state} · {now:%H:%M}"[:127]


def poll_all(sources: Sequence[Source]) -> list[Reading]:
    """A source that raises becomes one error reading — the tray never stops over it."""
    readings = []
    for source in sources:
        try:
            readings.extend(source.poll())
        except Exception as e:  # any bug in a source must not end the poll loop
            name = type(source).__name__
            readings.append(Reading(source=name, device_id=name, name=name, percent=None, error=repr(e)))
    return readings


class TrayIcons:
    def __init__(self, sources: Sequence[Source], make_icon: Callable[..., Any] = pystray.Icon) -> None:
        self._sources = sources
        self._make_icon = make_icon
        self._icons: dict[str, Any] = {}
        self._stop = threading.Event()
        self._wake = threading.Event()

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Refresh now", lambda _icon, _item: self._wake.set()),
            pystray.MenuItem("Quit", lambda _icon, _item: self.quit()),
        )

    def _show(self, key: str, text: str, lvl: Level, title: str) -> None:
        icon = self._icons.get(key)
        if icon is None:
            icon = self._make_icon(f"juice-mate-{key}", icon=draw(text, lvl), title=title, menu=self._menu())
            self._icons[key] = icon
            icon.run_detached()
        else:
            icon.icon = draw(text, lvl)
            icon.title = title

    def _hide(self, key: str) -> None:
        icon = self._icons.pop(key, None)
        if icon is not None:
            icon.stop()

    def refresh(self) -> None:
        """Call only from the thread running `run()`."""
        readings = poll_all(self._sources)
        now = datetime.now()
        keys = {f"{r.source}:{r.device_id}" for r in readings}
        for key in list(self._icons):
            if key not in keys and key != _PLACEHOLDER:
                self._hide(key)
        for r in readings:
            self._show(f"{r.source}:{r.device_id}", label(r), level(r), tooltip(r, now))
        if readings:
            self._hide(_PLACEHOLDER)
        else:
            self._show(_PLACEHOLDER, "–", Level.UNKNOWN, "Juice-Mate — no device reports a battery")

    @property
    def keys(self) -> set[str]:
        return set(self._icons)

    def quit(self) -> None:
        self._stop.set()
        self._wake.set()

    def run(self) -> None:
        while not self._stop.is_set():
            self.refresh()
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()
        for key in list(self._icons):
            self._hide(key)


def run(*sources: Source) -> None:
    TrayIcons(sources).run()
