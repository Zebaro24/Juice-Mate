#!/usr/bin/env python3
# template-managed: addons/docs-lint/scripts/docs_lint.py — edit in _Claude-Template, not here
"""Docs lint — every page declares what it owns, and the code it claims still exists.

From Director-Mode-AI: documentation rots because nothing says which page owns a subject, so writing
the fact again is cheaper than finding where it lives. Every page under the checked folders opens with

    ---
    owns: one sentence — the single subject this page is authoritative for
    not:  adjacent subjects and where they live · ...
    code: path/or/glob · ...            (or `code: none — <reason>`)
    ---

Checked: the header exists and parses (one `key: value` per line, no wrapping); `owns:` and `not:`
are present; every `code:` path or glob matches at least one file.

Folders: `.claude/project.json` → "docs_lint": {"dirs": ["docs", ".claude/docs"], "require_code": false}.
Wire into the gate: {"name": "docs", "kind": "lint", "cwd": ".", "cmd": ["python", "scripts/docs_lint.py"]}.
Exit 0 = clean, 1 = violations. Stdlib only.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def header(text):
    if not text.startswith("---"):
        return None, "no header"
    end = text.find("\n---", 3)
    if end < 0:
        return None, "header not closed"
    fields = {}
    for line in text[3:end].strip().splitlines():
        key, sep, value = line.partition(":")
        if not sep or not key.strip().isidentifier():
            return None, f"not `key: value`: {line.strip()!r}"
        fields[key.strip()] = value.strip()
    return fields, None


def main():
    try:
        with open(os.path.join(ROOT, ".claude", "project.json"), encoding="utf-8") as f:
            cfg = json.load(f).get("docs_lint") or {}
    except (OSError, ValueError):
        cfg = {}
    dirs = cfg.get("dirs") or ["docs", ".claude/docs"]
    bad = 0
    for d in dirs:
        for path in glob.glob(os.path.join(ROOT, d, "**", "*.md"), recursive=True):
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            with open(path, encoding="utf-8", errors="replace") as f:
                fields, err = header(f.read())
            problems = [err] if err else []
            if fields is not None:
                problems += [f"missing `{k}:`" for k in ("owns", "not") if not fields.get(k)]
                code = fields.get("code")
                if code is None and cfg.get("require_code"):
                    problems.append("missing `code:` (write `code: none — <reason>` if deliberate)")
                elif code and not code.startswith("none"):
                    for g in (c.strip() for c in code.split("·")):
                        if g and not glob.glob(os.path.join(ROOT, g), recursive=True):
                            problems.append(f"`code:` matches nothing: {g}")
            for p in problems:
                bad += 1
                print(f"✗ {rel}: {p}")
    print(f"{'RED' if bad else 'GREEN'}: {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
