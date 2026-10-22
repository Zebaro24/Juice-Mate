"""System sensors without a kernel driver (docs/architecture.md §4a).

Each class reads one value. Rates (network, disk) remember the previous counters, so the first read
after construction already has a value: the constructor takes the baseline.
"""

import contextlib
import ctypes
import re
import threading
import time
from collections.abc import Callable, Mapping
from ctypes import wintypes

import psutil

from juice_mate.core.metric import OFFLINE, Metric, Unit


def _failed(sensor: str, name: str, unit: Unit, error: Exception | str) -> Metric:
    return Metric(sensor=sensor, name=name, value=None, unit=unit, error=str(error))


class _Rate:
    """Bytes per second between two reads of a growing counter.

    The baseline is taken at construction when possible; a counter that cannot be read yet (adapter
    missing) takes it on the first successful read instead, which then reports 0.
    """

    def __init__(self, counter: Callable[[], int], clock: Callable[[], float] = time.monotonic) -> None:
        self._counter = counter
        self._clock = clock
        self._last: tuple[float, int] | None = None
        try:
            self._last = (clock(), counter())
        except Exception:  # a constructor never raises; read() reports the error
            self._last = None

    def per_second(self) -> float:
        now, value = self._clock(), self._counter()
        if self._last is None:
            self._last = (now, value)
            return 0.0
        then, before = self._last
        self._last = (now, value)
        elapsed = now - then
        # A counter that went backwards is a reset adapter or a wrapped counter, not negative traffic.
        return max(value - before, 0) / elapsed if elapsed > 0 else 0.0


class NetworkSpeed:
    """Upload or download speed. `interface=None` sums every adapter except loopback.

    Virtual adapters (Hyper-V vEthernet, VPN) carry the same bytes as the real one; name an
    interface when the sum double-counts.
    """

    def __init__(self, direction: str, interface: str | None = None) -> None:
        if direction not in ("up", "down"):
            raise ValueError(f"direction must be 'up' or 'down', not {direction!r}")
        self._direction = direction
        self._interface = interface
        self.sensor = f"net.{direction}" + (f".{interface}" if interface else "")
        self.name = "Upload" if direction == "up" else "Download"
        self._rate = _Rate(self._total)

    def _total(self) -> int:
        counters = psutil.net_io_counters(pernic=True)
        chosen = (
            [counters[self._interface]]
            if self._interface
            else [c for nic, c in counters.items() if "loopback" not in nic.lower()]
        )
        return sum(c.bytes_sent if self._direction == "up" else c.bytes_recv for c in chosen)

    def read(self) -> Metric:
        try:
            return Metric(self.sensor, self.name, self._rate.per_second(), Unit.BYTES_PER_SECOND)
        except Exception as e:
            return _failed(self.sensor, self.name, Unit.BYTES_PER_SECOND, e)


class DiskSpeed:
    """Read or write speed summed over all physical disks."""

    def __init__(self, direction: str) -> None:
        if direction not in ("read", "write"):
            raise ValueError(f"direction must be 'read' or 'write', not {direction!r}")
        self._direction = direction
        self.sensor = f"disk.{direction}"
        self.name = "Disk read" if direction == "read" else "Disk write"
        self._rate = _Rate(self._total)

    def _total(self) -> int:
        counters = psutil.disk_io_counters()
        if counters is None:
            raise OSError("no disk counters")
        return counters.read_bytes if self._direction == "read" else counters.write_bytes

    def read(self) -> Metric:
        try:
            return Metric(self.sensor, self.name, self._rate.per_second(), Unit.BYTES_PER_SECOND)
        except Exception as e:
            return _failed(self.sensor, self.name, Unit.BYTES_PER_SECOND, e)


class CpuLoad:
    sensor = "cpu.load"
    name = "CPU"

    def __init__(self) -> None:
        with contextlib.suppress(Exception):
            psutil.cpu_percent()  # the first call only sets the baseline and returns 0.0

    def read(self) -> Metric:
        try:
            return Metric(self.sensor, self.name, psutil.cpu_percent(), Unit.PERCENT)
        except Exception as e:
            return _failed(self.sensor, self.name, Unit.PERCENT, e)


class MemoryLoad:
    sensor = "memory.load"
    name = "Memory"

    def read(self) -> Metric:
        try:
            return Metric(self.sensor, self.name, psutil.virtual_memory().percent, Unit.PERCENT)
        except Exception as e:
            return _failed(self.sensor, self.name, Unit.PERCENT, e)


