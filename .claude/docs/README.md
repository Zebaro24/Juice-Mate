---
owns: Which playbook page answers which question — the router /playbook reads.
not:  The answers themselves (the pages below) · the product (docs/README.md)
---
<!-- scaffold: core/.claude/docs/README.md — project-owned after setup -->

# Juice-Mate playbook — how to work here

Lazy on purpose: `CLAUDE.md` is loaded into every session and holds the thin spine; this folder
holds the depth, the edge cases and the reasons. Read one page — the one that answers the question.

| Need                                                              | Page                             |
| ----------------------------------------------------------------- | -------------------------------- |
| What next · the cycle · what needs the owner's word               | [workflow.md](workflow.md)       |
| Commits · the gate · versions · language · secrets · writing docs | [conventions.md](conventions.md) |
| A guard blocked something · CI is red · how to undo               | [faq.md](faq.md)                 |

## The harness

- **Skills** (`.claude/skills/`) — `workflow.md` says which run on their own and which only on the
  owner's word.
- **Agents** (`.claude/agents/`) — `explorer` · `code-reviewer` · `test-writer` · `docs-sync`
  <!-- project-specific: plus the specialised ones -->
- **Hooks** (`.claude/hooks/`) — `guard-git` · `guard-secrets` · `notify` (+ `guard-branch` in team).
  Behaviour is configured in `.claude/project.json`; the code comes from the template unchanged.
- **Scripts** (`scripts/`) — `gate.py` (the only checker) · `approve.py` · `check_hooks.py` ·
  `start-claude.bat` <!-- project-specific: + dev / prod helpers -->

## Where things live

- What we build → `docs/`, indexed by `docs/README.md`.
- How we work → this folder.
- Findings that are not tasks yet → `_ideas/` (outside git).
- Scratch → `_temp/` (outside git, disposable). Credentials → `_secrets/` (outside git, never read).
