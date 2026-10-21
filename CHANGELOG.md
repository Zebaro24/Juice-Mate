# Changelog

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
