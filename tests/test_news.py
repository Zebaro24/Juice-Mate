from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from juice_mate.core.news import Story, stories
from juice_mate.sources import news
from juice_mate.sources.news import FEEDS, fetch, numbered, parse

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Apple unveils   iPhone 18</title><link>https://www.theverge.com/iphone-18</link>
<pubDate>Thu, 22 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>Old story</title><pubDate>Mon, 19 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>No date</title></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Anthropic ships a new model</title><link rel="alternate" href="https://techcrunch.com/model"/>
<published>2026-10-22T10:00:00-04:00</published></entry>
</feed>"""


def test_parse_keeps_the_last_day_with_links_from_rss_and_atom() -> None:
    since = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    [apple] = parse("A", RSS, since)
    assert (apple.title, apple.url) == ("Apple unveils iPhone 18", "https://www.theverge.com/iphone-18")
    [model] = parse("B", ATOM, since)
    assert (model.title, model.url) == ("Anthropic ships a new model", "https://techcrunch.com/model")


def test_fetch_newest_first_and_a_broken_feed_is_skipped() -> None:
    bodies = dict(zip(FEEDS.values(), [RSS, ATOM, b"<not xml"], strict=True))

    def get(url: str, **_kw: Any) -> httpx.Response:
        return httpx.Response(200, content=bodies[url], request=httpx.Request("GET", url))

    found = fetch(get, now=lambda: NOW)
    assert numbered(found).splitlines() == [
        "[1] [TechCrunch] Anthropic ships a new model",
        "[2] [The Verge] Apple unveils iPhone 18",
    ]


def test_no_feed_at_all_means_no_headlines() -> None:
    def get(url: str, **_kw: Any) -> httpx.Response:
        raise httpx.ConnectError("offline")

    assert fetch(get, now=lambda: NOW) == []


def test_the_answer_points_back_at_its_articles() -> None:
    links = [("TechCrunch", "https://techcrunch.com/model"), ("The Verge", None)]
    answer = "🤖 A new model is out #1\n\n📱 Something else (#2)\n🎮 No number here\n🧪 A wrong one #9"
    assert stories(answer, links) == [
        Story("🤖 A new model is out", "https://techcrunch.com/model", "TechCrunch"),
        Story("📱 Something else", None, "The Verge"),
        Story("🎮 No number here"),
        Story("🧪 A wrong one"),
    ]


def test_told_stories_are_kept_newest_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    news.remember([Story("old", "https://techcrunch.com/a", "TechCrunch")], at=1.0)
    news.remember([Story("new", None, None)], at=2.0)
    assert [s.text for s in news.recent()] == ["new", "old"]
    assert news.recent()[1].url == "https://techcrunch.com/a"


def test_only_news_sites_open(monkeypatch: pytest.MonkeyPatch) -> None:
    from juice_mate import app

    opened: list[str] = []
    monkeypatch.setattr("os.startfile", opened.append, raising=False)
    monkeypatch.setattr("threading.Thread", lambda target, **_kw: type("T", (), {"start": lambda self: target()})())
    for url in (
        "https://www.theverge.com/a",
        "https://evil.example/a",
        "http://techcrunch.com/a",
        "https://techcrunch.com.evil.io/a",
    ):
        app.open_article(url)
    assert opened == ["https://www.theverge.com/a"]


def test_the_old_default_question_moves_to_the_new_one(tmp_path: Path) -> None:
    import json

    from juice_mate.settings import DEFAULT_PROMPT, OLD_DEFAULT_PROMPTS, Settings

    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"claude_prompt": next(iter(OLD_DEFAULT_PROMPTS))}), encoding="utf-8")
    assert Settings.load(path).claude_prompt == DEFAULT_PROMPT
    path.write_text(json.dumps({"claude_prompt": "my own"}), encoding="utf-8")
    assert Settings.load(path).claude_prompt == "my own"
