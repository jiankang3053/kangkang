# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests


@dataclass(frozen=True)
class WeatherConfig:
    city_query: str = "Jiayu County"
    city_label: str = "嘉鱼县"
    timeout_seconds: float = 20.0
    language: str = "zh-cn"
    latitude: float = 29.9724209
    longitude: float = 113.9335326


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
        raw_value = hour.get("chanceofrain", "0")
        try:
            values.append(int(raw_value))
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


def _advice(today: dict[str, Any], current: dict[str, Any]) -> str:
    rain = _max_rain(today)
    temp = int(current.get("temp_C", "0"))

    tips: list[str] = []
    if rain >= 60:
        tips.append("降雨概率较高，出门带伞。")
    if temp >= 30:
        tips.append("气温偏高，注意防晒和补水。")
    if temp <= 8:
        tips.append("体感偏冷，注意添衣。")
    if not tips:
        tips.append("出门前再看一眼体感和降雨概率。")

    return "".join(tips)


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


def _weather_code_desc(code: int | float | None) -> str:
    try:
        return WEATHER_CODE_TEXT[int(code)]
    except (KeyError, TypeError, ValueError):
        return "未知"


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


def fetch_open_meteo_weather(config: WeatherConfig) -> dict[str, Any]:
    params = {
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
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params=params,
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _build_open_meteo_days(data: dict[str, Any]) -> list[dict[str, Any]]:
    daily = data["daily"]
    hourly = data["hourly"]
    hourly_rows = [
        {
            "time": time,
            "date": time.split("T", 1)[0],
            "hour": int(time.split("T", 1)[1].split(":", 1)[0]),
            "code": hourly["weather_code"][index],
            "rain": hourly["precipitation_probability"][index],
        }
        for index, time in enumerate(hourly["time"])
    ]

    days: list[dict[str, Any]] = []
    for index, date in enumerate(daily["time"]):
        rows = [row for row in hourly_rows if row["date"] == date]
        rows.sort(key=lambda row: row["hour"])
        days.append(
            {
                "date": date,
                "code": daily["weather_code"][index],
                "temp_max": daily["temperature_2m_max"][index],
                "temp_min": daily["temperature_2m_min"][index],
                "rain_max": daily["precipitation_probability_max"][index],
                "hourly_codes": [row["code"] for row in rows],
                "hourly_rain": [row["rain"] for row in rows],
                "hourly_rows": rows,
            }
        )
    return days


def build_weather_snapshot(config: WeatherConfig) -> dict[str, Any]:
    data = fetch_open_meteo_weather(config)
    return {
        "city_label": config.city_label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "days": _build_open_meteo_days(data),
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


def _format_temp(value: int | float) -> int:
    return int(round(float(value)))


def _build_open_meteo_message(config: WeatherConfig, data: dict[str, Any]) -> str:
    days = _build_open_meteo_days(data)
    if len(days) < 4:
        raise ValueError("Open-Meteo 返回的预报天数不足 4 天。")

    today, tomorrow, after_tomorrow, third_day = days[:4]
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
        punctuation = "。" if index == len(periods) - 1 else "；"
        period_lines.append(
            f"{start:02d}:00-{end:02d}:00{weather}，降雨概率{rain}%{punctuation}"
        )

    def day_line(label: str, day: dict[str, Any]) -> str:
        return (
            f"{label}：{_weather_code_desc(day['code'])}，"
            f"气温{_format_temp(day['temp_min'])}-{_format_temp(day['temp_max'])}℃，"
            f"降雨可能{_rain_level(day['rain_max'])}。"
        )

    return "\n".join(
        [
            "【天气预报】",
            "",
            "今日：",
            *period_lines,
            "",
            (
                f"今日气温{_format_temp(today['temp_min'])}-"
                f"{_format_temp(today['temp_max'])}℃，"
                f"建议{_open_meteo_advice(today)}。"
            ),
            "",
            day_line("明天", tomorrow),
            day_line("后天", after_tomorrow),
            day_line("大后天", third_day),
        ]
    )


def fetch_wttr_weather(config: WeatherConfig) -> dict[str, Any]:
    url = f"https://wttr.in/{quote(config.city_query)}"
    params = {"format": "j1", "lang": config.language}
    response = requests.get(url, params=params, timeout=config.timeout_seconds)
    response.raise_for_status()
    return response.json()


def build_weather_message(config: WeatherConfig) -> str:
    try:
        return _build_open_meteo_message(config, fetch_open_meteo_weather(config))
    except Exception:
        return _build_wttr_message(config)


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
        f"{_advice(today, current)}"
    )
