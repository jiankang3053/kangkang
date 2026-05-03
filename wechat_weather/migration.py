# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from .config import config_to_dict, load_config, user_data_dir


def _migration_dir() -> Path:
    path = user_data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_migration_package(config_path: str | None = None) -> Path:
    config = load_config(config_path, create_user_config=config_path is None)
    data = config_to_dict(config)
    data["app"]["setup_complete"] = False
    for target in data.get("wechat_targets", []):
        target["verified"] = False
        target.pop("last_open_test_at", None)
        target.pop("last_send_test_at", None)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = _migration_dir() / f"KangkangWeather-migration-{stamp}.zip"
    manifest = {
        "kind": "KangkangWeatherMigration",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "contains": ["config.json"],
        "requires_reverify": True,
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (root / "config.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.write(root / "manifest.json", "manifest.json")
            archive.write(root / "config.json", "config.json")
    return output


def inspect_migration_package(path: str | Path) -> dict[str, Any]:
    package = Path(path)
    with ZipFile(package) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8")) if "manifest.json" in names else {}
        config = json.loads(archive.read("config.json").decode("utf-8")) if "config.json" in names else {}
    return {
        "ok": "config.json" in names,
        "path": str(package),
        "manifest": manifest,
        "summary": {
            "locations": len(config.get("locations", [])),
            "wechat_targets": len(config.get("wechat_targets", [])),
            "automation_jobs": len(config.get("automation_jobs", [])),
            "requires_reverify": True,
        },
    }

