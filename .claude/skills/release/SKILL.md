---
name: release
description: Release to production — strict gate, version, CHANGELOG, tag, the owner's go, push. Triggered by the owner saying "release" or "deploy". The model never tags or deploys on its own.
user-invocable: true
allowed-tools: Bash, Read, Edit, Write
---
<!-- scaffold: solo/.claude/skills/release/SKILL.md — project-owned after setup -->

Pushing a `vX.Y.Z` tag is what reaches production. So this is slow on purpose and ends with an
explicit go from the owner.

1. **Agree the scope:** `git log <last tag>..HEAD --oneline`, and the bump — `patch` (fixes), `minor`
   (features), `major` (breaking). Say which you would pick and why; the owner decides.
2. **Strict gate:** `python scripts/gate.py --strict`. Red → stop.
3. **Prepare:** `python scripts/release.py prepare --bump <kind>` (`--dry-run` first if unsure). It
   bumps `VERSION` and opens a CHANGELOG stub. No commit yet.
4. **Write the CHANGELOG entry properly** — what changed for the people who use it, not a list of
   commits. Read the file with a `limit`; only its top matters.
5. **Finalize:** `python scripts/release.py finalize`. Commits `chore(release): vX.Y.Z`, tags that
   commit, mints the push + release approvals. It refuses while the entry is still the placeholder.
6. **Stop and ask for the go.** Say plainly what the deploy does to users (a restart, seconds
   offline, a migration). Wait for the answer.
7. **Ship:** `git push origin <main>`, then `git push origin vX.Y.Z` — the tag push deploys.
8. **Watch it land** and say what you saw, not "deployed successfully".
   <!-- project-specific: how CD is watched and how health is checked (/prod) -->
9. **Report** the version, what is in it, and the health result.

## If it goes wrong

Roll forward: fix, `prepare --bump patch`, release again. Moving a tag backwards leaves production on
a build nobody can reproduce from history. Production down and no quick fix → tell the owner; on
their word, restart the previous image by hand.
