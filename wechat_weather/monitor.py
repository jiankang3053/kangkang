# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time as dt_time, timedelta
import json
from pathlib import Path
import threading
import time
from typing import Any

from .config import (
    AlertOptionsConfig,
    AppConfig,
    AutomationJobConfig,
    LocationConfig,
    WechatTargetConfig,
    load_config,
    user_data_dir,
)
from .send_batch import (
    SendTaskLock,
    append_send_history,
    apply_send_result,
    create_send_batch,
)
from .busy_detector import BusyDetector, BusyCheckResult
from .reminder_policy import ReminderDecision, choose_reminder_decision
from .weather import (
    _format_temp,
    _rain_level,
    _weather_code_desc,
    build_weather_message_from_snapshot,
    build_weather_snapshot,
    weather_code_severity,
)
from .wechat import SendResult, choose_sender


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


def _parse_minutes(value: str, *, allow_2400: bool = False) -> int:
    hour, minute = value.split(":", 1)
    hour_int = int(hour)
    minute_int = int(minute)
    if minute_int < 0 or minute_int >= 60:
        raise ValueError(f"时间格式错误：{value}")
    if hour_int == 24 and minute_int == 0 and allow_2400:
        return 24 * 60
    if hour_int < 0 or hour_int >= 24:
        raise ValueError(f"时间格式错误：{value}")
    return hour_int * 60 + minute_int


def _is_quiet(now: datetime, start: str, end: str) -> bool:
    start_time = _parse_time(start)
    end_time = _parse_time(end)
    current = now.time()
    if start_time <= end_time:
        return start_time <= current < end_time
    return current >= start_time or current < end_time


def _is_active_window(now: datetime, windows: list[str]) -> bool:
    current = now.hour * 60 + now.minute
    for window in windows:
        if "-" not in window:
            continue
        start_text, end_text = [item.strip() for item in window.split("-", 1)]
        try:
            start = _parse_minutes(start_text)
            end = _parse_minutes(end_text, allow_2400=True)
        except Exception:
            continue
        if start < end and start <= current < end:
            return True
        if start > end and (current >= start or current < end):
            return True
    return False


def _today_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _row_datetime(row: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(row["time"]))


