---
owns: Stack, layout, the data sources and how each is read, the update channel, what talks to what.
not:  The order of building (docs/plan/) · process (.claude/docs/)
code: src/juice_mate/** · pyproject.toml
---

# Architecture

## 1. Goal

A Windows utility that shows, **on the taskbar itself** (not in the tray — owner, 2026-10-20), each
device's battery %, Claude usage limits and chosen system sensors, in the system's own visual style. It must run unnoticed (target < 60 MB RAM), start with Windows, and **update
itself without anyone touching it** — it will be installed on a second, non-technical user's PC.

Rules that follow from the second PC:
- **Nothing is hard-coded to the owner's hardware.** Every source discovers what is present; a source
  that finds nothing shows nothing. No config is required to get a useful result.
- **No admin rights, no UAC, no prompts** — install and updates are per-user.

## 2. Stack — LOCKED (owner, 2026-10-20)

| Concern | Choice | Why |
| ------- | ------ | --- |
| Language | Python 3.13, Poetry | the owner's main language; same tooling as Zebaro-Core-Bot / YA-32-Bot |
| Display | a Win32 window inside the taskbar via `ctypes`, drawn with `Pillow`, glyphs from Segoe Fluent Icons | §4b, §6 |
| Bluetooth battery | Windows PnP device properties (CfgMgr32 via `ctypes`, or `winrt` DeviceInformation) | see §3.1 |
| HID | `hidapi` (`hid` package) | feature reports for the Hator dongle, §3.2 |
| HTTP | `httpx` | Claude usage, §3.3 |
| Toasts | `windows-toasts` | native Windows notifications |
| Build | PyInstaller `--onedir` → Velopack `vpk pack` | §4 |
| Quality | ruff, mypy `--strict`, pytest — run only through `scripts/gate.py` | |

Rejected: Tauri (needs Rust, HID/DEVPKEY through windows-rs is verbose), C# (not the owner's stack),
Electron (RAM).

## 3. Sources

Every source implements one interface: `poll() -> list[Reading]`. A `Reading` is
`(source_id, device_id, name, percent | None, charging: bool | None, connected: bool, stale_after)`.
A failing source returns an error reading, never raises into the poll loop.

### 3.1 Bluetooth devices (MX Keys S, G435, any BT device that reports battery)

- Battery: property `DEVPKEY_Bluetooth_Battery` = `{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2`.
- Connected: `{83DA6326-97A6-4088-9453-A1923F573B29} 15`. **Must be checked** — when a device is
  disconnected Windows still returns the last cached battery value (seen with an Xbox controller).
  Disconnected → the device glyph dimmed with a "disconnected" mark, no %.

### 3.2 Hator Stellar Pro Wireless (HID)

- Dongle: Telink `VID_248A PID_5B4A`, the interface with usage page `0xFF01`.
- Request: `SetFeature 07 89 00 00 00 00 00 00` → `GetFeature(report 7, len 8)` (eight bytes with the
  report id; asking for nine fails with "read error") →
  `07 89 XX 01 02 03 00 00`, `XX` = battery %.
- The value is voltage-based and jitters ±1–3 % → smooth (median of recent readings, show integer).
- Charging: on cable the mouse also appears as USB `VID_248A PID_5B49` → `charging = True`.
- No answer, or zeros → the mouse is off or asleep → disconnected. The dongle cannot be opened → error.
- Present only when the dongle is found. Replaces Hator Hub (to be uninstalled at the end).

### 3.3 Claude usage limits — the fragile one

- Token: Claude Code's OAuth token from `~/.claude/.credentials.json`. **Read only. Never refresh it** —
  refreshing rotates the token and logs Claude Code out. Expired token → "re-open Claude Code" state,
  not a refresh.
- Request (confirmed 2026-10-21): `GET https://api.anthropic.com/api/oauth/usage`, headers
  `Authorization: Bearer <accessToken>` and `anthropic-beta: oauth-2025-04-20` → `five_hour` and
  `seven_day`, each `{utilization: % used, resets_at: ISO time}`. The answer also carries a dozen
  code-named experimental keys — **only those two are read**; parsing lives in `core/usage.py`, and an
  answer that no longer fits becomes "the usage answer changed", never a crash.
- On the panel: the ✳ glyph (Segoe UI Symbol) + the larger % used of the two windows; red from 80 %.
  Tooltip: both windows with the time to reset. 429 → five minutes' pause; 401/403 → "open Claude Code".
- One request every three minutes (once a minute drew 429s after an hour); on 429 a pause of 5 min,
  doubling to 30. A passing failure keeps the last numbers on the panel with "as of HH:MM" in the
  tooltip, for up to an hour; signing out drops them.
- No credentials file → no Claude item (the second PC).

## 4. Install and self-update

**Velopack** over a PyInstaller `--onedir` build:
- `Setup.exe` installs into `%LocalAppData%\JuiceMate` — per-user, no admin, no UAC; creates the Start
  menu shortcut; the app registers its own autostart (HKCU `Run`), toggled from the panel's menu.
- On start and every 6 h the app checks for an update, downloads it in the background (delta
  packages), and applies it **on the next start** or from the panel's menu item "Restart to update".
  Never restarts under the user on its own.
- `vpk` is a .NET tool — needed only in CI (`windows-latest`), never on the user's PC.
- **No console window, ever**: PyInstaller builds with `--windowed`; in development the app runs
  under `pythonw.exe`. Then `sys.stdout` / `sys.stderr` are `None` — code must not assume them.
- The app calls `velopack.App().run()` first thing in `main`, before argparse (Velopack runs the exe
  with its own hook arguments); the first run after install switches autostart on.
- Build: `poetry run python scripts/build.py` → `dist/JuiceMate/` (~42 MB, ~62 MB RAM running).
  CI: `.github/workflows/ci.yml` runs the strict gate on every push to main;
  `.github/workflows/release.yml` on a `vX.Y.Z` tag checks the tag against `VERSION`, builds,
  `vpk download` (deltas) → `vpk pack` → `vpk upload github --publish`.
- A frozen build run from `dist/` (not installed) logs once and skips self-update.

### 4.1 Where updates are downloaded from — LOCKED (owner, 2026-10-20)

**The repo `Zebaro24/Juice-Mate` is public**, and the app reads updates from its GitHub Releases with
Velopack's GitHub source — no token anywhere, no server.

Why not private: GitHub has no release-only token (a release asset needs `Contents: read`, which
also reads the source), so a token inside the app is the source for everyone who has the app. A
second "releases" repo and a Cloudflare Worker proxy were rejected as extra moving parts.

Consequence: **nothing secret ever goes into the repo** — no tokens, no personal device serials, no
account ids. The Hator protocol and the Claude usage call are public by choice.

## 4a. System sensors — replaces TrafficMonitor (owner, 2026-10-20)

TrafficMonitor is flagged by Defender because of `TrafficMonitor.sys`, the WinRing0 kernel driver it
installs for CPU temperature. Juice-Mate reads **only what needs no driver**. Each reading is a
`Sensor` class in `sources/system.py` (`read() -> Metric`); which ones are shown, and where, the owner
decides later — the classes exist so that choice is configuration, not code.

| Sensor | Value | How |
| ------ | ----- | --- |
| `NetworkSpeed("up" / "down")` | bytes/s | `psutil.net_io_counters()` delta between two reads |
| `CpuLoad` | % | `psutil.cpu_percent()` |
| `MemoryLoad` | % | `psutil.virtual_memory().percent` |
| `DiskUsage(path)` | % | `psutil.disk_usage(path).percent` |
| `DiskSpeed("read" / "write")` | bytes/s | `psutil.disk_io_counters()` delta |
| `GpuLoad` | % | PDH counter `\GPU Engine(*engtype_3D)\Utilization Percentage` — what Task Manager shows |
| `GpuTemperature` | °C | NVML (`nvml.dll`, ships with the NVIDIA driver); no NVIDIA → `error` |

Not read: **CPU temperature** — it needs ring 0, which is exactly what got TrafficMonitor flagged.
A sensor that cannot read returns a `Metric` with `error`, never raises.

## 4b. Taskbar panel — LOCKED: the only UI; no tray icons (owner, 2026-10-20)

Everything is shown on the taskbar itself, the way TrafficMonitor shows its numbers: device
batteries, Claude limits, the system sensors the owner picks. Tray icons were tried and rejected —
Windows 11 hides them behind "^", and they hold two digits at most.

How, chosen for robustness:
- **A child of the taskbar, not a floating window.** The panel window is re-parented into
  `Shell_TrayWnd` (`SetParent`, `WS_CHILD`). It then moves, hides (auto-hide, full-screen games) and
  stacks with the taskbar for free. Rejected: a topmost overlay — it fights the taskbar for z-order,
  shows over full-screen apps, and flickers when the taskbar takes focus.
- **Placement.** Windows 11: right-aligned just left of `TrayNotifyWnd` (still a Win32 child of
  `Shell_TrayWnd`), plus a configurable offset. Windows 10: shrink `MSTaskSwWClass` inside
  `ReBarWindow32` and sit in the gap — TrafficMonitor's own Win10 method.
- **Drawing.** Pillow renders RGBA, `UpdateLayeredWindow` pushes it with per-pixel alpha, so it blends
  with any taskbar colour or Mica (layered child windows work since Windows 8). Text colour follows
  `SystemUsesLightTheme`.
- **Staying attached.** Listen for the registered `TaskbarCreated` message (Explorer restarted →
  re-attach); a 2 s watchdog re-checks the parent handle and the free space; `WM_DISPLAYCHANGE` and
  DPI changes → re-layout.
- **Its own thread** with its own Win32 message loop; the poll loop hands it readings.
- **Fails quietly.** Cannot attach → a single tray icon appears *only then*, so the menu (Quit,
  autostart) stays reachable and its tooltip says "Taskbar panel unavailable".
- Main monitor first; `Shell_SecondaryTrayWnd` (other monitors) later.
- Right-click on the panel → the menu: Refresh, Start with Windows, Restart to update, Quit.

Risk: Windows 11 feature updates have reshaped the taskbar before. The panel step starts with a
spike that measures attach, Explorer restart, auto-hide and full screen on the real PC.

## 5. Layout

```
src/juice_mate/
  core/        readings, metrics, formatting, thresholds, icon state — pure, no IO, fully unit-tested
  sources/     bluetooth.py, hator.py, claude.py, system.py — one file per source, IO lives here
  panel/       the taskbar panel (§4b): Win32 window, layout, drawing, menu
  tray/        the fallback tray icon only (§4b), toasts
  update/      Velopack wiring, autostart
  app.py       poll loop: sources → core → panel
tests/
```

Layering (checked by `scripts/arch_lint.py`): `core` imports nothing from `sources`, `panel`, `tray`,
`update` or any IO library; `sources` never import `panel` or `tray`.

## 6. Look — the system's own style (owner, 2026-10-20 / 21; design council 2026-10-21)

**Two rows**, filled column by column, the way TrafficMonitor lays out its numbers. Each item is a
glyph and a number, nothing else — like the clock and the Wi-Fi / volume glyphs next to it:

```
 ✳ 5h  8%    🖱 88%
 ✳ 7d 57%    🎧 80%        (glyphs from Segoe Fluent Icons, not emoji)
```

Measured against the taskbar's own clock (digits 9 px tall, rows centred at y 15 and 31 of 48) and
Wi-Fi glyph (16 px), at 96 DPI, scaled with the taskbar's DPI:

| Element | Value | Why |
| ------- | ----- | --- |
| Rows | centres at 15/48 and 31/48 of the height | the clock's rows — the panel reads as part of it |
| Numbers | Segoe UI Variable 14 px, weight 500, gamma-lifted alpha | digits ~10 px tall; 12 px read "small" to the owner |
| Glyphs | 16 px, drawn at 4×, strokes grown by a 3×3 max filter, scaled down | the Wi-Fi glyph's size; owner asked for thicker lines |
| Tags `5h` / `7d` | the number's size (owner), ~75 % alpha | a smaller tag was unreadable on a red taskbar |
| Number slot | right-aligned, at least as wide as `00%` | 9 → 10 % and 88 → 89 % move nothing; % signs line up |
| Gaps | glyph → number 5, columns 12, usage ↔ devices 18, padding 8 | spacing separates the groups; no divider lines |
| Lone last item | top row | centred, it lines up with neither clock row |

- **Glyphs**: keyboard, mouse, headphones, game controller, phone, a generic Bluetooth glyph when the
  kind is unknown; the usage spark ✳ from Segoe UI Symbol. The kind comes from the device's classes
  and Bluetooth profiles, not from its name (except game controllers).
- **Colour**: the taskbar's text colour (light/dark theme), no background, no boxes. Low (< 20 %) →
  system red. Charging → a small bolt before the number. Unavailable → dimmed, `!` for a number, the
  reason in the tooltip (a badge over the glyph is not a Windows pattern).
- **Disconnected devices are not shown at all** — a cached number says nothing (owner, 2026-10-21).
- **Usage limits** → two items, one per window, ✳ `5h` and ✳ `7d` + % used; red from 80 %.
- **Tooltip** on hover: the full name, state, the time of the reading; for usage the window's time
  to reset. Hover areas split each column at the middle.
- A toast once when a device drops below 15 % (not again until it recovers).
