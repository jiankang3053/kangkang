from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wechat_weather.config import load_config, normalize_active_windows, read_config_data
from wechat_weather.monitor import WeatherMonitor, evaluate_alerts
from wechat_weather.weather import WeatherConfig, build_weather_message_from_snapshot, merge_snapshots


def make_snapshot(
    city: str,
    future_rain: int,
    code: int = 3,
    temp_min: int = 18,
    temp_max: int = 24,
) -> dict:
    start = date.today()
    days = []
    for offset in range(4):
        current = start + timedelta(days=offset)
        rows = []
        for hour in range(24):
            rain = future_rain if offset == 0 and 10 <= hour < 16 else 5
            rows.append(
                {
                    "time": f"{current.isoformat()}T{hour:02d}:00",
                    "date": current.isoformat(),
                    "hour": hour,
                    "code": code,
                    "rain": rain,
                    "sources": ["test"],
                }
            )
        days.append(
            {
                "date": current.isoformat(),
                "code": code,
                "temp_min": temp_min,
                "temp_max": temp_max,
                "rain_max": max(row["rain"] for row in rows),
                "hourly_codes": [row["code"] for row in rows],
                "hourly_rain": [row["rain"] for row in rows],
                "hourly_rows": rows,
                "sources": ["test"],
            }
        )
    return {
        "city_label": city,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "test",
        "sources": ["test"],
        "source_count": 1,
        "provider_failures": [],
        "source_disagreement": False,
        "days": days,
    }


class FakeMonitor(WeatherMonitor):
    def __init__(self, config_path: str, state_path: Path, snapshots: dict[str, list[dict]]) -> None:
        super().__init__(config_path=config_path, window_handle=None)
        self._state_path = state_path
        self._snapshots = snapshots

    @property
    def state_file(self) -> Path:
        return self._state_path

    def _job_weather_snapshot(self, config, location):
        queue = self._snapshots[location.id]
        if len(queue) > 1:
            return queue.pop(0)
        return queue[0]


class BlockedReadiness:
    def to_dict(self) -> dict:
        return {
            "ok": False,
            "status": "blocked_sleep_or_locked",
            "can_send_now": False,
            "can_retry_later": True,
            "checks": [],
        }


