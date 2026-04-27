# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time as dt_time, timedelta
import json
from pathlib import Path
import threading
import time
from typing import Any

from .config import AppConfig, RecipientConfig, load_config, user_data_dir
from .weather import (
    _format_temp,
    _rain_level,
    _weather_code_desc,
    build_weather_snapshot,
    weather_code_severity,
)
from .wechat import choose_sender


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
    return user_data_dir() / path


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


def _future_rows(
    snapshot: dict[str, Any],
    now: datetime,
    hours: int = 6,
) -> list[dict[str, Any]]:
    end = now + timedelta(hours=hours)
    rows: list[dict[str, Any]] = []
    for day in snapshot.get("days", [])[:2]:
        for row in day.get("hourly_rows", []):
            row_time = _row_datetime(row)
            if now <= row_time < end:
                rows.append(row)
    rows.sort(key=lambda item: str(item["time"]))
    return rows


def _snapshot_signal(
    snapshot: dict[str, Any],
    now: datetime,
    future_hours: int = 6,
) -> dict[str, Any]:
    days = snapshot.get("days", [])
    if not days:
        raise ValueError("天气快照缺少 days 数据。")
    today = days[0]
    future = _future_rows(snapshot, now, hours=future_hours)
    future_rain = [int(row.get("rain") or 0) for row in future]
    future_codes = [row.get("code") for row in future]
    future_severities = [weather_code_severity(code) for code in future_codes]
    wettest = max(future, key=lambda row: int(row.get("rain") or 0), default=None)
    worst = max(future, key=lambda row: weather_code_severity(row.get("code")), default=None)
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
        "future_severity_max": max(future_severities, default=0),
        "future_severe_weather": _weather_code_desc(worst.get("code")) if worst else "未知",
        "today_temp_min": _format_temp(today["temp_min"]),
        "today_temp_max": _format_temp(today["temp_max"]),
        "future_days": future_days,
        "future_rows": future,
    }


def _snapshot_summary(
    snapshot: dict[str, Any] | None,
    now: datetime | None = None,
    future_hours: int = 6,
) -> dict[str, Any] | None:
    if not snapshot:
        return None
    now = now or _now()
    try:
        signal = _snapshot_signal(snapshot, now, future_hours=future_hours)
    except Exception:
        signal = {}
    days = snapshot.get("days", [])
    today = days[0] if days else {}
    return {
        "created_at": snapshot.get("created_at"),
        "city_label": snapshot.get("city_label"),
        "source": snapshot.get("source"),
        "source_count": snapshot.get("source_count", len(snapshot.get("sources", []))),
        "source_disagreement": bool(snapshot.get("source_disagreement")),
        "provider_failures": snapshot.get("provider_failures", []),
        "today_weather": _weather_code_desc(today.get("code")) if today else None,
        "today_temp_min": _format_temp(today["temp_min"]) if "temp_min" in today else None,
        "today_temp_max": _format_temp(today["temp_max"]) if "temp_max" in today else None,
        "today_rain_max": int(today.get("rain_max") or 0) if today else None,
        "future_hours": future_hours,
        "future_rain_max": signal.get("future_rain_max"),
        "future_weather": signal.get("future_severe_weather") or signal.get("future_weather"),
    }


