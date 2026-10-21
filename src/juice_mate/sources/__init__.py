"""Data sources. Every IO call lives here; a source reports errors as readings, never raises."""

from collections.abc import Sequence
from typing import Protocol

from juice_mate.core.metric import Metric
from juice_mate.core.reading import Reading


class Source(Protocol):
    """Batteries: one poll may find several devices, or none."""

    def poll(self) -> list[Reading]: ...


class Sensor(Protocol):
    """One system value. `sensor` is its stable id (settings, item keys), `name` its menu label."""

    sensor: str
    name: str

    def read(self) -> Metric: ...


def poll_all(sources: Sequence[Source]) -> list[Reading]:
    """A source that raises becomes one error reading — the app never stops over it."""
    readings = []
    for source in sources:
        try:
            readings.extend(source.poll())
        except Exception as e:  # any bug in a source must not end the poll loop
            name = type(source).__name__
            readings.append(Reading(source=name, device_id=name, name=name, percent=None, error=repr(e)))
    return readings
