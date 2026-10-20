#!/usr/bin/env python3
# template-managed: core/scripts/approve.py — edit in _Claude-Template, not here
"""Mint the approval marker that unlocks one outward action.

guard-git refuses `git push` and pushing a release tag. This is what opens them — a separate step on
purpose: an approval should be a deliberate act with a name, not a flag buried in a command line.

  push      one push (solo: consumed by it; team: covers every repo of the feature until it expires)
  release   one release-tag push = a deploy (also mints `push`, the release commit goes out first)

The marker records the HEAD of every repo here (the root, and repos one level below), so a commit
made after approving makes it stale — the approval covers exactly the commits that were checked.
TTL: `.claude/project.json` → approval.ttl_minutes.

Usage:  python scripts/approve.py push | release
Stdlib only.
"""
import json
import os
import sys
import time

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# Root from this file, not the cwd: a marker dropped in the wrong .claude/ is one no guard reads.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
import _lib  # noqa: E402


def mint(action):
    heads = {}
    for repo in _lib.repos_under(ROOT):
        sha = _lib.git_out(repo, "rev-parse", "HEAD")
        if sha:
            heads[_lib.repo_key(ROOT, repo)] = sha
    path = _lib.marker_path(ROOT, action)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"created": int(time.time()), "heads": heads}, f)
    return path, heads


def main():
    actions = [a for a in sys.argv[1:] if not a.startswith("-")] or [""]
    action = actions[0].lstrip("-")
    if action not in ("push", "release"):
        print("usage: python scripts/approve.py push | release")
        return 2
    cfg = _lib.load_config(ROOT)
    ttl = cfg["approval"]["ttl_minutes"]
    for name in (["push", "release"] if action == "release" else ["push"]):
        path, heads = mint(name)
        bound = ", ".join(f"{k}@{v[:7]}" for k, v in heads.items()) or "no git repo"
        print(f"  ✓ {os.path.relpath(path, ROOT)} — valid {ttl} min, bound to {bound}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
