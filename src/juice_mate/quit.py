"""Quitting Juice-Mate from another process — the settings window's power button.

The panel process owns a named event and waits on it on a thread of its own; any process of the same
user can set it. A named event and not a file: it needs no polling and leaves nothing behind.
"""

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes

log = logging.getLogger(__name__)

NAME = "Local\\JuiceMateQuit"
_EVENT_MODIFY_STATE = 0x0002
_INFINITE = 0xFFFFFFFF
_WAIT_OBJECT_0 = 0

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.OpenEventW.restype = wintypes.HANDLE
_kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.SetEvent.argtypes = [wintypes.HANDLE]
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def listen(on_quit: Callable[[], None]) -> None:
    """The panel process: call `on_quit` (on a daemon thread) when someone asks to quit."""
    handle = _kernel32.CreateEventW(None, False, False, NAME)
    if not handle:
        log.warning("no quit event (error %s): the settings window cannot quit the panel", ctypes.get_last_error())
        return

    def wait() -> None:
        if _kernel32.WaitForSingleObject(handle, _INFINITE) == _WAIT_OBJECT_0:
            log.info("asked to quit by the settings window")
            on_quit()

    threading.Thread(target=wait, name="quit", daemon=True).start()


def request() -> bool:
    """Any other process: ask the panel to quit. False when no panel is running."""
    handle = _kernel32.OpenEventW(_EVENT_MODIFY_STATE, False, NAME)
    if not handle:
        return False
    try:
        return bool(_kernel32.SetEvent(handle))
    finally:
        _kernel32.CloseHandle(handle)
