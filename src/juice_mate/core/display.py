"""What one panel item looks like, decided without drawing anything (docs/architecture.md §6).

Glyphs are code points of Segoe Fluent Icons (Windows 11) — the same codes exist in Segoe MDL2 Assets
(Windows 10), so one table serves both.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from juice_mate.core.metric import OFFLINE, Metric, Unit, short
from juice_mate.core.reading import HIGH_USAGE_PERCENT, LOW_PERCENT, Kind, Level, Reading, level

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
    suffix: str = ""  # after the number, quiet: a usage window's reset time, `→16:00`


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


def reset_suffix(resets_at: datetime | None, now: datetime) -> str:
    """`→16:00` within a day, `→26.10` further off (owner, 2026-10-22). `now` is naive local time;
    `resets_at` local, aware or not."""
    if resets_at is None:
        return ""
    local = resets_at.replace(tzinfo=None)
    return f"→{local:%H:%M}" if local - now < timedelta(hours=24) else f"→{local:%d.%m}"


def item(
    reading: Reading,
    now: datetime,
    low: int = LOW_PERCENT,
    high: int = HIGH_USAGE_PERCENT,
    reset_time: bool = False,
    left: bool = False,
) -> Item:
    """For a usage window, `reset_time` adds `→16:00` and `left` shows what is left instead of what is
    used; the colour still follows what is used."""
    lvl = level(reading, low, high)
    unavailable = reading.error is not None
    offline = lvl is Level.OFFLINE
    has_number = not offline and not unavailable and reading.percent is not None
    usage = reading.kind is Kind.CLAUDE
    shown = 100 - reading.percent if usage and left and reading.percent is not None else reading.percent
    text = f"{shown}%" if has_number else UNAVAILABLE if unavailable else ""
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
        group="usage" if usage else "devices",
        tooltip=tooltip(reading, now),
        suffix=reset_suffix(reading.resets_at, now) if usage and reset_time and has_number else "",
    )


# System sensors (docs/architecture.md §4a). Code points written with chr(): editors and tools have
# turned literal Private Use Area characters into invisible ones before.
SENSOR_GLYPHS: dict[str, str] = {
    "net.up": chr(0xE74A),  # Up
    "net.down": chr(0xE74B),  # Down
    "net.ping": chr(0xE774),  # Globe: the internet, answering or not
    "cpu": chr(0xE950),  # Component: a chip
    "gpu": chr(0xE964),  # a graphics card
    "gpu.temperature": chr(0xE9CA),  # Thermometer
    "memory": chr(0xEEA1),  # a memory chip
    "disk": chr(0xEDA2),  # a drive
}
HOT_CELSIUS = 85
# The widest ordinary value per unit: the number slot never narrows below it.
RESERVE = {Unit.BYTES_PER_SECOND: "000K", Unit.CELSIUS: "00°", Unit.BYTES: "00.0G", Unit.MILLISECONDS: "00ms"}
BUSY_PERCENT = 95


def _sensor_glyph(sensor: str) -> str:
    # The longest matching prefix: "gpu.temperature" must not stop at "gpu".
    for prefix in sorted(SENSOR_GLYPHS, key=len, reverse=True):
        if sensor == prefix or sensor.startswith(prefix + "."):
            return SENSOR_GLYPHS[prefix]
    return SENSOR_GLYPHS["cpu"]


def metric_item(metric: Metric, now: datetime, busy: int = BUSY_PERCENT, hot: int = HOT_CELSIUS) -> Item:
    """A sensor as a panel item: its glyph and a short value — `1.2M`, `37%`, `52°`, `21.3G`, `23ms`.
    A ping that gets no answer is `off`, red: the internet is gone, which is news, not a failure."""
    value = metric.value
    offline = metric.error == OFFLINE
    alarm = offline or (
        value is not None
        and ((metric.unit is Unit.CELSIUS and value >= hot) or (metric.unit is Unit.PERCENT and value >= busy))
    )
    text = short(metric) + ("%" if metric.unit is Unit.PERCENT and value is not None else "")
    if metric.error:
        state = metric.error
    elif metric.unit is Unit.BYTES and value is not None and metric.total:
        state = f"{value / 1024**3:.1f} / {metric.total / 1024**3:.1f} GB"
    else:
        state = f"{text}{'/s' if metric.unit is Unit.BYTES_PER_SECOND else ''}"
    return Item(
        key=f"system:{metric.sensor}",
        glyph=_sensor_glyph(metric.sensor),
        text="off" if offline else UNAVAILABLE if value is None else text,
        tone=Tone.CRITICAL if alarm else Tone.DIM if value is None else Tone.NORMAL,
        charging=False,
        tag="",
        group="system",
        tooltip=f"{metric.name} — {state} · {now:%H:%M}"[:127],
        reserve=RESERVE.get(metric.unit, "00%"),
        # The arrows fill the whole em box; at full size the two rows merge into one "↕". The globe too.
        glyph_scale=0.7 if metric.sensor.startswith("net.") else 1.0,
    )


ORDER = [Kind.CLAUDE, Kind.KEYBOARD, Kind.MOUSE, Kind.HEADSET, Kind.GAMEPAD, Kind.PHONE, Kind.OTHER]


def items(
    readings: list[Reading],
    now: datetime,
    low: int = LOW_PERCENT,
    high: int = HIGH_USAGE_PERCENT,
    reset_time: bool = False,
    left: bool = False,
) -> list[Item]:
    """What the panel shows, in a stable order: by kind, then name — items do not jump around.

    A disconnected device is not shown at all (owner, 2026-10-21): a cached number says nothing, and a
    crossed-out glyph is clutter. An unavailable source still shows, dimmed, with "!" for a number.
    """
    shown = [r for r in readings if level(r) is not Level.OFFLINE]
    ordered = sorted(shown, key=lambda r: (ORDER.index(r.kind), r.device_id, r.name.lower()))
    return [item(r, now, low, high, reset_time, left) for r in ordered]
