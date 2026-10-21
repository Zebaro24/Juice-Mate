from juice_mate.core.alerts import Alerts
from juice_mate.core.reading import Kind, Reading


def mouse(percent: int | None, **kw: object) -> Reading:
    return Reading("hator", "m", "Hator Stellar PRO", percent, kind=Kind.MOUSE, **kw)  # type: ignore[arg-type]


def titles(alerts: Alerts, *readings: Reading) -> list[str]:
    return [a.title for a in alerts.check(list(readings))]


def test_one_alert_when_the_battery_drops_below_15() -> None:
    alerts = Alerts()
    assert titles(alerts, mouse(16)) == []
    assert titles(alerts, mouse(14)) == ["Hator Stellar PRO — 14%"]
    assert titles(alerts, mouse(13)) == [], "not again while still low"
    assert titles(alerts, mouse(17)) == [], "hovering below 20 does not re-arm"
    assert titles(alerts, mouse(14)) == []


def test_recovery_re_arms_it() -> None:
    alerts = Alerts()
    alerts.check([mouse(10)])
    alerts.check([mouse(20)])
    assert titles(alerts, mouse(12)) == ["Hator Stellar PRO — 12%"]


def test_the_charger_re_arms_it_and_silences_it() -> None:
    alerts = Alerts()
    alerts.check([mouse(10)])
    assert titles(alerts, mouse(9, charging=True)) == []
    assert titles(alerts, mouse(11)) == ["Hator Stellar PRO — 11%"]


def test_no_alert_for_usage_disconnected_or_broken() -> None:
    alerts = Alerts()
    usage = Reading("claude", "five_hour", "Claude 5 h", 5, kind=Kind.CLAUDE)
    assert titles(alerts, usage, mouse(5, connected=False), mouse(None, error="x")) == []


def test_each_device_separately() -> None:
    alerts = Alerts()
    kb = Reading("bt", "kb", "MX KEYS S", 10, kind=Kind.KEYBOARD)
    assert titles(alerts, kb, mouse(12)) == ["MX KEYS S — 10%", "Hator Stellar PRO — 12%"]
