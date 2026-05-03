# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import ctypes
import os
import sys
from typing import Any


READY = "ready"
BLOCKED_LOCKED = "blocked_sleep_or_locked"
BLOCKED_NO_DESKTOP = "blocked_no_interactive_desktop"
BLOCKED_WECHAT_NOT_RUNNING = "blocked_wechat_not_running"
BLOCKED_WECHAT_WINDOW = "blocked_wechat_window_unavailable"
BLOCKED_PRIVILEGE = "blocked_privilege_mismatch"
WARNING_CLIPBOARD = "warning_clipboard_unavailable"
WARNING_RDP = "warning_rdp_risk"


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    title: str
    ok: bool
    severity: str = "info"
    status: str = READY
    detail: str = ""
    fix: str = ""


@dataclass(frozen=True)
class ReadinessReport:
    ok: bool
    status: str
    can_send_now: bool
    can_retry_later: bool
    generated_at: str
    title: str
    detail: str
    checks: list[ReadinessCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "can_send_now": self.can_send_now,
            "can_retry_later": self.can_retry_later,
            "generated_at": self.generated_at,
            "title": self.title,
            "detail": self.detail,
            "checks": [asdict(item) for item in self.checks],
        }


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _is_admin() -> bool:
    if not _is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _current_session_id() -> int | None:
    if not _is_windows():
        return None
    try:
        session_id = ctypes.c_uint()
        pid = ctypes.windll.kernel32.GetCurrentProcessId()
        if ctypes.windll.kernel32.ProcessIdToSessionId(pid, ctypes.byref(session_id)):
            return int(session_id.value)
    except Exception:
        return None
    return None


