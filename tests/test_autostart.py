import sys
import winreg
from collections.abc import Iterator

import pytest

from juice_mate.update import autostart

TEST_KEY = "Software\\JuiceMateTests\\Run"


@pytest.fixture
def run_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A throwaway key under HKCU — the real Run key is never touched by tests."""
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, TEST_KEY).Close()
    monkeypatch.setattr(autostart, "RUN_KEY", TEST_KEY)
    yield TEST_KEY
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, "Software\\JuiceMateTests")


def test_toggle(run_key: str) -> None:
    assert not autostart.is_enabled()
    autostart.set_enabled(True)
    assert autostart.is_enabled()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key) as key:
        assert winreg.QueryValueEx(key, "JuiceMate")[0] == autostart.command()
    autostart.set_enabled(False)
    assert not autostart.is_enabled()
    autostart.set_enabled(False)  # disabling twice is fine


def test_dev_checkout_starts_without_a_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert autostart.command().endswith('pythonw.exe" -m juice_mate')


def test_installed_build_starts_its_own_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:\\Users\\x\\AppData\\Local\\JuiceMate\\current\\JuiceMate.exe")
    assert autostart.command() == '"C:\\Users\\x\\AppData\\Local\\JuiceMate\\current\\JuiceMate.exe"'
