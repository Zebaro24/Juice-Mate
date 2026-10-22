"""Tying the news answer back to its articles (docs/architecture.md §3.3). Pure.

The prompt numbers the headlines (`[7] [The Verge] …`) and asks each line of the answer to end with
its number (`… #7`). This turns the answer into stories that know their link; a line without a
number, or with one that matches nothing, is still a story — just without a link.
"""

import re
from dataclasses import dataclass

_MARK = re.compile(r"\s*[\[(]?#\s*(\d+)[\])]?\s*$")


@dataclass(frozen=True)
class Story:
    text: str
    url: str | None = None
    source: str | None = None


def stories(answer: str, links: list[tuple[str, str | None]]) -> list[Story]:
    """`links[i]` is (source, url) of headline number i + 1."""
    told = []
    for line in answer.splitlines():
        line = line.strip()
        if not line:
            continue
        mark = _MARK.search(line)
        if mark is None:
            told.append(Story(line))
            continue
        number = int(mark.group(1))
        text = line[: mark.start()].rstrip(" ·—-")
        source, url = links[number - 1] if 1 <= number <= len(links) else (None, None)
        told.append(Story(text, url, source))
    return told
