"""What a history says in words — the hover card's lines (docs/architecture.md §6b). Pure."""

from dataclasses import dataclass

from juice_mate.core.history import Sample

MIN_SPAN = 20 * 60  # seconds: a rate from less than this is noise (a battery reads in whole percents)
RISE = 3.0  # percent: a battery gaining this much between samples was being charged


@dataclass(frozen=True)
class BatteryStory:
    rate: float | None  # percent per hour; negative while discharging
    hours_left: float | None  # to 0 % when discharging, to 100 % when charging
    charged_at: float | None  # when the last charge ended (epoch seconds)
    charging: bool


def _since_last_charge(samples: list[Sample]) -> list[Sample]:
    """The samples after the last charge ended: only they show how fast it drains now."""
    start = 0
    for i, sample in enumerate(samples):
        if sample.charging:
            start = i + 1  # still on the charger: drain starts after it
        elif i and sample.value - samples[i - 1].value >= RISE:
            start = i  # a jump seen between two reads: the top is the first drained point
    return samples[start:]


def _this_charge(samples: list[Sample]) -> list[Sample]:
    """The unbroken run of charging samples at the end: the current charge, not yesterday's too."""
    start = len(samples)
    while start > 0 and samples[start - 1].charging:
        start -= 1
    return samples[start:]


def _rate(samples: list[Sample]) -> float | None:
    """Percent per hour: a least-squares line, so one odd reading does not swing it."""
    if len(samples) < 2 or samples[-1].t - samples[0].t < MIN_SPAN:
        return None
    n = len(samples)
    mean_t = sum(s.t for s in samples) / n
    mean_v = sum(s.value for s in samples) / n
    spread = sum((s.t - mean_t) ** 2 for s in samples)
    if spread == 0:
        return None
    slope = sum((s.t - mean_t) * (s.value - mean_v) for s in samples) / spread
    return slope * 3600


def battery(samples: list[Sample]) -> BatteryStory:
    if not samples:
        return BatteryStory(None, None, None, False)
    charging = samples[-1].charging
    drained = _since_last_charge(samples)
    charged_at = drained[0].t if drained and len(drained) < len(samples) else None
    if charging:
        rate = _rate(_this_charge(samples)[-30:])
        left = (100 - samples[-1].value) / rate if rate and rate > 0 else None
        return BatteryStory(rate, left, None, True)
    rate = _rate(drained)
    left = samples[-1].value / -rate if rate and rate < 0 else None
    return BatteryStory(rate, left, charged_at, False)


@dataclass(frozen=True)
class Spread:
    low: float
    mean: float
    high: float


def spread(samples: list[Sample]) -> Spread | None:
    if not samples:
        return None
    values = [s.value for s in samples]
    return Spread(min(values), sum(values) / len(values), max(values))


def hours(value: float) -> str:
    """`9 h 20 min`, `45 min`, `2 d 3 h`."""
    minutes = max(round(value * 60), 0)
    days, minutes = divmod(minutes, 24 * 60)
    h, m = divmod(minutes, 60)
    if days:
        return f"{days} d {h} h"
    if h:
        return f"{h} h {m:02d} min"
    return f"{m} min"
