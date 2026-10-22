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

## Step 03 — taskbar panel (2026-10-20)

The tray icons are gone from the normal path: `panel/window.py` creates a layered window, re-parents
it into `Shell_TrayWnd` and places it just left of `TrayNotifyWnd`; `panel/render.py` draws each
device as a Segoe Fluent Icons glyph + percent in the taskbar's text colour, with Windows-like
antialiasing weight (alpha gamma 0.45). Disconnected → the glyph struck through and no number; low →
system red; charging → bolt; unavailable → warning badge. Device kind comes from the Bluetooth
profiles and device classes of the container (G435 headset, MX KEYS S keyboard, Xbox controller
gamepad, Zebaro-Phone phone — all correct on the owner's PC). Hover → a system tooltip with name,
state and time; right-click → Refresh now / Quit. A 2 s watchdog and `TaskbarCreated` re-attach after
Explorer restarts. One instance only (named mutex); log at `%LOCALAPPDATA%\JuiceMate\juice-mate.log`.
Tray icons remain only as the fallback when the panel cannot attach. Running: ~35 MB RAM.

Seen on the owner's PC: the panel in place, the tooltip on hover. ⚠️ Not tried yet: Explorer restart,
auto-hide, full-screen apps, a light taskbar, the right-click menu, a second monitor.

## Step 04 — Hator mouse (2026-10-21)

`sources/hator.py` finds the Telink dongle (248A:5B4A, usage page 0xFF01), sends `07 89 00…` and reads
feature report 7, eight bytes. The owner's mouse answered `07 89 59 01 02 03 00 00` → 89 %. A median
of the last five reads (`core/smoothing.py`) holds the voltage jitter still and resets on a charger
change. On the panel: mouse glyph + 89 % next to the live G435 80 % (which also closes step 02's
"connected" check). No dongle → no item. ⚠️ Charging via PID 5B49 on the cable, and the mouse switched
off, are covered by tests only — a 5-minute watch on the real mouse saw no change because nothing was
plugged or switched.

## Step 05 — Claude limits (2026-10-21)

`sources/claude.py` reads the access token from `~/.claude/.credentials.json` (never writes it, never
refreshes it — a test checks the file is byte-identical after a poll) and asks the usage endpoint at
most once a minute. Live on the owner's PC: ✳ 55 % on the panel, tooltip "5 h 13% (resets in 20 min) ·
week 55% (resets in 4 d 23 h)". No credentials file → no item; expired token / 401 → "open Claude
Code"; 429 → five minutes' pause; a changed answer → "the usage answer changed".

## Panel v2 (2026-10-21, owner's feedback)

Two rows, column by column; disconnected devices hidden; usage as two items (5h / 7d); glyphs drawn
bolder (4× + 3×3 max filter). Live: `✳ 5h 18% · ✳ 7d 55% | 🖱 88% · 🎧 80%`.

## Step 06 — alerts and autostart (2026-10-21)

`core/alerts.py`: one toast when a device drops below 15 %, re-armed only at 20 % or on the charger.
`tray/toasts.py` registers the AppUserModelID `Zebaro.JuiceMate` under HKCU so the toast is signed
"Juice-Mate" (seen on the owner's PC with a test toast). `update/autostart.py`: the HKCU `Run` entry —
the installed exe, or `pythonw -m juice_mate` from a dev checkout. The panel's right-click menu is
built from entries each time it opens: Refresh now · Start with Windows (checkmark) · Quit — opened
on the owner's PC.

## Panel v3 (2026-10-21, owner's feedback + design council)

Three reviewers (Windows fidelity, glanceability, layout) measured the panel against the clock:
numbers 14 px weight 500, glyphs 16 px, tags the number's size, rows on the clock's rows (15/31),
right-aligned numbers in a fixed slot, group spacing instead of dividers, `!` instead of a badge.
The usage source went to one request per three minutes after the endpoint answered 429, and keeps
its last numbers through passing failures. Seen: the panel hides with the taskbar in a full-screen
app.

## Step 07 — packaging and self-update (2026-10-21)

`scripts/build.py` draws the app icon and builds `dist/JuiceMate/JuiceMate.exe` with PyInstaller
`--windowed`; run on the owner's PC it attached the panel and read every source (62 MB RAM).
`update/updater.py`: Velopack hooks at start, autostart on first run, a check every 6 h against this
repo's GitHub Releases, download in the background, "Restart to update to X" in the panel menu, else
applied on the next start. CI and release workflows in `.github/workflows/`. ⚠️ Setup.exe and an
actual update are seen only once the first two releases exist.

## v0.1.0 released, then step 08 (2026-10-21)

v0.1.0: the release workflow built, packed and published `JuiceMate-win-Setup.exe` (34 MB), the full
package, a portable zip and `releases.win.json` to GitHub Releases.

Step 08: system sensors on the panel (2 s refresh, a Show submenu with checkmarks, settings.json),
the usage pace forecast with its toasts, and left-click targets. Rendered with live data on the
owner's PC: `✳ 5h 29% / 7d 60% · 🖱 86% / 🎧 80% · ↑ 16K / ↓ 2K · CPU 28% / GPU 41% · 83°`.

## Two strips, clock-sized text, Claude Code runs (2026-10-22)

The panel is two strips: sensors at the taskbar's left end after the weather widget (UI Automation
found its edge at x 158 on the owner's PC), batteries and usage by the notification area. Numbers are
13 px at weight 450, whole-pixel positions and a contrast curve — 9 px digits, measured equal to the clock's — and the rows sit 2 px further apart. Usage %
rounds down like Claude Code's `/usage` (it showed 2 % where the panel said 3 %). An expired token or
an idle 5-hour window makes Juice-Mate run `claude -p` on Haiku once (tried by hand: 3 s, answer in
Russian); its answer comes as a toast. ⚠️ Not yet seen in the app itself: a run on a real expiry or
idle window, the toast, a left-aligned taskbar.
