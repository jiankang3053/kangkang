# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Callable
from urllib import request
import webbrowser

from .config import APP_NAME, APP_VERSION, load_config, user_data_dir
from .server import WeatherServer
from .startup_manager import StartupManager


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
    return StartupManager().is_enabled()


def _startup_args(config_path: str | None) -> list[str]:
    if getattr(sys, "frozen", False):
        args = [sys.executable, "tray"]
    else:
        args = [sys.executable, "-m", "wechat_weather.cli", "tray"]
    if config_path:
        args.extend(["--config", str(Path(config_path).resolve())])
    return args


def _set_autostart(enabled: bool, config_path: str | None) -> None:
    manager = StartupManager(config_path)
    if enabled:
        manager.enable()
    else:
        manager.disable()


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False


def _configure_logging() -> None:
    log_dir = user_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_dir / "app.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def _get_json(url: str) -> dict[str, Any]:
    with request.urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


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


def _is_existing_kangkang(url: str) -> bool:
    try:
        data = _get_json(f"{url}api/state")
        app = data.get("app", {})
        return app.get("name") == APP_NAME and app.get("version") == APP_VERSION
    except Exception:
        return False


def _find_free_port(host: str, preferred: int) -> int:
    for port in range(preferred + 1, preferred + 80):
        if not _port_open(host, port):
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


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
            if _is_existing_kangkang(self.url):
                logging.info("Reusing existing KangkangWeather service at %s", self.url)
                return
            old_port = self.port
            self.port = _find_free_port(self.host, self.port)
            self.url = f"http://{self.host}:{self.port}/"
            logging.warning("Port %s is occupied by another service; using %s", old_port, self.port)
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
        logging.info("Started KangkangWeather service at %s", self.url)
        deadline = time.time() + 8
        while time.time() < deadline:
            if _port_open(self.host, self.port):
                return
            time.sleep(0.2)

    def stop_server(self) -> None:
        if self.server is not None:
            logging.info("Stopping KangkangWeather service")
            self.server.shutdown()
            self.server.monitor.stop()
            self.server.server_close()

    def _background(self, action: Callable[[], None]) -> None:
        threading.Thread(target=action, daemon=True).start()

    def _set_title(self, text: str) -> None:
        if self.icon is not None:
            self.icon.title = text[:63]

    def refresh_tooltip(self) -> None:
        try:
            state = _get_json(f"{self.url}api/state")
            location = next(
                (
                    item
                    for item in state.get("locations", [])
                    if item.get("id") == state.get("defaults", {}).get("location_id")
                ),
                {},
            )
            dashboard = state.get("dashboard", {})
            monitor = state.get("monitor", {})
            self._set_title(
                "\n".join(
                    [
                        "Kangkang Weather",
                        f"城市：{location.get('name') or '待确认'}",
                        f"自动化：{'已开启' if monitor.get('enabled') else '已暂停'}",
                        f"下次发送：{dashboard.get('next_fixed_send_at') or dashboard.get('next_check_at') or '暂无'}",
                    ]
                )
            )
        except Exception:
            self._set_title("Kangkang Weather")

    def open_console(self, *_: Any) -> None:
        webbrowser.open(self.url)

    def open_settings(self, *_: Any) -> None:
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
                self.refresh_tooltip()
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
                self.refresh_tooltip()
            except Exception as exc:
                self._set_title(f"发送失败: {exc}")

    def refresh_weather(self, *_: Any) -> None:
        def run() -> None:
            self._set_title("Kangkang Weather: 正在刷新天气")
            try:
                _get_json(f"{self.url}api/preview")
                self._set_title("Kangkang Weather: 天气已刷新")
                self.refresh_tooltip()
            except Exception as exc:
                self._set_title(f"刷新失败: {exc}")

        self._background(run)

    def pause_monitor(self, *_: Any) -> None:
        def run() -> None:
            try:
                _post_json(f"{self.url}api/monitor/pause", {})
                self._set_title("Kangkang Weather: 自动化已暂停")
            except Exception as exc:
                self._set_title(f"暂停失败: {exc}")

        self._background(run)

    def resume_monitor(self, *_: Any) -> None:
        def run() -> None:
            try:
                _post_json(f"{self.url}api/monitor/resume", {})
                self._set_title("Kangkang Weather: 自动化已恢复")
            except Exception as exc:
                self._set_title(f"恢复失败: {exc}")

        self._background(run)

    def export_diagnostics(self, *_: Any) -> None:
        def run() -> None:
            try:
                result = _post_json(f"{self.url}api/diagnostics/export", {})
                self._set_title("诊断包已导出")
                logging.info("Diagnostics exported: %s", result.get("path"))
            except Exception as exc:
                self._set_title(f"导出失败: {exc}")

        self._background(run)

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
    _configure_logging()
    try:
        import pystray
    except Exception as exc:  # pragma: no cover - optional desktop dependency
        logging.exception("pystray import failed")
        raise RuntimeError("缺少 pystray，先执行：python -m pip install pystray pillow") from exc

    try:
        runtime = TrayRuntime(config_path=config_path, window_handle=window_handle)
        runtime.start_server()
        if runtime.config.app.open_browser_on_start:
            runtime.open_console()
    except Exception:
        logging.exception("Failed to start tray runtime")
        raise

    menu = pystray.Menu(
        pystray.MenuItem("显示主窗口", runtime.open_console, default=True),
        pystray.MenuItem("刷新天气", runtime.refresh_weather),
        pystray.MenuItem("立即检查", runtime.check_now),
        pystray.MenuItem("发送今日天气", runtime.send_weather),
        pystray.MenuItem("暂停自动化", runtime.pause_monitor),
        pystray.MenuItem("恢复自动化", runtime.resume_monitor),
        pystray.MenuItem("打开设置", runtime.open_settings),
        pystray.MenuItem("导出诊断包", runtime.export_diagnostics),
        pystray.MenuItem(
            "开机自启",
            runtime.toggle_autostart,
            checked=lambda item: _autostart_enabled(),
        ),
        pystray.MenuItem("退出", runtime.quit),
    )
    icon = pystray.Icon(APP_NAME, _make_icon_image(), "Kangkang Weather", menu)
    runtime.icon = icon
    runtime.refresh_tooltip()
    icon.run()
