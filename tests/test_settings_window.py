from pathlib import Path

import pytest

from juice_mate import quit
from juice_mate.settings import Settings
from juice_mate.ui import settings_app
from juice_mate.ui.settings_app import Api, Entry, read_items, write_items


@pytest.fixture(autouse=True)
def data_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path / "JuiceMate"


def test_items_round_trip() -> None:
    entries = [Entry("bluetooth:kb", "MX KEYS S", "device", "keyboard"), Entry("system:cpu.load", "CPU", "sensor")]
    write_items(entries)
    assert read_items() == entries


def test_the_page_changes_one_field_and_the_panel_sees_it(data_folder: Path) -> None:
    panel = Settings.load()
    assert Api().assign("claude_left", True)
    assert not Api().assign("claude_left", "yes")  # a wrong shape is refused, nothing written
    assert not Api().assign("_lock", None)
    assert panel.reload_if_changed()
    assert panel.claude_left is True
    assert not panel.reload_if_changed()  # nothing new since


def test_device_changes_from_the_page() -> None:
    Api().device("bluetooth:kb", {"name": "Клава", "kind": "keyboard", "evil": 1})
    assert Settings.load().devices == {"bluetooth:kb": {"name": "Клава", "kind": "keyboard"}}


def test_the_state_lists_entries_with_their_glyphs() -> None:
    write_items(
        [Entry("system:net.ping", "Ping", "sensor"), Entry("claude:five_hour", "Claude 5 h", "usage", "claude")]
    )
    state = Api().state()
    glyphs = {e["key"]: e["glyph"] for e in state["entries"]}
    assert glyphs["claude:five_hour"] == "✳"
    assert state["entries"][0]["place"] == "left"
    assert "claude" not in state["kinds"]


def test_only_the_project_page_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("os.startfile", opened.append, raising=False)
    Api().open_url("https://example.com")
    Api().open_url(settings_app.PROJECT_URL)
    assert opened == [settings_app.PROJECT_URL]


def test_quit_reaches_the_listener_and_only_it(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    import uuid

    # A name of its own: the real one would quit a Juice-Mate running on this PC.
    monkeypatch.setattr(quit, "NAME", f"Local\\JuiceMateQuitTest-{uuid.uuid4()}")
    assert quit.request() is False  # nobody listens yet
    asked = threading.Event()
    quit.listen(asked.set)
    assert quit.request() is True
    assert asked.wait(5)


def test_a_menu_click_does_not_undo_the_windows_change(data_folder: Path) -> None:
    panel = Settings.load()
    panel.save()
    assert Api().set_in("placement", "bluetooth:kb", "left")  # the window, meanwhile
    panel.change(lambda s: s.toggle_sensor("net.ping"))  # the panel's menu, with a stale copy
    on_disk = Settings.load()
    assert on_disk.placement == {"bluetooth:kb": "left"}
    assert "net.ping" in on_disk.sensors


def test_the_window_sends_entries_not_whole_maps() -> None:
    assert not Api().assign("sources", {"claude": False})
    assert Api().set_in("sources", "claude", False)
    assert Api().sensor("net.ping", True)
    assert Api().set_in("placement", "bluetooth:kb", None)
    settings = Settings.load()
    assert settings.sources["claude"] is False and settings.sources["bluetooth"] is True
    assert "net.ping" in settings.sensors


def test_an_unreadable_file_is_not_defaults(data_folder: Path) -> None:
    panel = Settings(battery_low=33)
    panel.save()
    path = data_folder / "settings.json"
    path.write_text("{ half written", encoding="utf-8")
    assert not panel.reload_if_changed()
    assert panel.battery_low == 33  # kept, not reset
    assert not Api().assign("usage_high", 90)  # and the window does not write defaults over it
    assert path.read_text(encoding="utf-8") == "{ half written"