def evaluate_alerts(
    previous_snapshot: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
    now: datetime | None = None,
    future_hours: int = 6,
) -> list[Alert]:
    if previous_snapshot is None:
        return []

    now = now or _now()
    previous = _snapshot_signal(previous_snapshot, now, future_hours=future_hours)
    current = _snapshot_signal(current_snapshot, now, future_hours=future_hours)
    alerts: list[Alert] = []

    if previous["future_rain_max"] < 50 <= current["future_rain_max"]:
        alerts.append(
            Alert(
                key="rain_6h_threshold",
                title="未来6小时降雨概率升高",
                detail=f"未来{future_hours}小时最高降雨概率升至{current['future_rain_max']}%。",
            )
        )

    if current["future_rain_max"] - previous["future_rain_max"] >= 30:
        alerts.append(
            Alert(
                key="rain_6h_jump",
                title="未来6小时降雨概率明显上升",
                detail=(
                    f"未来{future_hours}小时最高降雨概率由{previous['future_rain_max']}%"
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
                detail=f"未来{future_hours}小时可能出现{current['future_severe_weather']}。",
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

    if current_snapshot.get("source_disagreement"):
        alerts.append(
            Alert(
                key="source_disagreement",
                title="多源预报分歧",
                detail="多源预报存在分歧，已按偏高风险提醒。",
            )
        )

    return alerts


def _format_future_rows(
    snapshot: dict[str, Any],
    now: datetime,
    future_hours: int,
) -> list[str]:
    rows = _future_rows(snapshot, now, hours=future_hours)
    lines = []
    for row in rows[:future_hours]:
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
    future_hours: int = 6,
) -> str:
    now = now or _now()
    header = "【夜间天气变化汇总】" if suppressed else "【天气变化提醒】"
    lines = [
        header,
        "",
        "天气预报有新变化：",
        *[f"- {alert.detail}" for alert in alerts],
        "",
        f"未来{future_hours}小时：",
        *_format_future_rows(snapshot, now, future_hours),
        "",
        "建议按偏高风险准备，必要时携带雨具或调整出行。",
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
            "recipients": {},
        }

    @property
    def app_config(self) -> AppConfig:
        return load_config(self.config_path, create_user_config=self.config_path is None)

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
        state = self._load_state()
        recipient_state = state.get("recipients", {})
        status.update(
            {
                "contact": config.contact,
                "backend": config.monitor.backend,
                "interval_minutes": config.monitor.interval_minutes,
                "quiet_hours": {
                    "start": config.monitor.quiet_start,
                    "end": config.monitor.quiet_end,
                },
                "state_path": str(self.state_file),
                "recipients": {
                    recipient.name: {
                        "enabled": recipient.enabled,
                        "city_label": recipient.city_label,
                        "last_check_at": recipient_state.get(recipient.name, {}).get("last_check_at"),
                        "last_result": recipient_state.get(recipient.name, {}).get("last_result"),
                        "current_risk": _snapshot_summary(
                            recipient_state.get(recipient.name, {}).get("last_snapshot"),
                            future_hours=config.monitor.future_hours,
                        ),
                        "recent_checks": recipient_state.get(recipient.name, {}).get("recent_checks", [])[-5:],
                        "recent_sends": recipient_state.get(recipient.name, {}).get("recent_sends", [])[-5:],
                    }
                    for recipient in config.recipients
                },
            }
        )
        return status

    def _load_state(self) -> dict[str, Any]:
        path = self.state_file
        if not path.exists():
            return {"recipients": {}}
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            state.setdefault("recipients", {})
            return state
        except Exception:
            return {"recipients": {}}

    def _save_state(self, state: dict[str, Any]) -> None:
        path = self.state_file
        path.parent.mkdir(parents=True, exist_ok=True)
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
                self.check_once(real_send=True, recipient_name=None)
            except Exception as exc:
                self._set_status(
                    last_check_at=_now().isoformat(timespec="seconds"),
                    last_result=f"轮询失败：{exc}",
                )
            wait_seconds = max(60, config.monitor.interval_minutes * 60)
            if self._stop.wait(wait_seconds):
                break

    def _recipient_weather_snapshot(
        self,
        config: AppConfig,
        recipient: RecipientConfig,
    ) -> dict[str, Any]:
        weather_config = recipient.weather_config(
            timeout_seconds=config.providers.timeout_seconds,
            language=config.providers.language,
        )
        return build_weather_snapshot(
            weather_config,
            comparison_models=config.providers.comparison_models,
            fallback_wttr=config.providers.fallback_wttr,
        )

    def _append_limited(
        self,
        items: list[dict[str, Any]],
        item: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        return [*items, item][-limit:]

    def check_once(
        self,
        real_send: bool,
        recipient_name: str | None = None,
    ) -> dict[str, Any]:
        config = self.app_config
        recipients = [
            config.recipient_by_name(recipient_name)
        ] if recipient_name else [recipient for recipient in config.recipients if recipient.enabled]
        state = self._load_state()
        state.setdefault("recipients", {})
        results = []
        for recipient in recipients:
            results.append(self._check_recipient(config, recipient, state, real_send=real_send))
        self._save_state(state)
        checked_at = _now().isoformat(timespec="seconds")
        message = "；".join(result["message"] for result in results) if results else "没有启用的目标。"
        self._set_status(
            enabled=config.monitor.enabled,
            running=self._thread is not None,
            last_check_at=checked_at,
            last_result=message,
            last_send=next((r.get("send_result") for r in results if r.get("send_result")), None),
        )
        return {
            "ok": all(result.get("ok", False) for result in results),
            "checked_at": checked_at,
            "dry_run": not real_send,
            "results": results,
        }

    def _check_recipient(
        self,
        config: AppConfig,
        recipient: RecipientConfig,
        state: dict[str, Any],
        real_send: bool,
    ) -> dict[str, Any]:
        monitor = config.monitor
        now = _now()
        recipient_state = state["recipients"].setdefault(recipient.name, {})
        previous = recipient_state.get("last_snapshot")
        current = self._recipient_weather_snapshot(config, recipient)
        day_key = _today_key(now)
        sent_by_day = recipient_state.setdefault("sent_alert_keys", {})
        sent_today = set(sent_by_day.get(day_key, []))
        suppressed_alerts = [
            Alert(**item)
            for item in recipient_state.get("suppressed_alerts", [])
            if isinstance(item, dict) and {"key", "title", "detail"} <= set(item)
        ]

        alerts = evaluate_alerts(
            previous,
            current,
            now=now,
            future_hours=monitor.future_hours,
        )
        active_alerts = [alert for alert in alerts if alert.key not in sent_today]
        quiet = _is_quiet(now, monitor.quiet_start, monitor.quiet_end)
        result: dict[str, Any] = {
            "ok": True,
            "recipient": recipient.name,
            "checked_at": now.isoformat(timespec="seconds"),
            "dry_run": not real_send,
            "baseline_created": previous is None,
            "quiet": quiet,
            "alerts": [asdict(alert) for alert in alerts],
            "sent": False,
            "send_result": None,
            "message": "",
            "source_count": current.get("source_count", 0),
            "source_disagreement": current.get("source_disagreement", False),
            "provider_failures": current.get("provider_failures", []),
        }

        if previous is None:
            result["message"] = f"{recipient.name}：首次轮询只建立天气基准。"
        elif quiet and active_alerts:
            recipient_state["suppressed_alerts"] = [asdict(alert) for alert in active_alerts]
            result["message"] = f"{recipient.name}：夜间免打扰，已记录变化但未发送。"
        else:
            pending_by_key = {
                alert.key: alert
                for alert in suppressed_alerts
                if alert.key not in sent_today
            }
            pending_by_key.update({alert.key: alert for alert in active_alerts})
            pending = list(pending_by_key.values())
            suppressed_send = bool(suppressed_alerts and pending)

            if pending:
                message = build_alert_message(
                    pending,
                    current,
                    suppressed=suppressed_send,
                    now=now,
                    future_hours=monitor.future_hours,
                )
                sender = choose_sender(
                    real_send=real_send,
                    backend=monitor.backend,
                    window_handle=self.window_handle,
                )
                send_result = sender.send(recipient.name, message)
                result["ok"] = send_result.ok
                result["sent"] = bool(real_send and send_result.ok)
                result["send_result"] = asdict(send_result)
                result["message"] = message
                if send_result.ok:
                    if real_send:
                        sent_today.update(alert.key for alert in pending)
                        recipient_state["suppressed_alerts"] = []
                    recipient_state["recent_sends"] = self._append_limited(
                        recipient_state.get("recent_sends", []),
                        {
                            "sent_at": result["checked_at"],
                            "dry_run": not real_send,
                            "alerts": [alert.key for alert in pending],
                            "ok": send_result.ok,
                            "delivered": bool(real_send and send_result.ok),
                        },
                        monitor.daily_history_limit,
                    )
            else:
                result["message"] = f"{recipient.name}：没有达到补发条件。"

        recipient_state["last_snapshot"] = current
        recipient_state["last_check_at"] = result["checked_at"]
        recipient_state["last_result"] = result["message"]
        sent_by_day[day_key] = sorted(sent_today)
        recipient_state["recent_checks"] = self._append_limited(
            recipient_state.get("recent_checks", []),
            {
                "checked_at": result["checked_at"],
                "alerts": [alert["key"] for alert in result["alerts"]],
                "sent": result["sent"],
                "quiet": result["quiet"],
                "source_count": result["source_count"],
                "source_disagreement": result["source_disagreement"],
            },
            monitor.daily_history_limit,
        )
        return result
