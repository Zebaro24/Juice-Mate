---
name: step
description: Take the next step of docs/plan/ — find the first unfinished step, ask only what is genuinely undecided, build it, check its criterion literally. Use at the start of a session, or whenever the answer to "what next" is needed.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, Agent, Skill
---
<!-- template-managed: addons/docs-as-spec/.claude/skills/step/SKILL.md — edit in _Claude-Template, not here -->

The project is built step by step from `docs/plan/`. Each step is one session: a clear input, a clear
output, and a "done when" you can check. Steps are ordered by dependency, not importance — skipping
ahead builds on something that is not there yet.

1. **Find the step.** `docs/plan/README.md` is the table of steps with their state (✅ done,
   ⚠️ next to it = written, not verified on the real target). Take the first row without ✅ and read
   only its file. All ticked → say so and offer the open items from `_ideas/` instead of inventing a
   step. The owner named a later step while an earlier one is open → say it out loud.
2. **Read what the step tells you to read.** Those sections are the specification — do not start
   from memory or from the code.
3. **Ask only what is genuinely undecided**, in plain language, **with a concrete example of each
   option**. Never ask what the documents already answer.
4. **Sketch the approach** in a few lines — files, order, where the risk is. Large step → show it and
   wait for a go. Small → say what you are about to do and start.
5. **Build it.** Scout with `explorer`, test with `test-writer`, keep heavy reading out of the main
   session.
6. **Check "done when" literally.** It is a command with an expected result, not a feeling. Run it,
   show the output.
7. **`/finish`**, then tick the step (✅ in its heading and in the table, `· ⚠️ …` for anything not
   verified on the real target), add a paragraph to `docs/status.md`, and say which step is next and
   what it needs from the owner.

The code and the docs diverge → **the document is corrected first.** Never grow `CLAUDE.md` with
history.
