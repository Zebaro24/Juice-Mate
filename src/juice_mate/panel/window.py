"""The panel window: a layered child of the taskbar (docs/architecture.md §4b).

Threading: everything Win32 happens on the panel's own thread, which runs a message loop. Other
threads only call `show()` / `stop()`, which hand data over under a lock and post a message.

**This thread must never block.** A window parented into Explorer's taskbar shares its input queue
with the taskbar; a hang here would freeze the taskbar itself. Sources are polled elsewhere.
"""

import ctypes
import logging
import threading
import winreg
from collections.abc import Callable
from ctypes import wintypes as w
from dataclasses import dataclass

from juice_mate.core.display import Item
from juice_mate.panel import win32 as api
from juice_mate.panel.render import Span, Theme, premultiplied_bgra, render

log = logging.getLogger(__name__)

_CLASS = "JuiceMatePanel"
_WM_UPDATE = api.WM_APP + 1
_WATCHDOG_TIMER = 1
_WATCHDOG_MS = 2000
_MARGIN = 8  # gap between the panel and the notification area, at 96 DPI


@dataclass(frozen=True)
class MenuEntry:
    """One right-click menu line; `None` in the list is a separator."""

    label: str
    action: Callable[[], None]
    checked: bool = False


def _light_theme() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return bool(winreg.QueryValueEx(key, "SystemUsesLightTheme")[0])
    except OSError:
        return False


