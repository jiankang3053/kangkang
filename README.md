# Kangkang Weather v2.1

Windows 微信天气提醒桌面版。程序在本机读取天气预报，通过已登录的 Windows 微信客户端把日报或风险变化提醒发送到指定会话。

## 功能

- 天气地址和微信好友分开管理，不再绑定在同一个“目标”里。
- 地址管理器支持地址搜索、浏览器当前位置、IP 粗定位、新增、删除、重命名、设默认。
- 微信好友管理器支持多个好友或群名称，自定义、重命名、删除、设默认。
- 自动化任务可以组合任意地址和任意微信好友，配置轮询间隔、固定发送时间、免打扰时间。
- 多源天气校验：Open-Meteo `best_match` + `gfs_seamless` + `icon_seamless` + `cma_grapes_global`，全部失败时尝试 wttr.in。
- 默认任务仍是 `嘉鱼县 -> 湘楠`，每 120 分钟检查一次，`22:00-07:00` 免打扰。

## 安装

```powershell
python -m pip install -r .\requirements-wechat-weather.txt
```

微信发送默认使用 `pywinauto-session`。目标会话需要在微信左侧会话列表可见。

## 启动

```powershell
python -m wechat_weather.cli tray
```

首次不传 `--config` 时会自动创建用户配置：

```text
%APPDATA%\KangkangWeather\config.json
```

本地控制台：

```text
http://127.0.0.1:8766/
```

## CLI

预览默认地址并发送到默认微信好友，默认 dry-run：

```powershell
python -m wechat_weather.cli send-weather --config .\wechat_weather_config.example.json
```

指定地址和微信好友：

```powershell
python -m wechat_weather.cli send-weather --location-id jiayu --wechat-target-id xiangnan
```

真实发送：

```powershell
python -m wechat_weather.cli send-weather --real --backend pywinauto-session
```

检查指定自动化任务，不发送微信：

```powershell
python -m wechat_weather.cli monitor-check --job-id default --dry-run
```

启动浏览器控制台：

```powershell
python -m wechat_weather.cli serve --port 8766
```

## 配置结构

```json
{
  "locations": [
    {
      "id": "jiayu",
      "name": "嘉鱼县",
      "latitude": 29.9724209,
      "longitude": 113.9335326,
      "source": "default",
      "enabled": true,
      "default": true
    }
  ],
  "wechat_targets": [
    {
      "id": "xiangnan",
      "name": "湘楠",
      "enabled": true,
      "default": true
    }
  ],
  "automation_jobs": [
    {
      "id": "default",
      "location_id": "jiayu",
      "wechat_target_id": "xiangnan",
      "enabled": true,
      "interval_minutes": 120,
      "fixed_times": [],
      "quiet_start": "22:00",
      "quiet_end": "07:00",
      "allow_quiet_send": false
    }
  ]
}
```

旧版 `contact/recipients` 配置仍能读取，并会在保存设置时迁移到新结构。

## 打包 EXE

```powershell
.\build_exe.ps1
```

输出：

```text
dist\KangkangWeather-v2.1.0.zip
```

## 说明

本项目不使用微信协议登录、Hook 或注入，只控制当前电脑上已经登录的 Windows 微信客户端。天气和定位使用无 Key 来源：Open-Meteo Geocoding、浏览器定位和 ipapi.co。
