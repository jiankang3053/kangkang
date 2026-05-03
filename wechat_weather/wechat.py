# -*- coding: utf-8 -*-
from __future__ import annotations

import ctypes
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib.util import find_spec
import time
from typing import Any, Protocol

from .error_analysis import analyze_error


@dataclass(frozen=True)
class SendResult:
    ok: bool
    backend: str
    contact: str
    detail: str = ""
    preview: str = ""
    diagnostics: list[str] = field(default_factory=list)
    error_analysis: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.ok and self.error_analysis is None:
            object.__setattr__(
                self,
                "error_analysis",
                analyze_error(self.detail, self.diagnostics, context=self.backend).to_dict(),
            )


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
VK_CONTROL = 0x11
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
DEFAULT_TEST_MESSAGE = "康康天气测试消息：如果你收到这条，说明微信发送链路正常。"
WECHAT_MAIN_CLASS = "mmui::MainWindow"
WECHAT_WINDOW_MARKERS = ("微信", "WeChat", "Weixin")


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


def _send_virtual_key(vk_code: int, flags: int = 0) -> None:
    send_input = ctypes.windll.user32.SendInput
    event = _Input(
        type=INPUT_KEYBOARD,
        union=_InputUnion(ki=_KeybdInput(vk_code, 0, flags, 0, None)),
    )
    send_input(1, ctypes.byref(event), ctypes.sizeof(_Input))


def _press_enter(ctrl: bool = False) -> None:
    if ctrl:
        _send_virtual_key(VK_CONTROL)
        time.sleep(0.03)
    try:
        _send_virtual_key(VK_RETURN)
        time.sleep(0.03)
        _send_virtual_key(VK_RETURN, KEYEVENTF_KEYUP)
    finally:
        if ctrl:
            time.sleep(0.03)
            _send_virtual_key(VK_CONTROL, KEYEVENTF_KEYUP)


def _open_clipboard_with_retry(attempts: int = 8, delay: float = 0.08) -> None:
    user32 = ctypes.windll.user32
    last_error = "无法打开 Windows 剪贴板。"
    for _ in range(attempts):
        if user32.OpenClipboard(None):
            return
        time.sleep(delay)
    raise RuntimeError(last_error)


def _get_clipboard_text() -> str | None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    _open_clipboard_with_retry()
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _set_clipboard_text_once(text: str) -> None:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

    _open_clipboard_with_retry()
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


def _set_clipboard_text(text: str, attempts: int = 3) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            _set_clipboard_text_once(text)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.12)
    if last_error is not None:
        raise last_error


@contextmanager
def _temporary_clipboard_text(text: str, diagnostics: list[str]):
    previous: str | None = None
    has_previous = False
    try:
        previous = _get_clipboard_text()
        has_previous = previous is not None
        diagnostics.append("clipboard: 已保存当前文本剪贴板。")
    except Exception as exc:
        diagnostics.append(f"clipboard: 保存当前剪贴板失败，将继续发送：{exc}")

    _set_clipboard_text(text)
    diagnostics.append("clipboard: 已写入待发送消息。")
    try:
        yield
    finally:
        if has_previous:
            try:
                _set_clipboard_text(previous or "")
                diagnostics.append("clipboard: 已恢复原文本剪贴板。")
            except Exception as exc:
                diagnostics.append(f"clipboard: 恢复原文本剪贴板失败：{exc}")


def _send_keys(sequence: str) -> None:
    from pywinauto.keyboard import send_keys

    send_keys(sequence)


def _type_text_directly(text: str, diagnostics: list[str], label: str = "type_fallback") -> None:
    diagnostics.append(f"{label}: 剪贴板不可用，改用 Unicode 直接输入。")
    for index, char in enumerate(text):
        if char == "\r":
            continue
        _send_unicode_char(char)
        if index and index % 80 == 0:
            time.sleep(0.01)
    diagnostics.append(f"{label}: 已完成 Unicode 直接输入。")


def _set_input_text_directly(
    edit,
    text: str,
    diagnostics: list[str],
    label: str = "type_fallback",
) -> bool:
    setters = (
        ("set_edit_text", lambda: edit.set_edit_text(text)),
        ("set_text", lambda: edit.set_text(text)),
        ("uia_value", lambda: edit.iface_value.SetValue(text)),
    )
    for name, setter in setters:
        try:
            setter()
            diagnostics.append(f"{label}: 已通过 {name} 写入输入框。")
            return True
        except Exception as exc:
            diagnostics.append(f"{label}: {name} 写入失败：{exc}")
    return False


def _button_label(button) -> str:
    parts = []
    try:
        parts.append(button.window_text())
    except Exception:
        pass
    try:
        parts.append(button.element_info.name)
    except Exception:
        pass
    return " ".join(part for part in parts if part).strip()


