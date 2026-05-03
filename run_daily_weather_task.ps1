$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $env:APPDATA "KangkangWeather\logs"
$ConfigPath = Join-Path $env:APPDATA "KangkangWeather\config.json"
$LogPath = Join-Path $LogDir "daily_task.log"
$ExePath = Join-Path $Root "dist\KangkangWeather.exe"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-TaskLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Encoding UTF8 -Path $LogPath -Value "$stamp $Message"
}

Write-TaskLog "daily task started"
Write-TaskLog "root=$Root"
Write-TaskLog "config=$ConfigPath"

if (-not (Test-Path $ConfigPath)) {
    Write-TaskLog "config missing, abort"
    exit 2
}

Set-Location $Root

if (Test-Path $ExePath) {
    Write-TaskLog "using exe=$ExePath"
    & $ExePath monitor-run-due --config $ConfigPath 2>&1 | ForEach-Object { Write-TaskLog $_ }
    $code = $LASTEXITCODE
} else {
    $Python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $Python) {
        Write-TaskLog "python.exe missing, abort"
        exit 2
    }
    Write-TaskLog "using python=$Python"
    & $Python -m wechat_weather.cli monitor-run-due --config $ConfigPath 2>&1 | ForEach-Object { Write-TaskLog $_ }
    $code = $LASTEXITCODE
}

Write-TaskLog "daily task finished exit_code=$code"
exit $code
