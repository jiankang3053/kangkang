# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import socket
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any
from urllib import parse, request

from .config import APP_VERSION, load_config
from .server import WeatherServer


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _find_free_port(host: str, preferred: int) -> int:
    for port in range(preferred + 1, preferred + 80):
        if not _port_open(host, port):
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class DesktopRuntime:
    def __init__(self, config_path: str | None, window_handle: int | None) -> None:
        self.config_path = config_path
        self.window_handle = window_handle
        self.config = load_config(config_path, create_user_config=config_path is None)
        self.host = self.config.app.host
        self.port = self.config.app.port
        if _port_open(self.host, self.port):
            self.port = _find_free_port(self.host, self.port)
        self.url = f"http://{self.host}:{self.port}/"
        self.server = WeatherServer(
            (self.host, self.port),
            config_path=config_path,
            window_handle=window_handle,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="KangkangWeatherServer",
            daemon=True,
        )
        self.thread.start()
        deadline = time.time() + 8
        while time.time() < deadline:
            if _port_open(self.host, self.port):
                return
            time.sleep(0.1)
        raise RuntimeError("本地服务启动超时。")

    def close(self) -> None:
        self.server.shutdown()
        self.server.monitor.stop()
        self.server.server_close()

    def get_json(self, path: str) -> dict[str, Any]:
        with request.urlopen(f"{self.url}{path.lstrip('/')}", timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, path: str, payload: dict[str, Any] | None = None, timeout: int = 120) -> dict[str, Any]:
        data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self.url}{path.lstrip('/')}",
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            if hasattr(exc, "fp") and exc.fp:
                return json.loads(exc.fp.read().decode("utf-8"))
            raise


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_inner)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def _update_scroll_region(self, _: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_inner(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self.winfo_toplevel().focus_displayof() is None:
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class DesktopApp:
    def __init__(self, runtime: DesktopRuntime) -> None:
        self.runtime = runtime
        self.root = tk.Tk()
        self.root.title("Kangkang Weather")
        self.root.geometry("1060x720")
        self.root.minsize(760, 560)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.state: dict[str, Any] = {}
        self.monitor_state: dict[str, Any] = {}
        self.regions: list[dict[str, Any]] = []
        self.location_map: dict[str, str] = {}
        self.target_map: dict[str, str] = {}
        self.settings_window: tk.Toplevel | None = None

        self.location_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.backend_var = tk.StringVar(value="pywinauto-session")
        self.daily_prefix_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪")

        self.settings_target = tk.StringVar()
        self.settings_interval = tk.StringVar(value="120")
        self.settings_window_start = tk.StringVar(value="07:00")
        self.settings_window_end = tk.StringVar(value="22:00")
        self.settings_fixed_time = tk.StringVar(value="07:30")
        self.settings_allow_outside = tk.BooleanVar(value=False)
        self.settings_rain_threshold = tk.StringVar(value="50")
        self.settings_rain_jump = tk.StringVar(value="30")
        self.settings_temp_change = tk.StringVar(value="3")
        self.settings_weather_upgrade = tk.BooleanVar(value=True)
        self.settings_future_rain_upgrade = tk.BooleanVar(value=True)
        self.settings_search = tk.StringVar()
        self.settings_active_windows: list[str] = ["07:00-22:00"]
        self.settings_fixed_times: list[str] = []
        self.reminder_mode = tk.StringVar(value="smart")
        self.normal_weather_action = tk.StringVar(value="full")
        self.abnormal_weather_action = tk.StringVar(value="full")
        self.startup_enabled = tk.BooleanVar(value=False)
        self.tray_minimize_to_tray = tk.BooleanVar(value=True)
        self.tray_close_to_tray = tk.BooleanVar(value=True)
        self.tray_notifications = tk.BooleanVar(value=True)
        self.dnd_enabled = tk.BooleanVar(value=True)
        self.dnd_fullscreen = tk.BooleanVar(value=True)
        self.dnd_busy_process = tk.BooleanVar(value=True)
        self.dnd_busy_app = tk.BooleanVar(value=True)
        self.dnd_action = tk.StringVar(value="delay")
        self.dnd_delay = tk.StringVar(value="10")
        self.dnd_max_delay = tk.StringVar(value="60")
        self._really_exit = False
        self._tray_icon = None

        self._build_ui()
        self.root.bind("<Unmap>", self._on_unmap, add="+")
        self.refresh_regions()
        self.refresh_state()
        self.refresh_preview()
        self.refresh_monitor()
        self.refresh_history()
        if not self.state.get("app", {}).get("setup_complete", False):
            self.root.after(400, self.open_settings)

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"))

        root = ttk.Frame(self.root, padding=14)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text=f"Kangkang Weather  v{APP_VERSION}", font=("Microsoft YaHei UI", 18, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.status_var).pack(side="right")

        controls = ttk.LabelFrame(root, text="发送控制", padding=10)
        controls.pack(fill="x", pady=(12, 8))
        ttk.Label(controls, text="天气地址").grid(row=0, column=0, sticky="w")
        self.location_combo = ttk.Combobox(controls, textvariable=self.location_var, state="readonly", width=24)
        self.location_combo.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(2, 0))
        ttk.Label(controls, text="微信好友/群").grid(row=0, column=1, sticky="w")
        self.target_combo = ttk.Combobox(controls, textvariable=self.target_var, state="readonly", width=24)
        self.target_combo.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(2, 0))
        ttk.Label(controls, text="后端").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            controls,
            textvariable=self.backend_var,
            state="readonly",
            width=18,
            values=["pywinauto-session", "pywinauto-active", "wxauto"],
        ).grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(2, 0))

        buttons = ttk.Frame(controls)
        buttons.grid(row=1, column=3, sticky="e", pady=(2, 0))
        for text, command, style_name in [
            ("刷新预览", self.refresh_preview, ""),
            ("立即检查", self.monitor_check, ""),
            ("打开会话测试", self.open_target, ""),
            ("发送测试消息", self.send_test_message, ""),
            ("自动化设置", self.open_settings, ""),
            ("发送今日天气", self.send_weather, "Primary.TButton"),
        ]:
            ttk.Button(buttons, text=text, command=command, style=style_name).pack(side="left", padx=(0, 5))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="发送前缀").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(controls, textvariable=self.daily_prefix_var).grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=(0, 8),
            pady=(2, 0),
        )
        ttk.Button(controls, text="保存前缀", command=self.save_message_settings).grid(
            row=3,
            column=3,
            sticky="e",
            pady=(2, 0),
        )

        body = ttk.PanedWindow(root, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=2)

        forecast_box = ttk.LabelFrame(left, text="今日预报", padding=8)
        forecast_box.pack(fill="both", expand=True)
        self.message_text = tk.Text(forecast_box, wrap="word", font=("Microsoft YaHei UI", 10), height=18)
        self.message_text.pack(fill="both", expand=True)

        result_box = ttk.LabelFrame(left, text="运行结果", padding=8)
        result_box.pack(fill="both", expand=True, pady=(8, 0))
        self.result_text = tk.Text(result_box, wrap="word", font=("Consolas", 9), height=10)
        self.result_text.pack(fill="both", expand=True)

        status_box = ttk.LabelFrame(right, text="状态与诊断", padding=8)
        status_box.pack(fill="both", expand=True)
        self.metrics_text = tk.Text(status_box, wrap="word", font=("Microsoft YaHei UI", 9), height=10)
        self.metrics_text.pack(fill="both", expand=True)
        btns = ttk.Frame(status_box)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="兼容性自检", command=self.compat_check).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="导出诊断包", command=self.export_diagnostics).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="刷新诊断", command=self.refresh_diagnostics).pack(side="left")

        history_box = ttk.LabelFrame(right, text="天气查询记录", padding=8)
        history_box.pack(fill="both", expand=True, pady=(8, 0))
        ttk.Button(history_box, text="刷新记录", command=self.refresh_history).pack(anchor="w")
        self.history_text = tk.Text(history_box, wrap="word", font=("Microsoft YaHei UI", 9), height=9)
        self.history_text.pack(fill="both", expand=True, pady=(6, 0))

    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="normal")

    def _format_result(self, data: dict[str, Any]) -> str:
        analysis = data.get("error_analysis")
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        if not analysis:
            return raw
        causes = "\n".join(f"- {item}" for item in analysis.get("likely_causes", [])) or "- 未识别到明确原因"
        steps = "\n".join(f"- {item}" for item in analysis.get("next_steps", [])) or "- 请复制完整运行结果继续排查"
        return f"错误分析\n类型：{analysis.get('title') or analysis.get('category')}\n说明：{analysis.get('summary', '-')}\n\n可能原因：\n{causes}\n\n建议操作：\n{steps}\n\n原始结果：\n{raw}"

    def _run_background(self, label: str, func) -> None:
        self.status_var.set(label)

        def worker() -> None:
            try:
                result = func()
                self.root.after(0, lambda: self._handle_result(result))
            except Exception as exc:
                self.root.after(0, lambda: self._show_error(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_result(self, data: dict[str, Any]) -> None:
        try:
            self.refresh_state()
        except Exception:
            pass
        self._set_text(self.result_text, self._format_result(data))
        self.status_var.set("完成" if data.get("ok", True) else "失败")
        if data.get("preview"):
            self._set_text(self.message_text, data["preview"])
        self.refresh_monitor()
        self.refresh_history()

    def _show_error(self, exc: Exception) -> None:
        self.status_var.set("失败")
        messagebox.showerror("执行失败", str(exc))

    def selected_location_id(self) -> str:
        return self.location_map.get(self.location_var.get(), self.state.get("defaults", {}).get("location_id", ""))

    def selected_target_id(self) -> str:
        return self.target_map.get(self.target_var.get(), self.state.get("defaults", {}).get("wechat_target_id", ""))

    def refresh_regions(self) -> None:
        self.regions = self.runtime.get_json("api/regions/tree").get("regions", [])

    def refresh_state(self) -> None:
        self.state = self.runtime.get_json("api/state")
        self.daily_prefix_var.set(self.state.get("message", {}).get("daily_prefix", ""))
        self.location_map = {item["name"]: item["id"] for item in self.state.get("locations", [])}
        self.target_map = {item["name"]: item["id"] for item in self.state.get("wechat_targets", [])}
        self.location_combo["values"] = list(self.location_map.keys())
        self.target_combo["values"] = list(self.target_map.keys())
        default_location = self.state.get("defaults", {}).get("location_id")
        default_target = self.state.get("defaults", {}).get("wechat_target_id")
        for name, item_id in self.location_map.items():
            if item_id == default_location:
                self.location_var.set(name)
        for name, item_id in self.target_map.items():
            if item_id == default_target:
                self.target_var.set(name)

    def refresh_preview(self) -> None:
        def work() -> dict[str, Any]:
            loc = parse.quote(self.selected_location_id())
            target = parse.quote(self.selected_target_id())
            return self.runtime.get_json(f"api/preview?location_id={loc}&wechat_target_id={target}")

        self._run_background("正在刷新预览...", work)

    def refresh_monitor(self) -> None:
        try:
            self.monitor_state = self.runtime.get_json("api/monitor/status")
            self._set_text(self.metrics_text, json.dumps(self.monitor_state, ensure_ascii=False, indent=2))
        except Exception:
            pass

    def refresh_history(self) -> None:
        try:
            data = self.runtime.get_json("api/weather/history?limit=10")
            send_data = self.runtime.get_json("api/send-history?limit=5")
            lines = []
            send_rows = send_data.get("history", [])
            if send_rows:
                lines.append("【最近发送批次】")
                for item in reversed(send_rows):
                    summary = item.get("summary", {})
                    lines.append(
                        f"{item.get('finished_at') or item.get('started_at') or '-'}\n"
                        f"{item.get('status', '-')}：共 {summary.get('total', 0)}，"
                        f"成功 {summary.get('success', 0)}，失败 {summary.get('failed', 0)}，"
                        f"跳过 {summary.get('skipped', 0)}\n"
                    )
                lines.append("【天气查询记录】")
            for item in data.get("history", []):
                status = {"ok": "成功", "cache": "缓存", "failed": "失败"}.get(item.get("status"), item.get("status", "-"))
                failures = f"；失败源 {len(item.get('failures') or [])}" if item.get("failures") else ""
                disagreement = "；多源分歧" if item.get("source_disagreement") else ""
                lines.append(
                    f"{item.get('fetched_at', '-')}\n"
                    f"{item.get('address', '-')}：{status}，{item.get('source_count', 0)} 源，{item.get('elapsed_ms', '-')} ms{failures}{disagreement}\n"
                    f"{item.get('error') or ', '.join(item.get('sources') or [])}\n"
                )
            self._set_text(self.history_text, "\n".join(lines) if lines else "还没有天气查询或发送记录。")
        except Exception:
            pass

    def refresh_diagnostics(self) -> None:
        self._run_background("正在刷新诊断...", lambda: {"ok": True, "diagnostics": self.runtime.get_json("api/diagnostics").get("lines", [])})

    def compat_check(self) -> None:
        self._run_background("正在兼容性自检...", lambda: self.runtime.get_json("api/compat/check"))

    def export_diagnostics(self) -> None:
        self._run_background("正在导出诊断包...", lambda: self.runtime.post_json("api/diagnostics/export", {}))

    def open_target(self) -> None:
        payload = {"wechat_target_id": self.selected_target_id()}
        self._run_background("正在打开会话...", lambda: self.runtime.post_json("api/wechat/open-target", payload))

    def send_test_message(self) -> None:
        if not messagebox.askyesno("发送测试消息", "会真实发送一条测试消息到当前微信好友/群，继续吗？"):
            return
        payload = {"wechat_target_id": self.selected_target_id(), "backend": self.backend_var.get()}
        self._run_background("正在发送测试消息...", lambda: self.runtime.post_json("api/wechat/test-message", payload))

    def send_weather(self) -> None:
        if not messagebox.askyesno("发送今日天气", "会真实发送今日天气到当前微信好友/群，继续吗？"):
            return
        payload = {
            "location_id": self.selected_location_id(),
            "wechat_target_id": self.selected_target_id(),
            "backend": self.backend_var.get(),
            "real": True,
        }
        self._run_background("正在发送天气...", lambda: self.runtime.post_json("api/send-weather", payload))

    def save_message_settings(self) -> None:
        payload = {
            "daily_style": "segmented_brief",
            "daily_prefix": self.daily_prefix_var.get().strip(),
        }

        def work() -> dict[str, Any]:
            return self.runtime.post_json("api/message", payload)

        self._run_background("正在保存发送前缀...", work)
        self.root.after(500, self.refresh_preview)

    def monitor_check(self) -> None:
        self._run_background("正在立即检查...", lambda: self.runtime.post_json("api/monitor/check", {"dry_run": True}))

    def _find_region_selection(self, code: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        for province in self.regions:
            for city in province.get("children", []):
                if city.get("code") == code and not city.get("children"):
                    return province, city, city
                for district in city.get("children", []):
                    if district.get("code") == code:
                        return province, city, district
        province = self.regions[0] if self.regions else None
        city = (province.get("children") or [None])[0] if province else None
        district = ((city.get("children") or [city])[0] if city else None)
        return province, city, district

    def _fill_region_selects(self, code: str | None = None) -> None:
        if not self.regions or not hasattr(self, "region_province"):
            return
        province, city, district = self._find_region_selection(code)
        self.region_province["values"] = [item["name"] for item in self.regions]
        self.province_by_name = {item["name"]: item for item in self.regions}
        if province:
            self.region_province_var.set(province["name"])
        self._refresh_city_values(city_name=city.get("name") if city else "")
        self._refresh_district_values(district_name=district.get("name") if district else "")

    def _refresh_city_values(self, city_name: str = "") -> None:
        province = self.province_by_name.get(self.region_province_var.get())
        cities = province.get("children", []) if province else []
        self.city_by_name = {item["name"]: item for item in cities}
        self.region_city["values"] = list(self.city_by_name.keys())
        if city_name in self.city_by_name:
            self.region_city_var.set(city_name)
        elif cities:
            self.region_city_var.set(cities[0]["name"])
        self._refresh_district_values()

    def _refresh_district_values(self, district_name: str = "") -> None:
        city = self.city_by_name.get(self.region_city_var.get())
        districts = city.get("children", []) if city and city.get("children") else ([city] if city else [])
        self.district_by_name = {item["name"]: item for item in districts}
        self.region_district["values"] = list(self.district_by_name.keys())
        if district_name in self.district_by_name:
            self.region_district_var.set(district_name)
        elif districts:
            self.region_district_var.set(districts[0]["name"])

    def _selected_region_payload(self) -> dict[str, Any]:
        province = self.province_by_name.get(self.region_province_var.get())
        city = self.city_by_name.get(self.region_city_var.get())
        district = self.district_by_name.get(self.region_district_var.get())
        if not province or not city or not district:
            raise ValueError("请先选择省/市/区县。")
        path = []
        for value in [province["name"], city["name"], district["name"]]:
            if value and value not in path:
                path.append(value)
        return {
            "name": district["name"],
            "region_code": district["code"],
            "address_path": path,
            "source": "china_regions",
        }

    def open_settings(self) -> None:
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        win = tk.Toplevel(self.root)
        self.settings_window = win
        win.title("自动化设置")
        win.geometry("760x560")
        win.minsize(640, 480)

        shell = ScrollableFrame(win)
        shell.pack(fill="both", expand=True)
        root = ttk.Frame(shell.inner, padding=14)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="自动化设置", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(root, text="选择全国地址、微信好友、运行时间段和提醒规则。手动发送和测试消息不受时间段限制。").pack(anchor="w", pady=(4, 12))

        address = ttk.LabelFrame(root, text="地址选择", padding=10)
        address.pack(fill="x", pady=(0, 10))
        self.region_province_var = tk.StringVar()
        self.region_city_var = tk.StringVar()
        self.region_district_var = tk.StringVar()
        for col, (label, var) in enumerate([
            ("省份", self.region_province_var),
            ("城市", self.region_city_var),
            ("区县", self.region_district_var),
        ]):
            ttk.Label(address, text=label).grid(row=0, column=col, sticky="w")
            combo = ttk.Combobox(address, textvariable=var, state="readonly")
            combo.grid(row=1, column=col, sticky="ew", padx=(0, 8), pady=(2, 0))
            address.columnconfigure(col, weight=1)
            if col == 0:
                self.region_province = combo
            elif col == 1:
                self.region_city = combo
            else:
                self.region_district = combo
        self.region_province.bind("<<ComboboxSelected>>", lambda _: self._refresh_city_values())
        self.region_city.bind("<<ComboboxSelected>>", lambda _: self._refresh_district_values())
        search_row = ttk.Frame(address)
        search_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        search_row.columnconfigure(0, weight=1)
        ttk.Entry(search_row, textvariable=self.settings_search).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(search_row, text="搜索地址", command=self.search_region).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(search_row, text="保存所选地址", command=self.save_selected_region).grid(row=0, column=2)
        self.search_result_frame = ttk.Frame(address)
        self.search_result_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        target = ttk.LabelFrame(root, text="微信好友", padding=10)
        target.pack(fill="x", pady=(0, 10))
        ttk.Label(target, text="好友或群名称").grid(row=0, column=0, sticky="w")
        ttk.Entry(target, textvariable=self.settings_target).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(target, text="保存好友", command=self.save_target_from_settings).grid(row=1, column=1, padx=(0, 8))
        ttk.Button(target, text="打开会话测试", command=self.open_target_from_settings).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(target, text="发送测试消息", command=self.send_test_from_settings).grid(row=1, column=3)
        target.columnconfigure(0, weight=1)

        timing = ttk.LabelFrame(root, text="运行时间段", padding=10)
        timing.pack(fill="x", pady=(0, 10))
        preset = ttk.Frame(timing)
        preset.pack(fill="x")
        for label, window_value in [
            ("早晨", "06:00-09:00"),
            ("上午", "09:00-12:00"),
            ("下午", "12:00-18:00"),
            ("晚上", "18:00-22:00"),
            ("全天", "00:00-24:00"),
        ]:
            ttk.Button(preset, text=label, command=lambda value=window_value: self.add_active_window(value)).pack(side="left", padx=(0, 6))
        custom = ttk.Frame(timing)
        custom.pack(fill="x", pady=(8, 0))
        ttk.Entry(custom, textvariable=self.settings_window_start, width=8).pack(side="left")
        ttk.Label(custom, text=" 到 ").pack(side="left")
        ttk.Entry(custom, textvariable=self.settings_window_end, width=8).pack(side="left")
        ttk.Button(custom, text="新增时间段", command=self.add_custom_active_window).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(custom, text="允许时间段外自动发送", variable=self.settings_allow_outside).pack(side="left", padx=(12, 0))
        self.window_chip_frame = ttk.Frame(timing)
        self.window_chip_frame.pack(fill="x", pady=(8, 0))

        fixed = ttk.LabelFrame(root, text="固定发送点", padding=10)
        fixed.pack(fill="x", pady=(0, 10))
        ttk.Entry(fixed, textvariable=self.settings_fixed_time, width=8).pack(side="left")
        ttk.Button(fixed, text="新增固定点", command=self.add_fixed_time).pack(side="left", padx=(8, 0))
        self.fixed_chip_frame = ttk.Frame(fixed)
        self.fixed_chip_frame.pack(side="left", fill="x", expand=True, padx=(12, 0))

        rules = ttk.LabelFrame(root, text="提醒规则", padding=10)
        rules.pack(fill="x", pady=(0, 10))
        for col, (label, var) in enumerate([
            ("降雨阈值 %", self.settings_rain_threshold),
            ("降雨突增 %", self.settings_rain_jump),
            ("温差阈值 ℃", self.settings_temp_change),
        ]):
            ttk.Label(rules, text=label).grid(row=0, column=col, sticky="w")
            ttk.Entry(rules, textvariable=var, width=10).grid(row=1, column=col, sticky="ew", padx=(0, 8))
            rules.columnconfigure(col, weight=1)
        ttk.Checkbutton(rules, text="天气升级提醒", variable=self.settings_weather_upgrade).grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(rules, text="明后天降雨升级", variable=self.settings_future_rain_upgrade).grid(row=2, column=1, sticky="w", pady=(8, 0))

        smart = ttk.LabelFrame(root, text="智能提醒与后台运行", padding=10)
        smart.pack(fill="x", pady=(0, 10))
        ttk.Label(smart, text="提醒模式").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            smart,
            textvariable=self.reminder_mode,
            state="readonly",
            values=["always_full", "smart", "abnormal_only", "short_daily", "silent"],
        ).grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(2, 0))
        ttk.Label(smart, text="天气正常时").grid(row=0, column=1, sticky="w")
        ttk.Combobox(
            smart,
            textvariable=self.normal_weather_action,
            state="readonly",
            values=["none", "short", "full"],
        ).grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(2, 0))
        ttk.Label(smart, text="天气异常时").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            smart,
            textvariable=self.abnormal_weather_action,
            state="readonly",
            values=["short", "full", "urgent"],
        ).grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(2, 0))
        for col in range(3):
            smart.columnconfigure(col, weight=1)

        background = ttk.Frame(smart)
        background.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(background, text="开机自动启动", variable=self.startup_enabled).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(background, text="最小化到托盘", variable=self.tray_minimize_to_tray).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(background, text="关闭窗口时隐藏到托盘", variable=self.tray_close_to_tray).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(background, text="显示托盘通知", variable=self.tray_notifications).pack(side="left", padx=(0, 10))

        dnd = ttk.LabelFrame(root, text="勿扰模式", padding=10)
        dnd.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(dnd, text="自动发送前检查忙碌状态", variable=self.dnd_enabled).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(dnd, text="检测全屏应用", variable=self.dnd_fullscreen).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(dnd, text="检测游戏/视频软件", variable=self.dnd_busy_process).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(dnd, text="检测演示/忙碌窗口", variable=self.dnd_busy_app).grid(row=0, column=3, sticky="w")
        ttk.Label(dnd, text="忙碌时处理").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            dnd,
            textvariable=self.dnd_action,
            state="readonly",
            values=["delay", "skip", "tray_only", "force_send"],
            width=14,
        ).grid(row=2, column=0, sticky="ew", padx=(0, 8), pady=(2, 0))
        ttk.Label(dnd, text="延迟分钟").grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Entry(dnd, textvariable=self.dnd_delay, width=8).grid(row=2, column=1, sticky="w", padx=(0, 8), pady=(2, 0))
        ttk.Label(dnd, text="最大延迟分钟").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(dnd, textvariable=self.dnd_max_delay, width=8).grid(row=2, column=2, sticky="w", padx=(0, 8), pady=(2, 0))
        ttk.Label(dnd, text="高级进程黑名单暂通过配置文件维护；不会截图或记录窗口标题全文。").grid(
            row=3,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(8, 0),
        )

        history = ttk.LabelFrame(root, text="天气查询记录", padding=10)
        history.pack(fill="both", expand=True, pady=(0, 10))
        ttk.Button(history, text="刷新记录", command=self.refresh_history).pack(anchor="w")
        ttk.Label(history, text="主窗口右侧会显示最近 10 次查询，包括成功源、失败源、缓存和耗时。").pack(anchor="w", pady=(6, 0))

        actions = ttk.Frame(root)
        actions.pack(fill="x")
        ttk.Button(actions, text="填入当前选择", command=self.fill_settings_from_current).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="保存自动化配置", command=self.apply_settings_profile, style="Primary.TButton").pack(side="left")

        self.fill_settings_from_current()

    def _render_chips(self, frame: ttk.Frame, values: list[str], remove_command) -> None:
        for child in frame.winfo_children():
            child.destroy()
        if not values:
            ttk.Label(frame, text="未设置").pack(side="left")
            return
        for index, value in enumerate(values):
            chip = ttk.Frame(frame)
            chip.pack(side="left", padx=(0, 6), pady=2)
            ttk.Label(chip, text=value).pack(side="left")
            ttk.Button(chip, text="删除", command=lambda i=index: remove_command(i)).pack(side="left", padx=(4, 0))

    def refresh_settings_chips(self) -> None:
        if hasattr(self, "window_chip_frame"):
            self._render_chips(self.window_chip_frame, self.settings_active_windows, self.remove_active_window)
        if hasattr(self, "fixed_chip_frame"):
            self._render_chips(self.fixed_chip_frame, self.settings_fixed_times, self.remove_fixed_time)

    def add_active_window(self, value: str) -> None:
        if value == "00:00-24:00":
            self.settings_active_windows = [value]
        elif value not in self.settings_active_windows:
            self.settings_active_windows = sorted([item for item in self.settings_active_windows if item != "00:00-24:00"] + [value])
        self.refresh_settings_chips()

    def add_custom_active_window(self) -> None:
        self.add_active_window(f"{self.settings_window_start.get()}-{self.settings_window_end.get()}")

    def remove_active_window(self, index: int) -> None:
        if 0 <= index < len(self.settings_active_windows):
            del self.settings_active_windows[index]
        if not self.settings_active_windows:
            self.settings_active_windows = ["07:00-22:00"]
        self.refresh_settings_chips()

    def add_fixed_time(self) -> None:
        value = self.settings_fixed_time.get().strip()
        if value and value not in self.settings_fixed_times:
            self.settings_fixed_times = sorted([*self.settings_fixed_times, value])
        self.refresh_settings_chips()

    def remove_fixed_time(self, index: int) -> None:
        if 0 <= index < len(self.settings_fixed_times):
            del self.settings_fixed_times[index]
        self.refresh_settings_chips()

    def search_region(self) -> None:
        query = self.settings_search.get().strip()
        if not query:
            return
        data = self.runtime.get_json(f"api/regions/search?query={parse.quote(query)}&limit=8")
        for child in self.search_result_frame.winfo_children():
            child.destroy()
        for item in data.get("results", []):
            row = ttk.Frame(self.search_result_frame)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=item.get("display_name", item.get("name", ""))).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="选用", command=lambda code=item.get("code"): self._fill_region_selects(code)).pack(side="right")

    def save_selected_region(self) -> None:
        payload = self._selected_region_payload()
        data = self.runtime.post_json("api/locations", payload)
        self._handle_result({"ok": True, "location": data.get("location")})
        self.refresh_state()

    def save_target_from_settings(self) -> None:
        name = self.settings_target.get().strip()
        if not name:
            messagebox.showwarning("缺少微信好友", "请先填写微信好友或群名称。")
            return
        data = self.runtime.post_json("api/wechat-targets", {"name": name})
        self._handle_result({"ok": True, "wechat_target": data.get("wechat_target")})
        self.refresh_state()

    def open_target_from_settings(self) -> None:
        name = self.settings_target.get().strip()
        if not name:
            messagebox.showwarning("缺少微信好友", "请先填写微信好友或群名称。")
            return
        self._run_background("正在打开会话...", lambda: self.runtime.post_json("api/wechat/open-target", {"contact": name}))

    def send_test_from_settings(self) -> None:
        name = self.settings_target.get().strip()
        if not name:
            messagebox.showwarning("缺少微信好友", "请先填写微信好友或群名称。")
            return
        if not messagebox.askyesno("发送测试消息", f"会真实发送一条测试消息到「{name}」，继续吗？"):
            return
        self._run_background("正在发送测试消息...", lambda: self.runtime.post_json("api/wechat/test-message", {"contact": name, "backend": self.backend_var.get()}))

    def fill_settings_from_current(self) -> None:
        location = next((item for item in self.state.get("locations", []) if item["id"] == self.selected_location_id()), None)
        target = next((item for item in self.state.get("wechat_targets", []) if item["id"] == self.selected_target_id()), None)
        job = self.state.get("automation_jobs", [{}])[0]
        if location:
            self._fill_region_selects(location.get("region_code") or "421221")
        if target:
            self.settings_target.set(target.get("name", ""))
        self.settings_interval.set(str(job.get("interval_minutes", 120)))
        self.settings_active_windows = list(job.get("active_windows") or ["07:00-22:00"])
        self.settings_fixed_times = list(job.get("fixed_times") or [])
        self.settings_allow_outside.set(bool(job.get("allow_quiet_send", False)))
        options = job.get("alert_options") or {}
        self.settings_rain_threshold.set(str(options.get("rain_threshold_percent", 50)))
        self.settings_rain_jump.set(str(options.get("rain_jump_percent", 30)))
        self.settings_temp_change.set(str(options.get("temp_change_celsius", 3)))
        self.settings_weather_upgrade.set(bool(options.get("weather_upgrade_enabled", True)))
        self.settings_future_rain_upgrade.set(bool(options.get("future_rain_upgrade_enabled", True)))
        policy = self.state.get("reminder_policy") or {}
        self.reminder_mode.set(str(policy.get("mode") or "smart"))
        self.normal_weather_action.set(str(policy.get("normal_weather_action") or "full"))
        self.abnormal_weather_action.set(str(policy.get("abnormal_weather_action") or "full"))
        startup = self.state.get("startup") or {}
        self.startup_enabled.set(bool(startup.get("enabled", False)))
        tray = self.state.get("tray") or {}
        self.tray_minimize_to_tray.set(bool(tray.get("minimize_to_tray", True)))
        self.tray_close_to_tray.set(bool(tray.get("close_to_tray", True)))
        self.tray_notifications.set(bool(tray.get("show_tray_notifications", True)))
        dnd = self.state.get("do_not_disturb") or {}
        self.dnd_enabled.set(bool(dnd.get("enabled", True)))
        self.dnd_fullscreen.set(bool(dnd.get("detect_fullscreen", True)))
        self.dnd_busy_process.set(bool(dnd.get("detect_game_process", True)))
        self.dnd_busy_app.set(bool(dnd.get("detect_foreground_busy_app", True)))
        self.dnd_action.set(str(dnd.get("busy_action") or "delay"))
        self.dnd_delay.set(str(dnd.get("delay_minutes", 10)))
        self.dnd_max_delay.set(str(dnd.get("max_delay_minutes", 60)))
        self.refresh_settings_chips()
        self.status_var.set("已填入当前配置")

    def apply_settings_profile(self) -> None:
        try:
            payload = {
                "location": self._selected_region_payload(),
                "wechat_target": {"name": self.settings_target.get().strip()},
                "automation": {
                    "interval_minutes": int(self.settings_interval.get() or 120),
                    "fixed_times": self.settings_fixed_times,
                    "active_windows": self.settings_active_windows,
                    "allow_quiet_send": self.settings_allow_outside.get(),
                    "alert_options": {
                        "rain_threshold_percent": int(self.settings_rain_threshold.get() or 50),
                        "rain_jump_percent": int(self.settings_rain_jump.get() or 30),
                        "temp_change_celsius": float(self.settings_temp_change.get() or 3),
                        "weather_upgrade_enabled": self.settings_weather_upgrade.get(),
                        "future_rain_upgrade_enabled": self.settings_future_rain_upgrade.get(),
                    },
                },
            }
            if not payload["wechat_target"]["name"]:
                raise ValueError("请先填写微信好友或群名称。")
            system_payload = {
                "reminder_policy": {
                    "enabled": True,
                    "mode": self.reminder_mode.get(),
                    "normal_weather_action": self.normal_weather_action.get(),
                    "abnormal_weather_action": self.abnormal_weather_action.get(),
                },
                "startup": {"enabled": self.startup_enabled.get()},
                "tray": {
                    "enabled": True,
                    "minimize_to_tray": self.tray_minimize_to_tray.get(),
                    "close_to_tray": self.tray_close_to_tray.get(),
                    "show_tray_notifications": self.tray_notifications.get(),
                },
                "do_not_disturb": {
                    "enabled": self.dnd_enabled.get(),
                    "detect_fullscreen": self.dnd_fullscreen.get(),
                    "detect_game_process": self.dnd_busy_process.get(),
                    "detect_foreground_busy_app": self.dnd_busy_app.get(),
                    "busy_action": self.dnd_action.get(),
                    "delay_minutes": int(self.dnd_delay.get() or 10),
                    "max_delay_minutes": int(self.dnd_max_delay.get() or 60),
                },
            }
        except Exception as exc:
            messagebox.showwarning("配置不完整", str(exc))
            return

        def work() -> dict[str, Any]:
            profile = self.runtime.post_json("api/setup/apply-profile", payload)
            system = self.runtime.post_json("api/system-settings", system_payload)
            return {"ok": True, "profile": profile, "system_settings": system}

        self._run_background("正在保存自动化配置...", work)

    def _on_unmap(self, _: tk.Event) -> None:
        if self._really_exit:
            return
        try:
            if self.root.state() == "iconic" and self.state.get("tray", {}).get("minimize_to_tray", True):
                self.root.after(80, self.hide_to_tray)
        except Exception:
            pass

    def _ensure_desktop_tray(self) -> bool:
        if self._tray_icon is not None:
            return True
        try:
            import pystray
            from .tray import _make_icon_image
        except Exception as exc:
            messagebox.showwarning(
                "托盘不可用",
                f"系统托盘依赖不可用，窗口将正常退出或最小化。原始错误：{exc}",
            )
            return False

        def show(_: Any = None) -> None:
            self.root.after(0, self.show_from_tray)

        def refresh(_: Any = None) -> None:
            self.root.after(0, self.refresh_preview)

        def send(_: Any = None) -> None:
            self.root.after(0, self.send_weather)

        def pause(_: Any = None) -> None:
            self._run_background("正在暂停自动化...", lambda: self.runtime.post_json("api/monitor/pause", {}))

        def resume(_: Any = None) -> None:
            self._run_background("正在恢复自动化...", lambda: self.runtime.post_json("api/monitor/resume", {}))

        def settings(_: Any = None) -> None:
            self.root.after(0, self.open_settings)

        def diagnostics(_: Any = None) -> None:
            self.root.after(0, self.export_diagnostics)

        def quit_app(icon: Any, *_: Any) -> None:
            self.root.after(0, self.exit_program)

        menu = pystray.Menu(
            pystray.MenuItem("显示主窗口", show, default=True),
            pystray.MenuItem("刷新天气", refresh),
            pystray.MenuItem("发送今日天气", send),
            pystray.MenuItem("暂停自动化", pause),
            pystray.MenuItem("恢复自动化", resume),
            pystray.MenuItem("打开设置", settings),
            pystray.MenuItem("导出诊断包", diagnostics),
            pystray.MenuItem("退出程序", quit_app),
        )
        self._tray_icon = pystray.Icon("KangkangWeatherDesktop", _make_icon_image(), "Kangkang Weather", menu)
        try:
            self._tray_icon.run_detached()
        except Exception:
            self._tray_icon = None
            return False
        return True

    def hide_to_tray(self) -> bool:
        if not self.state.get("tray", {}).get("enabled", True):
            return False
        if not self._ensure_desktop_tray():
            return False
        self.root.withdraw()
        self.status_var.set("已隐藏到托盘，自动化继续运行")
        return True

    def show_from_tray(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.status_var.set("已显示主窗口")

    def exit_program(self) -> None:
        self._really_exit = True
        try:
            if self._tray_icon is not None:
                self._tray_icon.stop()
                self._tray_icon = None
        except Exception:
            pass
        self.close()

    def close(self) -> None:
        if not self._really_exit and self.state.get("tray", {}).get("close_to_tray", True):
            if self.hide_to_tray():
                return
        try:
            self.runtime.close()
        finally:
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_desktop(config_path: str | None = None, window_handle: int | None = None) -> None:
    runtime = DesktopRuntime(config_path=config_path, window_handle=window_handle)
    DesktopApp(runtime).run()
