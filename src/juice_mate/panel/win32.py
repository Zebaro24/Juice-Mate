"""The few Win32 calls the panel needs, with argument types declared — on 64-bit Windows an
undeclared handle or LPARAM is silently truncated to 32 bits."""

import ctypes
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.UINT),
        ("style", w.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", w.HINSTANCE),
        ("hIcon", w.HICON),
        ("hCursor", w.HANDLE),
        ("hbrBackground", w.HBRUSH),
        ("lpszMenuName", w.LPCWSTR),
        ("lpszClassName", w.LPCWSTR),
        ("hIconSm", w.HICON),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", w.DWORD),
        ("biWidth", w.LONG),
        ("biHeight", w.LONG),
        ("biPlanes", w.WORD),
        ("biBitCount", w.WORD),
        ("biCompression", w.DWORD),
        ("biSizeImage", w.DWORD),
        ("biXPelsPerMeter", w.LONG),
        ("biYPelsPerMeter", w.LONG),
        ("biClrUsed", w.DWORD),
        ("biClrImportant", w.DWORD),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class TOOLINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.UINT),
        ("uFlags", w.UINT),
        ("hwnd", w.HWND),
        ("uId", ctypes.c_size_t),
        ("rect", w.RECT),
        ("hinst", w.HINSTANCE),
        ("lpszText", w.LPWSTR),
        ("lParam", w.LPARAM),
        ("lpReserved", ctypes.c_void_p),
    ]


def _sig(dll: ctypes.WinDLL, name: str, restype: object, *argtypes: object) -> None:
    fn = getattr(dll, name)
    fn.restype = restype
    fn.argtypes = list(argtypes)


_sig(user32, "DefWindowProcW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_sig(user32, "RegisterClassExW", w.ATOM, ctypes.POINTER(WNDCLASSEXW))
_sig(user32, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
     ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)  # fmt: skip
_sig(user32, "DestroyWindow", w.BOOL, w.HWND)
_sig(user32, "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)
_sig(user32, "FindWindowExW", w.HWND, w.HWND, w.HWND, w.LPCWSTR, w.LPCWSTR)
_sig(user32, "SetParent", w.HWND, w.HWND, w.HWND)
_sig(user32, "GetParent", w.HWND, w.HWND)
_sig(user32, "IsWindow", w.BOOL, w.HWND)
_sig(user32, "IsWindowVisible", w.BOOL, w.HWND)
_sig(user32, "GetWindowRect", w.BOOL, w.HWND, ctypes.POINTER(w.RECT))
_sig(user32, "GetWindowLongPtrW", ctypes.c_ssize_t, w.HWND, ctypes.c_int)
_sig(user32, "SetWindowLongPtrW", ctypes.c_ssize_t, w.HWND, ctypes.c_int, ctypes.c_ssize_t)
_sig(user32, "SetWindowPos", w.BOOL, w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT)
_sig(user32, "UpdateLayeredWindow", w.BOOL, w.HWND, w.HDC, ctypes.POINTER(w.POINT), ctypes.POINTER(w.SIZE), w.HDC,
     ctypes.POINTER(w.POINT), w.COLORREF, ctypes.POINTER(BLENDFUNCTION), w.DWORD)  # fmt: skip
_sig(user32, "GetDC", w.HDC, w.HWND)
_sig(user32, "ReleaseDC", ctypes.c_int, w.HWND, w.HDC)
_sig(user32, "GetMessageW", w.BOOL, ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
_sig(user32, "TranslateMessage", w.BOOL, ctypes.POINTER(w.MSG))
_sig(user32, "DispatchMessageW", LRESULT, ctypes.POINTER(w.MSG))
_sig(user32, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_sig(user32, "SendMessageW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_sig(user32, "PostQuitMessage", None, ctypes.c_int)
_sig(user32, "RegisterWindowMessageW", w.UINT, w.LPCWSTR)
_sig(user32, "SetTimer", ctypes.c_size_t, w.HWND, ctypes.c_size_t, w.UINT, w.LPVOID)
_sig(user32, "CreatePopupMenu", w.HMENU)
_sig(user32, "AppendMenuW", w.BOOL, w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR)
_sig(user32, "TrackPopupMenu", w.BOOL, w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.LPVOID)
_sig(user32, "DestroyMenu", w.BOOL, w.HMENU)
_sig(user32, "SetForegroundWindow", w.BOOL, w.HWND)
_sig(user32, "GetCursorPos", w.BOOL, ctypes.POINTER(w.POINT))
_sig(user32, "GetDpiForWindow", w.UINT, w.HWND)
_sig(user32, "SetThreadDpiAwarenessContext", w.HANDLE, w.HANDLE)
_sig(user32, "LoadCursorW", w.HANDLE, w.HINSTANCE, w.LPVOID)
_sig(gdi32, "CreateCompatibleDC", w.HDC, w.HDC)
_sig(gdi32, "DeleteDC", w.BOOL, w.HDC)
_sig(gdi32, "CreateDIBSection", w.HBITMAP, w.HDC, ctypes.POINTER(BITMAPINFOHEADER), w.UINT,
     ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD)  # fmt: skip
_sig(gdi32, "SelectObject", w.HGDIOBJ, w.HDC, w.HGDIOBJ)
_sig(gdi32, "DeleteObject", w.BOOL, w.HGDIOBJ)
_sig(kernel32, "GetModuleHandleW", w.HMODULE, w.LPCWSTR)

GWL_STYLE = -16
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_CLIPSIBLINGS = 0x04000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
HWND_TOP = None
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_MOUSELEAVE = 0x02A3
WM_DISPLAYCHANGE = 0x007E
WM_SETTINGCHANGE = 0x001A
WM_APP = 0x8000
ULW_ALPHA = 0x02
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
MF_STRING = 0x0000
MF_CHECKED = 0x0008
MF_SEPARATOR = 0x0800
MF_POPUP = 0x0010
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020
IDC_ARROW = 32512
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = w.HANDLE(-4)

# Tooltips (comctl32 v6 is loaded by Python's manifest).
TOOLTIPS_CLASS = "tooltips_class32"
TTS_ALWAYSTIP = 0x01
TTS_NOPREFIX = 0x02
TTF_SUBCLASS = 0x0010
TTF_TRACK = 0x0020
TTF_ABSOLUTE = 0x0080
TTM_ADDTOOLW = 0x0432
TTM_NEWTOOLRECTW = 0x0434
TTM_UPDATETIPTEXTW = 0x0439
TTM_DELTOOLW = 0x0433
TTM_SETMAXTIPWIDTH = 0x0418
CW_USEDEFAULT = ctypes.c_int(0x80000000).value


def rect(hwnd: int | None) -> tuple[int, int, int, int]:
    r = w.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom
