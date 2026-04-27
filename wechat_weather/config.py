# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any

from .weather import WeatherConfig


APP_NAME = "KangkangWeather"
APP_VERSION = "2.0.0"
DEFAULT_CONTACT = "湘楠"
DEFAULT_CITY_LABEL = "嘉鱼县"
DEFAULT_LATITUDE = 29.9724209
DEFAULT_LONGITUDE = 113.9335326


@dataclass(frozen=True)
class AppSettings:
    name: str = APP_NAME
    version: str = APP_VERSION
    host: str = "127.0.0.1"
    port: int = 8766
    open_browser_on_start: bool = True


@dataclass(frozen=True)
class RecipientConfig:
    name: str = DEFAULT_CONTACT
    city_label: str = DEFAULT_CITY_LABEL
    latitude: float = DEFAULT_LATITUDE
    longitude: float = DEFAULT_LONGITUDE
    enabled: bool = True

    def weather_config(self, timeout_seconds: float, language: str) -> WeatherConfig:
        return WeatherConfig(
            city_query=self.city_label,
            city_label=self.city_label,
            timeout_seconds=timeout_seconds,
            language=language,
            latitude=self.latitude,
            longitude=self.longitude,
        )


@dataclass(frozen=True)
class ProvidersConfig:
    timeout_seconds: float = 20.0
    language: str = "zh-cn"
    primary: str = "open_meteo_best_match"
    comparison_models: list[str] = field(
        default_factory=lambda: ["gfs_seamless", "icon_seamless", "cma_grapes_global"]
    )
    fallback_wttr: bool = True


@dataclass(frozen=True)
class MonitorConfig:
    enabled: bool = True
    interval_minutes: int = 120
    backend: str = "pywinauto-session"
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"
    state_path: str = "weather_poll_state.json"
    future_hours: int = 6
    daily_history_limit: int = 5


@dataclass(frozen=True)
class ReleaseConfig:
    package_name: str = "KangkangWeather"
    version: str = APP_VERSION
    output_dir: str = "dist"


@dataclass(frozen=True)
class AppConfig:
    app: AppSettings = AppSettings()
    contact: str = DEFAULT_CONTACT
    recipients: list[RecipientConfig] = field(default_factory=lambda: [RecipientConfig()])
    providers: ProvidersConfig = ProvidersConfig()
    monitor: MonitorConfig = MonitorConfig()
    release: ReleaseConfig = ReleaseConfig()

    @property
    def default_recipient(self) -> RecipientConfig:
        for recipient in self.recipients:
            if recipient.name == self.contact:
                return recipient
        for recipient in self.recipients:
            if recipient.enabled:
                return recipient
        return self.recipients[0]

    def recipient_by_name(self, name: str | None) -> RecipientConfig:
        if not name:
            return self.default_recipient
        for recipient in self.recipients:
            if recipient.name == name:
                return recipient
        raise KeyError(f"没有找到发送目标：{name}")


def user_data_dir() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / APP_NAME
    return Path.home() / f".{APP_NAME}"


def default_user_config_path() -> Path:
    return user_data_dir() / "config.json"


def _default_data() -> dict[str, Any]:
    return {
        "app": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "host": "127.0.0.1",
            "port": 8766,
            "open_browser_on_start": True,
        },
        "contact": DEFAULT_CONTACT,
        "recipients": [
            {
                "name": DEFAULT_CONTACT,
                "city_label": DEFAULT_CITY_LABEL,
                "latitude": DEFAULT_LATITUDE,
                "longitude": DEFAULT_LONGITUDE,
                "enabled": True,
            }
        ],
        "providers": {
            "timeout_seconds": 20,
            "language": "zh-cn",
            "primary": "open_meteo_best_match",
            "comparison_models": ["gfs_seamless", "icon_seamless", "cma_grapes_global"],
            "fallback_wttr": True,
        },
        "monitor": {
            "enabled": True,
            "interval_minutes": 120,
            "backend": "pywinauto-session",
            "quiet_start": "22:00",
            "quiet_end": "07:00",
            "state_path": "weather_poll_state.json",
            "future_hours": 6,
            "daily_history_limit": 5,
        },
        "release": {
            "package_name": "KangkangWeather",
            "version": APP_VERSION,
            "output_dir": "dist",
        },
    }


