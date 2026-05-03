# Kangkang Weather v3.5.0 正式发布前迭代工程文档

> 生成时间：2026-05-03  
> 当前源码基线：`wechat_weather.config.APP_VERSION = "3.1.1"`  
> 本轮目标：先形成工程执行文档，不直接修改功能代码、不重新打包。  
> 本轮验证：`python -m compileall wechat_weather tests` 通过；`python -m unittest discover -s tests -v` 通过，43 个测试全部通过。

## 0. 执行结论

Kangkang Weather 当前已经不是原型脚本，而是一个可运行的 Windows 本地桌面工具：它有 Tkinter/ttk 桌面端、内置 HTTP 控制台、全国地址选择、Open-Meteo 多源天气、微信 UI 自动化、Windows 计划任务、自检、诊断包、PyInstaller 打包和自定义安装器。

v3.5.0 不应重写项目，也不应换 PyQt/Electron。下一阶段最该做的是把“已经能跑”的能力工程化成“别人电脑上也能可靠判断、可靠失败、可靠恢复”的发布版。

v3.5.0 的主线建议定为：

**正式发布前的多对象发送、自动化状态机、微信前台自动化可靠性、迁移可用性和发布诊断升级。**

必须明确一个底层事实：官方 Windows 微信没有公开的本地发消息 API，本项目当前路线依赖 Windows UI 自动化控制已登录的微信客户端。它不能在注销、锁屏、UAC 安全桌面、权限级别不一致、微信未登录、微信窗口不可访问的场景下稳定发送。v3.5.0 的正确方向不是承诺“完全后台发送”，而是建立 P0 运行条件检查、可读错误、自动恢复建议和迁移向导。

## 1. 调研来源与工程影响

