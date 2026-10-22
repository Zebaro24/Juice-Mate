"""The right-click menu, in Juice-Mate's own look (docs/architecture.md §6c).

Windows' own popup menu cannot be restyled, so this one is drawn like the hover card: a layered
window with a Pillow image, redrawn on every hover change. Lives on the panel thread and is not
modal — the panel keeps updating while it is open.

- Switches instead of check marks; clicking one flips it with a short slide and leaves the menu
  open, so several sensors can be switched in one go.
- Submenus slide out to the side on hover; the parent keeps the keyboard focus.
- Closes when it loses focus (a click anywhere else), on Esc, or after a plain item is picked.
- Up / Down / Enter / Right / Left work as in any menu.
"""

import ctypes
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace

from PIL import Image, ImageDraw, ImageFilter

from juice_mate.panel import win32 as api
from juice_mate.panel.card import DIM, LINE, LINE_2, MIST, PAPER, PULSE, RAISED, SIGNAL, SURFACE, _font
from juice_mate.panel.layered import blit
from juice_mate.panel.render import _glyph_mask, premultiplied_bgra

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MenuEntry:
    """One menu line; `None` in a list is a separator. With `children` it opens a submenu.
    `checked` is None for a plain item, True/False for a switch. `style`: "", "accent" or "danger"."""

    label: str
    action: Callable[[], None] | None = None
    checked: bool | None = None
    children: "list[MenuEntry | None] | None" = None
    icon: str = ""  # a Segoe Fluent Icons code point
    style: str = ""


WIDTH = 252  # at 96 DPI
ROW = 34
SEP = 9
PAD = 6
HEAD = 26
SHADOW = 12
SS = 2
FADE_FRAMES, SLIDE_FRAMES, FRAME_MS = 8, 7, 15
ANIM_TIMER, SUBMENU_TIMER = 1, 2
SUBMENU_DELAY_MS = 220
WM_ACTIVATE, WA_INACTIVE = 0x0006, 0
WM_KEYDOWN = 0x0100
VK_RETURN, VK_ESCAPE, VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN = 0x0D, 0x1B, 0x25, 0x26, 0x27, 0x28
CHEVRON = chr(0xE76C)


def _layout(entries: list[MenuEntry | None], header: bool) -> tuple[list[tuple[int, int]], int]:
    """(top, bottom) of every line at 96 DPI inside the card, and the card's height."""
    y = PAD + (HEAD if header else 0)
    rows = []
    for entry in entries:
        height = SEP if entry is None else ROW
        rows.append((y, y + height))
        y += height
    return rows, y + PAD


