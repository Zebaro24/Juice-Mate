# Changelog

## v0.3.0 — 2026-10-22

Two strips, text that matches the clock, and Claude limits that no longer wait for Claude Code.

- **Sensors at the left end** — network, CPU and GPU now sit at the left of the taskbar, right after
  the weather widget; batteries and Claude stay by the clock. On Windows 10 or a left-aligned
  taskbar everything stays by the clock.
- **Text like the clock's** — numbers at the clock's size and density, crisp instead of blurry; the
  two rows sit a little further apart so the icons no longer touch. The Claude ✳ is bolder.
- **Claude without opening Claude Code** — when the login's token has expired, Juice-Mate runs Claude
  Code once, invisibly, and the numbers come back on their own; the login is never touched.
- **Keep the 5-hour window running** (menu checkbox, off by default) — starts a new window whenever
  the last one has ended, and tells you the day's two biggest tech stories as a notification.
  **Ask Claude now** in the menu does it on demand. Each run costs a fraction of a percent.
- **Claude % matches `/usage`** — rounded down like Claude Code (it said 2 % where the panel said 3 %).
- **Red when the pace runs out** — a Claude window turns red when it will run out before it resets.
- **A logo** — the app, its installer and its shortcut get their own icon.

## v0.2.0 — 2026-10-21

TrafficMonitor's job, without its flagged driver, plus a forecast for the Claude limits.

- **System monitor on the panel** — upload/download speed, CPU and GPU load, refreshed every two
  seconds; GPU temperature, memory and disk on request. Right-click → **Show** to pick what is shown;
  the choice is remembered. No kernel driver, so nothing for an antivirus to flag.
- **Claude pace** — the tooltip says when you will hit a limit at your current pace, if that comes
  before the reset, and one notification warns you. When a nearly spent window resets, a
  notification says the limit is back.
- **Click to open** — the Claude items open your usage page, devices open Bluetooth settings,
  sensors open Task Manager.
- **Steadier numbers** — the layout matches the taskbar clock: same rows, numbers of its size,
  right-aligned so they do not jump; the 5h / 7d labels at full size.
- A Claude rate limit no longer hides the numbers: the last ones stay, marked with their time.

## v0.1.0 — 2026-10-21

The first release: Juice-Mate puts your devices' charge and your Claude limits on the taskbar itself.

- **On the taskbar, next to the clock** — two rows in the style of Windows' own icons: a glyph and a
  number per item. Hover for details, right-click for the menu.
- **Bluetooth devices** — any paired keyboard, mouse, headset, game controller or phone that reports
  its battery; only connected ones are shown. The kind (and its icon) is recognised automatically.
- **Hator Stellar Pro Wireless** mouse through its USB dongle, with a charging mark on the cable.
- **Claude usage** — the 5-hour and the weekly window, % used, red from 80 %, time to reset in the
  tooltip. Needs Claude Code signed in on this PC; nothing is shown otherwise.
- **Low-battery notification** once a device drops below 15 %.
- **Start with Windows** (on after install, toggle in the menu) and **self-update** from GitHub:
  updates download in the background and apply on the next start, or at once from the menu.
