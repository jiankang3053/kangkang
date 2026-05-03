# -*- coding: utf-8 -*-
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


@dataclass(frozen=True)
class WeatherConfig:
    city_query: str = "Jiayu County"
    city_label: str = "嘉鱼县"
    timeout_seconds: float = 8.0
    language: str = "zh-cn"
    latitude: float = 29.9724209
    longitude: float = 113.9335326


@dataclass(frozen=True)
class WeatherHour:
    time: str
    date: str
    hour: int
    code: int | float | None
    rain: int | float | None
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WeatherDay:
    date: str
    code: int | float | None
    temp_min: int | float
    temp_max: int | float
    rain_max: int | float
    hourly_codes: list[int | float | None]
    hourly_rain: list[int | float | None]
    hourly_rows: list[dict[str, Any]]
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WeatherSnapshot:
    city_label: str
    created_at: str
    source: str
    sources: list[str]
    days: list[dict[str, Any]]
    provider_failures: list[str] = field(default_factory=list)
    source_disagreement: bool = False
    source_count: int = 1
    cached: bool = False
    stale: bool = False
    elapsed_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


WEATHER_CODE_TEXT = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "浓毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷阵雨",
    96: "雷阵雨伴小冰雹",
    99: "雷阵雨伴大冰雹",
}


SEVERITY_BY_CODE = {
    0: 0,
    1: 1,
    2: 1,
    3: 1,
    45: 1,
    48: 1,
    51: 2,
    53: 2,
    55: 2,
    56: 2,
    57: 2,
    61: 3,
    66: 3,
    80: 3,
    63: 4,
    67: 4,
    71: 4,
    73: 4,
    75: 4,
    81: 4,
    65: 5,
    82: 5,
    85: 4,
    86: 5,
    95: 5,
    96: 6,
    99: 6,
}


def _weather_code_desc(code: int | float | None) -> str:
    try:
        return WEATHER_CODE_TEXT[int(code)]
    except (KeyError, TypeError, ValueError):
        return "未知"


def weather_code_severity(code: int | float | None) -> int:
    try:
        return SEVERITY_BY_CODE.get(int(code), 0)
    except (TypeError, ValueError):
        return 0


def _riskier_code(codes: list[int | float | None]) -> int | float | None:
    return max(codes, key=weather_code_severity, default=None)


def _rain_level(probability: int | float | None) -> str:
    try:
        value = int(probability)
    except (TypeError, ValueError):
        return "未知"
    if value <= 30:
        return "低"
    if value <= 60:
        return "中"
    return "高"


def _format_temp(value: int | float) -> int:
    return int(round(float(value)))


def fetch_open_meteo_weather(
    config: WeatherConfig,
    model: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "latitude": config.latitude,
        "longitude": config.longitude,
        "timezone": "Asia/Shanghai",
        "forecast_days": 4,
        "hourly": "weather_code,precipitation_probability",
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max"
        ),
    }
    if model and model != "best_match":
        params["models"] = model
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params=params,
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def weather_cache_path() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / "KangkangWeather" / "weather_cache.json"
    return Path.home() / ".KangkangWeather" / "weather_cache.json"


def weather_history_path() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / "KangkangWeather" / "weather_fetch_history.json"
    return Path.home() / ".KangkangWeather" / "weather_fetch_history.json"


