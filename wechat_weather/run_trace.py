# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
import json
from pathlib import Path
import threading
import uuid
from typing import Any

from .config import user_data_dir


_LOCK = threading.Lock()
TRACE_LIMIT = 5000


@dataclass(frozen=True)
class TraceStep:
    run_id: str
    job_id: str | None
    run_type: str
    step: str
    status: str
    summary: str
    detail: dict[str, Any]
    created_at: str


def trace_path() -> Path:
    return user_data_dir() / "run_traces.jsonl"


def new_run_id(prefix: str = "run") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def append_step(
    run_id: str,
    step: str,
    status: str,
    summary: str,
    *,
    job_id: str | None = None,
    run_type: str = "manual",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = TraceStep(
        run_id=run_id,
        job_id=job_id,
        run_type=run_type,
        step=step,
        status=status,
        summary=summary,
        detail=detail or {},
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    path = trace_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        lines: list[str] = []
        if path.exists():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        lines.append(json.dumps(asdict(item), ensure_ascii=False))
        if len(lines) > TRACE_LIMIT:
            lines = lines[-TRACE_LIMIT:]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return asdict(item)


def read_steps(limit: int = 200, run_id: str | None = None) -> list[dict[str, Any]]:
    path = trace_path()
    if not path.exists():
        return []
    result: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if run_id and item.get("run_id") != run_id:
            continue
        result.append(item)
    return result[-max(1, min(int(limit), TRACE_LIMIT)) :]


def read_runs(limit: int = 50) -> list[dict[str, Any]]:
    steps = read_steps(limit=TRACE_LIMIT)
    grouped: dict[str, dict[str, Any]] = {}
    for step in steps:
        run_id = str(step.get("run_id") or "")
        if not run_id:
            continue
        item = grouped.setdefault(
            run_id,
            {
                "run_id": run_id,
                "job_id": step.get("job_id"),
                "run_type": step.get("run_type"),
                "started_at": step.get("created_at"),
                "ended_at": step.get("created_at"),
                "status": step.get("status"),
                "summary": step.get("summary"),
                "step_count": 0,
            },
        )
        item["ended_at"] = step.get("created_at")
        item["status"] = step.get("status")
        item["summary"] = step.get("summary")
        item["step_count"] = int(item.get("step_count") or 0) + 1
    return list(grouped.values())[-max(1, min(int(limit), 200)) :]

