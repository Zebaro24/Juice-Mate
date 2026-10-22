from datetime import datetime

from juice_mate.core.display import Tone, metric_item
from juice_mate.core.metric import OFFLINE, Metric, Unit
from juice_mate.sources.system import Ping

GB = 1024**3
NOW = datetime(2026, 10, 22, 12, 0)


def test_ping_goes_offline_after_two_misses_and_back() -> None:
    answers = iter([12.0, None, None, 15.0])
    ping = Ping(probe=lambda: next(answers), start=False)
    ping.measure()
    assert ping.read().value == 12.0
    ping.measure()
    assert ping.read().value == 12.0  # one lost packet is noise
    ping.measure()
    assert ping.read().error == OFFLINE
    ping.measure()
    assert ping.read().value == 15.0


def test_memory_in_gigabytes_with_the_total_in_the_tooltip() -> None:
    used = metric_item(Metric("memory.used", "RAM used", 21.3 * GB, Unit.BYTES, total=32 * GB), NOW)
    assert used.text == "21.3G"
    assert "21.3 / 32.0 GB" in used.tooltip


def test_no_answer_is_off_in_red() -> None:
    off = metric_item(Metric("net.ping", "Ping", None, Unit.MILLISECONDS, OFFLINE), NOW)
    assert (off.text, off.tone) == ("off", Tone.CRITICAL)
    assert metric_item(Metric("net.ping", "Ping", 23.0, Unit.MILLISECONDS), NOW).text == "23ms"
