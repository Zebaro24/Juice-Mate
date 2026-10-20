#!/usr/bin/env python3
# template-managed: solo/scripts/release.py — edit in _Claude-Template, not here
"""Release helper — a deliberate, deployable version. It never pushes.

Pushing a release tag is what reaches production, so this is slow on purpose and split in two, so
the tag always points at the commit that carries the finished CHANGELOG:

  prepare   checks main + clean tree, bumps VERSION, opens a CHANGELOG entry. No commit.
            → the /release skill now writes the entry properly.
  finalize  commits `chore(release): vX.Y.Z`, tags it, mints the push + release approvals.
            → the skill asks for the owner's go, then pushes main and the tag.

(The single-step version tagged first and amended the CHANGELOG afterwards — leaving the tag on a
commit that is not on main.)

One version, one file: `VERSION` at the root. Anything else that needs the version reads it there.

Usage
  python scripts/release.py prepare --bump patch|minor|major [--dry-run]
  python scripts/release.py prepare --version 1.4.0
  python scripts/release.py finalize
Stdlib only.
"""
import argparse
import os
import re
import subprocess
import sys
from datetime import date

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import _lib  # noqa: E402
import approve  # noqa: E402

VERSION_FILE = os.path.join(ROOT, "VERSION")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
ENTRY = re.compile(r"^## v(\d+\.\d+\.\d+)", re.M)
PLACEHOLDER = "- <what actually changed for the people who use it>"


def git(*args):
    p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def read_version():
    try:
        raw = open(VERSION_FILE, encoding="utf-8").read().strip().lstrip("v")
        return tuple(int(x) for x in raw.split("."))
    except (OSError, ValueError):
        return (0, 0, 0)


def preflight(cfg):
    _, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    main = cfg["git"]["main_branch"]
    if branch.strip() != main:
        return f"a release is cut from {main}, you are on {branch.strip()}"
    return None


def prepare(args, cfg):
    problem = preflight(cfg)
    _, dirty = git("status", "--porcelain")
    if problem or dirty.strip():
        print(f"✗ {problem or 'the tree is not clean — commit or stash first'}")
        return 2
    cur = read_version()
    if args.version:
        new = tuple(int(x) for x in args.version.lstrip("v").split("."))
    else:
        major, minor, patch = (cur + (0, 0, 0))[:3]
        new = {"patch": (major, minor, patch + 1), "minor": (major, minor + 1, 0), "major": (major + 1, 0, 0)}[args.bump]
    if new <= cur:
        print(f"✗ {'.'.join(map(str, new))} is not above {'.'.join(map(str, cur))}")
        return 2
    ver = ".".join(map(str, new))
    print(f"  {'.'.join(map(str, cur))} → {ver}")
    if args.dry_run:
        print("  (dry-run) would bump VERSION and open a CHANGELOG entry")
        return 0
    open(VERSION_FILE, "w", encoding="utf-8").write(ver + "\n")
    entry = f"## v{ver} — {date.today().isoformat()}\n\n{PLACEHOLDER}\n\n"
    old = open(CHANGELOG, encoding="utf-8").read() if os.path.isfile(CHANGELOG) else "# Changelog\n\n"
    first = ENTRY.search(old)
    # The new entry goes before the previous one but after the intro — inserting right under the
    # heading would push the intro further down with every release.
    new_text = old[:first.start()] + entry + old[first.start():] if first else old.rstrip() + "\n\n" + entry
    open(CHANGELOG, "w", encoding="utf-8").write(new_text)
    print("  ✓ VERSION and a CHANGELOG stub. Write the entry, then: python scripts/release.py finalize")
    return 0


def finalize(cfg):
    problem = preflight(cfg)
    if problem:
        print(f"✗ {problem}")
        return 2
    ver = ".".join(map(str, read_version()))
    text = open(CHANGELOG, encoding="utf-8").read() if os.path.isfile(CHANGELOG) else ""
    top = ENTRY.search(text)
    if not top or top.group(1) != ver:
        print(f"✗ CHANGELOG.md has no entry for v{ver} on top — run prepare first")
        return 2
    if PLACEHOLDER in text[top.start():top.start() + 2000]:
        print("✗ the CHANGELOG entry is still the placeholder — write what changed")
        return 2
    tag = f"v{ver}"
    for step in (("add", "VERSION", "CHANGELOG.md"), ("commit", "-m", f"chore(release): {tag}"),
                 ("tag", "-a", tag, "-m", tag)):
        code, out = git(*step)
        if code != 0:
            print(f"✗ git {' '.join(step)} failed:\n{out}")
            return 1
    approve.mint("push")
    approve.mint("release")
    print(f"  ✓ committed and tagged {tag}; push + release approved for {cfg['approval']['ttl_minutes']} min")
    print(f"  after the owner's go:\n    git push origin {cfg['git']['main_branch']}\n    git push origin {tag}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["prepare", "finalize"])
    ap.add_argument("--bump", choices=["patch", "minor", "major"])
    ap.add_argument("--version")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = _lib.load_config(ROOT)
    if args.phase == "prepare":
        if not (args.bump or args.version):
            print("prepare needs --bump patch|minor|major or --version X.Y.Z")
            return 2
        return prepare(args, cfg)
    return finalize(cfg)


if __name__ == "__main__":
    sys.exit(main())
