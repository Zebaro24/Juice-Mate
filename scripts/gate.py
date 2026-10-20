#!/usr/bin/env python3
# template-managed: core/scripts/gate.py — edit in _Claude-Template, not here
"""Quality gate — the single checker. Never run a linter or a test runner by hand.

A green that this script did not produce is not the green CI produces. The checks themselves are
declared per project in `.claude/project.json` → gate.targets; this file is the same everywhere.

    "gate": {
      "base_ref": "origin/main",
      "targets": {
        "api": {
          "dir": "apps/api",
          "checks": [
            {"name": "ruff",   "kind": "lint", "cmd": ["poetry", "run", "ruff", "check", "."]},
            {"name": "mypy",   "kind": "lint", "cmd": ["poetry", "run", "mypy", "."]},
            {"name": "pytest", "kind": "test", "cmd": ["poetry", "run", "pytest", "-q"], "args_ok": true},
            {"name": "audit",  "kind": "lint", "cmd": ["poetry", "run", "pip-audit"], "strict": true}
          ]
        }
      }
    }

A target whose `dir` does not exist yet prints `— no directory` and fails nothing: the repo grows,
the command never changes. The built-in target `hooks` runs scripts/check_hooks.py — the guards sit
outside every app, so no CI ever sees them.

Usage
  python scripts/gate.py                         everything that exists
  python scripts/gate.py --target api,web        some targets
  python scripts/gate.py --changed               only targets touched since base_ref (unknown path → all)
  python scripts/gate.py --lint | --tests        one kind of check
  python scripts/gate.py --strict                + checks marked "strict" (before a release / submit)
  python scripts/gate.py --only pytest -- tests/test_x.py::test_y
  python scripts/gate.py --jobs 1                one at a time, honest per-check timing
  python scripts/gate.py --list

Exit code is non-zero if any selected check failed. Stdlib only.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILTIN = {
    "hooks": {"dir": ".claude/hooks", "builtin": True, "checks": [
        {"name": "check_hooks", "kind": "test", "cmd": [sys.executable, "scripts/check_hooks.py"], "cwd": "."},
    ]},
}


def load_targets():
    try:
        with open(os.path.join(ROOT, ".claude", "project.json"), encoding="utf-8") as f:
            gate = (json.load(f) or {}).get("gate") or {}
    except (OSError, ValueError):
        gate = {}
    targets = dict(gate.get("targets") or {})
    for name, spec in BUILTIN.items():
        targets.setdefault(name, spec)
    return targets, gate.get("base_ref") or "origin/main"


def changed_targets(targets, base_ref):
    try:
        out = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", base_ref, "--"],
                             capture_output=True, text=True, timeout=30)
        local = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                               capture_output=True, text=True, timeout=30)
    except Exception:
        return list(targets)
    if out.returncode != 0:
        return list(targets)
    paths = [p for p in out.stdout.splitlines() if p]
    paths += [line[3:] for line in local.stdout.splitlines() if len(line) > 3]
    hit = set()
    for p in paths:
        p = p.replace("\\", "/")
        owners = [n for n, t in targets.items() if p.startswith(t["dir"].rstrip("/") + "/")]
        if p.startswith("scripts/"):
            owners.append("hooks")
        if not owners:
            # A path no target owns could break anything — say so by running everything.
            return list(targets)
        hit.update(owners)
    return [n for n in targets if n in hit]


def run_check(target, spec, check, extra):
    cwd = os.path.join(ROOT, check.get("cwd", spec["dir"]))
    cmd = list(check["cmd"]) + list(extra)
    if shutil.which(cmd[0]) is None and not os.path.exists(cmd[0]):
        return target, check["name"], "MISSING", 0.0, f"`{cmd[0]}` not found on PATH"
    start = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=check.get("timeout", 1800))
        status = "ok" if r.returncode == 0 else "FAIL"
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-40:]) if status != "ok" else ""
    except subprocess.TimeoutExpired:
        status, tail = "FAIL", "timed out"
    return target, check["name"], status, time.time() - start, tail


def main():
    argv = sys.argv[1:]
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description="The single quality gate.")
    ap.add_argument("--target", default="")
    ap.add_argument("--changed", action="store_true")
    ap.add_argument("--lint", action="store_true")
    ap.add_argument("--tests", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--jobs", type=int, default=max(2, (os.cpu_count() or 4) // 2))
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    targets, base_ref = load_targets()
    if args.list:
        for name, spec in targets.items():
            exists = os.path.isdir(os.path.join(ROOT, spec["dir"]))
            print(f"{name:10} {spec['dir']:28} {'' if exists else '(no directory) '}"
                  + " · ".join(c["name"] + (" [strict]" if c.get("strict") else "") for c in spec["checks"]))
        return 0

    names = [t for t in args.target.split(",") if t] if args.target else (
        changed_targets(targets, base_ref) if args.changed else list(targets))
    unknown = [n for n in names if n not in targets]
    if unknown:
        print(f"unknown target(s): {', '.join(unknown)} — see --list")
        return 2

    jobs, rows = [], []
    for name in names:
        spec = targets[name]
        if not os.path.isdir(os.path.join(ROOT, spec["dir"])):
            rows.append((name, "—", "skip", 0.0, "no directory"))
            continue
        for check in spec["checks"]:
            if args.only and check["name"] != args.only:
                continue
            if check.get("strict") and not args.strict:
                continue
            if args.lint and check.get("kind") != "lint":
                continue
            if args.tests and check.get("kind") != "test":
                continue
            if extra and not check.get("args_ok"):
                continue
            jobs.append((name, spec, check, extra))
    if not jobs and not rows:
        print("nothing selected — see --list")
        return 2

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rows += list(pool.map(lambda j: run_check(*j), jobs))

    failed = [r for r in rows if r[2] in ("FAIL", "MISSING")]
    for target, check, status, secs, _tail in rows:
        mark = {"ok": "✓", "FAIL": "✗", "MISSING": "?", "skip": "—"}[status]
        print(f"  {mark} {target:10} {check:16} {status:8} {secs:6.1f}s")
    for target, check, status, _secs, tail in failed:
        print(f"\n── {target} · {check} ──\n{tail}")
    print(f"\n{'RED' if failed else 'GREEN'}: {len(rows) - len(failed)}/{len(rows)} ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
