# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any

from .regions import (
    DEFAULT_ADDRESS_PATH as REGION_DEFAULT_ADDRESS_PATH,
    DEFAULT_REGION_CODE as REGION_DEFAULT_REGION_CODE,
    find_region_by_name,
)
from .weather import WeatherConfig


APP_NAME = "KangkangWeather"
APP_VERSION = "3.6.0"
CONFIG_VERSION = 3
DEFAULT_CONTACT = "湘楠"
DEFAULT_CITY_LABEL = "嘉鱼县"
DEFAULT_LATITUDE = 29.9724209
DEFAULT_LONGITUDE = 113.9335326
DEFAULT_REGION_CODE = REGION_DEFAULT_REGION_CODE
DEFAULT_ADDRESS_PATH = REGION_DEFAULT_ADDRESS_PATH
DEFAULT_LOCATION_ID = "jiayu"
DEFAULT_TARGET_ID = "xiangnan"
DEFAULT_JOB_ID = "default"
DEFAULT_ACTIVE_WINDOWS = ["07:00-22:00"]
DEFAULT_WECHAT_SEND_STRATEGY = "enter_first"
DEFAULT_ALLOW_SEND_BUTTON_COORDINATE_FALLBACK = False
DEFAULT_DAILY_STYLE = "segmented_brief"
DEFAULT_DAILY_PREFIX = ""


@dataclass(frozen=True)
class AppSettings:
    name: str = APP_NAME
    version: str = APP_VERSION
    host: str = "127.0.0.1"
    port: int = 8766
    open_browser_on_start: bool = True
    setup_complete: bool = False


@dataclass(frozen=True)
class LocationConfig:
    id: str = DEFAULT_LOCATION_ID
    name: str = DEFAULT_CITY_LABEL
    latitude: float = DEFAULT_LATITUDE
    longitude: float = DEFAULT_LONGITUDE
    region_code: str = DEFAULT_REGION_CODE
    address_path: list[str] = field(default_factory=lambda: list(DEFAULT_ADDRESS_PATH))
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
    type: str = "friend"
    enabled: bool = True
    default: bool = True
    remark: str = ""
    send_mode: str = "normal"
    send_interval_seconds: int = 3
    last_send_at: str | None = None
    last_send_status: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None


@dataclass(frozen=True)
class AlertOptionsConfig:
    rain_threshold_percent: int = 50
    rain_jump_percent: int = 30
    temp_change_celsius: float = 3.0
    weather_upgrade_enabled: bool = True
    future_rain_upgrade_enabled: bool = True


@dataclass(frozen=True)
class AutomationJobConfig:
    id: str = DEFAULT_JOB_ID
    location_id: str = DEFAULT_LOCATION_ID
    wechat_target_id: str = DEFAULT_TARGET_ID
    enabled: bool = True
    interval_minutes: int = 120
    fixed_times: list[str] = field(default_factory=list)
    active_windows: list[str] = field(default_factory=lambda: list(DEFAULT_ACTIVE_WINDOWS))
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"
    allow_quiet_send: bool = False
    alert_options: AlertOptionsConfig = field(default_factory=AlertOptionsConfig)


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
    timeout_seconds: float = 8.0
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
    wechat_send_strategy: str = DEFAULT_WECHAT_SEND_STRATEGY
    allow_send_button_coordinate_fallback: bool = DEFAULT_ALLOW_SEND_BUTTON_COORDINATE_FALLBACK
    state_path: str = "weather_poll_state.json"
    future_hours: int = 6
    daily_history_limit: int = 5
    fixed_send_grace_minutes: int = 180
    require_readiness_for_auto_send: bool = True
    interval_minutes: int = 120
    quiet_start: str = "22:00"
    quiet_end: str = "07:00"


@dataclass(frozen=True)
class ReleaseConfig:
    package_name: str = "KangkangWeather"
    version: str = APP_VERSION
    output_dir: str = "dist"


@dataclass(frozen=True)
class MessageConfig:
    daily_style: str = DEFAULT_DAILY_STYLE
    daily_prefix: str = DEFAULT_DAILY_PREFIX


