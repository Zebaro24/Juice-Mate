"""Data sources. Every IO call lives here; a source reports errors as readings, never raises."""

from typing import Protocol

from juice_mate.core.metric import Metric
from juice_mate.core.reading import Reading


class Source(Protocol):
    """Batteries: one poll may find several devices, or none."""

    def poll(self) -> list[Reading]: ...


class Sensor(Protocol):
    """One system value."""

    def read(self) -> Metric: ...
