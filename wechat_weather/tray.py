# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Callable
from urllib import request
import webbrowser

from .config import APP_NAME, load_config
from .server import WeatherServer


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _startup_file() -> Path:
    startup = (
        Path.home()
        / "AppData"
        / "Roaming"
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )
    return startup / f"{APP_NAME}.cmd"


def _autostart_enabled() -> bool:
    return _startup_file().exists()


def _startup_args(config_path: str | None) -> list[str]:
    if getattr(sys, "frozen", False):
        args = [sys.executable, "tray"]
    else:
        args = [sys.executable, "-m", "wechat_weather.cli", "tray"]
    if config_path:
        args.extend(["--config", str(Path(config_path).resolve())])
    return args


def _set_autostart(enabled: bool, config_path: str | None) -> None:
    path = _startup_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        command = subprocess.list2cmdline(_startup_args(config_path))
        root = _project_root()
        path.write_text(
            f"@echo off\r\ncd /d {subprocess.list2cmdline([str(root)])}\r\n"
            f"start \"\" /min {command}\r\n",
            encoding="utf-8",
        )
    elif path.exists():
        path.unlink()


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


class TrayRuntime:
    def __init__(self, config_path: str | None, window_handle: int | None) -> None:
        self.config_path = config_path
        self.window_handle = window_handle
        self.config = load_config(config_path, create_user_config=config_path is None)
        self.host = self.config.app.host
        self.port = self.config.app.port
        self.url = f"http://{self.host}:{self.port}/"
        self.server: WeatherServer | None = None
        self.server_thread: threading.Thread | None = None
        self.icon = None

    def start_server(self) -> None:
        if _port_open(self.host, self.port):
            return
        self.server = WeatherServer(
            (self.host, self.port),
            config_path=self.config_path,
            window_handle=self.window_handle,
        )
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            name="KangkangWeatherServer",
            daemon=True,
        )
        self.server_thread.start()
        deadline = time.time() + 8
        while time.time() < deadline:
            if _port_open(self.host, self.port):
                return
            time.sleep(0.2)

    def stop_server(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.monitor.stop()
            self.server.server_close()

    def _background(self, action: Callable[[], None]) -> None:
        threading.Thread(target=action, daemon=True).start()

    def _set_title(self, text: str) -> None:
        if self.icon is not None:
            self.icon.title = text[:63]

    def open_console(self, *_: Any) -> None:
        webbrowser.open(self.url)

    def check_now(self, *_: Any) -> None:
        def run() -> None:
            self._set_title("Kangkang Weather: 正在检查")
            try:
                _post_json(
                    f"{self.url}api/monitor/check",
                    {"real": True, "recipient": self.config.contact},
                )
                self._set_title("Kangkang Weather: 检查完成")
            except Exception as exc:
                self._set_title(f"检查失败: {exc}")

        self._background(run)

    def send_weather(self, *_: Any) -> None:
        def run() -> None:
            self._set_title("Kangkang Weather: 正在发送")
            try:
                _post_json(
                    f"{self.url}api/send-weather",
                    {
                        "real": True,
                        "recipient": self.config.contact,
                        "backend": self.config.monitor.backend,
                    },
                )
                self._set_title("Kangkang Weather: 发送完成")
            except Exception as exc:
                self._set_title(f"发送失败: {exc}")

        self._background(run)

    def toggle_autostart(self, *_: Any) -> None:
        enabled = not _autostart_enabled()
        _set_autostart(enabled, self.config_path)
        self._set_title("Kangkang Weather: 已开启自启" if enabled else "Kangkang Weather: 已关闭自启")

    def quit(self, icon, *_: Any) -> None:
        self.stop_server()
        icon.stop()


def _make_icon_image():
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:  # pragma: no cover - optional desktop dependency
        raise RuntimeError("缺少 Pillow，先执行：python -m pip install pillow") from exc

    image = Image.new("RGBA", (64, 64), (34, 115, 72, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 14, 52, 48), fill=(255, 255, 255, 235))
    draw.rectangle((14, 34, 50, 50), fill=(255, 255, 255, 235))
    draw.line((22, 54, 18, 61), fill=(41, 93, 122, 255), width=3)
    draw.line((34, 54, 30, 61), fill=(41, 93, 122, 255), width=3)
    draw.line((46, 54, 42, 61), fill=(41, 93, 122, 255), width=3)
    return image


def run_tray(config_path: str | None = None, window_handle: int | None = None) -> None:
    try:
        import pystray
    except Exception as exc:  # pragma: no cover - optional desktop dependency
        raise RuntimeError("缺少 pystray，先执行：python -m pip install pystray pillow") from exc

    runtime = TrayRuntime(config_path=config_path, window_handle=window_handle)
    runtime.start_server()
    if runtime.config.app.open_browser_on_start:
        runtime.open_console()

    menu = pystray.Menu(
        pystray.MenuItem("打开控制台", runtime.open_console, default=True),
        pystray.MenuItem("立即检查", runtime.check_now),
        pystray.MenuItem("发送今日天气", runtime.send_weather),
        pystray.MenuItem(
            "开机自启",
            runtime.toggle_autostart,
            checked=lambda item: _autostart_enabled(),
        ),
        pystray.MenuItem("退出", runtime.quit),
    )
    icon = pystray.Icon(APP_NAME, _make_icon_image(), "Kangkang Weather", menu)
    runtime.icon = icon
    icon.run()
