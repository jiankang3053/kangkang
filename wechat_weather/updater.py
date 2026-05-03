# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any
import requests

from .config import APP_VERSION


def _version_tuple(value: str) -> tuple[int, ...]:
    value = value.strip().lstrip("v")
    parts = []
    for part in value.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def check_latest_release(repo: str = "jiankang3053/kangkang", timeout: float = 8.0) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        response = requests.get(url, timeout=timeout, headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        data = response.json()
        latest = str(data.get("tag_name") or "").lstrip("v")
        assets = [
            {
                "name": item.get("name"),
                "download_url": item.get("browser_download_url"),
                "size": item.get("size"),
            }
            for item in data.get("assets", [])
        ]
        return {
            "ok": True,
            "current_version": APP_VERSION,
            "latest_version": latest,
            "has_update": bool(latest and _version_tuple(latest) > _version_tuple(APP_VERSION)),
            "release_url": data.get("html_url"),
            "assets": assets,
        }
    except Exception as exc:
        return {
            "ok": False,
            "current_version": APP_VERSION,
            "latest_version": None,
            "has_update": False,
            "release_url": None,
            "assets": [],
            "error": str(exc),
        }

