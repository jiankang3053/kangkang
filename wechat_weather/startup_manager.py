# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
from pathlib import Path
import subprocess
import sys
from typing import Any

from .config import APP_NAME


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


@dataclass(frozen=True)
class StartupStatus:
    ok: bool
    enabled: bool
    command: str
    executable_path: str
    is_frozen: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StartupManager:
    def __init__(self, config_path: str | None = None, app_name: str = APP_NAME) -> None:
        self.config_path = config_path
        self.app_name = app_name

    def get_executable_path(self) -> str:
        return str(Path(sys.executable).resolve())

    def get_startup_command(self) -> str:
        if getattr(sys, "frozen", False):
            args = [self.get_executable_path(), "tray"]
        else:
            args = [self.get_executable_path(), "-m", "wechat_weather.cli", "tray"]
        if self.config_path:
            args.extend(["--config", str(Path(self.config_path).resolve())])
        return subprocess.list2cmdline(args)

    def _winreg(self):
        import winreg  # type: ignore

        return winreg

    def _open_key(self, access: int):
        winreg = self._winreg()
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access)

    def is_enabled(self) -> bool:
        try:
            winreg = self._winreg()
            with self._open_key(winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, self.app_name)
            return str(value).strip() == self.get_startup_command()
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def enable(self) -> None:
        winreg = self._winreg()
        command = self.get_startup_command()
        logging.info("Enabling HKCU autostart for %s; frozen=%s", self.app_name, getattr(sys, "frozen", False))
        with self._open_key(winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, command)

    def disable(self) -> None:
        winreg = self._winreg()
        logging.info("Disabling HKCU autostart for %s", self.app_name)
        try:
            with self._open_key(winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self.app_name)
        except FileNotFoundError:
            return

    def status(self) -> StartupStatus:
        try:
            enabled = self.is_enabled()
            return StartupStatus(
                ok=True,
                enabled=enabled,
                command=self.get_startup_command(),
                executable_path=self.get_executable_path(),
                is_frozen=bool(getattr(sys, "frozen", False)),
                detail="已开启" if enabled else "未开启",
            )
        except Exception as exc:
            return StartupStatus(
                ok=False,
                enabled=False,
                command=self.get_startup_command(),
                executable_path=self.get_executable_path(),
                is_frozen=bool(getattr(sys, "frozen", False)),
                detail=f"检测失败：{exc}",
            )
