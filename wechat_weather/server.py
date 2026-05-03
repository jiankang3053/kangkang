# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from .config import (
    active_windows_from_quiet,
    load_config,
    normalize_active_windows,
    normalize_alert_options,
    normalize_do_not_disturb,
    normalize_fixed_times,
    normalize_reminder_policy,
    normalize_startup,
    normalize_tray,
    read_config_data,
    write_config_data,
)
from .busy_detector import BusyDetector
from .compat import build_compat_report, export_diagnostics_package
from .error_analysis import analyze_error
from .monitor import WeatherMonitor
from .power import apply_ac_power_profile, get_power_status
from .readiness import check_readiness
from .regions import (
    find_region,
    normalize_region_payload,
    regions_tree,
    resolve_region_coordinates,
    search_regions,
)
from .scheduler import remove_scheduler_tasks, repair_scheduler_tasks, scheduler_status
from .send_batch import (
    SendTaskLock,
    append_send_history,
    apply_send_result,
    create_send_batch,
    read_send_history,
    select_send_targets,
)
from .startup_manager import StartupManager
from .migration import export_migration_package, inspect_migration_package
from .run_trace import append_step, new_run_id, read_runs, read_steps
from .updater import check_latest_release
from .weather import (
    build_weather_message_from_snapshot,
    build_weather_snapshot,
    read_weather_history,
    weather_status_from_snapshot,
)
from .wechat import DEFAULT_TEST_MESSAGE, SendResult, choose_sender, collect_diagnostics, open_target_chat


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>微信天气发送台</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f4;
      --ink: #171a16;
      --muted: #6d746b;
      --line: #dfe4dc;
      --accent: #1f8f4d;
      --accent-ink: #ffffff;
      --warn: #9b4d16;
      --bad: #b42318;
      --surface: #ffffff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    .shell {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      min-height: 100vh;
    }
    aside {
      border-right: 1px solid var(--line);
      padding: 28px 24px;
      background: #eef2ec;
    }
    main {
      padding: 30px clamp(22px, 4vw, 56px);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 26px;
      line-height: 1.15;
      font-weight: 700;
    }
    h2 {
      margin: 0;
      font-size: 15px;
      line-height: 1.3;
      font-weight: 700;
    }
    p {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.65;
    }
    .stack { display: grid; gap: 20px; }
    .meta {
      margin-top: 30px;
      display: grid;
      gap: 14px;
      font-size: 13px;
    }
    .meta div {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }
    .meta span:first-child { color: var(--muted); }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--line);
      padding-bottom: 20px;
      margin-bottom: 24px;
    }
    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }
    input, select {
      height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      background: var(--surface);
      color: var(--ink);
      font: inherit;
      min-width: 170px;
    }
    button {
      height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 14px;
      background: var(--surface);
      color: var(--ink);
      font: inherit;
      cursor: pointer;
      transition: background .16s ease, transform .16s ease, border-color .16s ease;
    }
    button:hover {
      transform: translateY(-1px);
      border-color: #b8c2b3;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: var(--accent-ink);
      font-weight: 700;
    }
    section {
      display: grid;
      gap: 12px;
      border-bottom: 1px solid var(--line);
      padding: 22px 0;
    }
    textarea {
      width: 100%;
      min-height: 220px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
      background: var(--surface);
      color: var(--ink);
      font: 14px/1.7 "Microsoft YaHei", "Segoe UI", sans-serif;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
      background: #fbfcfa;
      min-height: 120px;
      font: 12px/1.6 Consolas, monospace;
      color: #343a32;
    }
    .status {
      min-height: 24px;
      color: var(--muted);
      font-size: 13px;
    }
    .status.ok { color: var(--accent); }
    .status.bad { color: var(--bad); }
    .status.warn { color: var(--warn); }
    @media (max-width: 780px) {
      .shell { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      main { padding: 22px; }
      .toolbar { align-items: stretch; }
      .controls, button, input, select { width: 100%; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h1>微信天气发送台</h1>
      <p>本地运行，只控制当前电脑上的 Windows 微信。</p>
      <div class="meta">
        <div><span>默认目标</span><strong id="defaultContact">-</strong></div>
        <div><span>发送后端</span><strong>pywinauto-session</strong></div>
        <div><span>模式</span><strong>本地服务</strong></div>
      </div>
    </aside>
    <main>
      <div class="toolbar">
        <div>
          <h2>发送控制</h2>
          <p>发送前会先打开目标会话并校验标题。</p>
        </div>
        <div class="controls">
          <label>目标会话
            <input id="contact" value="湘楠">
          </label>
          <label>后端
            <select id="backend">
              <option value="pywinauto-session">pywinauto-session</option>
              <option value="pywinauto-active">pywinauto-active</option>
              <option value="wxauto">wxauto</option>
            </select>
          </label>
          <label>发送前缀
            <input id="dailyPrefix" placeholder="例如：早上好，今天出门前看一下天气：">
          </label>
          <button id="saveMessageSettings">保存前缀</button>
          <button id="refresh">刷新预览</button>
          <button class="primary" id="send">发送天气</button>
        </div>
      </div>

      <section>
        <h2>天气预览</h2>
        <textarea id="message" readonly>正在生成天气预报...</textarea>
      </section>

      <section>
        <h2>运行结果</h2>
        <div id="status" class="status">等待操作。</div>
        <pre id="result"></pre>
      </section>

      <section>
        <h2>轮询状态</h2>
        <button id="monitorCheck">立即检查一次</button>
        <pre id="monitorOutput">读取中...</pre>
      </section>

      <section>
        <h2>环境诊断</h2>
        <button id="diagnostics">刷新诊断</button>
        <pre id="diagnosticsOutput"></pre>
      </section>
    </main>
  </div>
  <script>
    const state = {
      contact: document.querySelector("#contact"),
      backend: document.querySelector("#backend"),
      dailyPrefix: document.querySelector("#dailyPrefix"),
      message: document.querySelector("#message"),
      status: document.querySelector("#status"),
      result: document.querySelector("#result"),
      monitor: document.querySelector("#monitorOutput"),
      diagnostics: document.querySelector("#diagnosticsOutput"),
      defaultContact: document.querySelector("#defaultContact")
    };

    function setStatus(text, kind = "") {
      state.status.textContent = text;
      state.status.className = `status ${kind}`;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }

    async function loadState() {
      const data = await api("/api/state");
      state.contact.value = data.contact;
      state.defaultContact.textContent = data.contact;
      state.dailyPrefix.value = data.message?.daily_prefix || "";
    }

    async function refreshPreview() {
      setStatus("正在刷新天气预览...");
      const data = await api("/api/preview");
      state.message.value = data.message;
      setStatus("预览已更新。", "ok");
    }

    async function sendWeather() {
      setStatus("正在发送到微信...");
      const data = await api("/api/send-weather", {
        method: "POST",
        body: JSON.stringify({
          contact: state.contact.value,
          backend: state.backend.value,
          real: true
        })
      });
      state.result.textContent = JSON.stringify(data, null, 2);
      setStatus(data.ok ? "发送完成。" : "发送失败，查看运行结果。", data.ok ? "ok" : "bad");
      if (data.preview) state.message.value = data.preview;
    }

    async function saveMessageSettings() {
      await api("/api/message", {
        method: "POST",
        body: JSON.stringify({
          daily_style: "segmented_brief",
          daily_prefix: state.dailyPrefix.value.trim()
        })
      });
      await refreshPreview();
      setStatus("发送前缀已保存。", "ok");
    }

    async function refreshDiagnostics() {
      state.diagnostics.textContent = "读取中...";
      const data = await api("/api/diagnostics");
      state.diagnostics.textContent = data.lines.join("\\n");
    }

    async function refreshMonitor() {
      const data = await api("/api/monitor/status");
      state.monitor.textContent = JSON.stringify(data, null, 2);
    }

    async function checkMonitor() {
      state.monitor.textContent = "检查中...";
      const data = await api("/api/monitor/check", {
        method: "POST",
        body: JSON.stringify({ real: false })
      });
      state.monitor.textContent = JSON.stringify(data, null, 2);
      setStatus("轮询 dry-run 检查完成。", "ok");
    }

    document.querySelector("#refresh").addEventListener("click", refreshPreview);
    document.querySelector("#saveMessageSettings").addEventListener("click", saveMessageSettings);
    document.querySelector("#send").addEventListener("click", sendWeather);
    document.querySelector("#diagnostics").addEventListener("click", refreshDiagnostics);
    document.querySelector("#monitorCheck").addEventListener("click", checkMonitor);

    loadState().then(refreshPreview).then(refreshMonitor).then(refreshDiagnostics).catch(error => {
      setStatus(error.message, "bad");
    });
  </script>
</body>
</html>
"""


def _index_html() -> str:
    path = Path(__file__).with_name("web_console.html")
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return INDEX_HTML


def _make_id(prefix: str, value: Any, existing: set[str]) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    base = f"{prefix}-{text}" if text else prefix
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _bool_value(data: dict[str, Any], key: str, default: bool = False) -> bool:
    if key not in data:
        return default
    value = data[key]
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _display_location(item: dict[str, Any]) -> str:
    parts = [
        item.get("name"),
        item.get("admin1"),
        item.get("country"),
    ]
    return " · ".join(str(part) for part in parts if part)


class WeatherServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        config_path: str | None,
        window_handle: int | None,
    ) -> None:
        super().__init__(server_address, WeatherRequestHandler)
        self.config_path = config_path
        self.window_handle = window_handle
        self.monitor = WeatherMonitor(config_path=config_path, window_handle=window_handle)
        self.monitor.start()

    @property
    def app_config(self):
        return load_config(self.config_path, create_user_config=self.config_path is None)

    def read_config_data(self) -> dict[str, Any]:
        return read_config_data(self.config_path, create_user_config=self.config_path is None)

    def write_config_data(self, data: dict[str, Any]) -> None:
        write_config_data(self.config_path, data)


class WeatherRequestHandler(BaseHTTPRequestHandler):
    server: WeatherServer

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        self._send_bytes(
            status,
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _load_config_data_for_write(self) -> dict[str, Any]:
        return self.server.read_config_data()

    def _save_config_data(self, data: dict[str, Any]) -> None:
        self.server.write_config_data(data)

    def _set_default(self, items: list[dict[str, Any]], item_id: str) -> None:
        for item in items:
            item["default"] = item.get("id") == item_id

    def _location_from_body(self, body: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(existing or {})
        payload.update({key: value for key, value in body.items() if value is not None})
        if existing and not any(
            key in body for key in ("name", "region_code", "address_path", "latitude", "longitude", "source")
        ):
            return payload
        if existing and "name" in body and not any(
            key in body for key in ("region_code", "address_path", "latitude", "longitude")
        ):
            payload["name"] = str(body.get("name") or existing.get("name") or "").strip()
            payload.setdefault("address_path", [payload["name"]])
            payload.setdefault("region_code", "")
            return payload
        has_coordinates = payload.get("latitude") is not None and payload.get("longitude") is not None
        if payload.get("region_code") or payload.get("address_path") or not has_coordinates:
            resolved = resolve_region_coordinates(payload)
            payload["name"] = resolved["name"]
            payload["latitude"] = resolved["latitude"]
            payload["longitude"] = resolved["longitude"]
            payload["region_code"] = resolved["region_code"]
            payload["address_path"] = resolved["address_path"]
            payload["source"] = str(body.get("source") or resolved.get("geocode_source") or payload.get("source") or "china_regions")
            return payload
        normalized = normalize_region_payload(payload)
        payload["name"] = str(payload.get("name") or normalized["name"]).strip()
        payload["region_code"] = normalized.get("region_code") or str(payload.get("region_code") or "")
        payload["address_path"] = normalized.get("address_path") or list(payload.get("address_path") or [payload["name"]])
        return payload

    def _upsert_location(self, body: dict[str, Any], item_id: str | None = None) -> dict[str, Any]:
        data = self._load_config_data_for_write()
        locations = data.setdefault("locations", [])
        existing_ids = {str(item.get("id")) for item in locations}
        if item_id is None:
            item_id = str(body.get("id") or _make_id("loc", body.get("name"), existing_ids))
            item = {"id": item_id}
            locations.append(item)
        else:
            item = next((entry for entry in locations if entry.get("id") == item_id), None)
            if item is None:
                raise KeyError(f"没有找到天气地址：{item_id}")
        location_payload = self._location_from_body(body, existing=item)
        item["name"] = str(location_payload.get("name") or "未命名地址").strip()
        item["latitude"] = float(location_payload.get("latitude", 0.0))
        item["longitude"] = float(location_payload.get("longitude", 0.0))
        item["region_code"] = str(location_payload.get("region_code") or "")
        item["address_path"] = list(location_payload.get("address_path") or [item["name"]])
        item["source"] = str(location_payload.get("source") or "manual")
        if "enabled" in body:
            item["enabled"] = _bool_value(body, "enabled", True)
        else:
            item.setdefault("enabled", True)
        item.setdefault("name", "未命名地址")
        item.setdefault("latitude", 0.0)
        item.setdefault("longitude", 0.0)
        item.setdefault("region_code", "")
        item.setdefault("address_path", [item["name"]])
        item.setdefault("source", "manual")
        item.setdefault("default", False)
        if _bool_value(body, "default", False) or len(locations) == 1:
            self._set_default(locations, item_id)
        self._save_config_data(data)
        return item

    def _delete_location(self, item_id: str) -> dict[str, Any]:
        data = self._load_config_data_for_write()
        locations = data.setdefault("locations", [])
        if len(locations) <= 1:
            raise ValueError("至少需要保留一个天气地址。")
        removed = next((item for item in locations if item.get("id") == item_id), None)
        if removed is None:
            raise KeyError(f"没有找到天气地址：{item_id}")
        data["locations"] = [item for item in locations if item.get("id") != item_id]
        if not any(item.get("default") for item in data["locations"]):
            data["locations"][0]["default"] = True
        default_location = next(item["id"] for item in data["locations"] if item.get("default"))
        for job in data.get("automation_jobs", []):
            if job.get("location_id") == item_id:
                job["location_id"] = default_location
        self._save_config_data(data)
        return removed

    def _upsert_target(self, body: dict[str, Any], item_id: str | None = None) -> dict[str, Any]:
        data = self._load_config_data_for_write()
        targets = data.setdefault("wechat_targets", [])
        existing_ids = {str(item.get("id")) for item in targets}
        if item_id is None:
            item_id = str(body.get("id") or _make_id("target", body.get("name"), existing_ids))
            item = {"id": item_id}
            targets.append(item)
        else:
            item = next((entry for entry in targets if entry.get("id") == item_id), None)
            if item is None:
                raise KeyError(f"没有找到微信好友：{item_id}")
        if "name" in body:
            item["name"] = str(body["name"]).strip()
        if "type" in body or "target_type" in body:
            item["type"] = str(body.get("type") or body.get("target_type") or "friend")
        if "enabled" in body:
            item["enabled"] = _bool_value(body, "enabled", True)
        else:
            item.setdefault("enabled", True)
        item.setdefault("name", "未命名好友")
        item.setdefault("type", "friend")
        if "remark" in body:
            item["remark"] = str(body.get("remark") or "")
        else:
            item.setdefault("remark", "")
        if "send_mode" in body:
            item["send_mode"] = str(body.get("send_mode") or "normal")
        else:
            item.setdefault("send_mode", "normal")
        if "send_interval_seconds" in body:
            item["send_interval_seconds"] = max(0, int(body.get("send_interval_seconds") or 0))
        else:
            item.setdefault("send_interval_seconds", 3)
        item.setdefault("last_send_at", None)
        item.setdefault("last_send_status", None)
        item.setdefault("last_error_code", None)
        item.setdefault("last_error_message", None)
        item.setdefault("default", False)
        if _bool_value(body, "default", False) or len(targets) == 1:
            self._set_default(targets, item_id)
        self._save_config_data(data)
        return item

    def _delete_target(self, item_id: str) -> dict[str, Any]:
        data = self._load_config_data_for_write()
        targets = data.setdefault("wechat_targets", [])
        if len(targets) <= 1:
            raise ValueError("至少需要保留一个微信好友。")
        removed = next((item for item in targets if item.get("id") == item_id), None)
        if removed is None:
            raise KeyError(f"没有找到微信好友：{item_id}")
        data["wechat_targets"] = [item for item in targets if item.get("id") != item_id]
        if not any(item.get("default") for item in data["wechat_targets"]):
            data["wechat_targets"][0]["default"] = True
        default_target = next(item["id"] for item in data["wechat_targets"] if item.get("default"))
        for job in data.get("automation_jobs", []):
            if job.get("wechat_target_id") == item_id:
                job["wechat_target_id"] = default_target
        self._save_config_data(data)
        return removed

    def _upsert_job(self, body: dict[str, Any], item_id: str | None = None) -> dict[str, Any]:
        data = self._load_config_data_for_write()
        jobs = data.setdefault("automation_jobs", [])
        existing_ids = {str(item.get("id")) for item in jobs}
        if item_id is None:
            item_id = str(body.get("id") or _make_id("job", len(jobs) + 1, existing_ids))
            item = {"id": item_id}
            jobs.append(item)
        else:
            item = next((entry for entry in jobs if entry.get("id") == item_id), None)
            if item is None:
                raise KeyError(f"没有找到自动化任务：{item_id}")
        config = self.server.app_config
        if "location_id" in body:
            config.location_by_id(str(body["location_id"]))
            item["location_id"] = str(body["location_id"])
        if "wechat_target_id" in body:
            config.wechat_target_by_id(str(body["wechat_target_id"]))
            item["wechat_target_id"] = str(body["wechat_target_id"])
        item.setdefault("location_id", config.default_location.id)
        item.setdefault("wechat_target_id", config.default_wechat_target.id)
        if "enabled" in body:
            item["enabled"] = _bool_value(body, "enabled", True)
        else:
            item.setdefault("enabled", True)
        if "interval_minutes" in body:
            item["interval_minutes"] = max(1, int(body["interval_minutes"]))
        else:
            item.setdefault("interval_minutes", config.monitor.interval_minutes)
        if "fixed_times" in body:
            item["fixed_times"] = normalize_fixed_times(body["fixed_times"])
        else:
            item.setdefault("fixed_times", [])
        if "quiet_start" in body:
            item["quiet_start"] = str(body["quiet_start"])
        else:
            item.setdefault("quiet_start", config.monitor.quiet_start)
        if "quiet_end" in body:
            item["quiet_end"] = str(body["quiet_end"])
        else:
            item.setdefault("quiet_end", config.monitor.quiet_end)
        if "allow_quiet_send" in body:
            item["allow_quiet_send"] = _bool_value(body, "allow_quiet_send", False)
        else:
            item.setdefault("allow_quiet_send", False)
        if "active_windows" in body:
            item["active_windows"] = normalize_active_windows(body["active_windows"], strict=True)
        elif any(key in body for key in ("quiet_start", "quiet_end", "allow_quiet_send")):
            item["active_windows"] = active_windows_from_quiet(
                item.get("quiet_start"),
                item.get("quiet_end"),
                bool(item.get("allow_quiet_send", False)),
            )
        else:
            item.setdefault("active_windows", active_windows_from_quiet(item.get("quiet_start"), item.get("quiet_end"), bool(item.get("allow_quiet_send", False))))
        if "alert_options" in body:
            item["alert_options"] = normalize_alert_options(body.get("alert_options"))
        else:
            item.setdefault("alert_options", normalize_alert_options(item.get("alert_options")))
        self._save_config_data(data)
        return item

    def _delete_job(self, item_id: str) -> dict[str, Any]:
        data = self._load_config_data_for_write()
        jobs = data.setdefault("automation_jobs", [])
        if len(jobs) <= 1:
            raise ValueError("至少需要保留一个自动化任务。")
        removed = next((item for item in jobs if item.get("id") == item_id), None)
        if removed is None:
            raise KeyError(f"没有找到自动化任务：{item_id}")
        data["automation_jobs"] = [item for item in jobs if item.get("id") != item_id]
        self._save_config_data(data)
        return removed

    def _save_message_config(self, body: dict[str, Any]) -> dict[str, Any]:
        data = self._load_config_data_for_write()
        message = data.setdefault("message", {})
        if "daily_style" in body:
            message["daily_style"] = str(body.get("daily_style") or "segmented_brief")
        else:
            message.setdefault("daily_style", "segmented_brief")
        if "daily_prefix" in body:
            message["daily_prefix"] = str(body.get("daily_prefix") or "").strip()
        else:
            message.setdefault("daily_prefix", "")
        self._save_config_data(data)
        return asdict(self.server.app_config.message)

    def _save_system_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        data = self._load_config_data_for_write()
        if "reminder_policy" in body:
            data["reminder_policy"] = normalize_reminder_policy(body.get("reminder_policy"))
        if "startup" in body:
            startup = normalize_startup(body.get("startup"))
            manager = StartupManager(self.server.config_path)
            try:
                if startup.get("enabled"):
                    manager.enable()
                else:
                    manager.disable()
                startup["status"] = manager.status().to_dict()
            except Exception as exc:
                startup["status"] = {
                    "ok": False,
                    "enabled": False,
                    "detail": (
                        "开机自启动设置失败，可能被系统权限或安全软件拦截。"
                        f"原始错误：{exc}"
                    ),
                    "command": manager.get_startup_command(),
                    "executable_path": manager.get_executable_path(),
                    "is_frozen": bool(getattr(sys, "frozen", False)),
                }
                startup["enabled"] = False
            data["startup"] = startup
        if "tray" in body:
            data["tray"] = normalize_tray(body.get("tray"))
        if "do_not_disturb" in body:
            data["do_not_disturb"] = normalize_do_not_disturb(body.get("do_not_disturb"))
        self._save_config_data(data)
        config = self.server.app_config
        return {
            "ok": True,
            "reminder_policy": asdict(config.reminder_policy),
            "startup": asdict(config.startup),
            "startup_status": StartupManager(self.server.config_path).status().to_dict(),
            "tray": asdict(config.tray),
            "do_not_disturb": asdict(config.do_not_disturb),
        }

    def _complete_setup(self, body: dict[str, Any]) -> dict[str, Any]:
        location = body.get("location") or {}
        target_value = body.get("wechat_target") or body.get("target") or ""
        if isinstance(target_value, dict):
            target_value = target_value.get("name") or ""
        target_name = str(target_value).strip()
        if not target_name:
            raise ValueError("请先填写微信好友或群名称。")
        resolved_location = self._location_from_body(
            {
                **location,
                "name": location.get("name") or body.get("location_name"),
                "latitude": location.get("latitude", body.get("latitude")),
                "longitude": location.get("longitude", body.get("longitude")),
                "source": location.get("source") or "setup",
            }
        )

        data = self._load_config_data_for_write()
        data.setdefault("app", {})["setup_complete"] = True
        data["locations"] = [
            {
                "id": "default-location",
                "name": resolved_location["name"],
                "latitude": float(resolved_location["latitude"]),
                "longitude": float(resolved_location["longitude"]),
                "region_code": str(resolved_location.get("region_code") or ""),
                "address_path": list(resolved_location.get("address_path") or [resolved_location["name"]]),
                "source": str(resolved_location.get("source") or "setup"),
                "enabled": True,
                "default": True,
            }
        ]
        data["wechat_targets"] = [
            {
                "id": "default-target",
                "name": target_name,
                "enabled": True,
                "default": True,
            }
        ]
        data["automation_jobs"] = [
            {
                "id": "default",
                "location_id": "default-location",
                "wechat_target_id": "default-target",
                "enabled": True,
                "interval_minutes": 120,
                "fixed_times": [],
                "active_windows": ["07:00-22:00"],
                "quiet_start": "22:00",
                "quiet_end": "07:00",
                "allow_quiet_send": False,
                "alert_options": normalize_alert_options({}),
            }
        ]
        self._save_config_data(data)
        config = self.server.app_config
        return {
            "setup_complete": config.app.setup_complete,
            "default_location": asdict(config.default_location),
            "default_wechat_target": asdict(config.default_wechat_target),
            "default_job": asdict(config.default_job),
        }

    def _apply_setup_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        location = body.get("location") or {}
        target = body.get("wechat_target") or body.get("target") or {}
        automation = body.get("automation") or {}
        target_name = target.get("name") if isinstance(target, dict) else target
        payload = {
            "location": {
                "name": location.get("name") or body.get("location_name"),
                "latitude": location.get("latitude", body.get("latitude")),
                "longitude": location.get("longitude", body.get("longitude")),
                "region_code": location.get("region_code") or body.get("region_code"),
                "address_path": location.get("address_path") or body.get("address_path"),
                "source": location.get("source") or "assisted-profile",
            },
            "wechat_target": target_name or body.get("wechat_target_name"),
        }
        result = self._complete_setup(payload)

        data = self._load_config_data_for_write()
        jobs = data.setdefault("automation_jobs", [])
        if jobs:
            job = jobs[0]
            if "interval_minutes" in automation:
                job["interval_minutes"] = max(1, int(automation.get("interval_minutes") or 120))
            if "fixed_times" in automation:
                job["fixed_times"] = normalize_fixed_times(automation.get("fixed_times"))
            if "active_windows" in automation:
                job["active_windows"] = normalize_active_windows(automation.get("active_windows"), strict=True)
            if "quiet_start" in automation:
                job["quiet_start"] = str(automation.get("quiet_start") or "22:00")
            if "quiet_end" in automation:
                job["quiet_end"] = str(automation.get("quiet_end") or "07:00")
            if "allow_quiet_send" in automation:
                job["allow_quiet_send"] = bool(automation.get("allow_quiet_send"))
            if "active_windows" not in automation and any(
                key in automation for key in ("quiet_start", "quiet_end", "allow_quiet_send")
            ):
                job["active_windows"] = active_windows_from_quiet(
                    job.get("quiet_start"),
                    job.get("quiet_end"),
                    bool(job.get("allow_quiet_send", False)),
                )
            if "alert_options" in automation:
                job["alert_options"] = normalize_alert_options(automation.get("alert_options"))
            self._save_config_data(data)
        config = self.server.app_config
        result.update(
            {
                "ok": True,
                "profile_applied": True,
                "default_location": asdict(config.default_location),
                "default_wechat_target": asdict(config.default_wechat_target),
                "default_job": asdict(config.default_job),
            }
        )
        return result

    def _send_error(self, status: int, detail: str, context: str = "server", diagnostics: list[str] | None = None) -> None:
        diagnostics = diagnostics or []
        self._send_json(
            status,
            {
                "ok": False,
                "error": detail,
                "detail": detail,
                "diagnostics": diagnostics,
                "error_analysis": analyze_error(detail, diagnostics, context=context).to_dict(),
            },
        )

    def _target_name_from_body(self, body: dict[str, Any]) -> str:
        config = self.server.app_config
        value = str(
            body.get("wechat_target")
            or body.get("wechat_target_id")
            or body.get("recipient")
            or body.get("contact")
            or config.contact
        )
        try:
            return config.wechat_target_by_id(value).name
        except KeyError:
            return value

    def _target_ids_from_body(self, body: dict[str, Any]) -> list[str] | None:
        raw = (
            body.get("wechat_target_ids")
            or body.get("target_ids")
            or body.get("targets")
        )
        if raw is None:
            single = body.get("wechat_target_id") or body.get("recipient") or body.get("contact")
            return [str(single)] if single else None
        if isinstance(raw, str):
            return [item.strip() for item in raw.replace("；", ",").split(",") if item.strip()]
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        return None

    def _update_target_send_status(
        self,
        target_id: str,
        *,
        sent_at: str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        data = self._load_config_data_for_write()
        for item in data.setdefault("wechat_targets", []):
            if str(item.get("id")) != target_id:
                continue
            item["last_send_at"] = sent_at
            item["last_send_status"] = status
            item["last_error_code"] = error_code
            item["last_error_message"] = error_message
            self._save_config_data(data)
            return

    def _readiness_block_result(
        self,
        backend: str,
        contact: str,
        preview: str = "",
    ) -> SendResult | None:
        report = check_readiness(require_wechat=True).to_dict()
        if report.get("can_send_now"):
            return None
        detail = (
            f"当前环境不能自动发送微信：{report.get('status')}。"
            "程序已停止真实发送，避免在锁屏、睡眠、权限不一致或微信不可访问时误操作。"
        )
        return SendResult(
            ok=False,
            backend=backend,
            contact=contact,
            detail=detail,
            preview=preview,
            diagnostics=[json.dumps(report, ensure_ascii=False)],
            error_analysis={
                "category": str(report.get("status") or "readiness_blocked"),
                "title": str(report.get("title") or "环境不可自动发送"),
                "summary": str(report.get("detail") or detail),
                "likely_causes": [
                    "电脑锁屏、睡眠、注销或没有可交互桌面",
                    "微信未打开、未登录或窗口不可访问",
                    "微信和本程序权限级别不一致",
                ],
                "next_steps": [
                    "保持用户登录，允许关闭屏幕但不要睡眠",
                    "打开并登录官方 Windows 微信",
                    "用普通权限同时运行微信和 KangkangWeather",
                ],
                "severity": "error",
                "retryable": bool(report.get("can_retry_later")),
            },
        )

    def _next_fixed_send_at(self, config) -> str | None:
        now = datetime.now()
        candidates: list[datetime] = []
        for job in config.automation_jobs:
            if not job.enabled:
                continue
            for fixed_time in job.fixed_times:
                try:
                    hour, minute = [int(part) for part in str(fixed_time).split(":", 1)]
                    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if candidate <= now:
                        candidate += timedelta(days=1)
                    candidates.append(candidate)
                except Exception:
                    continue
        if not candidates:
            return None
        return min(candidates).isoformat(timespec="seconds")

    def _pending_compensations(self) -> list[dict[str, Any]]:
        try:
            state = self.server.monitor._load_state()
        except Exception:
            return []
        rows: list[dict[str, Any]] = []
        jobs = state.get("jobs", {})
        if not isinstance(jobs, dict):
            return rows
        for job_id, job_state in jobs.items():
            if not isinstance(job_state, dict):
                continue
            pending = job_state.get("fixed_pending", {})
            if not isinstance(pending, dict):
                continue
            for item in pending.values():
                if not isinstance(item, dict):
                    continue
                rows.append({"job_id": job_id, **item})
        return rows[-10:]

    def _dashboard_summary(self, config) -> dict[str, Any]:
        # Keep /api/state cheap. Deep readiness checks may touch WeChat UIAutomation,
        # powercfg, or schtasks and can hang on some machines during startup.
        readiness = {
            "can_send_now": None,
            "status": "not_checked",
            "title": "点击自动发送环境检查",
        }
        power = {"recommended": None}
        sched = {"ok": None}
        try:
            monitor_status = self.server.monitor.status()
        except Exception as exc:
            monitor_status = {"enabled": False, "running": False, "error": str(exc)}
        runs = read_runs(limit=1)
        return {
            "can_send_now": readiness.get("can_send_now"),
            "readiness_status": readiness.get("status"),
            "readiness_title": readiness.get("title"),
            "power_recommended": power.get("recommended"),
            "scheduler_ok": sched.get("ok"),
            "monitor_running": bool(monitor_status.get("running")),
            "next_check_at": monitor_status.get("next_check_at"),
            "next_fixed_send_at": self._next_fixed_send_at(config),
            "pending_compensations": self._pending_compensations(),
            "last_run": runs[-1] if runs else None,
        }

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send_bytes(200, _index_html().encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/favicon.ico":
                self._send_bytes(204, b"", "image/x-icon")
            elif parsed.path == "/api/state":
                config = self.server.app_config
                self._send_json(
                    200,
                    {
                        "config_version": config.config_version,
                        "app": asdict(config.app),
                        "contact": config.contact,
                        "locations": [asdict(item) for item in config.locations],
                        "wechat_targets": [asdict(item) for item in config.wechat_targets],
                        "automation_jobs": [asdict(item) for item in config.automation_jobs],
                        "recipients": [asdict(item) for item in config.recipients],
                        "defaults": {
                            "location_id": config.default_location.id,
                            "wechat_target_id": config.default_wechat_target.id,
                            "job_id": config.default_job.id,
                        },
                        "providers": asdict(config.providers),
                        "monitor": asdict(config.monitor),
                        "message": asdict(config.message),
                        "reminder_policy": asdict(config.reminder_policy),
                        "startup": asdict(config.startup),
                        "tray": asdict(config.tray),
                        "do_not_disturb": asdict(config.do_not_disturb),
                        "startup_status": StartupManager(self.server.config_path).status().to_dict(),
                        "release": asdict(config.release),
                        "dashboard": self._dashboard_summary(config),
                    },
                )
            elif parsed.path == "/api/startup/status":
                self._send_json(200, StartupManager(self.server.config_path).status().to_dict())
            elif parsed.path == "/api/busy/status":
                config = self.server.app_config
                self._send_json(200, BusyDetector(config.do_not_disturb).should_delay_send().to_dict())
            elif parsed.path == "/api/setup/status":
                config = self.server.app_config
                self._send_json(
                    200,
                    {
                        "setup_complete": config.app.setup_complete,
                        "default_location": asdict(config.default_location),
                        "default_wechat_target": asdict(config.default_wechat_target),
                    },
                )
            elif parsed.path == "/api/regions/tree":
                self._send_json(200, {"regions": regions_tree()})
            elif parsed.path == "/api/regions/search":
                query = (parse_qs(parsed.query).get("query") or [""])[0].strip()
                limit = int((parse_qs(parsed.query).get("limit") or ["20"])[0] or "20")
                self._send_json(200, {"results": search_regions(query, limit=limit)})
            elif parsed.path == "/api/weather/history":
                limit = int((parse_qs(parsed.query).get("limit") or ["50"])[0] or "50")
                self._send_json(200, {"history": read_weather_history(limit=limit)})
            elif parsed.path == "/api/send-history":
                limit = int((parse_qs(parsed.query).get("limit") or ["50"])[0] or "50")
                self._send_json(200, {"history": read_send_history(limit=limit)})
            elif parsed.path == "/api/readiness":
                self._send_json(200, check_readiness(require_wechat=True).to_dict())
            elif parsed.path == "/api/power/status":
                self._send_json(200, get_power_status())
            elif parsed.path == "/api/scheduler/status":
                self._send_json(200, scheduler_status())
            elif parsed.path == "/api/runs/timeline":
                limit = int((parse_qs(parsed.query).get("limit") or ["50"])[0] or "50")
                self._send_json(200, {"runs": read_runs(limit=limit)})
            elif parsed.path == "/api/runs/detail":
                query = parse_qs(parsed.query)
                run_id = (query.get("run_id") or [""])[0].strip()
                limit = int((query.get("limit") or ["200"])[0] or "200")
                self._send_json(200, {"steps": read_steps(limit=limit, run_id=run_id or None)})
            elif parsed.path == "/api/update/check":
                repo = (parse_qs(parsed.query).get("repo") or ["jiankang3053/kangkang"])[0].strip()
                self._send_json(200, check_latest_release(repo=repo or "jiankang3053/kangkang"))
            elif parsed.path == "/api/locations/search":
                query = (parse_qs(parsed.query).get("query") or [""])[0].strip()
                if not query:
                    self._send_json(400, {"error": "query is required"})
                    return
                self._send_json(200, {"results": search_regions(query, limit=20), "failures": []})
            elif parsed.path == "/api/preview":
                config = self.server.app_config
                query = parse_qs(parsed.query)
                location = config.location_by_id((query.get("location_id") or [None])[0])
                target = config.wechat_target_by_id(
                    (query.get("wechat_target_id") or query.get("recipient") or query.get("contact") or [None])[0]
                )
                weather = location.weather_config(
                    timeout_seconds=config.providers.timeout_seconds,
                    language=config.providers.language,
                )
                try:
                    snapshot = build_weather_snapshot(
                        weather,
                        comparison_models=config.providers.comparison_models,
                        fallback_wttr=config.providers.fallback_wttr,
                    )
                    message = build_weather_message_from_snapshot(
                        snapshot,
                        daily_prefix=config.message.daily_prefix,
                        daily_style=config.message.daily_style,
                    )
                    weather_status = {"ok": True, **weather_status_from_snapshot(snapshot)}
                except Exception as exc:
                    message = f"天气加载失败：{exc}"
                    weather_status = {
                        "ok": False,
                        "error": str(exc),
                        "source_count": 0,
                        "failures": [str(exc)],
                        "cached": False,
                        "stale": False,
                        "elapsed_ms": None,
                    }
                self._send_json(
                    200,
                    {
                        "location": asdict(location),
                        "wechat_target": asdict(target),
                        "contact": target.name,
                        "message": message,
                        "weather_status": weather_status,
                    },
                )
            elif parsed.path == "/api/diagnostics":
                self._send_json(200, {"lines": collect_diagnostics()})
            elif parsed.path == "/api/compat/check":
                self._send_json(200, build_compat_report(self.server.config_path, self.server.server_port))
            elif parsed.path == "/api/monitor/status":
                self._send_json(200, self.server.monitor.status())
            else:
                self._send_json(404, {"error": "not found"})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
            if parsed.path == "/api/locations/detect-ip":
                response = requests.get("https://ipapi.co/json/", timeout=12)
                response.raise_for_status()
                data = response.json()
                latitude = data.get("latitude")
                longitude = data.get("longitude")
                if latitude is None or longitude is None:
                    raise RuntimeError("IP 定位没有返回经纬度。")
                name = " · ".join(
                    str(part)
                    for part in [data.get("city"), data.get("region"), data.get("country_name")]
                    if part
                )
                self._send_json(
                    200,
                    {
                        "location": {
                            "name": name or "IP 定位地址",
                            "latitude": latitude,
                            "longitude": longitude,
                            "source": "ip",
                        }
                    },
                )
                return

            if parsed.path == "/api/locations":
                self._send_json(200, {"location": self._upsert_location(body)})
                return

            if parsed.path == "/api/wechat-targets":
                self._send_json(200, {"wechat_target": self._upsert_target(body)})
                return

            if parsed.path == "/api/automation/jobs":
                self._send_json(200, {"automation_job": self._upsert_job(body)})
                return

            if parsed.path == "/api/message":
                self._send_json(200, {"message": self._save_message_config(body)})
                return

            if parsed.path == "/api/system-settings":
                self._send_json(200, self._save_system_settings(body))
                return

            if parsed.path == "/api/readiness/check":
                self._send_json(200, check_readiness(require_wechat=True).to_dict())
                return

            if parsed.path == "/api/power/apply-profile":
                minutes = int(body.get("monitor_timeout_minutes") or 5)
                self._send_json(200, apply_ac_power_profile(minutes))
                return

            if parsed.path == "/api/scheduler/repair":
                self._send_json(200, repair_scheduler_tasks(self.server.config_path))
                return

            if parsed.path == "/api/scheduler/remove-old":
                self._send_json(200, remove_scheduler_tasks())
                return

            if parsed.path == "/api/scheduler/run-once":
                result = self.server.monitor.run_due(real_send=bool(body.get("real", False)))
                self._send_json(200, result)
                return

            if parsed.path == "/api/setup/complete":
                self._send_json(200, self._complete_setup(body))
                return

            if parsed.path == "/api/setup/apply-profile":
                self._send_json(200, self._apply_setup_profile(body))
                return

            if parsed.path == "/api/diagnostics/export":
                path = export_diagnostics_package(self.server.config_path, self.server.server_port)
                self._send_json(200, {"ok": True, "path": str(path)})
                return

            if parsed.path == "/api/migration/export":
                path = export_migration_package(self.server.config_path)
                self._send_json(200, {"ok": True, "path": str(path)})
                return

            if parsed.path == "/api/migration/inspect":
                path = str(body.get("path") or "").strip()
                if not path:
                    self._send_json(400, {"ok": False, "error": "path is required"})
                    return
                self._send_json(200, inspect_migration_package(path))
                return

            if parsed.path == "/api/wechat/open-target":
                contact = self._target_name_from_body(body)
                result = open_target_chat(contact, window_handle=self.server.window_handle)
                self._send_json(200 if result.ok else 409, asdict(result))
                return

            if parsed.path == "/api/wechat/test-message":
                contact = self._target_name_from_body(body)
                message = str(body.get("message") or DEFAULT_TEST_MESSAGE).strip()
                run_id = new_run_id("test")
                append_step(
                    run_id,
                    "start",
                    "running",
                    f"准备发送测试消息到 {contact}",
                    run_type="test_message",
                    detail={"contact": contact},
                )
                if not message:
                    result = SendResult(
                        ok=False,
                        backend="pywinauto-session",
                        contact=contact,
                        detail="\u6d4b\u8bd5\u6d88\u606f\u4e0d\u80fd\u4e3a\u7a7a\u3002",
                        preview="",
                    )
                    append_step(run_id, "validate", "failed", "测试消息为空。", run_type="test_message")
                    payload = asdict(result)
                    payload["run_id"] = run_id
                    self._send_json(400, payload)
                    return
                backend = str(body.get("backend") or "pywinauto-session")
                blocked = self._readiness_block_result(backend, contact, preview=message)
                if blocked is not None:
                    append_step(
                        run_id,
                        "readiness",
                        "blocked",
                        "当前环境未通过发送前检查。",
                        run_type="test_message",
                        detail=blocked.error_analysis or {},
                    )
                    payload = asdict(blocked)
                    payload["run_id"] = run_id
                    self._send_json(409, payload)
                    return
                append_step(run_id, "readiness", "ok", "发送前检查通过。", run_type="test_message")
                sender = choose_sender(
                    real_send=True,
                    backend=backend,
                    window_handle=self.server.window_handle,
                    send_strategy=self.server.app_config.monitor.wechat_send_strategy,
                    allow_send_button_coordinate_fallback=(
                        self.server.app_config.monitor.allow_send_button_coordinate_fallback
                    ),
                )
                result = sender.send(contact, message)
                append_step(
                    run_id,
                    "wechat_send",
                    "ok" if result.ok else "failed",
                    result.detail,
                    run_type="test_message",
                    detail={"diagnostics": result.diagnostics, "error_analysis": result.error_analysis},
                )
                payload = asdict(result)
                payload["run_id"] = run_id
                self._send_json(200 if result.ok else 409, payload)
                return

            if parsed.path == "/api/monitor/check":
                real_send = bool(body.get("real", False)) and not bool(body.get("dry_run", False))
                result = self.server.monitor.check_once(
                    real_send=real_send,
                    job_id=body.get("job_id"),
                    recipient_name=body.get("recipient"),
                )
                self._send_json(200, result)
                return

            if parsed.path == "/api/monitor/pause":
                data = self._load_config_data_for_write()
                data.setdefault("monitor", {})["enabled"] = False
                self._save_config_data(data)
                self.server.monitor.stop()
                self._send_json(200, {"ok": True, "enabled": False, "message": "自动化已暂停。"})
                return

            if parsed.path == "/api/monitor/resume":
                data = self._load_config_data_for_write()
                data.setdefault("monitor", {})["enabled"] = True
                self._save_config_data(data)
                self.server.monitor.start()
                self._send_json(200, {"ok": True, "enabled": True, "message": "自动化已恢复。"})
                return

            if parsed.path != "/api/send-weather":
                self._send_json(404, {"error": "not found"})
                return

            config = self.server.app_config
            location = config.location_by_id(body.get("location_id"))
            target_values = self._target_ids_from_body(body)
            targets = select_send_targets(
                config,
                target_values,
                send_all_enabled=bool(body.get("send_all_enabled", False)),
            )
            if not targets:
                self._send_error(400, "没有启用的微信发送对象。", context="send_weather")
                return
            primary_target = targets[0]
            backend = str(body.get("backend") or "pywinauto-session")
            real = bool(body.get("real", False))
            dry_run = bool(body.get("dry_run", False)) or not real
            real = real and not dry_run
            trigger = str(body.get("trigger") or ("manual" if real else "dry_run"))
            run_id = new_run_id("weather")
            append_step(
                run_id,
                "start",
                "running",
                f"准备生成 {location.name} 天气，目标 {len(targets)} 个",
                run_type="send_weather",
                detail={
                    "location_id": location.id,
                    "wechat_target_ids": [target.id for target in targets],
                    "real": real,
                },
            )
            if real and not config.app.setup_complete:
                result = SendResult(
                    ok=False,
                    backend=backend,
                    contact=primary_target.name,
                    detail="\u9996\u6b21\u8bbe\u7f6e\u672a\u5b8c\u6210\u3002\u8bf7\u5148\u8bbe\u7f6e\u5929\u6c14\u5730\u5740\u548c\u5fae\u4fe1\u597d\u53cb/\u7fa4\u540d\u79f0\uff0c\u518d\u6267\u884c\u771f\u5b9e\u53d1\u9001\u3002",
                    preview="",
                )
                append_step(run_id, "setup", "blocked", "首次设置未完成。", run_type="send_weather")
                payload = asdict(result)
                payload["run_id"] = run_id
                self._send_json(409, payload)
                return
            weather = location.weather_config(
                timeout_seconds=config.providers.timeout_seconds,
                language=config.providers.language,
            )
            snapshot = build_weather_snapshot(
                weather,
                comparison_models=config.providers.comparison_models,
                fallback_wttr=config.providers.fallback_wttr,
            )
            append_step(
                run_id,
                "weather",
                "ok",
                "天气数据获取完成。",
                run_type="send_weather",
                detail=weather_status_from_snapshot(snapshot),
            )
            message = build_weather_message_from_snapshot(
                snapshot,
                daily_prefix=config.message.daily_prefix,
                daily_style=config.message.daily_style,
            )
            batch = create_send_batch(
                trigger=trigger,
                location=location,
                message=message,
                targets=targets,
                real_send=real,
            )
            if real:
                blocked = self._readiness_block_result(
                    backend,
                    "、".join(target.name for target in targets),
                    preview=message,
                )
                if blocked is not None:
                    append_step(
                        run_id,
                        "readiness",
                        "blocked",
                        "当前环境未通过发送前检查。",
                        run_type="send_weather",
                        detail=blocked.error_analysis or {},
                    )
                    payload = asdict(blocked)
                    payload["run_id"] = run_id
                    payload["batch"] = batch.to_dict()
                    self._send_json(409, payload)
                    return
                append_step(run_id, "readiness", "ok", "发送前检查通过。", run_type="send_weather")

            batch.started_at = datetime.now().isoformat(timespec="seconds")
            if not real:
                batch.status = "dry_run"
                batch.finished_at = batch.started_at
                for attempt in batch.targets:
                    attempt.status = "skipped"
                    attempt.started_at = batch.started_at
                    attempt.finished_at = batch.started_at
                    attempt.duration_ms = 0
                append_send_history(batch)
                result = SendResult(
                    ok=True,
                    backend=backend,
                    contact=primary_target.name,
                    detail=f"dry-run：已生成天气消息，目标 {len(targets)} 个，未调用微信发送。",
                    preview=message,
                )
                payload = asdict(result)
                payload.update(
                    {
                        "batch": batch.to_dict(),
                        "summary": batch.summary(),
                        "contacts": [target.name for target in targets],
                    }
                )
                append_step(
                    run_id,
                    "dry_run",
                    "ok",
                    result.detail,
                    run_type="send_weather",
                    detail=batch.to_dict(),
                )
                payload["run_id"] = run_id
                self._send_json(200, payload)
                return

            lock = SendTaskLock(owner=batch.batch_id)
            if not lock.acquire():
                self._send_error(
                    409,
                    "已有微信发送任务正在运行，请等待当前任务完成后再试。",
                    context="send_weather",
                    diagnostics=[f"batch_id={batch.batch_id}", f"targets={len(targets)}"],
                )
                return

            batch.status = "sending"
            last_result: SendResult | None = None
            try:
                sender = choose_sender(
                    real_send=True,
                    backend=backend,
                    window_handle=self.server.window_handle,
                    send_strategy=config.monitor.wechat_send_strategy,
                    allow_send_button_coordinate_fallback=(
                        config.monitor.allow_send_button_coordinate_fallback
                    ),
                )
                for index, (target, attempt) in enumerate(zip(targets, batch.targets)):
                    started_at = datetime.now().isoformat(timespec="seconds")
                    start = time.perf_counter()
                    append_step(
                        run_id,
                        "wechat_send",
                        "running",
                        f"发送到 {target.name}",
                        run_type="send_weather",
                        detail={"target_id": target.id, "batch_id": batch.batch_id},
                    )
                    result = sender.send(target.name, message)
                    last_result = result
                    finished_at = datetime.now().isoformat(timespec="seconds")
                    duration_ms = int((time.perf_counter() - start) * 1000)
                    apply_send_result(
                        attempt,
                        result,
                        started_at=started_at,
                        finished_at=finished_at,
                        duration_ms=duration_ms,
                        real_send=True,
                    )
                    self._update_target_send_status(
                        target.id,
                        sent_at=finished_at,
                        status=attempt.status,
                        error_code=attempt.error_code,
                        error_message=attempt.error_message,
                    )
                    append_step(
                        run_id,
                        "wechat_send",
                        "ok" if result.ok else "failed",
                        result.detail,
                        run_type="send_weather",
                        detail={
                            "target_id": target.id,
                            "batch_id": batch.batch_id,
                            "diagnostics": result.diagnostics,
                            "error_analysis": result.error_analysis,
                        },
                    )
                    if index < len(targets) - 1 and target.send_interval_seconds > 0:
                        time.sleep(target.send_interval_seconds)
            finally:
                batch.finished_at = datetime.now().isoformat(timespec="seconds")
                summary = batch.summary()
                if summary["failed"] == 0:
                    batch.status = "success"
                elif summary["success"] > 0:
                    batch.status = "partial_success"
                else:
                    batch.status = "failed"
                append_send_history(batch)
                lock.release()

            if last_result is None:
                last_result = SendResult(
                    ok=False,
                    backend=backend,
                    contact=primary_target.name,
                    detail="没有执行任何微信发送对象。",
                    preview=message,
                )
            payload = asdict(last_result)
            payload.update(
                {
                    "ok": batch.summary()["failed"] == 0,
                    "contact": primary_target.name,
                    "contacts": [target.name for target in targets],
                    "preview": message,
                    "batch": batch.to_dict(),
                    "summary": batch.summary(),
                }
            )
            payload["run_id"] = run_id
            self._send_json(200 if payload["ok"] else 409, payload)
        except Exception as exc:
            self._send_error(500, str(exc), context="server")

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
            if parsed.path == "/api/locations":
                item_id = str(body.get("id") or "")
                self._send_json(200, {"location": self._upsert_location(body, item_id=item_id)})
            elif parsed.path == "/api/wechat-targets":
                item_id = str(body.get("id") or "")
                self._send_json(200, {"wechat_target": self._upsert_target(body, item_id=item_id)})
            elif parsed.path == "/api/automation/jobs":
                item_id = str(body.get("id") or "")
                self._send_json(200, {"automation_job": self._upsert_job(body, item_id=item_id)})
            elif parsed.path == "/api/message":
                self._send_json(200, {"message": self._save_message_config(body)})
            elif parsed.path == "/api/system-settings":
                self._send_json(200, self._save_system_settings(body))
            else:
                self._send_json(404, {"error": "not found"})
        except Exception as exc:
            self._send_error(500, str(exc), context="server")

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
            item_id = str(body.get("id") or "")
            if parsed.path == "/api/locations":
                self._send_json(200, {"deleted": self._delete_location(item_id)})
            elif parsed.path == "/api/wechat-targets":
                self._send_json(200, {"deleted": self._delete_target(item_id)})
            elif parsed.path == "/api/automation/jobs":
                self._send_json(200, {"deleted": self._delete_job(item_id)})
            else:
                self._send_json(404, {"error": "not found"})
        except Exception as exc:
            self._send_error(500, str(exc), context="server")


def run_server(
    host: str,
    port: int,
    config: str | None,
    window_handle: int | None,
) -> None:
    if config is not None and not Path(config).exists():
        raise FileNotFoundError(config)
    server = WeatherServer((host, port), config_path=config, window_handle=window_handle)
    print(f"Serving WeChat weather console at http://{host}:{port}/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    finally:
        server.monitor.stop()
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local web console for WeChat weather sending.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--config")
    parser.add_argument("--window-handle", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_server(
        host=args.host,
        port=args.port,
        config=args.config,
        window_handle=args.window_handle,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
