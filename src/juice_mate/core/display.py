"""What one panel item looks like, decided without drawing anything (docs/architecture.md §6).

Glyphs are code points of Segoe Fluent Icons (Windows 11) — the same codes exist in Segoe MDL2 Assets
(Windows 10), so one table serves both.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from juice_mate.core.reading import Kind, Level, Reading, level

GLYPHS: dict[Kind, str] = {
    Kind.KEYBOARD: "\ue765",  # KeyboardClassic
    Kind.MOUSE: "\ue962",  # Mouse
    Kind.HEADSET: "\ue7f6",  # Headphone
    Kind.GAMEPAD: "\ue7fc",  # Game
    Kind.PHONE: "\ue8ea",  # CellPhone
    Kind.OTHER: "\ue702",  # Bluetooth
    Kind.CLAUDE: "\u2733",  # eight-spoked asterisk, drawn from Segoe UI Symbol: Claude's spark
}
BOLT = "\ue945"  # LightningBolt
WARNING = "\ue7ba"  # Warning


class Tone(StrEnum):
    """How the item is painted: the taskbar's text colour, dimmed, or the system red."""

    NORMAL = "normal"
    DIM = "dim"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Item:
    key: str
    glyph: str
    text: str  # "45%", or "" when there is no number to show
    tone: Tone
    charging: bool
    tag: str  # "" or a short label before the number
    badge: str  # "" or a small glyph next to the main one (WARNING when unavailable)
    tooltip: str


def tooltip(reading: Reading, now: datetime) -> str:
    lvl = level(reading)
    if reading.error:
        state = f"unavailable: {reading.error}"
    elif reading.note:
        state = reading.note
    elif lvl is Level.OFFLINE:
        state = "disconnected"
    else:
        state = f"{reading.percent}%" + (" · charging" if lvl is Level.CHARGING else "")
    # Windows cuts tooltips of this kind at 127 characters.
    return f"{reading.name} — {state} · {now:%H:%M}"[:127]


def item(reading: Reading, now: datetime) -> Item:
    lvl = level(reading)
    unavailable = reading.error is not None
    offline = lvl is Level.OFFLINE
    has_number = not offline and not unavailable and reading.percent is not None
    return Item(
        key=f"{reading.source}:{reading.device_id}",
        glyph=GLYPHS[reading.kind],
        text=f"{reading.percent}%" if has_number else "",
        tone=Tone.CRITICAL if lvl is Level.LOW else Tone.DIM if (offline or unavailable) else Tone.NORMAL,
        charging=lvl is Level.CHARGING,
        tag=reading.tag or "",
        badge=WARNING if unavailable and not offline else "",
        tooltip=tooltip(reading, now),
    )


ORDER = [Kind.CLAUDE, Kind.KEYBOARD, Kind.MOUSE, Kind.HEADSET, Kind.GAMEPAD, Kind.PHONE, Kind.OTHER]


def items(readings: list[Reading], now: datetime) -> list[Item]:
    """What the panel shows, in a stable order: by kind, then name — items do not jump around.

    A disconnected device is not shown at all (owner, 2026-10-21): a cached number says nothing, and a
    crossed-out glyph is clutter. An unavailable source still shows, with its warning badge.
    """
    shown = [r for r in readings if level(r) is not Level.OFFLINE]
    ordered = sorted(shown, key=lambda r: (ORDER.index(r.kind), r.device_id, r.name.lower()))
    return [item(r, now) for r in ordered]
