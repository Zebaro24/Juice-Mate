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

from juice_mate.core.display import Item
from juice_mate.panel import win32 as api
from juice_mate.panel.render import Span, Theme, premultiplied_bgra, render
from juice_mate.panel.uia import LeftEdge, centred_taskbar

log = logging.getLogger(__name__)

_CLASS = "JuiceMatePanel"
_WM_UPDATE = api.WM_APP + 1
_WATCHDOG_TIMER = 1
_WATCHDOG_MS = 2000
_MARGIN = 8  # gap between a strip and its neighbour (notification area, Widgets button), at 96 DPI


@dataclass(frozen=True)
class MenuEntry:
    """One right-click menu line; `None` in the list is a separator. With `children` it is a submenu."""

    label: str
    action: Callable[[], None] | None = None
    checked: bool = False
    children: "list[MenuEntry | None] | None" = None


@dataclass
class _Strip:
    """One layered child window of the taskbar, with its own hover areas and tooltip."""

    hwnd: int | None = None
    tooltip: int | None = None
    tools: int = 0
    spans: list[Span] = field(default_factory=list)


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
        self, menu: Callable[[], list[MenuEntry | None]], on_click: Callable[[str], None] = lambda _key: None
    ) -> None:
        """`menu` is asked for the entries each time the menu opens, so a checkmark is always current.
        `on_click` gets the key of the item under a left click.

        Both run on the panel thread: they must return at once (set an event, flip a setting, start a
        thread).
        """
        self._menu_entries = menu
        self._on_click = on_click
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
            strip.tooltip = self._make_tooltip(strip.tooltip)
            strip.tools = 0
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

    def _make_tooltip(self, old: int | None) -> int | None:
        if old:
            api.user32.DestroyWindow(old)
        tooltip: int | None = api.user32.CreateWindowExW(
            api.WS_EX_TOPMOST,
            api.TOOLTIPS_CLASS,
            None,
            api.WS_POPUP | api.TTS_NOPREFIX | api.TTS_ALWAYSTIP,
            api.CW_USEDEFAULT,
            api.CW_USEDEFAULT,
            api.CW_USEDEFAULT,
            api.CW_USEDEFAULT,
            self._control,
            None,
            api.kernel32.GetModuleHandleW(None),
            None,
        )
        return tooltip

    def _set_tools(self, strip: _Strip, spans: list[Span]) -> None:
        if not strip.tooltip or not strip.hwnd:
            return
        info = api.TOOLINFOW()
        info.cbSize = ctypes.sizeof(api.TOOLINFOW)
        info.hwnd = strip.hwnd
        for i in range(strip.tools):
            info.uId = i
            api.user32.SendMessageW(strip.tooltip, api.TTM_DELTOOLW, 0, ctypes.addressof(info))
        texts = []
        for i, span in enumerate(spans):
            info.uFlags = api.TTF_SUBCLASS
            info.uId = i
            info.rect = w.RECT(span.left, span.top, span.right, span.bottom)
            text = ctypes.create_unicode_buffer(span.tooltip)
            texts.append(text)  # the tooltip copies the text during the call
            info.lpszText = ctypes.cast(text, w.LPWSTR)
            api.user32.SendMessageW(strip.tooltip, api.TTM_ADDTOOLW, 0, ctypes.addressof(info))
        strip.tools = len(spans)
        strip.spans = spans

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

    def _place(self, strip: _Strip, x: int, width: int, height: int, image: Image.Image, spans: list[Span]) -> None:
        if not strip.hwnd:
            return
        api.user32.SetWindowPos(strip.hwnd, api.HWND_TOP, x, 0, width, height, api.SWP_NOACTIVATE | api.SWP_SHOWWINDOW)
        self._blit(strip.hwnd, image.width, height, premultiplied_bgra(image))
        self._set_tools(strip, spans)

    def _blit(self, hwnd: int, width: int, height: int, pixels: bytes) -> None:
        header = api.BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(api.BITMAPINFOHEADER)
        header.biWidth, header.biHeight = width, -height  # negative: top-down rows
        header.biPlanes, header.biBitCount = 1, 32
        bits = ctypes.c_void_p()
        screen = api.user32.GetDC(None)
        memory = api.gdi32.CreateCompatibleDC(screen)
        bitmap = api.gdi32.CreateDIBSection(memory, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        try:
            if not bitmap or not bits.value:
                return
            ctypes.memmove(bits.value, pixels, len(pixels))
            old = api.gdi32.SelectObject(memory, bitmap)
            size = w.SIZE(width, height)
            origin = w.POINT(0, 0)
            blend = api.BLENDFUNCTION(api.AC_SRC_OVER, 0, 255, api.AC_SRC_ALPHA)
            ok = api.user32.UpdateLayeredWindow(
                hwnd,
                screen,
                None,
                ctypes.byref(size),
                memory,
                ctypes.byref(origin),
                0,
                ctypes.byref(blend),
                api.ULW_ALPHA,
            )
            if not ok:
                log.warning("UpdateLayeredWindow failed (error %s)", ctypes.get_last_error())
            api.gdi32.SelectObject(memory, old)
        finally:
            if bitmap:
                api.gdi32.DeleteObject(bitmap)
            api.gdi32.DeleteDC(memory)
            api.user32.ReleaseDC(None, screen)

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

    def _build(self, entries: list[MenuEntry | None], actions: list[Callable[[], None]]) -> int:
        """A Win32 menu for `entries`; every action gets the command id `index + 1` in `actions`."""
        menu: int = api.user32.CreatePopupMenu()
        for entry in entries:
            if entry is None:
                api.user32.AppendMenuW(menu, api.MF_SEPARATOR, 0, None)
            elif entry.children is not None:
                submenu = self._build(entry.children, actions)
                api.user32.AppendMenuW(menu, api.MF_STRING | api.MF_POPUP, submenu, entry.label)
            else:
                flags = api.MF_STRING | (api.MF_CHECKED if entry.checked else 0)
                actions.append(entry.action or (lambda: None))
                api.user32.AppendMenuW(menu, flags, len(actions), entry.label)
        return menu

    def _menu(self) -> None:
        actions: list[Callable[[], None]] = []
        menu = self._build(self._menu_entries(), actions)
        point = w.POINT()
        api.user32.GetCursorPos(ctypes.byref(point))
        api.user32.SetForegroundWindow(self._control)
        flags = api.TPM_RETURNCMD | api.TPM_RIGHTBUTTON | api.TPM_BOTTOMALIGN
        command = api.user32.TrackPopupMenu(menu, flags, point.x, point.y, 0, self._control, None)
        api.user32.DestroyMenu(menu)  # destroys the submenus with it
        if 1 <= command <= len(actions):
            actions[command - 1]()

    def _click(self, strip: _Strip, lparam: int) -> None:
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        for span in strip.spans:
            if span.left <= x < span.right and span.top <= y < span.bottom:
                self._on_click(span.key)
                return

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        try:
            if hwnd == self._control:
                if msg == _WM_UPDATE:
                    self._paint()
                    return 0
                if msg == api.WM_TIMER and wparam == _WATCHDOG_TIMER:
                    self._watchdog()
                    return 0
                if msg == self._taskbar_created:  # Explorer restarted: the old taskbar and our children are gone
                    self._detach()
                    self._attach()
                    return 0
                if msg == api.WM_CLOSE:
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
                if msg == api.WM_DESTROY:
                    strip.hwnd = None
                    return 0
        except Exception:  # an exception must not cross back into Windows' message dispatch
            log.exception("panel message %#x", msg)
        result: int = api.user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        return result
