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

## Step 02 — Bluetooth (2026-10-20)

`sources/bluetooth.py` enumerates every device node through SetupAPI (disconnected ones included),
keeps the containers that have a battery node and folds each into one reading named after its
`BTHENUM\DEV_…` / `BTHLE\DEV_…` node. One poll takes ~0.15 s. Interim tray icons, one per device, refreshed every 30 s and from the menu ("Refresh now"); no device →
one grey placeholder. The owner rejected tray icons — the taskbar panel (step 03) replaces them.
On the owner's PC with everything away: G435 80, MX KEYS S 45, Xbox controller 77, Zebaro-Phone 0 —
all correctly *disconnected* (cached %). ⚠️ Not yet seen with a device connected.

`python -m juice_mate --dump` prints every reading once — the quickest check on any PC.

## Step 02b — system sensors (2026-10-20)

`sources/system.py`: `NetworkSpeed`, `CpuLoad`, `MemoryLoad`, `DiskUsage`, `DiskSpeed`, `GpuLoad`
(PDH, Task Manager's number), `GpuTemperature` (NVML; NVIDIA only). All read on the owner's PC
(GPU temp 52°). Not shown anywhere yet except `--dump` — the taskbar panel (step 08) shows them.
