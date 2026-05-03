from __future__ import annotations

from datetime import date, datetime, timedelta
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from wechat_weather.config import APP_VERSION, load_config
from wechat_weather.regions import find_region, search_regions
from wechat_weather.server import WeatherServer
from wechat_weather.weather import _append_weather_history, read_weather_history


def message_snapshot(city: str = "嘉鱼县") -> dict:
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
                "rain": 80,
                "sources": ["test"],
            }
            for hour in range(24)
        ]
        days.append(
            {
                "date": current.isoformat(),
                "code": 61,
                "temp_min": 14 + offset,
                "temp_max": 21 + offset,
                "rain_max": 80,
                "hourly_codes": [61] * 24,
                "hourly_rain": [80] * 24,
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


def get_json(port: int, path: str) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        return response.status, data
    finally:
        connection.close()


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


class V241RegionsHistoryTests(unittest.TestCase):
    def test_region_search_finds_jiayu_without_coordinates(self) -> None:
        result = search_regions("嘉鱼", limit=5)

        self.assertTrue(result)
        self.assertEqual(result[0]["code"], "421221")
        self.assertEqual(result[0]["address_path"], ["湖北省", "咸宁市", "嘉鱼县"])
        self.assertNotIn("latitude", result[0])
        self.assertEqual(find_region("421221")["name"], "嘉鱼县")

    def test_old_location_config_gets_region_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "locations": [
                            {
                                "id": "jiayu",
                                "name": "嘉鱼县",
                                "latitude": 29.9724209,
                                "longitude": 113.9335326,
                                "enabled": True,
                                "default": True,
                            }
                        ],
                        "wechat_targets": [{"id": "target", "name": "文件传输助手", "enabled": True, "default": True}],
                        "automation_jobs": [{"id": "default", "location_id": "jiayu", "wechat_target_id": "target"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            cfg = load_config(str(config_path))

        self.assertEqual(APP_VERSION, "3.1.1")
        self.assertEqual(cfg.default_location.region_code, "421221")
        self.assertEqual(cfg.default_location.address_path, ["湖北省", "咸宁市", "嘉鱼县"])

    def test_weather_history_trims_to_latest_200(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"APPDATA": tmp}):
                start = datetime.now() - timedelta(seconds=1)
                for index in range(205):
                    _append_weather_history(
                        {
                            "fetched_at": f"2026-04-28T10:{index:02d}:00",
                            "address": "嘉鱼县",
                            "source": "test",
                            "sources": ["test"],
                            "source_count": 1,
                            "failures": [],
                            "cached": False,
                            "stale": False,
                            "source_disagreement": False,
                            "elapsed_ms": int((datetime.now() - start).total_seconds() * 1000),
                            "status": "ok",
                            "error": "",
                        }
                    )
                history = read_weather_history(limit=250)

        self.assertEqual(len(history), 200)
        self.assertEqual(history[0]["fetched_at"], "2026-04-28T10:204:00")
        self.assertEqual(history[-1]["fetched_at"], "2026-04-28T10:05:00")

    def test_regions_and_history_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(json.dumps({"app": {"setup_complete": False}}, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"APPDATA": tmp}):
                with patch("wechat_weather.server.WeatherMonitor.start", return_value=None):
                    server, thread = run_test_server(config_path)
                    try:
                        status, search = get_json(server.server_port, "/api/regions/search?query=%E5%98%89%E9%B1%BC")
                        history_status, history = get_json(server.server_port, "/api/weather/history?limit=10")
                    finally:
                        server.shutdown()
                        server.server_close()
                        thread.join(timeout=2)

        self.assertEqual(status, 200)
        self.assertEqual(search["results"][0]["code"], "421221")
        self.assertEqual(history_status, 200)
        self.assertEqual(history["history"], [])

    def test_message_prefix_api_updates_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "app": {"setup_complete": True},
                        "locations": [
                            {
                                "id": "jiayu",
                                "name": "嘉鱼县",
                                "latitude": 29.9724209,
                                "longitude": 113.9335326,
                                "region_code": "421221",
                                "address_path": ["湖北省", "咸宁市", "嘉鱼县"],
                                "enabled": True,
                                "default": True,
                            }
                        ],
                        "wechat_targets": [{"id": "target", "name": "微信快存", "enabled": True, "default": True}],
                        "automation_jobs": [{"id": "default", "location_id": "jiayu", "wechat_target_id": "target"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch("wechat_weather.server.WeatherMonitor.start", return_value=None):
                with patch("wechat_weather.server.build_weather_snapshot", return_value=message_snapshot("嘉鱼县")):
                    server, thread = run_test_server(config_path)
                    try:
                        prefix = "早上好，今天出门前看一下天气："
                        post_status, post_data = post_json(
                            server.server_port,
                            "/api/message",
                            {"daily_style": "segmented_brief", "daily_prefix": prefix},
                        )
                        state_status, state = get_json(server.server_port, "/api/state")
                        preview_status, preview = get_json(
                            server.server_port,
                            "/api/preview?location_id=jiayu&wechat_target_id=target",
                        )
                    finally:
                        server.shutdown()
                        server.server_close()
                        thread.join(timeout=2)

        self.assertEqual(post_status, 200)
        self.assertEqual(post_data["message"]["daily_prefix"], prefix)
        self.assertEqual(state_status, 200)
        self.assertEqual(state["message"]["daily_prefix"], prefix)
        self.assertEqual(preview_status, 200)
        self.assertTrue(preview["message"].startswith(f"{prefix}\n\n【嘉鱼县天气提醒】"))
        self.assertNotIn("大后天", preview["message"])

    def test_setup_complete_accepts_region_code_and_resolves_coordinates(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"lat": "29.9724209", "lon": "113.9335326"}]

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(json.dumps({"app": {"setup_complete": False}}, ensure_ascii=False), encoding="utf-8")
            with patch("wechat_weather.server.WeatherMonitor.start", return_value=None):
                with patch("wechat_weather.regions.requests.get", return_value=response):
                    server, thread = run_test_server(config_path)
                    try:
                        status, data = post_json(
                            server.server_port,
                            "/api/setup/complete",
                            {
                                "location": {
                                    "region_code": "421221",
                                    "name": "嘉鱼县",
                                    "address_path": ["湖北省", "咸宁市", "嘉鱼县"],
                                },
                                "wechat_target": "文件传输助手",
                            },
                        )
                    finally:
                        server.shutdown()
                        server.server_close()
                        thread.join(timeout=2)
            cfg = load_config(str(config_path))

        self.assertEqual(status, 200)
        self.assertTrue(data["setup_complete"])
        self.assertEqual(cfg.default_location.region_code, "421221")
        self.assertEqual(cfg.default_location.latitude, 29.9724209)
        self.assertEqual(cfg.default_wechat_target.name, "文件传输助手")


if __name__ == "__main__":
    unittest.main()
