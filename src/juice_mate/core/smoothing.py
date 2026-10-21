"""Steady numbers from jittery ones (docs/architecture.md §3.2).

The Hator mouse estimates its charge from the cell voltage, which moves ±1–3 % between two reads a
second apart. The median of the last few reads holds still and still follows a real change within a
few polls.
"""

from collections import deque
from statistics import median


class Median:
    def __init__(self, size: int = 5) -> None:
        self._values: deque[int] = deque(maxlen=size)

    def add(self, value: int) -> int:
        self._values.append(value)
        return round(median(self._values))

    def reset(self) -> None:
        """A jump (charger plugged in, mouse swapped) should not be averaged with the past."""
        self._values.clear()
