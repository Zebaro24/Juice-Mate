---
name: playbook
description: Open the project playbook — how the workflow, gate, commits, release and guards work here. Use when a step is unclear, a situation is non-standard, or a guard blocked something.
user-invocable: true
allowed-tools: Read
---
<!-- template-managed: core/.claude/skills/playbook/SKILL.md — edit in _Claude-Template, not here -->

The deep "how to work here" lives in `.claude/docs/`. It is lazy on purpose: `CLAUDE.md` is loaded
into every session and stays thin; this is the depth. Read **only** the page the question needs.

1. **Read `.claude/docs/README.md` first.** It is the router — one row per page, saying when to open
   it. The mapping lives there and nowhere else; do not restate it here.
2. Open the one page it points at. Answer concisely and cite the page and section.
3. A question about the **product** (what we build, how the schema works) is answered by `docs/`,
   mapped by `docs/README.md` — never from memory.
4. **Nothing covers it?** Say so plainly. That is a gap: propose the one-line entry it deserves and
   the page that owns it, or write it down with `/idea`. A question that had no answer once will be
   asked again.
