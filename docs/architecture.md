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
  refreshing rotates the token and logs Claude Code out. Expired token → Juice-Mate runs Claude Code
  itself, invisibly (`sources/claude_run.py`): `claude -p <prompt> --model haiku`, no tools, no MCP,
  no session file, no user settings. Claude Code renews its own token as it always does; the file is
  re-read every poll (no request), so the renewed token shows at once.
- **Keeping the 5-hour window running** (owner, 2026-10-22; a menu checkbox, off by default — it spends the account's quota): when the
  answer shows no running 5-hour window, the same run opens one. At most one run per 30 min; "Ask
  Claude now" in the menu (shown when Claude Code is installed) runs it at once. The
  prompt is `claude_prompt` in `settings.json` and its answer comes as a toast; an empty prompt
  renews silently. `{news}` in the prompt becomes the last day's headlines from The Verge, TechCrunch
  and Engadget RSS (`sources/news.py`, fetched by Juice-Mate: ~1k tokens, where a web search by
  Claude Code would cost thousands). The default (owner, 2026-10-22): the two tech stories that matter
  most to an ordinary user — a new device, a new AI model, a launch — one Russian line each.
- **News with links** (owner, 2026-10-22): the headlines go into the prompt numbered
  (`[7] [The Verge] …`) and each answer line ends with its number (`… #7`); `core/news.py` ties the
  lines back to their articles. The notification gets a "Read · source" button per story and opens
  the first article when clicked; the menu's **Recent news** lists the last five
  (`news.json` in the data folder, thirty kept). Only `https` links to the three feeds' own sites
  are ever opened (`app.open_article`): the answer of a language model must not choose what opens.
- **Topics** (`news_topics`, the settings window's chips): AI, devices, games, software, science,
  business; a partial pick adds "Prefer stories about: …" to the prompt. Saved prompts equal to an
  earlier default move to the current one on load (`OLD_DEFAULT_PROMPTS`). One run costs a fraction of a percent of the window.
- Request (confirmed 2026-10-21): `GET https://api.anthropic.com/api/oauth/usage`, headers
  `Authorization: Bearer <accessToken>` and `anthropic-beta: oauth-2025-04-20` → `five_hour` and
  `seven_day`, each `{utilization: % used, resets_at: ISO time}`. The answer also carries a dozen
  code-named experimental keys — **only those two are read**; parsing lives in `core/usage.py`, and an
  answer that no longer fits becomes "the usage answer changed", never a crash.
- On the panel: the ✳ glyph (Segoe UI Symbol) + % used, rounded down like Claude Code's `/usage`;
  red from 80 % or when the pace runs the window out before it resets. Then the reset time, quiet as
  the tag: `5h 45% →16:00`, `7d 66% →26.10` — a time within a day, a date further off (owner,
  2026-10-22; `claude_reset_time`). `claude_left` shows what is left instead; the colour still
  follows what is used.
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
  with its own hook arguments). Autostart: on in the after-install hook and again at the first run,
  off in the before-uninstall hook. Every hook gets the version as an argument — 0.3.0's hook took
  none, failed silently and installed without autostart.
- Build: `poetry run python scripts/build.py` → `dist/JuiceMate/` (~42 MB, ~62 MB RAM running).
  CI: `.github/workflows/ci.yml` runs the strict gate on every push to main;
  `.github/workflows/release.yml` on a `vX.Y.Z` tag checks the tag against `VERSION`, builds,
  `vpk download` (deltas) → `vpk pack` → `vpk upload github --publish`. The release's description
  and the package's notes are that version's CHANGELOG section only (`scripts/release_notes.py`).
  Both workflows cache `.venv` keyed on `poetry.lock`, and pip for Poetry itself.
- Update conditions (seen 2026-10-22, 0.3.0 → 0.3.1): a check at every start and every 6 h; the delta
  downloads in the background (~3 s); applied at the next start, or at once from "Restart to update".
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
| `MemoryUsed` | bytes (`21.3G`) | `psutil.virtual_memory().used`; the total in the tooltip |
| `VideoMemoryUsed` | bytes | PDH `\GPU Adapter Memory(*)\Dedicated Usage`, the busiest adapter; total from the display class key's `HardwareInformation.qwMemorySize`. A sleeping laptop GPU reads 0 |
| `Ping` | ms (`23ms`) | `IcmpSendEcho` (iphlpapi, no admin) to 1.1.1.1 every 2 s on its own thread; two misses in a row → `off` in red |

On the panel (2026-10-21): each sensor is an item in the `system` group — ↑/↓ arrows (70 % size, they
fill the em box), a chip for CPU, a card for GPU, a thermometer, a memory chip, a drive — refreshed
every 2 s while batteries refresh every 30 s. Right-click → **Show** → a checkmark per sensor; the
choice lives in `%APPDATA%\JuiceMate\settings.json` (`settings.py`, written atomically), next to the
log — never in `%LOCALAPPDATA%\JuiceMate`, Velopack's install folder: a file there made Setup think
the app was installed, and uninstall wipes it (`folders.py`; 0.3.0's settings are carried over once).
Default: up, down, CPU, GPU — what TrafficMonitor showed on the owner's taskbar. Red: ≥ 85 °C, ≥ 95 %.

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
- **Placement.** Two strips (owner, 2026-10-22). Batteries and usage: right-aligned just left of
  `TrayNotifyWnd`. System sensors: the taskbar's left end, after the Widgets (weather) button, whose
  right edge comes from UI Automation (AutomationId `WidgetsButton`, `panel/uia.py`, on its own
  thread). A left-aligned taskbar (`TaskbarAl` = 0) has Start there, so the sensors join the right strip. Windows 10: shrink `MSTaskSwWClass` inside
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
- Right-click on the panel → the menu (§6c): Settings, Show, Sources, Refresh, Ask Claude, the 5-hour window, Start with Windows, Restart to update, Quit.

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
Wi-Fi glyph (16 px), at 96 DPI, scaled with the taskbar's DPI (re-measured 2026-10-22):

| Element | Value | Why |
| ------- | ----- | --- |
| Rows | centres at 14/48 and 32/48 of the height | 2 px further apart than the clock's: 16 px glyphs stuck together (owner) |
| Numbers | Segoe UI Variable 14 px, weight 600, whole pixels, contrast curve on alpha | digits 10 px; 13 px (the clock's 9 px) still read smaller than the clock, 12 px "tiny" (owner) |
| Glyphs | 16 px, drawn at 4×, strokes grown by a 3×3 max filter (5×5 for ✳), scaled down | the Wi-Fi glyph's size; owner asked for thicker lines, and a bolder ✳ |
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
- **Usage limits** → two items, one per window, ✳ `5h` and ✳ `7d` + % used; red from 80 % or when
  the pace says the window runs out before it resets. Sensors are red from 95 % load or 85 °C.
- **Tooltip** on hover: the full name, state, the time of the reading; for usage the window's time
  to reset. Hover areas split each column at the middle.
- A toast once when a device drops below 15 % (not again until it recovers).
- **Usage pace** (the Bento note's main idea): from the last hour of samples, when a window runs out
  at the current pace; shown in the tooltip only if that comes before the reset, with one toast per
  window. A window that was ≥ 80 % used and resets earns a "limit is back" toast.
- **Left click** opens what the item belongs to: usage → claude.ai/settings/usage, devices → Windows'
  Bluetooth settings, sensors → Task Manager.

## 6a. Settings — the owner's word on every item (owner, 2026-10-22)

All in `settings.json` (`settings.py`), read by the poll loop every tick, so a change shows within
two seconds; the menu and the settings window (step 13) only change fields and save.

**The settings window** (owner, 2026-10-22) — menu → **Settings…**. A process of its own,
`JuiceMate.exe --settings` (`ui/settings_app.py`), so a window waiting on the user never touches the
taskbar's thread and a crash there never takes the panel along. Drawn by WebView2 (Edge, built into
Windows 11; `pywebview`) from `ui/settings.html`: chosen over real WinUI 3, which worked in a spike
but leaves no room for the charts and motion the owner wants. Its look is Juice-Mate's own — dark,
quiet, a distant cousin of zebaro.dev: night navy, one cyan signal for what is on, magenta only for
what is red, mono labels, the site's calm easing. No Windows frame: the page draws a title bar with
minimize, close (this window only) and quit (Juice-Mate entirely, two clicks), with Windows 11's
rounded corners and the logo as the icon (`logo.py` → `%APPDATA%\JuiceMate\icon.ico`).

- The page changes one field at a time through `Api` (reload the file, `Settings.assign`, save);
  the panel process picks the file up with `Settings.reload_if_changed()` on its next tick.
- What can be listed comes from `items.json`, which the panel writes when a new device reports.
- Quit everything: a named event `Local\JuiceMateQuit` the panel waits on (`quit.py`).
- One window at a time (mutex `Local\JuiceMateSettings`); a second **Settings…** brings it forward.

- **Sources** on/off (`sources`): Claude usage, Bluetooth devices, HATOR mouse. Off = not polled at
  all; the Claude menu items go too. Menu → **Sources**.
- **Devices** (`devices`, by item key `source:device_id`): a name, an icon (a `Kind` — for a device
  whose kind was guessed wrong), hidden. A usage window keeps its spark whatever is set
  (`core/arrange.py: personalise`).
- **Order** (`order`): item keys named come first in that order; the rest follow in the default order,
  so a new device never jumps ahead of the arranged ones.
- **Placement** (`placement`): `left`, `right`, `second-left`, `second-right`. Default: sensors left,
  everything else right. Until the second monitor's strips exist (step 16) `second-*` join the main ones.
- **Thresholds**: battery red below `battery_low` (20), its notification below `battery_alert` (15),
  Claude red from `usage_high` (80), a sensor red from `busy_percent` (95) or `hot_celsius` (85).
- **Notifications** by kind (`alerts`): `battery`, `usage_pace`, `usage_back`, `news`.
- A broken field falls back to its own default and is logged; switch maps (`sources`, `alerts`) keep
  defaults for keys the file does not name, so a source added in an update starts on.

## 6b. Hover card — the tooltip's replacement (owner, 2026-10-22)

The plain tooltip blinked out every time the panel repainted. Now resting the mouse on an item for
~0.3 s opens a card above it, in the settings window's look (`panel/card.py` draws it with Pillow,
`panel/hover.py` runs it on the panel thread): glyph, name, the number, a few lines of story, and a
chart. It rises a few pixels while it fades in, swaps its content in place when the mouse moves to
the next item, is redrawn in place with every update (nothing blinks), and fades out on leave.
A layered top-most window that never takes focus or clicks; no WebView — instant and light.

- **Batteries**: draining N% an hour, lasts about X more, last charged at HH:MM; charging → full in
  about X. Chart: the last 12 h, the charging stretches shaded (`core/insight.py`: a least-squares
  rate over the samples since the last charge, at least 20 minutes of them).
- **Usage windows**: resets in X at HH:MM, and when the limit comes at this pace. Chart: 5 h.
- **Sensors**: low / average / high of the last hour, GB of total for memory. Chart: the hour.
- History (`core/history.py`): batteries and usage windows one sample per 2 min for two days, saved
  to `%APPDATA%\JuiceMate\history.json` every 10 min and at quit; sensors every tick for an hour, in
  memory. One sample per step-long bucket, the newest value in it.

## 6c. The right-click menu — Juice-Mate's own (owner, 2026-10-22)

Windows' popup menu cannot be restyled, so `panel/menu.py` draws one like the hover card: a layered
window, the same palette, redrawn on every hover change; not modal, so the panel keeps updating.
A header label, Fluent glyphs per line, a cyan bar on the line under the mouse (magenta for Quit,
cyan text for "Restart to update"). Switches instead of check marks: clicking one slides it and
keeps the menu open. Submenus (Show, Sources) slide out beside it after a short rest; the root keeps
the keyboard focus (submenus never activate), so a click anywhere else closes everything. Esc,
arrows and Enter work. Opens above the cursor, kept between the taskbar's ends.
