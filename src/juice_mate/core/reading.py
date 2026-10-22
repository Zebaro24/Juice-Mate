"""One reading from one source, and the level the panel shows for it (docs/architecture.md §3, §6)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

LOW_PERCENT = 20
HIGH_USAGE_PERCENT = 80


class Kind(StrEnum):
    """What a device is — picks its glyph on the panel."""

    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    HEADSET = "headset"
    GAMEPAD = "gamepad"
    PHONE = "phone"
    OTHER = "other"
    CLAUDE = "claude"  # not a battery: `percent` is usage, and high is the bad end


class Level(StrEnum):
    OK = "ok"
    LOW = "low"
    CHARGING = "charging"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Reading:
    """What a source saw for one device. `percent` is `None` when the device gave no number."""

    source: str
    device_id: str
    name: str
    percent: int | None
    connected: bool = True
    charging: bool | None = None
    error: str | None = None
    kind: Kind = Kind.OTHER
    note: str | None = None  # replaces the default state text in the tooltip
    tag: str | None = None  # a short label drawn before the number ("5h", "7d")
    limit_at: datetime | None = None  # usage only: when the window runs out at the current pace


def level(reading: Reading, low: int = LOW_PERCENT, high: int = HIGH_USAGE_PERCENT) -> Level:
    """Disconnected wins over everything: Windows keeps returning a stale battery value then.
    `low` is the battery threshold, `high` the usage one (both the owner's, settings.py)."""
    if not reading.connected:
        return Level.OFFLINE
    if reading.error is not None or reading.percent is None:
        return Level.UNKNOWN
    if reading.kind is Kind.CLAUDE:
        return Level.LOW if reading.percent >= high else Level.OK
    if reading.charging:
        return Level.CHARGING
    return Level.LOW if reading.percent < low else Level.OK


def label(reading: Reading) -> str:
    """The text drawn on the icon: up to three characters."""
    if not reading.connected or reading.percent is None:
        return "–"
    return str(max(0, min(reading.percent, 100)))
