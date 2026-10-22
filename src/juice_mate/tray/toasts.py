"""Windows notifications from Juice-Mate (docs/architecture.md §6).

An unpackaged app needs an AppUserModelID for its toasts to carry its own name; it is registered
per user under HKCU (no admin). Without it Windows would sign the toast "Windows PowerShell".
A toast that fails is logged and dropped — a notification is never worth a crash.
"""

import logging
import winreg

import windows_toasts as wt

from juice_mate.core.alerts import Alert
from juice_mate.core.news import Story

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

    def show_news(self, stories: list[Story]) -> None:
        """The day's tech news: one line per story, a "Read" button per story that has its article;
        clicking the notification itself opens the first one."""
        if self._toaster is None or not stories:
            return
        linked = [s for s in stories if s.url]
        try:
            toast = wt.Toast(
                ["Tech news", *(s.text for s in stories[:2])],
                launch_action=linked[0].url if linked else None,
                actions=[wt.ToastButton(f"Read · {s.source or 'article'}", launch=s.url) for s in linked[:2]],
            )
            self._toaster.show_toast(toast)
        except Exception:
            log.exception("news toast failed")

    def show(self, alert: Alert) -> None:
        if self._toaster is None:
            return
        try:
            self._toaster.show_toast(wt.Toast([alert.title, alert.body]))
        except Exception:
            log.exception("toast failed: %s", alert.title)
