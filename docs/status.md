---
owns: What already works, step by step, and what was not verified on the real target.
not:  What is planned (docs/plan/) · how it is built (docs/architecture.md)
code: src/juice_mate/**
---

# Status

## Step 01 — skeleton and gate (2026-10-20)

`poetry run python -m juice_mate` puts one grey "–" icon in the tray with a single menu item, Quit.
`core/reading.py` holds the reading model and its level (ok / low < 20 % / charging / offline /
unknown; offline wins over a cached percent). `tray/drawing.py` draws the number on a coloured
square with a bolt while charging. Gate: ruff, ruff format, mypy strict, pytest, arch-lint,
docs-lint, hooks — all green. ⚠️ Quit from the menu not clicked yet — the owner checks it.
