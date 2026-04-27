$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python -m pip install -r .\requirements-wechat-weather.txt
python -m pip install pyinstaller
python -m wechat_weather.cli build-package --config .\wechat_weather_config.example.json --output-dir .\dist
