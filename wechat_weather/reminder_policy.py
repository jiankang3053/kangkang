# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .config import ReminderPolicyConfig
from .weather import _weather_code_desc


RAIN_WORDS = ("雨", "雷阵雨", "暴雨", "小雨", "中雨", "大雨")
STORM_WORDS = ("雷", "暴雨", "大雨", "强降雨")


@dataclass(frozen=True)
class WeatherAbnormality:
    key: str
    title: str
    detail: str


@dataclass(frozen=True)
class ReminderDecision:
    should_send: bool
    action: str
    message_kind: str
    weather_status: str
    reason: str
    message: str = ""
    abnormalities: list[WeatherAbnormality] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["abnormalities"] = [asdict(item) for item in self.abnormalities]
        return data


def _today(snapshot: dict[str, Any]) -> dict[str, Any]:
    days = snapshot.get("days") or []
    if not days:
        return {}
    return days[0] if isinstance(days[0], dict) else {}


def _weather_text(day: dict[str, Any]) -> str:
    return str(day.get("weather") or _weather_code_desc(day.get("code")) or "")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(day: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _as_float(day.get(key))
        if value is not None:
            return value
    return None


def detect_abnormal_weather(
    snapshot: dict[str, Any],
    policy: ReminderPolicyConfig,
    previous_snapshot: dict[str, Any] | None = None,
) -> tuple[list[WeatherAbnormality], list[str]]:
    day = _today(snapshot)
    previous_day = _today(previous_snapshot or {})
    rules = policy.abnormal_rules
    thresholds = policy.thresholds
    abnormalities: list[WeatherAbnormality] = []
    missing: list[str] = []
    weather = _weather_text(day)
    rain_max = int(day.get("rain_max") or max(day.get("hourly_rain") or [0], default=0) or 0)

    if rules.rain and (rain_max >= thresholds.rain_probability_percent or any(word in weather for word in RAIN_WORDS)):
        abnormalities.append(
            WeatherAbnormality(
                key="rain",
                title="降雨提醒",
                detail="今天可能有雨，出门记得带伞。",
            )
        )

    if rules.storm and any(word in weather for word in STORM_WORDS):
        abnormalities.append(
            WeatherAbnormality(
                key="storm",
                title="强降雨提醒",
                detail="今天可能有较强降雨，出行注意安全。",
            )
        )

    temp_max = _as_float(day.get("temp_max"))
    temp_min = _as_float(day.get("temp_min"))
    if rules.high_temperature and temp_max is not None and temp_max >= thresholds.high_temperature_c:
        abnormalities.append(
            WeatherAbnormality(
                key="high_temperature",
                title="高温提醒",
                detail="今天气温偏高，注意防晒和补水。",
            )
        )
    if rules.low_temperature and temp_min is not None and temp_min <= thresholds.low_temperature_c:
        abnormalities.append(
            WeatherAbnormality(
                key="low_temperature",
                title="低温提醒",
                detail="今天气温偏低，出门注意保暖。",
            )
        )

    previous_max = _as_float(previous_day.get("temp_max"))
    if rules.temperature_drop:
        if temp_max is None or previous_max is None:
            missing.append("temperature_drop_baseline")
        elif previous_max - temp_max >= thresholds.temperature_drop_c:
            abnormalities.append(
                WeatherAbnormality(
                    key="temperature_drop",
                    title="降温提醒",
                    detail="今天降温明显，出门多穿一点。",
                )
            )

    wind_level = _first_number(day, ("wind_level", "wind_scale", "wind_speed_level"))
    wind_speed = _first_number(day, ("wind_speed_max", "windspeed_max", "wind_speed"))
    if rules.strong_wind:
        if wind_level is None and wind_speed is None:
            missing.append("wind")
        elif (wind_level is not None and wind_level >= thresholds.strong_wind_level) or (
            wind_speed is not None and wind_speed >= thresholds.strong_wind_level * 5
        ):
            abnormalities.append(
                WeatherAbnormality(
                    key="strong_wind",
                    title="大风提醒",
                    detail="今天风力较大，出行注意安全。",
                )
            )

    aqi = _first_number(day, ("aqi", "air_quality_index"))
    if rules.bad_air_quality:
        if aqi is None:
            missing.append("aqi")
        elif aqi >= thresholds.bad_aqi:
            abnormalities.append(
                WeatherAbnormality(
                    key="bad_air_quality",
                    title="空气质量提醒",
                    detail="今天空气质量一般，外出注意防护。",
                )
            )

    uv = _first_number(day, ("uv_index", "uv"))
    if rules.strong_uv:
        if uv is None:
            missing.append("uv")
        elif uv >= thresholds.strong_uv:
            abnormalities.append(
                WeatherAbnormality(
                    key="strong_uv",
                    title="紫外线提醒",
                    detail="今天紫外线较强，出门注意防晒。",
                )
            )

    unique: dict[str, WeatherAbnormality] = {}
    for item in abnormalities:
        unique.setdefault(item.key, item)
    return list(unique.values()), sorted(set(missing))


def _trim_short(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)].rstrip("，。； ") + "。"


