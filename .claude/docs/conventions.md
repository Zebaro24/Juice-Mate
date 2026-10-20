---
owns: The rules every change follows — commits, the gate, versions, language, secrets, how docs are written.
not:  The order of steps (workflow.md) · what to do when something blocks (faq.md)
---
<!-- scaffold: core/.claude/docs/conventions.md — project-owned after setup -->

# Conventions

## Commits

- One line, lower-case, imperative: `type(scope): summary`. Types: `feat` `fix` `refactor` `perf`
  `test` `docs` `chore`. Scope = the part of the code (`api`, `web`, `gate`, ...).
- **The author is the human.** No `Co-Authored-By`, no mention of the assistant or its vendor — in
  commits, tags, PRs, issues. `guard-git` refuses it.
- Commits are local savepoints and free. What leaves the machine (push, tag) needs an approval.

## The gate

- `python scripts/gate.py` is the only checker — the same commands CI runs. Never run a linter or a
  test runner by hand; `--only <check> -- <args>` is how one test is run.
- Checks are declared in `.claude/project.json` → `gate.targets`. Add a check there, never a second
  way of running it. Keep `settings.json` from allowing the raw tools (`Bash(pytest:*)` ...): an
  allow-list entry invites exactly the by-hand run this rule forbids.
- The guards are covered by `--target hooks`. Touched `.claude/hooks/` or `scripts/`? Run it.

## The guards' own config

- `.claude/project.json` and `.claude/settings.json` are editable — guards evolve and need finishing
  work. But **never weaken a guard (protected branches, attribution, approvals, deny rules) or
  unwire a hook without the owner's word**, and say so in the report when you touch them.
- The guards are a tripwire against the wrong reflex, not a security boundary. Do not route around
  one; if it is wrong, raise it.

## Versions

- One source: `VERSION` at the root. Everything else reads it. SemVer: fix → patch, feature → minor,
  breaking → major.
- A release is a tag `vX.Y.Z`; pushing it is a deploy.

## Language

- **Everything written into the project is English**: code, comments, identifiers, commits, branch
  names, issues, PRs, `docs/`, `CLAUDE.md`, `.claude/`, `_ideas/`.
- **Speech to the owner is Russian** — answers, reports, the text a skill prints to them,
  notifications.
- **User-facing UI text** is in the language the product needs (`.claude/project.json` →
  `project.ui_language`) — only when the owner asks for it, and only there.

## Secrets

- Values live only in `.env` files (outside git), `_secrets/` (outside git) and the CI secret store.
  Never in `settings.json`, `settings.local.json`, scripts or the conversation.
- `.env.example` carries the names. Added a variable → add its name there.
- The agent never prints a secret: `settings.json` denies reading them, `guard-secrets` refuses the
  shell commands that would print them.

## Writing docs

- One page owns one subject and says so in its header (`owns:` / `not:` / `code:`).
- A big document is a folder: one section per file, the folder's `README.md` is its index. Open the
  index and one file, never the whole folder.
- `CLAUDE.md` stays thin (target ≤ 120 lines): only what every session needs. A rule for one part of
  the code goes into `.claude/rules/<part>.md` with `paths:` — it loads only when those files are
  touched. HTML comments in `CLAUDE.md` are stripped before loading and cost nothing.
