from typing import Any

from juice_mate.core.reading import Reading
from juice_mate.tray.icons import TrayIcons, poll_all


class FakeIcon:
    def __init__(self, name: str, **kw: Any) -> None:
        self.name = name
        self.title = kw["title"]
        self.running = False

    def run_detached(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


class Devices:
    def __init__(self, *readings: Reading) -> None:
        self.readings = list(readings)

    def poll(self) -> list[Reading]:
        return self.readings


class Broken:
    def poll(self) -> list[Reading]:
        raise UnicodeDecodeError("utf-16-le", b"\x00", 0, 1, "bad name")


KB = Reading("bluetooth", "kb", "MX KEYS S", 45)
HEADSET = Reading("bluetooth", "hs", "G435", 80)


def test_icons_follow_the_devices() -> None:
    created: list[FakeIcon] = []

    def make(name: str, **kw: Any) -> FakeIcon:
        created.append(FakeIcon(name, **kw))
        return created[-1]

    devices = Devices(KB, HEADSET)
    tray = TrayIcons([devices], make_icon=make)
    tray.refresh()
    assert tray.keys == {"bluetooth:kb", "bluetooth:hs"}

    devices.readings = [KB]
    tray.refresh()
    assert tray.keys == {"bluetooth:kb"}
    assert [i.running for i in created] == [True, False]

    tray.refresh()
    assert len(created) == 2, "an existing icon is updated, not created again"


def test_placeholder_only_while_nothing_is_found() -> None:
    devices = Devices()
    tray = TrayIcons([devices], make_icon=FakeIcon)
    tray.refresh()
    assert tray.keys == {"__placeholder__"}
    devices.readings = [KB]
    tray.refresh()
    assert tray.keys == {"bluetooth:kb"}


def test_a_raising_source_becomes_an_error_reading() -> None:
    readings = poll_all([Broken(), Devices(KB)])
    assert readings[0].error is not None
    assert "UnicodeDecodeError" in readings[0].error
    assert readings[1] == KB


def test_quit_ends_run_and_removes_every_icon() -> None:
    created: list[FakeIcon] = []

    def make(name: str, **kw: Any) -> FakeIcon:
        created.append(FakeIcon(name, **kw))
        return created[-1]

    tray = TrayIcons([Devices(KB)], make_icon=make)
    tray.quit()
    tray.run()
    assert tray.keys == set()
    assert not any(i.running for i in created)
