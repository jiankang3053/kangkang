# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from .config import load_config, read_config_data, write_config_data, normalize_fixed_times
from .monitor import WeatherMonitor
from .weather import build_weather_message
from .wechat import choose_sender, collect_diagnostics


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
        if "name" in body:
            item["name"] = str(body["name"]).strip()
        if "latitude" in body:
            item["latitude"] = float(body["latitude"])
        if "longitude" in body:
            item["longitude"] = float(body["longitude"])
        if "source" in body:
            item["source"] = str(body["source"])
        if "enabled" in body:
            item["enabled"] = _bool_value(body, "enabled", True)
        else:
            item.setdefault("enabled", True)
        item.setdefault("name", "未命名地址")
        item.setdefault("latitude", 0.0)
        item.setdefault("longitude", 0.0)
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
        if "enabled" in body:
            item["enabled"] = _bool_value(body, "enabled", True)
        else:
            item.setdefault("enabled", True)
        item.setdefault("name", "未命名好友")
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
                        "release": asdict(config.release),
                    },
                )
            elif parsed.path == "/api/locations/search":
                query = (parse_qs(parsed.query).get("query") or [""])[0].strip()
                if not query:
                    self._send_json(400, {"error": "query is required"})
                    return
                results = []
                failures = []
                try:
                    response = requests.get(
                        "https://geocoding-api.open-meteo.com/v1/search",
                        params={
                            "name": query,
                            "count": 8,
                            "language": "zh",
                            "format": "json",
                        },
                        timeout=12,
                    )
                    response.raise_for_status()
                    for item in response.json().get("results", []):
                        name = _display_location(item)
                        results.append(
                            {
                                "name": name,
                                "latitude": item.get("latitude"),
                                "longitude": item.get("longitude"),
                                "source": "open_meteo_geocoding",
                                "country": item.get("country"),
                                "admin1": item.get("admin1"),
                            }
                        )
                except Exception as exc:
                    failures.append(f"open_meteo_geocoding: {exc}")
                if not results:
                    response = requests.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={
                            "q": query,
                            "format": "jsonv2",
                            "limit": 8,
                            "accept-language": "zh-CN",
                        },
                        headers={"User-Agent": "KangkangWeather/2.1"},
                        timeout=12,
                    )
                    response.raise_for_status()
                    for item in response.json():
                        results.append(
                            {
                                "name": item.get("display_name") or query,
                                "latitude": float(item.get("lat")),
                                "longitude": float(item.get("lon")),
                                "source": "nominatim",
                            }
                        )
                self._send_json(200, {"results": results, "failures": failures})
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
                self._send_json(
                    200,
                    {
                        "location": asdict(location),
                        "wechat_target": asdict(target),
                        "contact": target.name,
                        "message": build_weather_message(
                            weather,
                            comparison_models=config.providers.comparison_models,
                        ),
                    },
                )
            elif parsed.path == "/api/diagnostics":
                self._send_json(200, {"lines": collect_diagnostics()})
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

            if parsed.path == "/api/monitor/check":
                real_send = bool(body.get("real", False)) and not bool(body.get("dry_run", False))
                result = self.server.monitor.check_once(
                    real_send=real_send,
                    job_id=body.get("job_id"),
                    recipient_name=body.get("recipient"),
                )
                self._send_json(200, result)
                return

            if parsed.path != "/api/send-weather":
                self._send_json(404, {"error": "not found"})
                return

            config = self.server.app_config
            location = config.location_by_id(body.get("location_id"))
            target = config.wechat_target_by_id(
                str(body.get("wechat_target_id") or body.get("recipient") or body.get("contact") or config.contact)
            )
            backend = str(body.get("backend") or "pywinauto-session")
            real = bool(body.get("real", False))
            weather = location.weather_config(
                timeout_seconds=config.providers.timeout_seconds,
                language=config.providers.language,
            )
            message = build_weather_message(
                weather,
                comparison_models=config.providers.comparison_models,
            )
            sender = choose_sender(
                real_send=real,
                backend=backend,
                window_handle=self.server.window_handle,
            )
            result = sender.send(target.name, message)
            payload = asdict(result)
            self._send_json(200 if result.ok else 409, payload)
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

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
            else:
                self._send_json(404, {"error": "not found"})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

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
            self._send_json(500, {"error": str(exc)})


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
