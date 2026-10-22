"""Tech headlines of the last day, for the Claude Code run's `{news}` prompt (sources/claude_run.py).

Juice-Mate fetches the feeds itself and hands Haiku only the titles (~700 tokens): letting Claude Code
search the web would cost thousands of tokens of search results per run. Feeds chosen 2026-10-22 for
consumer tech — devices, AI models, launches; Ars Technica (much politics) and Hacker News (niche) left out.

Feeds are parsed with defusedxml (no external entities, no entity-expansion bombs) under a size cap.
A feed that fails is skipped; none at all → "" and the run falls back to a silent prompt.
"""

import logging
import xml.etree.ElementTree as ET  # the Element type only; parsing goes through defusedxml
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx
from defusedxml import ElementTree as SafeET

log = logging.getLogger(__name__)

FEEDS = {
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Engadget": "https://www.engadget.com/rss.xml",
}
WINDOW = timedelta(hours=24)
MAX_BYTES = 2_000_000
MAX_ITEMS = 45  # ~15 tokens a title
_ATOM = "{http://www.w3.org/2005/Atom}"


def _published(entry: ET.Element) -> datetime | None:
    raw = entry.findtext("pubDate")
    try:
        if raw:
            return parsedate_to_datetime(raw)
        raw = entry.findtext(_ATOM + "published") or entry.findtext(_ATOM + "updated")
        return datetime.fromisoformat(raw) if raw else None
    except (TypeError, ValueError):
        return None


def parse(name: str, content: bytes, since: datetime) -> list[tuple[datetime, str]]:
    """(published, "[source] title") for every RSS item or Atom entry newer than `since`."""
    root = SafeET.fromstring(content)
    found = []
    for entry in root.iter():
        if entry.tag not in ("item", _ATOM + "entry"):
            continue
        title = (entry.findtext("title") or entry.findtext(_ATOM + "title") or "").strip()
        published = _published(entry)
        if title and published is not None and published.tzinfo is not None and published >= since:
            found.append((published, f"[{name}] {' '.join(title.split())}"))
    return found


def headlines(
    get: Callable[..., httpx.Response] = httpx.get, now: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> str:
    """The last day's titles from every feed, newest first, one per line; "" when none came."""
    since = now() - WINDOW
    found: list[tuple[datetime, str]] = []
    for name, url in FEEDS.items():
        try:
            response = get(url, timeout=10.0, follow_redirects=True, headers={"User-Agent": "Juice-Mate"})
            response.raise_for_status()
            if len(response.content) > MAX_BYTES:
                raise ValueError(f"{len(response.content)} bytes")
            found.extend(parse(name, response.content, since))
        except (httpx.HTTPError, ET.ParseError, ValueError) as e:  # defusedxml refusals are ValueErrors
            log.warning("news feed %s skipped: %s", name, e)
    found.sort(reverse=True)
    return "\n".join(f"- {line}" for _when, line in found[:MAX_ITEMS])
