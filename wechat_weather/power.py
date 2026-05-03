# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import re
import subprocess
import sys
from typing import Any


@dataclass(frozen=True)
class PowerStatus:
    ok: bool
    ac_line_status: str
    active_scheme: str
    monitor_timeout_ac_minutes: int | None
    standby_timeout_ac_minutes: int | None
    recommended: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "ac_line_status": self.ac_line_status,
            "active_scheme": self.active_scheme,
            "monitor_timeout_ac_minutes": self.monitor_timeout_ac_minutes,
            "standby_timeout_ac_minutes": self.standby_timeout_ac_minutes,
            "recommended": self.recommended,
            "notes": self.notes,
        }


def _run_powercfg(args: list[str]) -> str:
    completed = subprocess.run(
        ["powercfg", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (completed.stdout or "") + (completed.stderr or "")


def _active_scheme() -> str:
    if not sys.platform.startswith("win"):
        return "not windows"
    output = _run_powercfg(["/getactivescheme"])
    return " ".join(output.split())


def _power_setting_minutes(subgroup: str, setting: str) -> int | None:
    if not sys.platform.startswith("win"):
        return None
    output = _run_powercfg(["/query", "SCHEME_CURRENT", subgroup, setting])
    matches = re.findall(r"0x([0-9a-fA-F]+)", output)
    if not matches:
        return None
    try:
        # The query output includes many GUID fragments before the AC/DC values.
        # The last two numeric indexes are normally AC and DC; prefer AC.
        seconds = int(matches[-2] if len(matches) >= 2 else matches[-1], 16)
        return seconds // 60
    except Exception:
        return None


def _ac_line_status() -> str:
    if not sys.platform.startswith("win"):
        return "unknown"

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_ubyte),
            ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte),
            ("SystemStatusFlag", ctypes.c_ubyte),
            ("BatteryLifeTime", ctypes.c_ulong),
            ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    status = SYSTEM_POWER_STATUS()
    try:
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            if status.ACLineStatus == 1:
                return "plugged"
            if status.ACLineStatus == 0:
                return "battery"
    except Exception:
        pass
    return "unknown"


def get_power_status() -> dict[str, Any]:
    monitor_ac = _power_setting_minutes("SUB_VIDEO", "VIDEOIDLE")
    standby_ac = _power_setting_minutes("SUB_SLEEP", "STANDBYIDLE")
    notes: list[str] = []
    if monitor_ac is None:
        notes.append("Unable to read AC display timeout.")
    elif monitor_ac == 0:
        notes.append("The display never turns off on AC power.")
    elif monitor_ac > 15:
        notes.append("Display timeout is longer than the recommended 5-15 minutes.")

    if standby_ac is None:
        notes.append("Unable to read AC sleep timeout.")
    elif standby_ac != 0:
        notes.append("AC sleep is enabled. WeChat automation stops when the PC sleeps.")

    recommended = standby_ac == 0 and monitor_ac is not None and 0 < monitor_ac <= 15
    return PowerStatus(
        ok=True,
        ac_line_status=_ac_line_status(),
        active_scheme=_active_scheme(),
        monitor_timeout_ac_minutes=monitor_ac,
        standby_timeout_ac_minutes=standby_ac,
        recommended=recommended,
        notes=notes,
    ).to_dict()


def apply_ac_power_profile(monitor_timeout_minutes: int = 5) -> dict[str, Any]:
    if not sys.platform.startswith("win"):
        return {"ok": False, "error": "Power profile changes are only supported on Windows."}
    monitor_timeout_minutes = max(1, min(int(monitor_timeout_minutes), 60))
    commands = [
        ["powercfg", "/change", "monitor-timeout-ac", str(monitor_timeout_minutes)],
        ["powercfg", "/change", "standby-timeout-ac", "0"],
    ]
    results = []
    ok = True
    for command in commands:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        item = {
            "command": " ".join(command),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        results.append(item)
        ok = ok and completed.returncode == 0
    return {"ok": ok, "results": results, "status": get_power_status()}

