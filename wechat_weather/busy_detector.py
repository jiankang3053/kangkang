# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .config import DoNotDisturbConfig


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


@dataclass(frozen=True)
class ForegroundWindowInfo:
    hwnd: int | None
    process_id: int | None
    process_name: str | None
    fullscreen: bool
    matched_keyword: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BusyCheckResult:
    busy: bool
    reason: str
    action: str
    delay_minutes: int
    max_delay_minutes: int
    process_name: str | None = None
    fullscreen: bool = False
    matched_keyword: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BusyDetector:
    def __init__(self, config: DoNotDisturbConfig) -> None:
        self.config = config

    def _user32(self):
        return ctypes.windll.user32

    def _kernel32(self):
        return ctypes.windll.kernel32

    def _foreground_hwnd(self) -> int | None:
        try:
            hwnd = int(self._user32().GetForegroundWindow())
            return hwnd or None
        except Exception:
            return None

    def _window_rect(self, hwnd: int) -> tuple[int, int, int, int] | None:
        rect = wintypes.RECT()
        if not self._user32().GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return None
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)

    def _screen_rect(self) -> tuple[int, int]:
        return int(self._user32().GetSystemMetrics(0)), int(self._user32().GetSystemMetrics(1))

    def _process_id(self, hwnd: int) -> int | None:
        pid = wintypes.DWORD()
        self._user32().GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        return int(pid.value) or None

    def _process_name(self, pid: int | None) -> str | None:
        if not pid:
            return None
        kernel32 = self._kernel32()
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            query = getattr(kernel32, "QueryFullProcessImageNameW", None)
            if not query:
                return None
            if not query(handle, 0, buffer, ctypes.byref(size)):
                return None
            return Path(buffer.value).name
        finally:
            kernel32.CloseHandle(handle)

    def _matched_title_keyword(self, hwnd: int) -> str | None:
        if not self.config.window_title_keywords:
            return None
        try:
            length = int(self._user32().GetWindowTextLengthW(wintypes.HWND(hwnd)))
            if length <= 0:
                return None
            buffer = ctypes.create_unicode_buffer(min(length + 1, 512))
            self._user32().GetWindowTextW(wintypes.HWND(hwnd), buffer, len(buffer))
            title = buffer.value
        except Exception:
            return None
        lowered = title.lower()
        for keyword in self.config.window_title_keywords:
            text = str(keyword).strip()
            if text and text.lower() in lowered:
                return text
        return None

    def is_fullscreen_window(self, hwnd: int | None = None) -> bool:
        hwnd = hwnd or self._foreground_hwnd()
        if not hwnd:
            return False
        rect = self._window_rect(hwnd)
        if not rect:
            return False
        left, top, right, bottom = rect
        width = max(0, right - left)
        height = max(0, bottom - top)
        screen_width, screen_height = self._screen_rect()
        if screen_width <= 0 or screen_height <= 0:
            return False
        return width >= screen_width - 8 and height >= screen_height - 8 and left <= 8 and top <= 8

    def get_foreground_window_info(self) -> ForegroundWindowInfo:
        hwnd = self._foreground_hwnd()
        if not hwnd:
            return ForegroundWindowInfo(None, None, None, False)
        pid = self._process_id(hwnd)
        return ForegroundWindowInfo(
            hwnd=hwnd,
            process_id=pid,
            process_name=self._process_name(pid),
            fullscreen=self.is_fullscreen_window(hwnd),
            matched_keyword=self._matched_title_keyword(hwnd),
        )

    def is_busy_process(self, process_name: str | None) -> bool:
        if not process_name:
            return False
        blocked = {str(item).lower() for item in self.config.process_blocklist}
        return process_name.lower() in blocked

    def should_delay_send(self) -> BusyCheckResult:
        if not self.config.enabled or self.config.busy_action == "force_send":
            return BusyCheckResult(
                busy=False,
                reason="disabled",
                action=self.config.busy_action,
                delay_minutes=self.config.delay_minutes,
                max_delay_minutes=self.config.max_delay_minutes,
                detail="勿扰检测未启用或已设置强制发送。",
            )
        try:
            info = self.get_foreground_window_info()
        except Exception as exc:
            return BusyCheckResult(
                busy=False,
                reason="detect_failed",
                action=self.config.busy_action,
                delay_minutes=self.config.delay_minutes,
                max_delay_minutes=self.config.max_delay_minutes,
                detail=f"忙碌检测失败，按不忙碌处理：{exc}",
            )
        if self.config.detect_fullscreen and info.fullscreen:
            return BusyCheckResult(
                busy=True,
                reason="fullscreen_window",
                action=self.config.busy_action,
                delay_minutes=self.config.delay_minutes,
                max_delay_minutes=self.config.max_delay_minutes,
                process_name=info.process_name,
                fullscreen=True,
                matched_keyword=info.matched_keyword,
                detail="检测到前台全屏窗口，暂不打开微信抢焦点。",
            )
        if self.config.detect_game_process and self.is_busy_process(info.process_name):
            return BusyCheckResult(
                busy=True,
                reason="busy_process",
                action=self.config.busy_action,
                delay_minutes=self.config.delay_minutes,
                max_delay_minutes=self.config.max_delay_minutes,
                process_name=info.process_name,
                fullscreen=info.fullscreen,
                matched_keyword=info.matched_keyword,
                detail="检测到游戏/视频/演示类前台进程，暂不打开微信。",
            )
        if self.config.detect_foreground_busy_app and info.matched_keyword:
            return BusyCheckResult(
                busy=True,
                reason="busy_window_keyword",
                action=self.config.busy_action,
                delay_minutes=self.config.delay_minutes,
                max_delay_minutes=self.config.max_delay_minutes,
                process_name=info.process_name,
                fullscreen=info.fullscreen,
                matched_keyword=info.matched_keyword,
                detail="检测到前台窗口关键词命中勿扰规则，暂不打开微信。",
            )
        return BusyCheckResult(
            busy=False,
            reason="idle",
            action=self.config.busy_action,
            delay_minutes=self.config.delay_minutes,
            max_delay_minutes=self.config.max_delay_minutes,
            process_name=info.process_name,
            fullscreen=info.fullscreen,
            matched_keyword=info.matched_keyword,
            detail="未检测到忙碌状态。",
        )