def draw(
    entries: list[MenuEntry | None], highlight: int | None, scale: float, header: bool, knobs: dict[int, float]
) -> Image.Image:
    """The menu's image, its shadow included. `knobs`: a switch's knob position 0..1 while it slides."""
    k = scale * SS
    rows, height = _layout(entries, header)
    w, h = round((WIDTH + 2 * SHADOW) * scale), round((height + 2 * SHADOW) * scale)
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))

    def px(v: float) -> int:
        return round(v * k)

    left, top = px(SHADOW), px(SHADOW)
    right, bottom = w * SS - px(SHADOW), h * SS - px(SHADOW)
    shadow = Image.new("L", big.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((left, top + px(3), right, bottom + px(3)), radius=px(10), fill=140)
    big.paste((0, 0, 0, 255), (0, 0), shadow.filter(ImageFilter.GaussianBlur(px(8))))
    canvas = ImageDraw.Draw(big)
    canvas.rounded_rectangle((left, top, right, bottom), radius=px(10), fill=(*SURFACE, 252), outline=(*LINE_2, 255),
                             width=max(1, px(1)))  # fmt: skip
    if header:
        canvas.text((left + px(16), top + px(PAD + HEAD / 2)), "JUICE-MATE", font=_font("mono", px(10), 500),
                    fill=(*DIM, 255), anchor="lm")  # fmt: skip

    label_font = _font("text", px(13))
    for index, (entry, (y0, y1)) in enumerate(zip(entries, rows, strict=True)):
        if entry is None:
            line_y = top + px((y0 + y1) / 2)
            canvas.line((left + px(12), line_y, right - px(12), line_y), fill=(*LINE, 255), width=max(1, px(1)))
            continue
        row = (left + px(PAD), top + px(y0), right - px(PAD), top + px(y1))
        hot = index == highlight
        tint = PULSE if entry.style == "danger" else SIGNAL
        if hot:
            canvas.rounded_rectangle(row, radius=px(6), fill=(*RAISED, 255))
            bar_top, bar_bottom = (row[1] + row[3]) / 2 - px(7), (row[1] + row[3]) / 2 + px(7)
            canvas.rounded_rectangle((row[0], bar_top, row[0] + px(2.5), bar_bottom), radius=px(1.5), fill=(*tint, 255))
        mid = (row[1] + row[3]) / 2
        text_colour = PULSE if (hot and entry.style == "danger") else SIGNAL if entry.style == "accent" else PAPER
        if entry.icon:
            mask = _glyph_mask(entry.icon, px(14))
            colour = tint if (hot or entry.checked or entry.style) else MIST
            layer = Image.new("RGBA", mask.size, (*colour, 0))
            layer.putalpha(mask)
            big.alpha_composite(layer, (row[0] + px(12) - 2 * SS, round(mid - mask.height / 2)))
        canvas.text((row[0] + px(40), mid), entry.label, font=label_font, fill=(*text_colour, 255), anchor="lm")
        if entry.children is not None:
            mask = _glyph_mask(CHEVRON, px(10))
            layer = Image.new("RGBA", mask.size, (*MIST, 0))
            layer.putalpha(mask)
            big.alpha_composite(layer, (row[2] - px(18), round(mid - mask.height / 2)))
        elif entry.checked is not None:
            _switch(
                canvas,
                (row[2] - px(40), mid - px(8), row[2] - px(10), mid + px(8)),
                knobs.get(index, float(entry.checked)),
                k,
            )
    return big.resize((w, h), Image.Resampling.LANCZOS)


def _switch(canvas: ImageDraw.ImageDraw, box: tuple[float, float, float, float], t: float, k: float) -> None:
    """The settings window's switch, small: `t` 0 = off, 1 = on, in between while it slides."""
    x0, y0, x1, y1 = box

    def mix(a: tuple[int, int, int], b: tuple[int, int, int]) -> tuple[int, int, int]:
        return (round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t), round(a[2] + (b[2] - a[2]) * t))

    track = mix((29, 29, 63), (21, 70, 82))
    canvas.rounded_rectangle(box, radius=(y1 - y0) / 2, fill=(*track, 255), outline=(*mix(LINE_2, (40, 130, 140)), 255),
                             width=max(1, round(k)))  # fmt: skip
    r = (y1 - y0) / 2 - 3 * k
    cx = x0 + (y1 - y0) / 2 + (x1 - x0 - (y1 - y0)) * t
    cy = (y0 + y1) / 2
    canvas.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*mix(MIST, SIGNAL), 255))


