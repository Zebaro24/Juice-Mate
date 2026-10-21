"""Claude usage limits — the same call Claude Code's `/usage` makes (docs/architecture.md §3.3).

**The token is only ever read, never refreshed.** Claude Code rotates its refresh token on use; a
refresh from here would log Claude Code out. An expired access token → "open Claude Code", and
Claude Code refreshes it the next time it runs.

The endpoint is internal and undocumented. Confirmed on 2026-10-21: `GET /api/oauth/usage` with the
`oauth-2025-04-20` beta header → 200 with `five_hour` / `seven_day` windows.
"""

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from juice_mate.core.reading import Kind, Reading
from juice_mate.core.usage import UsageFormatError, parse, summary

SOURCE = "claude"
URL = "https://api.anthropic.com/api/oauth/usage"
BETA = "oauth-2025-04-20"
MIN_INTERVAL = 60.0  # seconds between requests, however often the app polls
BACKOFF = 300.0  # after a 429
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
NAME = "Claude"


class Claude:
    def __init__(
        self,
        credentials: Path = CREDENTIALS,
        get: Callable[..., httpx.Response] = httpx.get,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._credentials = credentials
        self._get = get
        self._clock = clock
        self._last: list[Reading] = []
        self._next_request = 0.0

    def _reading(self, error: str) -> Reading:
        return Reading(SOURCE, SOURCE, NAME, None, kind=Kind.CLAUDE, error=error)

    def poll(self) -> list[Reading]:
        now = self._clock()
        if now < self._next_request:
            return self._last
        self._next_request = now + MIN_INTERVAL
        self._last = self._fetch(now)
        return self._last

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
            raise PermissionError("signed out — open Claude Code to sign in again")
        return token

    def _fetch(self, now: float) -> list[Reading]:
        try:
            token = self._token(now)
            if token is None:
                return []  # no Claude Code here: no item (the second PC)
            response = self._get(
                URL, headers={"Authorization": f"Bearer {token}", "anthropic-beta": BETA}, timeout=10.0
            )
            if response.status_code == 429:
                self._next_request = now + BACKOFF
                return [self._reading(error="rate limited, retrying in 5 min")]
            if response.status_code in (401, 403):
                return [self._reading(error="signed out — open Claude Code to sign in again")]
            response.raise_for_status()
            windows = parse(response.json())
        except PermissionError as e:
            return [self._reading(error=str(e))]
        except UsageFormatError as e:
            return [self._reading(error=f"the usage answer changed: {e}")]
        except (httpx.HTTPError, OSError, ValueError, KeyError) as e:
            return [self._reading(error=f"{type(e).__name__}: {e}"[:80])]
        now_utc = datetime.now(UTC)
        # One item per window: the 5-hour session and the week stop you independently.
        return [
            Reading(
                SOURCE,
                w.key,
                f"{NAME} {w.label}",
                round(w.used),
                kind=Kind.CLAUDE,
                tag=w.tag,
                note=summary([w], now_utc),
            )
            for w in windows
        ]