def _input_desktop_name() -> tuple[bool, str]:
    if not _is_windows():
        return False, "not windows"
    user32 = ctypes.windll.user32
    handle = None
    try:
        DESKTOP_READOBJECTS = 0x0001
        DESKTOP_SWITCHDESKTOP = 0x0100
        handle = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS | DESKTOP_SWITCHDESKTOP)
        if not handle:
            return False, "OpenInputDesktop failed"
        UOI_NAME = 2
        needed = ctypes.c_uint(0)
        user32.GetUserObjectInformationW(handle, UOI_NAME, None, 0, ctypes.byref(needed))
        if needed.value <= 0:
            return True, "unknown"
        buffer = ctypes.create_unicode_buffer(max(needed.value // 2, 1))
        if user32.GetUserObjectInformationW(
            handle,
            UOI_NAME,
            buffer,
            needed,
            ctypes.byref(needed),
        ):
            return True, buffer.value or "unknown"
        return True, "unknown"
    except Exception as exc:
        return False, str(exc)
    finally:
        if handle:
            try:
                user32.CloseDesktop(handle)
            except Exception:
                pass


def _clipboard_available() -> tuple[bool, str]:
    if not _is_windows():
        return False, "not windows"
    try:
        user32 = ctypes.windll.user32
        if not user32.OpenClipboard(None):
            return False, "OpenClipboard failed"
        user32.CloseClipboard()
        return True, "clipboard can be opened"
    except Exception as exc:
        return False, str(exc)


def _rdp_session() -> bool:
    return bool(os.environ.get("SESSIONNAME", "").upper().startswith("RDP"))


def _token_elevated_for_pid(pid: int) -> bool | None:
    if not _is_windows() or not pid:
        return None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    TOKEN_QUERY = 0x0008
    TokenElevation = 20

    class TOKEN_ELEVATION(ctypes.Structure):
        _fields_ = [("TokenIsElevated", ctypes.c_ulong)]

    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32
    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not process:
        return None
    token = ctypes.c_void_p()
    try:
        if not advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
            return None
        elevation = TOKEN_ELEVATION()
        returned = ctypes.c_ulong()
        if not advapi32.GetTokenInformation(
            token,
            TokenElevation,
            ctypes.byref(elevation),
            ctypes.sizeof(elevation),
            ctypes.byref(returned),
        ):
            return None
        return bool(elevation.TokenIsElevated)
    except Exception:
        return None
    finally:
        if token:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(process)


def _wechat_window_probe() -> dict[str, Any]:
    probe: dict[str, Any] = {
        "found": False,
        "window_count": 0,
        "has_search": False,
        "has_input": False,
        "pids": [],
        "details": [],
        "error": "",
    }
    try:
        from .wechat import (
            WECHAT_MAIN_CLASS,
            WECHAT_WINDOW_MARKERS,
            PywinautoActiveChatSender,
            _safe_class_name,
            _safe_process_id,
            _safe_window_text,
        )
        from pywinauto import Desktop
    except Exception as exc:
        probe["error"] = str(exc)
        return probe

    try:
        for window in Desktop(backend="uia").windows():
            title = _safe_window_text(window)
            class_name = _safe_class_name(window)
            marker = f"{title} {class_name}"
            if class_name != WECHAT_MAIN_CLASS and not any(token in marker for token in WECHAT_WINDOW_MARKERS):
                continue
            probe["found"] = True
            probe["window_count"] += 1
            pid = _safe_process_id(window)
            if pid:
                probe["pids"].append(pid)
            has_search = PywinautoActiveChatSender._search_edit(window) is not None
            has_input = PywinautoActiveChatSender._has_chat_input(window)
            probe["has_search"] = bool(probe["has_search"] or has_search)
            probe["has_input"] = bool(probe["has_input"] or has_input)
            probe["details"].append(
                {
                    "title": title,
                    "class_name": class_name,
                    "pid": pid,
                    "has_search": has_search,
                    "has_input": has_input,
                }
            )
    except Exception as exc:
        probe["error"] = str(exc)
    return probe


def check_readiness(require_wechat: bool = True) -> ReadinessReport:
    checks: list[ReadinessCheck] = []

    windows_ok = _is_windows()
    checks.append(
        ReadinessCheck(
            id="windows",
            title="Windows platform",
            ok=windows_ok,
            severity="error" if not windows_ok else "info",
            status=BLOCKED_NO_DESKTOP if not windows_ok else READY,
            detail=sys.platform,
            fix="KangkangWeather only supports Windows 10/11 for WeChat automation.",
        )
    )

    desktop_ok, desktop_name = _input_desktop_name()
    desktop_ready = desktop_ok and desktop_name.lower() == "default"
    checks.append(
        ReadinessCheck(
            id="interactive_desktop",
            title="Interactive desktop",
            ok=desktop_ready,
            severity="error" if not desktop_ready else "info",
            status=READY if desktop_ready else (BLOCKED_LOCKED if desktop_ok else BLOCKED_NO_DESKTOP),
            detail=f"desktop={desktop_name}",
            fix="Keep the user logged in and unlocked. The display may turn off, but Windows must not sleep, lock, or log off.",
        )
    )

    session_id = _current_session_id()
    session_ok = session_id is not None and session_id > 0
    checks.append(
        ReadinessCheck(
            id="session",
            title="User session",
            ok=session_ok,
            severity="error" if not session_ok else "info",
            status=BLOCKED_NO_DESKTOP if not session_ok else READY,
            detail=f"session_id={session_id}",
            fix="Run KangkangWeather in the logged-in user session, not as a service or SYSTEM task.",
        )
    )

    if _rdp_session():
        checks.append(
            ReadinessCheck(
                id="rdp",
                title="Remote Desktop",
                ok=True,
                severity="warn",
                status=WARNING_RDP,
                detail=f"SESSIONNAME={os.environ.get('SESSIONNAME')}",
                fix="Avoid minimizing or disconnecting RDP while WeChat automation is sending.",
            )
        )

    clip_ok, clip_detail = _clipboard_available()
    checks.append(
        ReadinessCheck(
            id="clipboard",
            title="Clipboard",
            ok=clip_ok,
            severity="warn" if not clip_ok else "info",
            status=WARNING_CLIPBOARD if not clip_ok else READY,
            detail=clip_detail,
            fix="Close clipboard managers or remote clipboard sync if long message paste fails.",
        )
    )

    if require_wechat:
        probe = _wechat_window_probe()
        wechat_ok = bool(probe.get("found"))
        checks.append(
            ReadinessCheck(
                id="wechat_window",
                title="WeChat window",
                ok=wechat_ok,
                severity="error" if not wechat_ok else "info",
                status=BLOCKED_WECHAT_NOT_RUNNING if not wechat_ok else READY,
                detail=str(probe),
                fix="Open and log in to the official Windows WeChat client before sending.",
            )
        )
        if wechat_ok:
            accessible = bool(probe.get("has_search") or probe.get("has_input"))
            checks.append(
                ReadinessCheck(
                    id="wechat_accessible",
                    title="WeChat UI accessible",
                    ok=accessible,
                    severity="error" if not accessible else "info",
                    status=BLOCKED_WECHAT_WINDOW if not accessible else READY,
                    detail=str(probe.get("details")),
                    fix="Make sure WeChat is logged in, not showing a modal, and runs at the same privilege level as KangkangWeather.",
                )
            )
            current_admin = _is_admin()
            elevated_values = [
                value
                for value in (_token_elevated_for_pid(int(pid)) for pid in probe.get("pids", []))
                if value is not None
            ]
            if elevated_values:
                same_privilege = any(value == current_admin for value in elevated_values)
                checks.append(
                    ReadinessCheck(
                        id="privilege_level",
                        title="Privilege level",
                        ok=same_privilege,
                        severity="error" if not same_privilege else "info",
                        status=BLOCKED_PRIVILEGE if not same_privilege else READY,
                        detail=f"kangkang_admin={current_admin}, wechat_admin_values={elevated_values}",
                        fix="Run WeChat and KangkangWeather at the same privilege level. The recommended mode is both as normal user.",
                    )
                )

    blocking = next((item for item in checks if not item.ok and item.severity == "error"), None)
    if blocking:
        return ReadinessReport(
            ok=False,
            status=blocking.status,
            can_send_now=False,
            can_retry_later=blocking.status
            in {BLOCKED_LOCKED, BLOCKED_NO_DESKTOP, BLOCKED_WECHAT_NOT_RUNNING, BLOCKED_WECHAT_WINDOW},
            generated_at=datetime.now().isoformat(timespec="seconds"),
            title="Current environment cannot send automatically",
            detail=blocking.detail,
            checks=checks,
        )
    return ReadinessReport(
        ok=True,
        status=READY,
        can_send_now=True,
        can_retry_later=False,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        title="Ready to send",
        detail="The current Windows session can run foreground WeChat automation.",
        checks=checks,
    )
