"""Self-update through Velopack from this repo's GitHub Releases (docs/architecture.md §4).

`startup()` runs first thing in `main`: Velopack's install / update / uninstall hooks call the exe with
special arguments and expect it to do its part and exit. On the first run after install, autostart
is switched on — the second PC's owner should never have to find a setting.

`Updater` checks every six hours, downloads in the background, and never restarts under the user:
the update is applied on the next start, or at once from the panel menu ("Restart to update").
A dev checkout is not installed: everything here quietly does nothing.
"""

import logging
import sys
import threading
from collections.abc import Callable

import velopack

log = logging.getLogger(__name__)

REPO = "https://github.com/Zebaro24/Juice-Mate"
CHECK_EVERY = 6 * 3600.0


def installed() -> bool:
    return bool(getattr(sys, "frozen", False))


def version() -> str:
    """The installed version, as Velopack knows it; "dev" for a checkout or a build run from dist/."""
    if installed():
        try:
            return str(velopack.UpdateManager(velopack.GithubSource(REPO)).get_current_version())
        except Exception as e:  # not installed through Setup.exe
            log.info("no installed version: %s", e)
    return "dev"


def startup() -> None:
    if not installed():
        return
    from juice_mate.update import autostart

    # Velopack passes the version to every hook: a hook without a parameter failed silently, and
    # v0.3.0 installed without autostart (2026-10-22).
    def switch(enabled: bool) -> Callable[..., None]:
        def hook(*_version: object) -> None:
            try:
                autostart.set_enabled(enabled)
            except OSError:
                log.exception("could not switch autostart %s", "on" if enabled else "off")

        return hook

    # On at install (a fast hook, inside Setup), again at the first run in case that failed, and off
    # at uninstall — a Run entry must not outlive the app.
    (
        velopack.App()
        .on_after_install_fast_callback(switch(True))
        .on_first_run(switch(True))
        .on_before_uninstall_fast_callback(switch(False))
        .run()
    )


class Updater:
    def __init__(self) -> None:
        self._pending: velopack.UpdateInfo | None = None
        self._manager: velopack.UpdateManager | None = None
        self._stop = threading.Event()

    @property
    def ready(self) -> str | None:
        """The downloaded version waiting for a restart, if any."""
        return self._pending.TargetFullRelease.Version if self._pending is not None else None

    def start(self) -> None:
        if installed():
            threading.Thread(target=self._loop, name="updater", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.check()
            self._stop.wait(CHECK_EVERY)

    def check(self) -> None:
        try:
            manager = velopack.UpdateManager(velopack.GithubSource(REPO))
        except RuntimeError as e:  # a frozen build run from dist/, not installed by Setup.exe
            log.info("not installed through Setup.exe, no self-update: %s", e)
            self._stop.set()
            return
        try:
            info = manager.check_for_updates()
            if info is None:
                return
            manager.download_updates(info)
            self._manager, self._pending = manager, info
            log.info("update %s downloaded; applies on the next start", info.TargetFullRelease.Version)
        except Exception:  # offline, GitHub's 60-requests-an-hour limit, a broken release: try later
            log.exception("update check failed")

    def restart_now(self) -> None:
        if self._manager is None or self._pending is None:
            return
        try:
            self._manager.apply_updates_and_restart(self._pending)
        except Exception:
            log.exception("could not apply the update")
