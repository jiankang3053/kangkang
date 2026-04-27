from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def _recipient_weather_snapshot(self, config, recipient):
        queue = self._snapshots[recipient.name]
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

    def test_monitor_dry_run_keeps_recipient_state_isolated_and_unsent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            state_path = root / "state.json"
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
            snapshots = {
                "湘楠": [make_snapshot("嘉鱼县", 10), make_snapshot("嘉鱼县", 80, code=65)],
                "备用": [make_snapshot("武汉市", 10), make_snapshot("武汉市", 10)],
            }
            monitor = FakeMonitor(str(config_path), state_path, snapshots)

            fixed_now = datetime.combine(date.today(), time(10, 0))
            with patch("wechat_weather.monitor._now", return_value=fixed_now):
                monitor.check_once(real_send=False)
                result = monitor.check_once(real_send=False, recipient_name="湘楠")

            self.assertTrue(result["ok"])
            self.assertFalse(result["results"][0]["sent"])
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("湘楠", state["recipients"])
            self.assertIn("备用", state["recipients"])
            sent_today = state["recipients"]["湘楠"]["sent_alert_keys"][fixed_now.strftime("%Y-%m-%d")]
            self.assertEqual(sent_today, [])


if __name__ == "__main__":
    unittest.main()
