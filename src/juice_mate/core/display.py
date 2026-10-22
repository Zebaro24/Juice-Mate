"""What one panel item looks like, decided without drawing anything (docs/architecture.md §6).

Glyphs are code points of Segoe Fluent Icons (Windows 11) — the same codes exist in Segoe MDL2 Assets
(Windows 10), so one table serves both.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from juice_mate.core.metric import Metric, Unit, short
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
    reserve: str = "00%"  # the widest ordinary value: the number slot never narrows below it
    glyph_scale: float = 1.0  # tall glyphs (arrows) shrink so two rows do not touch


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
    # Red is "act now": a battery under 20%, a usage window past 80%, or one that runs out before it
    # resets at the pace of the last hour.
    critical = lvl is Level.LOW or (has_number and reading.limit_at is not None)
    return Item(
        key=f"{reading.source}:{reading.device_id}",
        glyph=GLYPHS[reading.kind],
        text=text,
        tone=Tone.CRITICAL if critical else Tone.DIM if (offline or unavailable) else Tone.NORMAL,
        charging=lvl is Level.CHARGING,
        tag=reading.tag or "",
        group="usage" if reading.kind is Kind.CLAUDE else "devices",
        tooltip=tooltip(reading, now),
    )


# System sensors (docs/architecture.md §4a). Code points written with chr(): editors and tools have
# turned literal Private Use Area characters into invisible ones before.
SENSOR_GLYPHS: dict[str, str] = {
    "net.up": chr(0xE74A),  # Up
    "net.down": chr(0xE74B),  # Down
    "cpu": chr(0xE950),  # Component: a chip
    "gpu": chr(0xE964),  # a graphics card
    "gpu.temperature": chr(0xE9CA),  # Thermometer
    "memory": chr(0xEEA1),  # a memory chip
    "disk": chr(0xEDA2),  # a drive
}
HOT_CELSIUS = 85
BUSY_PERCENT = 95


def _sensor_glyph(sensor: str) -> str:
    # The longest matching prefix: "gpu.temperature" must not stop at "gpu".
    for prefix in sorted(SENSOR_GLYPHS, key=len, reverse=True):
        if sensor == prefix or sensor.startswith(prefix + "."):
            return SENSOR_GLYPHS[prefix]
    return SENSOR_GLYPHS["cpu"]


def metric_item(metric: Metric, now: datetime) -> Item:
    """A sensor as a panel item: its glyph and a short value — `1.2M`, `37%`, `52°`."""
    value = metric.value
    hot = value is not None and (
        (metric.unit is Unit.CELSIUS and value >= HOT_CELSIUS)
        or (metric.unit is Unit.PERCENT and value >= BUSY_PERCENT)
    )
    text = short(metric) + ("%" if metric.unit is Unit.PERCENT and value is not None else "")
    state = metric.error or f"{text}{'/s' if metric.unit is Unit.BYTES_PER_SECOND else ''}"
    return Item(
        key=f"system:{metric.sensor}",
        glyph=_sensor_glyph(metric.sensor),
        text=UNAVAILABLE if value is None else text,
        tone=Tone.DIM if value is None else Tone.CRITICAL if hot else Tone.NORMAL,
        charging=False,
        tag="",
        group="system",
        tooltip=f"{metric.name} — {state} · {now:%H:%M}"[:127],
        reserve={Unit.BYTES_PER_SECOND: "000K", Unit.CELSIUS: "00°"}.get(metric.unit, "00%"),
        # The arrows fill the whole em box; at full size the two rows merge into one "↕".
        glyph_scale=0.7 if metric.sensor.startswith("net.") else 1.0,
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
