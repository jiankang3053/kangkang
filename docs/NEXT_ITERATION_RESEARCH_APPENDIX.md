# Kangkang Weather v3.5.0 迭代调研补充附录

> 用途：本文件用于补充到 `docs/NEXT_ITERATION.md`，并作为下一轮工程执行提示词来源。  
> 生成日期：2026-05-04  
> 重要校正：原调研提示词写“当前版本约 v3.1.1”，但当前仓库实际已是 `APP_VERSION = "3.5.0"`，且已有部分多对象发送、发送历史、配置版本和打包资产基础。下一轮应基于当前代码继续收敛，不要从旧版本设想重做。

## 1. 建议追加到“外部参考调研”的内容

````markdown
### 外部调研补充：同类天气工具、Windows 工具和自动化发布体系

本轮补充调研了天气展示类、天气 Bot、Windows 桌面工具、自动化调度工具、PyInstaller 打包和 GitHub 发布规范。结论如下：

1. 天气类项目如 [Breezy Weather](https://github.com/breezy-weather/breezy-weather)、[wttr.in](https://github.com/chubin/wttr.in)、[Open-Meteo](https://open-meteo.com/en/docs) 的成熟方向是小时级预报、多日预报、多源、缓存、降雨概率、AQI/UV 和天气预警。但 Kangkang Weather 当前不应把展示功能放在第一位，天气能力应服务于“是否需要提醒”和“消息是否可信”。
2. 天气 Bot 类项目如 [Discord WeatherBot](https://github.com/smmhrdmn/WeatherBot)、[Telegram Weather Forecast Bot](https://github.com/artur-sannikov/weather-forecast-bot-on-Telegram)、[Weatherbot](https://pypi.org/project/weatherbot/) 的共同点是订阅对象、多地点、异常提醒、发送历史和失败重试。Kangkang 应重点吸收“多对象 + 多城市绑定 + 发送历史 + 只重试失败对象”，但明确不做营销群发和聊天内容读取。
3. Windows 工具如 [PowerToys](https://learn.microsoft.com/en-us/windows/powertoys/)、[GitHub Desktop](https://github.com/desktop/desktop/releases)、[ShareX](https://github.com/ShareX/ShareX/releases)、[AutoHotkey](https://www.autohotkey.com/docs/v2/) 的迭代经验是：正式工具必须重视配置备份恢复、托盘/自启、诊断日志、错误提示、Release Notes、Issue 模板和安装/便携双形态。
4. 自动化任务参考 [APScheduler](https://apscheduler.readthedocs.io/en/stable/userguide.html) 和 [schedule](https://schedule.readthedocs.io/en/stable/index.html)。APScheduler 的 job store、executor、misfire、coalescing 可作为状态机设计参考；schedule 文档明确简单轮询不会自动补跑错过任务，说明 Kangkang 必须显式记录固定发送点是否错过、是否补发、是否过期。
5. 打包发布参考 [PyInstaller runtime](https://pyinstaller.org/en/stable/runtime-information.html)、[PyInstaller operating mode](https://pyinstaller.org/en/v5.13.1/operating-mode.html) 和 [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。Kangkang 必须区分源码运行、onefile、onedir、installer、portable，并把用户配置和日志放在 `%APPDATA%\KangkangWeather`。
6. 发布规范参考 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)、[Semantic Versioning](https://semver.org/)、[GitHub Issue Templates](https://docs.github.com/articles/configuring-issue-templates-for-your-repository)、[Generated Release Notes](https://docs.github.com/repositories/releasing-projects-on-github/automatically-generated-release-notes)。v3.5.x 应进入正式发布纪律：CHANGELOG、Release checklist、SHA256SUMS、Bug 模板、诊断包。
7. 微信 UI 自动化限制必须长期写入文档和自检逻辑：[Microsoft UI Automation](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview)、[Power Automate UIPI Issues](https://learn.microsoft.com/en-us/troubleshoot/power-platform/power-automate/desktop-flows/ui-automation/uipi-issues)、[SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)、[Window Stations](https://learn.microsoft.com/en-us/windows/win32/winstation/window-stations) 都说明官方 Windows 桌面 UI 自动化依赖交互式桌面、同级权限和可访问窗口。Kangkang 不能承诺锁屏/注销/权限错层下稳定发送。
````

## 2. 建议追加到“新版功能范围”的内容

````markdown
### v3.5.x 新版功能范围补充

v3.5.x 的范围应聚焦“正式发布前的稳定性和多对象发送闭环”，不再把核心时间投入到天气模板、视觉效果或大框架替换上。

进入范围：

- 多对象发送：目标列表、启用/禁用、单对象测试、批量测试、发送批次、发送历史、只重试失败对象。
- 自动化稳定：全局发送锁、手动/定时冲突处理、固定发送点补偿窗口、轮询短提醒去重、明确 skipped/failed/success 状态。
- 微信发送守卫：发送前 readiness gate，检查微信是否运行和登录、是否锁屏、是否交互式桌面、是否权限不一致、目标会话是否精确匹配。
- 可读诊断：错误码、用户可读提示、开发者 JSON 折叠、诊断包脱敏、日志增强。
- 配置与迁移：`config_version`、旧配置迁移、配置损坏备份恢复、配置导出/导入的设计。
- 发布适配：installer、portable zip、onedir debug build、SHA256SUMS、CHANGELOG、Release checklist、GitHub Issue 模板。

不进入范围：

- 云账号系统。
- 微信聊天内容读取。
- 微信营销群发。
- 多账号微信。
- 大型数据库。
- 插件市场。
- 大规模 UI 框架替换。
- 完全后台无窗口微信发送承诺。
````

## 3. 建议追加到“多对象发送设计”的内容

````markdown
### 多对象发送补充设计：SendTarget / SendResult / SendBatch

多对象发送必须先建立结构化模型，再改 UI。推荐模型：

```json
{
  "target": {
    "id": "target_001",
    "name": "微信好友或群名",
    "type": "friend|group|file_transfer|other",
    "enabled": true,
    "default": false,
    "remark": "",
    "last_test_at": null,
    "last_send_at": null,
    "last_error_code": null
  },
  "result": {
    "target_id": "target_001",
    "target_name": "微信好友或群名",
    "status": "pending|sending|success|failed|skipped",
    "error_code": null,
    "error_message": null,
    "retryable": false,
    "started_at": null,
    "finished_at": null,
    "duration_ms": null
  },
  "batch": {
    "batch_id": "20260504-073000-abc123",
    "trigger": "manual|fixed_time|interval_alert|retry|test",
    "message_hash": "sha256...",
    "dry_run": false,
    "targets": []
  }
}
```

实现规则：

- 单对象发送路径必须继续可用。
- 批量发送默认只发送 enabled 对象。
- 发送前展示名单和目标数。
- 所有目标串行发送，中间加间隔。
- 每个目标打开会话后必须标题精确校验。
- 已成功目标不参与“只重试失败对象”。
- 发送历史不保存完整消息正文，只保存摘要、hash、目标结果和错误码。
- 多目标功能不得用于营销群发；文档中明确限制建议目标数量。
````

## 4. 建议追加到“自动化稳定性设计”的内容

````markdown
### 自动化稳定性补充：状态机、锁、错过任务和交互桌面守卫

自动化任务建议统一进入状态机：

```text
IDLE
SCHEDULED
PREPARING
CHECKING_READINESS
FETCHING_WEATHER
RENDERING_MESSAGE
SENDING
RETRYING
SUCCESS
PARTIAL_SUCCESS
FAILED
SKIPPED
RECOVERING
```

每次自动化执行必须先拿全局发送锁：

- 锁路径：`%APPDATA%\KangkangWeather\locks\send_task.lock`
- 锁内容：`owner`、`batch_id`、`created_at`、`expires_at`
- 锁过期：标记 stale，允许恢复或一键释放

发送前 readiness gate：

- 当前是否为交互式桌面。
- 电脑是否锁屏、UAC 安全桌面、RDP 最小化或屏保状态。
- 微信是否运行、窗口是否可见或可恢复。
- 微信是否登录。
- Kangkang 与微信是否同级权限。
- 搜索框、聊天标题、输入框是否可访问。

错过固定发送点处理：

- 固定发送点错过后进入补偿窗口，默认 60 分钟。
- 唤醒后如果用户仍未解锁，继续跳过，不强行输入微信。
- 超过补偿窗口标记 `SKIPPED_EXPIRED`，不再补发，避免下午补早报。
- 轮询短提醒不补跑历史，只记录最近一次基准和风险变化。
````

## 5. 建议追加到“Windows 正式发布方案”的内容

````markdown
### Windows 正式发布方案补充

发布形态：

| 形态 | 文件 | 面向对象 | 用途 |
|---|---|---|---|
| 安装版 | `KangkangWeatherSetup-vX.Y.Z.exe` | 普通用户 | 安装到 `%LOCALAPPDATA%\Programs\KangkangWeather`，创建快捷方式和卸载入口 |
| 便携版 | `KangkangWeather-vX.Y.Z.zip` | 测试用户/迁移用户 | 解压即用，包含 README 和示例配置 |
| onedir debug | `KangkangWeather-vX.Y.Z-onedir.zip` | 开发/排障 | 依赖展开，方便定位资源缺失 |

发布资产：

- EXE、zip、setup exe 上传 GitHub Release，不长期提交到源码仓库。
- 生成 `SHA256SUMS-vX.Y.Z.txt`。
- Release Notes 分普通用户版和开发者版。
- README 说明 SmartScreen 可能提醒，因为当前无代码签名。
- 诊断包不包含用户配置原文、微信聊天记录、完整消息正文。

启动路径自检：

- `sys.frozen`
- `sys._MEIPASS`
- 程序目录
- `%APPDATA%\KangkangWeather`
- 配置写权限
- 日志写权限
- 资源文件是否存在
- 中文路径和空格路径
````

## 6. 建议追加到“测试计划”的内容

````markdown
### 调研补充后的测试计划

#### 单元测试

- 旧配置迁移到当前 `config_version`。
- 多对象 enabled/disabled 筛选。
- `SendTarget`、`SendResult`、`SendBatch` 序列化。
- `message_hash` 防重复。
- `send_task.lock` 创建、占用、过期、释放。
- 只重试失败对象。
- 手动发送和自动化发送冲突。
- 固定发送点错过、补偿、过期。
- 锁屏/权限/微信未登录错误码映射。
- 诊断包脱敏。
- 配置损坏备份恢复。

#### API/界面测试

- `/api/state` 返回启用目标数、自动化摘要、版本号。
- `/api/send-weather` 单对象兼容。
- `/api/send-weather` 多对象 dry-run。
- `/api/send-history` 返回最近发送记录。
- `/api/diagnostics` 返回路径、运行模式、readiness 和日志摘要。
- 桌面端 760x560 可滚动，JSON 默认折叠。

#### Windows 实机测试

- Windows 10/11 普通权限。
- 微信普通权限，Kangkang 普通权限。
- 微信管理员权限、Kangkang 普通权限时应提示权限不一致。
- 微信未启动、未登录、最小化、被遮挡。
- 锁屏等待固定发送点：应跳过并记录，不强发。
- 只关闭显示器但未睡眠未锁屏：允许执行。
- 睡眠跨过固定发送点：唤醒后在补偿窗口内才补发。
- 中文用户名路径、空格路径。
- 8766 端口占用自动换端口。

#### 发布测试

- `python -m compileall wechat_weather tests`
- `python -m unittest discover -s tests -v`
- 构建 installer、portable zip、onedir debug。
- 使用临时 `%APPDATA%` 验证首次设置。
- 验证安装版快捷方式、开始菜单、卸载入口。
- 验证 Release zip 内 README、示例配置、EXE、校验文件齐全。
````

## 7. 建议追加到“发布说明草稿”的内容

````markdown
## Kangkang Weather v3.5.x 发布说明草稿

### 面向普通用户

- 新增多个微信好友/群发送目标管理。
- 新增发送目标启用/禁用、单对象测试和批量测试。
- 新增发送历史，可以看到每次发送给谁、是否成功、失败原因。
- 自动化状态更清楚，可以看到下次检查、上次发送和跳过原因。
- 发送前会检查微信是否已登录、电脑是否锁屏、权限是否一致，减少无提示失败。
- 错误提示更容易看懂，不再只显示开发者 JSON。
- 诊断包增强，方便把问题发给开发者排查。
- 配置兼容和损坏恢复更稳，换电脑时更容易重新设置。

### 面向开发者

- 引入结构化 SendTarget / SendResult / SendBatch 模型。
- 增加 JSONL send history 和全局 send lock。
- 增强 automation readiness gate。
- 增加错误码和用户可读 error analysis。
- 增强 PyInstaller runtime/path diagnostics。
- 增加 release checklist、CHANGELOG 和 GitHub issue templates。

### 已知限制

- 官方 Windows 微信没有公开本地发消息 API，本软件依赖真实微信窗口和 Windows UI 自动化。
- 电脑锁屏、注销、睡眠、UAC 安全桌面、权限级别不一致时，不能保证微信自动发送。
- 当前不支持读取微信聊天内容，不支持营销群发，不支持多账号微信。
- 未代码签名的 EXE 可能触发 SmartScreen 提醒。
````

## 下一条给 Codex 的执行提示词

```text
请按照 docs/NEXT_ITERATION.md、docs/COMPETITOR_ITERATION_RESEARCH.md、docs/FEATURE_POOL.md 和 docs/NEXT_ITERATION_RESEARCH_APPENDIX.md，开始执行下一轮工程实现。

本轮只执行“阶段 1：多对象发送底层能力 + P0 稳定性收口”，不要做 P2/P3，也不要大改 UI。

硬性限制：
1. 不重写项目。
2. 不换 UI 框架。
3. 不做云服务。
4. 不读取微信聊天内容。
5. 不做营销群发。
6. 不破坏当前单对象发送。
7. 不把 EXE/安装包提交进源码仓库。
8. 不承诺锁屏/注销状态能通过官方微信发送。

优先实现：
1. 检查当前代码中已有 v3.5.0 多对象/发送历史/锁实现，先审计，不重复造轮子。
2. 明确定义或补齐 SendTarget、SendResult、SendBatch。
3. 配置层继续使用 wechat_targets，支持 contact/recipients 旧配置迁移。
4. 支持目标启用/禁用、逐个发送、部分失败。
5. 支持只重试失败对象。
6. 完善 send_history.jsonl，历史记录不保存完整微信消息正文。
7. 完善 send_task.lock，处理 stale lock。
8. 修改 /api/send-weather，兼容单对象，同时支持 send_all_enabled、target_ids、dry_run。
9. 修改 /api/send-history，返回用户可读历史摘要。
10. 自动化发送前必须经过 readiness gate 和全局发送锁。
11. 手动发送与固定发送冲突时，不允许两个线程同时操作微信。
12. 增加错误码和用户可读错误提示，原始 JSON 只作为开发者诊断。

需要补测试：
1. 配置迁移：contact、recipients、已有 wechat_targets。
2. 多对象 enabled/disabled 筛选。
3. SendBatch 成功、部分失败、全部失败。
4. 只重试失败对象。
5. 全局锁占用、过期、释放。
6. 手动发送与定时发送冲突。
7. send_history 不保存完整消息正文。
8. API 单对象兼容和多对象 dry-run。

完成后运行：
- python -m compileall wechat_weather tests
- python -m unittest discover -s tests -v

完成后汇报：
1. 修改文件。
2. 当前实现了哪些 P0。
3. 测试结果。
4. 未完成风险。
5. 下一步建议。
```
