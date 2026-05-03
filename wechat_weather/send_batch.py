# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from .config import AppConfig, LocationConfig, WechatTargetConfig, user_data_dir
from .wechat import SendResult


DEFAULT_HISTORY_LIMIT = 500
DEFAULT_LOCK_STALE_SECONDS = 15 * 60


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def message_hash(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def new_batch_id(trigger: str = "manual") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{trigger}-{uuid4().hex[:8]}"


def send_history_path() -> Path:
    return user_data_dir() / "history" / "send_history.jsonl"


def send_task_lock_path() -> Path:
    return user_data_dir() / "locks" / "send_task.lock"


@dataclass(frozen=True)
class SendTarget:
    id: str
    name: str
    type: str = "friend"
    enabled: bool = True
    remark: str = ""
    send_mode: str = "normal"
    send_interval_seconds: int = 3


@dataclass
class TargetSendAttempt:
    target_id: str
    target_name: str
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    delivered: bool = False
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class SendBatch:
    batch_id: str
    trigger: str
    location_id: str
    location_name: str
    message_hash: str
    real_send: bool
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    targets: list[TargetSendAttempt] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        total = len(self.targets)
        success = sum(1 for item in self.targets if item.status == "success")
        failed = sum(1 for item in self.targets if item.status == "failed")
        skipped = sum(1 for item in self.targets if item.status == "skipped")
        pending = sum(1 for item in self.targets if item.status == "pending")
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "pending": pending,
            "partial_success": success > 0 and failed > 0,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["summary"] = self.summary()
        return payload


def target_from_config(target: WechatTargetConfig) -> SendTarget:
    return SendTarget(
        id=target.id,
        name=target.name,
        type=target.type,
        enabled=target.enabled,
        remark=target.remark,
        send_mode=target.send_mode,
        send_interval_seconds=target.send_interval_seconds,
    )


def select_send_targets(
    config: AppConfig,
    values: list[str] | None = None,
    *,
    send_all_enabled: bool = False,
) -> list[WechatTargetConfig]:
    if send_all_enabled:
        return [target for target in config.wechat_targets if target.enabled]
    if not values:
        return [config.default_wechat_target]

    selected: list[WechatTargetConfig] = []
    seen: set[str] = set()
    for value in values:
        target = config.wechat_target_by_id(value)
        if target.id in seen:
            continue
        seen.add(target.id)
        if target.enabled:
            selected.append(target)
    return selected


def create_send_batch(
    *,
    trigger: str,
    location: LocationConfig,
    message: str,
    targets: list[WechatTargetConfig],
    real_send: bool,
) -> SendBatch:
    batch = SendBatch(
        batch_id=new_batch_id(trigger),
        trigger=trigger,
        location_id=location.id,
        location_name=location.name,
        message_hash=message_hash(message),
        real_send=real_send,
        status="pending",
        targets=[
            TargetSendAttempt(
                target_id=target.id,
                target_name=target.name,
                status="pending",
            )
            for target in targets
        ],
    )
    return batch


def apply_send_result(
    attempt: TargetSendAttempt,
    result: SendResult,
    *,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    real_send: bool,
) -> None:
    category = None
    if isinstance(result.error_analysis, dict):
        category = result.error_analysis.get("category")
    attempt.started_at = started_at
    attempt.finished_at = finished_at
    attempt.duration_ms = duration_ms
    attempt.status = "success" if result.ok else "failed"
    attempt.delivered = bool(real_send and result.ok)
    attempt.error_code = None if result.ok else str(category or "UNKNOWN_WECHAT_ERROR")
    attempt.error_message = None if result.ok else result.detail
    attempt.diagnostics = list(result.diagnostics or [])


def append_send_history(batch: SendBatch, *, path: Path | None = None, limit: int = DEFAULT_HISTORY_LIMIT) -> Path:
    history_path = path or send_history_path()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    rows = read_send_history(limit=limit - 1, path=history_path)
    rows.append(batch.to_dict())
    history_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows[-limit:]),
        encoding="utf-8",
    )
    return history_path


def read_send_history(*, limit: int = 50, path: Path | None = None) -> list[dict[str, Any]]:
    history_path = path or send_history_path()
    if not history_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:] if limit > 0 else rows


class SendTaskLock:
    def __init__(
        self,
        path: Path | None = None,
        *,
        owner: str | None = None,
        stale_seconds: int = DEFAULT_LOCK_STALE_SECONDS,
    ) -> None:
        self.path = path or send_task_lock_path()
        self.owner = owner or f"{os.getpid()}-{uuid4().hex[:8]}"
        self.stale_seconds = stale_seconds
        self.acquired = False

    def _is_stale(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            created = float(payload.get("created_monotonic", 0))
        except Exception:
            created = 0
        if created <= 0:
            try:
                age = time.time() - self.path.stat().st_mtime
            except OSError:
                return True
            return age > self.stale_seconds
        return time.monotonic() - created > self.stale_seconds

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self._is_stale():
            try:
                self.path.unlink()
            except OSError:
                pass
        payload = {
            "owner": self.owner,
            "pid": os.getpid(),
            "created_at": _now_iso(),
            "created_monotonic": time.monotonic(),
        }
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        self.acquired = True
        return True

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("owner") != self.owner:
                return
        except Exception:
            pass
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False

    def __enter__(self) -> "SendTaskLock":
        if not self.acquire():
            raise RuntimeError("send task is already running")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
