"""Hator Stellar Pro Wireless through its USB dongle (docs/architecture.md §3.2).

Request: feature report `07 89 00…` to the vendor interface (usage page 0xFF01), then read feature
report 7, eight bytes: `07 89 XX 01 02 03 00 00`, where XX is the charge in %.

The dongle not plugged in → no reading at all (the second PC). Plugged in but no answer → the mouse
is off or asleep → disconnected. On a cable the mouse also appears as its own USB device (PID 5B49) —
that is the charging signal.
"""

from collections.abc import Sequence

import hid

from juice_mate.core.reading import Kind, Reading
from juice_mate.core.smoothing import Median

SOURCE = "hator"
VENDOR = 0x248A
DONGLE = 0x5B4A
WIRED = 0x5B49
VENDOR_PAGE = 0xFF01
REPORT_ID = 0x07
COMMAND = 0x89
REQUEST = [REPORT_ID, COMMAND, 0, 0, 0, 0, 0, 0]
REPLY_LENGTH = 8


def parse(reply: Sequence[int]) -> int | None:
    """The charge from a reply, or None when the reply is not one (a sleeping mouse answers zeros)."""
    if len(reply) < 3 or reply[0] != REPORT_ID or reply[1] != COMMAND:
        return None
    percent = reply[2]
    return percent if 0 < percent <= 100 else None


class Hator:
    def __init__(self) -> None:
        self._median = Median()
        self._was_charging: bool | None = None

    def poll(self) -> list[Reading]:
        dongles = [d for d in hid.enumerate(VENDOR, DONGLE) if d["usage_page"] == VENDOR_PAGE]
        if not dongles:
            self._median.reset()
            return []
        dongle = dongles[0]
        name = f"Hator {dongle.get('product_string') or 'mouse'}".strip()
        charging = bool(hid.enumerate(VENDOR, WIRED))
        if charging != self._was_charging:
            self._median.reset()  # the voltage jumps when the charger comes or goes
            self._was_charging = charging
        device_id = f"{VENDOR:04x}:{DONGLE:04x}"
        device = hid.device()
        try:
            device.open_path(dongle["path"])
        except OSError as e:  # the dongle is there but cannot be opened: a real fault, say so
            return [Reading(SOURCE, device_id, name, None, kind=Kind.MOUSE, error=f"cannot open the dongle: {e}")]
        try:
            device.send_feature_report(REQUEST)
            percent = parse(device.get_feature_report(REPORT_ID, REPLY_LENGTH))
        except OSError:
            percent = None  # the dongle did not get an answer: the mouse is off or asleep
        finally:
            device.close()
        if percent is None:
            self._median.reset()
            return [Reading(SOURCE, device_id, name, None, connected=False, charging=charging, kind=Kind.MOUSE)]
        return [Reading(SOURCE, device_id, name, self._median.add(percent), charging=charging, kind=Kind.MOUSE)]