def ensure_user_config() -> Path:
    path = default_user_config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_default_data(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return path


def _read_config_data(path: str | None, create_user_config: bool) -> tuple[dict[str, Any], Path | None]:
    if path is None:
        config_path = ensure_user_config() if create_user_config else None
        if config_path is None:
            return _default_data(), None
    else:
        config_path = Path(path)
    return json.loads(config_path.read_text(encoding="utf-8")), config_path


def _legacy_recipient(raw: dict[str, Any]) -> RecipientConfig:
    weather = raw.get("weather", {})
    return RecipientConfig(
        name=str(raw.get("contact", DEFAULT_CONTACT)),
        city_label=str(weather.get("city_label", DEFAULT_CITY_LABEL)),
        latitude=float(weather.get("latitude", DEFAULT_LATITUDE)),
        longitude=float(weather.get("longitude", DEFAULT_LONGITUDE)),
        enabled=True,
    )


def load_config(path: str | None, create_user_config: bool = False) -> AppConfig:
    raw, _ = _read_config_data(path, create_user_config=create_user_config)

    app_raw = raw.get("app", {})
    providers_raw = raw.get("providers", {})
    monitor_raw = raw.get("monitor", {})
    release_raw = raw.get("release", {})

    if "recipients" in raw:
        recipients = [
            RecipientConfig(
                name=str(item.get("name", DEFAULT_CONTACT)),
                city_label=str(item.get("city_label", DEFAULT_CITY_LABEL)),
                latitude=float(item.get("latitude", DEFAULT_LATITUDE)),
                longitude=float(item.get("longitude", DEFAULT_LONGITUDE)),
                enabled=bool(item.get("enabled", True)),
            )
            for item in raw.get("recipients", [])
        ]
    else:
        recipients = [_legacy_recipient(raw)]

    if not recipients:
        recipients = [RecipientConfig()]

    default_contact = str(raw.get("contact", recipients[0].name))

    # Backward compatibility: old configs placed timeout/language under weather.
    weather_raw = raw.get("weather", {})
    timeout_seconds = float(
        providers_raw.get("timeout_seconds", weather_raw.get("timeout_seconds", 20.0))
    )
    language = str(providers_raw.get("language", weather_raw.get("language", "zh-cn")))

    return AppConfig(
        app=AppSettings(
            name=str(app_raw.get("name", APP_NAME)),
            version=str(app_raw.get("version", APP_VERSION)),
            host=str(app_raw.get("host", "127.0.0.1")),
            port=int(app_raw.get("port", 8766)),
            open_browser_on_start=bool(app_raw.get("open_browser_on_start", True)),
        ),
        contact=default_contact,
        recipients=recipients,
        providers=ProvidersConfig(
            timeout_seconds=timeout_seconds,
            language=language,
            primary=str(providers_raw.get("primary", "open_meteo_best_match")),
            comparison_models=list(
                providers_raw.get(
                    "comparison_models",
                    ["gfs_seamless", "icon_seamless", "cma_grapes_global"],
                )
            ),
            fallback_wttr=bool(providers_raw.get("fallback_wttr", True)),
        ),
        monitor=MonitorConfig(
            enabled=bool(monitor_raw.get("enabled", True)),
            interval_minutes=int(monitor_raw.get("interval_minutes", 120)),
            backend=str(monitor_raw.get("backend", "pywinauto-session")),
            quiet_start=str(monitor_raw.get("quiet_start", "22:00")),
            quiet_end=str(monitor_raw.get("quiet_end", "07:00")),
            state_path=str(monitor_raw.get("state_path", "weather_poll_state.json")),
            future_hours=int(monitor_raw.get("future_hours", 6)),
            daily_history_limit=int(monitor_raw.get("daily_history_limit", 5)),
        ),
        release=ReleaseConfig(
            package_name=str(release_raw.get("package_name", "KangkangWeather")),
            version=str(release_raw.get("version", APP_VERSION)),
            output_dir=str(release_raw.get("output_dir", "dist")),
        ),
    )


def dump_example(path: str) -> None:
    Path(path).write_text(
        json.dumps(_default_data(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
