from typing import Any

import pytest

from juice_mate.core.reading import Kind, Level, level
from juice_mate.core.smoothing import Median
from juice_mate.sources import hator
from juice_mate.sources.hator import Hator, parse

DONGLE = {"usage_page": 0xFF01, "path": b"dongle", "product_string": "Stellar PRO"}
OTHER_INTERFACE = {"usage_page": 0x0001, "path": b"mouse", "product_string": "Stellar PRO"}


@pytest.mark.parametrize(
    ("reply", "percent"),
    [
        ([0x07, 0x89, 0x59, 0x01, 0x02, 0x03, 0x00, 0x00], 89),  # real reply, owner's mouse 2026-10-21
        ([0x07, 0x89, 100, 1, 2, 3, 0, 0], 100),
        ([0x07, 0x89, 0x00, 0, 0, 0, 0, 0], None),  # asleep: zeros
        ([0x07, 0x89, 0xFF, 0, 0, 0, 0, 0], None),
        ([0x07, 0x88, 0x59, 0, 0, 0, 0, 0], None),  # another command's reply
        ([0x06, 0x89, 0x59], None),
        ([0x07], None),
    ],
)
def test_parse(reply: list[int], percent: int | None) -> None:
    assert parse(reply) == percent


def test_median_holds_still_through_jitter_and_resets() -> None:
    m = Median(5)
    assert [m.add(v) for v in (80, 82, 79, 81, 80)] == [80, 81, 80, 80, 80]
    m.reset()
    assert m.add(40) == 40


class FakeHid:
    """Stands in for the `hid` module: which devices are plugged in, and what the dongle answers."""

    def __init__(
        self, devices: dict[int, list[dict[str, Any]]], reply: list[int] | Exception, open_fails: bool = False
    ):
        self.devices = devices
        self.reply = reply
        self.open_fails = open_fails
        self.sent: list[list[int]] = []

    def enumerate(self, vendor: int, product: int) -> list[dict[str, Any]]:
        assert vendor == 0x248A
        return self.devices.get(product, [])

    def device(self) -> "FakeHid":
        return self

    def open_path(self, path: bytes) -> None:
        assert path == b"dongle"
        if self.open_fails:
            raise OSError("open failed")

    def send_feature_report(self, data: list[int]) -> int:
        self.sent.append(data)
        return len(data)

    def get_feature_report(self, report_id: int, length: int) -> list[int]:
        assert (report_id, length) == (0x07, 8)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply

    def close(self) -> None:
        pass


REPLY = [0x07, 0x89, 0x59, 0x01, 0x02, 0x03, 0x00, 0x00]


def poll(monkeypatch: pytest.MonkeyPatch, fake: FakeHid, source: Hator | None = None) -> list[Any]:
    monkeypatch.setattr(hator, "hid", fake)
    return (source or Hator()).poll()


def test_no_dongle_no_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    assert poll(monkeypatch, FakeHid({}, REPLY)) == []
    assert poll(monkeypatch, FakeHid({0x5B4A: [OTHER_INTERFACE]}, REPLY)) == []


def test_the_vendor_interface_is_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeHid({0x5B4A: [OTHER_INTERFACE, DONGLE]}, REPLY)
    [reading] = poll(monkeypatch, fake)
    assert fake.sent == [[0x07, 0x89, 0, 0, 0, 0, 0, 0]]
    assert (reading.name, reading.percent, reading.kind, reading.charging) == (
        "Hator Stellar PRO",
        89,
        Kind.MOUSE,
        False,
    )


def test_on_the_cable_it_is_charging(monkeypatch: pytest.MonkeyPatch) -> None:
    [reading] = poll(monkeypatch, FakeHid({0x5B4A: [DONGLE], 0x5B49: [{"usage_page": 1}]}, REPLY))
    assert level(reading) is Level.CHARGING


def test_no_answer_means_the_mouse_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    [reading] = poll(monkeypatch, FakeHid({0x5B4A: [DONGLE]}, OSError("read error")))
    assert level(reading) is Level.OFFLINE
    [reading] = poll(monkeypatch, FakeHid({0x5B4A: [DONGLE]}, [0x07, 0x89, 0, 0, 0, 0, 0, 0]))
    assert level(reading) is Level.OFFLINE


def test_a_dongle_that_cannot_be_opened_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    [reading] = poll(monkeypatch, FakeHid({0x5B4A: [DONGLE]}, REPLY, open_fails=True))
    assert reading.error is not None
    assert "open" in reading.error


def test_jitter_is_smoothed_across_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    source = Hator()
    seen = []
    for value in (80, 83, 79):
        seen.append(poll(monkeypatch, FakeHid({0x5B4A: [DONGLE]}, [7, 0x89, value, 1, 2, 3, 0, 0]), source)[0].percent)
    assert seen == [80, 82, 80]
