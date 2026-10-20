"""Entry point: `python -m juice_mate` runs the tray; `--dump` prints every reading once and exits."""

import argparse
import sys
import time

from juice_mate.core.metric import Unit, short
from juice_mate.core.reading import level
from juice_mate.sources import Sensor
from juice_mate.sources.bluetooth import Bluetooth
from juice_mate.sources.system import (
    CpuLoad,
    DiskSpeed,
    DiskUsage,
    GpuLoad,
    GpuTemperature,
    MemoryLoad,
    NetworkSpeed,
)


def sensors() -> list[Sensor]:
    """Every sensor there is. Which ones the panel shows is decided at the panel step."""
    return [
        NetworkSpeed("up"),
        NetworkSpeed("down"),
        CpuLoad(),
        MemoryLoad(),
        GpuLoad(),
        GpuTemperature(),
        DiskUsage("C:\\"),
        DiskSpeed("read"),
        DiskSpeed("write"),
    ]


def dump() -> None:
    print("Batteries")
    readings = Bluetooth().poll()
    for r in readings:
        state = r.error or ("connected" if r.connected else "disconnected — % is cached")
        print(f"  {r.name:<32} {r.percent if r.percent is not None else '–':>4}  {level(r):<9} {state}")
    if not readings:
        print("  (no device reports a battery)")
    print("System")
    all_sensors = sensors()
    time.sleep(1)  # rates and loads need an interval
    for m in (s.read() for s in all_sensors):
        unit = "" if m.unit is Unit.CELSIUS else m.unit  # short() already writes "52°"
        print(f"  {m.name:<32} {short(m):>6} {unit:<3}  {m.error or ''}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="juice_mate")
    parser.add_argument("--dump", action="store_true", help="print every reading once and exit")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        # A windowed build (pythonw, PyInstaller --windowed) has no console: the streams are None.
        if stream is not None:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if args.dump:
        dump()
        return
    from juice_mate.tray.icons import run

    run(Bluetooth())
