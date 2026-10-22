"""The owner's choices that outlive a restart — %LOCALAPPDATA%\\JuiceMate\\settings.json.

Only what the menu can change lives here, plus `claude_prompt`, edited in the file by hand. A missing or
broken file, or a broken field, means the defaults: the app must start on a clean PC (the second one)
without anyone writing a config.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# What TrafficMonitor showed on the owner's taskbar (config.ini, 2026-10-20), minus CPU temperature.
DEFAULT_SENSORS = ["net.up", "net.down", "cpu.load", "gpu.load"]
# What the invisible Claude Code run asks (sources/claude_run.py); its answer becomes a notification.
# `{news}` becomes the last day's tech headlines (sources/news.py). An empty string: the run still
# renews the token and starts the window, silently. The owner wants the day's tech news (2026-10-22),
# in Russian, the owner's language.
NEWS_PROMPT = (
    "Tech news headlines from the last 24 hours:\n{news}\n\n"
    "Pick the two that matter most to an ordinary tech user: a new device and what it can do, a new AI "
    "model, a major launch, release or deal. Skip politics, lawsuits, deals of the day and opinion "
    "pieces. For each, one line in Russian, at most 20 words: what happened and why it is interesting. "
    "Start each line with an emoji. No intro, no links, nothing else."
)
DEFAULT_PROMPT = NEWS_PROMPT


def _path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "JuiceMate" / "settings.json"


@dataclass
class Settings:
    sensors: list[str] = field(default_factory=lambda: list(DEFAULT_SENSORS))
    # Run Claude Code when the 5-hour window is not running. Off until ticked in the menu: it spends
    # the account's quota, and the second PC's user never asked for it.
    keep_claude_window: bool = False
    claude_prompt: str = DEFAULT_PROMPT

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
        if not isinstance(raw, dict):
            return Settings()
        settings = Settings()
        sensors = raw.get("sensors")
        if isinstance(sensors, list) and all(isinstance(s, str) for s in sensors):
            settings.sensors = sensors
        if isinstance(raw.get("keep_claude_window"), bool):
            settings.keep_claude_window = raw["keep_claude_window"]
        if isinstance(raw.get("claude_prompt"), str):
            settings.claude_prompt = raw["claude_prompt"]
        return settings

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
