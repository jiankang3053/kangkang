# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
from typing import Any

from .weather import WeatherConfig


APP_NAME = "KangkangWeather"
APP_VERSION = "2.1.0"
DEFAULT_CONTACT = "湘楠"
DEFAULT_CITY_LABEL = "嘉鱼县"
DEFAULT_LATITUDE = 29.9724209
DEFAULT_LONGITUDE = 113.9335326
DEFAULT_LOCATION_ID = "jiayu"
DEFAULT_TARGET_ID = "xiangnan"
DEFAULT_JOB_ID = "default"


@dataclass(frozen=True)
class AppSettings:
    name: str = APP_NAME
    version: str = APP_VERSION
    host: str = "127.0.0.1"
    port: int = 8766
    open_browser_on_start: bool = True


@dataclass(frozen=True)
class LocationConfig:
    id: str = DEFAULT_LOCATION_ID
    name: str = DEFAULT_CITY_LABEL
    latitude: float = DEFAULT_LATITUDE
    longitude: float = DEFAULT_LONGITUDE
    source: str = "default"
    enabled: bool = True
    default: bool = True

    def weather_config(self, timeout_seconds: float, language: str) -> WeatherConfig:
        return WeatherConfig(
            city_query=self.name,
            city_label=self.name,
            timeout_seconds=timeout_seconds,
            language=language,
            latitude=self.latitude,
            longitude=self.longitude,
        )


@dataclass(frozen=True)
class WechatTargetConfig:
    id: str = DEFAULT_TARGET_ID
    name: str = DEFAULT_CONTACT
    enabled: bool = True
    default: bool = True


@dataclass(frozen=True)
class AutomationJobConfig:
    id: str = DEFAULT_JOB_ID
    location_id: str = DEFAULT_LOCATION_ID
    wechat_target_id: str = DEFAULT_TARGET_ID
    enabled: bool = True
    interval_minutes: int = 120
    fixed_times: list[str] = field(default_factory=list)
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"
    allow_quiet_send: bool = False


@dataclass(frozen=True)
class RecipientConfig:
    """Compatibility view for the v2 recipient model."""

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
    backend: str = "pywinauto-session"
    state_path: str = "weather_poll_state.json"
    future_hours: int = 6
    daily_history_limit: int = 5
    interval_minutes: int = 120
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"


@dataclass(frozen=True)
class ReleaseConfig:
    package_name: str = "KangkangWeather"
    version: str = APP_VERSION
    output_dir: str = "dist"


@dataclass(frozen=True)
class AppConfig:
    app: AppSettings = AppSettings()
    locations: list[LocationConfig] = field(default_factory=lambda: [LocationConfig()])
    wechat_targets: list[WechatTargetConfig] = field(
        default_factory=lambda: [WechatTargetConfig()]
    )
    automation_jobs: list[AutomationJobConfig] = field(
        default_factory=lambda: [AutomationJobConfig()]
    )
    providers: ProvidersConfig = ProvidersConfig()
    monitor: MonitorConfig = MonitorConfig()
    release: ReleaseConfig = ReleaseConfig()

    @property
    def default_location(self) -> LocationConfig:
        for location in self.locations:
            if location.default and location.enabled:
                return location
        for location in self.locations:
            if location.enabled:
                return location
        return self.locations[0]

    @property
    def default_wechat_target(self) -> WechatTargetConfig:
        for target in self.wechat_targets:
            if target.default and target.enabled:
                return target
        for target in self.wechat_targets:
            if target.enabled:
                return target
        return self.wechat_targets[0]

    @property
    def default_job(self) -> AutomationJobConfig:
        for job in self.automation_jobs:
            if (
                job.enabled
                and job.location_id == self.default_location.id
                and job.wechat_target_id == self.default_wechat_target.id
            ):
                return job
        for job in self.automation_jobs:
            if job.enabled:
                return job
        return self.automation_jobs[0]

    @property
    def contact(self) -> str:
        return self.default_wechat_target.name

    @property
    def recipients(self) -> list[RecipientConfig]:
        recipients: list[RecipientConfig] = []
        for job in self.automation_jobs:
            try:
                location = self.location_by_id(job.location_id)
                target = self.wechat_target_by_id(job.wechat_target_id)
            except KeyError:
                continue
            recipients.append(
                RecipientConfig(
                    name=target.name,
                    city_label=location.name,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    enabled=job.enabled and location.enabled and target.enabled,
                )
            )
        if recipients:
            return recipients
        return [
            RecipientConfig(
                name=self.default_wechat_target.name,
                city_label=self.default_location.name,
                latitude=self.default_location.latitude,
                longitude=self.default_location.longitude,
                enabled=True,
            )
        ]

    def location_by_id(self, value: str | None) -> LocationConfig:
        if not value:
            return self.default_location
        for location in self.locations:
            if location.id == value or location.name == value:
                return location
        raise KeyError(f"没有找到天气地址：{value}")

    def wechat_target_by_id(self, value: str | None) -> WechatTargetConfig:
        if not value:
            return self.default_wechat_target
        for target in self.wechat_targets:
            if target.id == value or target.name == value:
                return target
        raise KeyError(f"没有找到微信好友：{value}")

    def job_by_id(self, value: str | None) -> AutomationJobConfig:
        if not value:
            return self.default_job
        for job in self.automation_jobs:
            if job.id == value:
                return job
        raise KeyError(f"没有找到自动化任务：{value}")

    def jobs_for_target_name(self, name: str | None) -> list[AutomationJobConfig]:
        if not name:
            return [job for job in self.automation_jobs if job.enabled]
        target_ids = {
            target.id
            for target in self.wechat_targets
            if target.name == name or target.id == name
        }
        return [
            job
            for job in self.automation_jobs
            if job.enabled and job.wechat_target_id in target_ids
        ]

    def recipient_by_name(self, name: str | None) -> RecipientConfig:
        target = self.wechat_target_by_id(name)
        job = next(
            (
                item
                for item in self.automation_jobs
                if item.wechat_target_id == target.id and item.enabled
            ),
            self.default_job,
        )
        location = self.location_by_id(job.location_id)
        return RecipientConfig(
            name=target.name,
            city_label=location.name,
            latitude=location.latitude,
            longitude=location.longitude,
            enabled=target.enabled and location.enabled and job.enabled,
        )


