from __future__ import annotations

from datetime import date, timedelta
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from wechat_weather.config import load_config, read_config_data
from wechat_weather.compat import build_compat_report, export_diagnostics_package
from wechat_weather.error_analysis import analyze_error
from wechat_weather.server import WeatherServer
from wechat_weather.weather import WeatherConfig, build_weather_snapshot
from wechat_weather.wechat import DEFAULT_TEST_MESSAGE, PywinautoActiveChatSender, SendResult


def open_meteo_payload() -> dict:
    start = date.today()
    daily_dates = [(start + timedelta(days=index)).isoformat() for index in range(4)]
    hourly_times = [
        f"{(start + timedelta(days=day)).isoformat()}T{hour:02d}:00"
        for day in range(4)
        for hour in range(24)
    ]
    return {
        "daily": {
            "time": daily_dates,
            "weather_code": [3, 61, 63, 3],
            "temperature_2m_max": [24, 23, 22, 25],
            "temperature_2m_min": [16, 15, 14, 17],
            "precipitation_probability_max": [70, 80, 60, 20],
        },
        "hourly": {
            "time": hourly_times,
            "weather_code": [3] * len(hourly_times),
            "precipitation_probability": [40] * len(hourly_times),
        },
    }


class FakeElementInfo:
    def __init__(self, automation_id: str, name: str) -> None:
        self.automation_id = automation_id
        self.name = name


class FakeListItem:
    def __init__(self, automation_id: str, name: str, class_name: str = "", on_click=None) -> None:
        self.element_info = FakeElementInfo(automation_id, name)
        self._class_name = class_name
        self.on_click = on_click
        self.clicked = 0

    def window_text(self) -> str:
        return self.element_info.name

    def class_name(self) -> str:
        return self._class_name

    def click_input(self) -> None:
        self.clicked += 1
        if self.on_click:
            self.on_click()


class FakeWindow:
    def __init__(self, items: list[FakeListItem]) -> None:
        self.items = items

    def descendants(self, control_type: str | None = None):
        return self.items


class FakeChatEdit:
    def __init__(self, text: str | None = None) -> None:
        self.element_info = FakeElementInfo("chat_input_field", "")
        self.iface_value = type("FakeValue", (), {"CurrentValue": text or ""})()
        self.text = text or ""
        self.clicked = 0

    def set_text(self, text: str) -> None:
        self.text = text
        self.iface_value.CurrentValue = text

    def click_input(self) -> None:
        self.clicked += 1

    def window_text(self) -> str:
        return self.text


class FakeSearchEdit(FakeChatEdit):
    def __init__(self, text: str | None = None, fail_direct: bool = False) -> None:
        super().__init__(text)
        self.element_info = FakeElementInfo("", "搜索")
        self.fail_direct = fail_direct
        if fail_direct:
            self.iface_value = type("FakeValue", (), {"CurrentValue": text or "", "SetValue": self._fail_set_value})()
        else:
            self.iface_value = type("FakeValue", (), {"CurrentValue": text or "", "SetValue": self.set_text})()

    def class_name(self) -> str:
        return "mmui::XValidatorTextEdit"

    def set_edit_text(self, text: str) -> None:
        if self.fail_direct:
            raise RuntimeError("set_edit_text failed")
        self.set_text(text)

    def set_text(self, text: str) -> None:
        if self.fail_direct:
            raise RuntimeError("set_text failed")
        super().set_text(text)

    def append_text(self, text: str) -> None:
        FakeChatEdit.set_text(self, self.text + text)

    def clear_text(self) -> None:
        FakeChatEdit.set_text(self, "")

    def _fail_set_value(self, text: str) -> None:
        raise RuntimeError("uia value failed")


class FakeCurrentChatLabel:
    def __init__(self, window: "FakeSearchWindow") -> None:
        self.window = window
        self.element_info = FakeElementInfo("current_chat_name_label", "")

    def window_text(self) -> str:
        return self.window.current_chat


