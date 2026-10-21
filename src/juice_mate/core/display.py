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
UNAVAILABLE = "!"  # in place of the number: a badge over a glyph is not a Windows pattern


class Tone(StrEnum):
    """How the item is painted: the taskbar's text colour, dimmed, or the system red."""

    NORMAL = "normal"
    DIM = "dim"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Item:
    key: str
    glyph: str
    text: str  # "45%", "!" when unavailable, "" when there is no number
    tone: Tone
    charging: bool
    tag: str  # "" or a short label before the number
    group: str  # items of one group sit closer together than items of different groups
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
    text = f"{reading.percent}%" if has_number else UNAVAILABLE if unavailable else ""
    return Item(
        key=f"{reading.source}:{reading.device_id}",
        glyph=GLYPHS[reading.kind],
        text=text,
        tone=Tone.CRITICAL if lvl is Level.LOW else Tone.DIM if (offline or unavailable) else Tone.NORMAL,
        charging=lvl is Level.CHARGING,
        tag=reading.tag or "",
        group="usage" if reading.kind is Kind.CLAUDE else "devices",
        tooltip=tooltip(reading, now),
    )


ORDER = [Kind.CLAUDE, Kind.KEYBOARD, Kind.MOUSE, Kind.HEADSET, Kind.GAMEPAD, Kind.PHONE, Kind.OTHER]


def items(readings: list[Reading], now: datetime) -> list[Item]:
    """What the panel shows, in a stable order: by kind, then name — items do not jump around.

    A disconnected device is not shown at all (owner, 2026-10-21): a cached number says nothing, and a
    crossed-out glyph is clutter. An unavailable source still shows, dimmed, with "!" for a number.
    """
    shown = [r for r in readings if level(r) is not Level.OFFLINE]
    ordered = sorted(shown, key=lambda r: (ORDER.index(r.kind), r.device_id, r.name.lower()))
    return [item(r, now) for r in ordered]
