---
owns: The ordered steps that build the project, and the state of each.
not:  What each part does (docs/architecture.md) · what already works in detail (docs/status.md)
---

# Plan

One step = one session: input, output, and a **done when** that is a command with an expected result.
Ordered by dependency. ✅ done · ⚠️ written, not verified on the real target.

| #  | Step | State |
| -- | ---- | ----- |
| 01 | Skeleton and gate: `pyproject.toml` (Poetry, ruff, mypy strict, pytest), `src/juice_mate/`, `core` reading model, an empty tray icon that quits from the menu | ✅ · ⚠️ Quit clicked by the owner |
| 02 | Bluetooth source (§3.1): battery + connected state, any device; icons with numbers, tooltip | |
| 03 | Hator source (§3.2): HID feature report, smoothing, charging via PID 5B49 | |
| 04 | Claude source (§3.3): confirm the usage endpoint, read-only token, 5 h + weekly icon | |
| 05 | Thresholds and toasts (§6), autostart toggle | |
| 06 | Packaging and self-update (§4): PyInstaller + Velopack, CI release on tag, update source per §4.1 | |
| 07 | Install on both PCs, uninstall Hator Hub and Frida | |

Later (not v0.1): popover window with all readings and reset timers; laptop battery; Android phone
via ADB; usage pace forecast; history; a driver-free replacement for TrafficMonitor (network speed,
CPU / GPU load) — open questions in `_ideas/system-monitor-without-driver.md`. Source ideas: the
Bento note "Tray app — ideas, names, analysis".

Every step: **Read** docs/architecture.md (the § named) · **Done when** `python scripts/gate.py` is
GREEN and the behaviour named in the row is visible in the tray on the owner's PC.
