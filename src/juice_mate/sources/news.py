"""Tech headlines of the last day, for the Claude Code run's `{news}` prompt (sources/claude_run.py).

Juice-Mate fetches the feeds itself and hands Haiku only the titles (~700 tokens): letting Claude Code
search the web would cost thousands of tokens of search results per run. Feeds chosen 2026-10-22 for
consumer tech — devices, AI models, launches; Ars Technica (much politics) and Hacker News (niche) left out.

Feeds are parsed with defusedxml (no external entities, no entity-expansion bombs) under a size cap.
A feed that fails is skipped; none at all → [] and the run falls back to a silent prompt.
"""

import json
import logging
import xml.etree.ElementTree as ET  # the Element type only; parsing goes through defusedxml
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from defusedxml import ElementTree as SafeET

from juice_mate import folders
from juice_mate.core.news import Story

log = logging.getLogger(__name__)

FEEDS = {
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Engadget": "https://www.engadget.com/rss.xml",
}
SITES = ("theverge.com", "techcrunch.com", "engadget.com")  # the only hosts an article link may open
WINDOW = timedelta(hours=24)
MAX_BYTES = 2_000_000
MAX_ITEMS = 45  # ~15 tokens a title
_ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class Headline:
    source: str
    title: str
    url: str | None
    published: datetime


def _published(entry: ET.Element) -> datetime | None:
    raw = entry.findtext("pubDate")
    try:
        if raw:
            return parsedate_to_datetime(raw)
        raw = entry.findtext(_ATOM + "published") or entry.findtext(_ATOM + "updated")
        return datetime.fromisoformat(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _link(entry: ET.Element) -> str | None:
    """RSS: <link>text</link>; Atom: <link href=…> (the alternate one when there are several)."""
    text = (entry.findtext("link") or "").strip()
    if text.startswith("http"):
        return text
    for link in entry.findall(_ATOM + "link"):
        if link.get("rel", "alternate") == "alternate" and (link.get("href") or "").startswith("http"):
            return link.get("href")
    return None


def parse(name: str, content: bytes, since: datetime) -> list[Headline]:
    """Every RSS item or Atom entry newer than `since`."""
    root = SafeET.fromstring(content)
    found = []
    for entry in root.iter():
        if entry.tag not in ("item", _ATOM + "entry"):
            continue
        title = (entry.findtext("title") or entry.findtext(_ATOM + "title") or "").strip()
        published = _published(entry)
        if title and published is not None and published.tzinfo is not None and published >= since:
            found.append(Headline(name, " ".join(title.split()), _link(entry), published))
    return found


def fetch(
    get: Callable[..., httpx.Response] = httpx.get, now: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> list[Headline]:
    """The last day's headlines from every feed, newest first; [] when none came."""
    since = now() - WINDOW
    found: list[Headline] = []
    for name, url in FEEDS.items():
        try:
            response = get(url, timeout=10.0, follow_redirects=True, headers={"User-Agent": "Juice-Mate"})
            response.raise_for_status()
            if len(response.content) > MAX_BYTES:
                raise ValueError(f"{len(response.content)} bytes")
            found.extend(parse(name, response.content, since))
        except (httpx.HTTPError, ET.ParseError, ValueError) as e:  # defusedxml refusals are ValueErrors
            log.warning("news feed %s skipped: %s", name, e)
    found.sort(key=lambda h: h.published, reverse=True)
    return found[:MAX_ITEMS]


def numbered(headlines: list[Headline]) -> str:
    """What the prompt gets: `[7] [The Verge] Title`, one per line — the number is how the answer
    points back at the article it is about."""
    return "\n".join(f"[{i}] [{h.source}] {h.title}" for i, h in enumerate(headlines, 1))


# ── what was told: news.json in the data folder, the menu's "Recent news" ──────

KEEP = 30


def _log_path() -> Path:
    return folders.data() / "news.json"


def remember(stories: list[Story], at: float) -> None:
    told = [{"text": s.text, "url": s.url, "source": s.source, "at": at} for s in stories]
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps((told + recent_raw())[:KEEP], ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        log.exception("could not keep the news")


def recent_raw() -> list[dict[str, Any]]:
    try:
        raw = json.loads(_log_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in raw if isinstance(r, dict) and isinstance(r.get("text"), str)] if isinstance(raw, list) else []


def recent(count: int = 5) -> list[Story]:
    """The newest told stories first."""
    return [
        Story(r["text"], r.get("url") if isinstance(r.get("url"), str) else None, r.get("source")) for r in recent_raw()
    ][:count]
