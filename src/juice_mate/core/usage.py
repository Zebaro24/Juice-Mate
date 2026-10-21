"""Claude usage windows: parsing the `/usage` answer and saying it in a tooltip (docs/architecture.md §3.3).

The answer carries a dozen experimental keys with code names; only `five_hour` and `seven_day` are
read. Anything unexpected in them → `UsageFormatError`, which the source shows as "data unavailable".
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

WINDOWS = {"five_hour": ("5 h", "5h"), "seven_day": ("week", "7d")}  # key → (tooltip label, panel tag)


class UsageFormatError(ValueError):
    """The answer no longer looks like the one this code was written against."""


@dataclass(frozen=True)
class Window:
    key: str
    label: str
    tag: str
    used: float  # percent of the window's limit already spent
    resets_at: datetime | None


def parse(answer: Any) -> list[Window]:
    if not isinstance(answer, dict):
        raise UsageFormatError(f"expected an object, got {type(answer).__name__}")
    windows = []
    for key, (label, tag) in WINDOWS.items():
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
        windows.append(Window(key, label, tag, float(raw["utilization"]), resets_at))
    if not windows:
        raise UsageFormatError("neither five_hour nor seven_day in the answer")
    return windows


PACE_WINDOW = timedelta(minutes=60)  # recent samples only: this hour's pace, not this morning's
PACE_MIN_SPAN = timedelta(minutes=10)  # less than this and two samples are noise, not a pace


def limit_at(samples: list[tuple[datetime, float]], window: Window, now: datetime) -> datetime | None:
    """When the window runs out at the recent pace — only if that is before it resets.

    `samples` are (time, % used) of this window, oldest first. The pace is the straight line from the
    oldest recent sample to the newest; a flat or falling line means no forecast.
    """
    recent = [(t, used) for t, used in samples if now - t <= PACE_WINDOW]
    if len(recent) < 2:
        return None
    (t0, u0), (t1, u1) = recent[0], recent[-1]
    span = t1 - t0
    if span < PACE_MIN_SPAN or u1 <= u0:
        return None
    per_second = (u1 - u0) / span.total_seconds()
    eta = t1 + timedelta(seconds=(100.0 - window.used) / per_second)
    if eta <= now:
        return None  # anchored at an old sample while fetches fail: a time already past says nothing
    if window.resets_at is not None and eta >= window.resets_at:
        return None
    return eta


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
