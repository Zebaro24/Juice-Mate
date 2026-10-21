"""When to tell the user something, once (docs/architecture.md §6).

Batteries: a device that drops below ALERT_PERCENT raises one alert. It is not raised again until the
device has recovered — charged back to REARM_PERCENT, or put on the charger — so a battery hovering
around the threshold does not nag every poll.

Usage limits: one warning when the current pace runs a window out before it resets, and one "back"
note when a window that was nearly spent resets — the moment to start the heavy task you held back.
"""

from dataclasses import dataclass

from juice_mate.core.reading import Kind, Reading

ALERT_PERCENT = 15
REARM_PERCENT = 20
SPENT_PERCENT = 80  # a window this used, then reset, earns a "back" note
FRESH_PERCENT = 20
NEW_WINDOW_DROP = 5  # usage only goes down when a window resets; a smaller dip is rounding


@dataclass(frozen=True)
class Alert:
    key: str
    title: str
    body: str


class Alerts:
    def __init__(self) -> None:
        self._raised: set[str] = set()
        self._usage: dict[str, int] = {}  # last % used per usage window

    def check(self, readings: list[Reading]) -> list[Alert]:
        alerts = []
        for r in readings:
            if r.percent is None or not r.connected or r.error:
                continue
            key = f"{r.source}:{r.device_id}"
            if r.kind is Kind.CLAUDE:
                alerts.extend(self._usage_alerts(key, r, r.percent))
            elif r.charging or r.percent >= REARM_PERCENT:
                self._raised.discard(key)
            elif r.percent < ALERT_PERCENT and key not in self._raised:
                self._raised.add(key)
                alerts.append(Alert(key, f"{r.name} — {r.percent}%", "Time to charge it."))
        return alerts

    def _usage_alerts(self, key: str, r: Reading, used: int) -> list[Alert]:
        alerts = []
        before = self._usage.get(key)
        self._usage[key] = used
        pace_key = key + ":pace"
        if before is not None and used < before - NEW_WINDOW_DROP:
            self._raised.discard(pace_key)  # the window reset: a new one may warn once again
            if before >= SPENT_PERCENT and used < FRESH_PERCENT:
                alerts.append(Alert(key, f"{r.name} limit is back", f"Now {used}% used — go for the heavy task."))
        if r.limit_at is not None and pace_key not in self._raised:
            self._raised.add(pace_key)
            # limit_at arrives in local time from the source: core/ stays free of the machine's time zone.
            alerts.append(
                Alert(pace_key, f"{r.name}: limit at {r.limit_at:%H:%M} at this pace", f"{used}% used so far.")
            )
        return alerts
