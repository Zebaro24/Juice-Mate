---
name: sync-docs
description: Check that docs/ still matches the code after a change, and fix the page that drifted. Called by /finish or /submit-task when behaviour, schema, contract or process changed.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
---
<!-- scaffold: core/.claude/skills/sync-docs/SKILL.md — project-owned after setup -->

Drift is not untidiness: it means the code or the document is wrong, and until it is resolved
nobody knows which.

1. **Look at what changed:** `git diff` and `git diff --staged`.
2. **Find the page that owns each changed fact.** `docs/README.md` is the index; its **Code** column
   maps source paths to pages, so grep it for the path you touched.
3. **Delegate the editing to the `docs-sync` agent** for anything beyond a one-line fix.
4. **Decide the direction.** If the docs are the specification (docs-as-spec), the document is
   corrected first, then the code. Otherwise the document follows the code. Never leave a page
   describing something that no longer exists.
5. **Never resolve a real disagreement alone.** If it is unclear which side is right, that is a
   design decision — state both sides with locations and ask the owner.
6. **Report** which pages changed, one line each, and separately anything you found and did not
   resolve.

> Where a fact belongs: always-on rules → `CLAUDE.md` (thin — it costs context in every session);
> rules for one part of the code → `.claude/rules/*.md` with `paths:`; process → `.claude/docs/`;
> product depth → `docs/`; history → `docs/status.md` or the CHANGELOG, never `CLAUDE.md`.

<!-- project-specific: list the doc pages and what they own -->
