# Kangkang Weather v2.0

Windows 微信天气提醒桌面版。程序在本机读取天气预报，通过已登录的 Windows 微信客户端把日报或风险变化提醒发送到指定会话。默认目标是 `湘楠`，默认城市是 `嘉鱼县`。

## 功能

- 托盘常驻：打开控制台、立即检查、发送今日天气、开机自启、退出。
- 浏览器控制台：查看预报、当前风险、数据源一致性、最近轮询、最近发送和环境诊断。
- 多目标配置：配置文件使用 `recipients` 列表，默认只启用 `湘楠`。
- 多源天气校验：Open-Meteo `best_match` 主源，加 `gfs_seamless`、`icon_seamless`、`cma_grapes_global` 交叉校验；全部失败时尝试 wttr.in 兜底。
- 自动轮询：默认每 2 小时检查一次，第一次只建立基准。
- 少打扰补发：只在降雨突增、天气升级、温差明显、明后天降雨等级升级或多源分歧时补发短提醒。
- 夜间抑制：`22:00-07:00` 只记录变化，早上风险仍存在时汇总提醒。

## 安装

```powershell
python -m pip install -r .\requirements-wechat-weather.txt
```

微信发送默认使用 `pywinauto-session`。目标会话需要在微信左侧会话列表可见，否则 UIAutomation 不能稳定打开它。

## 启动桌面版

```powershell
python -m wechat_weather.cli tray
```

首次不传 `--config` 时会自动创建用户配置：

```text
%APPDATA%\KangkangWeather\config.json
```

本地控制台默认地址：

```text
http://127.0.0.1:8766/
```

## CLI

预览今日天气，不发送微信：

```powershell
python -m wechat_weather.cli send-weather --config .\wechat_weather_config.example.json
```

真实发送到默认目标 `湘楠`：

```powershell
python -m wechat_weather.cli send-weather --config .\wechat_weather_config.example.json --real --backend pywinauto-session
```

启动浏览器控制台：

```powershell
python -m wechat_weather.cli serve --config .\wechat_weather_config.example.json --port 8766
```

执行一次轮询 dry-run，不发送微信：

```powershell
python -m wechat_weather.cli monitor-check --config .\wechat_weather_config.example.json --dry-run
```

环境诊断：

```powershell
python -m wechat_weather.cli diagnostics
```

## 配置

仓库内保留样例配置 `wechat_weather_config.example.json`。桌面版实际运行建议使用 `%APPDATA%\KangkangWeather\config.json`，避免升级源码时覆盖个人设置。

核心字段：

```json
{
  "contact": "湘楠",
  "recipients": [
    {
      "name": "湘楠",
      "city_label": "嘉鱼县",
      "latitude": 29.9724209,
      "longitude": 113.9335326,
      "enabled": true
    }
  ],
  "monitor": {
    "enabled": true,
    "interval_minutes": 120,
    "backend": "pywinauto-session",
    "quiet_start": "22:00",
    "quiet_end": "07:00"
  }
}
```

## 打包 EXE

```powershell
.\build_exe.ps1
```

输出文件：

```text
dist\KangkangWeather-v2.0.0.zip
```

压缩包内包含 `KangkangWeather.exe`、样例配置和 README。EXE 首次运行同样会创建 `%APPDATA%\KangkangWeather\config.json`。

## 说明

本项目不使用微信协议登录、Hook 或注入，只控制当前电脑上已经登录的 Windows 微信客户端。天气数据使用无 Key 来源，适合个人本机自动化，不适合作为高可靠灾害预警系统。
