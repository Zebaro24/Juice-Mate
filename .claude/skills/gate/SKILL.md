---
name: gate
description: Run the quality gate and relay its pass/fail table. Runs on its own before any commit, and piecemeal while building. The only way checks are ever run here.
user-invocable: true
allowed-tools: Bash, Read
---
<!-- template-managed: core/.claude/skills/gate/SKILL.md — edit in _Claude-Template, not here -->

One checker, one command: `python scripts/gate.py`. Never call a linter, type checker or test
runner by hand — a green that the gate did not produce is not the green CI produces.

The checks are declared in `.claude/project.json` → `gate.targets`. `python scripts/gate.py --list`
shows them.

1. **Pick the scope from what the change touched**, not from habit:

   | When                                   | Run                                                  |
   | -------------------------------------- | ---------------------------------------------------- |
   | while building                         | `--changed`, or `--target <t> --lint`, or `--only <check> -- <args>` |
   | the change is finished (`/finish`, `/submit-task`) | `--changed` at least; the targets you touched in full |
   | before a release or a submit           | `--strict` — adds the checks marked `strict`          |
   | touched `scripts/` or `.claude/hooks/` | `--target hooks` — no CI ever sees the guards         |

   `--changed` maps every touched path to its target; a path no target owns runs everything, so it
   cannot lie. `--jobs 1` runs one check at a time when you need to see who actually broke.

2. **One test, one check:** `--only pytest -- tests/test_x.py::test_y`. This replaces a manual
   `pytest`, it does not sit next to it.

3. **Relay the table as it printed.** Never summarise a red as "almost green".

4. **Fix the reds, then run again.** A failing check is the answer, not an obstacle. Loosening a
   test or skipping a rule to get green turns a caught bug into a shipped one — if a rule is truly
   wrong, that is a conversation with the owner, not an edit.

A target whose directory does not exist yet prints `— no directory` and fails nothing. A check
whose tool is not installed prints `MISSING` and does fail: an absent check is not a passed one.
