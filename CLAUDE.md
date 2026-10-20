<!--
scaffold: solo/CLAUDE.md — project-owned after setup.
This file is loaded into EVERY session in full, so it holds only what is always needed (≤ ~120 lines).
Everything else loads on demand:
  - rules for one part of the code — .claude/rules/*.md with `paths:`;
  - process — .claude/docs/ and the skills (/playbook, /finish, ...);
  - product depth — docs/; history — CHANGELOG.md / docs/status.md, never here.
HTML comments like this one are stripped before loading and cost no tokens.
-->

# Juice-Mate

Windows taskbar app: battery of Bluetooth/HID devices, Claude usage limits and system sensors, shown on
the taskbar itself in the system's style; self-updating installer

## Where to look

| Question                                    | Where                          |
| ------------------------------------------- | ------------------------------ |
| Which document describes this code file     | `docs/README.md`, Code column  |
| Process, gate, commits, a non-standard case | `/playbook` (`.claude/docs/`)  |
| Findings that are not tasks yet             | `_ideas/`                      |
| Stack, sources, update channel, layout      | `docs/architecture.md`         |
| What to build next                          | `docs/plan/README.md`, `/step` |

## How we work

No branches, no PRs, no board — work happens on `main`. **Everything is automatic; nothing leaves
the machine without the owner's word.**

- Finished a change → run **`/finish`** yourself: gate, review, docs, a **clean local commit**. Do not
  ask "shall I commit?".
- **`push`** → `/push` (gate → approval → `git push`). It runs CI; it is not a deploy.
- **`release`** / **`deploy`** → `/release` (strict gate → version → CHANGELOG → the owner's go → tag).
- Checks run **only** through `python scripts/gate.py`. Never a linter or test runner by hand.
  One test: `--only pytest -- tests/test_x.py`.
- **The author of every commit is the human.** No `Co-Authored-By`, no mention of the assistant —
  anywhere (`guard-git` refuses it). Format: one line, `type(scope): summary`.
- **Language:** everything written into the project is English. Speech to the owner is
  Russian. UI text is in the product's language, only where asked.
- **Noticed something off** (a bug in passing, a doc that lies, an idea) → ask the owner in one line:
  now, or a note. No answer → `/idea`. Never decide alone, never let it evaporate.
- Specialised work → agents: `explorer` (scout first), `code-reviewer`, `test-writer`, `docs-sync`.

## Structure

```
src/juice_mate/core/      pure logic: readings, smoothing, thresholds, icon state (no IO)
src/juice_mate/sources/   one file per data source: bluetooth, hator (HID), claude (usage)
src/juice_mate/panel/     the taskbar panel: Win32 window inside Shell_TrayWnd, drawing, menu
src/juice_mate/tray/      interim tray icons (go at step 03); later only the fallback icon and toasts
src/juice_mate/update/    Velopack wiring, autostart
tests/                    pytest; sources mocked, core covered fully
docs/                     architecture.md (the spec), plan/ (the steps)
scripts/      gate.py (the only checker), approve.py, release.py, start-claude.bat
.claude/      skills/, agents/, hooks/, rules/, docs/, project.json
_ideas/ _temp/ _secrets/   outside git
```

## Commands

```bash
python scripts/gate.py               # the only checker; --changed | --target <t> | --strict | --list
```

Python 3.13 + Poetry. Run the app without a console window: `scripts\run.bat` (pythonw);
print every reading once: `poetry run python -m juice_mate --dump`.
There is no server and no prod: "production" is the installed app on the owner's and a second PC.

## Rules for every part

- **Never refresh the Claude Code OAuth token** — read `~/.claude/.credentials.json` only. A refresh
  rotates the token and logs Claude Code out.
- **Nothing hard-coded to the owner's hardware**: every source discovers what is present; nothing found
  → no icon. The app also runs on a second, non-technical user's PC.
- **A source never crashes the app**: errors become a "data unavailable" reading.
- **No admin, no UAC, no blocking prompts** — install, autostart and updates are per-user.
- `core/` stays pure (enforced by `scripts/arch_lint.py`).
- **The UI is the taskbar panel, never tray icons** (owner's decision). It must look like part of
  Windows: system glyph font, taskbar text colour, no boxes.

- **Never weaken or unwire a guard** (`.claude/project.json`, `.claude/settings.json`) without the
  owner's word — they are editable so they can evolve, not so they can be switched off.
- **Secrets** live only in `.env` (outside git), `_secrets/` and CI secrets — never in
  `settings.json`, scripts or the conversation. A new variable → its name in `.env.example`.
- **SSH to production is an outward action**: ask before the first connection in a task.

## Talking to the owner

- **Show, don't tell**: real input → real output, before → after.
- **Explain with a scenario**: "A user opens Today — now they see…", not "added a field".
- **At a fork, two or three concrete options** side by side, each with an example.
- **Plain language**; explain a needed term once. Match the depth to what the owner knows.
