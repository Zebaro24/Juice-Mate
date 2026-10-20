---
owns: The order of work in the solo profile — the automatic cycle, and the two words that let work leave the machine.
not:  Commit format, gate, language, secrets (conventions.md) · when something blocks (faq.md)
---
<!-- scaffold: solo/.claude/docs/workflow.md — project-owned after setup -->

# Workflow (solo)

One repository, one owner, work on `main`. **By default everything is automatic**: the gate and the
commit happen on their own. The owner says two words by hand, and only they let work out.

```
request → build → /finish (gate · review · docs · commit) → … → "push" → "release"
                   automatic, local                           the owner's word
```

| Step          | Who starts it   | What it does                                                  |
| ------------- | --------------- | ------------------------------------------------------------- |
| `/finish`     | you, on your own | gate → review → docs → **local commit** → "how to check" block |
| `/push`       | owner: "push"   | gate → `approve.py push` → `git push` → CI. Not a deploy       |
| `/release`    | owner: "release" | strict gate → VERSION + CHANGELOG → the owner's go → tag push = deploy |
| `/prod`       | either          | read-only look at production                                  |
| `/idea`       | you             | a finding that is not the task → `_ideas/`                    |

## Why this split

- **Commits are free** — a local savepoint. Asking "shall I commit?" is noise.
- **Push and release are the two ways out of the machine**, so they are the two places the owner's
  word is required. `guard-git` holds that even when no skill was invoked.
- An approval is minted **only over a green gate**, and bound to the HEAD that was checked: a commit
  made afterwards makes it stale. One approval = one push.

## If no skill was invoked

Skills are conveniences; this flow is the contract. Finished something → gate and commit. Never
push, tag or deploy without the owner's word.
