import uuid

from juice_mate.core.reading import Level, level
from juice_mate.sources.bluetooth import Node, decode, merge


def node(**kw: object) -> Node:
    base: dict[str, object] = {
        "instance_id": "BTHLE\\DEV_1",
        "name": "MX KEYS S",
        "battery": 45,
        "connected": True,
        "container": "c1",
    }
    base.update(kw)
    return Node(**base)  # type: ignore[arg-type]


def test_nodes_of_one_container_become_one_reading() -> None:
    readings = merge(
        [
            node(instance_id="BTHENUM\\A", name="G435 Bluetooth Gaming Headset Hands-Free AG", container="g"),
            node(instance_id="BTHENUM\\B", name="G435 Bluetooth Gaming Headset", container="g"),
        ]
    )
    assert len(readings) == 1
    assert readings[0].name == "G435 Bluetooth Gaming Headset"
    assert readings[0].device_id == "g"


def test_the_device_node_names_the_device() -> None:
    # Real phone container: the shortest name is a service, the device node holds the real one.
    [reading] = merge(
        [
            node(instance_id="BTHENUM\\{0000111F-...}_VID&0001038F_", name="Zebaro-Phone Hands-Free HF", battery=0),
            node(instance_id="BTHENUM\\{00001132-...}_VID&0001038F_", name="SMS/MMS", battery=None),
            node(instance_id="BTHENUM\\DEV_3C135A339EA1\\7&7390520&0", name="Zebaro-Phone", battery=None),
        ]
    )
    assert reading.name == "Zebaro-Phone"


def test_the_connected_node_wins_over_a_cached_one() -> None:
    readings = merge(
        [
            node(instance_id="old", battery=90, connected=False),
            node(instance_id="live", battery=40, connected=True),
        ]
    )
    assert readings[0].percent == 40
    assert readings[0].connected


def test_no_connected_statement_means_disconnected() -> None:
    # Windows keeps the last value of a device that is gone; only "connected" makes it live.
    [reading] = merge([node(connected=None, battery=80)])
    assert level(reading) is Level.OFFLINE


def test_a_container_without_battery_is_ignored() -> None:
    assert merge([node(battery=None)]) == []


def test_a_node_without_battery_lends_its_name_and_connection() -> None:
    [reading] = merge(
        [
            node(instance_id="hfp", name="G435 Bluetooth Gaming Headset Hands-Free AG", battery=80, connected=None),
            node(instance_id="dev", name="G435", battery=None, connected=True),
        ]
    )
    assert reading.name == "G435"
    assert reading.percent == 80
    assert reading.connected


def test_no_container_falls_back_to_the_instance_id() -> None:
    readings = merge([node(instance_id="X", container=None), node(instance_id="Y", container=None)])
    assert [r.device_id for r in readings] == ["X", "Y"]


def test_readings_are_sorted_by_name_and_clamped() -> None:
    readings = merge([node(name="b", container="1", battery=150), node(name="A", container="2")])
    assert [r.name for r in readings] == ["A", "b"]
    assert readings[1].percent == 100


def test_decode() -> None:
    guid = uuid.uuid4()
    assert decode(0x03, b"\x2d") == 45
    assert decode(0x11, b"\xff") is True
    assert decode(0x11, b"\x00") is False
    assert decode(0x12, "MX KEYS S\x00".encode("utf-16-le")) == "MX KEYS S"
    assert decode(0x0D, guid.bytes_le) == str(guid)
    assert decode(0x99, b"\x01") is None
    assert decode(0x03, b"") is None
