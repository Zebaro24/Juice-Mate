#!/usr/bin/env python3
"""Print one version's CHANGELOG section — the GitHub release's description and Velopack's notes.

    python scripts/release_notes.py 0.3.1 > notes.md

Only that version's section: from its `## vX.Y.Z` heading (left out — the release has its own title)
to the next one. A version without a section is an error, so a release never goes out blank.
Stdlib only: CI runs it before Poetry matters.
"""

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section(text: str, version: str) -> str | None:
    found = re.search(rf"^## v{re.escape(version)}\b[^\n]*\n(.*?)(?=^## v|\Z)", text, re.M | re.S)
    if not found:
        return None
    # The file wraps at 100 columns; GitHub's release page would show every wrap as a line break.
    return re.sub(r"\n(?!\n|- |#)\s*", " ", found.group(1).strip())


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    notes = section(CHANGELOG.read_text(encoding="utf-8"), sys.argv[1].removeprefix("v"))
    if not notes:
        print(f"no CHANGELOG section for v{sys.argv[1]}", file=sys.stderr)
        return 1
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
