"""The hover card's content: what an item is, its number, a few lines of story, and a chart
(docs/architecture.md §6b). Pure: built from a reading or a metric plus its history.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from juice_mate.core import insight
from juice_mate.core.display import Item, Tone
from juice_mate.core.history import Sample
from juice_mate.core.metric import Metric, Unit, speed
from juice_mate.core.reading import Kind, Reading

BATTERY_WINDOW = 12 * 3600  # seconds of battery history on the chart
USAGE_WINDOW = 5 * 3600  # the 5-hour window, or the week's last 5 hours
SENSOR_WINDOW = 3600


@dataclass(frozen=True)
class Card:
    glyph: str
    title: str
    value: str
    tone: Tone
    lines: list[str]
    series: list[Sample] = field(default_factory=list)
    t0: float = 0.0  # the chart's time span, epoch seconds
    t1: float = 0.0
    y_max: float | None = 100.0  # None: scale to the data
    unit: str = "%"
    charging_marks: bool = False  # shade the stretches where the battery was charging


Clock = Callable[[float], str]  # epoch seconds → "14:20" in the machine's time: the caller's business


def battery_card(item: Item, reading: Reading, samples: list[Sample], now: float, clock: Clock) -> Card:
    story = insight.battery(samples)
    lines: list[str] = []
    if story.charging:
        lines.append("Charging" + (f" · full in about {insight.hours(story.hours_left)}" if story.hours_left else ""))
    elif story.rate is not None and story.rate < -0.05:
        lines.append(f"Draining {abs(story.rate):.1f}% an hour")
        if story.hours_left is not None:
            lines.append(f"Lasts about {insight.hours(story.hours_left)} more")
    elif story.rate is not None:
        lines.append("Holding steady")
    else:
        lines.append("Learning how fast it drains…")
    if story.charged_at is not None and not story.charging:
        lines.append(f"Last charged at {clock(story.charged_at)}")
    return Card(
        glyph=item.glyph,
        title=reading.name,
        value=item.text,
        tone=item.tone,
        lines=lines,
        series=samples,
        t0=now - BATTERY_WINDOW,
        t1=now,
        charging_marks=True,
    )


def usage_card(item: Item, reading: Reading, samples: list[Sample], now: float, clock: Clock) -> Card:
    lines: list[str] = []
    if reading.resets_at is not None:
        left = (reading.resets_at.timestamp() - now) / 3600
        lines.append(f"Resets in {insight.hours(left)} · at {clock(reading.resets_at.timestamp())}")
    if reading.limit_at is not None:
        lines.append(f"At this pace the limit comes at {clock(reading.limit_at.timestamp())}")
    elif reading.percent is not None:
        lines.append("On pace to last until the reset")
    return Card(
        glyph=item.glyph,
        title=reading.name,
        value=item.text,
        tone=item.tone,
        lines=lines,
        series=samples,
        t0=now - USAGE_WINDOW,
        t1=now,
    )


def sensor_card(item: Item, metric: Metric, samples: list[Sample], now: float) -> Card:
    lines: list[str] = []
    s = insight.spread(samples)
    if metric.error:
        lines.append(metric.error)
    elif s is not None:
        show = _formatter(metric.unit)
        lines.append(f"Last hour  low {show(s.low)} · avg {show(s.mean)} · high {show(s.high)}")
    if metric.total and metric.value is not None:
        lines.append(f"{metric.value / 1024**3:.1f} of {metric.total / 1024**3:.1f} GB")
    percent = metric.unit is Unit.PERCENT
    return Card(
        glyph=item.glyph,
        title=metric.name,
        value=item.text,
        tone=item.tone,
        lines=lines,
        series=samples,
        t0=now - SENSOR_WINDOW,
        t1=now,
        y_max=100.0 if percent else (metric.total if metric.total else None),
        unit=str(metric.unit),
    )


def _formatter(unit: Unit) -> Callable[[float], str]:
    if unit is Unit.BYTES_PER_SECOND:
        return lambda v: speed(v) + "/s"
    if unit is Unit.BYTES:
        return lambda v: f"{v / 1024**3:.1f}G"
    if unit is Unit.MILLISECONDS:
        return lambda v: f"{v:.0f}ms"
    if unit is Unit.CELSIUS:
        return lambda v: f"{v:.0f}°"
    return lambda v: f"{v:.0f}%"


def card_for(
    item: Item, reading: Reading | None, metric: Metric | None, samples: list[Sample], now: float, clock: Clock
) -> Card | None:
    if reading is not None:
        if reading.kind is Kind.CLAUDE:
            return usage_card(item, reading, samples, now, clock)
        return battery_card(item, reading, samples, now, clock)
    if metric is not None:
        return sensor_card(item, metric, samples, now)
    return None
