"""Bluetooth battery levels from Windows device properties (docs/architecture.md §3.1).

Any paired device that reports a battery shows up — nothing here knows the owner's hardware.
Devices are enumerated **including disconnected ones**: Windows keeps their last battery value, and
the connected property is what tells a live reading from a cached one.

One physical device often has several device nodes (the BLE device, its HID children...). They share
a container id, and `merge` folds them into one reading.
"""

import ctypes
import re
import uuid
from collections.abc import Iterable
from ctypes import wintypes
from dataclasses import dataclass

from juice_mate.core.reading import Reading

SOURCE = "bluetooth"
_DEVICE_NODE = re.compile(r"^BTH(ENUM|LE)\\DEV_", re.IGNORECASE)


@dataclass(frozen=True)
class Node:
    """What one device node said. Any field may be missing."""

    instance_id: str
    name: str | None
    battery: int | None
    connected: bool | None
    container: str | None


def merge(nodes: Iterable[Node]) -> list[Reading]:
    """One reading per physical device, ordered by name.

    Within a container: a node that says "connected" wins — its battery is live; otherwise the first
    node with a battery. A device whose nodes never state "connected" is treated as disconnected:
    its number may be a week old.

    The name comes from the device node itself (`BTHENUM\\DEV_…`, `BTHLE\\DEV_…`): profile nodes carry
    suffixes ("G435 Bluetooth Gaming Headset Hands-Free AG") or are services ("SMS/MMS"). No device
    node → the shortest name.
    """
    groups: dict[str, list[Node]] = {}
    for node in nodes:
        groups.setdefault(node.container or node.instance_id, []).append(node)
    readings = []
    for key, members in groups.items():
        # Nodes without a battery still lend their name and their "connected".
        powered = [n for n in members if n.battery is not None]
        if not powered:
            continue
        live = [n for n in members if n.connected]
        best = next((n for n in powered if n.connected), powered[0])
        device = next((n.name for n in members if n.name and _DEVICE_NODE.match(n.instance_id)), None)
        name = device or min((n.name for n in members if n.name), key=len, default=best.instance_id)
        readings.append(
            Reading(
                source=SOURCE,
                device_id=key,
                name=name,
                percent=max(0, min(best.battery or 0, 100)),
                connected=bool(live),
            )
        )
    return sorted(readings, key=lambda r: r.name.lower())


# ── SetupAPI ─────────────────────────────────────────────────────────────────


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", wintypes.DWORD),
        ("data2", wintypes.WORD),
        ("data3", wintypes.WORD),
        ("data4", ctypes.c_ubyte * 8),
    ]


class _PropKey(ctypes.Structure):
    _fields_ = [("fmtid", _Guid), ("pid", wintypes.ULONG)]


class _DevInfoData(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        ("class_guid", _Guid),
        ("dev_inst", wintypes.DWORD),
        ("reserved", ctypes.c_size_t),
    ]


def _key(fmtid: str, pid: int) -> _PropKey:
    return _PropKey(_Guid.from_buffer_copy(uuid.UUID(fmtid).bytes_le), pid)


BATTERY = _key("{104EA319-6EE2-4701-BD47-8DDBF425BBE5}", 2)  # DEVPKEY_Bluetooth_Battery
CONNECTED = _key("{83DA6326-97A6-4088-9453-A1923F573B29}", 15)
FRIENDLY_NAME = _key("{A45C254E-DF1C-4EFD-8020-67D146A850E0}", 14)  # DEVPKEY_Device_FriendlyName
DEVICE_DESC = _key("{A45C254E-DF1C-4EFD-8020-67D146A850E0}", 2)  # DEVPKEY_Device_DeviceDesc
CONTAINER_ID = _key("{8C7ED206-3F8A-4827-B3AB-AE9E1FAEFC6C}", 2)  # DEVPKEY_Device_ContainerId

_DEVPROP_TYPE_BYTE = 0x03
_DEVPROP_TYPE_GUID = 0x0D
_DEVPROP_TYPE_BOOLEAN = 0x11
_DEVPROP_TYPE_STRING = 0x12
_DIGCF_ALLCLASSES = 0x04  # no DIGCF_PRESENT: disconnected devices are wanted too
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_ERROR_INSUFFICIENT_BUFFER = 122


