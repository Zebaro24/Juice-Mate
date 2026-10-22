"""A system sensor value and how it is written in a few characters (docs/architecture.md §4a)."""

from dataclasses import dataclass
from enum import StrEnum


class Unit(StrEnum):
    PERCENT = "%"
    BYTES_PER_SECOND = "B/s"
    CELSIUS = "°C"
    BYTES = "B"
    MILLISECONDS = "ms"


OFFLINE = "offline"  # a ping's error when nothing answers: drawn red, not dimmed


@dataclass(frozen=True)
class Metric:
    """`value` is `None` when the sensor could not read; `error` then says why."""

    sensor: str
    name: str
    value: float | None
    unit: Unit
    error: str | None = None
    total: float | None = None  # bytes: the capacity, for the tooltip ("21.3 / 31.9 GB")


_PREFIXES = ("", "K", "M", "G", "T")


def speed(bytes_per_second: float) -> str:
    """`12.4M`, `850K`, `0K` — at most four characters plus the prefix, as on a taskbar."""
    value = max(bytes_per_second, 0.0) / 1024
    prefix = 1
    while value >= 1000 and prefix < len(_PREFIXES) - 1:
        value /= 1024
        prefix += 1
    text = f"{value:.1f}" if value < 10 and prefix > 1 else f"{value:.0f}"
    return f"{text}{_PREFIXES[prefix]}"


def short(metric: Metric) -> str:
    """The value as the panel shows it; `–` when there is none."""
    if metric.value is None:
        return "–"
    if metric.unit is Unit.BYTES_PER_SECOND:
        return speed(metric.value)
    if metric.unit is Unit.CELSIUS:
        return f"{metric.value:.0f}°"
    if metric.unit is Unit.BYTES:
        return gigabytes(metric.value)
    if metric.unit is Unit.MILLISECONDS:
        return f"{metric.value:.0f}ms"
    return f"{metric.value:.0f}"


def gigabytes(value: float) -> str:
    """`21.3G`, `8G` — a tenth while it fits in four characters."""
    gb = max(value, 0.0) / 1024**3
    return f"{gb:.1f}G" if gb < 100 else f"{gb:.0f}G"
