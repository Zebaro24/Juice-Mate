"""Claude usage limits — the same call Claude Code's `/usage` makes (docs/architecture.md §3.3).

**The token is only ever read, never refreshed.** Claude Code rotates its refresh token on use; a
refresh from here would log Claude Code out. An expired access token → Claude Code is run once,
invisibly (`claude_run.py`), and renews it itself; until then the item says "open Claude Code".

The endpoint is internal and undocumented. Confirmed on 2026-10-21: `GET /api/oauth/usage` with the
`oauth-2025-04-20` beta header → 200 with `five_hour` / `seven_day` windows. Asked once a minute it
started answering 429 after about an hour, so it is asked every three minutes and backs off on 429.
"""

import json
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from juice_mate.core.reading import Kind, Reading
from juice_mate.core.usage import UsageFormatError, Window, limit_at, parse, summary
from juice_mate.sources.claude_run import ClaudeRun

SOURCE = "claude"
URL = "https://api.anthropic.com/api/oauth/usage"
BETA = "oauth-2025-04-20"
INTERVAL = 180.0  # seconds between requests, however often the app polls
BACKOFF_FIRST, BACKOFF_MAX = 300.0, 1800.0  # after a 429: 5 min, doubling up to 30 min
NEW_WINDOW_DROP = 5.0  # % used falling by this much is a reset, not rounding
STALE_AFTER = 3600.0  # the last good numbers stay on the panel, marked, for up to an hour of failures
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
NAME = "Claude"
SIGNED_OUT = "signed out — open Claude Code to sign in again"
EXPIRED = "token expired — opening Claude Code renews it"


class _ExpiredError(PermissionError):
    """The access token's time is up. Claude Code renews it on its next run, so the file is read
    again on every poll until it does — no request is made with an expired token."""


class Claude:
    """Two readings, one per window. A passing failure (429, network) keeps the last good numbers on
    the panel with "as of HH:MM" in the tooltip — a "!" for a rate limit would hide what is still true.
    """

    def __init__(
        self,
        credentials: Path = CREDENTIALS,
        get: Callable[..., httpx.Response] = httpx.get,
        clock: Callable[[], float] = time.time,
        run: ClaudeRun | None = None,
        keep_window: Callable[[], bool] = lambda: False,
    ) -> None:
        """`run` renews an expired token through Claude Code; with `keep_window` on it also starts the
        5-hour window whenever it is not running."""
        self._credentials = credentials
        self._run = run
        self._keep_window = keep_window
        self._runs_seen = 0
        self._get = get
        self._clock = clock
        self._next_request = 0.0
        self._backoff = BACKOFF_FIRST
        self._windows: list[Window] = []
        self._good_at: float | None = None
        self._failure: str | None = None
        self._absent = False  # no Claude Code login on this PC
        self._history: dict[str, list[tuple[datetime, float]]] = {}  # per window: (time, % used)
        self._history_resets: dict[str, datetime | None] = {}  # the reset time the history belongs to

    def poll(self) -> list[Reading]:
        now = self._clock()
        if self._run is not None and self._run.finished != self._runs_seen:
            self._runs_seen = self._run.finished
            self._next_request = now  # Claude Code just ran: a fresh token, maybe a new window
        if now >= self._next_request:
            self._next_request = now + INTERVAL
            self._fetch(now)
        return self._readings(now)

    def _readings(self, now: float) -> list[Reading]:
        if self._absent:
            return []
        fresh = self._good_at is not None and now - self._good_at < STALE_AFTER
        if not self._windows or (self._failure and not fresh):
            return [Reading(SOURCE, SOURCE, NAME, None, kind=Kind.CLAUDE, error=self._failure or "no data yet")]
        suffix = ""
        if self._failure and self._good_at is not None:
            suffix = f" · as of {datetime.fromtimestamp(self._good_at):%H:%M} ({self._failure})"
        now_utc = datetime.fromtimestamp(now, UTC)
        readings = []
        # One item per window: the 5-hour session and the week stop you independently.
        for w in self._windows:
            forecast = limit_at(self._history.get(w.key, []), w, now_utc)
            eta = forecast.astimezone() if forecast else None  # local time, for the tooltip and the toast
            pace = f" · at this pace: limit at {eta:%H:%M}" if eta else ""
            readings.append(
                Reading(
                    SOURCE,
                    w.key,
                    f"{NAME} {w.label}",
                    math.floor(w.used),  # as Claude Code's /usage: 2.6% used is "2%"
                    kind=Kind.CLAUDE,
                    tag=w.tag,
                    note=summary([w], now_utc) + pace + suffix,
                    limit_at=eta,
                )
            )
        return readings

    def _remember(self, now: float) -> None:
        """Keep each window's recent samples. A new window — its reset time moved, or usage fell by more
        than rounding — starts afresh; a small dip is not a reset and keeps the hour of history."""
        moment = datetime.fromtimestamp(now, UTC)
        for w in self._windows:
            samples = self._history.setdefault(w.key, [])
            moved = self._history_resets.get(w.key, w.resets_at) != w.resets_at
            if samples and (moved or samples[-1][1] - w.used >= NEW_WINDOW_DROP):
                samples.clear()
            self._history_resets[w.key] = w.resets_at
            samples.append((moment, w.used))
            del samples[:-40]  # an hour at one sample per three minutes is 20; keep a margin

    def _token(self, now: float) -> str | None:
        """The access token, or None if there is no Claude Code login on this PC at all."""
        try:
            oauth = json.loads(self._credentials.read_text(encoding="utf-8"))["claudeAiOauth"]
        except FileNotFoundError:
            return None
        token = oauth.get("accessToken")
        if not isinstance(token, str) or not token:
            return None
        expires = oauth.get("expiresAt")
        if isinstance(expires, int | float) and expires / 1000 <= now:
            raise _ExpiredError(EXPIRED)
        return token

    def _fetch(self, now: float) -> None:
        try:
            token = self._token(now)
            self._absent = token is None
            if token is None:
                return
            response = self._get(
                URL, headers={"Authorization": f"Bearer {token}", "anthropic-beta": BETA}, timeout=10.0
            )
            if response.status_code == 429:
                self._next_request = now + self._backoff
                self._failure = f"rate limited, next try in {self._backoff / 60:.0f} min"
                self._backoff = min(self._backoff * 2, BACKOFF_MAX)
                return
            if response.status_code in (401, 403):
                raise PermissionError(SIGNED_OUT)
            response.raise_for_status()
            self._windows = parse(response.json())
        except PermissionError as e:
            if isinstance(e, _ExpiredError):
                self._next_request = now  # a renewed token shows on the next poll, not three minutes later
                if self._run is not None:
                    self._run.request("the token has expired")
            self._windows, self._failure = [], str(e)  # a signed-out account's old numbers mean nothing
            return
        except UsageFormatError as e:
            self._failure = f"the usage answer changed: {e}"
            return
        except (httpx.HTTPError, OSError, ValueError, KeyError) as e:
            self._failure = f"{type(e).__name__}: {e}"[:80]
            return
        self._good_at, self._failure, self._backoff = now, None, BACKOFF_FIRST
        self._remember(now)
        if self._run is not None and self._keep_window() and self._idle(now):
            self._run.request("the 5-hour window is not running")

    def _idle(self, now: float) -> bool:
        """No 5-hour window is counting: none in the answer, no reset time, or one already past."""
        session = next((w for w in self._windows if w.key == "five_hour"), None)
        return session is None or session.resets_at is None or session.resets_at.timestamp() <= now