def decode(prop_type: int, data: bytes) -> int | bool | str | None:
    """A raw DEVPROP value → Python; unknown types → None."""
    if prop_type == _DEVPROP_TYPE_BYTE and data:
        return data[0]
    if prop_type == _DEVPROP_TYPE_BOOLEAN and data:
        return data[0] != 0  # DEVPROP_TRUE is 0xFF
    if prop_type == _DEVPROP_TYPE_STRING:
        return data.decode("utf-16-le").rstrip("\x00")
    if prop_type == _DEVPROP_TYPE_GUID and len(data) == 16:
        return str(uuid.UUID(bytes_le=data))
    return None


class _DeviceList:
    def __init__(self) -> None:
        self._api = ctypes.WinDLL("setupapi", use_last_error=True)
        self._api.SetupDiGetClassDevsW.restype = ctypes.c_void_p
        self._handle = self._api.SetupDiGetClassDevsW(None, None, None, _DIGCF_ALLCLASSES)
        if self._handle in (None, _INVALID_HANDLE):
            raise OSError(ctypes.get_last_error(), "SetupDiGetClassDevsW failed")
        self._handle = ctypes.c_void_p(self._handle)

    def close(self) -> None:
        self._api.SetupDiDestroyDeviceInfoList(self._handle)

    def _infos(self) -> list[_DevInfoData]:
        infos: list[_DevInfoData] = []
        while True:
            info = _DevInfoData()
            info.size = ctypes.sizeof(_DevInfoData)
            if not self._api.SetupDiEnumDeviceInfo(self._handle, len(infos), ctypes.byref(info)):
                return infos
            infos.append(info)

    def nodes(self) -> list[Node]:
        """Two passes: find the nodes with a battery, then read every node of their containers.

        Reading names for all devices would cost a property call per device on every poll.
        """
        infos = self._infos()
        batteries: dict[int, int] = {}
        containers: dict[int, str] = {}
        for i, info in enumerate(infos):
            battery = self._prop(info, BATTERY)
            if isinstance(battery, int) and not isinstance(battery, bool):
                batteries[i] = battery
            container = self._prop(info, CONTAINER_ID)
            if isinstance(container, str):
                containers[i] = container
        wanted = {containers[i] for i in batteries if i in containers}
        found = []
        for i, info in enumerate(infos):
            if i not in batteries and containers.get(i) not in wanted:
                continue
            connected = self._prop(info, CONNECTED)
            name = self._prop(info, FRIENDLY_NAME) or self._prop(info, DEVICE_DESC)
            found.append(
                Node(
                    instance_id=self._instance_id(info),
                    name=name if isinstance(name, str) else None,
                    battery=batteries.get(i),
                    connected=connected if isinstance(connected, bool) else None,
                    container=containers.get(i),
                )
            )
        return found

    def _prop(self, info: _DevInfoData, key: _PropKey) -> int | bool | str | None:
        prop_type, size = wintypes.ULONG(), wintypes.DWORD()
        buffer = ctypes.create_string_buffer(256)
        for _attempt in range(2):  # a long name does not fit 256 bytes: retry once with the size asked for
            ok = self._api.SetupDiGetDevicePropertyW(
                self._handle,
                ctypes.byref(info),
                ctypes.byref(key),
                ctypes.byref(prop_type),
                buffer,
                len(buffer),
                ctypes.byref(size),
                0,
            )
            if ok:
                return decode(prop_type.value, buffer.raw[: size.value])
            if ctypes.get_last_error() != _ERROR_INSUFFICIENT_BUFFER:
                return None
            buffer = ctypes.create_string_buffer(size.value)
        return None

    def _instance_id(self, info: _DevInfoData) -> str:
        buffer = ctypes.create_unicode_buffer(512)
        ok = self._api.SetupDiGetDeviceInstanceIdW(self._handle, ctypes.byref(info), buffer, len(buffer), None)
        return buffer.value if ok else f"devinst-{info.dev_inst}"


class Bluetooth:
    """`poll()` never raises: an enumeration failure is one error reading."""

    def poll(self) -> list[Reading]:
        try:
            devices = _DeviceList()
            try:
                return merge(devices.nodes())
            finally:
                devices.close()
        except Exception as e:  # a source never crashes the app
            return [Reading(source=SOURCE, device_id=SOURCE, name="Bluetooth", percent=None, error=str(e))]
