# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from .config import load_config


def _add_data_arg(source: Path, target: str) -> str:
    separator = ";" if sys.platform.startswith("win") else ":"
    return f"{source}{separator}{target}"


def _copy_if_exists(source: Path, target: Path) -> None:
    if source.exists():
        shutil.copy2(source, target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_installer(root: Path, dist_dir: Path, package_dir: Path, package_name: str, version: str) -> Path:
    payload_dir = root / "build" / "installer_payload"
    if payload_dir.exists():
        shutil.rmtree(payload_dir)
    payload_dir.mkdir(parents=True)
    for item in package_dir.iterdir():
        target = payload_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    installer_name = f"{package_name}Setup-v{version}"
    installer_entry = root / "kangkang_weather_installer.py"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        installer_name,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(root / "build" / "pyinstaller-installer"),
        "--specpath",
        str(root / "build"),
        "--add-data",
        _add_data_arg(payload_dir, "payload"),
        str(installer_entry),
    ]
    subprocess.run(command, cwd=root, check=True)
    installer_path = dist_dir / f"{installer_name}.exe"
    if not installer_path.exists():
        raise FileNotFoundError(installer_path)
    return installer_path


def build_package(config_path: str | None = None, output_dir: str | None = None) -> Path:
    root = Path(__file__).resolve().parent.parent
    config = load_config(config_path, create_user_config=False)
    dist_dir = root / (output_dir or config.release.output_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    entry = root / "kangkang_weather.py"
    if not entry.exists():
        raise FileNotFoundError(entry)

    package_name = config.release.package_name
    version = config.release.version
    exe_path = dist_dir / f"{package_name}.exe"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        package_name,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(root / "build" / "pyinstaller"),
        "--specpath",
        str(root / "build"),
        "--add-data",
        _add_data_arg(root / "wechat_weather" / "web_console.html", "wechat_weather"),
        "--add-data",
        _add_data_arg(root / "wechat_weather" / "regions_level.json", "wechat_weather"),
        "--hidden-import",
        "pystray._win32",
        "--hidden-import",
        "wechat_weather.desktop",
        "--hidden-import",
        "wechat_weather.regions",
        "--hidden-import",
        "wechat_weather.compat",
        "--hidden-import",
        "wechat_weather.error_analysis",
        "--hidden-import",
        "wechat_weather.readiness",
        "--hidden-import",
        "wechat_weather.power",
        "--hidden-import",
        "wechat_weather.scheduler",
        "--hidden-import",
        "wechat_weather.run_trace",
        "--hidden-import",
        "wechat_weather.migration",
        "--hidden-import",
        "wechat_weather.updater",
        str(entry),
    ]
    subprocess.run(command, cwd=root, check=True)
    if not exe_path.exists():
        raise FileNotFoundError(exe_path)

    package_dir = dist_dir / f"{package_name}-v{version}"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)
    shutil.copy2(exe_path, package_dir / exe_path.name)
    _copy_if_exists(root / "README.md", package_dir / "README.md")
    _copy_if_exists(root / "README_PORTABLE.md", package_dir / "README_PORTABLE.md")
    _copy_if_exists(root / f"RELEASE_NOTES_v{version}.md", package_dir / f"RELEASE_NOTES_v{version}.md")
    _copy_if_exists(root / "wechat_weather_config.example.json", package_dir / "config.example.json")
    _copy_if_exists(root / "requirements-wechat-weather.txt", package_dir / "requirements.txt")
    _copy_if_exists(root / "build_exe.ps1", package_dir / "build_exe.ps1")
    _copy_if_exists(root / "start_wechat_weather_console.ps1", package_dir / "start_wechat_weather_console.ps1")
    _copy_if_exists(root / "run_daily_weather_task.ps1", package_dir / "run_daily_weather_task.ps1")

    zip_path = dist_dir / f"{package_name}-v{version}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        for item in package_dir.rglob("*"):
            archive.write(item, item.relative_to(package_dir))
    installer_path = _build_installer(root, dist_dir, package_dir, package_name, version)
    checksums = dist_dir / f"SHA256SUMS-v{version}.txt"
    checksums.write_text(
        "\n".join(
            [
                f"{_sha256(zip_path)}  {zip_path.name}",
                f"{_sha256(installer_path)}  {installer_path.name}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"created: {zip_path}")
    print(f"created: {installer_path}")
    print(f"created: {checksums}")
    return zip_path
