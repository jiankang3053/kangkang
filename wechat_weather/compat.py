# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import ctypes
import json
import os
from pathlib import Path
import platform
import socket
import sys
import tempfile
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import requests

from .config import APP_NAME, APP_VERSION, config_to_dict, default_user_config_path, load_config, user_data_dir
from .readiness import check_readiness
from .wechat import collect_diagnostics


@dataclass(frozen=True)
class CompatCheck:
    id: str
    title: str
    ok: bool
    severity: str = "info"
    detail: str = ""
    fix: str = ""


@dataclass(frozen=True)
class CompatReport:
    ok: bool
    status: str
    generated_at: str
    checks: list[CompatCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "generated_at": self.generated_at,
            "checks": [asdict(item) for item in self.checks],
        }


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _appdata_write_check() -> tuple[bool, str]:
    try:
        root = user_data_dir()
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, str(root)
    except Exception as exc:
        return False, str(exc)


def _clipboard_check() -> tuple[bool, str]:
    try:
        user32 = ctypes.windll.user32
        if not user32.OpenClipboard(None):
            return False, "OpenClipboard failed"
        user32.CloseClipboard()
        return True, "clipboard can be opened"
    except Exception as exc:
        return False, str(exc)


def _weather_check(timeout: float = 4.0) -> tuple[bool, str]:
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": 30, "longitude": 114, "daily": "weather_code", "forecast_days": 1},
            timeout=timeout,
        )
        response.raise_for_status()
        return True, f"Open-Meteo HTTP {response.status_code}"
    except Exception as exc:
        return False, str(exc)


def _wechat_check_lines() -> tuple[bool, list[str]]:
    try:
        lines = collect_diagnostics()
        joined = "\n".join(lines)
        return "WeChat-like top windows:" in joined or "Weixin" in joined or "微信" in joined, lines
    except Exception as exc:
        return False, [f"diagnostics failed: {exc}"]


def build_compat_report(config_path: str | None = None, active_port: int | None = None) -> dict[str, Any]:
    config = load_config(config_path, create_user_config=config_path is None)
    checks: list[CompatCheck] = []

    checks.append(
        CompatCheck(
            id="windows_version",
            title="Windows 版本",
            ok=sys.platform.startswith("win"),
            severity="error" if not sys.platform.startswith("win") else "info",
            detail=f"{platform.system()} {platform.release()} {platform.version()}",
            fix="本便携版只支持 Windows 10/11。",
        )
    )

    appdata_ok, appdata_detail = _appdata_write_check()
    checks.append(
        CompatCheck(
            id="appdata_write",
            title="用户配置写入",
            ok=appdata_ok,
            severity="error" if not appdata_ok else "info",
            detail=appdata_detail,
            fix="确认当前 Windows 用户有权限写入 APPDATA，或换普通用户目录运行。",
        )
    )

    checks.append(
        CompatCheck(
            id="admin_status",
            title="程序权限",
            ok=True,
            severity="warn" if _is_admin() else "info",
            detail="管理员权限" if _is_admin() else "普通用户权限",
            fix="微信和本程序最好使用相同权限级别启动。微信若是管理员权限，本程序也要管理员权限。",
        )
    )

    port = active_port or config.app.port
    port_busy = _port_open(config.app.host, port)
    checks.append(
        CompatCheck(
            id="service_port",
            title="本地服务端口",
            ok=True,
            severity="info",
            detail=f"{config.app.host}:{port} {'正在监听' if port_busy else '当前未监听'}",
            fix="如果 8766 被其他程序占用，托盘程序会自动换端口。",
        )
    )

    clipboard_ok, clipboard_detail = _clipboard_check()
    checks.append(
        CompatCheck(
            id="clipboard",
            title="剪贴板可用性",
            ok=clipboard_ok,
            severity="warn" if not clipboard_ok else "info",
            detail=clipboard_detail,
            fix="搜索目标优先使用 UIA/键盘输入；剪贴板不可用时仍可能影响长正文粘贴，建议关闭剪贴板管理器或远程桌面剪贴板同步后重试。",
        )
    )

    weather_ok, weather_detail = _weather_check()
    checks.append(
        CompatCheck(
            id="weather_network",
            title="天气源网络",
            ok=weather_ok,
            severity="warn" if not weather_ok else "info",
            detail=weather_detail,
            fix="检查网络、代理或防火墙；失败时程序会尽量使用兜底源和缓存。",
        )
    )

    wechat_ok, wechat_lines = _wechat_check_lines()
    checks.append(
        CompatCheck(
            id="wechat_window",
            title="微信窗口",
            ok=wechat_ok,
            severity="error" if not wechat_ok else "info",
            detail="\n".join(wechat_lines[:24]),
            fix="先打开并登录官方 Windows 微信，确认微信和本程序同级权限运行，再点打开会话测试。",
        )
    )

    readiness = check_readiness(require_wechat=True).to_dict()
    checks.append(
        CompatCheck(
            id="automation_readiness",
            title="自动发送环境",
            ok=bool(readiness.get("can_send_now")),
            severity="error" if not readiness.get("can_send_now") else "info",
            detail=json.dumps(readiness, ensure_ascii=False),
            fix="允许息屏，但不要让 Windows 睡眠、锁屏或注销；微信和本程序保持同级权限运行。",
        )
    )

    setup_ok = bool(config.app.setup_complete)
    checks.append(
        CompatCheck(
            id="setup_complete",
            title="首次设置",
            ok=setup_ok,
            severity="warn" if not setup_ok else "info",
            detail="已完成" if setup_ok else "未完成",
            fix="先设置天气地址和微信好友/群名称，再做真实发送。",
        )
    )

    error_count = sum(1 for item in checks if not item.ok and item.severity == "error")
    warn_count = sum(1 for item in checks if not item.ok and item.severity == "warn")
    status = "ready" if error_count == 0 and warn_count == 0 else ("blocked" if error_count else "warning")
    report = CompatReport(
        ok=error_count == 0,
        status=status,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        checks=checks,
    )
    return report.to_dict()


def _redact_config(data: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(data, ensure_ascii=False))
    for target in redacted.get("wechat_targets", []):
        name = str(target.get("name") or "")
        if len(name) > 1:
            target["name"] = name[0] + "***"
    return redacted


def export_diagnostics_package(config_path: str | None = None, active_port: int | None = None) -> Path:
    root = user_data_dir()
    export_dir = root / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = export_dir / f"KangkangWeather-diagnostics-{stamp}.zip"

    config = load_config(config_path, create_user_config=config_path is None)
    config_data = config_to_dict(config)
    report = build_compat_report(config_path=config_path, active_port=active_port)
    diagnostics = collect_diagnostics()
    log_path = root / "logs" / "app.log"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "compat_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (tmp_path / "diagnostics.txt").write_text("\n".join(diagnostics), encoding="utf-8")
        (tmp_path / "config.redacted.json").write_text(json.dumps(_redact_config(config_data), ensure_ascii=False, indent=2), encoding="utf-8")
        if log_path.exists():
            (tmp_path / "app.log").write_text(log_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
            for item in tmp_path.iterdir():
                archive.write(item, item.name)
    return zip_path
