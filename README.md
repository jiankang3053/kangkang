# 微信天气发送台

一个运行在 Windows 本地的微信天气预报发送工具。它会读取 Open-Meteo 天气数据，通过 Windows 微信客户端自动发送到指定会话。

当前默认目标会话：`湘楠`。

## 功能

- 浏览器本地控制台：预览天气、手动发送、查看诊断和轮询状态。
- 完整天气预报：按 3 小时区间展示今日天气和降雨概率，并给出未来 3 天概要。
- 自动轮询：服务启动后每 2 小时检查一次天气变化。
- 智能补发：只有降雨概率明显升高、天气转差、气温明显变化或未来降雨等级升级时才补发。
- 夜间免打扰：`22:00-07:00` 只记录变化，不主动发送微信。

## 环境要求

- Windows
- 已登录 Windows 微信客户端
- Python 3.10+，当前开发环境使用 Python 3.14
- 目标会话需要在微信左侧会话列表中可见，默认是 `湘楠`

安装依赖：

```powershell
python -m pip install -r requirements-wechat-weather.txt
```

## 启动本地控制台

```powershell
python -m wechat_weather.cli serve --config .\wechat_weather_config.example.json --window-handle 199668 --port 8766
```

浏览器打开：

```text
http://127.0.0.1:8766/
```

如果本机微信窗口句柄变化，可以先运行诊断：

```powershell
python -m wechat_weather.cli diagnostics
```

## 手动发送天气

先 dry-run 预览：

```powershell
python -m wechat_weather.cli send-weather --config .\wechat_weather_config.example.json
```

真实发送到默认目标 `湘楠`：

```powershell
python -m wechat_weather.cli send-weather --config .\wechat_weather_config.example.json --real --backend pywinauto-session --window-handle 199668
```

## 自动轮询

配置位于 `wechat_weather_config.example.json`：

```json
{
  "monitor": {
    "enabled": true,
    "interval_minutes": 120,
    "contact": "湘楠",
    "backend": "pywinauto-session",
    "quiet_start": "22:00",
    "quiet_end": "07:00",
    "state_path": "weather_poll_state.json"
  }
}
```

第一次轮询只建立基准，不自动发送。之后只有天气风险明显变化时才补发短提醒。

## 说明

- 本项目不使用微信协议 Hook，只通过本机 Windows UI 自动化控制已登录的微信客户端。
- `wxauto` 后端保留为可选能力；默认推荐 `pywinauto-session`。
- `weather_poll_state.json` 是本地运行状态文件，不应提交到 Git。