class Panel:
    def __init__(self, menu: Callable[[], list[MenuEntry | None]]) -> None:
        """`menu` is asked for the entries each time the menu opens, so a checkmark is always current.

        The actions run on the panel thread: they must return at once (set an event, flip a setting).
        """
        self._menu_entries = menu
        self._lock = threading.Lock()
        self._items: list[Item] = []
        self._attached = threading.Event()
        self._started = threading.Event()
        self._control: int | None = None  # hidden top-level window: messages, menu owner
        self._panel: int | None = None  # the child of the taskbar
        self._tooltip: int | None = None
        self._tools = 0
        self._spans: list[Span] = []
        self._anchor: tuple[object, ...] = ()
        self._light = _light_theme()
        self._proc = api.WNDPROC(self._wndproc)  # keep a reference: the callback must outlive the window
        self._taskbar_created = api.user32.RegisterWindowMessageW("TaskbarCreated")
        self._thread = threading.Thread(target=self._run, name="panel", daemon=True)

    # ── called from other threads ──────────────────────────────────────────

    def start(self, timeout: float = 5.0) -> bool:
        """True once the panel sits in the taskbar."""
        self._thread.start()
        return self._attached.wait(timeout)

    def show(self, items: list[Item]) -> None:
        with self._lock:
            self._items = list(items)
        if self._started.is_set() and self._control:
            api.user32.PostMessageW(self._control, _WM_UPDATE, 0, 0)

    def stop(self) -> None:
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
        hinst = api.kernel32.GetModuleHandleW(None)
        ex = api.WS_EX_LAYERED | api.WS_EX_TOOLWINDOW | api.WS_EX_NOACTIVATE
        panel = api.user32.CreateWindowExW(
            ex, _CLASS, "Juice-Mate panel", api.WS_POPUP, 0, 0, 1, 1, None, None, hinst, None
        )
        if not panel or not api.user32.SetParent(panel, taskbar):
            log.warning("could not attach to the taskbar (error %s)", ctypes.get_last_error())
            if panel:
                api.user32.DestroyWindow(panel)
            return
        style = api.user32.GetWindowLongPtrW(panel, api.GWL_STYLE)
        api.user32.SetWindowLongPtrW(panel, api.GWL_STYLE, (style & ~api.WS_POPUP) | api.WS_CHILD | api.WS_CLIPSIBLINGS)
        self._panel = panel
        self._make_tooltip()
        self._anchor = ()
        self._paint()
        self._attached.set()

    def _make_tooltip(self) -> None:
        if self._tooltip:
            api.user32.DestroyWindow(self._tooltip)
        self._tooltip = api.user32.CreateWindowExW(
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
        self._tools = 0

    def _set_tools(self, spans: list[Span], height: int) -> None:
        if not self._tooltip or not self._panel:
            return
        info = api.TOOLINFOW()
        info.cbSize = ctypes.sizeof(api.TOOLINFOW)
        info.hwnd = self._panel
        for i in range(self._tools):
            info.uId = i
            api.user32.SendMessageW(self._tooltip, api.TTM_DELTOOLW, 0, ctypes.addressof(info))
        texts = []
        for i, span in enumerate(spans):
            info.uFlags = api.TTF_SUBCLASS
            info.uId = i
            info.rect = w.RECT(span.left, span.top, span.right, span.bottom)
            text = ctypes.create_unicode_buffer(span.tooltip)
            texts.append(text)  # the tooltip copies the text during the call
            info.lpszText = ctypes.cast(text, w.LPWSTR)
            api.user32.SendMessageW(self._tooltip, api.TTM_ADDTOOLW, 0, ctypes.addressof(info))
        self._tools = len(spans)

    def _paint(self) -> None:
        """Re-render and put the panel just left of the notification area."""
        taskbar = self._taskbar()
        panel = self._panel
        if not taskbar or not panel:
            return
        notify = api.user32.FindWindowExW(taskbar, None, "TrayNotifyWnd", None)
        tb = api.rect(taskbar)
        right = api.rect(notify)[0] if notify else tb[2]
        height = tb[3] - tb[1]
        scale = (api.user32.GetDpiForWindow(taskbar) or 96) / 96
        with self._lock:
            items = list(self._items)
        image, spans = render(items, height, Theme.for_taskbar(self._light), scale)
        width = image.width if items else 1
        x = right - tb[0] - width - round(_MARGIN * scale)
        api.user32.SetWindowPos(panel, api.HWND_TOP, x, 0, width, height, api.SWP_NOACTIVATE | api.SWP_SHOWWINDOW)
        self._blit(panel, image.width, height, premultiplied_bgra(image))
        self._spans = spans
        self._set_tools(spans, height)
        self._anchor = (tb, right, scale, self._light)

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
        """Explorer restarted, the taskbar moved or resized, the theme flipped → re-attach or re-layout."""
        taskbar = self._taskbar()
        if self._panel and (not api.user32.IsWindow(self._panel) or api.user32.GetParent(self._panel) != taskbar):
            self._panel = None
        if not self._panel:
            if taskbar:
                self._attach()
            return
        self._light = _light_theme()
        notify = api.user32.FindWindowExW(taskbar, None, "TrayNotifyWnd", None)
        right = api.rect(notify)[0] if notify else api.rect(taskbar)[2]
        scale = (api.user32.GetDpiForWindow(taskbar) or 96) / 96
        if self._anchor != (api.rect(taskbar), right, scale, self._light):
            self._paint()

    def _menu(self) -> None:
        entries = self._menu_entries()
        menu = api.user32.CreatePopupMenu()
        for command_id, entry in enumerate(entries, start=1):
            if entry is None:
                api.user32.AppendMenuW(menu, api.MF_SEPARATOR, 0, None)
            else:
                flags = api.MF_STRING | (api.MF_CHECKED if entry.checked else 0)
                api.user32.AppendMenuW(menu, flags, command_id, entry.label)
        point = w.POINT()
        api.user32.GetCursorPos(ctypes.byref(point))
        api.user32.SetForegroundWindow(self._control)
        flags = api.TPM_RETURNCMD | api.TPM_RIGHTBUTTON | api.TPM_BOTTOMALIGN
        command = api.user32.TrackPopupMenu(menu, flags, point.x, point.y, 0, self._control, None)
        api.user32.DestroyMenu(menu)
        if 1 <= command <= len(entries):
            chosen = entries[command - 1]
            if chosen is not None:
                chosen.action()

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        try:
            if hwnd == self._control:
                if msg == _WM_UPDATE:
                    self._paint()
                    return 0
                if msg == api.WM_TIMER and wparam == _WATCHDOG_TIMER:
                    self._watchdog()
                    return 0
                if msg == self._taskbar_created:  # Explorer restarted: the old taskbar and our child are gone
                    self._panel = None
                    self._attach()
                    return 0
                if msg == api.WM_CLOSE:
                    if self._panel:
                        api.user32.DestroyWindow(self._panel)
                        self._panel = None
                    api.user32.DestroyWindow(hwnd)
                    return 0
                if msg == api.WM_DESTROY:
                    api.user32.PostQuitMessage(0)
                    return 0
            elif hwnd == self._panel:
                if msg == api.WM_RBUTTONUP:
                    self._menu()
                    return 0
                if msg == api.WM_DESTROY:
                    self._panel = None
                    return 0
        except Exception:  # an exception must not cross back into Windows' message dispatch
            log.exception("panel message %#x", msg)
        result: int = api.user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        return result
