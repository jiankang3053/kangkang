# -*- coding: utf-8 -*-
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from importlib.util import find_spec
import time
from typing import Protocol


@dataclass(frozen=True)
class SendResult:
    ok: bool
    backend: str
    contact: str
    detail: str = ""
    preview: str = ""
    diagnostics: list[str] = field(default_factory=list)


class Sender(Protocol):
    def send(self, contact: str, message: str) -> SendResult:
        ...


class DryRunSender:
    def send(self, contact: str, message: str) -> SendResult:
        return SendResult(
            ok=True,
            backend="dry-run",
            contact=contact,
            detail="没有调用微信，只生成了待发送内容。",
            preview=message,
        )


class WxautoSender:
    """Thin adapter around cluic/wxauto.

    wxauto is intentionally imported lazily so preview/dry-run still works on
    machines where the WeChat automation dependency is not installed yet.
    """

    def __init__(self) -> None:
        try:
            from wxauto import WeChat
        except Exception as exc:  # pragma: no cover - depends on local machine
            raise RuntimeError(
                "没有成功导入 wxauto。请先执行：python -m pip install wxauto"
            ) from exc

        self._wechat = WeChat()

    def send(self, contact: str, message: str) -> SendResult:
        try:
            result = self._wechat.SendMsg(message, contact)
        except Exception as exc:  # pragma: no cover - depends on local WeChat UI
            return SendResult(
                ok=False,
                backend="wxauto",
                contact=contact,
                detail=f"wxauto.SendMsg 调用失败：{exc}",
                preview=message,
            )

        return SendResult(
            ok=True,
            backend="wxauto",
            contact=contact,
            detail=f"wxauto.SendMsg 返回：{result!r}",
            preview=message,
        )


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


class _KeybdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_uint),
        ("time", ctypes.c_uint),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeybdInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint), ("union", _InputUnion)]


def _send_unicode_char(char: str) -> None:
    send_input = ctypes.windll.user32.SendInput
    codepoint = ord(char)
    press = _Input(
        type=INPUT_KEYBOARD,
        union=_InputUnion(ki=_KeybdInput(0, codepoint, KEYEVENTF_UNICODE, 0, None)),
    )
    release = _Input(
        type=INPUT_KEYBOARD,
        union=_InputUnion(
            ki=_KeybdInput(0, codepoint, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)
        ),
    )
    send_input(1, ctypes.byref(press), ctypes.sizeof(_Input))
    send_input(1, ctypes.byref(release), ctypes.sizeof(_Input))


def _press_enter() -> None:
    send_input = ctypes.windll.user32.SendInput
    press = _Input(
        type=INPUT_KEYBOARD,
        union=_InputUnion(ki=_KeybdInput(VK_RETURN, 0, 0, 0, None)),
    )
    release = _Input(
        type=INPUT_KEYBOARD,
        union=_InputUnion(ki=_KeybdInput(VK_RETURN, 0, KEYEVENTF_KEYUP, 0, None)),
    )
    send_input(1, ctypes.byref(press), ctypes.sizeof(_Input))
    send_input(1, ctypes.byref(release), ctypes.sizeof(_Input))


def _set_clipboard_text(text: str) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

    if not user32.OpenClipboard(None):
        raise RuntimeError("无法打开 Windows 剪贴板。")
    try:
        user32.EmptyClipboard()
        data = (text + "\0").encode("utf-16le")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise RuntimeError("Windows 剪贴板内存分配失败。")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise RuntimeError("Windows 剪贴板内存锁定失败。")
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise RuntimeError("写入 Windows 剪贴板失败。")
    finally:
        user32.CloseClipboard()


def _click_send_button(window) -> bool:
    deadline = time.time() + 2.0
    while time.time() < deadline:
        for button in window.descendants(control_type="Button"):
            try:
                if button.window_text() == "发送":
                    button.click_input()
                    return True
            except Exception:
                continue
        time.sleep(0.1)
    return False