class PopupMenu:
    def __init__(
        self,
        window_class: str,
        entries: list[MenuEntry | None],
        at: tuple[int, int],
        scale: float,
        bounds: tuple[int, int, int, int],
        registry: dict[int, "PopupMenu"],
        parent: "PopupMenu | None" = None,
    ) -> None:
        """`at`: where it opens (screen pixels) — the root opens above-right of the cursor, a submenu
        beside its parent's line. `bounds`: the screen area it must stay inside. `registry`: hwnd →
        menu, so window.py can route each window's messages here."""
        self.entries = entries
        self.scale = scale
        self.parent = parent
        self.child: PopupMenu | None = None
        self.registry = registry
        self.header = parent is None
        self.highlight: int | None = None
        self.knobs: dict[int, float] = {}
        self._frame = 0
        self._sliding: tuple[int, float, float, int] | None = None  # index, from, to, first frame
        self._class = window_class
        self._bounds = bounds
        self._tracking = False
        rows, height = _layout(entries, self.header)
        self.rows = rows
        w, h = round((WIDTH + 2 * SHADOW) * scale), round((height + 2 * SHADOW) * scale)
        margin = round(SHADOW * scale)
        x, y = at
        if parent is None:
            x, y = x - margin, y - h + margin  # above the cursor: the taskbar is below it
        else:
            y -= margin
        x = max(bounds[0] - margin, min(x, bounds[2] - w + margin))
        y = max(bounds[1] - margin, min(y, bounds[3] - h + margin))
        self.origin = (x, y)
        self.size = (w, h)
        ex = api.WS_EX_LAYERED | api.WS_EX_TOOLWINDOW | api.WS_EX_TOPMOST
        if parent is not None:
            ex |= api.WS_EX_NOACTIVATE  # the root keeps the focus: losing it closes the whole menu
        hinst = api.kernel32.GetModuleHandleW(None)
        self.hwnd: int = api.user32.CreateWindowExW(ex, window_class, "Juice-Mate menu", api.WS_POPUP, x, y, w, h,
                                                    None, None, hinst, None)  # fmt: skip
        registry[self.hwnd] = self
        self._paint(alpha=0, rise=1.0)
        api.user32.ShowWindow(self.hwnd, api.SW_SHOWNOACTIVATE if parent else 5)  # SW_SHOW
        if parent is None:
            api.user32.SetForegroundWindow(self.hwnd)
        api.user32.SetTimer(self.hwnd, ANIM_TIMER, FRAME_MS, None)

    # ── drawing ────────────────────────────────────────────────────────────

    def _paint(self, alpha: int = 255, rise: float = 0.0) -> None:
        image = draw(self.entries, self.highlight, self.scale, self.header, self.knobs)
        dx = round(-6 * self.scale * rise) if self.parent else 0
        dy = 0 if self.parent else round(8 * self.scale * rise)
        at = (self.origin[0] + dx, self.origin[1] + dy)
        blit(self.hwnd, image.width, image.height, premultiplied_bgra(image), at=at, alpha=alpha)

    def _tick(self) -> None:
        self._frame += 1
        if self._frame <= FADE_FRAMES:
            t = 1 - (1 - self._frame / FADE_FRAMES) ** 3
            self._paint(alpha=round(255 * t), rise=1 - t)
        if self._sliding is not None:
            index, start, end, first = self._sliding
            t = min(1.0, (self._frame - first) / SLIDE_FRAMES)
            self.knobs[index] = start + (end - start) * (1 - (1 - t) ** 3)
            if t >= 1.0:
                self.knobs.pop(index, None)
                self._sliding = None
            self._paint()
        if self._frame > FADE_FRAMES and self._sliding is None:
            api.user32.KillTimer(self.hwnd, ANIM_TIMER)

    # ── lines ──────────────────────────────────────────────────────────────

    def _row_at(self, lparam: int) -> int | None:
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value / self.scale - SHADOW
        x = ctypes.c_short(lparam & 0xFFFF).value / self.scale - SHADOW
        if not 0 <= x <= WIDTH:
            return None
        for index, (top, bottom) in enumerate(self.rows):
            if top <= y < bottom and self.entries[index] is not None:
                return index
        return None

    def _set_highlight(self, index: int | None) -> None:
        if index == self.highlight:
            return
        self.highlight = index
        self._paint()
        api.user32.KillTimer(self.hwnd, SUBMENU_TIMER)
        entry = self.entries[index] if index is not None else None
        if entry is not None and entry.children is not None:
            api.user32.SetTimer(self.hwnd, SUBMENU_TIMER, SUBMENU_DELAY_MS, None)
        elif self.child is not None and index is not None:
            self.child.close()

    def _open_child(self) -> None:
        index = self.highlight
        if index is None:
            return
        entry = self.entries[index]
        if entry is None or entry.children is None:
            return
        if self.child is not None:
            if self.child.entries is entry.children:
                return
            self.child.close()
        top = self.origin[1] + round((SHADOW + self.rows[index][0] - PAD) * self.scale)
        right = self.origin[0] + self.size[0] - round(SHADOW * self.scale * 1.6)
        at = (right, top)
        if right + self.size[0] > self._bounds[2]:  # no room on the right: open to the left
            at = (self.origin[0] - self.size[0] + round(SHADOW * self.scale * 1.6), top)
        self.child = PopupMenu(self._class, entry.children, at, self.scale, self._bounds, self.registry, parent=self)

    def _activate(self, index: int | None) -> None:
        entry = self.entries[index] if index is not None else None
        if entry is None:
            return
        if entry.children is not None:
            self.highlight = index
            self._open_child()
            return
        if entry.checked is not None and index is not None:
            # A switch flips in place, slides, and the menu stays.
            on = not entry.checked
            self.entries = [replace(e, checked=on) if i == index and e else e for i, e in enumerate(self.entries)]
            self._sliding = (index, float(not on), float(on), self._frame)
            self.knobs[index] = float(not on)
            api.user32.SetTimer(self.hwnd, ANIM_TIMER, FRAME_MS, None)
            self._run(entry.action)
            return
        self.root().close()
        self._run(entry.action)

    @staticmethod
    def _run(action: Callable[[], None] | None) -> None:
        if action is None:
            return
        try:
            action()
        except Exception:  # a menu action never takes the panel down
            log.exception("menu action failed")

    def root(self) -> "PopupMenu":
        return self.parent.root() if self.parent else self

    def deepest(self) -> "PopupMenu":
        return self.child.deepest() if self.child else self

    def close(self) -> None:
        if self.child is not None:
            self.child.close()
            self.child = None
        if self.parent is not None and self.parent.child is self:
            self.parent.child = None
        self.registry.pop(self.hwnd, None)
        api.user32.KillTimer(self.hwnd, ANIM_TIMER)
        api.user32.KillTimer(self.hwnd, SUBMENU_TIMER)
        api.user32.DestroyWindow(self.hwnd)

    def _key(self, key: int) -> None:
        menu = self.deepest()
        lines = [i for i, e in enumerate(menu.entries) if e is not None]
        if key == VK_ESCAPE:
            menu.close()  # a submenu first, then the menu itself
        elif key in (VK_DOWN, VK_UP) and lines:
            at = lines.index(menu.highlight) if menu.highlight in lines else (-1 if key == VK_DOWN else 0)
            menu._set_highlight(lines[(at + (1 if key == VK_DOWN else -1)) % len(lines)])
        elif key == VK_RIGHT:
            menu._open_child()
            if menu.child is not None:
                first = next((i for i, e in enumerate(menu.child.entries) if e is not None), None)
                menu.child._set_highlight(first)
        elif key == VK_LEFT and menu.parent is not None:
            menu.close()
        elif key == VK_RETURN:
            menu._activate(menu.highlight)

    # ── messages (routed here by window.py) ──────────────────────────────────

    def handle(self, msg: int, wparam: int, lparam: int) -> bool:
        if msg == api.WM_MOUSEMOVE:
            if not self._tracking:
                track = api.TRACKMOUSEEVENT(ctypes.sizeof(api.TRACKMOUSEEVENT), api.TME_LEAVE, self.hwnd, 0)
                self._tracking = bool(api.user32.TrackMouseEvent(ctypes.byref(track)))
            self._set_highlight(self._row_at(lparam))
            return True
        if msg == api.WM_MOUSELEAVE:
            self._tracking = False
            if self.child is None:
                self._set_highlight(None)
            return True
        if msg == api.WM_LBUTTONUP:
            self._activate(self._row_at(lparam))
            return True
        if msg == api.WM_TIMER:
            if wparam == ANIM_TIMER:
                self._tick()
            elif wparam == SUBMENU_TIMER:
                api.user32.KillTimer(self.hwnd, SUBMENU_TIMER)
                self._open_child()
            return True
        if msg == WM_ACTIVATE and self.parent is None and (wparam & 0xFFFF) == WA_INACTIVE:
            self.close()  # a click anywhere else
            return True
        if msg == WM_KEYDOWN and self.parent is None:
            self._key(wparam)
            return True
        return False
