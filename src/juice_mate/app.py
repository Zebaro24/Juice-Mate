"""Entry point: one tray icon for now; sources join it from step 02 on."""

import pystray

from juice_mate.core.reading import Reading, label, level
from juice_mate.tray.drawing import draw


def main() -> None:
    placeholder = Reading(source="app", device_id="app", name="Juice-Mate", percent=None)
    icon = pystray.Icon(
        "juice-mate",
        icon=draw(label(placeholder), level(placeholder)),
        title="Juice-Mate — no devices yet",
        menu=pystray.Menu(pystray.MenuItem("Quit", lambda icon, _item: icon.stop())),
    )
    icon.run()