@dataclass(frozen=True)
class ReminderAbnormalRulesConfig:
    rain: bool = True
    storm: bool = True
    temperature_drop: bool = True
    high_temperature: bool = True
    low_temperature: bool = True
    strong_wind: bool = True
    bad_air_quality: bool = True
    strong_uv: bool = True


@dataclass(frozen=True)
class ReminderThresholdsConfig:
    high_temperature_c: float = 35.0
    low_temperature_c: float = 5.0
    temperature_drop_c: float = 6.0
    strong_wind_level: float = 5.0
    bad_aqi: int = 100
    strong_uv: float = 6.0
    rain_probability_percent: int = 50


@dataclass(frozen=True)
class ReminderPolicyConfig:
    enabled: bool = True
    mode: str = "smart"
    normal_weather_action: str = "full"
    abnormal_weather_action: str = "full"
    short_message_max_chars: int = 30
    record_skipped_history: bool = True
    abnormal_rules: ReminderAbnormalRulesConfig = field(default_factory=ReminderAbnormalRulesConfig)
    thresholds: ReminderThresholdsConfig = field(default_factory=ReminderThresholdsConfig)


@dataclass(frozen=True)
class StartupConfig:
    enabled: bool = False


@dataclass(frozen=True)
class TrayConfig:
    enabled: bool = True
    minimize_to_tray: bool = True
    close_to_tray: bool = True
    show_tray_notifications: bool = True


@dataclass(frozen=True)
class DoNotDisturbConfig:
    enabled: bool = True
    detect_fullscreen: bool = True
    detect_game_process: bool = True
    detect_foreground_busy_app: bool = True
    busy_action: str = "delay"
    delay_minutes: int = 10
    max_delay_minutes: int = 60
    skip_if_still_busy: bool = True
    process_blocklist: list[str] = field(
        default_factory=lambda: [
            "steam.exe",
            "steamwebhelper.exe",
            "wegame.exe",
            "LeagueClient.exe",
            "League of Legends.exe",
            "cs2.exe",
            "valorant.exe",
            "GenshinImpact.exe",
            "YuanShen.exe",
            "PotPlayerMini64.exe",
            "PotPlayerMini.exe",
            "vlc.exe",
            "obs64.exe",
            "POWERPNT.EXE",
        ]
    )
    window_title_keywords: list[str] = field(
        default_factory=lambda: ["Presentation", "Slide Show", "全屏", "演示"]
    )


@dataclass(frozen=True)
class AppConfig:
    config_version: int = CONFIG_VERSION
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
    message: MessageConfig = MessageConfig()
    reminder_policy: ReminderPolicyConfig = ReminderPolicyConfig()
    startup: StartupConfig = StartupConfig()
    tray: TrayConfig = TrayConfig()
    do_not_disturb: DoNotDisturbConfig = DoNotDisturbConfig()
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


def _region_fields_for_location(item: dict[str, Any]) -> dict[str, Any]:
    region_code = str(item.get("region_code") or "").strip()
    address_path = item.get("address_path")
    if isinstance(address_path, list):
        path = [str(value).strip() for value in address_path if str(value).strip()]
    else:
        path = []
    if not region_code:
        match = find_region_by_name(item.get("name") or item.get("city_label"))
        if match:
            region_code = str(match.get("code") or "")
            path = list(match.get("address_path") or path)
    if not region_code and str(item.get("name") or item.get("city_label") or "") == DEFAULT_CITY_LABEL:
        region_code = DEFAULT_REGION_CODE
        path = list(DEFAULT_ADDRESS_PATH)
    return {
        "region_code": region_code,
        "address_path": path,
    }


def _time_value(value: Any, default: str, *, allow_2400: bool = False) -> str:
    text = str(value or default).strip()
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        hour, minute = text.split(":", 1)
        hour_int = int(hour)
        minute_int = int(minute)
        if 0 <= minute_int < 60 and (
            0 <= hour_int < 24 or (allow_2400 and hour_int == 24 and minute_int == 0)
        ):
            return f"{hour_int:02d}:{minute_int:02d}"
    return default