def normal_short_message(max_chars: int) -> str:
    return _trim_short("今日天气平稳，适合正常出行。", max_chars)


def abnormal_short_message(abnormalities: list[WeatherAbnormality], max_chars: int) -> str:
    if not abnormalities:
        return normal_short_message(max_chars)
    priority = ["storm", "rain", "temperature_drop", "high_temperature", "low_temperature", "strong_wind", "bad_air_quality", "strong_uv"]
    by_key = {item.key: item for item in abnormalities}
    for key in priority:
        if key in by_key:
            return _trim_short(by_key[key].detail, max_chars)
    return _trim_short(abnormalities[0].detail, max_chars)


def choose_reminder_decision(
    snapshot: dict[str, Any],
    policy: ReminderPolicyConfig,
    *,
    full_message: str,
    previous_snapshot: dict[str, Any] | None = None,
) -> ReminderDecision:
    if not policy.enabled:
        return ReminderDecision(
            should_send=False,
            action="none",
            message_kind="skipped",
            weather_status="silent",
            reason="reminder_policy_disabled",
            message="提醒策略已关闭，本次不发送。",
        )

    abnormalities, missing = detect_abnormal_weather(snapshot, policy, previous_snapshot)
    is_abnormal = bool(abnormalities)
    weather_status = "abnormal" if is_abnormal else "normal"
    mode = policy.mode

    if mode == "silent":
        return ReminderDecision(False, "none", "skipped", weather_status, "silent_mode", "提醒已暂停，本次不发送。", abnormalities, missing)
    if mode == "always_full":
        return ReminderDecision(True, "full", "full", weather_status, "always_full", full_message, abnormalities, missing)
    if mode == "short_daily":
        message = abnormal_short_message(abnormalities, policy.short_message_max_chars) if is_abnormal else normal_short_message(policy.short_message_max_chars)
        return ReminderDecision(True, "short", "short", weather_status, "short_daily", message, abnormalities, missing)

    if is_abnormal:
        action = policy.abnormal_weather_action
        if mode == "abnormal_only" or mode == "smart":
            if action == "short":
                return ReminderDecision(True, "short", "short", weather_status, "abnormal_short", abnormal_short_message(abnormalities, policy.short_message_max_chars), abnormalities, missing)
            if action == "urgent":
                urgent = "【重要天气提醒】\n" + abnormal_short_message(abnormalities, 60) + "\n\n" + full_message
                return ReminderDecision(True, "urgent", "urgent", weather_status, "abnormal_urgent", urgent, abnormalities, missing)
            return ReminderDecision(True, "full", "full", weather_status, "abnormal_full", full_message, abnormalities, missing)

    if mode == "abnormal_only":
        return ReminderDecision(False, "none", "skipped", weather_status, "normal_weather_quiet_policy", "天气正常，根据你的提醒策略未发送。", abnormalities, missing)

    action = policy.normal_weather_action
    if action == "none":
        return ReminderDecision(False, "none", "skipped", weather_status, "normal_weather_quiet_policy", "天气正常，根据你的提醒策略未发送。", abnormalities, missing)
    if action == "full":
        return ReminderDecision(True, "full", "full", weather_status, "normal_full", full_message, abnormalities, missing)
    return ReminderDecision(True, "short", "short", weather_status, "normal_short", normal_short_message(policy.short_message_max_chars), abnormalities, missing)