class FakeSearchWindow:
    def __init__(
        self,
        current_chat: str,
        search: FakeSearchEdit,
        items: list[FakeListItem] | None = None,
        edit: FakeChatEdit | None = None,
    ) -> None:
        self.current_chat = current_chat
        self.search = search
        self.items = items or []
        self.edit = edit
        self.alive = True
        self.handle = 1001

    def descendants(self, control_type: str | None = None):
        if control_type == "Edit":
            edits = [self.search]
            if self.edit is not None:
                edits.append(self.edit)
            return edits
        if control_type == "ListItem":
            return self.items
        return [FakeCurrentChatLabel(self), self.search, *self.items]

    def exists(self, timeout: float = 0.0) -> bool:
        return self.alive

    def window_text(self) -> str:
        if not self.alive:
            raise RuntimeError("window disappeared")
        return "微信"

    def class_name(self) -> str:
        if not self.alive:
            raise RuntimeError("window disappeared")
        return "mmui::MainWindow"

    def restore(self) -> None:
        pass

    def set_focus(self) -> None:
        pass

    def set_current_chat(self, name: str) -> None:
        self.current_chat = name


class FakeSendButton:
    def __init__(self, label: str = "发送", on_invoke=None, on_click=None) -> None:
        self.element_info = FakeElementInfo("", label)
        self.clicked = 0
        self.invoke_clicked = 0
        self.on_invoke = on_invoke
        self.on_click = on_click

    def window_text(self) -> str:
        return self.element_info.name

    def is_enabled(self) -> bool:
        return True

    def invoke(self) -> None:
        self.invoke_clicked += 1
        self.clicked += 1
        if self.on_invoke:
            self.on_invoke()

    def click_input(self) -> None:
        self.clicked += 1
        if self.on_click:
            self.on_click()


class FakeChatWindow:
    def __init__(self, edit: FakeChatEdit, buttons: list[FakeSendButton]) -> None:
        self.edit = edit
        self.buttons = buttons

    def descendants(self, control_type: str | None = None):
        if control_type == "Edit":
            return [self.edit]
        if control_type == "Button":
            return self.buttons
        return []


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send(self, contact: str, message: str) -> SendResult:
        self.calls.append((contact, message))
        return SendResult(
            ok=True,
            backend="pywinauto-session",
            contact=contact,
            detail="sent",
            preview=message,
            diagnostics=["fake-send"],
        )


class ReadyReport:
    def to_dict(self) -> dict:
        return {
            "ok": True,
            "status": "ready",
            "can_send_now": True,
            "can_retry_later": False,
            "checks": [],
        }


def post_json(port: int, path: str, payload: dict) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        return response.status, data
    finally:
        connection.close()


