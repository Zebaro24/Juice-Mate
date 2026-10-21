"""The owner's choices that outlive a restart — %LOCALAPPDATA%\\JuiceMate\\settings.json.

Only what the menu can change lives here. A missing or broken file means the defaults: the app must
start on a clean PC (the second one) without anyone writing a config.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# What TrafficMonitor showed on the owner's taskbar (config.ini, 2026-10-20), minus CPU temperature.
DEFAULT_SENSORS = ["net.up", "net.down", "cpu.load", "gpu.load"]


def _path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "JuiceMate" / "settings.json"


@dataclass
class Settings:
    sensors: list[str] = field(default_factory=lambda: list(DEFAULT_SENSORS))

    @staticmethod
    def load(path: Path | None = None) -> "Settings":
        path = path or _path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Settings()
        except (OSError, ValueError):
            log.exception("settings unreadable, using defaults")
            return Settings()
        sensors = raw.get("sensors") if isinstance(raw, dict) else None
        if not isinstance(sensors, list) or not all(isinstance(s, str) for s in sensors):
            return Settings()
        return Settings(sensors=sensors)

    def save(self, path: Path | None = None) -> None:
        path = path or _path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
            temporary.replace(path)  # atomic: a crash mid-write never leaves half a file
        except OSError:
            log.exception("could not save settings")

    def toggle_sensor(self, sensor: str) -> None:
        if sensor in self.sensors:
            self.sensors.remove(sensor)
        else:
            self.sensors.append(sensor)