def user_data_dir() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / APP_NAME
    return Path.home() / f".{APP_NAME}"


def default_user_config_path() -> Path:
    return user_data_dir() / "config.json"


def config_write_path(path: str | None) -> Path:
    if path is None:
        return ensure_user_config()
    return Path(path)


def _slug(prefix: str, value: Any, index: int) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text:
        text = str(index)
    return f"{prefix}-{text}"


def _time_value(value: Any, default: str) -> str:
    text = str(value or default).strip()
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        hour, minute = text.split(":", 1)
        return f"{int(hour):02d}:{int(minute):02d}"
    return default


def normalize_fixed_times(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_values = [item.strip() for item in values.replace("，", ",").split(",")]
    elif isinstance(values, list):
        raw_values = values
    else:
        raw_values = []
    result: list[str] = []
    for value in raw_values:
        text = str(value).strip()
        if not text:
            continue
        normalized = _time_value(text, "")
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _default_data() -> dict[str, Any]:
    return {
        "app": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "host": "127.0.0.1",
            "port": 8766,
            "open_browser_on_start": True,
        },
        "locations": [
            {
                "id": DEFAULT_LOCATION_ID,
                "name": DEFAULT_CITY_LABEL,
                "latitude": DEFAULT_LATITUDE,
                "longitude": DEFAULT_LONGITUDE,
                "source": "default",
                "enabled": True,
                "default": True,
            }
        ],
        "wechat_targets": [
            {
                "id": DEFAULT_TARGET_ID,
                "name": DEFAULT_CONTACT,
                "enabled": True,
                "default": True,
            }
        ],
        "automation_jobs": [
            {
                "id": DEFAULT_JOB_ID,
                "location_id": DEFAULT_LOCATION_ID,
                "wechat_target_id": DEFAULT_TARGET_ID,
                "enabled": True,
                "interval_minutes": 120,
                "fixed_times": [],
                "quiet_start": "22:00",
                "quiet_end": "07:00",
                "allow_quiet_send": False,
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
            "backend": "pywinauto-session",
            "state_path": "weather_poll_state.json",
            "future_hours": 6,
            "daily_history_limit": 5,
            "interval_minutes": 120,
            "quiet_start": "22:00",
            "quiet_end": "07:00",
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


def _legacy_recipients(raw: dict[str, Any]) -> list[dict[str, Any]]:
    if raw.get("recipients"):
        return list(raw.get("recipients") or [])
    weather = raw.get("weather", {})
    return [
        {
            "name": raw.get("contact", DEFAULT_CONTACT),
            "city_label": weather.get("city_label", DEFAULT_CITY_LABEL),
            "latitude": weather.get("latitude", DEFAULT_LATITUDE),
            "longitude": weather.get("longitude", DEFAULT_LONGITUDE),
            "enabled": True,
        }
    ]


def normalize_config_data(raw: dict[str, Any]) -> dict[str, Any]:
    defaults = _default_data()
    app_raw = {**defaults["app"], **raw.get("app", {})}
    providers_raw = {**defaults["providers"], **raw.get("providers", {})}
    monitor_raw = {**defaults["monitor"], **raw.get("monitor", {})}
    release_raw = {**defaults["release"], **raw.get("release", {})}
    app_raw["version"] = APP_VERSION
    release_raw["version"] = APP_VERSION

    if "locations" in raw and "wechat_targets" in raw:
        locations_raw = list(raw.get("locations") or [])
        targets_raw = list(raw.get("wechat_targets") or [])
        jobs_raw = list(raw.get("automation_jobs") or [])
    else:
        legacy = _legacy_recipients(raw)
        default_contact = str(raw.get("contact", legacy[0].get("name", DEFAULT_CONTACT)))
        locations_raw = []
        targets_raw = []
        jobs_raw = []
        for index, item in enumerate(legacy, start=1):
            location_id = DEFAULT_LOCATION_ID if index == 1 else _slug("loc", item.get("city_label"), index)
            target_id = DEFAULT_TARGET_ID if str(item.get("name")) == DEFAULT_CONTACT else _slug("target", item.get("name"), index)
            job_id = DEFAULT_JOB_ID if str(item.get("name")) == default_contact else _slug("job", item.get("name"), index)
            locations_raw.append(
                {
                    "id": location_id,
                    "name": item.get("city_label", DEFAULT_CITY_LABEL),
                    "latitude": item.get("latitude", DEFAULT_LATITUDE),
                    "longitude": item.get("longitude", DEFAULT_LONGITUDE),
                    "source": "legacy",
                    "enabled": bool(item.get("enabled", True)),
                    "default": str(item.get("name")) == default_contact,
                }
            )
            targets_raw.append(
                {
                    "id": target_id,
                    "name": item.get("name", DEFAULT_CONTACT),
                    "enabled": bool(item.get("enabled", True)),
                    "default": str(item.get("name")) == default_contact,
                }
            )
            jobs_raw.append(
                {
                    "id": job_id,
                    "location_id": location_id,
                    "wechat_target_id": target_id,
                    "enabled": bool(item.get("enabled", True)),
                    "interval_minutes": monitor_raw.get("interval_minutes", 120),
                    "fixed_times": [],
                    "quiet_start": monitor_raw.get("quiet_start", "22:00"),
                    "quiet_end": monitor_raw.get("quiet_end", "07:00"),
                    "allow_quiet_send": False,
                }
            )

    locations = []
    for index, item in enumerate(locations_raw or defaults["locations"], start=1):
        locations.append(
            {
                "id": str(item.get("id") or _slug("loc", item.get("name"), index)),
                "name": str(item.get("name") or item.get("city_label") or DEFAULT_CITY_LABEL),
                "latitude": float(item.get("latitude", DEFAULT_LATITUDE)),
                "longitude": float(item.get("longitude", DEFAULT_LONGITUDE)),
                "source": str(item.get("source", "manual")),
                "enabled": bool(item.get("enabled", True)),
                "default": bool(item.get("default", False)),
            }
        )
    if not any(item["default"] and item["enabled"] for item in locations):
        locations[0]["default"] = True

    targets = []
    seen_target_names: set[str] = set()
    for index, item in enumerate(targets_raw or defaults["wechat_targets"], start=1):
        name = str(item.get("name") or DEFAULT_CONTACT)
        if name in seen_target_names:
            continue
        seen_target_names.add(name)
        targets.append(
            {
                "id": str(item.get("id") or _slug("target", name, index)),
                "name": name,
                "enabled": bool(item.get("enabled", True)),
                "default": bool(item.get("default", False)),
            }
        )
    if not targets:
        targets = list(defaults["wechat_targets"])
    if not any(item["default"] and item["enabled"] for item in targets):
        targets[0]["default"] = True

    location_ids = {item["id"] for item in locations}
    target_ids = {item["id"] for item in targets}
    default_location_id = next(item["id"] for item in locations if item["default"])
    default_target_id = next(item["id"] for item in targets if item["default"])
    jobs = []
    for index, item in enumerate(jobs_raw or defaults["automation_jobs"], start=1):
        jobs.append(
            {
                "id": str(item.get("id") or _slug("job", index, index)),
                "location_id": str(item.get("location_id") if item.get("location_id") in location_ids else default_location_id),
                "wechat_target_id": str(item.get("wechat_target_id") if item.get("wechat_target_id") in target_ids else default_target_id),
                "enabled": bool(item.get("enabled", True)),
                "interval_minutes": max(1, int(item.get("interval_minutes", monitor_raw.get("interval_minutes", 120)))),
                "fixed_times": normalize_fixed_times(item.get("fixed_times", [])),
                "quiet_start": _time_value(item.get("quiet_start"), monitor_raw.get("quiet_start", "22:00")),
                "quiet_end": _time_value(item.get("quiet_end"), monitor_raw.get("quiet_end", "07:00")),
                "allow_quiet_send": bool(item.get("allow_quiet_send", False)),
            }
        )
    if not jobs:
        jobs = list(defaults["automation_jobs"])

    return {
        "app": app_raw,
        "locations": locations,
        "wechat_targets": targets,
        "automation_jobs": jobs,
        "providers": {
            **providers_raw,
            "comparison_models": list(
                providers_raw.get(
                    "comparison_models",
                    defaults["providers"]["comparison_models"],
                )
            ),
        },
        "monitor": {
            **monitor_raw,
            "interval_minutes": int(monitor_raw.get("interval_minutes", 120)),
            "future_hours": int(monitor_raw.get("future_hours", 6)),
            "daily_history_limit": int(monitor_raw.get("daily_history_limit", 5)),
        },
        "release": release_raw,
    }


def read_config_data(path: str | None, create_user_config: bool = False) -> dict[str, Any]:
    if path is None:
        config_path = ensure_user_config() if create_user_config else None
        if config_path is None:
            return _default_data()
    else:
        config_path = Path(path)
    return normalize_config_data(json.loads(config_path.read_text(encoding="utf-8")))


def write_config_data(path: str | None, data: dict[str, Any]) -> Path:
    config_path = config_write_path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_config_data(data)
    config_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path


def load_config(path: str | None, create_user_config: bool = False) -> AppConfig:
    raw = read_config_data(path, create_user_config=create_user_config)
    app_raw = raw["app"]
    providers_raw = raw["providers"]
    monitor_raw = raw["monitor"]
    release_raw = raw["release"]
    return AppConfig(
        app=AppSettings(
            name=str(app_raw.get("name", APP_NAME)),
            version=str(app_raw.get("version", APP_VERSION)),
            host=str(app_raw.get("host", "127.0.0.1")),
            port=int(app_raw.get("port", 8766)),
            open_browser_on_start=bool(app_raw.get("open_browser_on_start", True)),
        ),
        locations=[LocationConfig(**item) for item in raw["locations"]],
        wechat_targets=[WechatTargetConfig(**item) for item in raw["wechat_targets"]],
        automation_jobs=[AutomationJobConfig(**item) for item in raw["automation_jobs"]],
        providers=ProvidersConfig(
            timeout_seconds=float(providers_raw.get("timeout_seconds", 20.0)),
            language=str(providers_raw.get("language", "zh-cn")),
            primary=str(providers_raw.get("primary", "open_meteo_best_match")),
            comparison_models=list(providers_raw.get("comparison_models", [])),
            fallback_wttr=bool(providers_raw.get("fallback_wttr", True)),
        ),
        monitor=MonitorConfig(
            enabled=bool(monitor_raw.get("enabled", True)),
            backend=str(monitor_raw.get("backend", "pywinauto-session")),
            state_path=str(monitor_raw.get("state_path", "weather_poll_state.json")),
            future_hours=int(monitor_raw.get("future_hours", 6)),
            daily_history_limit=int(monitor_raw.get("daily_history_limit", 5)),
            interval_minutes=int(monitor_raw.get("interval_minutes", 120)),
            quiet_start=str(monitor_raw.get("quiet_start", "22:00")),
            quiet_end=str(monitor_raw.get("quiet_end", "07:00")),
        ),
        release=ReleaseConfig(
            package_name=str(release_raw.get("package_name", "KangkangWeather")),
            version=str(release_raw.get("version", APP_VERSION)),
            output_dir=str(release_raw.get("output_dir", "dist")),
        ),
    )


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "app": asdict(config.app),
        "locations": [asdict(item) for item in config.locations],
        "wechat_targets": [asdict(item) for item in config.wechat_targets],
        "automation_jobs": [asdict(item) for item in config.automation_jobs],
        "providers": asdict(config.providers),
        "monitor": asdict(config.monitor),
        "release": asdict(config.release),
    }


def dump_example(path: str) -> None:
    Path(path).write_text(
        json.dumps(_default_data(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
