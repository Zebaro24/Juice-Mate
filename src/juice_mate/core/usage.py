"""Claude usage windows: parsing the `/usage` answer and saying it in a tooltip (docs/architecture.md §3.3).

The answer carries a dozen experimental keys with code names; only `five_hour` and `seven_day` are
read. Anything unexpected in them → `UsageFormatError`, which the source shows as "data unavailable".
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

WINDOWS = {"five_hour": "5 h", "seven_day": "week"}


class UsageFormatError(ValueError):
    """The answer no longer looks like the one this code was written against."""


@dataclass(frozen=True)
class Window:
    label: str
    used: float  # percent of the window's limit already spent
    resets_at: datetime | None


def parse(answer: Any) -> list[Window]:
    if not isinstance(answer, dict):
        raise UsageFormatError(f"expected an object, got {type(answer).__name__}")
    windows = []
    for key, label in WINDOWS.items():
        raw = answer.get(key)
        if raw is None:
            continue  # a plan without this window
        if not isinstance(raw, dict) or not isinstance(raw.get("utilization"), int | float):
            raise UsageFormatError(f"{key}: no numeric utilization")
        resets = raw.get("resets_at")
        try:
            resets_at = datetime.fromisoformat(resets) if isinstance(resets, str) else None
        except ValueError as e:
            raise UsageFormatError(f"{key}: bad resets_at {resets!r}") from e
        windows.append(Window(label, float(raw["utilization"]), resets_at))
    if not windows:
        raise UsageFormatError("neither five_hour nor seven_day in the answer")
    return windows


def worst(windows: list[Window]) -> int:
    """The number on the panel: the window closest to its limit is the one that will stop you."""
    return round(max(w.used for w in windows))


def until(moment: datetime, now: datetime) -> str:
    """`2 h 05 min`, `40 min`, `3 d 4 h` — how long until a reset."""
    left = max(moment - now, timedelta(0))
    minutes = int(left.total_seconds() // 60)
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min"


def summary(windows: list[Window], now: datetime) -> str:
    """`5 h 10% (resets in 2 h 05 min) · week 54% (resets in 4 d 23 h)`; `now` must be timezone-aware."""
    parts = []
    for w in windows:
        reset = f" (resets in {until(w.resets_at, now)})" if w.resets_at else ""
        parts.append(f"{w.label} {w.used:.0f}%{reset}")
    return " · ".join(parts)
