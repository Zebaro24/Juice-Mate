"""The panel windows: layered children of the taskbar (docs/architecture.md §4b).

Two strips: batteries and usage just left of the notification area, system sensors at the taskbar's
left end — after the Widgets (weather) button when there is one. A left-aligned taskbar (or Windows
10) keeps its Start button there, so then everything goes into the right strip.

Threading: everything Win32 happens on the panel's own thread, which runs a message loop. Other
threads only call `show()` / `stop()`, which hand data over under a lock and post a message.

**This thread must never block.** A window parented into Explorer's taskbar shares its input queue
with the taskbar; a hang here would freeze the taskbar itself. Sources are polled elsewhere, and the
Widgets button is looked up on a thread of its own (uia.py).
"""

import ctypes
import logging
import threading
import winreg
from collections.abc import Callable
from ctypes import wintypes as w
from dataclasses import dataclass, field

from PIL import Image

from juice_mate.core.card import Card
from juice_mate.core.display import Item
from juice_mate.panel import win32 as api
from juice_mate.panel.hover import Hover
from juice_mate.panel.layered import blit
from juice_mate.panel.menu import MenuEntry, PopupMenu
from juice_mate.panel.render import Span, Theme, premultiplied_bgra, render
from juice_mate.panel.uia import LeftEdge, centred_taskbar

log = logging.getLogger(__name__)

_CLASS = "JuiceMatePanel"
_WM_UPDATE = api.WM_APP + 1
_WATCHDOG_TIMER = 1
_WATCHDOG_MS = 2000
_MARGIN = 8  # gap between a strip and its neighbour (notification area, Widgets button), at 96 DPI


@dataclass
class _Strip:
    """One layered child window of the taskbar, with its own hover areas."""

    hwnd: int | None = None
    spans: list[Span] = field(default_factory=list)
    tracking: bool = False  # asked Windows for WM_MOUSELEAVE


@dataclass(frozen=True)
class _Geometry:
    """Everything the layout depends on: a change re-paints (see the watchdog)."""

    taskbar: tuple[int, int, int, int]
    notify_left: int  # screen x where the notification area starts
    left_free: bool  # the taskbar's left end is not the Start button
    widgets_right: int | None  # screen x where the Widgets button ends
    scale: float
    light: bool


def _light_theme() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return bool(winreg.QueryValueEx(key, "SystemUsesLightTheme")[0])
    except OSError:
        return False


