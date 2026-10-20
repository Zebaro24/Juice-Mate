#!/usr/bin/env python3
# template-managed: addons/arch-lint/scripts/arch_lint.py — edit in _Claude-Template, not here
"""Architecture lint — the layering rules a reviewer keeps forgetting, checked mechanically.

Each rule: files matching `files` must not contain a line matching `forbid`. Declared in
`.claude/project.json`:

    "arch_lint": [
      {"name": "domain is pure", "files": ["apps/api/app/domain/**/*.py"],
       "forbid": "^\\s*(from|import)\\s+(sqlalchemy|app\\.services)", "why": "domain has no DB access"},
      {"name": "bot calls the API", "files": ["apps/bot/**/*.py"],
       "forbid": "^\\s*from\\s+app\\.(services|db)", "why": "the bot goes through HTTP"}
    ]

A line ending in `# arch-lint: allow <rule name>` is exempt — visible in review, greppable later.
Wire into the gate: {"name": "arch", "kind": "lint", "cwd": ".", "cmd": ["python", "scripts/arch_lint.py"]}.
Exit 0 = clean, 1 = violations, 2 = no config. Stdlib only.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    try:
        with open(os.path.join(ROOT, ".claude", "project.json"), encoding="utf-8") as f:
            rules = json.load(f).get("arch_lint") or []
    except (OSError, ValueError):
        rules = []
    if not rules:
        print("no arch_lint in .claude/project.json")
        return 2
    bad = 0
    for rule in rules:
        pat = re.compile(rule["forbid"])
        allow = f"# arch-lint: allow {rule['name']}"
        for g in rule["files"]:
            for path in glob.glob(os.path.join(ROOT, g), recursive=True):
                with open(path, encoding="utf-8", errors="replace") as f:
                    for no, line in enumerate(f, 1):
                        if pat.search(line) and allow not in line:
                            bad += 1
                            rel = os.path.relpath(path, ROOT).replace("\\", "/")
                            print(f"✗ {rel}:{no}  [{rule['name']}] {rule.get('why', '')}\n    {line.strip()}")
    print(f"{'RED' if bad else 'GREEN'}: {bad} violation(s), {len(rules)} rule(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
