"""Running Claude Code itself, invisibly, so its login and the 5-hour window keep going (§3.3).

Juice-Mate never refreshes the token (that would log Claude Code out). Claude Code does refresh it
whenever it runs — so when the token has expired, or the 5-hour window is not running, Juice-Mate runs
`claude -p <prompt>` once on Haiku: Claude Code renews its own token, the request opens a new window,
and the answer to the owner's prompt comes back as a notification.

One run costs a fraction of a percent of the 5-hour window. At most one run per PING_EVERY; a run that
fails only means the item keeps its "expired" note until Claude Code is opened.
"""

import logging
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from juice_mate import folders
from juice_mate.sources.news import headlines

log = logging.getLogger(__name__)

PING_EVERY = 1800.0  # seconds between runs, however often one is asked for
TIMEOUT = 120.0
MODEL = "haiku"
QUIET_PROMPT = "Reply with just: ok"  # an empty prompt in the settings: renew, no notification
NEWS = "{news}"  # in the prompt: replaced by the last day's tech headlines
TOLD_KEPT = 3  # answers remembered (two stories each) so a news prompt does not repeat itself
_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: no console flashes up from a windowed app


def find_claude() -> str | None:
    """The native claude.exe only. Its installer puts it in ~/.local/bin (autostart may not see an
    updated PATH). An npm install's claude.cmd is skipped: on a timeout only cmd.exe would be killed,
    node would keep the pipes open, and the run would never end."""
    default = Path.home() / ".local" / "bin" / "claude.exe"
    if default.is_file():
        return str(default)
    found = shutil.which("claude.exe")
    return found if found and found.lower().endswith(".exe") else None


def command(exe: str, prompt: str) -> list[str]:
    # No tools, no MCP servers, no session file, no user or project settings (their hooks would run):
    # only the request itself.
    return [
        exe,
        "-p",
        prompt,
        "--model",
        MODEL,
        "--tools",
        "",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--setting-sources",
        "local",
    ]


class ClaudeRun:
    def __init__(
        self,
        prompt: Callable[[], str],
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        exe: Callable[[], str | None] = find_claude,
        clock: Callable[[], float] = time.time,
        background: bool = True,
        news: Callable[[], str] = headlines,
    ) -> None:
        """`prompt` is asked at each run, so a change in the settings takes effect without a restart.
        A `{news}` in it becomes the last day's tech headlines (news.py)."""
        self._prompt = prompt
        self._news = news
        self._run = run
        self._exe = exe
        self._clock = clock
        self._background = background
        self._next = 0.0
        self._busy = False
        self._reply: str | None = None
        self._told: list[str] = []  # the last answers to a `{news}` prompt, so the next one differs
        self.finished = 0  # counts finished runs: a new value means "ask for the usage again now"

    def request(self, reason: str, now_please: bool = False) -> None:
        """`now_please` (the owner's menu item) skips the wait between runs, not a run in progress."""
        now = self._clock()
        if self._busy or (now < self._next and not now_please):
            return
        exe = self._exe()
        if exe is None:
            return
        self._next, self._busy = now + PING_EVERY, True
        log.info("running Claude Code: %s", reason)
        if self._background:
            threading.Thread(target=self._go, args=(exe,), name="claude-run", daemon=True).start()
        else:
            self._go(exe)

    def take_reply(self) -> str | None:
        """The answer of the last run, once; None when there is none to show."""
        reply, self._reply = self._reply, None
        return reply

    def _go(self, exe: str) -> None:
        folder = folders.data()
        try:
            prompt = self._prompt().strip()
            if NEWS in prompt:
                news = self._news()
                prompt = prompt.replace(NEWS, news) if news else ""  # no headlines: renew silently
                if prompt and self._told:
                    # The day's headlines barely change, so the same two stories would win every time.
                    prompt += "\n\nAlready told — pick other stories:\n" + "\n".join(self._told)
            folder.mkdir(parents=True, exist_ok=True)
            done = self._run(
                command(exe, prompt or QUIET_PROMPT),
                cwd=folder,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT,
                creationflags=_NO_WINDOW,
            )
            if done.returncode != 0:
                log.warning("Claude Code run failed (%s): %s", done.returncode, (done.stderr or done.stdout)[:300])
            elif prompt and done.stdout.strip():
                self._reply = done.stdout.strip()
                self._told = (self._told + [self._reply])[-TOLD_KEPT:]
        except Exception:  # whatever happens, the run must end and free the next one
            log.exception("could not run Claude Code")
        finally:
            self._busy = False
            self.finished += 1