def _append_weather_history(record: dict[str, Any], limit: int = 200) -> None:
    path = weather_history_path()
    try:
        if path.exists():
            current = json.loads(path.read_text(encoding="utf-8"))
            history = current if isinstance(current, list) else []
        else:
            history = []
        history.append(record)
        history = history[-limit:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(history, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        # Weather history must never break preview, sending, or monitoring.
        return


def read_weather_history(limit: int = 50) -> list[dict[str, Any]]:
    path = weather_history_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        history = data if isinstance(data, list) else []
    except Exception:
        return []
    return list(reversed(history[-max(1, int(limit)) :]))


def _history_record(
    config: WeatherConfig,
    *,
    started: datetime,
    snapshot: dict[str, Any] | None = None,
    ok: bool,
    error: str = "",
) -> dict[str, Any]:
    elapsed_ms = int((datetime.now() - started).total_seconds() * 1000)
    snapshot = snapshot or {}
    cached = bool(snapshot.get("cached"))
    return {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "address": config.city_label,
        "source": snapshot.get("source"),
        "sources": snapshot.get("sources", []),
        "source_count": snapshot.get("source_count", len(snapshot.get("sources", [])) if snapshot else 0),
        "failures": snapshot.get("provider_failures", []),
        "cached": cached,
        "stale": bool(snapshot.get("stale")),
        "source_disagreement": bool(snapshot.get("source_disagreement")),
        "elapsed_ms": snapshot.get("elapsed_ms") or elapsed_ms,
        "status": "ok" if ok and not cached else ("cache" if ok else "failed"),
        "error": error,
    }


def _cache_key(config: WeatherConfig) -> str:
    return f"{config.city_label}|{round(float(config.latitude), 5)}|{round(float(config.longitude), 5)}"


def _read_weather_cache() -> dict[str, Any]:
    path = weather_cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_weather_cache(data: dict[str, Any]) -> None:
    path = weather_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_cached_snapshot(config: WeatherConfig, max_age_hours: int = 12) -> dict[str, Any] | None:
    item = _read_weather_cache().get(_cache_key(config))
    if not isinstance(item, dict):
        return None
    snapshot = item.get("snapshot")
    cached_at = item.get("cached_at")
    if not isinstance(snapshot, dict) or not cached_at:
        return None
    try:
        age = datetime.now() - datetime.fromisoformat(str(cached_at))
    except ValueError:
        return None
    if age > timedelta(hours=max_age_hours):
        return None
    result = dict(snapshot)
    result["cached"] = True
    result["stale"] = True
    result["cache_age_minutes"] = int(age.total_seconds() // 60)
    return result


def _save_cached_snapshot(config: WeatherConfig, snapshot: dict[str, Any]) -> None:
    if snapshot.get("stale"):
        return
    data = _read_weather_cache()
    clean = dict(snapshot)
    clean["cached"] = False
    clean["stale"] = False
    data[_cache_key(config)] = {
        "cached_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot": clean,
    }
    _write_weather_cache(data)


def _snapshot_from_open_meteo_data(
    config: WeatherConfig,
    data: dict[str, Any],
    source_name: str,
) -> dict[str, Any]:
    daily = data["daily"]
    hourly = data["hourly"]
    hourly_rows = [
        asdict(
            WeatherHour(
                time=value,
                date=value.split("T", 1)[0],
                hour=int(value.split("T", 1)[1].split(":", 1)[0]),
                code=hourly["weather_code"][index],
                rain=hourly["precipitation_probability"][index],
                sources=[source_name],
            )
        )
        for index, value in enumerate(hourly["time"])
    ]

    days: list[dict[str, Any]] = []
    for index, date in enumerate(daily["time"]):
        rows = [row for row in hourly_rows if row["date"] == date]
        rows.sort(key=lambda row: row["hour"])
        days.append(
            asdict(
                WeatherDay(
                    date=date,
                    code=daily["weather_code"][index],
                    temp_max=daily["temperature_2m_max"][index],
                    temp_min=daily["temperature_2m_min"][index],
                    rain_max=daily["precipitation_probability_max"][index],
                    hourly_codes=[row["code"] for row in rows],
                    hourly_rain=[row["rain"] for row in rows],
                    hourly_rows=rows,
                    sources=[source_name],
                )
            )
        )

    return WeatherSnapshot(
        city_label=config.city_label,
        created_at=datetime.now().isoformat(timespec="seconds"),
        source=source_name,
        sources=[source_name],
        provider_failures=[],
        source_disagreement=False,
        source_count=1,
        days=days,
    ).to_dict()


def _merge_hourly_rows(rows_by_source: list[dict[str, Any]]) -> dict[str, Any]:
    first = rows_by_source[0]
    rain_values = [int(row.get("rain") or 0) for row in rows_by_source]
    code_values = [row.get("code") for row in rows_by_source]
    return {
        "time": first["time"],
        "date": first["date"],
        "hour": first["hour"],
        "code": _riskier_code(code_values),
        "rain": max(rain_values),
        "source_rain": rain_values,
        "source_codes": code_values,
        "sources": [source for row in rows_by_source for source in row.get("sources", [])],
    }


def _merge_days(days_by_source: list[dict[str, Any]]) -> dict[str, Any]:
    first = days_by_source[0]
    by_time: dict[str, list[dict[str, Any]]] = {}
    for day in days_by_source:
        for row in day.get("hourly_rows", []):
            by_time.setdefault(str(row["time"]), []).append(row)
    rows = [_merge_hourly_rows(items) for _, items in sorted(by_time.items())]
    rain_values = [int(day.get("rain_max") or 0) for day in days_by_source]
    code_values = [day.get("code") for day in days_by_source]
    temp_min_values = [float(day.get("temp_min")) for day in days_by_source]
    temp_max_values = [float(day.get("temp_max")) for day in days_by_source]
    return {
        "date": first["date"],
        "code": _riskier_code(code_values),
        "temp_min": min(temp_min_values),
        "temp_max": max(temp_max_values),
        "rain_max": max(rain_values),
        "hourly_codes": [row["code"] for row in rows],
        "hourly_rain": [row["rain"] for row in rows],
        "hourly_rows": rows,
        "source_rain_max": rain_values,
        "source_codes": code_values,
        "sources": [source for day in days_by_source for source in day.get("sources", [])],
    }


def _has_disagreement(snapshots: list[dict[str, Any]]) -> bool:
    if len(snapshots) < 2:
        return False
    days_by_date: dict[str, list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        for day in snapshot.get("days", []):
            days_by_date.setdefault(str(day["date"]), []).append(day)
    for days in days_by_date.values():
        rain_values = [int(day.get("rain_max") or 0) for day in days]
        severities = [weather_code_severity(day.get("code")) for day in days]
        if max(rain_values, default=0) - min(rain_values, default=0) >= 30:
            return True
        if max(severities, default=0) - min(severities, default=0) >= 2:
            return True
    return False


def merge_snapshots(
    config: WeatherConfig,
    snapshots: list[dict[str, Any]],
    failures: list[str] | None = None,
) -> dict[str, Any]:
    if not snapshots:
        raise ValueError("没有可用天气数据源。")
    days_by_date: dict[str, list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        for day in snapshot.get("days", []):
            days_by_date.setdefault(str(day["date"]), []).append(day)

    merged_days = [_merge_days(items) for _, items in sorted(days_by_date.items())]
    sources = [source for snapshot in snapshots for source in snapshot.get("sources", [])]
    return {
        "city_label": config.city_label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "conservative_merge" if len(snapshots) > 1 else snapshots[0].get("source"),
        "sources": sources,
        "source_count": len(set(sources)),
        "provider_failures": failures or [],
        "source_disagreement": _has_disagreement(snapshots),
        "cached": False,
        "stale": False,
        "elapsed_ms": None,
        "days": merged_days,
    }


def build_weather_snapshot(
    config: WeatherConfig,
    comparison_models: list[str] | None = None,
    fallback_wttr: bool = True,
) -> dict[str, Any]:
    started = datetime.now()
    models = ["best_match", *(comparison_models or [])]
    snapshots: list[dict[str, Any]] = []
    failures: list[str] = []
    seen: set[str] = set()
    unique_models: list[str] = []

    for model in models:
        if model in seen:
            continue
        seen.add(model)
        unique_models.append(model)

    executor = ThreadPoolExecutor(max_workers=min(len(unique_models), 4) or 1)
    futures = {
        executor.submit(fetch_open_meteo_weather, config, model): model
        for model in unique_models
    }
    try:
        for future in as_completed(futures, timeout=15):
            model = futures[future]
            source_name = f"open_meteo:{model}"
            try:
                data = future.result()
                snapshots.append(_snapshot_from_open_meteo_data(config, data, source_name))
            except Exception as exc:
                failures.append(f"{source_name}: {exc}")
    except FuturesTimeoutError:
        for future, model in futures.items():
            if not future.done():
                failures.append(f"open_meteo:{model}: timed out")
                future.cancel()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if not snapshots and fallback_wttr:
        try:
            snapshots.append(_snapshot_from_wttr_data(config, fetch_wttr_weather(config)))
        except Exception as exc:
            failures.append(f"wttr.in: {exc}")

    if snapshots:
        snapshot = merge_snapshots(config, snapshots, failures=failures)
        snapshot["elapsed_ms"] = int((datetime.now() - started).total_seconds() * 1000)
        _save_cached_snapshot(config, snapshot)
        _append_weather_history(_history_record(config, started=started, snapshot=snapshot, ok=True))
        return snapshot

    cached = _load_cached_snapshot(config)
    if cached:
        cached["provider_failures"] = failures
        cached["elapsed_ms"] = int((datetime.now() - started).total_seconds() * 1000)
        _append_weather_history(_history_record(config, started=started, snapshot=cached, ok=True))
        return cached

    error = "没有可用天气数据源：" + "；".join(failures)
    _append_weather_history(
        _history_record(
            config,
            started=started,
            snapshot={"provider_failures": failures, "elapsed_ms": int((datetime.now() - started).total_seconds() * 1000)},
            ok=False,
            error=error,
        )
    )
    raise ValueError(error)


def weather_status_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": snapshot.get("source"),
        "source_count": snapshot.get("source_count", len(snapshot.get("sources", []))),
        "sources": snapshot.get("sources", []),
        "failures": snapshot.get("provider_failures", []),
        "source_disagreement": bool(snapshot.get("source_disagreement")),
        "cached": bool(snapshot.get("cached")),
        "stale": bool(snapshot.get("stale")),
        "cache_age_minutes": snapshot.get("cache_age_minutes"),
        "elapsed_ms": snapshot.get("elapsed_ms"),
    }


def _period_forecast(day: dict[str, Any], start_hour: int, end_hour: int) -> tuple[str, int]:
    rows = [
        row
        for row in day["hourly_rows"]
        if start_hour <= row["hour"] < end_hour
    ]
    if not rows:
        return "未知", 0
    max_rain = max(int(row["rain"] or 0) for row in rows)
    wettest = max(rows, key=lambda row: int(row["rain"] or 0))
    return _weather_code_desc(wettest["code"]), max_rain


def _open_meteo_advice(today: dict[str, Any]) -> str:
    max_rain = max(today["hourly_rain"], default=0)
    min_temp = int(round(today["temp_min"]))
    max_temp = int(round(today["temp_max"]))
    sunny_codes = {0, 1}
    daytime_codes = today["hourly_codes"][3:6]
    if max_rain >= 50:
        return "携带雨具"
    if max_temp >= 28 or any(code in sunny_codes for code in daytime_codes):
        return "注意防晒"
    if min_temp <= 14 or (max_temp - min_temp) >= 8:
        return "早晚添衣"
    return "早晚添衣"


def build_weather_message_from_snapshot(
    snapshot: dict[str, Any],
    daily_prefix: str = "",
    daily_style: str = "segmented_brief",
) -> str:
    days = snapshot.get("days", [])
    if len(days) < 3:
        raise ValueError("天气快照的预报天数不足 3 天。")
    today, tomorrow, after_tomorrow = days[:3]
    periods = [
        (0, 3),
        (3, 6),
        (6, 9),
        (9, 12),
        (12, 15),
        (15, 18),
        (18, 21),
        (21, 24),
    ]
    period_lines = []
    for index, (start, end) in enumerate(periods):
        weather, rain = _period_forecast(today, start, end)
        period_lines.append(
            f"{start:02d}:00-{end:02d}:00 {weather}，降雨概率{rain}%"
        )

    def day_line(label: str, day: dict[str, Any]) -> str:
        return (
            f"{label}：{_weather_code_desc(day['code'])}，"
            f"{_format_temp(day['temp_min'])}-{_format_temp(day['temp_max'])}℃，"
            f"降雨可能{_rain_level(day['rain_max'])}。"
        )

    source_note = ""
    if snapshot.get("source_disagreement"):
        source_note = "\n\n提示：多源预报存在分歧，已按偏高风险提醒。"
    if snapshot.get("stale"):
        source_note += "\n\n提示：天气接口暂时不可用，已使用最近一次成功预报。"

    lines = [
        f"【{snapshot.get('city_label') or '天气'}天气提醒】",
        "",
        "今日分时段：",
        *period_lines,
        "",
        f"今日气温：{_format_temp(today['temp_min'])}-{_format_temp(today['temp_max'])}℃。",
        f"建议：{_open_meteo_advice(today)}。",
        "",
        day_line("明天", tomorrow),
        day_line("后天", after_tomorrow),
    ]
    prefix = str(daily_prefix or "").strip()
    if prefix:
        lines = [prefix, "", *lines]
    return "\n".join(lines) + source_note


def build_weather_message(
    config: WeatherConfig,
    comparison_models: list[str] | None = None,
    daily_prefix: str = "",
    daily_style: str = "segmented_brief",
) -> str:
    try:
        snapshot = build_weather_snapshot(config, comparison_models=comparison_models)
        return build_weather_message_from_snapshot(
            snapshot,
            daily_prefix=daily_prefix,
            daily_style=daily_style,
        )
    except Exception as exc:
        return f"天气加载失败：{exc}"


def _weather_desc(block: dict[str, Any]) -> str:
    desc = block.get("weatherDesc") or []
    if desc and isinstance(desc, list):
        value = desc[0].get("value")
        if value:
            return str(value)
    for key, value in block.items():
        if key.startswith("lang_") and isinstance(value, list) and value:
            translated = value[0].get("value")
            if translated:
                return str(translated)
    return "未知"


def _max_rain(day: dict[str, Any]) -> int:
    values: list[int] = []
    for hour in day.get("hourly", []):
        try:
            values.append(int(hour.get("chanceofrain", "0")))
        except (TypeError, ValueError):
            values.append(0)
    return max(values, default=0)


def _daytime_desc(day: dict[str, Any]) -> str:
    hourly = day.get("hourly", [])
    if not hourly:
        return "未知"
    for hour in hourly:
        if hour.get("time") == "1200":
            return _weather_desc(hour)
    return _weather_desc(hourly[len(hourly) // 2])


def _fallback_advice(today: dict[str, Any], current: dict[str, Any]) -> str:
    rain = _max_rain(today)
    temp = int(current.get("temp_C", "0"))
    if rain >= 60:
        return "降雨概率较高，出门带伞。"
    if temp >= 30:
        return "气温偏高，注意防晒和补水。"
    if temp <= 8:
        return "体感偏冷，注意添衣。"
    return "出门前再看一眼体感和降雨概率。"


def fetch_wttr_weather(config: WeatherConfig) -> dict[str, Any]:
    url = f"https://wttr.in/{quote(config.city_query)}"
    params = {"format": "j1", "lang": config.language}
    response = requests.get(url, params=params, timeout=config.timeout_seconds)
    response.raise_for_status()
    return response.json()


def _wttr_to_wmo_code(value: Any) -> int:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return 3
    if code == 113:
        return 0
    if code == 116:
        return 1
    if code in {119, 122}:
        return 3
    if code in {143, 248, 260}:
        return 45
    if code in {176, 263, 266, 293, 296, 353}:
        return 61
    if code in {299, 302, 305, 308, 356, 359}:
        return 65
    if code in {179, 182, 185, 281, 284, 311, 314, 317, 350, 362, 365, 374, 377}:
        return 67
    if code in {200, 386, 389, 392, 395}:
        return 95
    if code in {227, 230, 320, 323, 326, 329, 332, 335, 338, 368, 371}:
        return 73
    return 3


def _snapshot_from_wttr_data(
    config: WeatherConfig,
    data: dict[str, Any],
) -> dict[str, Any]:
    source_name = "wttr.in"
    days: list[dict[str, Any]] = []
    for day in data.get("weather", []):
        date = str(day.get("date"))
        rows = []
        for hour in day.get("hourly", []):
            raw_time = str(hour.get("time", "0")).zfill(4)
            hour_value = int(raw_time[:-2] or "0")
            code = _wttr_to_wmo_code(hour.get("weatherCode"))
            rain = int(hour.get("chanceofrain") or 0)
            rows.append(
                asdict(
                    WeatherHour(
                        time=f"{date}T{hour_value:02d}:00",
                        date=date,
                        hour=hour_value,
                        code=code,
                        rain=rain,
                        sources=[source_name],
                    )
                )
            )
        rows.sort(key=lambda row: row["hour"])
        noon = next((row for row in rows if row["hour"] == 12), rows[len(rows) // 2] if rows else None)
        day_code = noon["code"] if noon else 3
        days.append(
            asdict(
                WeatherDay(
                    date=date,
                    code=day_code,
                    temp_min=float(day.get("mintempC", 0)),
                    temp_max=float(day.get("maxtempC", 0)),
                    rain_max=_max_rain(day),
                    hourly_codes=[row["code"] for row in rows],
                    hourly_rain=[row["rain"] for row in rows],
                    hourly_rows=rows,
                    sources=[source_name],
                )
            )
        )

    return WeatherSnapshot(
        city_label=config.city_label,
        created_at=datetime.now().isoformat(timespec="seconds"),
        source=source_name,
        sources=[source_name],
        days=days,
        provider_failures=[],
        source_disagreement=False,
        source_count=1,
    ).to_dict()


def _build_wttr_message(config: WeatherConfig) -> str:
    data = fetch_wttr_weather(config)
    current = data["current_condition"][0]
    today = data["weather"][0]
    tomorrow = data["weather"][1]
    return (
        f"{config.city_label}天气预报 {today['date']}\n"
        f"当前：{_weather_desc(current)}，{current['temp_C']}°C，"
        f"体感{current['FeelsLikeC']}°C，湿度{current['humidity']}%\n"
        f"今天：{today['mintempC']}~{today['maxtempC']}°C，{_daytime_desc(today)}，"
        f"降雨概率最高{_max_rain(today)}%，"
        f"日出{today['astronomy'][0]['sunrise']}，日落{today['astronomy'][0]['sunset']}\n"
        f"明天：{tomorrow['mintempC']}~{tomorrow['maxtempC']}°C，{_daytime_desc(tomorrow)}，"
        f"降雨概率最高{_max_rain(tomorrow)}%\n"
        f"{_fallback_advice(today, current)}"
    )
