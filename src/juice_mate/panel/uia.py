"""Where the taskbar's left end is free: the right edge of the Widgets (weather) button.

Windows 11 draws its taskbar in XAML; the Widgets button has no window of its own, only a UI Automation
element (AutomationId "WidgetsButton", seen 2026-10-22). Raw COM through ctypes: one call, no
dependency. The vtable slots are those of UIAutomationClient.h.

UI Automation talks to Explorer across processes and may take a moment, so this runs on its own
thread, never on the panel thread (window.py must not block).
"""

import ctypes
import logging
import sys
import threading
import winreg
from collections.abc import Callable
from ctypes import wintypes as w

log = logging.getLogger(__name__)

_CLSID_CUIAUTOMATION = "{FF48DBA4-60EF-4201-AA87-54103EEF594E}"
_IID_IUIAUTOMATION = "{30CBE57D-D9D0-452A-AB13-7AC5AC4825EE}"
_AUTOMATION_ID_PROPERTY = 30011
_TREE_SCOPE_DESCENDANTS = 4
_VT_BSTR = 8
_CLSCTX_INPROC_SERVER = 1
# vtable slots
_ELEMENT_FROM_HANDLE = 6  # IUIAutomation
_CREATE_PROPERTY_CONDITION = 23  # IUIAutomation
_FIND_FIRST = 5  # IUIAutomationElement
_BOUNDING_RECTANGLE = 43  # IUIAutomationElement::get_CurrentBoundingRectangle
_RELEASE = 2

REFRESH_SECONDS = 5.0
_WINDOWS_11 = 22000  # the first Windows 11 build


class _Variant(ctypes.Structure):
    _fields_ = [
        ("vt", w.USHORT),
        ("r1", w.USHORT),
        ("r2", w.USHORT),
        ("r3", w.USHORT),
        ("value", ctypes.c_void_p),
        ("pad", ctypes.c_void_p),
    ]


def _guid(text: str) -> ctypes.Array[ctypes.c_byte]:
    buffer = (ctypes.c_byte * 16)()
    ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), buffer)
    return buffer


def _call(obj: ctypes.c_void_p, slot: int, *args: object, argtypes: tuple[object, ...] = ()) -> int:
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)  # type: ignore[arg-type]
    result: int = prototype(vtable[slot])(obj, *args)
    return result


def _release(*objects: ctypes.c_void_p) -> None:
    for obj in objects:
        if obj:
            vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[_RELEASE])(obj)


def centred_taskbar() -> bool:
    """Windows 11 centres the app buttons unless TaskbarAl is 0; a left-aligned taskbar has no free left end."""
    if sys.getwindowsversion().build < _WINDOWS_11:
        return False  # Windows 10: Start sits at the left end, and TaskbarAl does not exist
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced")
        return bool(winreg.QueryValueEx(key, "TaskbarAl")[0])
    except OSError:
        return True  # the value is absent until the owner changes it; centred is the default


def widgets_right(taskbar: int) -> int | None:
    """The Widgets button's right edge in screen pixels, or None when there is none (switched off,
    Windows 10). Raises OSError when UI Automation itself fails."""
    automation, element, condition, found = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    bstr = ctypes.windll.oleaut32.SysAllocString
    bstr.restype = ctypes.c_void_p
    name = bstr(ctypes.c_wchar_p("WidgetsButton"))
    try:
        ctypes.oledll.ole32.CoCreateInstance(
            _guid(_CLSID_CUIAUTOMATION),
            None,
            _CLSCTX_INPROC_SERVER,
            _guid(_IID_IUIAUTOMATION),
            ctypes.byref(automation),
        )
        _call(
            automation, _ELEMENT_FROM_HANDLE, w.HWND(taskbar), ctypes.byref(element), argtypes=(w.HWND, ctypes.c_void_p)
        )
        value = _Variant(vt=_VT_BSTR, value=name)
        _call(
            automation,
            _CREATE_PROPERTY_CONDITION,
            _AUTOMATION_ID_PROPERTY,
            ctypes.byref(value),  # a VARIANT larger than 8 bytes goes by reference in the x64 ABI
            ctypes.byref(condition),
            argtypes=(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p),
        )
        _call(
            element,
            _FIND_FIRST,
            _TREE_SCOPE_DESCENDANTS,
            condition,
            ctypes.byref(found),
            argtypes=(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p),
        )
        if not found:
            return None
        rect = w.RECT()
        _call(found, _BOUNDING_RECTANGLE, ctypes.byref(rect), argtypes=(ctypes.c_void_p,))
        return rect.right if rect.right > rect.left else None
    finally:
        _release(found, condition, element, automation)
        ctypes.windll.oleaut32.SysFreeString(ctypes.c_void_p(name))


class LeftEdge:
    """Keeps `value` — the Widgets button's right edge, or None — fresh from a thread of its own."""

    def __init__(self, taskbar: Callable[[], int | None]) -> None:
        self._taskbar = taskbar
        self.value: int | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="widgets", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        ctypes.oledll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        failed = False
        while not self._stop.is_set():
            taskbar = self._taskbar()
            try:
                self.value = widgets_right(taskbar) if taskbar else None
                failed = False
            except Exception:  # the thread must outlive any failure, or `value` would freeze
                if not failed:  # once per outage, not every five seconds
                    log.exception("UI Automation: could not find the Widgets button")
                failed = True
                self.value = None
            self._stop.wait(REFRESH_SECONDS)