class DiskUsage:
    """How full a drive is."""

    def __init__(self, path: str = "C:\\") -> None:
        self._path = path
        self.sensor = f"disk.usage.{path.rstrip(':/\\').lower()}"
        self.name = f"Disk {path.rstrip('/\\')}"

    def read(self) -> Metric:
        try:
            return Metric(self.sensor, self.name, psutil.disk_usage(self._path).percent, Unit.PERCENT)
        except Exception as e:
            return _failed(self.sensor, self.name, Unit.PERCENT, e)


# ── GPU load: the PDH counter Task Manager uses ─────────────────────────────

_ENGINE = re.compile(r"luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+)_phys_(\d+)_eng_(\d+)_engtype_3D", re.IGNORECASE)


def gpu_load(instances: Mapping[str, float]) -> float:
    """Task Manager's number: per 3D engine, sum the processes using it; the busiest engine wins.

    Instance names look like `pid_1234_luid_0x0000_0x9C2A_phys_0_eng_0_engtype_3D`.
    """
    engines: dict[tuple[str, ...], float] = {}
    for name, value in instances.items():
        match = _ENGINE.search(name)
        if match:
            engines[match.groups()] = engines.get(match.groups(), 0.0) + value
    return min(max(engines.values(), default=0.0), 100.0)


class _PdhValue(ctypes.Structure):
    # PDH_FMT_COUNTERVALUE with PDH_FMT_DOUBLE: CStatus, then the double of the union.
    _fields_ = [("status", wintypes.DWORD), ("value", ctypes.c_double)]


class _PdhItem(ctypes.Structure):
    # PDH_FMT_COUNTERVALUE_ITEM_W — nested, so the layout is right on 32- and 64-bit alike.
    _fields_ = [("name", wintypes.LPWSTR), ("value", _PdhValue)]


_PDH_FMT_DOUBLE = 0x00000200
_PDH_MORE_DATA = 0x800007D2
_PDH_NO_DATA = {0x800007D1, 0x800007D5}  # PDH_CSTATUS_NO_INSTANCE, PDH_NO_DATA: no 3D work at all
_PDH_VALID = {0, 1}  # PDH_CSTATUS_VALID_DATA, PDH_CSTATUS_NEW_DATA
_GPU_COUNTER = r"\GPU Engine(*engtype_3D)\Utilization Percentage"


class _PdhArray:
    """One wildcard PDH counter, read as {instance: value}. A rate counter needs two samples, so the
    first one is taken at construction."""

    def __init__(self, path: str) -> None:
        self._pdh = ctypes.WinDLL("pdh")
        self._query = wintypes.HANDLE()
        self._counter = wintypes.HANDLE()
        self.error: str | None = None
        status = self._pdh.PdhOpenQueryW(None, None, ctypes.byref(self._query))
        if status == 0:
            status = self._pdh.PdhAddEnglishCounterW(self._query, path, None, ctypes.byref(self._counter))
        if status == 0:
            self._pdh.PdhCollectQueryData(self._query)
        else:
            self.error = f"PDH status 0x{status & 0xFFFFFFFF:08X}"

    def instances(self) -> dict[str, float]:
        status = self._pdh.PdhCollectQueryData(self._query)
        if status != 0:
            raise OSError(f"PdhCollectQueryData 0x{status & 0xFFFFFFFF:08X}")
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        get = self._pdh.PdhGetFormattedCounterArrayW
        status = get(self._counter, _PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None)
        if status & 0xFFFFFFFF in _PDH_NO_DATA:
            return {}
        if status & 0xFFFFFFFF != _PDH_MORE_DATA:
            raise OSError(f"PdhGetFormattedCounterArrayW 0x{status & 0xFFFFFFFF:08X}")
        buffer = ctypes.create_string_buffer(size.value)
        status = get(self._counter, _PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), buffer)
        if status != 0:
            raise OSError(f"PdhGetFormattedCounterArrayW 0x{status & 0xFFFFFFFF:08X}")
        items = ctypes.cast(buffer, ctypes.POINTER(_PdhItem))
        return {items[i].name: items[i].value.value for i in range(count.value) if items[i].value.status in _PDH_VALID}

    def close(self) -> None:
        if self._query:
            self._pdh.PdhCloseQuery(self._query)
            self._query = wintypes.HANDLE()


