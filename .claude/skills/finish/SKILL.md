---
name: finish
description: Wrap up a finished change — gate, review, docs, then a clean local commit and a "how to check" block. Runs on its own when the work for a request is done; never asks permission and never pushes.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Agent, Skill
---
<!-- scaffold: solo/.claude/skills/finish/SKILL.md — project-owned after setup -->

Run this **on your own** when the work for the owner's request is complete. Do not wait to be told,
do not ask "shall I commit?". Every finished change ends up gated and committed with no ceremony —
and nothing leaves the machine without the owner's word.

1. **`/gate`** — green for every target the change touched (`--changed` at least). Reds are fixed
   first. Bugs do not enter history.

2. **Review, sized to the change.** Trivial edit → a careful self-check. Substantial change → the
   **`code-reviewer`** agent; address blockers and majors.
   <!-- project-specific: area → specialised agent (schema → db-guardian, ...) -->

3. **Docs, if behaviour changed** → `/sync-docs`. Skip it only when the change touches no documented
   fact.

4. **Regenerate what is generated**, if its source changed.
   <!-- project-specific: e.g. `pnpm gen:api` after schemas/ -->

5. **The "how to check" block** — two to four concrete checks the owner can run: a `curl`, a query,
   a targeted test through the gate, a click path. Nothing command-verifiable → a few plain sentences
   about what changed and why. This block is the actual deliverable; the commit is bookkeeping.

6. **Commit — never push.** One line, `type(scope): summary`. No `Co-Authored-By`, no mention of the
   assistant — the author is the human. Show the diff summary and the check block.

7. **Tell the owner it is committed** — and that `push` sends it to GitHub and `release` deploys it,
   whenever they want, not now.

> Stop here. `git push` and deploying happen only on the owner's word.
