# Kangkang Weather v3.6.0

Windows 微信天气提醒桌面版。程序在本机获取天气预报，通过已登录的官方 Windows 微信客户端发送日报或风险变化提醒。

## 功能

- 全国地址选择：省份 -> 城市 -> 区县三级选择，支持本地搜索“北京、朝阳区、嘉鱼”等关键字。
- 微信好友和天气地址分开管理，可组合成多个自动化任务。
- 自动化任务支持运行时间段、固定发送点、轮询间隔和提醒规则。
- 天气查询记录保留最近 200 条，记录数据源数量、失败源、缓存、多源分歧和耗时。
- 多源天气校验：Open-Meteo 主源 + 多模型对比，失败时尝试 wttr.in，网络全失败时可使用最近缓存。
- 微信发送使用稳定前台自动化：自动选择已登录官方 Windows 微信窗口，搜索联系人优先 UIAutomation/键盘输入，默认不做搜索框或发送按钮坐标点击。
- 消息正文默认使用“粘贴后 Enter，再 Ctrl+Enter”键盘提交；微信窗口中途消失会停止后续输入并给出诊断。
- 天气日报样式为“今日分时段提醒 + 明天/后天简报”，支持保存发送前缀。
- v3.1 新增运行总览、左上角版本号、运行追踪、迁移包导出和 GitHub 更新检查。
- v3.1.1 修复桌面版启动时深度自检导致 `/api/state` 超时弹窗的问题，启动状态接口现在保持轻量。
- v3.5.0 新增多微信目标发送底层能力：配置带目标类型、备注、发送间隔、最近结果；发送天气支持批次 ID、目标级结果、JSONL 发送历史和并发发送锁。
- 新增智能提醒与后台勿扰能力：自动发送可按天气正常/异常选择完整、简短或跳过；支持 HKCU 开机自启动、托盘后台运行、全屏/游戏/视频/演示勿扰检测。
- v3.6.0 将近几轮工程收束为正式构建版：多对象发送、智能提醒、后台托盘、开机自启、勿扰检测和发布文档同步完成。
- 默认任务是 `嘉鱼县 -> 湘楠`，每 120 分钟检查一次，自动发送时间段为 `07:00-22:00`。

## 使用

```powershell
python -m pip install -r .\requirements-wechat-weather.txt
python -m wechat_weather.cli desktop
```

首次运行会在 `%APPDATA%\KangkangWeather\config.json` 创建用户配置。页面或桌面设置窗口会引导选择全国地址和微信好友/群名称。

## CLI

```powershell
python -m wechat_weather.cli send-weather --location-id jiayu --wechat-target-id xiangnan
python -m wechat_weather.cli send-weather --real --backend pywinauto-session
python -m wechat_weather.cli monitor-check --job-id default --dry-run
python -m wechat_weather.cli monitor-run-due --config "$env:APPDATA\KangkangWeather\config.json"
python -m wechat_weather.cli serve --port 8766
python -m wechat_weather.cli build-package
```

## 配置结构

用户界面不需要填写经纬度。配置中会保留内部坐标字段供天气接口使用，用户只需要通过全国地址选择器保存地址。

```json
{
  "locations": [
    {
      "id": "jiayu",
      "name": "嘉鱼县",
      "region_code": "421221",
      "address_path": ["湖北省", "咸宁市", "嘉鱼县"],
      "source": "default",
      "enabled": true,
      "default": true
    }
  ],
  "wechat_targets": [
    { "id": "xiangnan", "name": "湘楠", "enabled": true, "default": true }
  ],
  "automation_jobs": [
    {
      "id": "default",
      "location_id": "jiayu",
      "wechat_target_id": "xiangnan",
      "enabled": true,
      "interval_minutes": 120,
      "fixed_times": [],
      "active_windows": ["07:00-22:00"],
      "allow_quiet_send": false,
      "alert_options": {
        "rain_threshold_percent": 50,
        "rain_jump_percent": 30,
        "temp_change_celsius": 3,
        "weather_upgrade_enabled": true,
        "future_rain_upgrade_enabled": true
      }
    }
  ],
  "message": {
    "daily_style": "segmented_brief",
    "daily_prefix": ""
  },
  "reminder_policy": {
    "enabled": true,
    "mode": "smart",
    "normal_weather_action": "full",
    "abnormal_weather_action": "full",
    "short_message_max_chars": 30,
    "record_skipped_history": true
  },
  "startup": {
    "enabled": false
  },
  "tray": {
    "enabled": true,
    "minimize_to_tray": true,
    "close_to_tray": true,
    "show_tray_notifications": true
  },
  "do_not_disturb": {
    "enabled": true,
    "busy_action": "delay",
    "delay_minutes": 10,
    "max_delay_minutes": 60
  }
}
```

旧版 `contact/recipients` 和 `quiet_start/quiet_end` 配置仍能读取，并会在保存设置时迁移到新结构。

## 打包

```powershell
.\build_exe.ps1
```

输出：

```text
dist\KangkangWeather-v3.6.0.zip
dist\KangkangWeatherSetup-v3.6.0.exe
```

## 说明

本项目不使用微信协议登录、Hook 或注入，只控制当前电脑上已经登录的 Windows 微信客户端。安装包未做代码签名，Windows SmartScreen 可能提醒。

智能提醒和勿扰模式说明见 [docs/SMART_BACKGROUND_DND.md](docs/SMART_BACKGROUND_DND.md)。全屏/游戏检测只能判断前台窗口和进程名，不截图、不读取窗口内容，也不能保证 100% 准确。