class GpuLoad:
    sensor = "gpu.load"
    name = "GPU"

    def __init__(self) -> None:
        self._counter = _PdhArray(_GPU_COUNTER)

    def read(self) -> Metric:
        if self._counter.error:
            return _failed(self.sensor, self.name, Unit.PERCENT, self._counter.error)
        try:
            return Metric(self.sensor, self.name, gpu_load(self._counter.instances()), Unit.PERCENT)
        except Exception as e:
            return _failed(self.sensor, self.name, Unit.PERCENT, e)

    def close(self) -> None:
        self._counter.close()


# ── Memory in gigabytes: RAM from psutil, VRAM as Task Manager counts it ────

_VRAM_COUNTER = r"\GPU Adapter Memory(*)\Dedicated Usage"
_DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


def video_memory_total() -> float | None:
    """The largest adapter's memory in bytes, as the driver reports it to Windows; None if unknown."""
    import winreg

    sizes = []
    with contextlib.suppress(OSError), winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS) as root:
        for index in range(64):
            try:
                name = winreg.EnumKey(root, index)
            except OSError:
                break
            with contextlib.suppress(OSError), winreg.OpenKey(root, name) as adapter:
                value, _kind = winreg.QueryValueEx(adapter, "HardwareInformation.qwMemorySize")
                if isinstance(value, int):
                    sizes.append(float(value))
    return max(sizes, default=None)


class MemoryUsed:
    sensor = "memory.used"
    name = "RAM used"

    def read(self) -> Metric:
        try:
            memory = psutil.virtual_memory()
            return Metric(self.sensor, self.name, float(memory.used), Unit.BYTES, total=float(memory.total))
        except Exception as e:
            return _failed(self.sensor, self.name, Unit.BYTES, e)


class VideoMemoryUsed:
    """Dedicated video memory in use on the busiest adapter — the "Dedicated GPU memory" of Task Manager."""

    sensor = "gpu.memory"
    name = "VRAM used"

    def __init__(self) -> None:
        self._counter = _PdhArray(_VRAM_COUNTER)
        self._total = video_memory_total()

    def read(self) -> Metric:
        if self._counter.error:
            return _failed(self.sensor, self.name, Unit.BYTES, self._counter.error)
        try:
            used = max(self._counter.instances().values(), default=0.0)
            return Metric(self.sensor, self.name, used, Unit.BYTES, total=self._total)
        except Exception as e:
            return _failed(self.sensor, self.name, Unit.BYTES, e)

    def close(self) -> None:
        self._counter.close()


# ── GPU temperature: NVML, shipped with the NVIDIA driver ───────────────────

_NVML_TEMPERATURE_GPU = 0


class GpuTemperature:
    """NVIDIA only. Other vendors have no user-mode temperature API worth depending on."""

    sensor = "gpu.temperature"
    name = "GPU temp"

    def __init__(self, index: int = 0) -> None:
        self._handle = ctypes.c_void_p()
        self._error: str | None = None
        self._initialised = False
        try:
            self._nvml = ctypes.WinDLL("nvml.dll")
        except OSError:
            self._error = "no NVIDIA driver (nvml.dll not found)"
            return
        try:
            status = self._nvml.nvmlInit_v2()
            self._initialised = status == 0
            if status == 0:
                status = self._nvml.nvmlDeviceGetHandleByIndex_v2(index, ctypes.byref(self._handle))
        except AttributeError as e:  # an old driver without these exports
            self._error = f"NVML: {e}"
            return
        if status != 0:
            self._error = f"NVML status {status}"

    def read(self) -> Metric:
        if self._error:
            return _failed(self.sensor, self.name, Unit.CELSIUS, self._error)
        value = ctypes.c_uint()
        try:
            status = self._nvml.nvmlDeviceGetTemperature(self._handle, _NVML_TEMPERATURE_GPU, ctypes.byref(value))
        except Exception as e:
            return _failed(self.sensor, self.name, Unit.CELSIUS, e)
        if status != 0:
            return _failed(self.sensor, self.name, Unit.CELSIUS, f"NVML status {status}")
        return Metric(self.sensor, self.name, float(value.value), Unit.CELSIUS)

    def close(self) -> None:
        if self._initialised:
            self._nvml.nvmlShutdown()
            self._initialised = False


