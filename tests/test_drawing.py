import pytest

from juice_mate.core.reading import Level
from juice_mate.tray.drawing import COLOURS, SIZE, draw


@pytest.mark.parametrize("lvl", list(Level))
def test_every_level_draws_a_square_icon(lvl: Level) -> None:
    image = draw("100", lvl)
    assert image.size == (SIZE, SIZE)
    assert image.mode == "RGBA"


def test_background_is_the_level_colour() -> None:
    corner_inside = draw("5", Level.LOW).getpixel((SIZE // 2, 4))
    assert corner_inside[:3] == (0xC6, 0x28, 0x28)  # type: ignore[index]
    assert COLOURS[Level.LOW] == "#c62828"


def test_charging_adds_the_bolt() -> None:
    bolt = (48, 8)
    assert draw("50", Level.CHARGING).getpixel(bolt) != draw("50", Level.OK).getpixel(bolt)