def run_test_server(config_path: Path):
    server = WeatherServer(("127.0.0.1", 0), config_path=str(config_path), window_handle=None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class PortableV22Tests(unittest.TestCase):

    def test_error_analysis_classifies_common_wechat_failures(self) -> None:
        target = analyze_error("\u6ca1\u6709\u6210\u529f\u6253\u5f00\u76ee\u6807\u4f1a\u8bdd\u3002\u5f53\u524d\u5fae\u4fe1\u804a\u5929\u662f '\u674e\u946b'\uff0c\u76ee\u6807\u662f '\u9ad8\u76f8\u70e8'\u3002")
        self.assertEqual(target.category, "wechat_target_not_found")
        self.assertTrue(target.next_steps)

        clipboard = analyze_error("pywinauto-session \u53d1\u9001\u5931\u8d25\uff1a\u65e0\u6cd5\u6253\u5f00 Windows \u526a\u8d34\u677f\u3002")
        self.assertEqual(clipboard.category, "clipboard_unavailable")

        send_button = analyze_error("\u7c98\u8d34\u540e\u6ca1\u6709\u627e\u5230\u660e\u786e\u53ef\u70b9\u51fb\u7684\u53d1\u9001\u6309\u94ae\uff0c\u5df2\u53d6\u6d88\u53d1\u9001\u3002", ["paste: \u5df2\u6267\u884c Ctrl+V"])
        self.assertEqual(send_button.category, "paste_or_send_button_failed")

        not_submitted = analyze_error(
            "pywinauto-session 发送失败：消息已粘贴但没有提交发送。",
            [
                "clipboard: 已保存当前文本剪贴板。",
                "clipboard: 已写入待发送消息。",
                "clipboard: 已恢复原文本剪贴板。",
                "send_key: 已尝试 Enter 发送。",
                "send_key: Enter 后未确认提交。",
            ],
        )
        self.assertEqual(not_submitted.category, "send_not_submitted")


    def test_compat_report_and_diagnostics_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"APPDATA": tmp}):
                with patch("wechat_weather.compat._weather_check", return_value=(True, "ok")):
                    with patch("wechat_weather.compat._wechat_check_lines", return_value=(False, ["no wechat"])):
                        report = build_compat_report(None, active_port=8766)
                        package = export_diagnostics_package(None, active_port=8766)
                        self.assertTrue(package.exists())
                        self.assertTrue(package.name.startswith("KangkangWeather-diagnostics-"))

        self.assertIn(report["status"], {"ready", "warning", "blocked"})
        self.assertTrue(report["checks"])

    def test_apply_setup_profile_updates_default_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(json.dumps({"app": {"setup_complete": False}}, ensure_ascii=False), encoding="utf-8")
            with patch("wechat_weather.server.WeatherMonitor.start", return_value=None):
                server, thread = run_test_server(config_path)
                try:
                    status, data = post_json(
                        server.server_port,
                        "/api/setup/apply-profile",
                        {
                            "location": {"name": "嘉鱼县", "latitude": 29.97, "longitude": 113.93},
                            "wechat_target": {"name": "文件传输助手"},
                            "automation": {
                                "interval_minutes": 90,
                                "fixed_times": ["07:30", "18:00"],
                                "active_windows": ["06:00-09:00", "18:00-22:00"],
                                "allow_quiet_send": True,
                                "alert_options": {
                                    "rain_threshold_percent": 60,
                                    "rain_jump_percent": 25,
                                    "temp_change_celsius": 2,
                                    "weather_upgrade_enabled": False,
                                    "future_rain_upgrade_enabled": True,
                                },
                            },
                        },
                    )
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

            cfg = load_config(str(config_path))

        self.assertEqual(status, 200)
        self.assertTrue(data["profile_applied"])
        self.assertTrue(cfg.app.setup_complete)
        self.assertEqual(cfg.default_location.name, "嘉鱼县")
        self.assertEqual(cfg.default_wechat_target.name, "文件传输助手")
        self.assertEqual(cfg.default_job.interval_minutes, 90)
        self.assertEqual(cfg.default_job.fixed_times, ["07:30", "18:00"])
        self.assertEqual(cfg.default_job.active_windows, ["06:00-09:00", "18:00-22:00"])
        self.assertTrue(cfg.default_job.allow_quiet_send)
        self.assertEqual(cfg.default_job.alert_options.rain_threshold_percent, 60)
        self.assertFalse(cfg.default_job.alert_options.weather_upgrade_enabled)

    def test_clean_user_config_starts_in_setup_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"APPDATA": tmp}):
                cfg = load_config(None, create_user_config=True)
                data = read_config_data(None, create_user_config=True)

        self.assertFalse(cfg.app.setup_complete)
        self.assertFalse(data["app"]["setup_complete"])

    def test_existing_v21_config_is_treated_as_setup_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "app": {"name": "KangkangWeather"},
                        "locations": [
                            {
                                "id": "loc",
                                "name": "嘉鱼县",
                                "latitude": 29.9,
                                "longitude": 113.9,
                                "enabled": True,
                                "default": True,
                            }
                        ],
                        "wechat_targets": [
                            {"id": "target", "name": "文件传输助手", "enabled": True, "default": True}
                        ],
                        "automation_jobs": [
                            {
                                "id": "default",
                                "location_id": "loc",
                                "wechat_target_id": "target",
                                "enabled": True,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            cfg = load_config(str(path))

        self.assertTrue(cfg.app.setup_complete)
        self.assertEqual(cfg.app.version, "3.6.0")
        self.assertEqual(cfg.monitor.wechat_send_strategy, "enter_first")
        self.assertFalse(cfg.monitor.allow_send_button_coordinate_fallback)

    def test_weather_uses_recent_cache_when_all_sources_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = WeatherConfig(city_label="嘉鱼县", timeout_seconds=1)
            with patch.dict(os.environ, {"APPDATA": tmp}):
                with patch("wechat_weather.weather.fetch_open_meteo_weather", return_value=open_meteo_payload()):
                    first = build_weather_snapshot(config, comparison_models=[], fallback_wttr=False)

                with patch("wechat_weather.weather.fetch_open_meteo_weather", side_effect=RuntimeError("offline")):
                    with patch("wechat_weather.weather.fetch_wttr_weather", side_effect=RuntimeError("offline")):
                        cached = build_weather_snapshot(config, comparison_models=[], fallback_wttr=True)

        self.assertFalse(first["stale"])
        self.assertTrue(cached["stale"])
        self.assertTrue(cached["cached"])
        self.assertIn("offline", " ".join(cached["provider_failures"]))

    def test_search_result_prefers_exact_automation_id(self) -> None:
        contact = "文件传输助手"
        window = FakeWindow(
            [
                FakeListItem("", contact),
                FakeListItem(f"search_item_{contact}", contact),
            ]
        )

        result = PywinautoActiveChatSender._search_result_for_contact(window, contact)

        self.assertEqual(result.element_info.automation_id, f"search_item_{contact}")

    def test_open_session_search_writes_contact_with_uia_without_clipboard(self) -> None:
        contact = "文件传输助手"
        search = FakeSearchEdit("")
        window = FakeSearchWindow(current_chat="旧会话", search=search)
        window.items = [
            FakeListItem(
                f"search_item_{contact}",
                contact,
                on_click=lambda: window.set_current_chat(contact),
            )
        ]
        diagnostics: list[str] = []

        with patch("wechat_weather.wechat._temporary_clipboard_text", side_effect=AssertionError("clipboard must not be used")):
            with patch("wechat_weather.wechat.time.sleep", return_value=None):
                current = PywinautoActiveChatSender._open_session_from_search(
                    window,
                    contact,
                    diagnostics,
                )

        self.assertEqual(current, contact)
        self.assertEqual(search.text, contact)
        self.assertEqual(window.items[0].clicked, 1)
        self.assertTrue(any("search: 已通过 set_edit_text 写入输入框" in item for item in diagnostics))

    def test_open_session_search_falls_back_to_unicode_typing_without_clipboard(self) -> None:
        contact = "微信快存"
        search = FakeSearchEdit("", fail_direct=True)
        window = FakeSearchWindow(current_chat="旧会话", search=search)
        window.items = [
            FakeListItem(
                f"search_item_{contact}",
                contact,
                on_click=lambda: window.set_current_chat(contact),
            )
        ]
        keys: list[str] = []
        diagnostics: list[str] = []

        def fake_send_keys(sequence: str) -> None:
            keys.append(sequence)
            if sequence == "^a{BACKSPACE}":
                search.clear_text()

        with patch("wechat_weather.wechat._send_keys", side_effect=fake_send_keys):
            with patch("wechat_weather.wechat._send_unicode_char", side_effect=search.append_text):
                with patch("wechat_weather.wechat._temporary_clipboard_text", side_effect=AssertionError("clipboard must not be used")):
                    with patch("wechat_weather.wechat.time.sleep", return_value=None):
                        current = PywinautoActiveChatSender._open_session_from_search(
                            window,
                            contact,
                            diagnostics,
                        )

        self.assertEqual(current, contact)
        self.assertEqual(search.text, contact)
        self.assertIn("^a{BACKSPACE}", keys)
        self.assertTrue(any("search: 已完成 Unicode 直接输入" in item for item in diagnostics))

    def test_open_session_search_requires_exact_match_and_does_not_press_enter(self) -> None:
        contact = "高相烨"
        search = FakeSearchEdit("")
        window = FakeSearchWindow(
            current_chat="旧会话",
            search=search,
            items=[FakeListItem("", "高相烨备注不一致")],
        )
        keys: list[str] = []
        diagnostics: list[str] = []

        with patch("wechat_weather.wechat._send_keys", side_effect=keys.append):
            with patch("wechat_weather.wechat.time.sleep", return_value=None):
                current = PywinautoActiveChatSender._open_session_from_search(
                    window,
                    contact,
                    diagnostics,
                )

        self.assertEqual(current, "旧会话")
        self.assertNotIn("{ENTER}", keys)
        self.assertEqual(window.items[0].clicked, 0)
        self.assertTrue(any("未找到精确匹配搜索结果" in item for item in diagnostics))

    def test_open_session_stops_when_wechat_window_disappears(self) -> None:
        contact = "文件传输助手"
        search = FakeSearchEdit("")
        window = FakeSearchWindow(current_chat="旧会话", search=search)
        window.items = [
            FakeListItem(
                f"search_item_{contact}",
                contact,
                on_click=lambda: setattr(window, "alive", False),
            )
        ]
        diagnostics: list[str] = []

        with patch("wechat_weather.wechat.time.sleep", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "微信窗口已退出或不可访问"):
                PywinautoActiveChatSender._open_session_from_search(
                    window,
                    contact,
                    diagnostics,
                )

        analysis = analyze_error("打开目标会话失败：微信窗口已退出或不可访问", diagnostics)
        self.assertEqual(analysis.category, "wechat_window_gone")

    def test_safe_send_pastes_then_enter_and_restores_clipboard(self) -> None:
        keys: list[str] = []
        clipboard_writes: list[str] = []
        message = "康康天气测试消息：如果你收到这条，说明微信发送链路正常。"
        edit = FakeChatEdit("")
        button = FakeSendButton("发送(S)")
        window = FakeChatWindow(edit, [button])
        diagnostics: list[str] = []

        def fake_send_keys(sequence: str) -> None:
            keys.append(sequence)
            if sequence == "^v":
                edit.set_text(message)
            if sequence == "{ENTER}":
                edit.set_text("")

        with patch("wechat_weather.wechat._send_keys", side_effect=fake_send_keys):
            with patch("wechat_weather.wechat._get_clipboard_text", return_value="old clipboard"):
                with patch("wechat_weather.wechat._set_clipboard_text", side_effect=clipboard_writes.append):
                    with patch("wechat_weather.wechat.time.sleep", return_value=None):
                        PywinautoActiveChatSender._send_message_to_open_chat(
                            window,
                            message,
                            diagnostics,
                        )

        self.assertIn("^a", keys)
        self.assertIn("^v", keys)
        self.assertNotIn("^a{BACKSPACE}", keys)
        self.assertIn("{ENTER}", keys)
        self.assertNotIn("^{ENTER}", keys)
        self.assertEqual(button.clicked, 0)
        self.assertEqual(clipboard_writes[-1], "old clipboard")
        self.assertTrue(any("paste_ok -> enter -> verified" in item for item in diagnostics))

    def test_safe_send_falls_back_to_ctrl_enter_when_enter_leaves_message_in_input(self) -> None:
        keys: list[str] = []
        edit = FakeChatEdit("测试消息")
        button = FakeSendButton("发送(S)")
        window = FakeChatWindow(edit, [button])
        diagnostics: list[str] = []

        def fake_send_keys(sequence: str) -> None:
            keys.append(sequence)
            if sequence == "^{ENTER}":
                edit.set_text("")

        with patch("wechat_weather.wechat._send_keys", side_effect=fake_send_keys):
            with patch("wechat_weather.wechat._get_clipboard_text", return_value="old"):
                with patch("wechat_weather.wechat._set_clipboard_text"):
                    with patch("wechat_weather.wechat._press_enter"):
                        with patch("wechat_weather.wechat.time.sleep", return_value=None):
                            PywinautoActiveChatSender._send_message_to_open_chat(
                                window,
                                "测试消息",
                                diagnostics,
                            )

        self.assertIn("{ENTER}", keys)
        self.assertIn("^{ENTER}", keys)
        self.assertEqual(button.clicked, 0)
        self.assertTrue(any("仍停留在输入框" in item for item in diagnostics))
        self.assertTrue(any("paste_ok -> ctrl_enter -> verified" in item for item in diagnostics))

    def test_safe_send_uses_native_enter_when_pywinauto_enter_does_not_submit(self) -> None:
        keys: list[str] = []
        native_calls: list[bool] = []
        edit = FakeChatEdit("测试消息")
        button = FakeSendButton("发送(S)")
        window = FakeChatWindow(edit, [button])
        diagnostics: list[str] = []

        def fake_native_enter(ctrl: bool = False) -> None:
            native_calls.append(ctrl)
            if not ctrl:
                edit.set_text("")

        with patch("wechat_weather.wechat._send_keys", side_effect=keys.append):
            with patch("wechat_weather.wechat._press_enter", side_effect=fake_native_enter):
                with patch("wechat_weather.wechat._get_clipboard_text", return_value="old"):
                    with patch("wechat_weather.wechat._set_clipboard_text"):
                        with patch("wechat_weather.wechat.time.sleep", return_value=None):
                            PywinautoActiveChatSender._send_message_to_open_chat(
                                window,
                                "测试消息",
                                diagnostics,
                            )

        self.assertIn("{ENTER}", keys)
        self.assertEqual(native_calls, [False])
        self.assertTrue(any("paste_ok -> enter_native -> verified" in item for item in diagnostics))

    def test_safe_send_fails_when_keyboard_methods_leave_message_in_input(self) -> None:
        edit = FakeChatEdit("测试消息")
        button = FakeSendButton("发送(S)")
        window = FakeChatWindow(edit, [button])

        with patch("wechat_weather.wechat._send_keys"):
            with patch("wechat_weather.wechat._get_clipboard_text", return_value="old"):
                with patch("wechat_weather.wechat._set_clipboard_text"):
                    with patch("wechat_weather.wechat._press_enter"):
                        with patch("wechat_weather.wechat.time.sleep", return_value=None):
                            with self.assertRaisesRegex(RuntimeError, "消息已粘贴但没有提交发送"):
                                PywinautoActiveChatSender._send_message_to_open_chat(
                                    window,
                                    "测试消息",
                                    [],
                                )
        self.assertEqual(button.clicked, 0)

    def test_safe_send_does_not_coordinate_click_by_default(self) -> None:
        keys: list[str] = []
        edit = FakeChatEdit("测试消息")
        button = FakeSendButton("发送(S)")
        window = FakeChatWindow(edit, [button])

        with patch("wechat_weather.wechat._send_keys", side_effect=keys.append):
            with patch("wechat_weather.wechat._get_clipboard_text", return_value="old"):
                with patch("wechat_weather.wechat._set_clipboard_text"):
                    with patch("wechat_weather.wechat._press_enter"):
                        with patch("wechat_weather.wechat.time.sleep", return_value=None):
                            with self.assertRaisesRegex(RuntimeError, "消息已粘贴但没有提交发送"):
                                PywinautoActiveChatSender._send_message_to_open_chat(
                                    window,
                                    "测试消息",
                                    [],
                                )

        self.assertNotIn("^a{BACKSPACE}", keys)
        self.assertIn("{ENTER}", keys)
        self.assertIn("^{ENTER}", keys)
        self.assertEqual(button.clicked, 0)

    def test_safe_send_can_use_explicit_button_fallback_after_keyboard_failure(self) -> None:
        keys: list[str] = []
        edit = FakeChatEdit("测试消息")
        button = FakeSendButton("发送(S)", on_invoke=lambda: edit.set_text(""))
        window = FakeChatWindow(edit, [button])
        diagnostics: list[str] = []

        with patch("wechat_weather.wechat._send_keys", side_effect=keys.append):
            with patch("wechat_weather.wechat._get_clipboard_text", return_value="old"):
                with patch("wechat_weather.wechat._set_clipboard_text"):
                    with patch("wechat_weather.wechat._press_enter"):
                        with patch("wechat_weather.wechat.time.sleep", return_value=None):
                            PywinautoActiveChatSender._send_message_to_open_chat(
                                window,
                                "测试消息",
                                diagnostics,
                                allow_send_button_coordinate_fallback=True,
                            )

        self.assertEqual(button.invoke_clicked, 1)
        self.assertTrue(any("显式按钮兜底" in item for item in diagnostics))

    def test_safe_send_uses_direct_input_when_clipboard_is_unavailable(self) -> None:
        keys: list[str] = []
        message = "康康天气测试消息"
        edit = FakeChatEdit("")
        button = FakeSendButton("发送(S)")
        window = FakeChatWindow(edit, [button])
        diagnostics: list[str] = []

        def fake_send_keys(sequence: str) -> None:
            keys.append(sequence)
            if sequence == "{ENTER}":
                edit.set_text("")

        with patch("wechat_weather.wechat._send_keys", side_effect=fake_send_keys):
            with patch("wechat_weather.wechat._get_clipboard_text", side_effect=RuntimeError("无法打开 Windows 剪贴板。")):
                with patch("wechat_weather.wechat._set_clipboard_text", side_effect=RuntimeError("无法打开 Windows 剪贴板。")):
                    with patch("wechat_weather.wechat.time.sleep", return_value=None):
                        PywinautoActiveChatSender._send_message_to_open_chat(
                            window,
                            message,
                            diagnostics,
                        )

        self.assertIn("{ENTER}", keys)
        self.assertEqual(button.clicked, 0)
        self.assertTrue(any("set_text 写入" in item for item in diagnostics))

    def test_open_target_endpoint_does_not_send_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(json.dumps({"contact": "文件传输助手"}, ensure_ascii=False), encoding="utf-8")
            with patch("wechat_weather.server.WeatherMonitor.start", return_value=None):
                with patch("wechat_weather.server.open_target_chat") as open_target:
                    with patch("wechat_weather.server.choose_sender", side_effect=AssertionError("must not send")):
                        open_target.return_value = SendResult(
                            ok=True,
                            backend="pywinauto-session",
                            contact="文件传输助手",
                            detail="opened",
                        )
                        server, thread = run_test_server(config_path)
                        try:
                            status, data = post_json(server.server_port, "/api/wechat/open-target", {"contact": "文件传输助手"})
                        finally:
                            server.shutdown()
                            server.server_close()
                            thread.join(timeout=2)

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(open_target.call_count, 1)


    def test_failed_test_message_response_contains_error_analysis(self) -> None:
        class FailingSender:
            def send(self, contact: str, message: str) -> SendResult:
                return SendResult(
                    ok=False,
                    backend="pywinauto-session",
                    contact=contact,
                    detail="\u7c98\u8d34\u540e\u6ca1\u6709\u627e\u5230\u660e\u786e\u53ef\u70b9\u51fb\u7684\u53d1\u9001\u6309\u94ae\uff0c\u5df2\u53d6\u6d88\u53d1\u9001\u3002",
                    preview=message,
                    diagnostics=["paste: \u5df2\u6267\u884c Ctrl+V"],
                )

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(json.dumps({"contact": "\u6587\u4ef6\u4f20\u8f93\u52a9\u624b"}, ensure_ascii=False), encoding="utf-8")
            with patch("wechat_weather.server.WeatherMonitor.start", return_value=None):
                with patch("wechat_weather.server.choose_sender", return_value=FailingSender()):
                    with patch("wechat_weather.server.check_readiness", return_value=ReadyReport()):
                        server, thread = run_test_server(config_path)
                        try:
                            status, data = post_json(server.server_port, "/api/wechat/test-message", {"contact": "\u6587\u4ef6\u4f20\u8f93\u52a9\u624b"})
                        finally:
                            server.shutdown()
                            server.server_close()
                            thread.join(timeout=2)

        self.assertEqual(status, 409)
        self.assertEqual(data["error_analysis"]["category"], "paste_or_send_button_failed")
        self.assertTrue(data["error_analysis"]["next_steps"])

    def test_test_message_endpoint_sends_default_test_message(self) -> None:
        sender = FakeSender()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(json.dumps({"contact": "文件传输助手"}, ensure_ascii=False), encoding="utf-8")
            with patch("wechat_weather.server.WeatherMonitor.start", return_value=None):
                with patch("wechat_weather.server.choose_sender", return_value=sender):
                    with patch("wechat_weather.server.check_readiness", return_value=ReadyReport()):
                        server, thread = run_test_server(config_path)
                        try:
                            status, data = post_json(server.server_port, "/api/wechat/test-message", {"contact": "文件传输助手"})
                        finally:
                            server.shutdown()
                            server.server_close()
                            thread.join(timeout=2)

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(sender.calls, [("文件传输助手", DEFAULT_TEST_MESSAGE)])
        self.assertEqual(data["diagnostics"], ["fake-send"])


if __name__ == "__main__":
    unittest.main()
