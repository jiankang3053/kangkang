# Kangkang Weather 智能提醒、后台运行与勿扰模式说明

> 适用版本：v3.6.0 之后  
> 目标：让软件更适合长期后台运行，同时减少天气正常、用户全屏或游戏时的打扰。

## 1. 智能提醒策略

新增配置段 `reminder_policy`：

```json
{
  "reminder_policy": {
    "enabled": true,
    "mode": "smart",
    "normal_weather_action": "full",
    "abnormal_weather_action": "full",
    "short_message_max_chars": 30,
    "record_skipped_history": true
  }
}
```

支持模式：

| 模式 | 行为 |
|---|---|
| `always_full` | 无论天气是否异常，都发送完整日报。 |
| `smart` | 根据天气是否异常选择正常动作或异常动作。当前默认正常动作保持 `full`，避免升级后突然少发。 |
| `abnormal_only` | 只有异常天气才发送，正常天气跳过并记录历史。 |
| `short_daily` | 每天只发一句简短天气。 |
| `silent` | 暂停天气提醒，但仍记录任务状态。 |

正常天气动作：

- `none`：不发送。
- `short`：发送一句简短提醒。
- `full`：发送完整日报。

异常天气动作：

- `short`：发送一句短提醒。
- `full`：发送完整日报。
- `urgent`：发送加强提醒，先给出重要提示，再附完整日报。

异常判断优先使用现有天气字段：

- 降雨：天气描述包含“雨/雷阵雨/暴雨/小雨/中雨/大雨”，或降雨概率达到阈值。
- 高温/低温：按最高温、最低温阈值判断。
- 明显降温：需要上次天气基准；没有基准时只记录字段缺失，不编造。
- 大风、AQI、UV：当前天气源缺字段时只记录缺失，不编造。

## 2. 开机自启动

新增 `startup.enabled`。开启后写入当前用户注册表：

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
```

特点：

- 不要求管理员权限。
- 打包版使用当前 EXE 路径。
- 源码运行使用 `python -m wechat_weather.cli tray`。
- 支持中文路径和空格路径。

限制：

- Windows 启动项设置或安全软件可能禁用它。
- EXE 移动位置后需要重新开启自启动。

## 3. 托盘后台运行

新增 `tray` 配置：

```json
{
  "tray": {
    "enabled": true,
    "minimize_to_tray": true,
    "close_to_tray": true,
    "show_tray_notifications": true
  }
}
```

支持：

- 桌面窗口最小化到托盘。
- 点击关闭窗口时隐藏到托盘，不直接退出。
- 托盘菜单：显示主窗口、刷新天气、发送今日天气、暂停自动化、恢复自动化、打开设置、导出诊断包、退出程序。
- `wechat_weather.cli tray` 仍可作为后台托盘入口启动本地服务。

真正退出必须从托盘菜单选择“退出程序”，会停止本地服务和自动化线程。

## 4. 勿扰检测 / 忙碌模式

新增 `do_not_disturb` 配置：

```json
{
  "do_not_disturb": {
    "enabled": true,
    "detect_fullscreen": true,
    "detect_game_process": true,
    "detect_foreground_busy_app": true,
    "busy_action": "delay",
    "delay_minutes": 10,
    "max_delay_minutes": 60
  }
}
```

自动发送前会检测：

- 当前前台窗口是否接近全屏。
- 前台进程是否命中默认游戏/视频/演示进程列表。
- 前台窗口标题是否命中用户配置关键词。

忙碌时处理：

| 动作 | 行为 |
|---|---|
| `delay` | 不打开微信，延迟后重试。 |
| `skip` | 跳过本次自动发送并记录历史。 |
| `tray_only` | 只记录状态，不打开微信。 |
| `force_send` | 忽略忙碌检测，继续发送。 |

隐私边界：

- 不截图。
- 不读取屏幕内容。
- 不读取微信聊天内容。
- 不保存完整窗口标题。
- 只记录进程名、是否全屏、命中原因代码。

## 5. 已知限制

- 全屏检测不保证 100% 准确。
- 游戏/视频进程列表需要后续维护。
- 某些游戏或反作弊软件可能阻止进程信息读取。
- 自动化延迟发送可能晚于原计划。
- 如果用户选择 `force_send`，仍可能打断当前窗口。
- 官方 Windows 微信没有公开本地发消息 API，锁屏、注销、睡眠、权限不一致时仍不能保证自动发送。