def write_fixed_config(path: Path, fixed_times: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "locations": [
                    {
                        "id": "jiayu",
                        "name": "jiayu",
                        "latitude": 29.9724209,
                        "longitude": 113.9335326,
                        "source": "test",
                        "enabled": True,
                        "default": True,
                    }
                ],
                "wechat_targets": [
                    {"id": "target", "name": "filehelper", "enabled": True, "default": True}
                ],
                "automation_jobs": [
                    {
                        "id": "default",
                        "location_id": "jiayu",
                        "wechat_target_id": "target",
                        "enabled": True,
                        "interval_minutes": 120,
                        "fixed_times": fixed_times,
                        "active_windows": ["07:00-22:00"],
                    }
                ],
                "providers": {"comparison_models": []},
                "monitor": {"fixed_send_grace_minutes": 180},
                "message": {"daily_style": "segmented_brief", "daily_prefix": ""},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class WeatherV2Tests(unittest.TestCase):
    def test_segmented_brief_daily_message_without_prefix(self) -> None:
        message = build_weather_message_from_snapshot(make_snapshot("嘉鱼县", future_rain=70))

        self.assertTrue(message.startswith("【嘉鱼县天气提醒】"))
        self.assertIn("今日分时段：", message)
        self.assertIn("00:00-03:00", message)
        self.assertIn("21:00-24:00", message)
        self.assertIn("今日气温：18-24℃。", message)
        self.assertIn("明天：", message)
        self.assertIn("后天：", message)
        self.assertNotIn("大后天", message)

    def test_segmented_brief_daily_message_with_prefix(self) -> None:
        prefix = "早上好，今天出门前看一下天气："
        message = build_weather_message_from_snapshot(
            make_snapshot("嘉鱼县", future_rain=70),
            daily_prefix=prefix,
        )

        self.assertTrue(message.startswith(f"{prefix}\n\n【嘉鱼县天气提醒】"))

    def test_merge_snapshots_uses_conservative_risk(self) -> None:
        low = make_snapshot("嘉鱼县", future_rain=20, code=3, temp_min=18, temp_max=24)
        high = make_snapshot("嘉鱼县", future_rain=80, code=65, temp_min=16, temp_max=27)
        merged = merge_snapshots(WeatherConfig(city_label="嘉鱼县"), [low, high])
        today = merged["days"][0]

        self.assertEqual(today["rain_max"], 80)
        self.assertEqual(today["code"], 65)
        self.assertEqual(today["temp_min"], 16)
        self.assertEqual(today["temp_max"], 27)
        self.assertTrue(merged["source_disagreement"])

    def test_alerts_trigger_on_rain_jump_and_weather_upgrade(self) -> None:
        now = datetime.combine(date.today(), time(10, 0))
        previous = make_snapshot("嘉鱼县", future_rain=20, code=3)
        current = make_snapshot("嘉鱼县", future_rain=70, code=65)

        keys = {alert.key for alert in evaluate_alerts(previous, current, now=now, future_hours=6)}

        self.assertIn("rain_6h_threshold", keys)
        self.assertIn("rain_6h_jump", keys)
        self.assertIn("weather_upgrade_6h", keys)

    def test_legacy_recipients_migrate_to_locations_targets_and_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "contact": "湘楠",
                        "recipients": [
                            {"name": "湘楠", "city_label": "嘉鱼县", "enabled": True},
                            {"name": "备用", "city_label": "武汉市", "enabled": True},
                        ],
                        "providers": {"comparison_models": []},
                        "monitor": {
                            "enabled": True,
                            "interval_minutes": 120,
                            "backend": "pywinauto-session",
                            "quiet_start": "22:00",
                            "quiet_end": "07:00",
                            "future_hours": 6,
                            "daily_history_limit": 5,
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            cfg = load_config(str(config_path))
            data = read_config_data(str(config_path))

            self.assertEqual(cfg.default_wechat_target.name, "湘楠")
            self.assertEqual(cfg.message.daily_style, "segmented_brief")
            self.assertEqual(cfg.message.daily_prefix, "")
            self.assertEqual(data["message"]["daily_style"], "segmented_brief")
            self.assertEqual(cfg.default_location.name, "嘉鱼县")
            self.assertEqual(len(data["locations"]), 2)
            self.assertEqual(len(data["wechat_targets"]), 2)
            self.assertEqual(len(data["automation_jobs"]), 2)
            self.assertEqual(data["automation_jobs"][0]["active_windows"], ["07:00-22:00"])
            self.assertIn("alert_options", data["automation_jobs"][0])

    def test_active_windows_normalize_merge_and_reject_invalid(self) -> None:
        self.assertEqual(
            normalize_active_windows(["09:00-12:00", "11:30-14:00", "18:00-22:00"]),
            ["09:00-14:00", "18:00-22:00"],
        )
        self.assertEqual(
            normalize_active_windows(["22:00-02:00"]),
            ["00:00-02:00", "22:00-24:00"],
        )
        with self.assertRaises(ValueError):
            normalize_active_windows(["99:00-10:00"], strict=True)

    def test_alert_options_change_thresholds_and_disable_upgrades(self) -> None:
        now = datetime.combine(date.today(), time(10, 0))
        previous = make_snapshot("嘉鱼县", future_rain=20, code=3)
        current = make_snapshot("嘉鱼县", future_rain=45, code=65)

        default_keys = {alert.key for alert in evaluate_alerts(previous, current, now=now)}
        custom_keys = {
            alert.key
            for alert in evaluate_alerts(
                previous,
                current,
                now=now,
                alert_options={
                    "rain_threshold_percent": 40,
                    "rain_jump_percent": 50,
                    "temp_change_celsius": 10,
                    "weather_upgrade_enabled": False,
                    "future_rain_upgrade_enabled": False,
                },
            )
        }

        self.assertNotIn("rain_6h_threshold", default_keys)
        self.assertIn("weather_upgrade_6h", default_keys)
        self.assertIn("rain_6h_threshold", custom_keys)
        self.assertNotIn("weather_upgrade_6h", custom_keys)

    def test_monitor_dry_run_keeps_job_state_isolated_and_unsent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            state_path = root / "state.json"
            config_path.write_text(
                json.dumps(
                    {
                        "locations": [
                            {
                                "id": "jiayu",
                                "name": "嘉鱼县",
                                "latitude": 29.9724209,
                                "longitude": 113.9335326,
                                "source": "test",
                                "enabled": True,
                                "default": True,
                            },
                            {
                                "id": "wuhan",
                                "name": "武汉市",
                                "latitude": 30.5928,
                                "longitude": 114.3055,
                                "source": "test",
                                "enabled": True,
                                "default": False,
                            },
                        ],
                        "wechat_targets": [
                            {"id": "xiangnan", "name": "湘楠", "enabled": True, "default": True},
                            {"id": "backup", "name": "备用", "enabled": True, "default": False},
                        ],
                        "automation_jobs": [
                            {
                                "id": "default",
                                "location_id": "jiayu",
                                "wechat_target_id": "xiangnan",
                                "enabled": True,
                                "interval_minutes": 120,
                                "fixed_times": [],
                                "quiet_start": "22:00",
                                "quiet_end": "07:00",
                                "allow_quiet_send": False,
                            },
                            {
                                "id": "backup",
                                "location_id": "wuhan",
                                "wechat_target_id": "backup",
                                "enabled": True,
                                "interval_minutes": 120,
                                "fixed_times": [],
                                "quiet_start": "22:00",
                                "quiet_end": "07:00",
                                "allow_quiet_send": False,
                            },
                        ],
                        "providers": {"comparison_models": []},
                        "message": {
                            "daily_style": "segmented_brief",
                            "daily_prefix": "早上好，今天出门前看一下天气：",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshots = {
                "jiayu": [make_snapshot("嘉鱼县", 10), make_snapshot("嘉鱼县", 80, code=65)],
                "wuhan": [make_snapshot("武汉市", 10), make_snapshot("武汉市", 10)],
            }
            monitor = FakeMonitor(str(config_path), state_path, snapshots)

            fixed_now = datetime.combine(date.today(), time(10, 0))
            with patch("wechat_weather.monitor._now", return_value=fixed_now):
                monitor.check_once(real_send=False)
                result = monitor.check_once(real_send=False, job_id="default")

            self.assertTrue(result["ok"])
            self.assertFalse(result["results"][0]["sent"])
            self.assertFalse(result["results"][0]["message"].startswith("早上好"))
            self.assertIn("天气预报有新变化", result["results"][0]["message"])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("default", state["jobs"])
            self.assertIn("backup", state["jobs"])
            sent_today = state["jobs"]["default"]["sent_alert_keys"][fixed_now.strftime("%Y-%m-%d")]
            self.assertEqual(sent_today, [])

    def test_interval_task_skips_outside_active_window_without_weather_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            state_path = root / "state.json"
            config_path.write_text(
                json.dumps(
                    {
                        "locations": [
                            {
                                "id": "jiayu",
                                "name": "嘉鱼县",
                                "latitude": 29.9724209,
                                "longitude": 113.9335326,
                                "source": "test",
                                "enabled": True,
                                "default": True,
                            }
                        ],
                        "wechat_targets": [
                            {"id": "xiangnan", "name": "湘楠", "enabled": True, "default": True}
                        ],
                        "automation_jobs": [
                            {
                                "id": "default",
                                "location_id": "jiayu",
                                "wechat_target_id": "xiangnan",
                                "enabled": True,
                                "interval_minutes": 120,
                                "fixed_times": [],
                                "active_windows": ["07:00-22:00"],
                                "allow_quiet_send": False,
                            }
                        ],
                        "providers": {"comparison_models": []},
                        "message": {
                            "daily_style": "segmented_brief",
                            "daily_prefix": "早上好，今天出门前看一下天气：",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshot = make_snapshot("嘉鱼县", 80, code=65)
            snapshots = {"jiayu": [snapshot]}
            monitor = FakeMonitor(str(config_path), state_path, snapshots)
            fixed_now = datetime.combine(date.today(), time(23, 0))

            with patch("wechat_weather.monitor._now", return_value=fixed_now):
                result = monitor.check_once(real_send=False, job_id="default")

            self.assertEqual(result["results"][0]["type"], "interval_skipped")
            self.assertFalse(result["results"][0]["sent"])
            self.assertEqual(snapshots["jiayu"], [snapshot])

    def test_fixed_time_sends_full_weather_once_per_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            state_path = root / "state.json"
            config_path.write_text(
                json.dumps(
                    {
                        "locations": [
                            {
                                "id": "jiayu",
                                "name": "嘉鱼县",
                                "latitude": 29.9724209,
                                "longitude": 113.9335326,
                                "source": "test",
                                "enabled": True,
                                "default": True,
                            }
                        ],
                        "wechat_targets": [
                            {"id": "xiangnan", "name": "湘楠", "enabled": True, "default": True}
                        ],
                        "automation_jobs": [
                            {
                                "id": "default",
                                "location_id": "jiayu",
                                "wechat_target_id": "xiangnan",
                                "enabled": True,
                                "interval_minutes": 120,
                                "fixed_times": ["10:00"],
                                "quiet_start": "22:00",
                                "quiet_end": "07:00",
                                "allow_quiet_send": False,
                            }
                        ],
                        "providers": {"comparison_models": []},
                        "message": {
                            "daily_style": "segmented_brief",
                            "daily_prefix": "早上好，今天出门前看一下天气：",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            snapshots = {"jiayu": [make_snapshot("嘉鱼县", 10), make_snapshot("嘉鱼县", 10)]}
            monitor = FakeMonitor(str(config_path), state_path, snapshots)
            fixed_now = datetime.combine(date.today(), time(10, 0, 10))
            state_path.write_text(
                json.dumps(
                    {
                        "jobs": {
                            "default": {
                                "last_check_at": fixed_now.isoformat(timespec="seconds")
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with patch("wechat_weather.monitor._now", return_value=fixed_now):
                result = monitor.run_due(real_send=False)
                second = monitor.run_due(real_send=False)

            self.assertEqual(result["results"][0]["type"], "fixed_weather")
            self.assertTrue(result["results"][0]["send_result"]["ok"])
            self.assertTrue(
                result["results"][0]["message"].startswith(
                    "早上好，今天出门前看一下天气：\n\n【嘉鱼县天气提醒】"
                )
            )
            self.assertEqual(second["results"], [])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn(f"{fixed_now.strftime('%Y-%m-%d')}:10:00", state["jobs"]["default"]["fixed_sent_keys"])

    def test_fixed_time_compensates_after_original_minute_was_missed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            state_path = root / "state.json"
            write_fixed_config(config_path, ["10:00"])
            monitor = FakeMonitor(str(config_path), state_path, {"jiayu": [make_snapshot("jiayu", 10)]})
            missed_now = datetime.combine(date.today(), time(11, 30))
            state_path.write_text(
                json.dumps({"jobs": {"default": {"last_check_at": missed_now.isoformat(timespec="seconds")}}}),
                encoding="utf-8",
            )

            with patch("wechat_weather.monitor._now", return_value=missed_now):
                result = monitor.run_due(real_send=False)

            self.assertEqual(result["results"][0]["type"], "fixed_weather")
            self.assertEqual(result["results"][0]["fixed_time"], "10:00")
            self.assertTrue(result["results"][0]["send_result"]["ok"])

    def test_fixed_time_expires_after_compensation_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            state_path = root / "state.json"
            write_fixed_config(config_path, ["10:00"])
            monitor = FakeMonitor(str(config_path), state_path, {"jiayu": [make_snapshot("jiayu", 10)]})
            expired_now = datetime.combine(date.today(), time(13, 1))
            state_path.write_text(
                json.dumps({"jobs": {"default": {"last_check_at": expired_now.isoformat(timespec="seconds")}}}),
                encoding="utf-8",
            )

            with patch("wechat_weather.monitor._now", return_value=expired_now):
                result = monitor.run_due(real_send=False)

            self.assertEqual(result["results"][0]["type"], "fixed_weather_expired")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn(f"{expired_now.strftime('%Y-%m-%d')}:10:00", state["jobs"]["default"]["fixed_expired_keys"])

    def test_fixed_time_waits_for_readiness_when_real_send_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            state_path = root / "state.json"
            write_fixed_config(config_path, ["10:00"])
            monitor = FakeMonitor(str(config_path), state_path, {"jiayu": [make_snapshot("jiayu", 10)]})
            fixed_now = datetime.combine(date.today(), time(10, 5))
            state_path.write_text(
                json.dumps({"jobs": {"default": {"last_check_at": fixed_now.isoformat(timespec="seconds")}}}),
                encoding="utf-8",
            )

            with patch("wechat_weather.monitor._now", return_value=fixed_now):
                with patch("wechat_weather.readiness.check_readiness", return_value=BlockedReadiness()):
                    result = monitor.run_due(real_send=True)

            item = result["results"][0]
            self.assertFalse(item["sent"])
            self.assertTrue(item["will_retry"])
            self.assertEqual(item["blocked_reason"], "blocked_sleep_or_locked")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            pending = state["jobs"]["default"]["fixed_pending"][f"{fixed_now.strftime('%Y-%m-%d')}:10:00"]
            self.assertEqual(pending["status"], "waiting_for_ready")


if __name__ == "__main__":
    unittest.main()
