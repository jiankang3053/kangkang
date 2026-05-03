# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Any

from .config import default_user_config_path


STARTUP_TASK = "KangkangWeather-Startup"
MONITOR_TASK = "KangkangWeather-MonitorDue"


@dataclass(frozen=True)
class TaskStatus:
    name: str
    exists: bool
    raw: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "exists": self.exists, "raw": self.raw, "error": self.error}


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _query_task(name: str) -> TaskStatus:
    if not sys.platform.startswith("win"):
        return TaskStatus(name=name, exists=False, error="not windows")
    completed = _run(["schtasks", "/Query", "/TN", name, "/FO", "LIST", "/V"])
    raw = (completed.stdout or "") + (completed.stderr or "")
    return TaskStatus(name=name, exists=completed.returncode == 0, raw=raw, error="" if completed.returncode == 0 else raw)


def scheduler_status() -> dict[str, Any]:
    tasks = [_query_task(STARTUP_TASK), _query_task(MONITOR_TASK)]
    return {
        "ok": all(item.exists for item in tasks),
        "tasks": [item.to_dict() for item in tasks],
        "recommended": {
            "logon_type": "InteractiveToken",
            "run_level": "LeastPrivilege",
            "mode": "run only when current user is logged on",
        },
    }


def _python_command(subcommand: str, config_path: Path) -> str:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        return f'"{exe}" {subcommand} --config "{config_path}"'
    return f'"{sys.executable}" -m wechat_weather.cli {subcommand} --config "{config_path}"'


def repair_scheduler_tasks(config_path: str | None = None) -> dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {"ok": False, "error": "Task Scheduler repair is only supported on Windows."}
    config = Path(config_path) if config_path else default_user_config_path()
    startup_cmd = _python_command("tray", config)
    monitor_cmd = _python_command("monitor-run-due", config)
    commands = [
        [
            "schtasks",
            "/Create",
            "/TN",
            STARTUP_TASK,
            "/SC",
            "ONLOGON",
            "/TR",
            startup_cmd,
            "/RL",
            "LIMITED",
            "/IT",
            "/F",
        ],
        [
            "schtasks",
            "/Create",
            "/TN",
            MONITOR_TASK,
            "/SC",
            "MINUTE",
            "/MO",
            "1",
            "/TR",
            monitor_cmd,
            "/RL",
            "LIMITED",
            "/IT",
            "/F",
        ],
    ]
    results = []
    ok = True
    for command in commands:
        completed = _run(command)
        raw = (completed.stdout or "") + (completed.stderr or "")
        results.append({"command": " ".join(command), "returncode": completed.returncode, "output": raw})
        ok = ok and completed.returncode == 0
    return {"ok": ok, "results": results, "status": scheduler_status()}


def remove_scheduler_tasks() -> dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {"ok": False, "error": "Task Scheduler is only supported on Windows."}
    results = []
    ok = True
    for name in [STARTUP_TASK, MONITOR_TASK]:
        completed = _run(["schtasks", "/Delete", "/TN", name, "/F"])
        raw = (completed.stdout or "") + (completed.stderr or "")
        exists_after = _query_task(name).exists
        success = completed.returncode == 0 or not exists_after
        ok = ok and success
        results.append({"task": name, "returncode": completed.returncode, "output": raw, "removed": not exists_after})
    return {"ok": ok, "results": results}