class PywinautoActiveChatSender:
    """Fallback sender for the currently open WeChat chat window.

    This backend deliberately does not search or switch contacts. It types into
    the active chat input of the discovered Weixin main window and presses Enter.
    """

    def __init__(self, window_handle: int | None = None) -> None:
        if find_spec("pywinauto") is None:
            raise RuntimeError("没有成功导入 pywinauto。请先执行：python -m pip install pywinauto")
        self._window_handle = window_handle

    def _resolve_window(self):
        from pywinauto import Application, Desktop

        if self._window_handle is not None:
            app = Application(backend="uia").connect(handle=self._window_handle)
            return app.window(handle=self._window_handle)

        desktop = Desktop(backend="uia")
        candidates = []
        for window in desktop.windows():
            title = window.window_text()
            class_name = window.class_name()
            marker = f"{title} {class_name}"
            if "Weixin" in marker or "微信" in marker or "WeChat" in marker:
                candidates.append(window)

        main_windows = [w for w in candidates if w.class_name() == "mmui::MainWindow"]
        if main_windows:
            return main_windows[0]
        if candidates:
            return candidates[0]
        raise RuntimeError("没有找到微信主窗口。请先打开并登录 Windows 微信。")

    @staticmethod
    def _current_chat_name(window) -> str:
        for child in window.descendants():
            try:
                if child.element_info.automation_id.endswith("current_chat_name_label"):
                    return child.window_text()
            except Exception:
                continue
        return ""

    @staticmethod
    def _has_chat_input(window) -> bool:
        try:
            window.child_window(auto_id="chat_input_field", control_type="Edit").wrapper_object()
            return True
        except Exception:
            return False

    @staticmethod
    def _wait_for_chat(window, contact: str, timeout: float = 2.0) -> str:
        deadline = time.time() + timeout
        current = ""
        while time.time() < deadline:
            current = PywinautoActiveChatSender._current_chat_name(window)
            if current == contact and PywinautoActiveChatSender._has_chat_input(window):
                return current
            time.sleep(0.2)
        return current or PywinautoActiveChatSender._current_chat_name(window)

    @staticmethod
    def _open_visible_session(window, contact: str) -> str:
        session_id = f"session_item_{contact}"
        target = None
        alternate = None
        for child in window.descendants(control_type="ListItem"):
            try:
                if child.element_info.automation_id == session_id:
                    target = child
                elif alternate is None and child.class_name() == "mmui::ChatSessionCell":
                    alternate = child
            except Exception:
                continue

        if target is None:
            return PywinautoActiveChatSender._current_chat_name(window)

        target.click_input()
        current = PywinautoActiveChatSender._wait_for_chat(window, contact)
        if current == contact:
            return current

        # Weixin sometimes leaves the right pane blank when re-clicking the
        # selected session. Switching away and back forces the detail pane to load.
        if alternate is not None:
            alternate.click_input()
            time.sleep(0.5)
            target.click_input()
            current = PywinautoActiveChatSender._wait_for_chat(window, contact, timeout=4.0)

        return current

    @staticmethod
    def _send_message_to_open_chat(window, message: str) -> None:
        from pywinauto.keyboard import send_keys

        edit = window.child_window(
            auto_id="chat_input_field",
            control_type="Edit",
        ).wrapper_object()
        edit.click_input()
        send_keys("^a{BACKSPACE}")
        time.sleep(0.2)
        _set_clipboard_text(message)
        send_keys("^v")
        time.sleep(0.5)
        if not _click_send_button(window):
            _press_enter()

    def send(self, contact: str, message: str) -> SendResult:
        try:
            window = self._resolve_window()
            window.restore()
            window.set_focus()
            current_chat = self._current_chat_name(window)
            active_aliases = {"当前聊天", "CURRENT_CHAT", "active", "ACTIVE_CHAT"}
            if contact not in active_aliases and contact != current_chat:
                return SendResult(
                    ok=False,
                    backend="pywinauto-active",
                    contact=contact,
                    detail=(
                        "当前微信聊天是 "
                        f"{current_chat!r}，不是目标 {contact!r}；已取消发送。"
                    ),
                    preview=message,
                )

            self._send_message_to_open_chat(window, message)
        except Exception as exc:  # pragma: no cover - depends on local WeChat UI
            return SendResult(
                ok=False,
                backend="pywinauto-active",
                contact=contact,
                detail=f"pywinauto-active 发送失败：{exc}",
                preview=message,
            )

        return SendResult(
            ok=True,
            backend="pywinauto-active",
            contact=contact,
            detail=(
                "已发送到当前微信主窗口打开的聊天；此后端不会自动切换联系人。"
                f" current_chat={current_chat!r}"
            ),
            preview=message,
        )


