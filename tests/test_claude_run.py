import subprocess
from datetime import UTC, datetime
from typing import Any

from juice_mate.sources.claude_run import PING_EVERY, QUIET_PROMPT, ClaudeRun
from juice_mate.sources.news import Headline

HEADLINE = Headline("X", "Y", "https://techcrunch.com/y", datetime(2026, 10, 22, tzinfo=UTC))


class Runner:
    def __init__(self, returncode: int = 0, stdout: str = "Octopuses have three hearts.") -> None:
        self.returncode, self.stdout = returncode, stdout
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "")


def make(
    runner: Runner, prompt: str = "a fact", now: list[float] | None = None, exe: str | None = "claude"
) -> ClaudeRun:
    clock = now or [1000.0]
    return ClaudeRun(lambda: prompt, runner, exe=lambda: exe, clock=lambda: clock[0], background=False)


def test_runs_claude_code_on_haiku_without_tools_and_hands_over_the_answer_once() -> None:
    runner = Runner()
    run = make(runner)
    run.request("expired")
    args = runner.calls[0]
    assert args[:3] == ["claude", "-p", "a fact"]
    assert args[args.index("--model") + 1] == "haiku"
    assert args[args.index("--tools") + 1] == ""
    assert run.finished == 1
    reply = run.take_reply()
    assert reply is not None and reply.text == "Octopuses have three hearts." and not reply.news
    assert run.take_reply() is None


def test_at_most_one_run_per_period() -> None:
    runner, now = Runner(), [1000.0]
    run = make(runner, now=now)
    run.request("expired")
    run.request("expired")
    now[0] += PING_EVERY
    run.request("expired")
    assert len(runner.calls) == 2


def test_an_empty_prompt_renews_silently() -> None:
    runner = Runner(stdout="ok")
    run = make(runner, prompt="  ")
    run.request("idle window")
    assert runner.calls[0][2] == QUIET_PROMPT
    assert run.take_reply() is None


def test_a_failed_run_shows_nothing_and_still_counts_as_finished() -> None:
    run = make(Runner(returncode=1, stdout="error"))
    run.request("expired")
    assert run.take_reply() is None
    assert run.finished == 1


def test_no_claude_code_on_this_pc_means_no_run() -> None:
    runner = Runner()
    make(runner, exe=None).request("expired")
    assert runner.calls == []


def test_news_in_the_prompt_becomes_headlines() -> None:
    runner = Runner()
    run = ClaudeRun(lambda: "News:\n{news}", runner, exe=lambda: "claude", background=False, news=lambda: [HEADLINE])
    run.request("idle window")
    assert runner.calls[0][2] == "News:\n[1] [X] Y"


def test_no_headlines_renews_silently() -> None:
    runner = Runner()
    run = ClaudeRun(lambda: "News:\n{news}", runner, exe=lambda: "claude", background=False, news=lambda: [])
    run.request("idle window")
    assert runner.calls[0][2] == QUIET_PROMPT
    assert run.take_reply() is None


def test_asking_from_the_menu_skips_the_wait() -> None:
    runner = Runner()
    run = make(runner)
    run.request("idle window")
    run.request("asked from the menu", now_please=True)
    assert len(runner.calls) == 2


def test_a_news_prompt_asks_for_other_stories_than_last_time() -> None:
    runner, now = Runner(stdout="iPhone 18 is out"), [1000.0]
    run = ClaudeRun(
        lambda: "News:\n{news}",
        runner,
        exe=lambda: "claude",
        clock=lambda: now[0],
        background=False,
        news=lambda: [HEADLINE],
    )
    run.request("menu", now_please=True)
    run.request("menu", now_please=True)
    assert "Already told" not in runner.calls[0][2]
    assert runner.calls[1][2].endswith("Already told — pick other stories:\niPhone 18 is out")


def test_a_news_answer_knows_its_articles_and_the_topics_steer_it() -> None:
    runner = Runner(stdout="📱 Y happened #1")
    run = ClaudeRun(
        lambda: "News:\n{news}",
        runner,
        exe=lambda: "claude",
        background=False,
        news=lambda: [HEADLINE],
        topics=lambda: ["AI models and tools"],
    )
    run.request("menu", now_please=True)
    assert "Prefer stories about: AI models and tools." in runner.calls[0][2]
    reply = run.take_reply()
    assert reply is not None and reply.news
    assert [(s.text, s.url, s.source) for s in reply.stories] == [("📱 Y happened", "https://techcrunch.com/y", "X")]
