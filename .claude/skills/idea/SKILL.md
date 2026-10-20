---
name: idea
description: Write a finding into _ideas/ — something noticed in passing that is not the current task (a rough edge, a doc that lies, a bug walked past, an idea). Use the moment you stumble over it, not later.
user-invocable: true
allowed-tools: Read, Write, Edit, Glob
---
<!-- template-managed: core/.claude/skills/idea/SKILL.md — edit in _Claude-Template, not here -->

Everything noticed that is **not the task in front of you** goes here. `_ideas/` is the owner's desk:
outside git on purpose, a working surface, not documentation.

## The rule

> **Never decide alone, and never let it evaporate.** Ask the owner in one line: now, or a note?
> "Now" → it becomes work. "Note", or you could not ask yet → write it here.

Write it **the moment you stumble**: an hour later you remember the conclusion, not the place you got
stuck — and the place is what makes it checkable.

## How

1. Name it `<area>-<short-slug>.md`:

   | Prefix     | About                                                               |
   | ---------- | ------------------------------------------------------------------- |
   | `tooling-` | `scripts/`, the gate, hooks — something missing, awkward, routed around |
   | `docs-`    | a document lies, contradicts another, or cannot be found            |
   | `product-` | behaviour for the user: a bug, a gap, a feature idea                |
   | `process-` | how we work: the cycle, conventions, review, release                |
   | `data-`    | schema, migrations, queries — the most expensive things to fix later |

2. Copy `_ideas/_TEMPLATE.md` and fill it in. English, like every file in the project.
3. Never skip these two sections:
   - **How it surfaced** — what you ran, what you expected, what you got, with the command and
     `file:line`. "Docs are stale" cannot be checked; "`docs/api.md` §7 promises `PATCH /reminders/{id}`,
     the router has none" can.
   - **What must be decided first** — why this is a note and not work: an open question, a decision
     not taken, something to measure.
4. Tell the owner in one line that you wrote it and what it is about. A note nobody was told about
   is a note nobody reads.

## When it closes

It became work, got fixed in passing, or was declined → delete the file and add one line to
`_ideas/CLOSED.md`: date, what it was, how it ended. `_ideas/` lists **open** questions only and
must stay readable in one sitting.
