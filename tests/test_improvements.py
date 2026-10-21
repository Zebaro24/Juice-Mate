"""v0.2: sensors on the panel, the menu's "Show" choices, the usage pace forecast and its alerts."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from juice_mate.core.alerts import Alerts
from juice_mate.core.display import SENSOR_GLYPHS, Tone, metric_item
from juice_mate.core.metric import Metric, Unit
from juice_mate.core.reading import Kind, Reading
from juice_mate.core.usage import Window, limit_at
from juice_mate.settings import DEFAULT_SENSORS, Settings

NOW = datetime(2026, 10, 21, 14, 0, tzinfo=UTC)


# ── sensors as panel items ──────────────────────────────────────────────────


def test_sensor_items_carry_their_glyph_value_and_slot() -> None:
    down = metric_item(Metric("net.down", "Download", 12.4 * 1024 * 1024, Unit.BYTES_PER_SECOND), NOW)
    assert (down.key, down.glyph, down.text, down.group, down.reserve) == (
        "system:net.down",
        SENSOR_GLYPHS["net.down"],
        "12M",
        "system",
        "000K",
    )
    assert down.tooltip.startswith("Download — 12M/s")
    cpu = metric_item(Metric("cpu.load", "CPU", 37.4, Unit.PERCENT), NOW)
    assert (cpu.glyph, cpu.text) == (SENSOR_GLYPHS["cpu"], "37%")


def test_gpu_temperature_gets_the_thermometer_not_the_card() -> None:
    temp = metric_item(Metric("gpu.temperature", "GPU temp", 52.0, Unit.CELSIUS), NOW)
    assert (temp.glyph, temp.text, temp.reserve) == (SENSOR_GLYPHS["gpu.temperature"], "52°", "00°")


def test_hot_and_busy_are_red_unreadable_is_dim() -> None:
    assert metric_item(Metric("gpu.temperature", "GPU temp", 88.0, Unit.CELSIUS), NOW).tone is Tone.CRITICAL
    assert metric_item(Metric("cpu.load", "CPU", 97.0, Unit.PERCENT), NOW).tone is Tone.CRITICAL
    broken = metric_item(Metric("gpu.temperature", "GPU temp", None, Unit.CELSIUS, error="no NVIDIA"), NOW)
    assert (broken.text, broken.tone) == ("!", Tone.DIM)
    assert "no NVIDIA" in broken.tooltip


# ── settings ────────────────────────────────────────────────────────────────


def test_settings_default_save_load_and_toggle(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = Settings.load(path)
    assert settings.sensors == DEFAULT_SENSORS
    settings.toggle_sensor("gpu.temperature")
    settings.toggle_sensor("cpu.load")
    settings.save(path)
    again = Settings.load(path)
    assert "gpu.temperature" in again.sensors
    assert "cpu.load" not in again.sensors


def test_broken_settings_fall_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert Settings.load(path).sensors == DEFAULT_SENSORS
    path.write_text('{"sensors": [1, 2]}', encoding="utf-8")
    assert Settings.load(path).sensors == DEFAULT_SENSORS


# ── pace forecast ───────────────────────────────────────────────────────────


def window(used: float, resets_in: timedelta = timedelta(hours=3)) -> Window:
    return Window("five_hour", "5 h", "5h", used, NOW + resets_in)


def test_the_pace_runs_out_before_the_reset() -> None:
    samples = [(NOW - timedelta(minutes=30), 40.0), (NOW, 70.0)]  # 30 % in 30 min → 1 %/min
    assert limit_at(samples, window(70.0), NOW) == NOW + timedelta(minutes=30)


def test_no_forecast_when_the_reset_comes_first_or_the_pace_is_unclear() -> None:
    slow = [(NOW - timedelta(minutes=30), 40.0), (NOW, 41.0)]
    assert limit_at(slow, window(41.0), NOW) is None, "30 h to the limit, the window resets in 3 h"
    assert limit_at([(NOW, 50.0)], window(50.0), NOW) is None, "one sample is no pace"
    short = [(NOW - timedelta(minutes=3), 40.0), (NOW, 45.0)]
    assert limit_at(short, window(45.0), NOW) is None, "three minutes is noise"
    flat = [(NOW - timedelta(minutes=30), 40.0), (NOW, 40.0)]
    assert limit_at(flat, window(40.0), NOW) is None
    old = [(NOW - timedelta(hours=3), 10.0), (NOW - timedelta(hours=2), 60.0)]
    assert limit_at(old, window(60.0), NOW) is None, "only the last hour counts"
    stale = [(NOW - timedelta(minutes=50), 40.0), (NOW - timedelta(minutes=40), 90.0)]
    assert limit_at(stale, window(90.0), NOW) is None, "a forecast already in the past is dropped"


# ── usage alerts ────────────────────────────────────────────────────────────


def usage(percent: int, limit: datetime | None = None) -> Reading:
    return Reading("claude", "five_hour", "Claude 5 h", percent, kind=Kind.CLAUDE, limit_at=limit)


def test_one_pace_warning_per_window() -> None:
    alerts = Alerts()
    eta = NOW + timedelta(minutes=40)
    first = alerts.check([usage(60, eta)])
    assert [a.title.split(":")[0] for a in first] == ["Claude 5 h"]
    assert "at this pace" in first[0].title
    assert alerts.check([usage(65, eta)]) == []


def test_a_pause_inside_one_window_does_not_warn_twice() -> None:
    # Review 2026-10-21: re-arming on "low % and no forecast" toasted on every burst of a fresh window.
    alerts = Alerts()
    assert len(alerts.check([usage(8, NOW + timedelta(minutes=90))])) == 1
    assert alerts.check([usage(9)]) == []
    assert alerts.check([usage(12, NOW + timedelta(minutes=80))]) == []


def test_arrows_stay_in_one_column_whatever_the_device_count() -> None:
    from juice_mate.core.display import items
    from juice_mate.panel.render import Theme, render

    devices = [Reading("bt", f"d{i}", f"Device {i}", 50, kind=Kind.MOUSE) for i in range(3)]
    sensors = [
        metric_item(Metric("net.up", "Upload", 1000.0, Unit.BYTES_PER_SECOND), NOW),
        metric_item(Metric("net.down", "Download", 9000.0, Unit.BYTES_PER_SECOND), NOW),
    ]
    _image, spans = render(items(devices, NOW) + sensors, 48, Theme.for_taskbar(False))
    up, down = (next(s for s in spans if s.key == key) for key in ("system:net.up", "system:net.down"))
    assert up.left == down.left, "↑ and ↓ share a column"
    assert (up.top, down.top) == (0, 24)


def test_a_spent_window_that_resets_says_so_and_re_arms_the_warning() -> None:
    alerts = Alerts()
    alerts.check([usage(85, NOW + timedelta(minutes=20))])
    back = alerts.check([usage(2)])
    assert [a.title for a in back] == ["Claude 5 h limit is back"]
    again = alerts.check([usage(30, NOW + timedelta(minutes=50))])
    assert len(again) == 1, "a new window may warn again"
