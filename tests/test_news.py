from datetime import UTC, datetime
from typing import Any

import httpx

from juice_mate.sources.news import FEEDS, headlines, parse

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Apple unveils   iPhone 18</title><pubDate>Thu, 22 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>Old story</title><pubDate>Mon, 19 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>No date</title></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Anthropic ships a new model</title><published>2026-10-22T10:00:00-04:00</published></entry>
</feed>"""


def test_parse_keeps_the_last_day_from_rss_and_atom() -> None:
    since = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    assert [line for _t, line in parse("A", RSS, since)] == ["[A] Apple unveils iPhone 18"]
    assert [line for _t, line in parse("B", ATOM, since)] == ["[B] Anthropic ships a new model"]


def test_headlines_newest_first_and_a_broken_feed_is_skipped() -> None:
    bodies = dict(zip(FEEDS.values(), [RSS, ATOM, b"<not xml"], strict=True))

    def get(url: str, **_kw: Any) -> httpx.Response:
        return httpx.Response(200, content=bodies[url], request=httpx.Request("GET", url))

    lines = headlines(get, now=lambda: NOW).splitlines()
    assert lines == ["- [TechCrunch] Anthropic ships a new model", "- [The Verge] Apple unveils iPhone 18"]


def test_no_feed_at_all_means_no_headlines() -> None:
    def get(url: str, **_kw: Any) -> httpx.Response:
        raise httpx.ConnectError("offline")

    assert headlines(get, now=lambda: NOW) == ""
