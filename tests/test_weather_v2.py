from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wechat_weather.config import load_config, read_config_data
from wechat_weather.monitor import WeatherMonitor, evaluate_alerts
from wechat_weather.weather import WeatherConfig, merge_snapshots


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


class WeatherV2Tests(unittest.TestCase):
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
            self.assertEqual(cfg.default_location.name, "嘉鱼县")
            self.assertEqual(len(data["locations"]), 2)
            self.assertEqual(len(data["wechat_targets"]), 2)
            self.assertEqual(len(data["automation_jobs"]), 2)

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
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("default", state["jobs"])
            self.assertIn("backup", state["jobs"])
            sent_today = state["jobs"]["default"]["sent_alert_keys"][fixed_now.strftime("%Y-%m-%d")]
            self.assertEqual(sent_today, [])

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
            self.assertEqual(second["results"], [])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn(f"{fixed_now.strftime('%Y-%m-%d')}:10:00", state["jobs"]["default"]["fixed_sent_keys"])


if __name__ == "__main__":
    unittest.main()
