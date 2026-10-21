import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from juice_mate.core.display import Tone, item
from juice_mate.core.reading import Kind, Level, Reading, level
from juice_mate.core.usage import UsageFormatError, Window, parse, summary, until
from juice_mate.sources.claude import BETA, URL, Claude

# Trimmed from the real answer of 2026-10-21; the code-named keys are what must be ignored.
ANSWER = {
    "five_hour": {"utilization": 10.0, "resets_at": "2026-10-21T16:19:59.792890+00:00", "limit_dollars": None},
    "seven_day": {"utilization": 54.0, "resets_at": "2026-10-26T14:59:59.792909+00:00"},
    "seven_day_opus": None,
    "iguana_necktie": {"utilization": 100.0, "resets_at": "2026-11-05T07:59:00+00:00"},
    "extra_usage": {"is_enabled": False},
}
NOW = datetime(2026, 10, 21, 14, 14, 59, tzinfo=UTC)


def test_parse_reads_only_the_two_windows() -> None:
    windows = parse(ANSWER)
    assert [(w.key, w.label, w.tag, w.used) for w in windows] == [
        ("five_hour", "5 h", "5h", 10.0),
        ("seven_day", "week", "7d", 54.0),
    ]


@pytest.mark.parametrize(
    "answer",
    [[], {}, {"five_hour": {"utilization": "ten"}}, {"seven_day": {"utilization": 5, "resets_at": "soon"}}],
)
def test_a_changed_answer_is_a_format_error(answer: Any) -> None:
    with pytest.raises(UsageFormatError):
        parse(answer)


def test_summary_and_until() -> None:
    assert summary(parse(ANSWER), NOW) == "5 h 10% (resets in 2 h 05 min) · week 54% (resets in 5 d 0 h)"
    assert until(datetime(2026, 10, 21, 14, 50, tzinfo=UTC), NOW) == "35 min"
    assert until(datetime(2026, 10, 21, 13, 0, tzinfo=UTC), NOW) == "0 min"
    assert summary([Window("five_hour", "5 h", "5h", 3.0, None)], NOW) == "5 h 3%"


def test_high_usage_is_the_critical_end() -> None:
    def claude(percent: int) -> Reading:
        return Reading("claude", "claude", "Claude", percent, kind=Kind.CLAUDE)

    assert level(claude(79)) is Level.OK
    assert level(claude(80)) is Level.LOW
    assert item(claude(5), NOW).tone is Tone.NORMAL  # a battery at 5 % would be red
    assert item(claude(91), NOW).tone is Tone.CRITICAL


class Http:
    def __init__(self, status: int = 200, body: Any = ANSWER, error: Exception | None = None) -> None:
        self.status, self.body, self.error = status, body, error
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, **kw: Any) -> httpx.Response:
        self.calls.append({"url": url, **kw})
        if self.error:
            raise self.error
        return httpx.Response(self.status, json=self.body, request=httpx.Request("GET", url))


def credentials(tmp_path: Path, expires_ms: float = 4e12, token: str = "tok") -> Path:
    path = tmp_path / ".credentials.json"
    path.write_text(json.dumps({"claudeAiOauth": {"accessToken": token, "expiresAt": expires_ms, "refreshToken": "r"}}))
    return path


def test_reads_usage_with_the_token_and_never_touches_the_file(tmp_path: Path) -> None:
    path = credentials(tmp_path)
    before = path.read_bytes()
    http = Http()
    session, week = Claude(path, http, clock=lambda: 1.8e9).poll()
    assert (session.device_id, session.tag, session.percent) == ("five_hour", "5h", 10)
    assert (week.device_id, week.tag, week.percent) == ("seven_day", "7d", 54)
    assert week.note is not None
    assert week.note.startswith("week 54%")
    assert http.calls[0]["url"] == URL
    assert http.calls[0]["headers"] == {"Authorization": "Bearer tok", "anthropic-beta": BETA}
    assert path.read_bytes() == before, "the credentials file must never be written"


def test_no_login_on_this_pc_means_no_item(tmp_path: Path) -> None:
    assert Claude(tmp_path / "missing.json", Http()).poll() == []


def test_an_expired_token_is_not_refreshed(tmp_path: Path) -> None:
    http = Http()
    [reading] = Claude(credentials(tmp_path, expires_ms=1000), http, clock=lambda: 1.8e9).poll()
    assert reading.error is not None
    assert "open Claude Code" in reading.error
    assert http.calls == []


@pytest.mark.parametrize(
    ("http", "fragment"),
    [
        (Http(status=401), "open Claude Code"),
        (Http(status=500), "HTTPStatusError"),
        (Http(body={"weird": 1}), "usage answer changed"),
        (Http(error=httpx.ConnectError("offline")), "ConnectError"),
    ],
)
def test_failures_become_error_readings(tmp_path: Path, http: Http, fragment: str) -> None:
    [reading] = Claude(credentials(tmp_path), http, clock=lambda: 1.8e9).poll()
    assert reading.error is not None
    assert fragment in reading.error


def test_at_most_one_request_a_minute_and_a_pause_after_429(tmp_path: Path) -> None:
    now = [1.8e9]
    http = Http()
    source = Claude(credentials(tmp_path), http, clock=lambda: now[0])
    source.poll()
    now[0] += 30
    source.poll()
    assert len(http.calls) == 1
    now[0] += 31
    http.status = 429
    [limited] = source.poll()
    assert limited.error is not None
    now[0] += 120
    source.poll()
    assert len(http.calls) == 2, "no request during the back-off"
