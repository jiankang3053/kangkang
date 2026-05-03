# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys

from .config import dump_example, load_config
from .weather import build_weather_message
from .wechat import choose_sender, collect_diagnostics


def _readiness_ok_for_real_send(real_send: bool) -> bool:
    if not real_send:
        return True
    from .readiness import check_readiness

    report = check_readiness(require_wechat=True).to_dict()
    if report.get("can_send_now"):
        return True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return False


def _print_result(result) -> int:
    print(f"backend: {result.backend}")
    print(f"contact: {result.contact}")
    print(f"ok: {result.ok}")
    if result.detail:
        print(f"detail: {result.detail}")
    if result.preview:
        print("message:")
        print(result.preview)
    return 0 if result.ok else 1


def cmd_send_weather(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    location = config.location_by_id(args.location_id)
    target = config.wechat_target_by_id(args.wechat_target_id or args.contact)
    weather = location.weather_config(
        timeout_seconds=config.providers.timeout_seconds,
        language=config.providers.language,
    )
    message = build_weather_message(
        weather,
        comparison_models=config.providers.comparison_models,
        daily_prefix=config.message.daily_prefix,
        daily_style=config.message.daily_style,
    )
    if not _readiness_ok_for_real_send(args.real):
        return 2
    sender = choose_sender(
        real_send=args.real,
        backend=args.backend,
        window_handle=args.window_handle,
        send_strategy=config.monitor.wechat_send_strategy,
        allow_send_button_coordinate_fallback=config.monitor.allow_send_button_coordinate_fallback,
    )
    return _print_result(sender.send(target.name, message))


def cmd_send_text(args: argparse.Namespace) -> int:
    if not _readiness_ok_for_real_send(args.real):
        return 2
    sender = choose_sender(
        real_send=args.real,
        backend=args.backend,
        window_handle=args.window_handle,
        send_strategy=args.send_strategy,
        allow_send_button_coordinate_fallback=args.allow_send_button_coordinate_fallback,
    )
    return _print_result(sender.send(args.contact, args.text))


def cmd_diagnostics(_: argparse.Namespace) -> int:
    for line in collect_diagnostics():
        print(line)
    return 0


def cmd_readiness(_: argparse.Namespace) -> int:
    from .readiness import check_readiness

    report = check_readiness(require_wechat=True).to_dict()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("can_send_now") else 1


def cmd_power_status(_: argparse.Namespace) -> int:
    from .power import get_power_status

    print(json.dumps(get_power_status(), ensure_ascii=False, indent=2))
    return 0


def cmd_power_apply(args: argparse.Namespace) -> int:
    from .power import apply_ac_power_profile

    result = apply_ac_power_profile(args.monitor_timeout_minutes)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_scheduler_status(_: argparse.Namespace) -> int:
    from .scheduler import scheduler_status

    result = scheduler_status()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_scheduler_repair(args: argparse.Namespace) -> int:
    from .scheduler import repair_scheduler_tasks

    result = repair_scheduler_tasks(args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_init_config(args: argparse.Namespace) -> int:
    dump_example(args.output)
    print(f"created: {args.output}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import run_server

    run_server(
        host=args.host,
        port=args.port,
        config=args.config,
        window_handle=args.window_handle,
    )
    return 0


def cmd_monitor_check(args: argparse.Namespace) -> int:
    from .monitor import WeatherMonitor

    monitor = WeatherMonitor(config_path=args.config, window_handle=args.window_handle)
    result = monitor.check_once(
        real_send=not args.dry_run,
        job_id=args.job_id,
        recipient_name=args.recipient,
    )
    print(result)
    return 0 if result.get("ok") else 1


def cmd_monitor_run_due(args: argparse.Namespace) -> int:
    from .monitor import WeatherMonitor

    monitor = WeatherMonitor(config_path=args.config, window_handle=args.window_handle)
    result = monitor.run_due(real_send=not args.dry_run)
    print(result)
    return 0 if result.get("ok") else 1


def cmd_tray(args: argparse.Namespace) -> int:
    from .tray import run_tray

    run_tray(config_path=args.config, window_handle=args.window_handle)
    return 0


def cmd_desktop(args: argparse.Namespace) -> int:
    from .desktop import run_desktop

    run_desktop(config_path=args.config, window_handle=args.window_handle)
    return 0


def cmd_build_package(args: argparse.Namespace) -> int:
    from .packaging import build_package

    build_package(config_path=args.config, output_dir=args.output_dir)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wechat-weather",
        description="Send weather forecasts to Windows WeChat through wxauto.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    weather = subparsers.add_parser("send-weather", help="Build and send a weather forecast.")
    weather.add_argument("--config", help="Path to JSON config.")
    weather.add_argument("--location-id", help="Weather location id or name.")
    weather.add_argument("--wechat-target-id", help="WeChat target id or name.")
    weather.add_argument("--contact", help="Legacy alias for --wechat-target-id.")
    weather.add_argument(
        "--real",
        action="store_true",
        help="Actually call wxauto.SendMsg. Omit this flag for dry-run.",
    )
    weather.add_argument(
        "--backend",
        choices=["auto", "wxauto", "pywinauto-active", "pywinauto-session"],
        default="auto",
        help="Real-send backend. auto uses wxauto.",
    )
    weather.add_argument(
        "--window-handle",
        type=int,
        help="Optional WeChat window handle for pywinauto-active.",
    )
    weather.set_defaults(func=cmd_send_weather)

    text = subparsers.add_parser("send-text", help="Send a custom text message.")
    text.add_argument("--contact", required=True, help="WeChat contact or group name.")
    text.add_argument("--text", required=True, help="Message text.")
    text.add_argument(
        "--real",
        action="store_true",
        help="Actually call wxauto.SendMsg. Omit this flag for dry-run.",
    )
    text.add_argument(
        "--backend",
        choices=["auto", "wxauto", "pywinauto-active", "pywinauto-session"],
        default="auto",
        help="Real-send backend. auto uses wxauto.",
    )
    text.add_argument(
        "--window-handle",
        type=int,
        help="Optional WeChat window handle for pywinauto-active.",
    )
    text.add_argument(
        "--send-strategy",
        default="enter_first",
        choices=["enter_first", "ctrl_enter_first", "enter_only"],
        help="Keyboard send strategy for pywinauto backends.",
    )
    text.add_argument(
        "--allow-send-button-coordinate-fallback",
        action="store_true",
        help="After keyboard send fails, allow button coordinate fallback. Disabled by default.",
    )
    text.set_defaults(func=cmd_send_text)

    diagnostics = subparsers.add_parser("diagnostics", help="Check dependencies and WeChat windows.")
    diagnostics.set_defaults(func=cmd_diagnostics)

    readiness = subparsers.add_parser("readiness", help="Check whether WeChat automation can send now.")
    readiness.set_defaults(func=cmd_readiness)

    power_status = subparsers.add_parser("power-status", help="Check display/sleep power settings.")
    power_status.set_defaults(func=cmd_power_status)

    power_apply = subparsers.add_parser("power-apply", help="Apply AC power profile: display off, no sleep.")
    power_apply.add_argument("--monitor-timeout-minutes", type=int, default=5)
    power_apply.set_defaults(func=cmd_power_apply)

    scheduler_status_cmd = subparsers.add_parser("scheduler-status", help="Check KangkangWeather scheduled tasks.")
    scheduler_status_cmd.set_defaults(func=cmd_scheduler_status)

    scheduler_repair = subparsers.add_parser("scheduler-repair", help="Create or repair KangkangWeather scheduled tasks.")
    scheduler_repair.add_argument("--config")
    scheduler_repair.set_defaults(func=cmd_scheduler_repair)

    init_config = subparsers.add_parser("init-config", help="Write an example config JSON.")
    init_config.add_argument("--output", default="wechat_weather_config.json")
    init_config.set_defaults(func=cmd_init_config)

    serve = subparsers.add_parser("serve", help="Run the local browser console.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8766)
    serve.add_argument("--config")
    serve.add_argument("--window-handle", type=int)
    serve.set_defaults(func=cmd_serve)

    monitor_check = subparsers.add_parser("monitor-check", help="Run one monitor check.")
    monitor_check.add_argument("--config")
    monitor_check.add_argument("--window-handle", type=int)
    monitor_check.add_argument("--job-id", help="Automation job id.")
    monitor_check.add_argument("--recipient", help="Recipient name. Defaults to all enabled recipients.")
    monitor_check.add_argument("--dry-run", action="store_true", help="Do not send WeChat messages.")
    monitor_check.set_defaults(func=cmd_monitor_check)

    monitor_run_due = subparsers.add_parser("monitor-run-due", help="Run due monitor jobs, including fixed send times.")
    monitor_run_due.add_argument("--config")
    monitor_run_due.add_argument("--window-handle", type=int)
    monitor_run_due.add_argument("--dry-run", action="store_true", help="Do not send WeChat messages.")
    monitor_run_due.set_defaults(func=cmd_monitor_run_due)

    tray = subparsers.add_parser("tray", help="Run the Windows tray app.")
    tray.add_argument("--config", default=None)
    tray.add_argument("--window-handle", type=int)
    tray.set_defaults(func=cmd_tray)

    desktop = subparsers.add_parser("desktop", help="Run the native desktop app.")
    desktop.add_argument("--config", default=None)
    desktop.add_argument("--window-handle", type=int)
    desktop.set_defaults(func=cmd_desktop)

    build_package_cmd = subparsers.add_parser("build-package", help="Build Windows EXE zip package.")
    build_package_cmd.add_argument("--config", default="wechat_weather_config.example.json")
    build_package_cmd.add_argument("--output-dir", default="dist")
    build_package_cmd.set_defaults(func=cmd_build_package)

    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
