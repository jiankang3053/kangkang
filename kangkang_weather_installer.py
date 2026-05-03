# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox


APP_NAME = "KangkangWeather"
DISPLAY_NAME = "Kangkang Weather"


def _payload_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "payload"


def _copy_payload(target: Path) -> None:
    source = _payload_dir()
    if not source.exists():
        raise FileNotFoundError(f"安装包资源缺失：{source}")
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


def _powershell_quote(value: Path | str) -> str:
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _create_shortcut(link: Path, target: Path, working_dir: Path, description: str) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    command = "\n".join(
        [
            "$shell = New-Object -ComObject WScript.Shell",
            f"$shortcut = $shell.CreateShortcut({_powershell_quote(link)})",
            f"$shortcut.TargetPath = {_powershell_quote(target)}",
            f"$shortcut.WorkingDirectory = {_powershell_quote(working_dir)}",
            f"$shortcut.Description = {_powershell_quote(description)}",
            "$shortcut.Save()",
        ]
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=False,
        creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )


def _write_uninstaller(install_dir: Path) -> Path:
    script = install_dir / "Uninstall Kangkang Weather.cmd"
    content = f"""@echo off
setlocal
taskkill /IM KangkangWeather.exe /F >nul 2>nul
del "%USERPROFILE%\\Desktop\\Kangkang Weather.lnk" >nul 2>nul
del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Kangkang Weather.lnk" >nul 2>nul
del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Uninstall Kangkang Weather.lnk" >nul 2>nul
cd /d "%LOCALAPPDATA%\\Programs"
rmdir /s /q "KangkangWeather"
echo Kangkang Weather 已卸载。
pause
"""
    script.write_text(content, encoding="utf-8")
    return script


def install() -> Path:
    local_appdata = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    install_dir = local_appdata / "Programs" / APP_NAME
    _copy_payload(install_dir)
    exe = install_dir / "KangkangWeather.exe"
    if not exe.exists():
        raise FileNotFoundError(exe)

    uninstall = _write_uninstaller(install_dir)
    desktop = Path(os.environ.get("USERPROFILE") or Path.home()) / "Desktop" / "Kangkang Weather.lnk"
    start_menu = Path(os.environ.get("APPDATA") or Path.home()) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    _create_shortcut(desktop, exe, install_dir, DISPLAY_NAME)
    _create_shortcut(start_menu / "Kangkang Weather.lnk", exe, install_dir, DISPLAY_NAME)
    _create_shortcut(start_menu / "Uninstall Kangkang Weather.lnk", uninstall, install_dir, "卸载 Kangkang Weather")
    (install_dir / "install.log").write_text(f"installed to {install_dir}\n", encoding="utf-8")
    return install_dir


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    try:
        install_dir = install()
    except Exception as exc:
        messagebox.showerror("Kangkang Weather 安装失败", str(exc))
        return 1
    messagebox.showinfo(
        "Kangkang Weather 安装完成",
        f"已安装到：\n{install_dir}\n\n桌面和开始菜单快捷方式已创建。",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
