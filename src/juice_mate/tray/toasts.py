"""Windows notifications from Juice-Mate (docs/architecture.md §6).

An unpackaged app needs an AppUserModelID for its toasts to carry its own name; it is registered
per user under HKCU (no admin). Without it Windows would sign the toast "Windows PowerShell".
A toast that fails is logged and dropped — a notification is never worth a crash.
"""

import logging
import winreg

import windows_toasts as wt

from juice_mate.core.alerts import Alert

log = logging.getLogger(__name__)

AUMID = "Zebaro.JuiceMate"
DISPLAY_NAME = "Juice-Mate"


def _register() -> None:
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\AppUserModelId\\" + AUMID)
    with key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, DISPLAY_NAME)


class Toasts:
    def __init__(self) -> None:
        self._toaster: wt.InteractableWindowsToaster | None = None
        try:
            _register()
            self._toaster = wt.InteractableWindowsToaster(DISPLAY_NAME, AUMID)
        except Exception:
            log.exception("toasts unavailable")

    def show(self, alert: Alert) -> None:
        if self._toaster is None:
            return
        try:
            self._toaster.show_toast(wt.Toast([alert.title, alert.body]))
        except Exception:
            log.exception("toast failed: %s", alert.title)
