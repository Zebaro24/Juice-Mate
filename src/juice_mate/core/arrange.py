"""What the owner changed about the panel: device names, icons, hidden items, order and placement
(docs/architecture.md §6a). Pure: the settings come in as plain values.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from juice_mate.core.display import Item
from juice_mate.core.reading import Kind, Reading

# Where an item can sit: the main taskbar's two strips, and the second monitor's (§4b).
LEFT, RIGHT, SECOND_LEFT, SECOND_RIGHT = "left", "right", "second-left", "second-right"
PLACES = (LEFT, RIGHT, SECOND_LEFT, SECOND_RIGHT)
SYSTEM = "system:"  # the key prefix of sensor items


@dataclass(frozen=True)
class DevicePref:
    """The owner's word on one device; `None` keeps what the source found."""

    name: str | None = None
    kind: Kind | None = None  # the icon, for a device whose kind was guessed wrong
    hidden: bool = False


def key(reading: Reading) -> str:
    """The same key the panel item gets: `source:device_id`."""
    return f"{reading.source}:{reading.device_id}"


def personalise(readings: Sequence[Reading], prefs: Mapping[str, DevicePref]) -> list[Reading]:
    """Hidden devices dropped, names and icons replaced. A usage window keeps its spark: its kind is
    what makes "high" the bad end."""
    shown = []
    for r in readings:
        pref = prefs.get(key(r))
        if pref is None:
            shown.append(r)
        elif not pref.hidden:
            kind = r.kind if r.kind is Kind.CLAUDE or pref.kind in (None, Kind.CLAUDE) else pref.kind
            shown.append(replace(r, name=pref.name or r.name, kind=kind))
    return shown


def default_place(item_key: str) -> str:
    """Sensors at the taskbar's left end, everything else by the clock (owner, 2026-10-22)."""
    return LEFT if item_key.startswith(SYSTEM) else RIGHT


def arrange(items: Sequence[Item], order: Sequence[str], placement: Mapping[str, str]) -> dict[str, list[Item]]:
    """Items per place. Keys named in `order` come first in that order; the rest keep the default
    order after them, so a new device never jumps ahead of the ones the owner arranged."""
    rank = {k: i for i, k in enumerate(order)}
    ordered = sorted(enumerate(items), key=lambda pair: (rank.get(pair[1].key, len(rank)), pair[0]))
    places: dict[str, list[Item]] = {place: [] for place in PLACES}
    for _index, it in ordered:
        place = placement.get(it.key, default_place(it.key))
        places[place if place in places else default_place(it.key)].append(it)
    return places