def _find_send_button(window, timeout: float = 2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for button in window.descendants(control_type="Button"):
            try:
                label = _button_label(button)
                if not label or not label.startswith("发送"):
                    continue
                if hasattr(button, "is_enabled") and not button.is_enabled():
                    continue
                return button
            except Exception:
                continue
        time.sleep(0.1)
    return None


def _click_button(button, diagnostics: list[str] | None = None) -> None:
    diagnostics = diagnostics if diagnostics is not None else []
    try:
        if hasattr(button, "invoke"):
            button.invoke()
            diagnostics.append("send_button: 已通过 UIA invoke 点击发送。")
            return
    except Exception as exc:
        diagnostics.append(f"send_button: UIA invoke 失败，尝试 click_input：{exc}")
    try:
        button.click_input()
        diagnostics.append("send_button: 已通过 click_input 点击发送。")
        return
    except Exception as exc:
        diagnostics.append(f"send_button: click_input 失败，尝试坐标点击：{exc}")
    try:
        from pywinauto.mouse import click

        rect = button.rectangle()
        click(button="left", coords=((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2))
        diagnostics.append("send_button: 已通过按钮中心坐标点击发送。")
        return
    except Exception as exc:
        raise RuntimeError(f"找到了发送按钮，但点击失败：{exc}") from exc


def _click_button_method(button, method: str, diagnostics: list[str]) -> None:
    if method == "invoke":
        if not hasattr(button, "invoke"):
            raise RuntimeError("按钮不支持 UIA invoke。")
        button.invoke()
        diagnostics.append("send_button: 已尝试 UIA invoke 发送。")
        return
    if method == "click_input":
        if not hasattr(button, "click_input"):
            raise RuntimeError("按钮不支持 click_input。")
        button.click_input()
        diagnostics.append("send_button: 已尝试 click_input 发送。")
        return
    if method == "coordinate":
        from pywinauto.mouse import click

        rect = button.rectangle()
        click(button="left", coords=((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2))
        diagnostics.append("send_button: 已尝试按钮中心坐标发送。")
        return
    raise ValueError(method)


def _wait_for_send_confirmation(
    window,
    edit,
    marker: str,
    diagnostics: list[str],
    timeout: float = 1.8,
) -> bool:
    deadline = time.time() + timeout
    last_text: str | None = None
    while time.time() < deadline:
        visible_text = _read_input_text(edit)
        if visible_text is not None:
            last_text = visible_text
            if not visible_text.strip() or (marker and marker not in visible_text):
                diagnostics.append("send_verify: 输入框已清空或不再包含消息标记。")
                return True
        elif _find_send_button(window, timeout=0.05) is None:
            diagnostics.append("send_verify: 输入框文本不可读，发送按钮已消失，按已发送处理。")
            return True
        time.sleep(0.15)

    if last_text is None:
        diagnostics.append("send_verify: 无法读取输入框文本，也无法确认发送按钮状态。")
    elif marker and marker in last_text:
        diagnostics.append("send_verify: 发送尝试后消息仍停留在输入框。")
    else:
        diagnostics.append("send_verify: 发送尝试后未确认输入框清空。")
    return False


def _click_send_button_verified(
    window,
    edit,
    send_button,
    marker: str,
    diagnostics: list[str],
    allow_coordinate: bool = False,
) -> None:
    errors: list[str] = []
    methods = ["invoke", "click_input"]
    if allow_coordinate:
        methods.append("coordinate")
    else:
        diagnostics.append("send_button: 坐标点击兜底未启用，跳过按钮中心坐标点击。")
    for index, method in enumerate(methods, start=1):
        button = send_button if index == 1 else (_find_send_button(window, timeout=0.4) or send_button)
        try:
            _click_button_method(button, method, diagnostics)
            if _wait_for_send_confirmation(window, edit, marker, diagnostics):
                diagnostics.append(f"send_verify: 第 {index} 种发送方式已确认成功。")
                return
        except Exception as exc:
            errors.append(f"{method}: {exc}")
            diagnostics.append(f"send_button: {method} 发送尝试失败：{exc}")
    raise RuntimeError(
        "点击发送后消息仍停留在输入框，已判定发送失败。"
        "请确认微信输入框右侧“发送”按钮可点击，或手动点击一次发送后重试。"
        + (f" 发送尝试错误：{'; '.join(errors)}" if errors else "")
    )


def _keyboard_send_attempts(strategy: str) -> list[tuple[str, str, str]]:
    if strategy == "ctrl_enter_first":
        return [
            ("Ctrl+Enter", "^{ENTER}", "ctrl_enter"),
            ("Enter", "{ENTER}", "enter"),
        ]
    if strategy == "enter_only":
        return [("Enter", "{ENTER}", "enter")]
    return [
        ("Enter", "{ENTER}", "enter"),
        ("Ctrl+Enter", "^{ENTER}", "ctrl_enter"),
    ]


def _send_with_keyboard_verified(
    window,
    edit,
    marker: str,
    diagnostics: list[str],
    strategy: str = "enter_first",
) -> None:
    errors: list[str] = []
    for label, keys, key_name in _keyboard_send_attempts(strategy):
        try:
            _focus_chat_input(edit, diagnostics)
            _send_keys(keys)
            diagnostics.append(f"send_key: 已尝试 {label} 发送。")
            if _wait_for_send_confirmation(window, edit, marker, diagnostics):
                diagnostics.append(f"send_verify: paste_ok -> {key_name} -> verified")
                return
            diagnostics.append(f"send_key: {label} 后未确认提交。")
            _focus_chat_input(edit, diagnostics)
            _press_enter(ctrl=key_name == "ctrl_enter")
            diagnostics.append(f"send_key: 已尝试 {label} 原生键盘发送。")
            if _wait_for_send_confirmation(window, edit, marker, diagnostics):
                diagnostics.append(f"send_verify: paste_ok -> {key_name}_native -> verified")
                return
            diagnostics.append(f"send_key: {label} 原生键盘后未确认提交。")
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            diagnostics.append(f"send_key: {label} 发送尝试失败：{exc}")

    raise RuntimeError(
        "消息已粘贴但没有提交发送。已尝试 Enter 和 Ctrl+Enter，输入框仍包含待发送内容。"
        + (f" 键盘发送错误：{'; '.join(errors)}" if errors else "")
    )


def _click_send_button(window, diagnostics: list[str] | None = None) -> bool:
    diagnostics = diagnostics if diagnostics is not None else []
    button = _find_send_button(window)
    if button is None:
        diagnostics.append("send_button: 未找到明确可点击的发送按钮。")
        return False
    _click_button(button, diagnostics)
    return True


def _read_input_text(edit) -> str | None:
    candidates: list[str] = []
    readable = False
    for getter in (
        lambda: edit.window_text(),
        lambda: edit.element_info.name,
        lambda: edit.iface_value.CurrentValue,
    ):
        try:
            value = getter()
            readable = True
            if value is not None:
                candidates.append(str(value))
        except Exception:
            continue
    if not candidates:
        return "" if readable else None
    return max(candidates, key=len)


def _message_marker(message: str) -> str:
    compact_lines = [line.strip() for line in message.splitlines() if line.strip()]
    marker = compact_lines[0] if compact_lines else message.strip()
    return marker[:24]


def _safe_window_text(window) -> str:
    try:
        return str(window.window_text() or "")
    except Exception:
        return ""


def _safe_class_name(window) -> str:
    try:
        return str(window.class_name() or "")
    except Exception:
        return ""


def _safe_handle(window) -> int | str:
    try:
        return getattr(window, "handle")
    except Exception:
        return "<unknown>"


def _safe_process_id(window) -> int | None:
    for getter in (
        lambda: window.process_id(),
        lambda: window.element_info.process_id,
    ):
        try:
            value = getter()
            if value:
                return int(value)
        except Exception:
            continue
    return None


def _process_exe_path(process_id: int | None) -> str:
    if not process_id:
        return ""
    try:
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
        if not handle:
            return ""
        try:
            size = ctypes.c_uint(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            query = kernel32.QueryFullProcessImageNameW
            query.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint)]
            query.restype = ctypes.c_int
            if query(handle, 0, buffer, ctypes.byref(size)):
                return buffer.value
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""
    return ""


def _describe_window(window) -> str:
    process_id = _safe_process_id(window)
    exe_path = _process_exe_path(process_id)
    pieces = [
        f"title={_safe_window_text(window)!r}",
        f"class={_safe_class_name(window)!r}",
        f"handle={_safe_handle(window)!r}",
    ]
    if process_id:
        pieces.append(f"pid={process_id}")
    if exe_path:
        pieces.append(f"exe={exe_path!r}")
    return ", ".join(pieces)


def _ensure_window_available(window, diagnostics: list[str], stage: str) -> None:
    try:
        if hasattr(window, "exists") and not window.exists(timeout=0.2):
            raise RuntimeError("window.exists returned False")
        if hasattr(window, "window_text"):
            window.window_text()
        if hasattr(window, "class_name"):
            window.class_name()
    except Exception as exc:
        diagnostics.append(f"window: {stage} 检测到微信窗口已退出或不可访问：{exc}")
        raise RuntimeError(
            f"微信窗口已退出或不可访问（{stage}）。请重新打开并登录微信，再重试。"
        ) from exc


def _focus_edit_without_coordinates(edit, diagnostics: list[str], label: str) -> None:
    try:
        edit.click_input()
        diagnostics.append(f"{label}: 已通过 click_input 聚焦。")
        time.sleep(0.12)
    except Exception as exc:
        diagnostics.append(f"{label}: click_input 聚焦失败：{exc}")
        raise RuntimeError(f"找到了{label}，但无法聚焦；请确认微信与本程序使用同级权限运行。") from exc


def _edit_contains_text(edit, text: str) -> bool:
    expected = text.strip()
    visible_text = _read_input_text(edit)
    if visible_text is None:
        return False
    return expected in visible_text


def _clear_and_write_edit_text(
    edit,
    text: str,
    diagnostics: list[str],
    label: str,
    allow_clipboard_fallback: bool = True,
) -> bool:
    _focus_edit_without_coordinates(edit, diagnostics, label)
    if _set_input_text_directly(edit, "", diagnostics, label=label):
        diagnostics.append(f"{label}: 已通过 UIA 清空文本。")
    else:
        try:
            _send_keys("^a{BACKSPACE}")
            diagnostics.append(f"{label}: 已通过 Ctrl+A+Backspace 清空文本。")
        except Exception as exc:
            diagnostics.append(f"{label}: 清空文本失败：{exc}")

    time.sleep(0.12)
    if _set_input_text_directly(edit, text, diagnostics, label=label):
        time.sleep(0.35)
        if _edit_contains_text(edit, text):
            diagnostics.append(f"{label}: 已确认 UIA 写入结果。")
            return True
        diagnostics.append(f"{label}: UIA 写入后未读到目标文本，准备尝试 Unicode 输入。")

    try:
        _focus_edit_without_coordinates(edit, diagnostics, label)
        _send_keys("^a{BACKSPACE}")
        _type_text_directly(text, diagnostics, label=label)
        time.sleep(0.45)
        if _edit_contains_text(edit, text):
            diagnostics.append(f"{label}: 已确认 Unicode 输入结果。")
            return True
        diagnostics.append(f"{label}: Unicode 输入后未读到目标文本。")
    except Exception as exc:
        diagnostics.append(f"{label}: Unicode 输入失败：{exc}")

    if allow_clipboard_fallback:
        try:
            _focus_edit_without_coordinates(edit, diagnostics, label)
            _send_keys("^a{BACKSPACE}")
            with _temporary_clipboard_text(text, diagnostics):
                _send_keys("^v")
            diagnostics.append(f"{label}: 已执行剪贴板兜底粘贴。")
            time.sleep(0.45)
            if _edit_contains_text(edit, text):
                diagnostics.append(f"{label}: 已确认剪贴板兜底写入结果。")
                return True
            diagnostics.append(f"{label}: 剪贴板兜底后未读到目标文本。")
        except Exception as exc:
            diagnostics.append(f"{label}: 剪贴板兜底写入失败：{exc}")

    return False


def _focus_chat_input(edit, diagnostics: list[str]) -> None:
    try:
        edit.click_input()
        diagnostics.append("chat_input: 已通过 click_input 聚焦。")
        time.sleep(0.15)
        return
    except Exception as exc:
        diagnostics.append(f"chat_input: click_input 聚焦失败，尝试坐标点击：{exc}")
    try:
        from pywinauto.mouse import click

        rect = edit.rectangle()
        click(button="left", coords=((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2))
        diagnostics.append("chat_input: 已通过输入框中心坐标聚焦。")
        time.sleep(0.15)
    except Exception as exc:
        raise RuntimeError(f"找到了微信聊天输入框，但无法聚焦：{exc}") from exc


class PywinautoActiveChatSender:
    """Fallback sender for the currently open WeChat chat window.

    This backend deliberately does not search or switch contacts. It types into
    the active chat input of the discovered Weixin main window and presses Enter.
    """

    def __init__(
        self,
        window_handle: int | None = None,
        send_strategy: str = "enter_first",
        allow_send_button_coordinate_fallback: bool = False,
    ) -> None:
        if find_spec("pywinauto") is None:
            raise RuntimeError("没有成功导入 pywinauto。请先执行：python -m pip install pywinauto")
        self._window_handle = window_handle
        self._send_strategy = send_strategy or "enter_first"
        self._allow_send_button_coordinate_fallback = bool(
            allow_send_button_coordinate_fallback
        )

    def _resolve_window(self, diagnostics: list[str] | None = None):
        from pywinauto import Application, Desktop

        if self._window_handle is not None:
            app = Application(backend="uia").connect(handle=self._window_handle)
            window = app.window(handle=self._window_handle)
            if diagnostics is not None:
                diagnostics.append(f"window: 使用指定窗口句柄，{_describe_window(window)}")
            return window

        desktop = Desktop(backend="uia")
        candidates = []
        for window in desktop.windows():
            title = _safe_window_text(window)
            class_name = _safe_class_name(window)
            marker = f"{title} {class_name}"
            if class_name != WECHAT_MAIN_CLASS and not any(token in marker for token in WECHAT_WINDOW_MARKERS):
                continue

            score = 0
            if class_name == WECHAT_MAIN_CLASS:
                score += 80
            if any(token in marker for token in WECHAT_WINDOW_MARKERS):
                score += 25
            try:
                if hasattr(window, "is_visible") and window.is_visible():
                    score += 5
            except Exception:
                pass
            try:
                if self._search_edit(window) is not None:
                    score += 20
            except Exception:
                pass
            try:
                if self._has_chat_input(window):
                    score += 12
            except Exception:
                pass
            try:
                if self._current_chat_name(window):
                    score += 8
            except Exception:
                pass
            candidates.append((score, window))

        candidates.sort(key=lambda item: item[0], reverse=True)
        if diagnostics is not None and candidates:
            diagnostics.append("window: 微信候选窗口评分：")
            for score, candidate in candidates[:5]:
                diagnostics.append(f"window: score={score}, {_describe_window(candidate)}")
        if candidates:
            selected = candidates[0][1]
            if diagnostics is not None:
                diagnostics.append(f"window: 已选择微信窗口，{_describe_window(selected)}")
            return selected
        raise RuntimeError("没有找到微信主窗口。请先打开并登录 Windows 微信。")

    @staticmethod
    def _restore_and_focus_window(window, diagnostics: list[str]) -> None:
        _ensure_window_available(window, diagnostics, "聚焦前")
        try:
            window.restore()
            diagnostics.append("window: 已恢复微信主窗口。")
        except Exception as exc:
            diagnostics.append(f"window: 恢复窗口失败，继续尝试聚焦：{exc}")
        time.sleep(0.2)
        try:
            window.set_focus()
            diagnostics.append("window: 已聚焦微信主窗口。")
        except Exception as exc:
            diagnostics.append(f"window: 聚焦微信主窗口失败：{exc}")
            raise RuntimeError(
                "无法聚焦微信主窗口。请确认微信和本程序使用同级权限运行，例如不要一个管理员、一个普通用户。"
            ) from exc
        time.sleep(0.2)
        _ensure_window_available(window, diagnostics, "聚焦后")

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
    def _chat_input(window):
        for edit in window.descendants(control_type="Edit"):
            try:
                if edit.element_info.automation_id == "chat_input_field":
                    return edit
            except Exception:
                continue
        raise RuntimeError("没有找到微信聊天输入框。请先打开目标聊天。")

    @staticmethod
    def _has_chat_input(window) -> bool:
        try:
            PywinautoActiveChatSender._chat_input(window)
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
    def _search_edit(window):
        for edit in window.descendants(control_type="Edit"):
            try:
                if edit.class_name() == "mmui::XValidatorTextEdit":
                    return edit
                if edit.element_info.name == "搜索":
                    return edit
            except Exception:
                continue
        return None

    @staticmethod
    def _search_result_for_contact(window, contact: str):
        exact_name = None
        expected_id = f"search_item_{contact}"
        for child in window.descendants(control_type="ListItem"):
            try:
                automation_id = child.element_info.automation_id
                name = child.element_info.name
                text = child.window_text()
                if automation_id == expected_id:
                    return child
                if exact_name is None and (
                    name == contact
                    or text == contact
                    or (name and name.splitlines()[0] == contact)
                    or (text and text.splitlines()[0] == contact)
                ):
                    exact_name = child
            except Exception:
                continue
        return exact_name

    @staticmethod
    def _focus_search(window, diagnostics: list[str] | None = None):
        diagnostics = diagnostics if diagnostics is not None else []
        search = PywinautoActiveChatSender._search_edit(window)
        if search is not None:
            _focus_edit_without_coordinates(search, diagnostics, "search")
            return search

        diagnostics.append("search: 未找到微信搜索框，坐标点击兜底已禁用。")
        raise RuntimeError("找不到微信搜索框，已停止搜索，避免坐标误点。")

    @staticmethod
    def _open_session_from_search(
        window,
        contact: str,
        diagnostics: list[str] | None = None,
    ) -> str:
        diagnostics = diagnostics if diagnostics is not None else []
        _ensure_window_available(window, diagnostics, "搜索会话前")
        search = PywinautoActiveChatSender._focus_search(window, diagnostics)

        time.sleep(0.2)
        if not _clear_and_write_edit_text(search, contact, diagnostics, "search"):
            raise RuntimeError("搜索框写入目标名称失败，已停止搜索。")

        result = None
        deadline = time.time() + 4.0
        while time.time() < deadline:
            _ensure_window_available(window, diagnostics, "等待搜索结果")
            result = PywinautoActiveChatSender._search_result_for_contact(window, contact)
            if result is not None:
                diagnostics.append(f"search: 已找到精确匹配搜索结果 {contact!r}。")
                break
            time.sleep(0.2)

        if result is None:
            diagnostics.append(f"search: 未找到精确匹配搜索结果 {contact!r}，不会按回车盲开会话。")
            return PywinautoActiveChatSender._current_chat_name(window)

        try:
            result.click_input()
            diagnostics.append("search: 已点击精确匹配搜索结果。")
        except Exception as exc:
            diagnostics.append(f"search: 点击搜索结果失败：{exc}")
            raise RuntimeError(f"搜索到目标 {contact!r}，但无法点击打开。") from exc
        time.sleep(0.4)
        _ensure_window_available(window, diagnostics, "点击搜索结果后")
        current = PywinautoActiveChatSender._wait_for_chat(window, contact, timeout=5.0)
        if current == contact:
            return current

        diagnostics.append(f"search: 打开后聊天标题为 {current!r}，目标为 {contact!r}。")
        try:
            _send_keys("{ESC}")
        except Exception:
            pass
        return current

    @staticmethod
    def _open_visible_session(
        window,
        contact: str,
        diagnostics: list[str] | None = None,
    ) -> str:
        diagnostics = diagnostics if diagnostics is not None else []
        _ensure_window_available(window, diagnostics, "打开会话前")
        current = PywinautoActiveChatSender._current_chat_name(window)
        if current == contact and PywinautoActiveChatSender._has_chat_input(window):
            diagnostics.append("chat: 当前会话已匹配目标。")
            return current

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
            diagnostics.append("chat: 左侧可见会话未找到目标，改用搜索。")
            return PywinautoActiveChatSender._open_session_from_search(window, contact, diagnostics)

        target.click_input()
        diagnostics.append("chat: 已点击左侧可见目标会话。")
        _ensure_window_available(window, diagnostics, "点击左侧会话后")
        current = PywinautoActiveChatSender._wait_for_chat(window, contact)
        if current == contact:
            return current

        # Weixin sometimes leaves the right pane blank when re-clicking the
        # selected session. Switching away and back forces the detail pane to load.
        if alternate is not None:
            alternate.click_input()
            time.sleep(0.5)
            _ensure_window_available(window, diagnostics, "切换备用会话后")
            target.click_input()
            diagnostics.append("chat: 已再次点击目标会话。")
            current = PywinautoActiveChatSender._wait_for_chat(window, contact, timeout=4.0)

        if current != contact:
            diagnostics.append(f"chat: 左侧会话打开后标题为 {current!r}，改用搜索校验。")
            return PywinautoActiveChatSender._open_session_from_search(window, contact, diagnostics)
        return current

    @staticmethod
    def _send_message_to_open_chat(
        window,
        message: str,
        diagnostics: list[str] | None = None,
        send_strategy: str = "enter_first",
        allow_send_button_coordinate_fallback: bool = False,
    ) -> list[str]:
        diagnostics = diagnostics if diagnostics is not None else []
        if not message.strip():
            raise RuntimeError("待发送消息为空，已取消发送。")
        _ensure_window_available(window, diagnostics, "准备输入消息前")
        edit = PywinautoActiveChatSender._chat_input(window)
        diagnostics.append("chat_input: 已找到微信聊天输入框。")
        marker = _message_marker(message)
        paste_ok = False
        try:
            with _temporary_clipboard_text(message, diagnostics):
                for attempt in range(1, 3):
                    _focus_chat_input(edit, diagnostics)
                    _send_keys("^a")
                    diagnostics.append(f"paste: 第 {attempt} 次尝试已选择输入框内容。")
                    time.sleep(0.12)
                    _send_keys("^v")
                    diagnostics.append(f"paste: 第 {attempt} 次尝试已执行 Ctrl+V。")
                    time.sleep(0.7)

                    visible_text = _read_input_text(edit)
                    if visible_text is None:
                        if _find_send_button(window, timeout=0.2) is not None:
                            diagnostics.append("paste: 输入框文本不可读，但发送按钮已出现，按粘贴成功处理。")
                            paste_ok = True
                        else:
                            diagnostics.append("paste: 输入框未暴露可读取文本，且未检测到发送按钮。")
                    elif marker and marker in visible_text:
                        diagnostics.append("paste: 已通过输入框文本确认消息内容。")
                        paste_ok = True
                    else:
                        diagnostics.append("paste: 输入框文本无法确认完整消息，准备重试粘贴。")
                    if paste_ok:
                        diagnostics.append("paste_ok: 已确认消息进入输入框，准备键盘提交。")
                        break
        except Exception as exc:
            diagnostics.append(f"paste: 剪贴板粘贴流程失败，改用直接输入兜底：{exc}")

        if not paste_ok:
            _ensure_window_available(window, diagnostics, "直接输入兜底前")
            _focus_chat_input(edit, diagnostics)
            _send_keys("^a")
            diagnostics.append("type_fallback: 已选择输入框内容。")
            if not _set_input_text_directly(edit, message, diagnostics):
                _type_text_directly(message, diagnostics)
            time.sleep(0.4)
            visible_text = _read_input_text(edit)
            if visible_text is None:
                if _find_send_button(window, timeout=0.2) is not None:
                    diagnostics.append("type_fallback: 输入框文本不可读，但发送按钮已出现，按输入成功处理。")
                    paste_ok = True
                    diagnostics.append("paste_ok: 已确认消息进入输入框，准备键盘提交。")
                else:
                    diagnostics.append("type_fallback: 输入框文本不可读，无法确认直接输入结果。")
            elif marker and marker in visible_text:
                diagnostics.append("type_fallback: 已通过输入框文本确认消息内容。")
                paste_ok = True
                diagnostics.append("paste_ok: 已确认消息进入输入框，准备键盘提交。")
            elif _find_send_button(window, timeout=0.2) is not None and visible_text.strip():
                diagnostics.append("type_fallback: 输入框文本未包含完整标记，但已有可发送文本和发送按钮。")
                paste_ok = True
                diagnostics.append("paste_ok: 已确认消息进入输入框，准备键盘提交。")
            else:
                diagnostics.append("type_fallback: 输入框文本无法确认完整消息。")

        if not paste_ok:
            raise RuntimeError("消息没有成功粘贴到输入框，已取消发送。")

        _ensure_window_available(window, diagnostics, "提交发送前")
        try:
            _send_with_keyboard_verified(window, edit, marker, diagnostics, strategy=send_strategy)
            return diagnostics
        except RuntimeError:
            if not allow_send_button_coordinate_fallback:
                diagnostics.append("send_button: 按钮点击兜底未启用，已停止，避免误点表情或其他控件。")
                raise

        diagnostics.append("send_button: 已启用显式按钮兜底，键盘发送失败后尝试发送按钮。")
        send_button = _find_send_button(window)
        if send_button is None:
            raise RuntimeError("消息已粘贴但没有提交发送，且没有找到明确可点击的发送按钮。")
        _click_send_button_verified(
            window,
            edit,
            send_button,
            marker,
            diagnostics,
            allow_coordinate=allow_send_button_coordinate_fallback,
        )
        return diagnostics

    def send(self, contact: str, message: str) -> SendResult:
        diagnostics: list[str] = []
        try:
            window = self._resolve_window(diagnostics)
            diagnostics.append("window: 已找到微信主窗口。")
            self._restore_and_focus_window(window, diagnostics)
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
                    diagnostics=diagnostics,
                )

            self._send_message_to_open_chat(
                window,
                message,
                diagnostics,
                send_strategy=self._send_strategy,
                allow_send_button_coordinate_fallback=self._allow_send_button_coordinate_fallback,
            )
        except Exception as exc:  # pragma: no cover - depends on local WeChat UI
            return SendResult(
                ok=False,
                backend="pywinauto-active",
                contact=contact,
                detail=f"pywinauto-active 发送失败：{exc}",
                preview=message,
                diagnostics=diagnostics,
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
            diagnostics=diagnostics,
        )


class PywinautoSessionSender(PywinautoActiveChatSender):
    """Sender that opens a target chat before sending."""

    def open_target(self, contact: str) -> SendResult:
        diagnostics: list[str] = []
        try:
            window = self._resolve_window(diagnostics)
            diagnostics.append("window: 已找到微信主窗口。")
            self._restore_and_focus_window(window, diagnostics)
            current_chat = self._open_visible_session(window, contact, diagnostics)
            diagnostics.append(f"chat: 当前会话 {current_chat!r}。")
            if current_chat != contact:
                return SendResult(
                    ok=False,
                    backend="pywinauto-session",
                    contact=contact,
                    detail=(
                        f"没有成功打开目标会话。当前微信聊天是 {current_chat!r}，"
                        f"目标是 {contact!r}。请确认微信已登录，且好友/群名称与微信搜索结果完全一致。"
                    ),
                    diagnostics=diagnostics,
                )
            PywinautoActiveChatSender._chat_input(window)
            diagnostics.append("chat_input: 已找到微信聊天输入框。")
        except Exception as exc:  # pragma: no cover - depends on local WeChat UI
            return SendResult(
                ok=False,
                backend="pywinauto-session",
                contact=contact,
                detail=f"打开目标会话失败：{exc}",
                diagnostics=diagnostics,
            )

        return SendResult(
            ok=True,
            backend="pywinauto-session",
            contact=contact,
            detail=f"已打开并校验目标会话 {contact!r}，尚未发送任何消息。",
            diagnostics=diagnostics,
        )

    def send(self, contact: str, message: str) -> SendResult:
        diagnostics: list[str] = []
        try:
            window = self._resolve_window(diagnostics)
            diagnostics.append("window: 已找到微信主窗口。")
            self._restore_and_focus_window(window, diagnostics)
            current_chat = self._open_visible_session(window, contact, diagnostics)
            diagnostics.append(f"chat: 当前会话 {current_chat!r}。")
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
                    diagnostics=diagnostics,
                )

            self._send_message_to_open_chat(
                window,
                message,
                diagnostics,
                send_strategy=self._send_strategy,
                allow_send_button_coordinate_fallback=self._allow_send_button_coordinate_fallback,
            )
        except Exception as exc:  # pragma: no cover - depends on local WeChat UI
            return SendResult(
                ok=False,
                backend="pywinauto-session",
                contact=contact,
                detail=f"pywinauto-session 发送失败：{exc}",
                preview=message,
                diagnostics=diagnostics,
            )

        return SendResult(
            ok=True,
            backend="pywinauto-session",
            contact=contact,
            detail=f"已打开并发送到目标会话 {contact!r}。",
            preview=message,
            diagnostics=diagnostics,
        )


def choose_sender(
    real_send: bool,
    backend: str = "auto",
    window_handle: int | None = None,
    send_strategy: str = "enter_first",
    allow_send_button_coordinate_fallback: bool = False,
) -> Sender:
    if not real_send:
        return DryRunSender()
    if backend in {"auto", "wxauto"}:
        return WxautoSender()
    if backend == "pywinauto-active":
        return PywinautoActiveChatSender(
            window_handle=window_handle,
            send_strategy=send_strategy,
            allow_send_button_coordinate_fallback=allow_send_button_coordinate_fallback,
        )
    if backend == "pywinauto-session":
        return PywinautoSessionSender(
            window_handle=window_handle,
            send_strategy=send_strategy,
            allow_send_button_coordinate_fallback=allow_send_button_coordinate_fallback,
        )
    raise ValueError(f"未知后端：{backend}")


def open_target_chat(contact: str, window_handle: int | None = None) -> SendResult:
    return PywinautoSessionSender(window_handle=window_handle).open_target(contact)


def send_test_message(
    contact: str,
    message: str = DEFAULT_TEST_MESSAGE,
    window_handle: int | None = None,
) -> SendResult:
    return PywinautoSessionSender(window_handle=window_handle).send(contact, message)


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
            title = _safe_window_text(window)
            class_name = _safe_class_name(window)
            if any(token in f"{title} {class_name}" for token in ["微信", "WeChat", "Weixin"]):
                matches.append(
                    _describe_window(window)
                )
        if matches:
            lines.append("WeChat-like top windows:")
            lines.extend(f"- {item}" for item in matches[:10])
            for window in desktop.windows():
                if _safe_class_name(window) == WECHAT_MAIN_CLASS:
                    current_chat = PywinautoActiveChatSender._current_chat_name(window)
                    lines.append(f"current Weixin chat: {current_chat!r}" if current_chat else "current Weixin chat: <unknown>")
                    lines.append(
                        "search box: available"
                        if PywinautoActiveChatSender._search_edit(window) is not None
                        else "search box: not found, coordinate fallback disabled"
                    )
                    lines.append(
                        "chat input: available"
                        if PywinautoActiveChatSender._has_chat_input(window)
                        else "chat input: not found"
                    )
                    sessions = []
                    for child in window.descendants(control_type="ListItem"):
                        try:
                            if child.class_name() == "mmui::ChatSessionCell":
                                first_line = child.window_text().splitlines()[0]
                                if first_line:
                                    sessions.append(first_line)
                        except Exception:
                            continue
                    if sessions:
                        lines.append("visible sessions:")
                        lines.extend(f"- {item}" for item in sessions[:15])
                    break
        else:
            lines.append("没有在顶层窗口里找到明显的微信窗口。")
    except Exception as exc:  # pragma: no cover - depends on Windows UI state
        lines.append(f"UIAutomation 诊断失败：{exc}")

    return lines
