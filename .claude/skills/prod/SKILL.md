---
name: prod
description: Look at production — health, containers, logs, data. Read-only. Use after a deploy, or when something looks wrong in production.
user-invocable: true
allowed-tools: Bash, Read
---
<!-- scaffold: solo/.claude/skills/prod/SKILL.md — project-owned after setup -->

<!-- project-specific: host, containers, compose path, public URL. Facts live in docs/deploy. -->
Production: `<user@host>`. Use the helper (`scripts\prod.bat`) instead of long `ssh` lines.

## Start with the cheap check

```bat
scripts\prod.bat health
```

Public HTTP only — no server login, no permission needed, and it answers "is it alive" most of the
time.

## Then, if needed

```bat
scripts\prod.bat ps          :: containers and uptime
scripts\prod.bat logs <c> 24h
```

**SSH is an outward action — ask before the first connection in a task.** `health` is exempt.

## Reading the answer

- **Container logs start at the last restart.** A redeploy erases earlier lines; history lives in the
  database or a log store, not in `docker logs`.
- **Green CD with a stale uptime** means the container was not recreated. Compare the running image
  with the one the deploy built.

## What you never do here

No editing files on the server, no restarts, no migrations, nothing but `SELECT` on the database —
unless the owner asked for that specific action in this conversation. Production changes through a
release. A hand-fix on the server is invisible to git and disappears with the next deploy, taking
the reason with it.