| 调研主题 | 来源 | 关键结论 | 对本项目的影响 |
| --- | --- | --- | --- |
| Windows UI Automation | [Microsoft UI Automation Overview](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview) | UIA 通过桌面 UI 树访问控件；不同用户通过 Run as 启动的进程之间不能直接通信。 | 微信发送必须运行在同一登录用户、同一权限层级下。 |
| Window Station / Desktop | [Microsoft Window Stations](https://learn.microsoft.com/en-us/windows/win32/winstation/window-stations)、[Microsoft Desktops](https://learn.microsoft.com/en-us/windows/win32/winstation/desktops) | 只有交互式窗口站 `WinSta0` 能显示 UI 和接收输入；只有当前 active desktop 接收用户输入；锁屏/UAC 会切换桌面。 | 锁屏、注销、UAC 弹窗时不能可靠操作微信；需要运行条件守卫。 |
| SendInput 与权限 | [Microsoft SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput) | 输入注入受 UIPI 限制，只能注入到同等或更低完整性级别。 | Kangkang 和微信必须同级权限运行；一个管理员一个普通用户会失败。 |
| UI 自动化失败场景 | [Power Automate UIPI issues](https://learn.microsoft.com/en-us/troubleshoot/power-platform/power-automate/desktop-flows/ui-automation/uipi-issues) | 锁屏、UAC、RDP 最小化、目标应用高权限、屏保都可能导致 UI 自动化失败。 | 自检页要把这些列成 P0 条件，不要只显示 Python 异常。 |
| 计划任务 | [Microsoft schtasks](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2012-r2-and-2012/cc725744%28v%3Dws.11%29) | `/IT` 表示仅当运行用户已登录时交互运行；可配置 onlogon、onstart、once、weekly 等触发。 | 微信发送任务应优先使用“用户已登录时运行”的交互式任务。 |
| Tkinter 线程模型 | [Python Tkinter Threading Model](https://docs.python.org/3/library/tkinter.html#threading-model) | Tkinter 是事件驱动，事件处理要快速返回，长任务应拆分或放到线程，结果回到 Tk 事件队列。 | 桌面端所有网络、UIA、自检、打包检查必须后台执行，UI 用 `after` 回填。 |
| PyInstaller 发布 | [PyInstaller usage](https://www.pyinstaller.org/en/stable/usage.html) | `--onedir` 产出带依赖目录，`--onefile` 产出单文件。 | 开发/排障阶段建议保留 onedir；普通用户发 installer；高级用户发 portable。 |
| Open-Meteo | [Open-Meteo Forecast](https://open-meteo.com/en/docs)、[Open-Meteo About](https://open-meteo.com/en/about)、[Geocoding API](https://open-meteo.com/en/docs/geocoding-api) | 无 Key、开放数据、多模型天气源；地理编码支持位置搜索。 | 继续作为默认天气源，但要保留缓存、超时、失败源和查询历史。 |
| wxauto | [cluic/wxauto](https://github.com/cluic/wxauto) | wxauto 也是 Windows 微信客户端 UIAutomation 路线，可发/收消息，但明确有适用与用途限制。 | 可作为可选后端参考，不应在 v3.5 强制替换现有 pywinauto-session。 |
| GitHub 大文件 | [GitHub large files](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) | GitHub 对普通仓库大文件有 50 MiB 警告和 100 MiB 阻止；大二进制应走 Release 或 LFS。 | 不应长期把安装包/EXE 当源码提交；发布资产放 GitHub Release。 |

## 2. 当前项目审计

### 2.1 项目结构

| 区域 | 当前文件/目录 | 结论 |
| --- | --- | --- |
| 入口 | `kangkang_weather.py` | 默认执行 `wechat_weather.cli.main(sys.argv[1:] or ["desktop"])`。 |
| 主包 | `wechat_weather/` | 核心业务代码均在该包内。 |
| 桌面 UI | `wechat_weather/desktop.py` | Tkinter/ttk 桌面程序，左上标题显示版本号。 |
| Web 控制台 | `wechat_weather/server.py`、`wechat_weather/web_console.html` | 内置 HTTP 服务和浏览器控制台。 |
| 天气 | `wechat_weather/weather.py` | Open-Meteo 多模型、wttr 兜底、缓存、历史记录。 |
| 地址 | `wechat_weather/regions.py`、`wechat_weather/regions_level*.json` | 全国省市区数据和搜索解析。 |
| 微信 | `wechat_weather/wechat.py` | wxauto 可选，默认 pywinauto-session。 |
| 自动化 | `wechat_weather/monitor.py`、`wechat_weather/scheduler.py`、`run_daily_weather_task.ps1` | 内部轮询和 Windows 计划任务并存。 |
| 配置 | `wechat_weather/config.py`、`wechat_weather_config.example.json` | JSON 配置，默认在 `%APPDATA%\KangkangWeather\config.json`。 |
| 自检诊断 | `wechat_weather/compat.py`、`wechat_weather/readiness.py`、`wechat_weather/run_trace.py` | 兼容性检查、自动发送就绪检查、运行轨迹。 |
| 打包发布 | `wechat_weather/packaging.py`、`build_exe.ps1`、`kangkang_weather_installer.py` | PyInstaller + 自定义 Tkinter 安装器。 |
| 测试 | `tests/` | 当前 43 个单元/接口/迁移测试通过。 |
| 文档 | `README.md`、`README_PORTABLE.md`、多份 `RELEASE_NOTES_*.md` | 发布文档已有基础，但需要 v3.5 统一。 |

### 2.2 技术栈证据

| 项目 | 判断 | 源码证据 |
| --- | --- | --- |
| UI 框架 | Tkinter/ttk | `wechat_weather/desktop.py` 使用 `tkinter`、`ttk`；没有发现 customtkinter 主路径。 |
| 打包 | PyInstaller | `build_exe.ps1` 调用 `python -m wechat_weather.cli build-package`；`wechat_weather/packaging.py` 使用 PyInstaller 参数。 |
| 安装器 | 自定义 Python/Tkinter 安装器 | `kangkang_weather_installer.py` 复制 payload 到 `%LOCALAPPDATA%\Programs\KangkangWeather`。 |
| 微信自动化 | pywinauto-session 为默认，wxauto 可选 | `requirements-wechat-weather.txt` 包含 `pywinauto`；`wxauto` 注释为 optional；`wechat_weather/wechat.py` 有 `WxautoSender` 和 `PywinautoSessionSender`。 |
| 天气源 | Open-Meteo 多模型 + wttr 兜底 | `wechat_weather/weather.py` 的 `build_weather_snapshot` 使用 `ThreadPoolExecutor` 请求多模型。 |
| 定时任务 | 内部 monitor + Windows schtasks | `wechat_weather/monitor.py` 有 `WeatherMonitor`；`scheduler.py` 调用 `schtasks`。 |
| 配置格式 | JSON | `config.py` 读取/写入 JSON；示例为 `wechat_weather_config.example.json`。 |
| 日志 | 文件日志 + JSON 轨迹 | `run_trace.py`、`compat.py`、PowerShell 脚本日志；日志体系还不够统一。 |
| 测试 | unittest | `python -m unittest discover -s tests -v` 当前通过。 |

### 2.3 当前能力地图

当前已经具备：

- 全国地址选择与地址搜索。
- 完整天气日报模板和发送前缀。
- Open-Meteo 多模型、缓存、查询历史。
- 单微信目标发送、打开会话测试、发送测试消息。
- 自动化任务：运行时间段、固定发送点、轮询检查、风险补发。
- Windows 计划任务修复入口、息屏/电源策略检测入口。
- 兼容性自检与诊断包导出。
- 便携包和安装包构建能力。

当前不完整或需工程化的能力：

- 多个微信好友/群批量发送还没有形成正式批次模型。
- 自动化状态机还不是显式状态机，失败恢复、冲突处理、重试队列不完整。
- 微信 UI 自动化仍依赖真实前台窗口，缺少更清晰的 P0 运行条件守卫。
- 诊断内容丰富，但普通用户看到的 JSON 仍偏多。
- 发布资产与源码仓库边界需要收紧，避免二进制污染 Git 历史。

## 3. 当前界面问题判断

### 3.1 普通用户真正需要的区域

- 当前城市/地址。
- 当前启用的微信目标。
- 今日天气预览。
- 发送前缀。
- 打开会话测试。
- 发送测试消息。
- 发送今日天气。
- 自动化是否开启、下次执行时间、上次结果。
- 最近天气查询记录。
- 兼容性自检和导出诊断包。

### 3.2 偏开发调试的区域

- 原始运行结果 JSON。
- 原始状态与诊断 JSON。
- 后端名称、接口耗时、深层状态对象。
- schtasks 原始输出、powercfg 原始输出。
- 完整 UIA 控件列表。

这些内容不应删除，但应默认折叠到“开发者诊断”区域。

### 3.3 当前主流程问题

当前界面功能很多，但主路径不够强：

1. 选择天气地址。
2. 选择/管理发送对象。
3. 预览今日天气。
4. 先测试微信目标。
5. 正式发送。
6. 再开启自动化。

v3.5.0 应把按钮分级，避免用户第一次打开就被“立即检查、刷新诊断、运行结果 JSON、状态 JSON、导出诊断包”等信息淹没。

## 4. v3.5.0 版本定位

### 4.1 为什么不是 v3.2.0

v3.5.0 不是小修补。它需要引入多对象发送、批次记录、自动化状态机、错误码体系、发布诊断和迁移可用性。这些会影响配置结构、发送流程、测试结构和 UI 信息架构，属于正式发布前的中大型工程升级。

### 4.2 为什么暂不建议 v4.0.0

v4.0.0 通常意味着架构大替换或产品形态重构。当前 Tkinter/ttk、pywinauto-session、Open-Meteo、多源缓存、诊断体系已经能运行。此时换框架或重写会扩大风险，尤其会破坏微信发送这条最敏感的链路。

### 4.3 为什么不现在强行换 UI 框架

当前最大风险不是视觉，而是：

- 锁屏/注销/权限不一致导致微信自动化失败。
- 多目标发送缺少批次和防重复。
- 自动化任务缺少显式状态机。
- 跨电脑迁移时缺少首启引导和可读诊断。

UI 应低风险产品化，而不是换技术栈。

## 5. P0：锁屏、息屏、睡眠与跨权限运行策略

### 5.1 必须对用户说清楚

| 状态 | 天气查询 | 微信发送 | 说明 |
| --- | --- | --- | --- |
| 只关闭屏幕，电脑未睡眠，用户桌面未锁定 | 可以 | 通常可以 | 显示器黑屏不等于锁屏，桌面仍在。 |
| 电脑睡眠/休眠 | 不可以 | 不可以 | 程序不运行，除非计划任务唤醒电脑；唤醒后仍要满足交互条件。 |
| Windows 锁屏 | 天气后台逻辑可能可跑 | 不可靠，不应发送 | 输入桌面切到 Winlogon/锁屏桌面，微信窗口不能可靠接收输入。 |
| 用户注销 | 不可以控制该用户微信 | 不可以 | 用户桌面和微信会话不存在。 |
| UAC 弹窗/安全桌面 | 不可靠 | 不可靠 | Windows 切换到安全桌面。 |
| Kangkang 普通权限、微信管理员权限 | 可能失败 | 高风险失败 | SendInput/UIA 受 UIPI 限制。 |
| Kangkang 管理员权限、微信普通权限 | 可见但不推荐 | 可能带来异常 | 两者最好同级权限，优先普通权限。 |

### 5.2 v3.5.0 要做的 P0 守卫

新增“自动发送就绪灯”，在每次自动发送前执行：

1. 当前用户是否已登录。
2. 当前是否为可交互桌面。
3. 是否处于锁屏、UAC 或屏保。
4. 微信进程/窗口是否存在。
5. 微信是否登录。
6. 微信和 Kangkang 是否同级权限。
7. 是否能找到搜索框和聊天输入框。
8. 是否允许当前时间段发送。

不满足 P0 时：

- 不发送。
- 写入 `automation.log` 和 `send_history.jsonl`。
- UI 显示“已跳过：电脑锁屏/微信不可操作/权限不一致”。
- 如果是固定发送点，进入补偿窗口，唤醒后仍在有效时间内再补发一次。

### 5.3 给别人电脑使用的正确方案

迁移到别人电脑必须走首次向导：

1. 检查 Windows 版本和路径权限。
2. 检查微信是否安装并登录。
3. 检查 Kangkang 与微信是否同级权限。
4. 让用户设置天气地址。
5. 让用户添加微信目标。
6. 先对“文件传输助手”或用户选择目标执行“打开会话测试”。
7. 再执行“发送测试消息”。
8. 测试通过后才允许开启自动化。

不要把本机的私人联系人、缓存、日志、自动化状态直接带到别人电脑上。迁移包只应包含程序、默认配置样例和迁移向导。

## 6. 多对象发送设计

### 6.1 配置结构建议

当前源码已经使用 `wechat_targets`，所以 v3.5.0 不建议立刻改名为 `targets`。建议扩展现有字段，并保留 `targets` 作为未来别名。

建议结构：

```json
{
  "config_version": 3,
  "wechat_targets": [
    {
      "id": "target_001",
      "name": "微信好友或群名",
      "type": "friend",
      "enabled": true,
      "default": true,
      "remark": "",
      "send_mode": "normal",
      "send_interval_seconds": 3,
      "last_send_at": null,
      "last_send_status": null,
      "last_error_code": null,
      "last_error_message": null
    }
  ]
}
```

`type` 支持：

- `friend`
- `group`
- `file_transfer`
- `other`

### 6.2 旧配置迁移

| 旧结构 | 迁移策略 |
| --- | --- |
| `contact` | 生成 1 个 `wechat_targets`。 |
| `recipients` | 每个 recipient 生成一个 `wechat_target`，地址信息迁移到 `locations`。 |
| `wechat_targets` 已存在 | 增补 `type/remark/send_mode/last_*`，不改用户名称。 |
| 默认目标缺失 | 第一个 enabled 目标设为 default；如果没有目标，进入 setup。 |

目标 id 生成策略：

- 首次迁移：`target_default`。
- 新增目标：`target_` + 短 UUID。
- 重名目标：允许存在，但 UI 必须提示“微信搜索可能匹配错误”，发送前要求目标精确校验。

### 6.3 多对象 UI

使用 Tkinter/ttk，推荐 `Treeview`：

| 列 | 内容 |
| --- | --- |
| 启用 | 勾选状态或文字状态。 |
| 名称 | 微信好友/群名称。 |
| 类型 | 好友/群/文件传输助手/其他。 |
| 备注 | 用户自定义。 |
| 上次结果 | 成功/失败/未测试。 |
| 上次时间 | 最近发送或测试时间。 |

按钮分级：

- 主要按钮：`发送今日天气给已启用对象`
- 二级按钮：`添加`、`编辑`、`删除`、`测试选中对象`、`测试全部启用对象`
- 高级按钮：`查看原始诊断`、`导出诊断包`

正式发送前必须显示：

- 本次会发送给几个对象。
- 对象名称摘要。
- 是否存在未测试对象。
- 是否存在重名/相似名称风险。

### 6.4 发送批次模型

新增概念：

```json
{
  "batch_id": "20260503-073000-abc123",
  "trigger": "manual|schedule|retry",
  "location_id": "jiayu",
  "message_hash": "sha256...",
  "started_at": "2026-05-03T07:30:00",
  "finished_at": null,
  "status": "SENDING",
  "targets": [
    {
      "target_id": "target_001",
      "target_name": "微信好友或群名",
      "status": "PENDING",
      "started_at": null,
      "finished_at": null,
      "duration_ms": null,
      "error_code": null,
      "error_message": null,
      "retry_count": 0
    }
  ]
}
```

存储建议：

- 当前运行批次：`%APPDATA%\KangkangWeather\state\current_send_batch.json`
- 发送历史：`%APPDATA%\KangkangWeather\history\send_history.jsonl`
- 任务锁：`%APPDATA%\KangkangWeather\locks\send_task.lock`

### 6.5 防重复机制

必须同时使用：

- `batch_id`
- `target_id`
- `message_hash`
- `last_send_at`
- `minimum_send_interval_seconds`
- `send_task.lock`

规则：

- 同一目标、同一消息 hash、短时间内不重复发送。
- 手动发送优先级高于自动发送，但如果已有发送批次进行中，手动发送应提示“正在发送，是否排队/取消/稍后再试”。
- 自动发送遇到手动发送中的锁，默认跳过并进入补偿窗口。
- 程序异常退出后，如果锁文件超过合理 TTL，标记为 stale lock，允许用户一键解锁。

## 7. 自动化状态机设计

### 7.1 状态定义

```text
IDLE
SCHEDULED
PREPARING
CHECKING_READINESS
FETCHING_WEATHER
RENDERING_MESSAGE
SENDING
RETRYING
PARTIAL_SUCCESS
SUCCESS
FAILED
SKIPPED
CANCELLED
RECOVERING
```

### 7.2 状态转移

| 当前状态 | 触发 | 下一个状态 | 记录内容 |
| --- | --- | --- | --- |
| `IDLE` | 加载任务 | `SCHEDULED` | job_id、next_run_at |
| `SCHEDULED` | 到达固定发送点 | `PREPARING` | trigger=`fixed_time` |
| `SCHEDULED` | 到达轮询间隔 | `PREPARING` | trigger=`interval` |
| `PREPARING` | 开始检查环境 | `CHECKING_READINESS` | batch_id |
| `CHECKING_READINESS` | 不满足 P0 | `SKIPPED` | readiness_error |
| `CHECKING_READINESS` | 通过 | `FETCHING_WEATHER` | readiness_ok |
| `FETCHING_WEATHER` | 成功 | `RENDERING_MESSAGE` | source_count、elapsed_ms |
| `FETCHING_WEATHER` | 失败且无缓存 | `FAILED` | weather_error |
| `RENDERING_MESSAGE` | 有可发送对象 | `SENDING` | target_count |
| `SENDING` | 全部成功 | `SUCCESS` | success_count |
| `SENDING` | 部分失败可重试 | `RETRYING` | failed_targets |
| `RETRYING` | 部分仍失败 | `PARTIAL_SUCCESS` | retry_summary |
| 任意 | 用户取消 | `CANCELLED` | operator_action |
| 启动时发现未完成批次 | 恢复 | `RECOVERING` | stale_batch |

### 7.3 手动与定时冲突策略

推荐策略：

- 一个全局发送锁，避免微信窗口被两个任务同时控制。
- 手动发送遇到定时任务正在发送：提示用户“等待当前任务完成/取消本次/查看进度”。
- 定时任务遇到手动发送正在进行：自动跳过本次，并记录“被手动任务占用”；固定发送点进入补偿窗口。
- 不允许两个线程同时操作微信。

### 7.4 睡眠/唤醒补偿

规则：

- 固定发送点错过后，默认补偿窗口 60 分钟。
- 唤醒后如果仍在补偿窗口、当天未发送同一固定点，则补发一次。
- 如果电脑唤醒但锁屏未解锁，只记录待补偿，不强行发送。
- 超过补偿窗口则标记 `SKIPPED_EXPIRED`，不再补发，避免下午补早报。

### 7.5 重试策略

| 错误 | 是否重试 | 策略 |
| --- | --- | --- |
| 天气源超时 | 是 | 立即换缓存/备用源；下次轮询重试。 |
| 微信未启动 | 否 | 提示用户打开并登录微信。 |
| 微信锁屏不可操作 | 否 | 等下次环境可用。 |
| 目标未找到 | 否 | 用户需要改目标名。 |
| 输入框焦点失败 | 是 | 同一目标最多重试 1 次，重新打开会话。 |
| Enter 发送未提交 | 是 | 尝试 Ctrl+Enter；仍失败则停止。 |
| 权限不一致 | 否 | 用户需调整运行权限。 |
| 微信窗口消失 | 否 | 停止批次，避免继续输入。 |

## 8. 微信发送可靠性设计

### 8.1 当前实现识别

当前源码中存在：

- `Sender` 协议：`wechat_weather/wechat.py`
- `WxautoSender`：可选 wxauto 后端。
- `PywinautoActiveChatSender`：面向当前聊天输入框。
- `PywinautoSessionSender`：默认会话搜索/打开/发送。
- `collect_diagnostics()`：采集微信窗口与控件诊断。

v3.5.0 应把现有 `Sender` 扩展为更正式的 `WeChatSender`：

```python
class WeChatSender:
    def check_environment(self) -> CheckResult:
        ...

    def open_session(self, target: SendTarget) -> CheckResult:
        ...

    def send_message(self, target: SendTarget, message: str) -> SendResult:
        ...

    def test_target(self, target: SendTarget) -> SendResult:
        ...
```

### 8.2 错误码体系

| 错误码 | 用户提示 | 是否可重试 |
| --- | --- | --- |
| `WECHAT_NOT_RUNNING` | 没有找到已打开的 Windows 微信，请先打开微信。 | 否 |
| `WECHAT_NOT_LOGIN` | 微信可能未登录，请登录后重试。 | 否 |
| `DESKTOP_LOCKED` | 当前电脑处于锁屏/安全桌面，无法自动发送。 | 稍后 |
| `PERMISSION_MISMATCH` | Kangkang 和微信权限级别不一致，请都用普通权限运行。 | 否 |
| `TARGET_NOT_FOUND` | 搜索不到目标好友或群，请确认名称完全一致。 | 否 |
| `TARGET_AMBIGUOUS` | 搜索结果存在相似名称，请改用更准确名称或备注。 | 否 |
| `TARGET_MISMATCH` | 打开的会话标题和目标不一致，已停止发送。 | 否 |
| `INPUT_NOT_FOCUSED` | 找不到或无法聚焦微信输入框。 | 是 |
| `PASTE_FAILED` | 消息写入输入框失败。 | 是 |
| `SEND_NOT_SUBMITTED` | 消息已写入但没有提交发送。 | 是 |
| `WECHAT_WINDOW_GONE` | 操作过程中微信窗口消失或异常退出。 | 否 |
| `USER_INTERRUPTED` | 发送过程中用户操作打断了微信窗口。 | 是 |
| `UNKNOWN_WECHAT_ERROR` | 微信自动化未知异常，请导出诊断包。 | 视情况 |

### 8.3 发送流程

每个目标单独执行：

1. 获取全局发送锁。
2. 检查交互桌面和权限。
3. 扫描微信窗口并打分选择。
4. 恢复微信窗口到前台。
5. 当前会话标题匹配则直接使用。
6. 左侧可见会话精确匹配则点击。
7. UIA 搜索框写入目标名。
8. 搜索结果必须精确匹配。
9. 打开后再次校验聊天标题。
10. 聚焦输入框。
11. 写入消息：优先直接 ValuePattern/控件文本，其次剪贴板，最后 Unicode 输入。
12. 校验输入框中出现消息 marker。
13. Enter 发送，失败再 Ctrl+Enter。
14. 校验输入框清空或不再包含 marker。
15. 记录 target result。

### 8.4 不要承诺完全后台发送

本项目不能承诺“锁屏也能通过官方微信发消息”。可做到的是：

- 自动识别并恢复微信窗口。
- 自动检查是否处于可交互桌面。
- 显示器可关闭，但电脑不能睡眠，桌面不能锁屏。
- 失败时不误发、不乱点、不闪退，而是给出可读原因。

## 9. Bug 风险与治理方案

| 等级 | 问题 | 相关文件 | 复现方式 | 修复建议 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| S0 | 锁屏/注销/权限不一致时自动发送失败或误判 | `readiness.py`、`wechat.py`、`monitor.py` | 锁屏后等待固定发送点 | 自动发送前强制 readiness gate；不满足直接 SKIPPED | 锁屏时不发送，日志显示 `DESKTOP_LOCKED` |
| S0 | 多对象发送缺少批次锁导致重复发送 | `monitor.py`、`server.py`、待新增 `send_batch.py` | 连续点击发送或定时同时触发 | 全局 send lock + batch_id + message_hash | 并发点击只产生一个有效批次 |
| S0 | 目标会话误匹配导致发错人 | `wechat.py` | 目标名相似 | 搜索结果和聊天标题双重精确校验 | 标题不一致时停止发送 |
| S1 | 固定发送点错过后的补偿规则不够显式 | `monitor.py` | 睡眠跨过固定时间 | 状态机记录 `fixed_pending`、补偿窗口和过期 | 唤醒后只补一次，过期不补 |
| S1 | 自动化任务状态分散，排障困难 | `monitor.py`、`run_trace.py` | 自动化失败后查看状态 | 显式状态机与 JSONL 轨迹 | UI 可看到当前状态和失败步骤 |
| S1 | 微信窗口更新后控件结构变化 | `wechat.py` | 更新微信版本 | 多后端探测、错误码、诊断导出 | 能定位为控件不可用而非崩溃 |
| S1 | 天气请求偶发超时导致 UI 卡或启动异常 | `weather.py`、`desktop.py` | 断网或 Open-Meteo 慢 | 所有请求后台化、统一超时、缓存兜底 | UI 不阻塞，提示可读 |
| S2 | `monitor.py` 存在两个 `_send_fixed_weather` 定义 | `monitor.py` | 阅读源码即可发现 | 合并为一个实现并加测试 | 文件内只保留一个定义 |
| S2 | JSON 诊断默认暴露过多 | `desktop.py`、`web_console.html` | 普通用户打开主界面 | 默认折叠到开发者模式 | 主界面只显示摘要 |
| S2 | Git 仓库存储大安装包风险 | 发布流程 | 提交 50 MiB+ EXE | 二进制走 GitHub Release，不进源码历史 | 源码仓库无大二进制 |
| S2 | PowerShell 脚本路径依赖源码布局 | `run_daily_weather_task.ps1`、`start_wechat_weather_console.ps1` | 安装后从非源码目录启动 | 脚本从安装目录和 `%APPDATA%` 查找资源 | 安装版/便携版均可运行 |
| S3 | 日志分散 | `compat.py`、`run_trace.py`、脚本日志 | 导出诊断包 | 统一日志目录和文件名 | 诊断包包含关键日志 |

## 10. 配置系统升级

### 10.1 配置版本

建议 v3.5.0 写入：

```json
{
  "config_version": 3,
  "app": {
    "name": "KangkangWeather",
    "version": "3.5.0"
  }
}
```

### 10.2 路径策略

当前项目已使用 `%APPDATA%\KangkangWeather` 作为用户配置目录。v3.5.0 继续沿用：

- `%APPDATA%\KangkangWeather\config.json`
- `%APPDATA%\KangkangWeather\logs\`
- `%APPDATA%\KangkangWeather\cache\`
- `%APPDATA%\KangkangWeather\history\`
- `%APPDATA%\KangkangWeather\diagnostics\`
- `%APPDATA%\KangkangWeather\state\`
- `%APPDATA%\KangkangWeather\locks\`

安装程序仍建议安装到：

- `%LOCALAPPDATA%\Programs\KangkangWeather`

### 10.3 配置损坏恢复

流程：

1. 读取 `config.json`。
2. JSON 解析失败时复制为 `config.corrupt.YYYYMMDD-HHMMSS.json`。
3. 尝试读取最近一次 `config.backup.json`。
4. 备份也失败则进入 setup。
5. UI 显示“配置文件损坏，已备份并进入重新设置”。

### 10.4 迁移验收

- v2.x `contact/recipients` 能迁移。
- v3.1.1 `wechat_targets/automation_jobs` 能迁移。
- 已有用户配置不丢目标名、地址、固定时间、前缀。
- 新电脑首次运行不继承本机私人联系人。

## 11. 日志与诊断设计

### 11.1 日志文件

| 文件 | 内容 |
| --- | --- |
| `app.log` | 启动、退出、端口、配置路径、版本。 |
| `weather.log` | 天气请求、源失败、缓存命中、耗时。 |
| `wechat.log` | 微信窗口、目标搜索、输入、发送、错误码。 |
| `automation.log` | 状态机、定时任务、跳过、补偿、重试。 |
| `send_history.jsonl` | 每个批次和目标发送结果。 |
| `error.log` | 未捕获异常和关键错误摘要。 |

### 11.2 诊断包内容

包含：

- app_version、build_time、Python 版本。
- 是否 PyInstaller 环境。
- Windows 版本。
- 配置路径和脱敏配置。
- 最近 app/weather/wechat/automation/error 日志。
- 最近 send_history。
- 最近 weather_fetch_history。
- readiness 检查结果。
- 微信窗口摘要。
- 任务计划状态。
- 电源策略摘要。

不包含：

- 聊天记录。
- 微信账号数据。
- 完整消息正文。
- 未脱敏好友/群名，除非用户显式允许。

### 11.3 用户可读错误

任何发送失败都不应只展示 traceback。必须展示：

- 一句话结论。
- 可能原因。
- 用户下一步操作。
- 是否需要导出诊断包。
- 原始错误折叠在开发者区域。

## 12. 低风险 UI 产品化方案

### 12.1 主界面重排

建议主界面分 5 个区域：

1. 顶部状态栏：版本、城市、启用对象数、自动化状态、下次执行时间。
2. 今日天气预览：最终发送文本和刷新按钮。
3. 发送对象：目标列表、测试、管理入口。
4. 操作区：发送测试消息、发送今日天气、自动化设置。
5. 结果与诊断：默认摘要，开发者模式展开 JSON。

### 12.2 按钮分级

一级：

- `发送今日天气`

二级：

- `刷新天气`
- `测试选中对象`
- `测试全部对象`
- `自动化设置`

高级：

- `兼容性自检`
- `导出诊断包`
- `刷新原始诊断`
- `查看原始 JSON`

### 12.3 多对象管理弹窗

保持 ttk：

- Treeview 列表。
- 右侧或底部表单编辑。
- 单对象测试按钮。
- 批量测试按钮。
- 保存前校验重名和空名称。

### 12.4 自动化设置弹窗

分组：

- 运行时间段。
- 固定发送点。
- 补偿窗口。
- 发送对象范围。
- 跳过条件。
- 重试规则。

小窗口必须可滚动到底部。

## 13. Windows 发布方案

### 13.1 当前判断

当前发布更像组合方案：

- PyInstaller `--onefile --windowed` 生成主 EXE。
- zip 便携包。
- 自定义 Python/Tkinter 安装器。
- PowerShell 脚本辅助启动与计划任务。

### 13.2 v3.5.0 推荐发布形态

| 形态 | 面向用户 | 说明 |
| --- | --- | --- |
| Installer | 普通用户 | 安装到 `%LOCALAPPDATA%\Programs\KangkangWeather`，创建快捷方式。 |
| Portable zip | 高级用户/测试 | 解压即用，便于诊断。 |
| onedir debug build | 开发/排障 | 依赖文件展开，便于定位缺失资源。 |

### 13.3 必测矩阵

- Windows 10 64 位。
- Windows 11 64 位。
- DPI：100%、125%、150%。
- 中文用户名路径。
- 带空格路径。
- 普通权限运行。
- 微信普通权限运行。
- 微信未启动。
- 微信未登录。
- 微信最小化。
- 锁屏。
- 显示器关闭但未锁屏。
- 电脑睡眠后唤醒。
- UAC 弹窗。
- 杀毒软件扫描。
- 断网。
- Open-Meteo 超时。
- 旧配置迁移。
- 卸载后重装。

### 13.4 GitHub 发布规则

- 源码仓库提交源码、测试、文档、脚本。
- EXE、zip、安装器上传 GitHub Release。
- 不把 50 MiB 以上二进制长期放普通 Git 历史。
- Release 附 `SHA256SUMS`。
- Release Notes 同时面向普通用户和开发者。

## 14. 测试计划

### 14.1 单元测试

新增测试：

- 多目标配置迁移。
- 目标启用/禁用筛选。
- 目标排序。
- batch_id 生成。
- message_hash 生成。
- 防重复逻辑。
- stale lock 处理。
- 自动化状态转移。
- 固定发送点补偿。
- 锁屏/权限 readiness 错误映射。
- 错误码到用户提示映射。
- 配置损坏备份恢复。
- 诊断包脱敏。

### 14.2 集成测试

- 天气查询到消息生成。
- 单目标发送 dry-run。
- 多目标发送 dry-run。
- 部分失败汇总。
- 自动化固定发送 dry-run。
- 自动化轮询补发 dry-run。
- 诊断包导出。
- setup 迁移。
- packaged resource path。

### 14.3 手动测试

- 微信未启动。
- 微信未登录。
- 目标好友不存在。
- 群名相似。
- 用户连续点击发送。
- 发送过程中切窗口。
- 发送过程中微信关闭。
- 锁屏后等待定时点。
- 睡眠后唤醒补偿。
- 别人电脑首次安装。
- 中文路径和非管理员运行。

### 14.4 回归测试

必须保证：

- 当前单目标发送仍可用。
- 当前地址选择仍可用。
- 当前天气预览仍可用。
- 当前固定发送点仍可用。
- 当前诊断包仍可导出。
- 当前安装包/便携包仍可构建。

## 15. 具体执行任务清单

### 阶段 0：建立安全基线

| 任务 | 文件 | 目标 | 验收 |
| --- | --- | --- | --- |
| T0.1 记录当前入口和版本 | `kangkang_weather.py`、`config.py` | 形成 baseline 文档 | 文档列明启动路径和版本。 |
| T0.2 固定 smoke test | `tests/` | 新增或整理 smoke checklist | `compileall` 和 unittest 通过。 |
| T0.3 运行条件说明 | `README.md`、`TROUBLESHOOTING.md` | 明确锁屏/睡眠/权限限制 | 用户文档能解释为什么锁屏不能发。 |
| T0.4 诊断基线 | `compat.py`、`readiness.py` | 记录当前诊断字段 | 导出包包含版本、路径、readiness。 |

### 阶段 1：多对象发送底层能力

| 任务 | 文件 | 目标 | 验收 |
| --- | --- | --- | --- |
| T1.1 SendTarget/Batch 模型 | 新增 `send_batch.py` 或扩展 `wechat.py` | 批次与目标结果结构化 | 单元测试覆盖序列化。 |
| T1.2 配置扩展 | `config.py` | `wechat_targets` 增加 type/remark/last_* | 旧配置迁移不丢数据。 |
| T1.3 多目标 dry-run | `server.py`、`monitor.py` | 批量发送前可预演 | UI 显示将发送名单。 |
| T1.4 防重复锁 | 新增 `locks.py` 或 `send_batch.py` | 防并发和重复发送 | 连点发送只生成一个 active batch。 |
| T1.5 发送历史 | `send_history.jsonl` | 每目标记录结果 | 可查询最近 50 条。 |

### 阶段 2：自动化稳定性

| 任务 | 文件 | 目标 | 验收 |
| --- | --- | --- | --- |
| T2.1 状态机 | `monitor.py` | 显式状态转移 | 单元测试覆盖主要状态。 |
| T2.2 手动/定时冲突 | `monitor.py`、`server.py` | 统一锁和队列策略 | 定时和手动不会同时操作微信。 |
| T2.3 补偿窗口 | `monitor.py` | 睡眠唤醒后有限补发 | 固定点错过只补一次。 |
| T2.4 重试策略 | `monitor.py` | 只重试可恢复错误 | 不会对目标不存在无限重试。 |

### 阶段 3：微信可靠性

| 任务 | 文件 | 目标 | 验收 |
| --- | --- | --- | --- |
| T3.1 WeChatSender 接口 | `wechat.py` | 环境检查/打开/发送/测试拆开 | mock 测试通过。 |
| T3.2 readiness gate | `readiness.py`、`wechat.py` | 自动发送前拦截锁屏/权限问题 | 锁屏返回 `DESKTOP_LOCKED`。 |
| T3.3 错误码统一 | `error_analysis.py`、`wechat.py` | 所有错误可读 | UI 不只显示 traceback。 |
| T3.4 目标精确校验 | `wechat.py` | 防发错对象 | 标题不一致停止。 |
| T3.5 微信异常退出处理 | `wechat.py` | 窗口消失立即停止 | 返回 `WECHAT_WINDOW_GONE`。 |

### 阶段 4：UI 产品化

| 任务 | 文件 | 目标 | 验收 |
| --- | --- | --- | --- |
| T4.1 主界面重排 | `desktop.py`、`web_console.html` | 主流程清晰 | 新用户 3 步内能测试发送。 |
| T4.2 多对象管理 | `desktop.py`、`server.py` | 添加/编辑/测试目标 | Treeview 正常显示。 |
| T4.3 诊断折叠 | `desktop.py`、`web_console.html` | JSON 默认折叠 | 普通界面不被 JSON 占满。 |
| T4.4 可读错误 | `desktop.py`、`error_analysis.py` | 错误有下一步建议 | 失败弹窗可直接指导用户。 |

### 阶段 5：正式发布适配

| 任务 | 文件 | 目标 | 验收 |
| --- | --- | --- | --- |
| T5.1 onedir debug build | `packaging.py` | 生成排障构建 | onedir 可启动。 |
| T5.2 安装器升级 | `kangkang_weather_installer.py` | 保留配置、支持升级 | 覆盖安装不丢配置。 |
| T5.3 发布文档 | `README.md`、`FAQ.md`、`TROUBLESHOOTING.md` | 用户可自行排障 | 文档覆盖锁屏/微信/权限。 |
| T5.4 Release checklist | `docs/RELEASE_CHECKLIST.md` | 发布前逐项检查 | v3.5.0 可按清单验收。 |

## 16. 风险清单

| 风险 | 等级 | 触发场景 | 后果 | 规避 | 检测 | 回滚 |
| --- | --- | --- | --- | --- | --- | --- |
| 微信版本更新导致控件变化 | S0 | 微信升级 | 发送失败或误匹配 | 精确校验、诊断、后端抽象 | 打开会话测试 | 回退到旧发送策略 |
| 锁屏/注销时自动发送 | S0 | 固定发送点电脑锁屏 | 失败或卡住 | readiness gate | `DESKTOP_LOCKED` | 跳过并补偿 |
| 多目标重复发送 | S0 | 连点或定时冲突 | 重复打扰用户 | batch lock/message_hash | send_history | stale lock 解锁 |
| 发错好友/群 | S0 | 名称相似 | 严重事故 | 搜索结果+标题双校验 | target mismatch | 停止发送 |
| UI 主线程卡住 | S1 | 网络慢/UIA 慢 | 界面无响应 | 后台线程 + after | UI 响应测试 | 回退同步调用 |
| 配置迁移失败 | S1 | 旧配置字段缺失 | 首启失败 | 备份和迁移测试 | setup 测试 | 使用备份配置 |
| 诊断包泄露隐私 | S1 | 用户分享诊断 | 隐私风险 | 脱敏、hash 消息正文 | 诊断包测试 | 停用敏感字段 |
| PowerShell 策略限制 | S2 | 脚本执行被禁 | 计划任务失败 | EXE 内部调度 + 文档 | scheduler status | 手动启动 |
| 杀毒误报 | S2 | PyInstaller EXE | 用户无法安装 | Release 说明、签名规划 | 下载反馈 | portable/源码运行 |
| 大文件污染 Git 仓库 | S2 | 提交 EXE | 仓库变慢 | Release Assets | git status/size | 清理历史 |

## 17. 不要做清单

v3.5.0 不要做：

1. 不要重写整个项目。
2. 不要强行切换 PyQt/Electron/Web 技术栈。
3. 不要为了视觉效果牺牲微信发送稳定性。
4. 不要删除现有 JSON 诊断，只能折叠到开发者模式。
5. 不要把天气文案模板当成本轮主线。
6. 不要一口气同时大改 UI、微信发送、定时任务和打包。
7. 不要在没有回归测试前改微信核心发送逻辑。
8. 不要默认所有用户有管理员权限。
9. 不要默认微信窗口结构固定不变。
10. 不要承诺锁屏/注销状态下能通过官方微信发送。
11. 不要默认 PowerShell 脚本在所有电脑可执行。
12. 不要让错误提示只显示 Python traceback。
13. 不要把 EXE/安装包长期提交到源码仓库。

## 18. 用户版更新日志草稿

### Kangkang Weather v3.5.0

- 新增多个微信好友/群批量发送。
- 新增发送前确认名单，减少发错对象风险。
- 自动化发送更稳定，支持任务状态、失败原因和补偿记录。
- 微信发送前会检查电脑是否锁屏、微信是否登录、权限是否一致。
- 优化首次安装和迁移到别人电脑的设置流程。
- 优化错误提示，不再只显示看不懂的 Python 报错。
- 诊断包更完整，同时默认脱敏隐私信息。
- 普通界面更简洁，开发者诊断信息默认折叠。

## 19. 开发者版更新日志草稿

### Kangkang Weather v3.5.0

- Introduce send batch model with `batch_id`, per-target result and JSONL history.
- Extend `wechat_targets` schema for multi-target delivery metadata.
- Add explicit automation state machine and conflict handling.
- Add readiness gate for interactive desktop, permission level, WeChat availability and locked desktop.
- Normalize WeChat automation error codes and user-facing error analysis.
- Add stale lock recovery and duplicate send protection.
- Improve diagnostics export with redaction and categorized logs.
- Add release flow guidance for installer, portable and onedir debug builds.

## 20. Release Checklist

- [ ] `APP_VERSION` 更新到 `3.5.0`。
- [ ] `config_version` 迁移测试通过。
- [ ] `python -m compileall wechat_weather tests` 通过。
- [ ] `python -m unittest discover -s tests -v` 通过。
- [ ] Win10 普通权限测试通过。
- [ ] Win11 普通权限测试通过。
- [ ] 100%/125%/150% DPI 测试通过。
- [ ] 中文路径测试通过。
- [ ] 首次安装 setup 流程通过。
- [ ] 旧配置迁移通过。
- [ ] 文件传输助手发送测试通过。
- [ ] 普通好友/群打开会话测试通过。
- [ ] 锁屏时自动发送被正确跳过。
- [ ] 睡眠唤醒补偿测试通过。
- [ ] 多目标 dry-run 通过。
- [ ] 多目标真实发送只在测试名单内执行。
- [ ] 诊断包脱敏检查通过。
- [ ] installer 构建通过。
- [ ] portable zip 构建通过。
- [ ] onedir debug build 构建通过。
- [ ] `SHA256SUMS` 生成。
- [ ] Release Notes 完成。
- [ ] GitHub Release 上传资产。

## 21. Bug Report 模板

```markdown
# Kangkang Weather 问题反馈

## 基本信息
- 软件版本：
- Windows 版本：
- 微信版本：
- 使用安装版还是便携版：
- 是否管理员运行 Kangkang：
- 是否管理员运行微信：
- 是否使用远程桌面：
- 出问题时电脑是否锁屏/睡眠/息屏：

## 发送对象
- 对象类型：好友 / 群 / 文件传输助手 / 其他
- 对象名称是否与微信搜索结果完全一致：

## 问题描述

## 复现步骤
1.
2.
3.

## 期望结果

## 实际结果

## 是否稳定复现
- 每次都出现 / 偶尔出现 / 只出现一次

## 已尝试操作
- 打开会话测试：
- 发送测试消息：
- 兼容性自检：

## 诊断包
- 是否已导出诊断包：
- 诊断包文件名：

## 截图或补充说明
```

## 22. 下一步执行建议

第一阶段应先改这些文件：

- `wechat_weather/config.py`
- `wechat_weather/monitor.py`
- `wechat_weather/wechat.py`
- `wechat_weather/error_analysis.py`
- `wechat_weather/readiness.py`
- `wechat_weather/server.py`
- `wechat_weather/desktop.py`
- `tests/`

不能马上做：

- 不能马上替换 UI 框架。
- 不能马上宣称支持锁屏微信发送。
- 不能在没有批次锁的情况下上线多目标真实发送。
- 不能把多目标真实发送直接默认开启。

需要先加测试：

- 多目标配置迁移。
- 批次锁。
- 防重复。
- 状态机。
- readiness gate。
- 微信错误码映射。
- 诊断包脱敏。

需要人工验证：

- 真实微信打开会话测试。
- 文件传输助手真实发送。
- 普通好友/群只做会话测试。
- 锁屏/息屏/睡眠差异。
- 别人电脑首次安装迁移。

## 23. 下一条给 Codex 的执行提示词

```text
请按照 docs/NEXT_ITERATION.md 执行 v3.5.0 的阶段 0 和阶段 1。

限制：
- 不重写项目。
- 不换 UI 框架。
- 不直接改微信发送核心流程，除非先补测试。
- 多目标真实发送必须先支持 dry-run、批次记录和防重复锁。
- 保持现有 43 个测试通过。

优先任务：
1. 在 config.py 中扩展 wechat_targets 字段并保持旧配置迁移。
2. 新增发送批次模型、batch_id、message_hash、send_history.jsonl。
3. 新增全局 send_task.lock 和 stale lock 恢复。
4. 在 server.py 暴露多目标 dry-run 预览接口。
5. 补充单元测试覆盖配置迁移、多目标筛选、批次汇总、防重复和锁。

执行后请运行：
- python -m compileall wechat_weather tests
- python -m unittest discover -s tests -v

完成后汇报修改文件、测试结果、风险和下一阶段建议。
```
