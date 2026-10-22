import json
from datetime import datetime
from pathlib import Path

from juice_mate.app import panel_items
from juice_mate.core.alerts import BATTERY, USAGE_PACE, Alerts
from juice_mate.core.arrange import LEFT, RIGHT, SECOND_RIGHT, DevicePref, arrange, personalise
from juice_mate.core.display import Tone, item
from juice_mate.core.metric import Metric, Unit
from juice_mate.core.reading import Kind, Reading
from juice_mate.settings import Settings

NOW = datetime(2026, 10, 22, 12, 0)


def reading(device_id: str = "kb", **kw: object) -> Reading:
    base: dict[str, object] = {"source": "bluetooth", "device_id": device_id, "name": "MX KEYS S", "percent": 45}
    base.update(kw)
    return Reading(**base)  # type: ignore[arg-type]


def test_personalise_renames_reicons_and_hides() -> None:
    readings = [reading("kb", kind=Kind.OTHER), reading("phone", kind=Kind.PHONE)]
    prefs = {"bluetooth:kb": DevicePref(name="Клава", kind=Kind.KEYBOARD), "bluetooth:phone": DevicePref(hidden=True)}
    [kb] = personalise(readings, prefs)
    assert (kb.name, kb.kind) == ("Клава", Kind.KEYBOARD)


def test_a_usage_window_keeps_its_spark() -> None:
    usage = reading("five_hour", source="claude", kind=Kind.CLAUDE)
    [shown] = personalise([usage], {"claude:five_hour": DevicePref(kind=Kind.MOUSE)})
    assert shown.kind is Kind.CLAUDE


def test_arrange_follows_order_then_default_and_placement() -> None:
    items = [item(reading(d), NOW) for d in ("a", "b", "c")]
    places = arrange(items, order=["bluetooth:c", "bluetooth:a"], placement={"bluetooth:b": SECOND_RIGHT})
    assert [it.key for it in places[RIGHT]] == ["bluetooth:c", "bluetooth:a"]
    assert [it.key for it in places[SECOND_RIGHT]] == ["bluetooth:b"]


def test_sensors_go_left_by_default() -> None:
    settings = Settings()
    metrics = [Metric("cpu.load", "CPU", 3.0, Unit.PERCENT)]
    places = panel_items([reading()], metrics, settings, NOW)
    assert [it.key for it in places[LEFT]] == ["system:cpu.load"]
    assert [it.key for it in places[RIGHT]] == ["bluetooth:kb"]


def test_thresholds_come_from_the_settings() -> None:
    settings = Settings(battery_low=50, busy_percent=2)
    places = panel_items([reading(percent=45)], [Metric("cpu.load", "CPU", 3.0, Unit.PERCENT)], settings, NOW)
    assert places[RIGHT][0].tone is Tone.CRITICAL
    assert places[LEFT][0].tone is Tone.CRITICAL


def test_alerts_carry_their_kind_and_the_owners_threshold() -> None:
    alerts = Alerts()
    assert alerts.check([reading(percent=25)], battery_at=30)[0].kind == BATTERY
    usage = reading("five_hour", source="claude", kind=Kind.CLAUDE, percent=40, limit_at=NOW)
    assert alerts.check([usage])[0].kind == USAGE_PACE


def test_a_broken_field_costs_only_itself(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    raw = {
        "battery_low": "twenty",
        "usage_high": 90,
        "sources": {"claude": False},
        "placement": {"bluetooth:kb": "on the moon", "system:cpu.load": "right"},
        "claude_left": 1,
    }
    path.write_text(json.dumps(raw), encoding="utf-8")
    settings = Settings.load(path)
    assert (settings.battery_low, settings.usage_high, settings.claude_left) == (20, 90, False)
    assert settings.sources == {"claude": False, "bluetooth": True, "hator": True}  # new sources start on
    assert settings.placement == {"system:cpu.load": "right"}


def test_device_changes_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = Settings()
    settings.set_device("bluetooth:kb", name="Клава", kind="keyboard")
    settings.set_device("bluetooth:phone", hidden=True)
    settings.save(path)
    prefs = Settings.load(path).device_prefs()
    assert prefs["bluetooth:kb"] == DevicePref(name="Клава", kind=Kind.KEYBOARD)
    assert prefs["bluetooth:phone"].hidden
    settings.set_device("bluetooth:kb", name="", kind=None)  # back to what the source found
    assert "bluetooth:kb" not in settings.devices
