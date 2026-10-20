from datetime import datetime

from juice_mate.core.display import tooltip
from juice_mate.core.reading import Reading

NOON = datetime(2026, 10, 20, 12, 5)


def test_tooltip_states() -> None:
    kb = Reading("bluetooth", "c1", "MX KEYS S", 45)
    assert tooltip(kb, NOON) == "MX KEYS S — 45% · 12:05"
    assert (
        tooltip(Reading("bluetooth", "c1", "MX KEYS S", 45, connected=False), NOON)
        == "MX KEYS S — disconnected · 12:05"
    )
    charging = Reading("hator", "m", "Mouse", 60, charging=True)
    assert tooltip(charging, NOON) == "Mouse — 60% · charging · 12:05"
    broken = Reading("bluetooth", "bluetooth", "Bluetooth", None, error="access denied")
    assert tooltip(broken, NOON) == "Bluetooth — unavailable: access denied · 12:05"


def test_tooltip_fits_the_windows_limit() -> None:
    assert len(tooltip(Reading("bt", "x", "N" * 300, 1), NOON)) == 127
