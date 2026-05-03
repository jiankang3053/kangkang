from __future__ import annotations

from datetime import date, datetime, timedelta
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from wechat_weather.config import APP_VERSION, load_config, read_config_data
from wechat_weather.send_batch import (
    SendTaskLock,
    append_send_history,
    create_send_batch,
    read_send_history,
)
from wechat_weather.server import WeatherServer


def snapshot(city: str = "Test City") -> dict:
    start = date.today()
    days = []
    for offset in range(3):
        current = start + timedelta(days=offset)
        rows = [
            {
                "time": f"{current.isoformat()}T{hour:02d}:00",
                "date": current.isoformat(),
                "hour": hour,
                "code": 61,
                "rain": 70,
                "sources": ["test"],
            }
            for hour in range(24)
        ]
        days.append(
            {
                "date": current.isoformat(),
                "code": 61,
                "temp_min": 14,
                "temp_max": 21,
                "rain_max": 70,
                "hourly_codes": [61] * 24,
                "hourly_rain": [70] * 24,
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


def post_json(port: int, path: str, payload: dict) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request("POST", path, body=body, headers={"Content-Type": "application/json"})
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


class V35SendBatchTests(unittest.TestCase):
    def test_target_config_upgrade_adds_send_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "app": {"setup_complete": True},
                        "locations": [
                            {
                                "id": "loc",
                                "name": "Test City",
                                "latitude": 30.0,
                                "longitude": 114.0,
                                "enabled": True,
                                "default": True,
                            }
                        ],
                        "wechat_targets": [
                            {"id": "target", "name": "File Helper", "enabled": True, "default": True}
                        ],
                        "automation_jobs": [
                            {"id": "job", "location_id": "loc", "wechat_target_id": "target"}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            cfg = load_config(str(config_path))
            data = read_config_data(str(config_path))

        self.assertEqual(APP_VERSION, "3.6.0")
        self.assertEqual(cfg.config_version, 3)
        self.assertEqual(data["config_version"], 3)
        self.assertEqual(cfg.default_wechat_target.type, "friend")
        self.assertEqual(cfg.default_wechat_target.send_interval_seconds, 3)
        self.assertEqual(cfg.default_wechat_target.last_send_status, None)

    def test_corrupt_config_is_backed_up_and_defaults_are_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text("{not-valid-json", encoding="utf-8")

            data = read_config_data(str(config_path))
            backups = list(Path(tmp).glob("config.corrupt.*.json"))

        self.assertEqual(data["config_version"], 3)
        self.assertTrue(backups)

    def test_send_batch_history_and_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"APPDATA": tmp}):
                cfg = load_config(None)
                batch = create_send_batch(
                    trigger="unit",
                    location=cfg.default_location,
                    message="hello",
                    targets=[cfg.default_wechat_target],
                    real_send=False,
                )
                batch.status = "dry_run"
                batch.targets[0].status = "skipped"
                history_path = append_send_history(batch)
                history = read_send_history(limit=5)
                history_exists = history_path.exists()

                lock_path = Path(tmp) / "lock.json"
                lock1 = SendTaskLock(lock_path, owner="a")
                lock2 = SendTaskLock(lock_path, owner="b")
                first_acquire = lock1.acquire()
                second_acquire = lock2.acquire()
                lock1.release()
                third_acquire = lock2.acquire()
                lock2.release()

        self.assertTrue(history_exists)
        self.assertEqual(history[-1]["batch_id"], batch.batch_id)
        self.assertEqual(history[-1]["summary"]["skipped"], 1)
        self.assertTrue(first_acquire)
        self.assertFalse(second_acquire)
        self.assertTrue(third_acquire)

    def test_send_weather_dry_run_supports_all_enabled_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "app": {"setup_complete": True},
                        "locations": [
                            {
                                "id": "loc",
                                "name": "Test City",
                                "latitude": 30.0,
                                "longitude": 114.0,
                                "enabled": True,
                                "default": True,
                            }
                        ],
                        "wechat_targets": [
                            {"id": "a", "name": "Target A", "enabled": True, "default": True},
                            {"id": "b", "name": "Target B", "enabled": True, "default": False},
                            {"id": "c", "name": "Disabled", "enabled": False, "default": False},
                        ],
                        "automation_jobs": [
                            {"id": "job", "location_id": "loc", "wechat_target_id": "a"}
                        ],
                        "providers": {"comparison_models": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"APPDATA": tmp}):
                with patch("wechat_weather.server.WeatherMonitor.start", return_value=None):
                    with patch("wechat_weather.server.build_weather_snapshot", return_value=snapshot("Test City")):
                        with patch("wechat_weather.server.choose_sender", side_effect=AssertionError("must not send")):
                            server, thread = run_test_server(config_path)
                            try:
                                status, data = post_json(
                                    server.server_port,
                                    "/api/send-weather",
                                    {"location_id": "loc", "send_all_enabled": True, "dry_run": True},
                                )
                            finally:
                                server.shutdown()
                                server.server_close()
                                thread.join(timeout=2)
                history = read_send_history(limit=5)

        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["summary"]["total"], 2)
        self.assertEqual(data["summary"]["skipped"], 2)
        self.assertEqual(data["contacts"], ["Target A", "Target B"])
        self.assertEqual(history[-1]["batch_id"], data["batch"]["batch_id"])


if __name__ == "__main__":
    unittest.main()
