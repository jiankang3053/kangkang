# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wechat_weather import updater
from wechat_weather.migration import export_migration_package, inspect_migration_package
from wechat_weather.run_trace import append_step, new_run_id, read_runs, read_steps


class V31RuntimeTests(unittest.TestCase):
    def test_run_trace_groups_steps_by_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"APPDATA": tmp}):
                run_id = new_run_id("test")
                append_step(run_id, "start", "running", "started", run_type="unit")
                append_step(run_id, "finish", "ok", "finished", run_type="unit")

                steps = read_steps(run_id=run_id)
                runs = read_runs(limit=5)

        self.assertEqual([item["step"] for item in steps], ["start", "finish"])
        self.assertEqual(runs[-1]["run_id"], run_id)
        self.assertEqual(runs[-1]["status"], "ok")
        self.assertEqual(runs[-1]["step_count"], 2)

    def test_migration_package_requires_target_reverify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "app": {"setup_complete": True},
                        "locations": [
                            {
                                "id": "loc",
                                "name": "嘉鱼县",
                                "latitude": 29.9724209,
                                "longitude": 113.9335326,
                                "enabled": True,
                                "default": True,
                            }
                        ],
                        "wechat_targets": [
                            {
                                "id": "target",
                                "name": "文件传输助手",
                                "enabled": True,
                                "default": True,
                                "verified": True,
                            }
                        ],
                        "automation_jobs": [
                            {
                                "id": "job",
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
            with patch.dict(os.environ, {"APPDATA": tmp}):
                package = export_migration_package(str(config_path))
                summary = inspect_migration_package(package)
                package_exists = package.exists()

        self.assertTrue(package_exists)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["summary"]["locations"], 1)
        self.assertEqual(summary["summary"]["wechat_targets"], 1)
        self.assertTrue(summary["summary"]["requires_reverify"])

    def test_update_check_detects_newer_github_release(self) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "tag_name": "v9.9.9",
                    "html_url": "https://github.com/jiankang3053/kangkang/releases/tag/v9.9.9",
                    "assets": [
                        {
                            "name": "KangkangWeather-v9.9.9.zip",
                            "browser_download_url": "https://example.com/KangkangWeather-v9.9.9.zip",
                            "size": 123,
                        }
                    ],
                }

        with patch.object(updater.requests, "get", return_value=FakeResponse()) as mocked_get:
            result = updater.check_latest_release(timeout=1)

        self.assertTrue(result["ok"])
        self.assertTrue(result["has_update"])
        self.assertEqual(result["latest_version"], "9.9.9")
        mocked_get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