class Panel:
    def __init__(
        self,
        menu: Callable[[], list[MenuEntry | None]],
        on_click: Callable[[str], None] = lambda _key: None,
        card_for: Callable[[str], Card | None] = lambda _key: None,
    ) -> None:
        """`menu` is asked for the entries each time the menu opens, so a checkmark is always current.
        `on_click` gets the key of the item under a left click; `card_for` the key under the mouse,
        for the hover card (hover.py).

        All three run on the panel thread: they must return at once (set an event, flip a setting,
        start a thread, build a card from what is already in memory).
        """
        self._menu_entries = menu
        self._on_click = on_click
        self._card_for = card_for
        self._hover: Hover | None = None
        self._menus: dict[int, PopupMenu] = {}  # open menu windows by hwnd: their messages go to them
        self._lock = threading.Lock()
        self._right_items: list[Item] = []
        self._left_items: list[Item] = []
        self._attached = threading.Event()
        self._started = threading.Event()
        self._control: int | None = None  # hidden top-level window: messages, menu owner
        self._right = _Strip()  # batteries and usage, by the notification area
        self._left = _Strip()  # system sensors, at the taskbar's left end
        self._widgets = LeftEdge(self._taskbar)
        self._anchor: _Geometry | None = None
        self._light = _light_theme()
        self._proc = api.WNDPROC(self._wndproc)  # keep a reference: the callback must outlive the window
        self._taskbar_created = api.user32.RegisterWindowMessageW("TaskbarCreated")
        self._thread = threading.Thread(target=self._run, name="panel", daemon=True)

    # ── called from other threads ──────────────────────────────────────────

    def start(self, timeout: float = 5.0) -> bool:
        """True once the panel sits in the taskbar."""
        self._thread.start()
        return self._attached.wait(timeout)

    def show(self, right: list[Item], left: list[Item] | None = None) -> None:
        """`right` goes by the notification area, `left` to the taskbar's left end — or in front of
        `right` when the left end is taken."""
        with self._lock:
            self._right_items, self._left_items = list(right), list(left or [])
        if self._started.is_set() and self._control:
            api.user32.PostMessageW(self._control, _WM_UPDATE, 0, 0)

    def stop(self) -> None:
        self._widgets.stop()
        if self._control:
            api.user32.PostMessageW(self._control, api.WM_CLOSE, 0, 0)
        self._thread.join(timeout=3)

    # ── the panel thread ───────────────────────────────────────────────────

    def _run(self) -> None:
        api.user32.SetThreadDpiAwarenessContext(api.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        hinst = api.kernel32.GetModuleHandleW(None)
        wc = api.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(api.WNDCLASSEXW)
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.hCursor = api.user32.LoadCursorW(None, ctypes.c_void_p(api.IDC_ARROW))
        wc.lpszClassName = _CLASS
        api.user32.RegisterClassExW(ctypes.byref(wc))
        self._control = api.user32.CreateWindowExW(
            api.WS_EX_TOOLWINDOW, _CLASS, "Juice-Mate", api.WS_POPUP, 0, 0, 0, 0, None, None, hinst, None
        )
        ctypes.WinDLL("comctl32").InitCommonControls()
        api.user32.SetTimer(self._control, _WATCHDOG_TIMER, _WATCHDOG_MS, None)
        self._hover = Hover(self._control, _CLASS, self._card_for)
        self._started.set()
        self._widgets.start()
        self._attach()
        msg = w.MSG()
        while api.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            api.user32.TranslateMessage(ctypes.byref(msg))
            api.user32.DispatchMessageW(ctypes.byref(msg))

    def _taskbar(self) -> int | None:
        found: int | None = api.user32.FindWindowW("Shell_TrayWnd", None)
        return found

    def _attach(self) -> None:
        taskbar = self._taskbar()
        if not taskbar:
            return
        for strip in (self._right, self._left):
            strip.hwnd = self._child(taskbar)
            if not strip.hwnd:
                self._detach()
                return
        self._anchor = None
        self._paint()
        self._attached.set()

    def _child(self, taskbar: int) -> int | None:
        hinst = api.kernel32.GetModuleHandleW(None)
        ex = api.WS_EX_LAYERED | api.WS_EX_TOOLWINDOW | api.WS_EX_NOACTIVATE
        hwnd: int | None = api.user32.CreateWindowExW(
            ex, _CLASS, "Juice-Mate panel", api.WS_POPUP, 0, 0, 1, 1, None, None, hinst, None
        )
        if not hwnd or not api.user32.SetParent(hwnd, taskbar):
            log.warning("could not attach to the taskbar (error %s)", ctypes.get_last_error())
            if hwnd:
                api.user32.DestroyWindow(hwnd)
            return None
        style = api.user32.GetWindowLongPtrW(hwnd, api.GWL_STYLE)
        api.user32.SetWindowLongPtrW(hwnd, api.GWL_STYLE, (style & ~api.WS_POPUP) | api.WS_CHILD | api.WS_CLIPSIBLINGS)
        return hwnd

    def _detach(self) -> None:
        for strip in (self._right, self._left):
            if strip.hwnd and api.user32.IsWindow(strip.hwnd):
                api.user32.DestroyWindow(strip.hwnd)
            strip.hwnd = None

    def _geometry(self, taskbar: int) -> _Geometry:
        notify = api.user32.FindWindowExW(taskbar, None, "TrayNotifyWnd", None)
        tb = api.rect(taskbar)
        left_free = centred_taskbar()
        return _Geometry(
            taskbar=tb,
            notify_left=api.rect(notify)[0] if notify else tb[2],
            left_free=left_free,
            widgets_right=self._widgets.value if left_free else None,
            scale=(api.user32.GetDpiForWindow(taskbar) or 96) / 96,
            light=self._light,
        )

    def _paint(self) -> None:
        """Re-render both strips and put them in place."""
        taskbar = self._taskbar()
        if not taskbar or not self._right.hwnd or not self._left.hwnd:
            return
        g = self._geometry(taskbar)
        height = g.taskbar[3] - g.taskbar[1]
        margin = round(_MARGIN * g.scale)
        with self._lock:
            right_items, left_items = list(self._right_items), list(self._left_items)
        if not g.left_free:
            right_items, left_items = left_items + right_items, []
        theme = Theme.for_taskbar(self._light)

        image, spans = render(right_items, height, theme, g.scale)
        width = image.width if right_items else 1
        self._place(self._right, g.notify_left - g.taskbar[0] - width - margin, width, height, image, spans)

        image, spans = render(left_items, height, theme, g.scale)
        width = image.width if left_items else 1
        start = g.widgets_right - g.taskbar[0] + margin if g.widgets_right is not None else margin
        self._place(self._left, start, width, height, image, spans)
        self._anchor = g
        if self._hover is not None:
            self._hover.refresh()

    def _place(self, strip: _Strip, x: int, width: int, height: int, image: Image.Image, spans: list[Span]) -> None:
        if not strip.hwnd:
            return
        api.user32.SetWindowPos(strip.hwnd, api.HWND_TOP, x, 0, width, height, api.SWP_NOACTIVATE | api.SWP_SHOWWINDOW)
        blit(strip.hwnd, image.width, height, premultiplied_bgra(image))
        strip.spans = spans

    def _watchdog(self) -> None:
        """Explorer restarted, the taskbar moved or resized, the theme flipped, the Widgets button came,
        went or widened → re-attach or re-layout."""
        taskbar = self._taskbar()
        lost = any(
            not strip.hwnd or not api.user32.IsWindow(strip.hwnd) or api.user32.GetParent(strip.hwnd) != taskbar
            for strip in (self._right, self._left)
        )
        if lost:
            self._detach()
            if taskbar:
                self._attach()
            return
        self._light = _light_theme()
        if taskbar and self._anchor != self._geometry(taskbar):
            self._paint()

    def _menu(self) -> None:
        """Juice-Mate's own menu (menu.py), above the cursor, kept between the taskbar's ends."""
        for menu in list(self._menus.values()):
            if menu.parent is None:
                menu.close()
        point = w.POINT()
        api.user32.GetCursorPos(ctypes.byref(point))
        taskbar = self._anchor.taskbar if self._anchor else (0, point.y, point.x + 1, point.y)
        scale = self._anchor.scale if self._anchor else 1.0
        bounds = (taskbar[0], 0, taskbar[2], taskbar[1])  # the screen above the taskbar
        if self._hover is not None:
            self._hover.leave()
        PopupMenu(_CLASS, self._menu_entries(), (point.x, point.y), scale, bounds, self._menus)

    @staticmethod
    def _span_at(strip: _Strip, lparam: int) -> Span | None:
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        return next((s for s in strip.spans if s.left <= x < s.right and s.top <= y < s.bottom), None)

    def _click(self, strip: _Strip, lparam: int) -> None:
        span = self._span_at(strip, lparam)
        if span is not None:
            self._on_click(span.key)

    def _mouse(self, strip: _Strip, lparam: int) -> None:
        """Over a strip: ask for WM_MOUSELEAVE once, and tell the card which item is under the mouse."""
        if not strip.tracking and strip.hwnd:
            track = api.TRACKMOUSEEVENT(ctypes.sizeof(api.TRACKMOUSEEVENT), api.TME_LEAVE, strip.hwnd, 0)
            strip.tracking = bool(api.user32.TrackMouseEvent(ctypes.byref(track)))
        if self._hover is None or self._anchor is None or not strip.hwnd:
            return
        span = self._span_at(strip, lparam)
        left = api.rect(strip.hwnd)[0]
        centre = left + (span.left + span.right) // 2 if span else left
        self._hover.point(span.key if span else None, centre, self._anchor.taskbar, self._anchor.scale)

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        try:
            menu = self._menus.get(hwnd)
            if menu is not None and menu.handle(msg, wparam, lparam):
                return 0
            if hwnd == self._control:
                if msg == _WM_UPDATE:
                    self._paint()
                    return 0
                if msg == api.WM_TIMER and wparam == _WATCHDOG_TIMER:
                    self._watchdog()
                    return 0
                if msg == api.WM_TIMER and self._hover is not None and self._hover.timer(wparam):
                    return 0
                if msg == self._taskbar_created:  # Explorer restarted: the old taskbar and our children are gone
                    self._detach()
                    self._attach()
                    return 0
                if msg == api.WM_CLOSE:
                    for open_menu in list(self._menus.values()):
                        if open_menu.parent is None:
                            open_menu.close()
                    if self._hover is not None:
                        self._hover.destroy()
                    self._detach()
                    api.user32.DestroyWindow(hwnd)
                    return 0
                if msg == api.WM_DESTROY:
                    api.user32.PostQuitMessage(0)
                    return 0
            elif hwnd and hwnd in (self._right.hwnd, self._left.hwnd):
                strip = self._right if hwnd == self._right.hwnd else self._left
                if msg == api.WM_RBUTTONUP:
                    self._menu()
                    return 0
                if msg == api.WM_LBUTTONUP:
                    self._click(strip, lparam)
                    return 0
                if msg == api.WM_MOUSEMOVE:
                    self._mouse(strip, lparam)
                    return 0
                if msg == api.WM_MOUSELEAVE:
                    strip.tracking = False
                    if self._hover is not None:
                        self._hover.leave()
                    return 0
                if msg == api.WM_DESTROY:
                    strip.hwnd = None
                    return 0
        except Exception:  # an exception must not cross back into Windows' message dispatch
            log.exception("panel message %#x", msg)
        result: int = api.user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        return result
