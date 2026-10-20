import pytest

from juice_mate.core.metric import Metric, Unit, short, speed


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (0, "0K"),
        (-5, "0K"),
        (500, "0K"),
        (850 * 1024, "850K"),
        (999 * 1024, "999K"),
        (1000 * 1024, "1.0M"),
        (12.4 * 1024 * 1024, "12M"),
        (5.25 * 1024 * 1024, "5.2M"),
        (3 * 1024**3, "3.0G"),
    ],
)
def test_speed(value: float, text: str) -> None:
    assert speed(value) == text


def test_short() -> None:
    assert short(Metric("cpu", "CPU", 37.4, Unit.PERCENT)) == "37"
    assert short(Metric("gpu", "GPU temp", 52.0, Unit.CELSIUS)) == "52°"
    assert short(Metric("net", "Down", 2048, Unit.BYTES_PER_SECOND)) == "2K"
    assert short(Metric("gpu", "GPU temp", None, Unit.CELSIUS, error="no NVIDIA")) == "–"
