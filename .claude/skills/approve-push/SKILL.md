---
name: approve-push
description: Mint the approval that lets one git push through. Used inside /push after a green gate — rarely needed on its own.
user-invocable: true
allowed-tools: Bash
---
<!-- template-managed: solo/.claude/skills/approve-push/SKILL.md — edit in _Claude-Template, not here -->

```bash
python scripts/approve.py push
```

The marker is bound to the current HEAD of every repo here, is consumed by the first push and
expires after `approval.ttl_minutes`. That is the point: an approval earned by yesterday's green gate
must not be spendable on today's unchecked change.

**Only ever mint it over a green gate.** Minting first and checking later inverts the arrangement —
the marker is evidence that the checks passed, not a way around them.

Normally `/push` does this. Reach for it alone only when a push failed after the marker was consumed
(rejected, then rebased) and you have re-run the gate.

> Releasing uses a different marker and a different skill: `/release`.
