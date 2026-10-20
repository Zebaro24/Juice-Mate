"""One reading from one source, and the level the tray shows for it (docs/architecture.md §3, §6)."""

from dataclasses import dataclass
from enum import StrEnum

LOW_PERCENT = 20


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


def level(reading: Reading, low: int = LOW_PERCENT) -> Level:
    """Disconnected wins over everything: Windows keeps returning a stale battery value then."""
    if not reading.connected:
        return Level.OFFLINE
    if reading.error is not None or reading.percent is None:
        return Level.UNKNOWN
    if reading.charging:
        return Level.CHARGING
    return Level.LOW if reading.percent < low else Level.OK


def label(reading: Reading) -> str:
    """The text drawn on the icon: up to three characters."""
    if not reading.connected or reading.percent is None:
        return "–"
    return str(max(0, min(reading.percent, 100)))
