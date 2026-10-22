"""Putting pixels on a layered window — the panel strips and the hover card alike."""

import ctypes
import logging
from ctypes import wintypes as w

from juice_mate.panel import win32 as api

log = logging.getLogger(__name__)


def blit(
    hwnd: int, width: int, height: int, pixels: bytes, at: tuple[int, int] | None = None, alpha: int = 255
) -> None:
    """`pixels`: premultiplied BGRA rows, top-down. `at` moves the window (screen pixels) in the same
    call; `alpha` fades the whole window on top of its per-pixel alpha."""
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
        where = w.POINT(*at) if at is not None else None
        blend = api.BLENDFUNCTION(api.AC_SRC_OVER, 0, max(0, min(255, alpha)), api.AC_SRC_ALPHA)
        ok = api.user32.UpdateLayeredWindow(
            hwnd,
            screen,
            ctypes.byref(where) if where is not None else None,
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
