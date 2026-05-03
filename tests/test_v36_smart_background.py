from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from wechat_weather.busy_detector import BusyCheckResult, BusyDetector, ForegroundWindowInfo
from wechat_weather.config import load_config, read_config_data
from wechat_weather.monitor import WeatherMonitor
from wechat_weather.reminder_policy import choose_reminder_decision
from wechat_weather.send_batch import read_send_history
from wechat_weather.startup_manager import StartupManager
from wechat_weather.weather import build_weather_message_from_snapshot


def make_snapshot(*, code: int = 0, rain: int = 0, temp_max: float = 26, temp_min: float = 16) -> dict:
    today = date.today()
    days = []
    for offset in range(3):
        current = today.fromordinal(today.toordinal() + offset)
        rows = [
            {
                "time": f"{current.isoformat()}T{hour:02d}:00",
                "date": current.isoformat(),
                "hour": hour,
                "code": code,
                "rain": rain,
                "sources": ["unit"],
            }
            for hour in range(24)
        ]
        days.append(
            {
                "date": current.isoformat(),
                "code": code,
                "temp_min": temp_min,
                "temp_max": temp_max,
                "rain_max": rain,
                "hourly_codes": [code] * 24,
                "hourly_rain": [rain] * 24,
                "hourly_rows": rows,
                "sources": ["unit"],
            }
        )
    return {
        "city_label": "嘉鱼县",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "unit",
        "sources": ["unit"],
        "source_count": 1,
        "provider_failures": [],
        "source_disagreement": False,
        "days": days,
    }


class FakeBusyDetector(BusyDetector):
    def __init__(self, config, info: ForegroundWindowInfo) -> None:
        super().__init__(config)
        self.info = info

    def get_foreground_window_info(self) -> ForegroundWindowInfo:
        return self.info


class V36SmartBackgroundTests(unittest.TestCase):
    def test_default_config_adds_smart_background_sections(self) -> None:
        data = read_config_data(None)
        cfg = load_config(None)

        self.assertEqual(data["reminder_policy"]["mode"], "smart")
        self.assertFalse(cfg.startup.enabled)
        self.assertTrue(cfg.tray.close_to_tray)
        self.assertEqual(cfg.do_not_disturb.busy_action, "delay")

    def test_reminder_policy_normal_none_skips_and_short_is_limited(self) -> None:
        cfg = load_config(None)
        snapshot = make_snapshot(code=0, rain=0)
        full = build_weather_message_from_snapshot(snapshot)
        policy = cfg.reminder_policy.__class__(
            **{
                **cfg.reminder_policy.__dict__,
                "mode": "abnormal_only",
                "normal_weather_action": "none",
            }
        )
        decision = choose_reminder_decision(snapshot, policy, full_message=full)

        self.assertFalse(decision.should_send)
        self.assertEqual(decision.reason, "normal_weather_quiet_policy")

        short_policy = cfg.reminder_policy.__class__(
            **{**cfg.reminder_policy.__dict__, "mode": "short_daily", "short_message_max_chars": 12}
        )
        short = choose_reminder_decision(snapshot, short_policy, full_message=full)
        self.assertTrue(short.should_send)
        self.assertLessEqual(len(short.message), 12)

    def test_reminder_policy_rain_and_high_temperature(self) -> None:
        cfg = load_config(None)
        rainy = make_snapshot(code=61, rain=80)
        full = build_weather_message_from_snapshot(rainy)
        decision = choose_reminder_decision(rainy, cfg.reminder_policy, full_message=full)

        self.assertTrue(decision.should_send)
        self.assertEqual(decision.weather_status, "abnormal")
        self.assertIn("rain", {item.key for item in decision.abnormalities})

        hot_policy = cfg.reminder_policy.__class__(
            **{**cfg.reminder_policy.__dict__, "abnormal_weather_action": "urgent"}
        )
        hot = make_snapshot(code=0, rain=0, temp_max=36)
        urgent = choose_reminder_decision(
            hot,
            hot_policy,
            full_message=build_weather_message_from_snapshot(hot),
        )
        self.assertIn("【重要天气提醒】", urgent.message)

    def test_busy_detector_blocks_fullscreen_and_process(self) -> None:
        cfg = load_config(None)
        fullscreen = FakeBusyDetector(
            cfg.do_not_disturb,
            ForegroundWindowInfo(1, 2, "notepad.exe", True),
        ).should_delay_send()
        game = FakeBusyDetector(
            cfg.do_not_disturb,
            ForegroundWindowInfo(1, 2, "cs2.exe", False),
        ).should_delay_send()

        self.assertTrue(fullscreen.busy)
        self.assertEqual(fullscreen.reason, "fullscreen_window")
        self.assertTrue(game.busy)
        self.assertEqual(game.reason, "busy_process")

    def test_startup_command_quotes_chinese_and_space_path(self) -> None:
        manager = StartupManager(config_path=r"C:\用户目录\Kangkang Weather\config.json")
        with patch.object(sys, "executable", r"C:\Program Files\Kangkang Weather\KangkangWeather.exe"):
            with patch.object(sys, "frozen", True, create=True):
                command = manager.get_startup_command()

        self.assertIn('"C:\\Program Files\\Kangkang Weather\\KangkangWeather.exe"', command)
        self.assertIn("tray", command)
        self.assertIn('"C:\\用户目录\\Kangkang Weather\\config.json"', command)

    def test_fixed_weather_normal_abnormal_only_records_skipped_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"APPDATA": tmp}):
                config_path = Path(tmp) / "config.json"
                config_path.write_text(
                    json.dumps(
                        {
                            "app": {"setup_complete": True},
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
                                {"id": "target", "name": "微信快存", "enabled": True, "default": True}
                            ],
                            "automation_jobs": [
                                {
                                    "id": "job",
                                    "location_id": "loc",
                                    "wechat_target_id": "target",
                                    "fixed_times": ["07:30"],
                                }
                            ],
                            "reminder_policy": {
                                "enabled": True,
                                "mode": "abnormal_only",
                                "normal_weather_action": "none",
                                "record_skipped_history": True,
                            },
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                monitor = WeatherMonitor(str(config_path), None)
                state = {"jobs": {"job": {}}}
                fixed_entry = {
                    "fixed_time": "07:30",
                    "key": f"{date.today().isoformat()}:07:30",
                    "due_at": datetime.now().isoformat(timespec="seconds"),
                    "deadline_at": datetime.now().isoformat(timespec="seconds"),
                }
                with patch.object(monitor, "_job_weather_snapshot", return_value=make_snapshot(code=0, rain=0)):
                    result = monitor._send_fixed_weather(
                        monitor.app_config,
                        monitor.app_config.default_job,
                        fixed_entry,
                        state,
                        real_send=False,
                    )
                history = read_send_history(limit=5)

        self.assertFalse(result["sent"])
        self.assertEqual(result["status"], "SKIPPED_NORMAL_WEATHER")
        self.assertEqual(history[-1]["status"], "skipped")
        self.assertEqual(history[-1]["targets"][0]["error_code"], "normal_weather_quiet_policy")


if __name__ == "__main__":
    unittest.main()