class PywinautoSessionSender(PywinautoActiveChatSender):
    """Sender that opens a visible left-side session before sending."""

    def send(self, contact: str, message: str) -> SendResult:
        try:
            window = self._resolve_window()
            window.restore()
            window.set_focus()
            current_chat = self._open_visible_session(window, contact)
            if current_chat != contact:
                return SendResult(
                    ok=False,
                    backend="pywinauto-session",
                    contact=contact,
                    detail=(
                        f"没有成功打开目标会话。当前微信聊天是 {current_chat!r}，"
                        f"目标是 {contact!r}。请把目标会话置顶或保持在左侧列表可见。"
                    ),
                    preview=message,
                )

            self._send_message_to_open_chat(window, message)
        except Exception as exc:  # pragma: no cover - depends on local WeChat UI
            return SendResult(
                ok=False,
                backend="pywinauto-session",
                contact=contact,
                detail=f"pywinauto-session 发送失败：{exc}",
                preview=message,
            )

        return SendResult(
            ok=True,
            backend="pywinauto-session",
            contact=contact,
            detail=f"已打开并发送到目标会话 {contact!r}。",
            preview=message,
        )


def choose_sender(
    real_send: bool,
    backend: str = "auto",
    window_handle: int | None = None,
) -> Sender:
    if not real_send:
        return DryRunSender()
    if backend in {"auto", "wxauto"}:
        return WxautoSender()
    if backend == "pywinauto-active":
        return PywinautoActiveChatSender(window_handle=window_handle)
    if backend == "pywinauto-session":
        return PywinautoSessionSender(window_handle=window_handle)
    raise ValueError(f"未知后端：{backend}")


def collect_diagnostics() -> list[str]:
    lines: list[str] = []
    import sys

    lines.append(f"python: {sys.version.split()[0]}")
    lines.append("wxauto documented Python range: 3.9-3.12")
    lines.append(f"wxauto installed: {find_spec('wxauto') is not None}")
    lines.append(f"pywinauto installed: {find_spec('pywinauto') is not None}")
    lines.append(f"requests installed: {find_spec('requests') is not None}")

    if find_spec("pywinauto") is None:
        return lines

    try:
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")
        matches = []
        for window in desktop.windows():
            title = window.window_text()
            class_name = window.class_name()
            if any(token in f"{title} {class_name}" for token in ["微信", "WeChat", "Weixin"]):
                matches.append(
                    f"title={title!r}, class={class_name!r}, handle={window.handle}"
                )
        if matches:
            lines.append("WeChat-like top windows:")
            lines.extend(f"- {item}" for item in matches[:10])
            for window in desktop.windows():
                if window.class_name() == "mmui::MainWindow":
                    current_chat = PywinautoActiveChatSender._current_chat_name(window)
                    if current_chat:
                        lines.append(f"current Weixin chat: {current_chat!r}")
                        break
        else:
            lines.append("没有在顶层窗口里找到明显的微信窗口。")
    except Exception as exc:  # pragma: no cover - depends on Windows UI state
        lines.append(f"UIAutomation 诊断失败：{exc}")

    return lines
