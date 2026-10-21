from datetime import datetime

from juice_mate.core.display import BOLT, GLYPHS, WARNING, Tone, item, items
from juice_mate.core.reading import Kind, Reading
from juice_mate.panel.render import Theme, premultiplied_bgra, render

NOW = datetime(2026, 10, 20, 15, 0)


def reading(**kw: object) -> Reading:
    base: dict[str, object] = {"source": "bt", "device_id": "kb", "name": "MX KEYS S", "percent": 45}
    base.update(kw)
    return Reading(**base)  # type: ignore[arg-type]


def test_a_connected_device_is_its_glyph_and_percent() -> None:
    it = item(reading(kind=Kind.KEYBOARD), NOW)
    assert (it.glyph, it.text, it.tone, it.tag, it.badge) == (GLYPHS[Kind.KEYBOARD], "45%", Tone.NORMAL, "", "")


def test_disconnected_devices_are_not_shown() -> None:
    shown = items([reading(device_id="a", connected=False), reading(device_id="b")], NOW)
    assert [it.key for it in shown] == ["bt:b"]


def test_an_unavailable_source_is_still_shown() -> None:
    assert len(items([reading(percent=None, error="dongle busy")], NOW)) == 1


def test_the_tag_is_carried_to_the_item() -> None:
    assert item(reading(tag="7d"), NOW).tag == "7d"


def test_low_is_critical_and_charging_is_not() -> None:
    assert item(reading(percent=12), NOW).tone is Tone.CRITICAL
    charging = item(reading(percent=12, charging=True), NOW)
    assert charging.tone is Tone.NORMAL
    assert charging.charging


def test_unavailable_gets_a_warning_badge() -> None:
    it = item(reading(percent=None, error="HID read failed"), NOW)
    assert it.badge == WARNING
    assert it.text == ""
    assert "HID read failed" in it.tooltip


def test_order_is_by_kind_then_name() -> None:
    rs = [
        reading(device_id="p", name="Phone", kind=Kind.PHONE),
        reading(device_id="h2", name="b", kind=Kind.HEADSET),
        reading(device_id="k", name="z", kind=Kind.KEYBOARD),
        reading(device_id="h1", name="A", kind=Kind.HEADSET),
    ]
    assert [it.key for it in items(rs, NOW)] == ["bt:k", "bt:h1", "bt:h2", "bt:p"]


def test_render_fills_two_rows_column_by_column() -> None:
    kinds = [Kind.KEYBOARD, Kind.MOUSE, Kind.HEADSET]
    its = items([reading(device_id=k.value, kind=k, charging=k is Kind.MOUSE) for k in kinds], NOW)
    image, spans = render(its, 48, Theme.for_taskbar(light=False))
    assert image.size[1] == 48
    keyboard, mouse, headset = spans
    assert (keyboard.left, keyboard.top, keyboard.bottom) == (mouse.left, 0, 24), "first column, top row"
    assert (mouse.top, mouse.bottom) == (24, 48), "first column, bottom row"
    assert (headset.top, headset.bottom) == (0, 48), "a column of one is centred and takes the full height"
    assert keyboard.right < headset.left <= headset.right <= image.width


def test_background_catches_the_mouse_but_is_invisible() -> None:
    # Alpha 0 would let clicks fall through a layered window to the taskbar.
    image, _ = render([], 48, Theme.for_taskbar(light=True))
    assert image.getpixel((0, 0)) == (0, 0, 0, 1)


def test_wider_at_higher_dpi() -> None:
    its = items([reading()], NOW)
    assert render(its, 72, Theme.for_taskbar(False), 1.5)[0].width > render(its, 48, Theme.for_taskbar(False))[0].width


def test_pixels_are_premultiplied_bgra() -> None:
    image, _ = render(items([reading()], NOW), 48, Theme.for_taskbar(False))
    data = premultiplied_bgra(image)
    assert len(data) == image.width * image.height * 4


def test_bolt_glyph_is_from_the_icon_font() -> None:
    assert BOLT == "\ue945"
