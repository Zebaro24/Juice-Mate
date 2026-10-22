from datetime import datetime, timedelta

from juice_mate.core import insight
from juice_mate.core.card import battery_card, sensor_card, usage_card
from juice_mate.core.display import item, metric_item
from juice_mate.core.history import History, Sample
from juice_mate.core.metric import Metric, Unit
from juice_mate.core.reading import Kind, Reading

HOUR = 3600.0
T0 = 1_800_000_000.0


def clock(t: float) -> str:
    return f"@{int((t - T0) // 60)}m"


def test_history_keeps_one_sample_per_step_and_the_latest_value() -> None:
    h = History(keep=10 * HOUR, step=120)
    for i in range(0, 600, 30):  # every 30 s for 10 minutes
        h.add("k", T0 + i, float(i))
    series = h.series("k")
    assert all(b.t - a.t >= 120 for a, b in zip(series[:-2], series[1:-1], strict=False))
    assert series[-1].value == 570.0  # the live point moved to the newest value


def test_history_drops_what_is_too_old_and_survives_a_file() -> None:
    h = History(keep=HOUR, step=1)
    h.add("k", T0, 1.0)
    h.add("k", T0 + 2 * HOUR, 2.0)
    assert [s.value for s in h.series("k")] == [2.0]
    again = History(keep=HOUR, step=1)
    again.load({**h.dump(), "bad": "x", 3: []}, now=T0 + 2 * HOUR)
    assert again.series("k") == h.series("k")


def drain(start: float, per_hour: float, hours: float, value: float, charging: bool = False) -> list[Sample]:
    return [Sample(start + i * 600, value - per_hour * i / 6, charging) for i in range(int(hours * 6) + 1)]


def test_a_draining_battery_tells_its_rate_and_what_is_left() -> None:
    story = insight.battery(drain(T0, 4.0, 3, 80))
    assert story.rate is not None and abs(story.rate + 4.0) < 0.01
    assert story.hours_left is not None and abs(story.hours_left - 68 / 4) < 0.05


def test_the_rate_counts_only_since_the_last_charge() -> None:
    before = drain(T0, 10.0, 2, 60)  # fast drain, then a charge, then slow drain
    charge = [Sample(T0 + 2 * HOUR + 600 * i, 40 + 20 * i, True) for i in range(1, 4)]
    after = drain(T0 + 3 * HOUR, 2.0, 3, 100)
    story = insight.battery(before + charge + after)
    assert story.rate is not None and abs(story.rate + 2.0) < 0.05
    assert story.charged_at == after[0].t


def test_too_short_a_history_says_nothing_yet() -> None:
    assert insight.battery(drain(T0, 4.0, 0.1, 80)).rate is None
    assert insight.hours(9.34) == "9 h 20 min"
    assert insight.hours(0.5) == "30 min"
    assert insight.hours(50) == "2 d 2 h"


def test_cards_read_like_a_story() -> None:
    now = T0 + 3 * HOUR
    r = Reading("bluetooth", "g435", "G435", 68, kind=Kind.HEADSET)
    card = battery_card(item(r, datetime(2026, 10, 22)), r, drain(T0, 4.0, 3, 80), now, clock)
    assert card.lines[0] == "Draining 4.0% an hour"
    assert card.lines[1].startswith("Lasts about 17 h")

    resets = datetime.fromtimestamp(now) + timedelta(hours=2)
    u = Reading("claude", "five_hour", "Claude 5 h", 40, kind=Kind.CLAUDE, tag="5h", resets_at=resets)
    usage = usage_card(item(u, datetime(2026, 10, 22)), u, [], now, clock)
    assert usage.lines[0].startswith("Resets in 2 h 00 min")
    assert usage.lines[1] == "On pace to last until the reset"

    m = Metric("cpu.load", "CPU", 30.0, Unit.PERCENT)
    samples = [Sample(now - 60, 10.0), Sample(now - 30, 50.0), Sample(now, 30.0)]
    sensor = sensor_card(metric_item(m, datetime(2026, 10, 22)), m, samples, now)
    assert sensor.lines == ["Last hour  low 10% · avg 30% · high 50%"]
    assert sensor.y_max == 100.0
