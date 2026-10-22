"""What each item read over time — the hover card's chart and its story (docs/architecture.md §6b).

Pure: times are seconds since the epoch, handed in by the caller. Two instances live in the app: a long
one for batteries and usage windows (a sample every two minutes, two days, kept on disk) and a short
one for sensors (every tick, one hour, memory only).

Thread-safe: the poll loop adds, the panel thread reads for the card.
"""

import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Sample:
    t: float
    value: float
    charging: bool = False


class History:
    def __init__(self, keep: float, step: float) -> None:
        """`keep`: seconds of history; `step`: at most one sample per this many seconds — a newer one
        within the step replaces the last (the latest value wins, the spacing stays even)."""
        self.keep = keep
        self.step = step
        self._series: dict[str, list[Sample]] = {}
        self._lock = threading.Lock()

    def add(self, key: str, t: float, value: float, charging: bool = False) -> None:
        with self._lock:
            series = self._series.setdefault(key, [])
            sample = Sample(t, value, charging)
            # One sample per step-long bucket of time, the newest value in it: the last one keeps moving
            # until its bucket ends, the spacing stays even.
            if series and series[-1].t // self.step == t // self.step:
                series[-1] = sample
            else:
                series.append(sample)
            cutoff = t - self.keep
            while series and series[0].t < cutoff:
                series.pop(0)

    def series(self, key: str, since: float | None = None) -> list[Sample]:
        with self._lock:
            samples = list(self._series.get(key, []))
        return [s for s in samples if since is None or s.t >= since]

    def dump(self) -> dict[str, list[list[Any]]]:
        """For the file: {key: [[t, value, charging], ...]}."""
        with self._lock:
            return {k: [[s.t, s.value, s.charging] for s in v] for k, v in self._series.items()}

    def load(self, raw: Any, now: float) -> None:
        """From the file; anything that does not look like samples is skipped, too-old samples dropped."""
        if not isinstance(raw, dict):
            return
        with self._lock:
            for key, rows in raw.items():
                if not isinstance(key, str) or not isinstance(rows, list):
                    continue
                kept = [
                    Sample(float(r[0]), float(r[1]), bool(r[2]) if len(r) > 2 else False)
                    for r in rows
                    if isinstance(r, list) and len(r) >= 2 and all(isinstance(x, int | float) for x in r[:2])
                ]
                self._series[key] = [s for s in kept if now - s.t <= self.keep]
