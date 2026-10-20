---
owns: What to do when something stopped you — a guard refusal, a red CI, an approval that will not take, an undo.
not:  The normal order of steps (workflow.md) · the rules themselves (conventions.md)
---
<!-- scaffold: core/.claude/docs/faq.md — project-owned after setup -->

# FAQ

## A guard refused a command

Read the reason — it names the rule. Then:

| Refusal                               | Meaning → what to do                                                      |
| ------------------------------------- | ------------------------------------------------------------------------- |
| `git push ... needs a fresh approval` | Go through the skill (`/push`, or the owner's `/approve`), never around it |
| `... approval: stale`                 | A commit was made after approving. Re-run the gate, approve again         |
| `... approval: expired`               | The TTL passed (`approval.ttl_minutes`). Approve again                    |
| `Dangerous git blocked`               | Force-push, `--no-verify`, `reset --hard origin`, `clean -f`. If truly needed, the owner types it by hand |
| `must not carry Co-Authored-By`       | Rewrite the message without the attribution                               |
| `prints a secret file`                | Read `.env.example` for names; ask the owner for a value                  |
| `Editing on 'main'` (team)            | Take the task first — `/start-task` cuts the branch                       |

**A refusal cancels the whole command**, including every part chained with `&&` / `;`. A
`git commit` in front of a refused push was **not** created — do not `--amend` afterwards.

A false alarm (an ordinary command refused)? Do not work around it. Tell the owner and write
`/idea tooling-...` with the exact command: the fix goes into the template's
`scripts/check_hooks.py` as a case first, then into the guard.

## CI is red after a push

Read the failing job (`gh run view --log-failed`). Red CI with a green local gate means the gate and
CI diverged — a bug in the gate config, worth fixing so it cannot happen twice.

## Undo

- Unpushed commit → `git commit --amend` or `git reset --soft HEAD~1`. Free.
- Pushed commit → a new commit that reverts it (`git revert`). Never a force-push.
- A bad release → roll forward: fix, bump patch, release again.

<!-- project-specific: prod is down, the local stack will not start, ... -->
