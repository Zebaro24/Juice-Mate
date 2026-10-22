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
| 02 | Bluetooth source (§3.1): battery + connected state, any device; shown as interim tray icons | ✅ · connected G435 seen live 2026-10-21 |
| 02b | System sensors (§4a) as components: network, CPU, memory, GPU load, GPU temp, disk — readable with `--dump`, not shown yet | ✅ |
| 03 | Taskbar panel (§4b, §6): spike first — attach to `Shell_TrayWnd`, survive Explorer restart, auto-hide, full screen, light/dark — then glyph + % per device in the system style, tooltip, right-click menu; the tray icons go | ✅ · ⚠️ Explorer restart, auto-hide, full screen and a light taskbar not yet tried |
| 04 | Hator source (§3.2): HID feature report, smoothing, charging via PID 5B49 | ✅ · ⚠️ charging (cable) and mouse-off not yet seen on the real mouse |
| 05 | Claude source (§3.3): confirm the usage endpoint, read-only token, 5 h + weekly item | ✅ |
| 06 | Thresholds and toasts (§6), autostart toggle | ✅ · ⚠️ a real low-battery toast not seen yet (rule covered by tests, toast shown once by hand) |
| 07 | Packaging and self-update (§4): PyInstaller `--windowed` + Velopack, CI release on tag, GitHub source | ✅ · ⚠️ install and a real update from v0.1.0 → v0.1.1 not yet seen |
| 08 | System sensors on the panel with a Show menu; usage pace forecast and alerts; click-to-open; then the owner uninstalls TrafficMonitor | ✅ · ⚠️ TrafficMonitor still installed (owner's call) |
| 09 | Install on both PCs, uninstall Hator Hub and Frida | ✅ owner's PC: v0.3.0 installed, self-updated to 0.3.1; Hator Hub removed (owner), Frida (pip `frida`, `frida-tools`) removed · ⚠️ second PC not yet |
| 10 | Settings model: sources on/off (Sources menu), device name / hide / order / icon, thresholds and per-kind notification switches, per-item placement — all in settings.json, read live | ✅ |
| 11 | Claude display: `5h 45% →16:00`, `7d 66% →26.10` (reset time, switchable), used or left | ✅ |
| 12 | New sensors, nothing to install: ping with "offline", RAM and VRAM in GB | ✅ |
| 13 | Settings window (WebView2, Juice-Mate's own dark look): everything of step 10 without editing JSON, icon picker for devices, own title bar with minimize / close / quit everything | ✅ · ⚠️ not yet in an installed build |
| 14 | Hover card instead of the tooltip: story and chart per item (battery drain and charges, usage pace, sensor hour), history kept on disk | ✅ · ⚠️ not yet seen by the owner on a real hover |
| 15 | News: buttons that open the articles, topics, recent news in the menu | ✅ · ⚠️ the notification's buttons not yet clicked by the owner |
| 16 | Second monitor: strips on `Shell_SecondaryTrayWnd`, each item placed main / second, left / right | |

Later (not v0.1): popover window with all readings and reset timers; laptop battery; Android phone
via ADB; per-day traffic history. Source ideas: the Bento note "Tray app —
ideas, names, analysis".

Every step: **Read** docs/architecture.md (the § named) · **Done when** `python scripts/gate.py` is
GREEN and the behaviour named in the row is visible on the taskbar on the owner's PC.