def _safe_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _fixed_run_key(now: datetime, fixed_time: str) -> str:
    return f"{_today_key(now)}:{fixed_time}"


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
    alert_options: AlertOptionsConfig | dict[str, Any] | None = None,
) -> list[Alert]:
    if previous_snapshot is None:
        return []

    now = now or _now()
    if isinstance(alert_options, AlertOptionsConfig):
        options = asdict(alert_options)
    elif isinstance(alert_options, dict):
        options = alert_options
    else:
        options = asdict(AlertOptionsConfig())
    rain_threshold = int(options.get("rain_threshold_percent", 50))
    rain_jump = int(options.get("rain_jump_percent", 30))
    temp_change = float(options.get("temp_change_celsius", 3.0))
    weather_upgrade_enabled = bool(options.get("weather_upgrade_enabled", True))
    future_rain_upgrade_enabled = bool(options.get("future_rain_upgrade_enabled", True))
    previous = _snapshot_signal(previous_snapshot, now, future_hours=future_hours)
    current = _snapshot_signal(current_snapshot, now, future_hours=future_hours)
    alerts: list[Alert] = []

    if previous["future_rain_max"] < rain_threshold <= current["future_rain_max"]:
        alerts.append(
            Alert(
                key="rain_6h_threshold",
                title="未来6小时降雨概率升高",
                detail=f"未来{future_hours}小时最高降雨概率升至{current['future_rain_max']}%。",
            )
        )

    if current["future_rain_max"] - previous["future_rain_max"] >= rain_jump:
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
        weather_upgrade_enabled
        and current["future_severity_max"] > previous["future_severity_max"]
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
        abs(current["today_temp_min"] - previous["today_temp_min"]) >= temp_change
        or abs(current["today_temp_max"] - previous["today_temp_max"]) >= temp_change
    ):
        alerts.append(
            Alert(
                key="temp_change_today",
                title="今日气温变化明显",
                detail=(
                    f"今日气温由{previous['today_temp_min']}-{previous['today_temp_max']}℃"
                    f"调整为{current['today_temp_min']}-{current['today_temp_max']}℃。"
                ),
            )
        )

    for index, (old_day, new_day) in enumerate(
        zip(previous["future_days"], current["future_days"]),
        start=1,
    ):
        if (
            future_rain_upgrade_enabled
            and new_day["rain_order"] > old_day["rain_order"]
            and new_day["rain_order"] >= 1
        ):
            label = ["明天", "后天", "大后天"][index - 1]
            alerts.append(
                Alert(
                    key=f"future_rain_upgrade_{index}",
                    title=f"{label}降雨可能升级",
                    detail=f"{label}降雨可能由{old_day['rain_level']}升至{new_day['rain_level']}。",
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
            "jobs": {},
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
            self._stop.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._last_status["running"] = True
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        with self._lock:
            self._last_status["running"] = False

    def status(self) -> dict[str, Any]:
        with self._lock:
            status = dict(self._last_status)
        config = self.app_config
        state = self._load_state()
        job_state = state.get("jobs", {})
        jobs = {}
        for job in config.automation_jobs:
            location = config.location_by_id(job.location_id)
            target = config.wechat_target_by_id(job.wechat_target_id)
            state_item = job_state.get(job.id, {})
            jobs[job.id] = {
                "id": job.id,
                "enabled": job.enabled,
                "location": asdict(location),
                "wechat_target": asdict(target),
                "interval_minutes": job.interval_minutes,
                "fixed_times": job.fixed_times,
                "active_windows": job.active_windows,
                "alert_options": asdict(job.alert_options),
                "quiet_hours": {
                    "start": job.quiet_start,
                    "end": job.quiet_end,
                    "allow_quiet_send": job.allow_quiet_send,
                },
                "last_check_at": state_item.get("last_check_at"),
                "next_interval_at": self._next_interval_time(job, state_item, _now()).isoformat(timespec="seconds"),
                "last_result": state_item.get("last_result"),
                "current_risk": _snapshot_summary(
                    state_item.get("last_snapshot"),
                    future_hours=config.monitor.future_hours,
                ),
                "recent_checks": state_item.get("recent_checks", [])[-5:],
                "recent_sends": state_item.get("recent_sends", [])[-5:],
                "automation_state": state_item.get("automation_state"),
                "recent_states": state_item.get("recent_states", [])[-5:],
                "fixed_pending": list((state_item.get("fixed_pending") or {}).values())[-5:]
                if isinstance(state_item.get("fixed_pending"), dict)
                else [],
            }

        status.update(
            {
                "contact": config.contact,
                "backend": config.monitor.backend,
                "state_path": str(self.state_file),
                "jobs": jobs,
                "recipients": {
                    item["wechat_target"]["name"]: {
                        "enabled": item["enabled"],
                        "city_label": item["location"]["name"],
                        "last_check_at": item["last_check_at"],
                        "last_result": item["last_result"],
                        "current_risk": item["current_risk"],
                        "recent_checks": item["recent_checks"],
                        "recent_sends": item["recent_sends"],
                    }
                    for item in jobs.values()
                },
            }
        )
        return status

    def _load_state(self) -> dict[str, Any]:
        path = self.state_file
        if not path.exists():
            return {"jobs": {}, "recipients": {}}
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            state.setdefault("jobs", {})
            state.setdefault("recipients", {})
            return state
        except Exception:
            return {"jobs": {}, "recipients": {}}

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
            try:
                result = self.run_due(real_send=True)
                self._set_status(
                    enabled=self.app_config.monitor.enabled,
                    running=self._thread is not None,
                    last_check_at=result["checked_at"],
                    next_check_at=result["next_check_at"],
                    last_result=result["message"],
                    last_send=result.get("last_send"),
                )
            except Exception as exc:
                self._set_status(
                    last_check_at=_now().isoformat(timespec="seconds"),
                    last_result=f"轮询失败：{exc}",
                )
            if self._stop.wait(60):
                break

    def _job_weather_snapshot(
        self,
        config: AppConfig,
        location: LocationConfig,
    ) -> dict[str, Any]:
        weather_config = location.weather_config(
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

    def _record_job_state(
        self,
        job_state: dict[str, Any],
        status: str,
        message: str = "",
        **detail: Any,
    ) -> dict[str, Any]:
        item = {
            "status": status,
            "message": message,
            "updated_at": _now().isoformat(timespec="seconds"),
            **{key: value for key, value in detail.items() if value is not None},
        }
        job_state["automation_state"] = item
        job_state["recent_states"] = self._append_limited(
            job_state.get("recent_states", []),
            item,
            10,
        )
        return item

    def _record_skipped_batch(
        self,
        *,
        location: LocationConfig,
        target: WechatTargetConfig,
        message: str,
        trigger: str,
        reason: str,
        detail: str,
        real_send: bool,
    ) -> dict[str, Any]:
        batch = create_send_batch(
            trigger=trigger,
            location=location,
            message=message or detail,
            targets=[target],
            real_send=real_send,
        )
        now_text = _now().isoformat(timespec="seconds")
        batch.started_at = now_text
        batch.finished_at = now_text
        batch.status = "skipped"
        if batch.targets:
            attempt = batch.targets[0]
            attempt.status = "skipped"
            attempt.started_at = now_text
            attempt.finished_at = now_text
            attempt.duration_ms = 0
            attempt.error_code = reason
            attempt.error_message = detail
            attempt.delivered = False
        append_send_history(batch)
        return batch.to_dict()

    def _busy_check(self, config: AppConfig) -> BusyCheckResult:
        return BusyDetector(config.do_not_disturb).should_delay_send()

    def _busy_skip_result(
        self,
        *,
        config: AppConfig,
        job: AutomationJobConfig,
        location: LocationConfig,
        target: WechatTargetConfig,
        message: str,
        trigger: str,
        job_state: dict[str, Any],
        real_send: bool,
        busy: BusyCheckResult,
    ) -> dict[str, Any] | None:
        if not real_send or not busy.busy:
            return None
        action = busy.action
        if action == "force_send":
            return None
        status_by_action = {
            "delay": "DELAYED_BUSY",
            "skip": "SKIPPED_BUSY",
            "tray_only": "TRAY_ONLY",
        }
        status = status_by_action.get(action, "DELAYED_BUSY")
        now = _now()
        retry_after = now + timedelta(minutes=busy.delay_minutes)
        detail = busy.detail or "检测到忙碌状态，本次自动发送暂不打开微信。"
        if action == "delay":
            detail = f"{detail} 已延迟 {busy.delay_minutes} 分钟后重试。"
        elif action == "skip":
            detail = f"{detail} 已按设置跳过本次发送。"
        elif action == "tray_only":
            detail = f"{detail} 已按设置只记录托盘提醒，不打开微信。"
        batch = self._record_skipped_batch(
            location=location,
            target=target,
            message=message,
            trigger=trigger,
            reason=status.lower(),
            detail=detail,
            real_send=real_send,
        )
        self._record_job_state(
            job_state,
            status,
            detail,
            trigger=trigger,
            busy=busy.to_dict(),
            retry_after_at=retry_after.isoformat(timespec="seconds") if action == "delay" else None,
            batch_id=batch.get("batch_id"),
        )
        return {
            "ok": True,
            "type": trigger,
            "job_id": job.id,
            "location": asdict(location),
            "wechat_target": asdict(target),
            "checked_at": now.isoformat(timespec="seconds"),
            "dry_run": not real_send,
            "sent": False,
            "send_result": None,
            "message": detail,
            "busy": busy.to_dict(),
            "batch": batch,
            "status": status,
            "retry_after_at": retry_after.isoformat(timespec="seconds") if action == "delay" else None,
        }

    def _policy_skip_result(
        self,
        *,
        config: AppConfig,
        job: AutomationJobConfig,
        location: LocationConfig,
        target: WechatTargetConfig,
        trigger: str,
        job_state: dict[str, Any],
        decision: ReminderDecision,
        real_send: bool,
    ) -> dict[str, Any]:
        now = _now()
        detail = decision.message or "天气正常，根据你的提醒策略未发送。"
        batch = None
        if config.reminder_policy.record_skipped_history:
            batch = self._record_skipped_batch(
                location=location,
                target=target,
                message=detail,
                trigger=trigger,
                reason=decision.reason,
                detail=detail,
                real_send=real_send,
            )
        self._record_job_state(
            job_state,
            "SKIPPED_NORMAL_WEATHER" if decision.weather_status == "normal" else "SKIPPED",
            detail,
            trigger=trigger,
            reminder_policy=decision.to_dict(),
            batch_id=(batch or {}).get("batch_id"),
        )
        return {
            "ok": True,
            "type": trigger,
            "job_id": job.id,
            "location": asdict(location),
            "wechat_target": asdict(target),
            "checked_at": now.isoformat(timespec="seconds"),
            "dry_run": not real_send,
            "sent": False,
            "send_result": None,
            "message": detail,
            "reminder_policy": decision.to_dict(),
            "batch": batch,
            "status": "SKIPPED_NORMAL_WEATHER",
        }

    def _blocked_send_result(
        self,
        config: AppConfig,
        target: WechatTargetConfig,
        message: str,
        detail: str,
        category: str,
        retryable: bool = True,
    ) -> SendResult:
        return SendResult(
            ok=False,
            backend=config.monitor.backend,
            contact=target.name,
            detail=detail,
            preview=message,
            diagnostics=[],
            error_analysis={
                "category": category,
                "title": "自动发送已被安全拦截",
                "summary": detail,
                "likely_causes": [
                    "已有发送任务正在操作微信",
                    "当前电脑或微信未达到自动发送条件",
                    "自动任务需要等待下一次可用窗口",
                ],
                "next_steps": [
                    "等待当前发送完成后重试",
                    "确认 Windows 未锁屏且微信已登录",
                    "在控制台查看自动发送环境检查和发送历史",
                ],
                "severity": "error",
                "retryable": retryable,
            },
        )

    def _send_single_with_batch(
        self,
        config: AppConfig,
        location: LocationConfig,
        target: WechatTargetConfig,
        message: str,
        *,
        real_send: bool,
        trigger: str,
    ) -> tuple[SendResult, dict[str, Any]]:
        batch = create_send_batch(
            trigger=trigger,
            location=location,
            message=message,
            targets=[target],
            real_send=real_send,
        )
        batch.started_at = _now().isoformat(timespec="seconds")
        attempt = batch.targets[0]
        lock: SendTaskLock | None = None
        if real_send:
            lock = SendTaskLock(owner=batch.batch_id)
            if not lock.acquire():
                result = self._blocked_send_result(
                    config,
                    target,
                    message,
                    "已有微信发送任务正在运行，本次自动发送已跳过，避免重复操作微信。",
                    "send_task_locked",
                )
                now_text = _now().isoformat(timespec="seconds")
                apply_send_result(
                    attempt,
                    result,
                    started_at=now_text,
                    finished_at=now_text,
                    duration_ms=0,
                    real_send=real_send,
                )
                batch.status = "failed"
                batch.finished_at = now_text
                append_send_history(batch)
                return result, batch.to_dict()
        try:
            started_at = _now().isoformat(timespec="seconds")
            start = time.perf_counter()
            sender = choose_sender(
                real_send=real_send,
                backend=config.monitor.backend,
                window_handle=self.window_handle,
                send_strategy=config.monitor.wechat_send_strategy,
                allow_send_button_coordinate_fallback=(
                    config.monitor.allow_send_button_coordinate_fallback
                ),
            )
            result = sender.send(target.name, message)
            finished_at = _now().isoformat(timespec="seconds")
            apply_send_result(
                attempt,
                result,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=int((time.perf_counter() - start) * 1000),
                real_send=real_send,
            )
            batch.status = "success" if result.ok else "failed"
            batch.finished_at = finished_at
            append_send_history(batch)
            return result, batch.to_dict()
        finally:
            if lock is not None:
                lock.release()

    def _next_interval_time(
        self,
        job: AutomationJobConfig,
        job_state: dict[str, Any],
        now: datetime,
    ) -> datetime:
        last_check = _safe_datetime(job_state.get("last_check_at"))
        if last_check is None:
            return now
        return last_check + timedelta(minutes=job.interval_minutes)

    def _interval_due(
        self,
        job: AutomationJobConfig,
        job_state: dict[str, Any],
        now: datetime,
    ) -> bool:
        return now >= self._next_interval_time(job, job_state, now)

    def _fixed_due_entries(
        self,
        job: AutomationJobConfig,
        job_state: dict[str, Any],
        now: datetime,
        grace_minutes: int,
    ) -> list[dict[str, Any]]:
        sent = set(job_state.get("fixed_sent_keys", []))
        expired = set(job_state.get("fixed_expired_keys", []))
        due = []
        grace_seconds = max(1, grace_minutes) * 60
        for fixed in job.fixed_times:
            fixed_time = _parse_time(fixed)
            scheduled = datetime.combine(now.date(), fixed_time)
            seconds = (now - scheduled).total_seconds()
            key = _fixed_run_key(now, fixed)
            if key in sent:
                continue
            entry = {
                "fixed_time": fixed,
                "key": key,
                "due_at": scheduled.isoformat(timespec="seconds"),
                "deadline_at": (scheduled + timedelta(seconds=grace_seconds)).isoformat(timespec="seconds"),
            }
            if 0 <= seconds <= grace_seconds:
                due.append({**entry, "status": "due"})
            elif seconds > grace_seconds and key not in expired:
                due.append({**entry, "status": "expired"})
        return due

    def _next_fixed_time(self, job: AutomationJobConfig, now: datetime) -> datetime | None:
        if not job.fixed_times:
            return None
        candidates = []
        for fixed in job.fixed_times:
            fixed_time = _parse_time(fixed)
            today = datetime.combine(now.date(), fixed_time)
            candidates.append(today if today >= now else today + timedelta(days=1))
        return min(candidates)

    def _next_due_at(self, config: AppConfig, state: dict[str, Any], now: datetime) -> str | None:
        candidates: list[datetime] = []
        for job in config.automation_jobs:
            if not job.enabled:
                continue
            job_state = state.get("jobs", {}).get(job.id, {})
            candidates.append(self._next_interval_time(job, job_state, now))
            fixed_at = self._next_fixed_time(job, now)
            if fixed_at is not None:
                candidates.append(fixed_at)
        if not candidates:
            return None
        return min(candidates).isoformat(timespec="seconds")

    def run_due(self, real_send: bool) -> dict[str, Any]:
        config = self.app_config
        state = self._load_state()
        state.setdefault("jobs", {})
        now = _now()
        results = []
        last_send = None
        for job in config.automation_jobs:
            if not job.enabled:
                continue
            job_state = state["jobs"].setdefault(job.id, {})
            if self._interval_due(job, job_state, now):
                result = self._check_job(config, job, state, real_send=real_send)
                results.append(result)
                if result.get("send_result"):
                    last_send = result["send_result"]
            for fixed_entry in self._fixed_due_entries(
                job,
                job_state,
                now,
                config.monitor.fixed_send_grace_minutes,
            ):
                if fixed_entry["status"] == "expired":
                    result = self._expire_fixed_weather(config, job, fixed_entry, state, real_send=real_send)
                else:
                    result = self._send_fixed_weather(config, job, fixed_entry, state, real_send=real_send)
                results.append(result)
                if result.get("send_result"):
                    last_send = result["send_result"]
        self._save_state(state)
        checked_at = _now().isoformat(timespec="seconds")
        message = "；".join(result["message"] for result in results) if results else "没有到达执行时间。"
        return {
            "ok": all(result.get("ok", False) for result in results) if results else True,
            "checked_at": checked_at,
            "next_check_at": self._next_due_at(config, state, _now()),
            "dry_run": not real_send,
            "message": message,
            "last_send": last_send,
            "results": results,
        }

    def check_once(
        self,
        real_send: bool,
        job_id: str | None = None,
        recipient_name: str | None = None,
    ) -> dict[str, Any]:
        config = self.app_config
        if job_id:
            jobs = [config.job_by_id(job_id)]
        elif recipient_name:
            jobs = config.jobs_for_target_name(recipient_name)
        else:
            jobs = [job for job in config.automation_jobs if job.enabled]
        state = self._load_state()
        state.setdefault("jobs", {})
        results = [self._check_job(config, job, state, real_send=real_send) for job in jobs]
        self._save_state(state)
        checked_at = _now().isoformat(timespec="seconds")
        message = "；".join(result["message"] for result in results) if results else "没有启用的自动化任务。"
        self._set_status(
            enabled=config.monitor.enabled,
            running=self._thread is not None,
            last_check_at=checked_at,
            next_check_at=self._next_due_at(config, state, _now()),
            last_result=message,
            last_send=next((r.get("send_result") for r in results if r.get("send_result")), None),
        )
        return {
            "ok": all(result.get("ok", False) for result in results),
            "checked_at": checked_at,
            "dry_run": not real_send,
            "results": results,
        }

    def _check_job(
        self,
        config: AppConfig,
        job: AutomationJobConfig,
        state: dict[str, Any],
        real_send: bool,
    ) -> dict[str, Any]:
        location = config.location_by_id(job.location_id)
        target = config.wechat_target_by_id(job.wechat_target_id)
        now = _now()
        job_state = state["jobs"].setdefault(job.id, {})
        self._record_job_state(
            job_state,
            "PREPARING",
            f"{location.name} -> {target.name}: interval check is preparing.",
            trigger="interval",
        )
        active_window = _is_active_window(now, job.active_windows)
        if not active_window and not job.allow_quiet_send:
            result: dict[str, Any] = {
                "ok": True,
                "type": "interval_skipped",
                "job_id": job.id,
                "location": asdict(location),
                "wechat_target": asdict(target),
                "checked_at": now.isoformat(timespec="seconds"),
                "dry_run": not real_send,
                "baseline_created": False,
                "quiet": True,
                "active_window": False,
                "outside_active_window": True,
                "active_windows": job.active_windows,
                "alerts": [],
                "sent": False,
                "send_result": None,
                "message": f"{location.name} -> {target.name}：未在自动发送时间段内，已跳过并记录。",
                "source_count": 0,
                "source_disagreement": False,
                "provider_failures": [],
            }
            self._record_job_state(job_state, "SKIPPED", result["message"], trigger="interval")
            job_state["last_check_at"] = result["checked_at"]
            job_state["last_result"] = result["message"]
            job_state["recent_checks"] = self._append_limited(
                job_state.get("recent_checks", []),
                {
                    "checked_at": result["checked_at"],
                    "type": result["type"],
                    "alerts": [],
                    "sent": False,
                    "quiet": True,
                    "active_window": False,
                    "outside_active_window": True,
                    "source_count": 0,
                    "source_disagreement": False,
                },
                config.monitor.daily_history_limit,
            )
            return result
        previous = job_state.get("last_snapshot")
        self._record_job_state(
            job_state,
            "FETCHING_WEATHER",
            f"{location.name} -> {target.name}: fetching weather for interval check.",
            trigger="interval",
        )
        current = self._job_weather_snapshot(config, location)
        self._record_job_state(
            job_state,
            "RENDERING_MESSAGE",
            f"{location.name} -> {target.name}: weather fetched, evaluating alert rules.",
            trigger="interval",
            source_count=current.get("source_count", 0),
        )
        day_key = _today_key(now)
        sent_by_day = job_state.setdefault("sent_alert_keys", {})
        sent_today = set(sent_by_day.get(day_key, []))
        suppressed_alerts = [
            Alert(**item)
            for item in job_state.get("suppressed_alerts", [])
            if isinstance(item, dict) and {"key", "title", "detail"} <= set(item)
        ]

        alerts = evaluate_alerts(
            previous,
            current,
            now=now,
            future_hours=config.monitor.future_hours,
            alert_options=job.alert_options,
        )
        active_alerts = [alert for alert in alerts if alert.key not in sent_today]
        quiet = not active_window
        result: dict[str, Any] = {
            "ok": True,
            "type": "interval_check",
            "job_id": job.id,
            "location": asdict(location),
            "wechat_target": asdict(target),
            "checked_at": now.isoformat(timespec="seconds"),
            "dry_run": not real_send,
            "baseline_created": previous is None,
            "quiet": quiet,
            "active_window": active_window,
            "outside_active_window": not active_window,
            "active_windows": job.active_windows,
            "alerts": [asdict(alert) for alert in alerts],
            "sent": False,
            "send_result": None,
            "message": "",
            "source_count": current.get("source_count", 0),
            "source_disagreement": current.get("source_disagreement", False),
            "provider_failures": current.get("provider_failures", []),
        }

        if previous is None:
            result["message"] = f"{location.name} -> {target.name}：首次轮询只建立天气基准。"
            self._record_job_state(job_state, "SUCCESS", result["message"], trigger="interval")
        elif quiet and active_alerts and not job.allow_quiet_send:
            job_state["suppressed_alerts"] = [asdict(alert) for alert in active_alerts]
            result["message"] = f"{location.name} -> {target.name}：夜间免打扰，已记录变化但未发送。"
            self._record_job_state(job_state, "SKIPPED", result["message"], trigger="interval")
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
                    future_hours=config.monitor.future_hours,
                )
                busy_result = self._busy_skip_result(
                    config=config,
                    job=job,
                    location=location,
                    target=target,
                    message=message,
                    trigger="interval_alert",
                    job_state=job_state,
                    real_send=real_send,
                    busy=self._busy_check(config),
                )
                if busy_result is not None:
                    result.update(busy_result)
                    job_state["last_snapshot"] = current
                    job_state["last_check_at"] = result["checked_at"]
                    job_state["last_result"] = result["message"]
                    job_state["recent_checks"] = self._append_limited(
                        job_state.get("recent_checks", []),
                        {
                            "checked_at": result["checked_at"],
                            "type": result["type"],
                            "alerts": [alert.key for alert in pending],
                            "sent": False,
                            "quiet": result.get("quiet", False),
                            "active_window": result.get("active_window", True),
                            "outside_active_window": result.get("outside_active_window", False),
                            "busy": busy_result.get("busy"),
                            "source_count": result["source_count"],
                            "source_disagreement": result["source_disagreement"],
                        },
                        config.monitor.daily_history_limit,
                    )
                    return result
                send_result: SendResult | None
                if real_send and config.monitor.require_readiness_for_auto_send:
                    from .readiness import check_readiness

                    readiness = check_readiness(require_wechat=True).to_dict()
                    result["readiness"] = readiness
                    if not readiness.get("can_send_now"):
                        detail = (
                            f"{location.name} -> {target.name}: interval alert is waiting for a usable "
                            f"desktop/WeChat session. status={readiness.get('status')}"
                        )
                        send_result = self._blocked_send_result(
                            config,
                            target,
                            message,
                            detail,
                            str(readiness.get("status") or "readiness_blocked"),
                            retryable=bool(readiness.get("can_retry_later")),
                        )
                        result["ok"] = True
                        result["sent"] = False
                        result["will_retry"] = bool(readiness.get("can_retry_later"))
                        result["blocked_reason"] = readiness.get("status")
                        result["send_result"] = asdict(send_result)
                        result["message"] = detail
                        self._record_job_state(
                            job_state,
                            "SKIPPED",
                            detail,
                            trigger="interval",
                            readiness=readiness,
                        )
                        send_result = None
                    else:
                        self._record_job_state(job_state, "SENDING", message, trigger="interval")
                        send_result, batch = self._send_single_with_batch(
                            config,
                            location,
                            target,
                            message,
                            real_send=real_send,
                            trigger="interval_alert",
                        )
                        result["batch"] = batch
                else:
                    self._record_job_state(job_state, "SENDING", message, trigger="interval")
                    send_result, batch = self._send_single_with_batch(
                        config,
                        location,
                        target,
                        message,
                        real_send=real_send,
                        trigger="interval_alert",
                    )
                    result["batch"] = batch

                if send_result is not None:
                    result["ok"] = send_result.ok
                    result["sent"] = bool(real_send and send_result.ok)
                    result["send_result"] = asdict(send_result)
                    result["message"] = message
                    self._record_job_state(
                        job_state,
                        "SUCCESS" if send_result.ok else "FAILED",
                        send_result.detail,
                        trigger="interval",
                        batch_id=(result.get("batch") or {}).get("batch_id"),
                    )
                if send_result is not None and send_result.ok:
                    if real_send:
                        sent_today.update(alert.key for alert in pending)
                        job_state["suppressed_alerts"] = []
                    job_state["recent_sends"] = self._append_limited(
                        job_state.get("recent_sends", []),
                        {
                            "sent_at": result["checked_at"],
                            "type": "alert",
                            "dry_run": not real_send,
                            "alerts": [alert.key for alert in pending],
                            "ok": send_result.ok,
                            "delivered": bool(real_send and send_result.ok),
                        },
                        config.monitor.daily_history_limit,
                    )
            else:
                result["message"] = f"{location.name} -> {target.name}：没有达到补发条件。"
                self._record_job_state(job_state, "SUCCESS", result["message"], trigger="interval")

        job_state["last_snapshot"] = current
        job_state["last_check_at"] = result["checked_at"]
        job_state["last_result"] = result["message"]
        sent_by_day[day_key] = sorted(sent_today)
        job_state["recent_checks"] = self._append_limited(
            job_state.get("recent_checks", []),
            {
                "checked_at": result["checked_at"],
                "type": result["type"],
                "alerts": [alert["key"] for alert in result["alerts"]],
                "sent": result["sent"],
                "quiet": result["quiet"],
                "active_window": result["active_window"],
                "outside_active_window": result["outside_active_window"],
                "source_count": result["source_count"],
                "source_disagreement": result["source_disagreement"],
            },
            config.monitor.daily_history_limit,
        )
        return result

    def _send_fixed_weather(
        self,
        config: AppConfig,
        job: AutomationJobConfig,
        fixed_entry: dict[str, Any],
        state: dict[str, Any],
        real_send: bool,
    ) -> dict[str, Any]:
        location = config.location_by_id(job.location_id)
        target = config.wechat_target_by_id(job.wechat_target_id)
        now = _now()
        job_state = state["jobs"].setdefault(job.id, {})
        fixed_time = str(fixed_entry["fixed_time"])
        key = str(fixed_entry["key"])
        from .run_trace import append_step, new_run_id

        run_id = new_run_id("fixed")
        self._record_job_state(
            job_state,
            "PREPARING",
            f"{location.name} -> {target.name}: fixed send {fixed_time} is preparing.",
            trigger="fixed_weather",
            run_id=run_id,
        )
        append_step(
            run_id,
            "start",
            "running",
            f"固定发送 {fixed_time}: {location.name} -> {target.name}",
            job_id=job.id,
            run_type="fixed_weather",
            detail={"fixed_key": key, "real_send": real_send},
        )
        active_window = _is_active_window(now, job.active_windows)
        fixed_sent_keys = set(job_state.get("fixed_sent_keys", []))
        fixed_pending = job_state.setdefault("fixed_pending", {})
        pending_item = fixed_pending.setdefault(
            key,
            {
                "job_id": job.id,
                "type": "fixed_weather",
                "fixed_time": fixed_time,
                "due_at": fixed_entry.get("due_at"),
                "deadline_at": fixed_entry.get("deadline_at"),
                "status": "pending",
                "blocked_reason": None,
                "attempt_count": 0,
                "last_attempt_at": None,
                "sent_at": None,
            },
        )
        checked_at = now.isoformat(timespec="seconds")
        pending_item["attempt_count"] = int(pending_item.get("attempt_count") or 0) + 1
        pending_item["last_attempt_at"] = checked_at
        retry_after_at = _safe_datetime(pending_item.get("retry_after_at"))
        result: dict[str, Any] = {
            "ok": True,
            "type": "fixed_weather",
            "job_id": job.id,
            "location": asdict(location),
            "wechat_target": asdict(target),
            "fixed_time": fixed_time,
            "fixed_key": key,
            "due_at": fixed_entry.get("due_at"),
            "deadline_at": fixed_entry.get("deadline_at"),
            "checked_at": checked_at,
            "dry_run": not real_send,
            "quiet": not active_window,
            "active_window": active_window,
            "outside_active_window": not active_window,
            "active_windows": job.active_windows,
            "sent": False,
            "send_result": None,
            "message": "",
            "run_id": run_id,
        }

        if real_send and retry_after_at is not None and now < retry_after_at:
            result["message"] = (
                f"{location.name} -> {target.name}: fixed send {fixed_time} is delayed "
                f"because the user is busy until {retry_after_at.isoformat(timespec='seconds')}."
            )
            pending_item["status"] = "waiting_user_idle"
            self._record_job_state(
                job_state,
                "WAITING_USER_IDLE",
                result["message"],
                trigger="fixed_weather",
                run_id=run_id,
                retry_after_at=retry_after_at.isoformat(timespec="seconds"),
            )
            job_state["fixed_pending"] = fixed_pending
            job_state["last_result"] = result["message"]
            return result

        if real_send and config.monitor.require_readiness_for_auto_send:
            from .readiness import check_readiness

            readiness = check_readiness(require_wechat=True).to_dict()
            result["readiness"] = readiness
            if not readiness.get("can_send_now"):
                blocked_reason = str(readiness.get("status") or "blocked")
                pending_item["status"] = "waiting_for_ready"
                pending_item["blocked_reason"] = blocked_reason
                result.update(
                    {
                        "sent": False,
                        "will_retry": True,
                        "blocked_reason": blocked_reason,
                        "message": (
                            f"{location.name} -> {target.name}: fixed send {fixed_time} is waiting "
                            f"for a usable desktop/WeChat session before {fixed_entry.get('deadline_at')}."
                        ),
                    }
                )
                append_step(
                    run_id,
                    "readiness",
                    "blocked",
                    result["message"],
                    job_id=job.id,
                    run_type="fixed_weather",
                    detail=readiness,
                )
                self._record_job_state(
                    job_state,
                    "SKIPPED",
                    result["message"],
                    trigger="fixed_weather",
                    run_id=run_id,
                    readiness=readiness,
                )
                job_state["fixed_pending"] = fixed_pending
                job_state["last_result"] = result["message"]
                return result
            append_step(
                run_id,
                "readiness",
                "ok",
                "固定发送前检查通过。",
                job_id=job.id,
                run_type="fixed_weather",
                detail=readiness,
            )

        self._record_job_state(
            job_state,
            "FETCHING_WEATHER",
            f"{location.name} -> {target.name}: fetching fixed weather.",
            trigger="fixed_weather",
            run_id=run_id,
        )
        snapshot = self._job_weather_snapshot(config, location)
        append_step(
            run_id,
            "weather",
            "ok",
            "固定发送天气数据获取完成。",
            job_id=job.id,
            run_type="fixed_weather",
            detail={"location": location.name},
        )
        message = build_weather_message_from_snapshot(
            snapshot,
            daily_prefix=config.message.daily_prefix,
            daily_style=config.message.daily_style,
        )
        decision = choose_reminder_decision(
            snapshot,
            config.reminder_policy,
            full_message=message,
            previous_snapshot=job_state.get("last_snapshot"),
        )
        result["reminder_policy"] = decision.to_dict()
        if not decision.should_send:
            policy_result = self._policy_skip_result(
                config=config,
                job=job,
                location=location,
                target=target,
                trigger="fixed_weather",
                job_state=job_state,
                decision=decision,
                real_send=real_send,
            )
            fixed_sent_keys.add(key)
            fixed_pending.pop(key, None)
            job_state["fixed_sent_keys"] = sorted(fixed_sent_keys)
            job_state["fixed_pending"] = fixed_pending
            job_state["last_snapshot"] = snapshot
            job_state["last_result"] = policy_result["message"]
            job_state["recent_sends"] = self._append_limited(
                job_state.get("recent_sends", []),
                {
                    "sent_at": policy_result["checked_at"],
                    "type": "fixed_weather",
                    "fixed_time": fixed_time,
                    "dry_run": not real_send,
                    "ok": True,
                    "delivered": False,
                    "skipped": True,
                    "reason": decision.reason,
                },
                config.monitor.daily_history_limit,
            )
            result.update(policy_result)
            return result
        message = decision.message or message
        busy = self._busy_check(config)
        due_at = _safe_datetime(pending_item.get("due_at"))
        if (
            real_send
            and busy.busy
            and busy.action == "delay"
            and config.do_not_disturb.skip_if_still_busy
            and due_at is not None
            and (now - due_at).total_seconds() >= config.do_not_disturb.max_delay_minutes * 60
        ):
            busy = BusyCheckResult(
                busy=True,
                reason=busy.reason,
                action="skip",
                delay_minutes=busy.delay_minutes,
                max_delay_minutes=busy.max_delay_minutes,
                process_name=busy.process_name,
                fullscreen=busy.fullscreen,
                matched_keyword=busy.matched_keyword,
                detail="忙碌状态持续超过最大延迟时间，本次自动发送已跳过。",
            )
        busy_result = self._busy_skip_result(
            config=config,
            job=job,
            location=location,
            target=target,
            message=message,
            trigger="fixed_weather",
            job_state=job_state,
            real_send=real_send,
            busy=busy,
        )
        if busy_result is not None:
            pending_item["status"] = str(busy_result.get("status") or "DELAYED_BUSY").lower()
            pending_item["blocked_reason"] = (busy_result.get("busy") or {}).get("reason")
            if busy_result.get("retry_after_at"):
                pending_item["retry_after_at"] = busy_result["retry_after_at"]
            job_state["fixed_pending"] = fixed_pending
            job_state["last_snapshot"] = snapshot
            job_state["last_result"] = busy_result["message"]
            result.update(busy_result)
            return result
        self._record_job_state(
            job_state,
            "SENDING",
            message,
            trigger="fixed_weather",
            run_id=run_id,
        )
        send_result, batch = self._send_single_with_batch(
            config,
            location,
            target,
            message,
            real_send=real_send,
            trigger="fixed_weather",
        )
        result["batch"] = batch
        result["ok"] = send_result.ok
        result["sent"] = bool(real_send and send_result.ok)
        result["send_result"] = asdict(send_result)
        result["message"] = message
        append_step(
            run_id,
            "wechat_send" if real_send else "dry_run",
            "ok" if send_result.ok else "failed",
            send_result.detail,
            job_id=job.id,
            run_type="fixed_weather",
            detail={"error_analysis": send_result.error_analysis},
        )
        job_state["last_snapshot"] = snapshot
        job_state["recent_sends"] = self._append_limited(
            job_state.get("recent_sends", []),
            {
                "sent_at": result["checked_at"],
                "type": "fixed_weather",
                "fixed_time": fixed_time,
                "dry_run": not real_send,
                "ok": send_result.ok,
                "delivered": bool(real_send and send_result.ok),
                "detail": send_result.detail,
                "error_analysis": send_result.error_analysis,
            },
            config.monitor.daily_history_limit,
        )
        if send_result.ok:
            fixed_sent_keys.add(key)
            fixed_pending.pop(key, None)
            self._record_job_state(
                job_state,
                "SUCCESS",
                send_result.detail,
                trigger="fixed_weather",
                run_id=run_id,
                batch_id=batch.get("batch_id"),
            )
        else:
            pending_item["status"] = "failed_waiting_for_retry"
            pending_item["blocked_reason"] = send_result.error_analysis.get("category")
            self._record_job_state(
                job_state,
                "FAILED",
                send_result.detail,
                trigger="fixed_weather",
                run_id=run_id,
                batch_id=batch.get("batch_id"),
            )
        job_state["fixed_sent_keys"] = sorted(fixed_sent_keys)
        job_state["fixed_pending"] = fixed_pending
        job_state["last_result"] = result["message"]
        return result

    def _expire_fixed_weather(
        self,
        config: AppConfig,
        job: AutomationJobConfig,
        fixed_entry: dict[str, Any],
        state: dict[str, Any],
        real_send: bool,
    ) -> dict[str, Any]:
        location = config.location_by_id(job.location_id)
        target = config.wechat_target_by_id(job.wechat_target_id)
        job_state = state["jobs"].setdefault(job.id, {})
        key = str(fixed_entry["key"])
        from .run_trace import append_step, new_run_id

        run_id = new_run_id("expired")
        expired = set(job_state.get("fixed_expired_keys", []))
        expired.add(key)
        pending = job_state.get("fixed_pending", {})
        if isinstance(pending, dict):
            pending.pop(key, None)
            job_state["fixed_pending"] = pending
        job_state["fixed_expired_keys"] = sorted(expired)
        checked_at = _now().isoformat(timespec="seconds")
        message = (
            f"{location.name} -> {target.name}: fixed send {fixed_entry['fixed_time']} expired "
            f"after compensation deadline {fixed_entry.get('deadline_at')}."
        )
        append_step(
            run_id,
            "expired",
            "expired",
            message,
            job_id=job.id,
            run_type="fixed_weather_expired",
            detail={"fixed_key": key, "real_send": real_send},
        )
        job_state["last_result"] = message
        return {
            "ok": True,
            "type": "fixed_weather_expired",
            "job_id": job.id,
            "location": asdict(location),
            "wechat_target": asdict(target),
            "fixed_time": fixed_entry["fixed_time"],
            "fixed_key": key,
            "due_at": fixed_entry.get("due_at"),
            "deadline_at": fixed_entry.get("deadline_at"),
            "checked_at": checked_at,
            "dry_run": not real_send,
            "sent": False,
            "send_result": None,
            "message": message,
            "run_id": run_id,
        }