# ── Ping: ICMP echo through iphlpapi — no admin, no raw socket ───────────────

PING_TARGET = "1.1.1.1"  # Cloudflare's resolver: answers ICMP everywhere, rarely blocked
PING_EVERY = 2.0
PING_TIMEOUT_MS = 1000
PING_MISSES_OFFLINE = 2  # one lost packet is noise; two in a row is "the internet is gone"
PING_IDLE = 10.0  # seconds without a read: the sensor is off the panel, stop pinging


class _IpOptions(ctypes.Structure):
    _fields_ = [
        ("ttl", ctypes.c_ubyte),
        ("tos", ctypes.c_ubyte),
        ("flags", ctypes.c_ubyte),
        ("size", ctypes.c_ubyte),
        ("data", ctypes.c_void_p),
    ]


class _EchoReply(ctypes.Structure):
    _fields_ = [
        ("address", wintypes.ULONG),
        ("status", wintypes.ULONG),
        ("round_trip", wintypes.ULONG),
        ("data_size", wintypes.USHORT),
        ("reserved", wintypes.USHORT),
        ("data", ctypes.c_void_p),
        ("options", _IpOptions),
    ]


def ping_once(target: str = PING_TARGET, timeout_ms: int = PING_TIMEOUT_MS) -> float | None:
    """Round trip in milliseconds, or None when nothing answered in time. Raises OSError if ICMP
    itself is unavailable."""
    import socket

    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    iphlpapi.IcmpCreateFile.restype = wintypes.HANDLE
    iphlpapi.IcmpSendEcho.argtypes = [
        wintypes.HANDLE,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.WORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    iphlpapi.IcmpCloseHandle.argtypes = [wintypes.HANDLE]
    handle = iphlpapi.IcmpCreateFile()
    if not handle or handle == wintypes.HANDLE(-1).value:
        raise OSError(f"IcmpCreateFile failed ({ctypes.get_last_error()})")
    try:
        # IPAddr is the address's bytes in network order, read as a little-endian ULONG.
        address = int.from_bytes(socket.inet_aton(target), "little")
        payload = b"juice-mate"
        size = ctypes.sizeof(_EchoReply) + len(payload) + 16
        reply = ctypes.create_string_buffer(size)
        answers = iphlpapi.IcmpSendEcho(handle, address, payload, len(payload), None, reply, size, timeout_ms)
        if answers == 0:
            return None
        echo = _EchoReply.from_buffer(reply)
        return float(echo.round_trip) if echo.status == 0 else None
    finally:
        iphlpapi.IcmpCloseHandle(handle)


class Ping:
    """Latency to PING_TARGET, measured on a thread of its own: a lost packet waits a whole second,
    which the poll loop must not.

    Only while shown: the thread starts at the first read and stops when nobody has read for
    PING_IDLE — a PC that never turns the sensor on never sends a packet."""

    sensor = "net.ping"
    name = "Ping"

    def __init__(self, probe: Callable[[], float | None] = ping_once, start: bool = True) -> None:
        self._probe = probe
        self._value: float | None = None
        self._misses = 0
        self._error: str | None = "measuring…"
        self._stop = threading.Event()
        self._background = start
        self._thread: threading.Thread | None = None
        self._last_read = 0.0

    def _loop(self) -> None:
        while not self._stop.is_set() and time.monotonic() - self._last_read < PING_IDLE:
            self.measure()
            self._stop.wait(PING_EVERY)

    def measure(self) -> None:
        try:
            rtt = self._probe()
        except Exception as e:
            self._value, self._error = None, str(e)[:80]
            return
        if rtt is None:
            self._misses += 1
            if self._misses >= PING_MISSES_OFFLINE:
                self._value, self._error = None, OFFLINE
            return
        self._misses, self._value, self._error = 0, rtt, None

    def read(self) -> Metric:
        self._last_read = time.monotonic()
        if self._background and (self._thread is None or not self._thread.is_alive()):
            self._error = self._error if self._value is not None else "measuring…"
            self._thread = threading.Thread(target=self._loop, name="ping", daemon=True)
            self._thread.start()
        if self._value is None:
            return _failed(self.sensor, self.name, Unit.MILLISECONDS, self._error or OFFLINE)
        return Metric(self.sensor, self.name, self._value, Unit.MILLISECONDS)

    def close(self) -> None:
        self._stop.set()
