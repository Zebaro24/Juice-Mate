---
owns: Stack, layout, the data sources and how each is read, the update channel, what talks to what.
not:  The order of building (docs/plan/) · process (.claude/docs/)
code: src/juice_mate/** · pyproject.toml
---

# Architecture

## 1. Goal

A Windows tray utility that shows, at a glance, one icon per device with its battery % and one icon
for Claude usage limits. It must run unnoticed (target < 60 MB RAM), start with Windows, and **update
itself without anyone touching it** — it will be installed on a second, non-technical user's PC.

Rules that follow from the second PC:
- **Nothing is hard-coded to the owner's hardware.** Every source discovers what is present; a source
  that finds nothing shows no icon. No config is required to get a useful result.
- **No admin rights, no UAC, no prompts** — install and updates are per-user.

## 2. Stack — LOCKED (owner, 2026-10-20)

| Concern | Choice | Why |
| ------- | ------ | --- |
| Language | Python 3.13, Poetry | the owner's main language; same tooling as Zebaro-Core-Bot / YA-32-Bot |
| Tray | `pystray` + `Pillow` (icons drawn at runtime) | small, native `NotifyIcon` underneath |
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
A failing source returns an error reading, never raises into the tray loop.

### 3.1 Bluetooth devices (MX Keys S, G435, any BT device that reports battery)

- Battery: property `DEVPKEY_Bluetooth_Battery` = `{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2`.
- Connected: `{83DA6326-97A6-4088-9453-A1923F573B29} 15`. **Must be checked** — when a device is
  disconnected Windows still returns the last cached battery value (seen with an Xbox controller).
  Disconnected → grey icon, no %.

### 3.2 Hator Stellar Pro Wireless (HID)

- Dongle: Telink `VID_248A PID_5B4A`, the interface with usage page `0xFF01`.
- Request: `SetFeature 07 89 00 00 00 00 00 00 00` → `GetFeature(report 7, len 8)` →
  `07 89 XX 01 02 03 00 00`, `XX` = battery %.
- The value is voltage-based and jitters ±1–3 % → smooth (median of recent readings, show integer).
- Charging: on cable the mouse also appears as USB `VID_248A PID_5B49` → `charging = True`.
- Present only when the dongle is found. Replaces Hator Hub (to be uninstalled at the end).

### 3.3 Claude usage limits — the fragile one

- Token: Claude Code's OAuth token from `~/.claude/.credentials.json`. **Read only. Never refresh it** —
  refreshing rotates the token and logs Claude Code out. Expired token → "re-open Claude Code" state,
  not a refresh.
- Request: the same one Claude Code's `/usage` makes — 5-hour window and weekly window, % used and
  reset time. The endpoint is internal and undocumented: confirm it on the spot (step 04), keep the
  parsing in one module with a schema version, and degrade to "data unavailable" instead of crashing.
- Poll no more than once a minute.
- No credentials file → no Claude icon (the second PC).

## 4. Install and self-update

**Velopack** over a PyInstaller `--onedir` build:
- `Setup.exe` installs into `%LocalAppData%\JuiceMate` — per-user, no admin, no UAC; creates the Start
  menu shortcut; the app registers its own autostart (HKCU `Run`), toggled from the tray menu.
- On start and every 6 h the app checks for an update, downloads it in the background (delta
  packages), and applies it **on the next start** or from the tray menu item "Restart to update".
  Never restarts under the user on its own.
- `vpk` is a .NET tool — needed only in CI (`windows-latest`), never on the user's PC.
- The app must call `velopack.App().run()` first thing in `main` (install/update hooks).

### 4.1 Where updates are downloaded from — LOCKED (owner, 2026-10-20)

**The repo `Zebaro24/Juice-Mate` is public**, and the app reads updates from its GitHub Releases with
Velopack's GitHub source — no token anywhere, no server.

Why not private: GitHub has no release-only token (a release asset needs `Contents: read`, which
also reads the source), so a token inside the app is the source for everyone who has the app. A
second "releases" repo and a Cloudflare Worker proxy were rejected as extra moving parts.

Consequence: **nothing secret ever goes into the repo** — no tokens, no personal device serials, no
account ids. The Hator protocol and the Claude usage call are public by choice.

## 5. Layout

```
src/juice_mate/
  core/        readings, smoothing, thresholds, icon state — pure, no IO, fully unit-tested
  sources/     bluetooth.py, hator.py, claude.py — one file per source, IO lives here
  tray/        pystray icons, Pillow drawing, menu, toasts
  update/      Velopack wiring, autostart
  app.py       poll loop: sources → core → tray
tests/
```

Layering (checked by `scripts/arch_lint.py`): `core` imports nothing from `sources`, `tray`, `update`
or any IO library; `sources` never import `tray`.

## 6. Icons

One tray icon per reading: the number drawn on a 32×32 image. Red below the threshold (default 20 %),
⚡ mark while charging, grey when disconnected. Tooltip: name, %, state, last update. A toast once when
a device drops below 15 % (not again until it recovers). The Claude icon shows the larger of the two
windows' % used; the tooltip shows both with time to reset.
