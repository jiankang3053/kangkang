# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys

from .config import dump_example, load_config
from .weather import build_weather_message
from .wechat import choose_sender, collect_diagnostics


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
    )
    sender = choose_sender(
        real_send=args.real,
        backend=args.backend,
        window_handle=args.window_handle,
    )
    return _print_result(sender.send(target.name, message))


def cmd_send_text(args: argparse.Namespace) -> int:
    sender = choose_sender(
        real_send=args.real,
        backend=args.backend,
        window_handle=args.window_handle,
    )
    return _print_result(sender.send(args.contact, args.text))


def cmd_diagnostics(_: argparse.Namespace) -> int:
    for line in collect_diagnostics():
        print(line)
    return 0


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


def cmd_tray(args: argparse.Namespace) -> int:
    from .tray import run_tray

    run_tray(config_path=args.config, window_handle=args.window_handle)
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
    text.set_defaults(func=cmd_send_text)

    diagnostics = subparsers.add_parser("diagnostics", help="Check dependencies and WeChat windows.")
    diagnostics.set_defaults(func=cmd_diagnostics)

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

    tray = subparsers.add_parser("tray", help="Run the Windows tray app.")
    tray.add_argument("--config", default=None)
    tray.add_argument("--window-handle", type=int)
    tray.set_defaults(func=cmd_tray)

    build_package_cmd = subparsers.add_parser("build-package", help="Build Windows EXE zip package.")
    build_package_cmd.add_argument("--config", default="wechat_weather_config.example.json")
    build_package_cmd.add_argument("--output-dir", default="dist")
    build_package_cmd.set_defaults(func=cmd_build_package)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
