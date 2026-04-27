# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time as dt_time, timedelta
import json
from pathlib import Path
import threading
import time
from typing import Any

from .config import AppConfig, load_config
from .weather import (
    _format_temp,
    _rain_level,
    _weather_code_desc,
    build_weather_snapshot,
)
from .wechat import choose_sender


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


RAIN_LEVEL_ORDER = {"未知": -1, "低": 0, "中": 1, "高": 2}


@dataclass(frozen=True)
class Alert:
    key: str
    title: str
    detail: str


def _now() -> datetime:
    return datetime.now()


def _state_path(config_path: str | None, state_path: str) -> Path:
    path = Path(state_path)
    if path.is_absolute():
        return path
    if config_path is not None:
        return Path(config_path).resolve().parent / path
    return Path.cwd() / path


def _parse_time(value: str) -> dt_time:
    hour, minute = value.split(":", 1)
    return dt_time(hour=int(hour), minute=int(minute))


def _is_quiet(now: datetime, start: str, end: str) -> bool:
    start_time = _parse_time(start)
    end_time = _parse_time(end)
    current = now.time()
    if start_time <= end_time:
        return start_time <= current < end_time
    return current >= start_time or current < end_time


def _today_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _row_datetime(row: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(row["time"]))


def _future_rows(snapshot: dict[str, Any], now: datetime, hours: int = 6) -> list[dict[str, Any]]:
    end = now + timedelta(hours=hours)
    rows: list[dict[str, Any]] = []
    for day in snapshot.get("days", [])[:2]:
        for row in day.get("hourly_rows", []):
            row_time = _row_datetime(row)
            if now <= row_time < end:
                rows.append(row)
    rows.sort(key=lambda item: str(item["time"]))
    return rows


def _severity(code: int | float | None) -> int:
    try:
        return SEVERITY_BY_CODE.get(int(code), 0)
    except (TypeError, ValueError):
        return 0


def _snapshot_signal(snapshot: dict[str, Any], now: datetime) -> dict[str, Any]:
    days = snapshot.get("days", [])
    today = days[0]
    future = _future_rows(snapshot, now)
    future_rain = [int(row.get("rain") or 0) for row in future]
    future_codes = [row.get("code") for row in future]
    future_severities = [_severity(code) for code in future_codes]
    max_severity = max(future_severities, default=0)
    wettest = max(future, key=lambda row: int(row.get("rain") or 0), default=None)
    worst = max(future, key=lambda row: _severity(row.get("code")), default=None)
    future_days = []
    for day in days[1:4]:
        level = _rain_level(day.get("rain_max"))
        future_days.append(
            {
                "date": day.get("date"),
                "rain_max": int(day.get("rain_max") or 0),
                "rain_level": level,
                "rain_order": RAIN_LEVEL_ORDER.get(level, -1),
                "weather": _weather_code_desc(day.get("code")),
            }
        )
    return {
        "future_rain_max": max(future_rain, default=0),
        "future_weather": _weather_code_desc(wettest.get("code")) if wettest else "未知",
        "future_severity_max": max_severity,
        "future_severe_weather": _weather_code_desc(worst.get("code")) if worst else "未知",
        "today_temp_min": _format_temp(today["temp_min"]),
        "today_temp_max": _format_temp(today["temp_max"]),
        "future_days": future_days,
        "future_rows": future,
    }


def evaluate_alerts(
    previous_snapshot: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
    now: datetime | None = None,
) -> list[Alert]:
    if previous_snapshot is None:
        return []

    now = now or _now()
    previous = _snapshot_signal(previous_snapshot, now)
    current = _snapshot_signal(current_snapshot, now)
    alerts: list[Alert] = []

    if previous["future_rain_max"] < 50 <= current["future_rain_max"]:
        alerts.append(
            Alert(
                key="rain_6h_threshold",
                title="未来6小时降雨概率升高",
                detail=f"未来6小时最高降雨概率升至{current['future_rain_max']}%。",
            )
        )

    if current["future_rain_max"] - previous["future_rain_max"] >= 30:
        alerts.append(
            Alert(
                key="rain_6h_jump",
                title="未来6小时降雨概率明显上升",
                detail=(
                    f"未来6小时最高降雨概率由{previous['future_rain_max']}%"
                    f"升至{current['future_rain_max']}%。"
                ),
            )
        )

    if (
        current["future_severity_max"] > previous["future_severity_max"]
        and current["future_severity_max"] >= 4
    ):
        alerts.append(
            Alert(
                key="weather_upgrade_6h",
                title="未来6小时天气转差",
                detail=f"未来6小时可能出现{current['future_severe_weather']}。",
            )
        )

    if (
        abs(current["today_temp_min"] - previous["today_temp_min"]) >= 3
        or abs(current["today_temp_max"] - previous["today_temp_max"]) >= 3
    ):
        alerts.append(
            Alert(
                key="temp_change_today",
                title="今日气温变化明显",
                detail=(
                    f"今日气温由{previous['today_temp_min']}-"
                    f"{previous['today_temp_max']}℃调整为"
                    f"{current['today_temp_min']}-{current['today_temp_max']}℃。"
                ),
            )
        )

    for index, (old_day, new_day) in enumerate(
        zip(previous["future_days"], current["future_days"]),
        start=1,
    ):
        if new_day["rain_order"] > old_day["rain_order"] and new_day["rain_order"] >= 1:
            label = ["明天", "后天", "大后天"][index - 1]
            alerts.append(
                Alert(
                    key=f"future_rain_upgrade_{index}",
                    title=f"{label}降雨可能升级",
                    detail=(
                        f"{label}降雨可能由{old_day['rain_level']}"
                        f"升至{new_day['rain_level']}。"
                    ),
                )
            )

    return alerts


