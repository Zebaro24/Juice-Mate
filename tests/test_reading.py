import pytest

from juice_mate.core.reading import Level, Reading, label, level


def reading(**kw: object) -> Reading:
    base: dict[str, object] = {"source": "bt", "device_id": "kb", "name": "MX Keys S", "percent": 50}
    base.update(kw)
    return Reading(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"percent": 50}, Level.OK),
        ({"percent": 20}, Level.OK),
        ({"percent": 19}, Level.LOW),
        ({"percent": 5, "charging": True}, Level.CHARGING),
        ({"percent": None}, Level.UNKNOWN),
        ({"error": "HID read failed"}, Level.UNKNOWN),
    ],
)
def test_level(kw: dict[str, object], expected: Level) -> None:
    assert level(reading(**kw)) is expected


def test_disconnected_ignores_the_cached_percent() -> None:
    # Windows returns the last known battery value for a disconnected device.
    stale = reading(percent=80, connected=False, charging=True)
    assert level(stale) is Level.OFFLINE
    assert label(stale) == "–"


def test_custom_threshold() -> None:
    assert level(reading(percent=25), low=30) is Level.LOW


@pytest.mark.parametrize(("percent", "text"), [(0, "0"), (7, "7"), (100, "100"), (130, "100"), (-3, "0"), (None, "–")])
def test_label(percent: int | None, text: str) -> None:
    assert label(reading(percent=percent)) == text
