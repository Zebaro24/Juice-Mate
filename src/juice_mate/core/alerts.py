"""When to tell the user about a battery, once (docs/architecture.md §6).

A device that drops below ALERT_PERCENT raises one alert. It is not raised again until the device
has recovered — charged back to REARM_PERCENT, or put on the charger — so a battery hovering around
the threshold does not nag every poll.
"""

from dataclasses import dataclass

from juice_mate.core.reading import Kind, Reading

ALERT_PERCENT = 15
REARM_PERCENT = 20


@dataclass(frozen=True)
class Alert:
    key: str
    title: str
    body: str


class Alerts:
    def __init__(self) -> None:
        self._raised: set[str] = set()

    def check(self, readings: list[Reading]) -> list[Alert]:
        alerts = []
        for r in readings:
            if r.kind is Kind.CLAUDE or r.percent is None or not r.connected or r.error:
                continue
            key = f"{r.source}:{r.device_id}"
            if r.charging or r.percent >= REARM_PERCENT:
                self._raised.discard(key)
            elif r.percent < ALERT_PERCENT and key not in self._raised:
                self._raised.add(key)
                alerts.append(Alert(key, f"{r.name} — {r.percent}%", "Time to charge it."))
        return alerts
