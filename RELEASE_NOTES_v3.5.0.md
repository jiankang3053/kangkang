# KangkangWeather v3.5.0

## 本轮重点

- 新增多微信目标发送底层能力，`wechat_targets` 配置现在包含类型、备注、发送间隔和最近发送结果字段。
- 新增发送批次模型：每次发送都会生成 `batch_id`、`message_hash` 和每个目标的独立结果。
- 新增发送历史：写入 `%APPDATA%\KangkangWeather\history\send_history.jsonl`，便于排查重复发送、部分失败和目标级错误。
- 新增发送锁：写入 `%APPDATA%\KangkangWeather\locks\send_task.lock`，避免手动发送和自动任务并发操作微信。
- `/api/send-weather` 支持 `send_all_enabled`、`wechat_target_ids`、`target_ids` 和 `dry_run`，可先预演多个启用目标而不调用微信。
- `/api/send-history` 返回最近发送批次记录。
- 新增智能提醒策略：固定发送点可根据天气正常/异常决定完整发送、简短发送或跳过；跳过也会写入发送历史。
- 新增勿扰检测：自动发送前可检测全屏窗口、游戏/视频/演示进程，忙碌时延迟、跳过、只记录或强制发送。
- 新增 HKCU 开机自启动管理，不要求管理员权限，兼容打包 EXE、中文路径和空格路径。
- 托盘入口菜单增强：显示主窗口、刷新天气、发送今日天气、暂停/恢复自动化、打开设置、导出诊断包、退出程序。

## 兼容性

- 旧 `contact`、`recipients`、`wechat_targets` 配置继续可读。
- 单目标发送接口保持兼容，新增字段以附加方式返回。
- 当前没有重写微信发送核心链路，真实发送仍使用已有 `pywinauto-session` 稳定前台自动化。
- 默认智能模式为了兼容旧用户仍保持正常天气完整日报；可在设置中改成正常天气简短提醒或不提醒。
- 勿扰检测只检查前台窗口形态和进程名，不截图、不读取微信聊天内容、不记录敏感窗口标题全文。

## 验证

- `python -m compileall wechat_weather tests`
- `python -m unittest discover -s tests -v`
- 当前 53 个测试全部通过。
