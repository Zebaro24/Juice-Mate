---
name: push
description: Send committed work to GitHub — gate, approval bound to HEAD, push. Triggered by the owner saying "push"; never on your own initiative.
user-invocable: true
allowed-tools: Bash, Read
---
<!-- template-managed: solo/.claude/skills/push/SKILL.md — edit in _Claude-Template, not here -->

Pushing is the first of two ways work leaves this machine. It runs CI. It does **not** deploy —
nothing reaches production without a release tag.

Trigger: the owner says **push** (or `/push`). Never push because it seemed like a good moment.

1. **Show what goes out:** `git log origin/<main>..HEAD --oneline` and `git status`. No remote branch
   yet → say this is the first push.
2. **`/gate`** for everything the outgoing commits touched. Red → stop and report. The approval is
   only ever minted over a green gate; that is its entire value.
3. **Approve:** `python scripts/approve.py push`. Bound to the current HEAD, one push, expires after
   `approval.ttl_minutes`. `guard-git` refuses a push without it, including one typed by hand.
4. **Push:** `git push origin <main>` (`-u` the first time).
5. **Report** what went out and that CI is running. Offer `gh run list --limit 3`; do not poll it.

## When it refuses

- **needs a fresh approval / stale** — step 3 was skipped, a commit came after it, or it expired.
  Re-run the gate and approve again; never work around the guard.
- **Rejected, remote is ahead** — `git pull --rebase`, gate again, approve again, push. Never
  `--force`: the guard refuses it, and on a single-author repo it destroys history for nothing.

> Deploying is a different skill with a different approval: `/release`.
