"""The hover card: what an item is, its story and its chart, above the item (docs/architecture.md §6b).

It replaces the tooltip, which blinked out every time the panel repainted. Lives on the panel thread
(window.py drives it from its messages) and never blocks it: the card is drawn from data already in
memory, in a few milliseconds.

Motion: after a short rest on an item the card rises a few pixels while it fades in; moving to the
next item swaps the content in place; leaving fades it out. While it is open it is redrawn with
every panel update, in place — nothing blinks.
"""

import logging
from collections.abc import Callable

from juice_mate.core.card import Card
from juice_mate.panel import card as drawing
from juice_mate.panel import win32 as api
from juice_mate.panel.layered import blit
from juice_mate.panel.render import premultiplied_bgra

log = logging.getLogger(__name__)

SHOW_TIMER, HIDE_TIMER, ANIMATE_TIMER = 11, 12, 13
SHOW_DELAY_MS = 320  # a rest, not a pass: sweeping across the panel must not flash cards
HIDE_DELAY_MS = 140
FRAME_MS = 15
FADE_IN, FADE_OUT = 9, 6  # frames
RISE = 8  # pixels at 96 DPI the card travels while it fades in
GAP = 10  # between the card and the taskbar, at 96 DPI


class Hover:
    def __init__(self, control: int, window_class: str, card_for: Callable[[str], Card | None]) -> None:
        self._control = control  # the window whose timers drive the card
        self._class = window_class
        self._card_for = card_for
        self._hwnd: int | None = None
        self._key: str | None = None
        self._anchor: tuple[int, int, int, int, float] | None = None  # item centre x, taskbar l/t/r, scale
        self._frame = 0
        self._direction = 0  # +1 fading in, -1 fading out, 0 still
        self._visible = False
        self._image: tuple[int, int, bytes, int, int] | None = None  # width, height, pixels, x, y

    # ── from window.py's messages ─────────────────────────────────────────

    def point(self, key: str | None, centre_x: int, taskbar: tuple[int, int, int, int], scale: float) -> None:
        """The mouse is over `key` (None: over the panel but between items)."""
        api.user32.KillTimer(self._control, HIDE_TIMER)
        if key is None:
            self.leave()
            return
        anchor = (centre_x, taskbar[0], taskbar[1], taskbar[2], scale)
        if key == self._key and self._visible and self._direction >= 0:
            return
        self._key, self._anchor = key, anchor
        if self._visible:
            self._draw(alpha=255, rise=0)  # already open: swap the content in place
            self._direction = 0
        else:
            api.user32.SetTimer(self._control, SHOW_TIMER, SHOW_DELAY_MS, None)

    def leave(self) -> None:
        api.user32.KillTimer(self._control, SHOW_TIMER)
        api.user32.SetTimer(self._control, HIDE_TIMER, HIDE_DELAY_MS, None)

    def refresh(self) -> None:
        """New readings: redraw the open card where it is."""
        if self._visible and self._direction == 0:
            self._draw(alpha=255, rise=0)

    def timer(self, which: int) -> bool:
        """True when the timer was the card's."""
        if which == SHOW_TIMER:
            api.user32.KillTimer(self._control, SHOW_TIMER)
            self._start(+1)
        elif which == HIDE_TIMER:
            api.user32.KillTimer(self._control, HIDE_TIMER)
            self._key = None
            if self._visible:
                self._start(-1)
        elif which == ANIMATE_TIMER:
            self._step()
        else:
            return False
        return True

    def destroy(self) -> None:
        for timer in (SHOW_TIMER, HIDE_TIMER, ANIMATE_TIMER):
            api.user32.KillTimer(self._control, timer)
        if self._hwnd:
            api.user32.DestroyWindow(self._hwnd)
            self._hwnd = None
        self._visible = False

    # ── drawing and motion ────────────────────────────────────────────────

    def _window(self) -> int | None:
        if self._hwnd and api.user32.IsWindow(self._hwnd):
            return self._hwnd
        ex = api.WS_EX_LAYERED | api.WS_EX_TOOLWINDOW | api.WS_EX_TOPMOST | api.WS_EX_NOACTIVATE | api.WS_EX_TRANSPARENT
        hinst = api.kernel32.GetModuleHandleW(None)
        self._hwnd = api.user32.CreateWindowExW(
            ex, self._class, "Juice-Mate card", api.WS_POPUP, 0, 0, 1, 1, None, None, hinst, None
        )
        return self._hwnd

    def _start(self, direction: int) -> None:
        if direction > 0 and not self._render():
            return
        self._direction = direction
        self._frame = 0
        api.user32.SetTimer(self._control, ANIMATE_TIMER, FRAME_MS, None)

    def _step(self) -> None:
        frames = FADE_IN if self._direction > 0 else FADE_OUT
        self._frame += 1
        t = min(self._frame / frames, 1.0)
        eased = 1 - (1 - t) ** 3  # ease-out: quick start, soft landing
        if self._direction > 0:
            self._show(alpha=round(255 * eased), rise=1 - eased)
        elif self._direction < 0:
            self._show(alpha=round(255 * (1 - eased)), rise=eased * 0.5)
        if t >= 1.0:
            api.user32.KillTimer(self._control, ANIMATE_TIMER)
            if self._direction < 0 and self._hwnd:
                api.user32.ShowWindow(self._hwnd, api.SW_HIDE)
                self._visible = False
            self._direction = 0

    def _render(self) -> bool:
        """Draw the card for the current key; False when there is nothing to show."""
        if self._key is None or self._anchor is None:
            return False
        try:
            card = self._card_for(self._key)
        except Exception:  # a card is never worth the panel
            log.exception("hover card for %s", self._key)
            return False
        if card is None:
            return False
        centre, tb_left, tb_top, tb_right, scale = self._anchor
        image = drawing.draw(card, scale)
        margin = round(drawing.SHADOW * scale)
        x = centre - image.width // 2
        x = max(tb_left - margin, min(x, tb_right - image.width + margin))
        y = tb_top - image.height + margin - round(GAP * scale)
        self._image = (image.width, image.height, premultiplied_bgra(image), x, y)
        return True

    def _draw(self, alpha: int, rise: float) -> None:
        if self._render():
            self._show(alpha, rise)

    def _show(self, alpha: int, rise: float) -> None:
        hwnd = self._window()
        if not hwnd or self._image is None or self._anchor is None:
            return
        width, height, pixels, x, y = self._image
        offset = round(RISE * self._anchor[4] * rise)
        blit(hwnd, width, height, pixels, at=(x, y + offset), alpha=alpha)
        if not self._visible:
            api.user32.ShowWindow(hwnd, api.SW_SHOWNOACTIVATE)
            self._visible = True