def _time_minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def _format_minutes(value: int) -> str:
    if value >= 24 * 60:
        return "24:00"
    return f"{value // 60:02d}:{value % 60:02d}"


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


def normalize_active_windows(
    values: Any,
    default: list[str] | None = None,
    *,
    strict: bool = False,
) -> list[str]:
    if default is None:
        default = list(DEFAULT_ACTIVE_WINDOWS)
    if isinstance(values, str):
        raw_values = [item.strip() for item in values.replace("，", ",").split(",")]
    elif isinstance(values, list):
        raw_values = values
    elif values is None:
        raw_values = []
    else:
        raw_values = []

    segments: list[tuple[int, int]] = []
    invalid: list[str] = []
    for value in raw_values:
        text = str(value).strip()
        if not text:
            continue
        match = re.fullmatch(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
        if not match:
            invalid.append(text)
            continue
        start = _time_value(match.group(1), "", allow_2400=False)
        end = _time_value(match.group(2), "", allow_2400=True)
        if not start or not end:
            invalid.append(text)
            continue
        start_min = _time_minutes(start)
        end_min = _time_minutes(end)
        if start_min == end_min:
            invalid.append(text)
            continue
        if start_min < end_min:
            segments.append((start_min, end_min))
        else:
            segments.append((start_min, 24 * 60))
            if end_min > 0:
                segments.append((0, end_min))

    if invalid and strict:
        raise ValueError(f"时间段格式错误：{', '.join(invalid)}。请使用 HH:MM-HH:MM。")
    if not segments:
        if strict and raw_values:
            raise ValueError("没有可用的运行时间段。")
        return list(default)

    segments.sort()
    merged: list[tuple[int, int]] = []
    for start, end in segments:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return [f"{_format_minutes(start)}-{_format_minutes(end)}" for start, end in merged]


def active_windows_from_quiet(
    quiet_start: Any,
    quiet_end: Any,
    allow_quiet_send: bool = False,
) -> list[str]:
    if allow_quiet_send:
        return ["00:00-24:00"]
    start = _time_value(quiet_start, "22:00", allow_2400=False)
    end = _time_value(quiet_end, "07:00", allow_2400=False)
    start_min = _time_minutes(start)
    end_min = _time_minutes(end)
    if start_min == end_min:
        return ["00:00-24:00"]
    if start_min < end_min:
        raw = []
        if start_min > 0:
            raw.append(f"00:00-{start}")
        if end_min < 24 * 60:
            raw.append(f"{end}-24:00")
        return normalize_active_windows(raw or ["00:00-24:00"])
    return normalize_active_windows([f"{end}-{start}"])


def normalize_alert_options(values: Any) -> dict[str, Any]:
    defaults = asdict(AlertOptionsConfig())
    raw = values if isinstance(values, dict) else {}
    rain_threshold = int(raw.get("rain_threshold_percent", defaults["rain_threshold_percent"]))
    rain_jump = int(raw.get("rain_jump_percent", defaults["rain_jump_percent"]))
    temp_change = float(raw.get("temp_change_celsius", defaults["temp_change_celsius"]))
    return {
        "rain_threshold_percent": min(100, max(1, rain_threshold)),
        "rain_jump_percent": min(100, max(1, rain_jump)),
        "temp_change_celsius": max(0.1, temp_change),
        "weather_upgrade_enabled": bool(
            raw.get("weather_upgrade_enabled", defaults["weather_upgrade_enabled"])
        ),
        "future_rain_upgrade_enabled": bool(
            raw.get("future_rain_upgrade_enabled", defaults["future_rain_upgrade_enabled"])
        ),
    }


def normalize_reminder_policy(values: Any) -> dict[str, Any]:
    defaults = asdict(ReminderPolicyConfig())
    raw = values if isinstance(values, dict) else {}
    allowed_modes = {"always_full", "smart", "abnormal_only", "short_daily", "silent"}
    allowed_normal = {"none", "short", "full"}
    allowed_abnormal = {"short", "full", "urgent"}
    rules_raw = raw.get("abnormal_rules") if isinstance(raw.get("abnormal_rules"), dict) else {}
    thresholds_raw = raw.get("thresholds") if isinstance(raw.get("thresholds"), dict) else {}
    rules_default = defaults["abnormal_rules"]
    thresholds_default = defaults["thresholds"]
    mode = str(raw.get("mode") or defaults["mode"])
    normal_action = str(raw.get("normal_weather_action") or defaults["normal_weather_action"])
    abnormal_action = str(raw.get("abnormal_weather_action") or defaults["abnormal_weather_action"])
    thresholds = {
        "high_temperature_c": float(
            thresholds_raw.get("high_temperature_c", thresholds_default["high_temperature_c"])
        ),
        "low_temperature_c": float(
            thresholds_raw.get("low_temperature_c", thresholds_default["low_temperature_c"])
        ),
        "temperature_drop_c": float(
            thresholds_raw.get("temperature_drop_c", thresholds_default["temperature_drop_c"])
        ),
        "strong_wind_level": float(
            thresholds_raw.get("strong_wind_level", thresholds_default["strong_wind_level"])
        ),
        "bad_aqi": int(thresholds_raw.get("bad_aqi", thresholds_default["bad_aqi"])),
        "strong_uv": float(thresholds_raw.get("strong_uv", thresholds_default["strong_uv"])),
        "rain_probability_percent": min(
            100,
            max(
                0,
                int(
                    thresholds_raw.get(
                        "rain_probability_percent",
                        thresholds_default["rain_probability_percent"],
                    )
                ),
            ),
        ),
    }
    return {
        "enabled": bool(raw.get("enabled", defaults["enabled"])),
        "mode": mode if mode in allowed_modes else defaults["mode"],
        "normal_weather_action": (
            normal_action if normal_action in allowed_normal else defaults["normal_weather_action"]
        ),
        "abnormal_weather_action": (
            abnormal_action if abnormal_action in allowed_abnormal else defaults["abnormal_weather_action"]
        ),
        "short_message_max_chars": max(
            8,
            min(80, int(raw.get("short_message_max_chars", defaults["short_message_max_chars"]))),
        ),
        "record_skipped_history": bool(
            raw.get("record_skipped_history", defaults["record_skipped_history"])
        ),
        "abnormal_rules": {
            key: bool(rules_raw.get(key, value))
            for key, value in rules_default.items()
        },
        "thresholds": thresholds,
    }


def normalize_startup(values: Any) -> dict[str, Any]:
    raw = values if isinstance(values, dict) else {}
    return {"enabled": bool(raw.get("enabled", False))}


def normalize_tray(values: Any) -> dict[str, Any]:
    defaults = asdict(TrayConfig())
    raw = values if isinstance(values, dict) else {}
    return {
        "enabled": bool(raw.get("enabled", defaults["enabled"])),
        "minimize_to_tray": bool(raw.get("minimize_to_tray", defaults["minimize_to_tray"])),
        "close_to_tray": bool(raw.get("close_to_tray", defaults["close_to_tray"])),
        "show_tray_notifications": bool(
            raw.get("show_tray_notifications", defaults["show_tray_notifications"])
        ),
    }


def normalize_do_not_disturb(values: Any) -> dict[str, Any]:
    defaults = asdict(DoNotDisturbConfig())
    raw = values if isinstance(values, dict) else {}
    allowed_actions = {"delay", "skip", "tray_only", "force_send"}
    action = str(raw.get("busy_action") or defaults["busy_action"])
    delay_minutes = max(1, int(raw.get("delay_minutes", defaults["delay_minutes"])))
    max_delay_minutes = max(
        delay_minutes,
        int(raw.get("max_delay_minutes", defaults["max_delay_minutes"])),
    )
    return {
        "enabled": bool(raw.get("enabled", defaults["enabled"])),
        "detect_fullscreen": bool(raw.get("detect_fullscreen", defaults["detect_fullscreen"])),
        "detect_game_process": bool(
            raw.get("detect_game_process", defaults["detect_game_process"])
        ),
        "detect_foreground_busy_app": bool(
            raw.get("detect_foreground_busy_app", defaults["detect_foreground_busy_app"])
        ),
        "busy_action": action if action in allowed_actions else defaults["busy_action"],
        "delay_minutes": delay_minutes,
        "max_delay_minutes": max_delay_minutes,
        "skip_if_still_busy": bool(
            raw.get("skip_if_still_busy", defaults["skip_if_still_busy"])
        ),
        "process_blocklist": [
            str(item).strip()
            for item in (raw.get("process_blocklist") or defaults["process_blocklist"])
            if str(item).strip()
        ],
        "window_title_keywords": [
            str(item).strip()
            for item in (raw.get("window_title_keywords") or defaults["window_title_keywords"])
            if str(item).strip()
        ],
    }


def _default_data() -> dict[str, Any]:
    return {
        "config_version": CONFIG_VERSION,
        "app": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "host": "127.0.0.1",
            "port": 8766,
            "open_browser_on_start": True,
            "setup_complete": False,
        },
        "locations": [
            {
                "id": DEFAULT_LOCATION_ID,
                "name": DEFAULT_CITY_LABEL,
                "latitude": DEFAULT_LATITUDE,
                "longitude": DEFAULT_LONGITUDE,
                "region_code": DEFAULT_REGION_CODE,
                "address_path": list(DEFAULT_ADDRESS_PATH),
                "source": "default",
                "enabled": True,
                "default": True,
            }
        ],
        "wechat_targets": [
            {
                "id": DEFAULT_TARGET_ID,
                "name": DEFAULT_CONTACT,
                "type": "friend",
                "enabled": True,
                "default": True,
                "remark": "",
                "send_mode": "normal",
                "send_interval_seconds": 3,
                "last_send_at": None,
                "last_send_status": None,
                "last_error_code": None,
                "last_error_message": None,
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
                "active_windows": list(DEFAULT_ACTIVE_WINDOWS),
                "quiet_start": "22:00",
                "quiet_end": "07:00",
                "allow_quiet_send": False,
                "alert_options": asdict(AlertOptionsConfig()),
            }
        ],
        "providers": {
            "timeout_seconds": 8,
            "language": "zh-cn",
            "primary": "open_meteo_best_match",
            "comparison_models": ["gfs_seamless", "icon_seamless", "cma_grapes_global"],
            "fallback_wttr": True,
        },
        "monitor": {
            "enabled": True,
            "backend": "pywinauto-session",
            "wechat_send_strategy": DEFAULT_WECHAT_SEND_STRATEGY,
            "allow_send_button_coordinate_fallback": DEFAULT_ALLOW_SEND_BUTTON_COORDINATE_FALLBACK,
            "state_path": "weather_poll_state.json",
            "future_hours": 6,
            "daily_history_limit": 5,
            "fixed_send_grace_minutes": 180,
            "require_readiness_for_auto_send": True,
            "interval_minutes": 120,
            "quiet_start": "22:00",
            "quiet_end": "07:00",
        },
        "message": {
            "daily_style": DEFAULT_DAILY_STYLE,
            "daily_prefix": DEFAULT_DAILY_PREFIX,
        },
        "reminder_policy": normalize_reminder_policy({}),
        "startup": normalize_startup({}),
        "tray": normalize_tray({}),
        "do_not_disturb": normalize_do_not_disturb({}),
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
    message_raw = {**defaults["message"], **raw.get("message", {})}
    reminder_policy_raw = normalize_reminder_policy(raw.get("reminder_policy"))
    startup_raw = normalize_startup(raw.get("startup"))
    tray_raw = normalize_tray(raw.get("tray"))
    do_not_disturb_raw = normalize_do_not_disturb(raw.get("do_not_disturb"))
    release_raw = {**defaults["release"], **raw.get("release", {})}
    app_raw["version"] = APP_VERSION
    release_raw["version"] = APP_VERSION
    if "setup_complete" not in raw.get("app", {}):
        app_raw["setup_complete"] = bool(
            raw.get("locations") or raw.get("wechat_targets") or raw.get("recipients") or raw.get("contact")
        )

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
                    **_region_fields_for_location(
                        {
                            "name": item.get("city_label", DEFAULT_CITY_LABEL),
                            "region_code": item.get("region_code"),
                            "address_path": item.get("address_path"),
                        }
                    ),
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
                    "active_windows": active_windows_from_quiet(
                        monitor_raw.get("quiet_start", "22:00"),
                        monitor_raw.get("quiet_end", "07:00"),
                    ),
                    "alert_options": asdict(AlertOptionsConfig()),
                }
            )

    locations = []
    for index, item in enumerate(locations_raw or defaults["locations"], start=1):
        region_fields = _region_fields_for_location(item)
        locations.append(
            {
                "id": str(item.get("id") or _slug("loc", item.get("name"), index)),
                "name": str(item.get("name") or item.get("city_label") or DEFAULT_CITY_LABEL),
                "latitude": float(item.get("latitude", DEFAULT_LATITUDE)),
                "longitude": float(item.get("longitude", DEFAULT_LONGITUDE)),
                "region_code": region_fields["region_code"],
                "address_path": region_fields["address_path"],
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
                "type": str(item.get("type") or item.get("target_type") or "friend"),
                "enabled": bool(item.get("enabled", True)),
                "default": bool(item.get("default", False)),
                "remark": str(item.get("remark") or ""),
                "send_mode": str(item.get("send_mode") or "normal"),
                "send_interval_seconds": max(
                    0,
                    int(item.get("send_interval_seconds", 3) or 0),
                ),
                "last_send_at": item.get("last_send_at"),
                "last_send_status": item.get("last_send_status"),
                "last_error_code": item.get("last_error_code"),
                "last_error_message": item.get("last_error_message"),
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
        allow_quiet_send = bool(item.get("allow_quiet_send", False))
        quiet_start = _time_value(item.get("quiet_start"), monitor_raw.get("quiet_start", "22:00"))
        quiet_end = _time_value(item.get("quiet_end"), monitor_raw.get("quiet_end", "07:00"))
        active_windows = normalize_active_windows(
            item.get("active_windows"),
            default=active_windows_from_quiet(quiet_start, quiet_end, allow_quiet_send),
        )
        jobs.append(
            {
                "id": str(item.get("id") or _slug("job", index, index)),
                "location_id": str(item.get("location_id") if item.get("location_id") in location_ids else default_location_id),
                "wechat_target_id": str(item.get("wechat_target_id") if item.get("wechat_target_id") in target_ids else default_target_id),
                "enabled": bool(item.get("enabled", True)),
                "interval_minutes": max(1, int(item.get("interval_minutes", monitor_raw.get("interval_minutes", 120)))),
                "fixed_times": normalize_fixed_times(item.get("fixed_times", [])),
                "active_windows": active_windows,
                "quiet_start": quiet_start,
                "quiet_end": quiet_end,
                "allow_quiet_send": allow_quiet_send,
                "alert_options": normalize_alert_options(item.get("alert_options")),
            }
        )
    if not jobs:
        jobs = list(defaults["automation_jobs"])

    return {
        "config_version": CONFIG_VERSION,
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
            "wechat_send_strategy": str(
                monitor_raw.get("wechat_send_strategy", DEFAULT_WECHAT_SEND_STRATEGY)
            )
            or DEFAULT_WECHAT_SEND_STRATEGY,
            "allow_send_button_coordinate_fallback": bool(
                monitor_raw.get(
                    "allow_send_button_coordinate_fallback",
                    DEFAULT_ALLOW_SEND_BUTTON_COORDINATE_FALLBACK,
                )
            ),
            "interval_minutes": int(monitor_raw.get("interval_minutes", 120)),
            "future_hours": int(monitor_raw.get("future_hours", 6)),
            "daily_history_limit": int(monitor_raw.get("daily_history_limit", 5)),
        },
        "message": {
            "daily_style": str(message_raw.get("daily_style") or DEFAULT_DAILY_STYLE),
            "daily_prefix": str(message_raw.get("daily_prefix") or DEFAULT_DAILY_PREFIX).strip(),
        },
        "reminder_policy": reminder_policy_raw,
        "startup": startup_raw,
        "tray": tray_raw,
        "do_not_disturb": do_not_disturb_raw,
        "release": release_raw,
    }


def read_config_data(path: str | None, create_user_config: bool = False) -> dict[str, Any]:
    if path is None:
        config_path = ensure_user_config() if create_user_config else None
        if config_path is None:
            return _default_data()
    else:
        config_path = Path(path)
    try:
        return normalize_config_data(json.loads(config_path.read_text(encoding="utf-8-sig")))
    except json.JSONDecodeError:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = config_path.with_name(f"{config_path.stem}.corrupt.{stamp}{config_path.suffix}")
        try:
            backup.write_text(config_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        except Exception:
            pass
        backup_config = config_path.with_name(f"{config_path.stem}.backup{config_path.suffix}")
        if backup_config.exists():
            try:
                return normalize_config_data(json.loads(backup_config.read_text(encoding="utf-8-sig")))
            except Exception:
                pass
        return _default_data()


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
    message_raw = raw["message"]
    reminder_policy_raw = raw["reminder_policy"]
    startup_raw = raw["startup"]
    tray_raw = raw["tray"]
    do_not_disturb_raw = raw["do_not_disturb"]
    release_raw = raw["release"]
    return AppConfig(
        config_version=int(raw.get("config_version", CONFIG_VERSION)),
        app=AppSettings(
            name=str(app_raw.get("name", APP_NAME)),
            version=str(app_raw.get("version", APP_VERSION)),
            host=str(app_raw.get("host", "127.0.0.1")),
            port=int(app_raw.get("port", 8766)),
            open_browser_on_start=bool(app_raw.get("open_browser_on_start", True)),
            setup_complete=bool(app_raw.get("setup_complete", False)),
        ),
        locations=[LocationConfig(**item) for item in raw["locations"]],
        wechat_targets=[WechatTargetConfig(**item) for item in raw["wechat_targets"]],
        automation_jobs=[
            AutomationJobConfig(
                id=str(item.get("id", DEFAULT_JOB_ID)),
                location_id=str(item.get("location_id", DEFAULT_LOCATION_ID)),
                wechat_target_id=str(item.get("wechat_target_id", DEFAULT_TARGET_ID)),
                enabled=bool(item.get("enabled", True)),
                interval_minutes=int(item.get("interval_minutes", 120)),
                fixed_times=list(item.get("fixed_times", [])),
                active_windows=list(item.get("active_windows", DEFAULT_ACTIVE_WINDOWS)),
                quiet_start=str(item.get("quiet_start", "22:00")),
                quiet_end=str(item.get("quiet_end", "07:00")),
                allow_quiet_send=bool(item.get("allow_quiet_send", False)),
                alert_options=AlertOptionsConfig(**normalize_alert_options(item.get("alert_options"))),
            )
            for item in raw["automation_jobs"]
        ],
        providers=ProvidersConfig(
            timeout_seconds=float(providers_raw.get("timeout_seconds", 8.0)),
            language=str(providers_raw.get("language", "zh-cn")),
            primary=str(providers_raw.get("primary", "open_meteo_best_match")),
            comparison_models=list(providers_raw.get("comparison_models", [])),
            fallback_wttr=bool(providers_raw.get("fallback_wttr", True)),
        ),
        monitor=MonitorConfig(
            enabled=bool(monitor_raw.get("enabled", True)),
            backend=str(monitor_raw.get("backend", "pywinauto-session")),
            wechat_send_strategy=str(
                monitor_raw.get("wechat_send_strategy", DEFAULT_WECHAT_SEND_STRATEGY)
            )
            or DEFAULT_WECHAT_SEND_STRATEGY,
            allow_send_button_coordinate_fallback=bool(
                monitor_raw.get(
                    "allow_send_button_coordinate_fallback",
                    DEFAULT_ALLOW_SEND_BUTTON_COORDINATE_FALLBACK,
                )
            ),
            state_path=str(monitor_raw.get("state_path", "weather_poll_state.json")),
            future_hours=int(monitor_raw.get("future_hours", 6)),
            daily_history_limit=int(monitor_raw.get("daily_history_limit", 5)),
            fixed_send_grace_minutes=max(
                1,
                int(monitor_raw.get("fixed_send_grace_minutes", 180)),
            ),
            require_readiness_for_auto_send=bool(
                monitor_raw.get("require_readiness_for_auto_send", True)
            ),
            interval_minutes=int(monitor_raw.get("interval_minutes", 120)),
            quiet_start=str(monitor_raw.get("quiet_start", "22:00")),
            quiet_end=str(monitor_raw.get("quiet_end", "07:00")),
        ),
        message=MessageConfig(
            daily_style=str(message_raw.get("daily_style") or DEFAULT_DAILY_STYLE),
            daily_prefix=str(message_raw.get("daily_prefix") or DEFAULT_DAILY_PREFIX).strip(),
        ),
        reminder_policy=ReminderPolicyConfig(
            enabled=bool(reminder_policy_raw.get("enabled", True)),
            mode=str(reminder_policy_raw.get("mode", "smart")),
            normal_weather_action=str(reminder_policy_raw.get("normal_weather_action", "full")),
            abnormal_weather_action=str(reminder_policy_raw.get("abnormal_weather_action", "full")),
            short_message_max_chars=int(reminder_policy_raw.get("short_message_max_chars", 30)),
            record_skipped_history=bool(reminder_policy_raw.get("record_skipped_history", True)),
            abnormal_rules=ReminderAbnormalRulesConfig(
                **dict(reminder_policy_raw.get("abnormal_rules") or {})
            ),
            thresholds=ReminderThresholdsConfig(
                **dict(reminder_policy_raw.get("thresholds") or {})
            ),
        ),
        startup=StartupConfig(enabled=bool(startup_raw.get("enabled", False))),
        tray=TrayConfig(
            enabled=bool(tray_raw.get("enabled", True)),
            minimize_to_tray=bool(tray_raw.get("minimize_to_tray", True)),
            close_to_tray=bool(tray_raw.get("close_to_tray", True)),
            show_tray_notifications=bool(tray_raw.get("show_tray_notifications", True)),
        ),
        do_not_disturb=DoNotDisturbConfig(
            enabled=bool(do_not_disturb_raw.get("enabled", True)),
            detect_fullscreen=bool(do_not_disturb_raw.get("detect_fullscreen", True)),
            detect_game_process=bool(do_not_disturb_raw.get("detect_game_process", True)),
            detect_foreground_busy_app=bool(
                do_not_disturb_raw.get("detect_foreground_busy_app", True)
            ),
            busy_action=str(do_not_disturb_raw.get("busy_action", "delay")),
            delay_minutes=int(do_not_disturb_raw.get("delay_minutes", 10)),
            max_delay_minutes=int(do_not_disturb_raw.get("max_delay_minutes", 60)),
            skip_if_still_busy=bool(do_not_disturb_raw.get("skip_if_still_busy", True)),
            process_blocklist=list(do_not_disturb_raw.get("process_blocklist", [])),
            window_title_keywords=list(do_not_disturb_raw.get("window_title_keywords", [])),
        ),
        release=ReleaseConfig(
            package_name=str(release_raw.get("package_name", "KangkangWeather")),
            version=str(release_raw.get("version", APP_VERSION)),
            output_dir=str(release_raw.get("output_dir", "dist")),
        ),
    )


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "config_version": config.config_version,
        "app": asdict(config.app),
        "locations": [asdict(item) for item in config.locations],
        "wechat_targets": [asdict(item) for item in config.wechat_targets],
        "automation_jobs": [asdict(item) for item in config.automation_jobs],
        "providers": asdict(config.providers),
        "monitor": asdict(config.monitor),
        "message": asdict(config.message),
        "reminder_policy": asdict(config.reminder_policy),
        "startup": asdict(config.startup),
        "tray": asdict(config.tray),
        "do_not_disturb": asdict(config.do_not_disturb),
        "release": asdict(config.release),
    }


def dump_example(path: str) -> None:
    Path(path).write_text(
        json.dumps(_default_data(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
