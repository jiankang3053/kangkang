# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .weather import WeatherConfig


@dataclass(frozen=True)
class MonitorConfig:
    enabled: bool = True
    interval_minutes: int = 120
    contact: str = "湘楠"
    backend: str = "pywinauto-session"
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"
    state_path: str = "weather_poll_state.json"


@dataclass(frozen=True)
class AppConfig:
    contact: str = "湘楠"
    weather: WeatherConfig = WeatherConfig()
    monitor: MonitorConfig = MonitorConfig()


def load_config(path: str | None) -> AppConfig:
    if path is None:
        return AppConfig()

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    weather = raw.get("weather", {})
    default_contact = str(raw.get("contact", "湘楠"))
    monitor = raw.get("monitor", {})
    return AppConfig(
        contact=default_contact,
        weather=WeatherConfig(
            city_query=str(weather.get("city_query", "Jiayu County")),
            city_label=str(weather.get("city_label", "嘉鱼县")),
            timeout_seconds=float(weather.get("timeout_seconds", 20.0)),
            language=str(weather.get("language", "zh-cn")),
            latitude=float(weather.get("latitude", 29.9724209)),
            longitude=float(weather.get("longitude", 113.9335326)),
        ),
        monitor=MonitorConfig(
            enabled=bool(monitor.get("enabled", True)),
            interval_minutes=int(monitor.get("interval_minutes", 120)),
            contact=str(monitor.get("contact", default_contact)),
            backend=str(monitor.get("backend", "pywinauto-session")),
            quiet_start=str(monitor.get("quiet_start", "22:00")),
            quiet_end=str(monitor.get("quiet_end", "07:00")),
            state_path=str(monitor.get("state_path", "weather_poll_state.json")),
        ),
    )


def dump_example(path: str) -> None:
    data: dict[str, Any] = {
        "contact": "湘楠",
        "weather": {
            "city_query": "Jiayu County",
            "city_label": "嘉鱼县",
            "timeout_seconds": 20,
            "language": "zh-cn",
            "latitude": 29.9724209,
            "longitude": 113.9335326,
        },
        "monitor": {
            "enabled": True,
            "interval_minutes": 120,
            "contact": "湘楠",
            "backend": "pywinauto-session",
            "quiet_start": "22:00",
            "quiet_end": "07:00",
            "state_path": "weather_poll_state.json",
        },
    }
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