def _format_future_rows(snapshot: dict[str, Any], now: datetime) -> list[str]:
    rows = _future_rows(snapshot, now)
    lines = []
    for row in rows[:6]:
        row_time = _row_datetime(row)
        lines.append(
            f"{row_time.strftime('%H:%M')} "
            f"{_weather_code_desc(row.get('code'))}，"
            f"降雨概率{int(row.get('rain') or 0)}%"
        )
    return lines


def build_alert_message(
    alerts: list[Alert],
    snapshot: dict[str, Any],
    suppressed: bool = False,
    now: datetime | None = None,
) -> str:
    now = now or _now()
    header = "【夜间天气变化汇总】" if suppressed else "【天气变化提醒】"
    lines = [
        header,
        "",
        "检测到天气预报有变化：",
        *[f"- {alert.detail}" for alert in alerts],
        "",
        "未来6小时：",
        *_format_future_rows(snapshot, now),
        "",
        "建议及时查看天气，必要时携带雨具或调整出行安排。",
    ]
    return "\n".join(lines)


class WeatherMonitor:
    def __init__(self, config_path: str | None, window_handle: int | None) -> None:
        self.config_path = config_path
        self.window_handle = window_handle
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_status: dict[str, Any] = {
            "enabled": False,
            "running": False,
            "last_check_at": None,
            "next_check_at": None,
            "last_result": "尚未检查。",
            "last_send": None,
        }

    @property
    def app_config(self) -> AppConfig:
        return load_config(self.config_path)

    @property
    def state_file(self) -> Path:
        config = self.app_config
        return _state_path(self.config_path, config.monitor.state_path)

    def start(self) -> None:
        config = self.app_config
        with self._lock:
            self._last_status["enabled"] = config.monitor.enabled
            if not config.monitor.enabled or self._thread is not None:
                return
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._last_status["running"] = True
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def status(self) -> dict[str, Any]:
        with self._lock:
            status = dict(self._last_status)
        config = self.app_config
        status.update(
            {
                "contact": config.monitor.contact,
                "backend": config.monitor.backend,
                "interval_minutes": config.monitor.interval_minutes,
                "quiet_hours": {
                    "start": config.monitor.quiet_start,
                    "end": config.monitor.quiet_end,
                },
                "state_path": str(self.state_file),
            }
        )
        return status

    def _load_state(self) -> dict[str, Any]:
        path = self.state_file
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        path = self.state_file
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _set_status(self, **values: Any) -> None:
        with self._lock:
            self._last_status.update(values)

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            config = self.app_config
            now = _now()
            next_check = now + timedelta(minutes=config.monitor.interval_minutes)
            self._set_status(next_check_at=next_check.isoformat(timespec="seconds"))
            try:
                self.check_once(real_send=True, force=False)
            except Exception as exc:
                self._set_status(
                    last_check_at=_now().isoformat(timespec="seconds"),
                    last_result=f"轮询失败：{exc}",
                )
            wait_seconds = max(60, config.monitor.interval_minutes * 60)
            if self._stop.wait(wait_seconds):
                break

    def check_once(self, real_send: bool, force: bool = True) -> dict[str, Any]:
        config = self.app_config
        monitor = config.monitor
        now = _now()
        state = self._load_state()
        previous = state.get("last_snapshot")
        current = build_weather_snapshot(config.weather)
        day_key = _today_key(now)
        sent_by_day = state.setdefault("sent_alert_keys", {})
        sent_today = set(sent_by_day.get(day_key, []))
        suppressed_alerts = [
            Alert(**item)
            for item in state.get("suppressed_alerts", [])
            if isinstance(item, dict) and {"key", "title", "detail"} <= set(item)
        ]

        alerts = evaluate_alerts(previous, current, now=now)
        active_alerts = [alert for alert in alerts if alert.key not in sent_today]
        quiet = _is_quiet(now, monitor.quiet_start, monitor.quiet_end)
        result = {
            "ok": True,
            "checked_at": now.isoformat(timespec="seconds"),
            "baseline_created": previous is None,
            "quiet": quiet,
            "alerts": [asdict(alert) for alert in alerts],
            "sent": False,
            "send_result": None,
            "message": "",
        }

        if previous is None:
            result["message"] = "首次轮询只建立天气基准，不自动发送。"
        elif quiet and active_alerts:
            state["suppressed_alerts"] = [asdict(alert) for alert in active_alerts]
            result["message"] = "当前在夜间免打扰时段，已记录变化但未发送。"
        else:
            pending = active_alerts
            suppressed_send = False
            if not pending and suppressed_alerts:
                pending = [alert for alert in suppressed_alerts if alert.key not in sent_today]
                suppressed_send = True

            if pending:
                message = build_alert_message(
                    pending,
                    current,
                    suppressed=suppressed_send,
                    now=now,
                )
                sender = choose_sender(
                    real_send=real_send,
                    backend=monitor.backend,
                    window_handle=self.window_handle,
                )
                send_result = sender.send(monitor.contact, message)
                result["sent"] = send_result.ok
                result["send_result"] = asdict(send_result)
                result["message"] = message
                if send_result.ok:
                    sent_today.update(alert.key for alert in pending)
                    state["suppressed_alerts"] = []
            else:
                result["message"] = "没有达到补发条件。"

        sent_by_day[day_key] = sorted(sent_today)
        state["last_snapshot"] = current
        state["last_check_at"] = result["checked_at"]
        self._save_state(state)
        self._set_status(
            enabled=monitor.enabled,
            running=self._thread is not None,
            last_check_at=result["checked_at"],
            last_result=result["message"],
            last_send=result["send_result"],
        )
        return result
