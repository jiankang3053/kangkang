# Kangkang Weather 功能池与优先级规划

> 调研日期：2026-05-04  
> 当前定位：本地微信天气自动提醒助手  
> 优先级原则：按稳定性、正式发布、诊断、配置兼容和用户可理解程度排序，不按炫酷程度排序。  
> 注意：本文件是工程功能池，不代表所有功能都要一次性实现。

## P0 必须做：v3.5.0 主线

P0 功能满足任一条件即可进入：影响发送稳定性、影响多对象发送、影响正式发布、影响 Bug 定位、影响旧配置兼容、影响用户是否能知道失败原因。

## 多对象发送列表

### 功能说明

把微信发送目标从单个 `contact` 扩展为可管理的目标列表，支持好友、群、文件传输助手、其他类型。

### 来源依据

- Discord WeatherBot 多地点/命令式对象管理：[GitHub](https://github.com/smmhrdmn/WeatherBot)
- PowerToys 工具开关式设置体验：[Docs](https://learn.microsoft.com/en-us/windows/powertoys/)

### 为什么适合 Kangkang Weather

用户常见场景是“家人一个、工作群一个、自己文件传输助手一个”，但不能做营销群发。列表化可以支持自用多对象，同时保留明确的启用开关和发送确认。

### 涉及模块

`wechat_weather/config.py`、`wechat_weather/server.py`、`wechat_weather/desktop.py`、`wechat_weather/send_batch.py`、`tests/`

### 实现建议

沿用现有 `wechat_targets`，补齐 `type`、`remark`、`last_test_at`、`last_send_status`、`last_error_code`。不要新增大型数据库，先使用配置 JSON 和历史 JSONL。

### 验收标准

- 能添加、编辑、删除、启用、禁用目标。
- 单目标发送兼容旧接口。
- 目标为空时进入设置引导，不默认继承本机私人联系人。

### 风险

重名目标可能误匹配；必须依赖打开会话后的标题精确校验。

### 推荐优先级

P0。

## 发送对象启用/禁用

### 功能说明

每个微信目标都有 `enabled` 状态，批量发送和自动化只发送启用对象。

### 来源依据

- PowerToys 快速开关式工具设置：[Docs](https://learn.microsoft.com/en-us/windows/powertoys/)
- GitHub Issue 模板要求清晰复现上下文：[Docs](https://docs.github.com/articles/configuring-issue-templates-for-your-repository)

### 为什么适合 Kangkang Weather

用户可以临时停发某个群，不需要删除配置，降低误操作。

### 涉及模块

`config.py`、`server.py`、`desktop.py`、`monitor.py`

### 实现建议

批量发送前统一调用 `get_enabled_targets()`；UI 明确显示启用对象数。

### 验收标准

- 禁用对象不会出现在批量发送名单。
- 手动选择禁用对象测试时需明确提示。

### 风险

用户可能以为禁用后删除；UI 文案要写成“暂停发送”。

### 推荐优先级

P0。

## 单对象测试

### 功能说明

对单个微信目标执行打开会话测试和发送测试消息，验证该目标在当前电脑上可用。

### 来源依据

- Kangkang 当前已有打开会话测试基础。
- Microsoft UI Automation 依赖真实窗口控件：[Docs](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview)

### 为什么适合 Kangkang Weather

迁移到别人电脑时，联系人名称、微信版本、权限和窗口状态都不同，单对象测试是启用自动化前的最小安全门。

### 涉及模块

`wechat.py`、`server.py`、`desktop.py`、`error_analysis.py`

### 实现建议

把“打开会话测试”和“发送测试消息”分开；测试消息必须清楚提示会真实发送。

### 验收标准

- 打开会话测试不发送文本。
- 发送测试消息能返回会话标题、输入方式、发送验证和可读错误。

### 风险

测试消息也可能打扰用户；默认建议先测试 `文件传输助手`。

### 推荐优先级

P0。

## 批量测试

### 功能说明

对所有启用对象执行批量测试，先 dry-run 展示名单，再逐个执行打开会话或测试消息。

### 来源依据

- Weather Bot 订阅对象管理：[GitHub](https://github.com/smmhrdmn/WeatherBot)
- APScheduler 任务执行器串行/并发模型：[Docs](https://apscheduler.readthedocs.io/en/stable/userguide.html)

### 为什么适合 Kangkang Weather

多对象上线前必须知道哪个对象失败，不能等正式发送才发现。

### 涉及模块

`send_batch.py`、`server.py`、`desktop.py`、`wechat.py`

### 实现建议

默认批量打开会话测试；批量发送测试消息需要二次确认。对象之间加 2-5 秒间隔。

### 验收标准

- 批量测试可中途停止。
- 每个对象都有独立结果。
- 失败不影响后续对象，除非微信窗口消失。

### 风险

连续操作微信 UI 可能触发不稳定；需要串行锁和间隔。

### 推荐优先级

P0。

## 发送批次记录

### 功能说明

一次手动或自动发送生成一个 `batch_id`，每个目标有独立 `SendResult`。

### 来源依据

- ShareX 详细历史和变更记录：[Changelog](https://getsharex.com/changelog)
- Keep a Changelog 的分类记录思想：[Docs](https://keepachangelog.com/en/1.1.0/)

### 为什么适合 Kangkang Weather

用户问“为什么没发到 A”时，必须定位到该批次和该对象，而不是只显示一坨 JSON。

### 涉及模块

`send_batch.py`、`monitor.py`、`server.py`、`compat.py`

### 实现建议

使用 `%APPDATA%\KangkangWeather\history\send_history.jsonl`，每行一条批次摘要或目标结果；正文只存 hash 和摘要，不保存完整微信消息正文。

### 验收标准

- 能查询最近 50 条。
- 诊断包包含脱敏发送历史。
- 同一批次可看到成功数、失败数、跳过数。

### 风险

目标名属于隐私；导出诊断包时需要脱敏或用户确认。

### 推荐优先级

P0。

## 只重试失败对象

### 功能说明

批次部分失败时，允许只对失败对象重新发送，不重复打扰已成功对象。

### 来源依据

- APScheduler misfire/coalescing 思路：[Docs](https://apscheduler.readthedocs.io/en/stable/userguide.html)
- RPA 常见重试策略参考 Microsoft UI 自动化故障文档：[Docs](https://learn.microsoft.com/en-us/troubleshoot/power-platform/power-automate/desktop-flows/ui-automation/uipi-issues)

### 为什么适合 Kangkang Weather

天气提醒是面向人的消息，重复发送比失败更糟。只重试失败对象是多目标发送的基本礼貌。

### 涉及模块

`send_batch.py`、`server.py`、`desktop.py`

### 实现建议

历史记录中保存 `failed_target_ids`，UI 提供“只重试失败对象”。不可恢复错误默认不重试。

### 验收标准

- 已成功目标不会再次收到同一条消息。
- 目标不存在、标题不一致、权限不一致不会自动重试。

### 风险

若上次成功验证不准，可能漏发；发送验证要保守。

### 推荐优先级

P0。

## 自动化任务锁

### 功能说明

新增全局发送锁，防止手动发送、固定时间发送、轮询补发同时操作微信。

### 来源依据

- APScheduler executor/job store 并发控制：[Docs](https://apscheduler.readthedocs.io/en/stable/userguide.html)
- schedule 文档提示简单轮询不会补跑错过任务：[Docs](https://schedule.readthedocs.io/en/stable/index.html)

### 为什么适合 Kangkang Weather

微信 UI 自动化无法并发。两个线程同时切会话、粘贴、回车，可能导致发错人。

### 涉及模块

`send_batch.py`、`monitor.py`、`server.py`

### 实现建议

使用 `%APPDATA%\KangkangWeather\locks\send_task.lock`，包含 owner、batch_id、created_at、ttl。过期锁标记 stale，允许用户一键释放。

### 验收标准

- 连续点击发送只启动一个发送批次。
- 定时任务遇到手动任务时跳过或排队，并记录原因。

### 风险

程序崩溃留下锁文件；必须有 TTL 和 stale lock 恢复。

### 推荐优先级

P0。

## 手动发送与定时发送冲突处理

### 功能说明

当用户手动发送和自动化任务同时触发时，统一通过任务锁和状态机处理。

### 来源依据

- APScheduler job/executor 概念：[Docs](https://apscheduler.readthedocs.io/en/stable/userguide.html)
- Windows 计划任务交互运行限制：[schtasks Docs](https://learn.microsoft.com/en-us/windows/win32/taskschd/schtasks)

### 为什么适合 Kangkang Weather

这类冲突是多对象正式发布后最容易产生的重复发送 Bug。

### 涉及模块

`monitor.py`、`server.py`、`send_batch.py`、`desktop.py`

### 实现建议

手动优先；自动化遇到锁时记录 `SKIPPED_BUSY`，固定发送点进入补偿窗口。

### 验收标准

- 自动化和手动不会同时调用 `wechat.py`。
- UI 显示“任务占用/已跳过/将补偿”。

### 风险

补偿规则过宽会造成延迟重复；默认补偿 60 分钟。

### 推荐优先级

P0。

## 微信环境自检

### 功能说明

发送前检测微信窗口、登录状态、权限级别、交互桌面、锁屏/UAC/RDP 影响。

### 来源依据

- Microsoft UI Automation：[Docs](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview)
- Power Automate UIPI Issues：[Docs](https://learn.microsoft.com/en-us/troubleshoot/power-platform/power-automate/desktop-flows/ui-automation/uipi-issues)
- SendInput UIPI 限制：[Docs](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)
- Window Stations/Desktops：[Docs](https://learn.microsoft.com/en-us/windows/win32/winstation/window-stations)

### 为什么适合 Kangkang Weather

用户最困惑的是“为什么别人电脑/息屏/锁屏/管理员运行就不能发”。自检必须在失败前告诉用户原因。

### 涉及模块

`readiness.py`、`compat.py`、`wechat.py`、`desktop.py`

### 实现建议

建立 readiness gate：`READY`、`WECHAT_NOT_RUNNING`、`WECHAT_NOT_LOGGED_IN`、`DESKTOP_LOCKED`、`PERMISSION_MISMATCH`、`UAC_DESKTOP`、`INPUT_UNAVAILABLE`。

### 验收标准

- 锁屏或权限不一致时不继续发送。
- UI 给出普通用户可读建议。
- 诊断包保存原始技术细节。

### 风险

Windows 状态检测可能不完美；宁可保守跳过，也不要误发。

### 推荐优先级

P0。

## 目标会话检测

### 功能说明

打开目标后再次校验当前聊天标题与目标名称一致，确认后才输入消息。

### 来源依据

- pywinauto UIA 控件自动化：[Docs](https://pywinauto.readthedocs.io/en/latest/)
- wxauto 也是基于 Windows 微信客户端自动化：[GitHub](https://github.com/cluic/wxauto)

### 为什么适合 Kangkang Weather

微信搜索结果可能有相似联系人或群，标题校验是防止发错人的最后一道门。

### 涉及模块

`wechat.py`、`error_analysis.py`、`tests/`

### 实现建议

搜索结果精确匹配、打开后标题精确匹配、输入前二次确认。失败返回 `TARGET_TITLE_MISMATCH`。

### 验收标准

- 相似名称不会发送。
- 标题不一致时输入框不粘贴消息。

### 风险

微信 UI 标题可能显示备注名或群名截断；需要在设置里提示名称必须与搜索结果一致。

### 推荐优先级

P0。

## 配置版本号

### 功能说明

配置文件写入 `config_version`，便于后续迁移和兼容判断。

### 来源依据

- Semantic Versioning 版本语义：[Docs](https://semver.org/)
- PowerToys 设置迁移思路：[Docs](https://learn.microsoft.com/en-us/windows/powertoys/)

### 为什么适合 Kangkang Weather

项目已经多次迭代，字段从 `contact` 到 `recipients` 到 `wechat_targets`，没有版本号会让迁移越来越脆。

### 涉及模块

`config.py`、`wechat_weather_config.example.json`、`tests/`

### 实现建议

当前保持 `config_version = 3`，所有新字段必须有默认值和迁移测试。

### 验收标准

- 旧配置读取后自动补齐字段。
- 保存后配置写入当前版本号。

### 风险

迁移函数覆盖用户手工配置；必须备份原文件。

### 推荐优先级

P0。

## 老配置迁移

### 功能说明

兼容旧 `contact`、`recipients`、早期 `locations/wechat_targets/automation_jobs` 配置。

### 来源依据

- Keep a Changelog 中 Changed/Deprecated 的迁移表达：[Docs](https://keepachangelog.com/en/1.1.0/)
- GitHub Desktop Release Notes 的兼容性说明：[Releases](https://github.com/desktop/desktop/releases)

### 为什么适合 Kangkang Weather

用户已经在本机多次安装测试，不能升级后丢地址、目标、固定时间和前缀。

### 涉及模块

`config.py`、`tests/test_config*`

### 实现建议

加载时先深拷贝原始配置，迁移失败时备份并进入 setup，不要静默覆盖。

### 验收标准

- v2.x、v3.0、v3.1、v3.5 配置样例测试通过。
- 迁移后默认目标仍明确可见。

### 风险

历史字段组合复杂；需要 fixture 覆盖真实旧配置。

### 推荐优先级

P0。

## 日志增强

### 功能说明

统一 `app.log`、`weather.log`、`wechat.log`、`automation.log`、`error.log`，记录关键步骤和错误码。

### 来源依据

- ShareX 的历史/日志式排障：[Changelog](https://getsharex.com/changelog)
- GitHub Issue 模板要求环境与复现信息：[Docs](https://docs.github.com/articles/configuring-issue-templates-for-your-repository)

### 为什么适合 Kangkang Weather

跨电脑失败时用户很难描述现场，日志是远程排查的基础。

### 涉及模块

`run_trace.py`、`compat.py`、`weather.py`、`wechat.py`、`monitor.py`

### 实现建议

日志写到 `%APPDATA%\KangkangWeather\logs`；每条包含 version、session_id、job_id、batch_id。

### 验收标准

- 启动、发送、天气查询、自动化跳过都有日志。
- 日志不会保存完整微信聊天内容。

### 风险

日志量膨胀；需要轮转或保留最近 N 天。

### 推荐优先级

P0。

## 诊断包增强

### 功能说明

导出包含版本、路径、配置摘要、日志、天气历史、发送历史、微信窗口摘要、readiness 的诊断包。

### 来源依据

- GitHub Issue 模板：[Docs](https://docs.github.com/articles/configuring-issue-templates-for-your-repository)
- PyInstaller runtime 路径诊断：[Docs](https://pyinstaller.org/en/stable/runtime-information.html)

### 为什么适合 Kangkang Weather

用户反馈“别人电脑不能用”时，诊断包应能定位到环境、权限、微信、天气源、配置或打包路径问题。

### 涉及模块

`compat.py`、`readiness.py`、`server.py`、`desktop.py`

### 实现建议

诊断包默认脱敏目标名和消息正文；提供用户显式允许的“包含目标名称”选项。

### 验收标准

- 包含 `app.log`、`wechat.log`、`weather_fetch_history`、`send_history`。
- 不包含微信聊天记录。

### 风险

隐私泄露；脱敏必须有测试。

### 推荐优先级

P0。

## 打包路径自检

### 功能说明

启动时检查 PyInstaller 运行模式、资源路径、配置路径、日志路径和写权限。

### 来源依据

- PyInstaller runtime `sys.frozen`/`sys._MEIPASS`：[Docs](https://pyinstaller.org/en/stable/runtime-information.html)
- PyInstaller onefile/onedir operating mode：[Docs](https://pyinstaller.org/en/v5.13.1/operating-mode.html)

### 为什么适合 Kangkang Weather

跨电脑不能用常常不是代码逻辑，而是资源文件、配置路径、中文路径、安装目录写权限问题。

### 涉及模块

`packaging.py`、`compat.py`、`config.py`

### 实现建议

自检输出 `is_frozen`、`bundle_dir`、`appdata_dir`、`resource_exists`、`config_writable`。

### 验收标准

- 安装版、便携版、源码运行都能显示正确路径。
- 缺资源时提示具体文件。

### 风险

过度依赖当前打包结构；需要 onedir debug 验证。

### 推荐优先级

P0。

## 发送失败错误码

### 功能说明

把微信、天气、配置、自动化失败统一映射成稳定错误码。

### 来源依据

- Power Automate UIPI 故障分类：[Docs](https://learn.microsoft.com/en-us/troubleshoot/power-platform/power-automate/desktop-flows/ui-automation/uipi-issues)
- GitHub Desktop Release Notes 中 Fixed/Known issue 分类：[Releases](https://github.com/desktop/desktop/releases)

### 为什么适合 Kangkang Weather

“发送失败”太模糊；用户需要知道是锁屏、未登录、权限不一致、目标不存在、输入框不可用还是天气源失败。

### 涉及模块

`error_analysis.py`、`wechat.py`、`weather.py`、`monitor.py`

### 实现建议

定义 `KANGKANG_ERROR_CODE`，每个错误包含 title、summary、likely_causes、next_steps、retryable。

### 验收标准

- 所有公开 API 失败返回错误码。
- UI 不只展示 traceback。

### 风险

错误码维护成本；先覆盖 P0 常见错误。

### 推荐优先级

P0。

## 用户可读错误提示

### 功能说明

把技术诊断转换成普通用户能执行的下一步。

### 来源依据

- PowerToys 正式工具文档体验：[Docs](https://learn.microsoft.com/en-us/windows/powertoys/)
- GitHub Issue Templates 降低反馈成本：[Docs](https://docs.github.com/articles/configuring-issue-templates-for-your-repository)

### 为什么适合 Kangkang Weather

用户不是 Python 开发者，看到 JSON 或 traceback 只会更困惑。

### 涉及模块

`desktop.py`、`web_console.html`、`error_analysis.py`

### 实现建议

主界面显示“发生了什么 / 可能原因 / 建议操作 / 是否可重试”，原始 JSON 放开发者模式。

### 验收标准

- 常见 10 类失败均有中文提示。
- 用户根据提示能完成下一步排查。

### 风险

提示过度简化；保留开发者详情。

### 推荐优先级

P0。

## 发送历史记录

### 功能说明

记录最近发送批次、目标结果、触发来源、是否 dry-run、错误码和耗时。

### 来源依据

- ShareX 历史与 Changelog：[Changelog](https://getsharex.com/changelog)
- GitHub Release/Issue 的可追溯信息要求：[Docs](https://docs.github.com/articles/configuring-issue-templates-for-your-repository)

### 为什么适合 Kangkang Weather

“今天六点为什么没发”必须从历史里直接查到原因：未到执行时间、锁屏跳过、天气失败、微信目标失败或已发送。

### 涉及模块

`send_batch.py`、`monitor.py`、`server.py`、`desktop.py`

### 实现建议

JSONL 最多保留最近 1000 条或最近 30 天；UI 默认显示最近 10 条。

### 验收标准

- 手动发送、固定发送、轮询补发、dry-run 都有记录。
- 历史不保存完整消息正文。

### 风险

历史过大；需要裁剪。

### 推荐优先级

P0。

## P1 应该做：正式小工具体验

P1 功能明显提升正式工具体验、降低使用门槛和问题反馈成本，但不应破坏 P0 稳定性。

## 自动化状态卡片

### 功能说明

主界面显示自动化启用状态、当前状态、下次执行、上次执行结果和最近跳过原因。

### 为什么要做

用户问“为什么没有自动发送”时，第一屏就应看到答案。

### 参考来源

- APScheduler 任务状态模型：[Docs](https://apscheduler.readthedocs.io/en/stable/userguide.html)
- GitHub Desktop 状态清晰的桌面工具体验：[Docs](https://docs.github.com/en/desktop)

### 涉及模块

`monitor.py`、`server.py`、`desktop.py`

### 实现建议

将 monitor 状态从原始 JSON 转成摘要字段：`running`、`next_run_at`、`last_result_title`、`last_skip_reason`。

### 验收标准

不用打开 JSON 就能知道下一次什么时候发、上次为什么没发。

### 风险

摘要和原始状态不一致；状态卡片由同一 API 生成。

## 下次发送时间显示

### 功能说明

显示每个自动化任务的下次固定发送时间和下次轮询时间。

### 为什么要做

减少用户误判“程序没运行”。

### 参考来源

- APScheduler next run time：[Docs](https://apscheduler.readthedocs.io/en/stable/userguide.html)

### 涉及模块

`monitor.py`、`desktop.py`、`web_console.html`

### 实现建议

区分 `next_fixed_send_at` 和 `next_interval_check_at`，不要只显示一个笼统时间。

### 验收标准

固定发送点和轮询检查分别可见。

### 风险

跨天计算错误；加时间解析测试。

## 上次发送结果显示

### 功能说明

显示上次真实发送的时间、目标数、成功数、失败数、失败原因。

### 为什么要做

发送历史太长，首页需要摘要。

### 参考来源

- ShareX 历史记录与状态反馈：[Changelog](https://getsharex.com/changelog)

### 涉及模块

`send_batch.py`、`desktop.py`

### 实现建议

从 `send_history.jsonl` 读取最近真实发送批次，dry-run 单独标注。

### 验收标准

最近一次发送结果在首页可读。

### 风险

历史文件损坏；读取失败时显示“历史不可用”并不影响发送。

## 发送历史页面

### 功能说明

提供历史列表，支持按触发来源、成功/失败、目标查看。

### 为什么要做

降低远程排查成本。

### 参考来源

- GitHub Issue 模板需要用户提供复现和日志：[Docs](https://docs.github.com/articles/configuring-issue-templates-for-your-repository)

### 涉及模块

`server.py`、`desktop.py`、`web_console.html`

### 实现建议

先用表格显示最近 50 条，不做复杂查询。

### 验收标准

用户能复制某条失败摘要给开发者。

### 风险

隐私；默认隐藏完整目标名或提供脱敏开关。

## 开发者模式折叠 JSON

### 功能说明

把原始运行状态和诊断 JSON 默认折叠到开发者模式。

### 为什么要做

当前界面更像调试工具，普通用户容易迷路。

### 参考来源

- PowerToys 设置页面向普通用户，复杂项分层：[Docs](https://learn.microsoft.com/en-us/windows/powertoys/)

### 涉及模块

`desktop.py`、`web_console.html`

### 实现建议

保留 JSON，不删除；默认隐藏，点击“开发者诊断”展开。

### 验收标准

主界面第一屏不被 JSON 占满。

### 风险

排障入口不明显；按钮放在诊断区。

## 配置备份/恢复

### 功能说明

支持导出配置、导入配置、自动备份、一键恢复最近备份。

### 为什么要做

换电脑使用是用户重点诉求。

### 参考来源

- PowerToys 设置迁移体验：[Docs](https://learn.microsoft.com/en-us/windows/powertoys/)

### 涉及模块

`config.py`、`desktop.py`、`compat.py`

### 实现建议

导出时默认不包含日志、缓存、历史；导入后进入兼容性自检。

### 验收标准

新电脑导入配置后仍要求测试微信目标。

### 风险

私人目标泄露；导出前提示内容范围。

## 多城市绑定

### 功能说明

每个微信目标或自动化任务绑定一个天气地址。

### 为什么要做

群 A 需要武汉，群 B 需要嘉鱼，用户自己需要本地。

### 参考来源

- WeatherBot 多地点支持：[GitHub](https://github.com/smmhrdmn/WeatherBot)
- Open-Meteo Geocoding API：[Docs](https://open-meteo.com/en/docs/geocoding-api)

### 涉及模块

`config.py`、`weather.py`、`monitor.py`、`desktop.py`

### 实现建议

当前 `automation_jobs` 已有 `location_id + wechat_target_id` 方向，继续增强 UI。

### 验收标准

不同对象可发送不同地址天气，历史中记录地址名。

### 风险

天气缓存和对象绑定混乱；缓存 key 必须包含 location id。

## 错峰发送

### 功能说明

多对象发送时按顺序间隔发送，避免微信 UI 和天气接口压力。

### 为什么要做

减少微信闪退、焦点错乱和重复请求。

### 参考来源

- 自动化工具串行任务思想：[APScheduler Docs](https://apscheduler.readthedocs.io/en/stable/userguide.html)

### 涉及模块

`send_batch.py`、`monitor.py`

### 实现建议

默认 3 秒间隔，可配置 2-10 秒。

### 验收标准

批量发送日志中显示每个对象的开始/结束时间。

### 风险

目标太多时耗时长；本项目不鼓励大量目标。

## 异常天气提醒

### 功能说明

下雨、降温、高温、大风、空气差、UV 强时发短提醒，普通天气不重复打扰。

### 为什么要做

这是 Kangkang 的差异化价值：不只是固定日报，而是有情况才提醒。

### 参考来源

- MMM-RAIN-MAP 只在降雨相关场景展示：[GitHub](https://github.com/jalibu/MMM-RAIN-MAP)
- Weatherbot 多级预警：[PyPI](https://pypi.org/project/weatherbot/)

### 涉及模块

`weather.py`、`monitor.py`、`config.py`

### 实现建议

使用 `alert_options` 控制阈值，短提醒不套用日报前缀。

### 验收标准

阈值变化能影响补发判断；重复提醒去重。

### 风险

天气源分歧导致误报；文案标注“按偏高风险提醒”。

## 天气接口失败缓存兜底

### 功能说明

网络失败时使用最近 12 小时成功预报，并标注缓存状态。

### 为什么要做

天气源超时不能让整个软件看起来坏掉。

### 参考来源

- Open-Meteo 主源：[Docs](https://open-meteo.com/en/docs)
- wttr.in 兜底：[GitHub](https://github.com/chubin/wttr.in)

### 涉及模块

`weather.py`、`desktop.py`、`server.py`

### 实现建议

缓存状态进入 `weather_status` 和查询历史。

### 验收标准

断网时有缓存则可预览，并显示“使用最近一次预报”。

### 风险

过期天气误导；缓存必须有时间限制。

## README 完善

### 功能说明

整理安装、首次设置、微信要求、常见限制和发布资产说明。

### 为什么要做

正式发布需要让别人能独立安装。

### 参考来源

- GitHub Desktop Docs：[Docs](https://docs.github.com/en/desktop)
- GitHub Releases：[Docs](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)

### 涉及模块

`README.md`、`README_PORTABLE.md`

### 实现建议

文档分普通用户版和开发者版。

### 验收标准

用户按 README 能完成安装、设置、测试、导出诊断。

### 风险

文档过长；用“快速开始 + 常见问题”结构。

## FAQ

### 功能说明

新增常见问题：息屏、锁屏、微信未登录、权限、目标搜索、杀毒提醒、更新。

### 为什么要做

用户反复问的问题不应靠聊天解释。

### 参考来源

- PowerToys 文档式用户支持：[Docs](https://learn.microsoft.com/en-us/windows/powertoys/)

### 涉及模块

`docs/FAQ.md`

### 实现建议

每个问题给一句结论和操作步骤。

### 验收标准

覆盖前 15 个常见问题。

### 风险

回答过度承诺；特别是锁屏必须诚实。

## TROUBLESHOOTING

### 功能说明

新增排障文档，按错误码查原因和操作。

### 为什么要做

跨电脑安装失败需要可自助排查。

### 参考来源

- Microsoft Power Automate UI 自动化故障文档：[Docs](https://learn.microsoft.com/en-us/troubleshoot/power-platform/power-automate/desktop-flows/ui-automation/uipi-issues)

### 涉及模块

`docs/TROUBLESHOOTING.md`、`error_analysis.py`

### 实现建议

错误码和文档保持同名标题。

### 验收标准

UI 的错误码能在文档中找到。

### 风险

错误码变更后文档滞后；Release checklist 检查。

## CHANGELOG

### 功能说明

建立 `CHANGELOG.md`，使用 Added/Changed/Fixed/Security 分类。

### 为什么要做

正式发布不能只靠散落的 release notes。

### 参考来源

- Keep a Changelog：[Docs](https://keepachangelog.com/en/1.1.0/)
- Semantic Versioning：[Docs](https://semver.org/)

### 涉及模块

`CHANGELOG.md`、release docs

### 实现建议

保留历史 `RELEASE_NOTES_v*.md`，新增总 changelog 汇总。

### 验收标准

每个版本有日期、分类、用户可读变更。

### 风险

维护成本；发布清单强制更新。

## Bug report 模板

### 功能说明

新增 `.github/ISSUE_TEMPLATE/bug_report.yml` 或 Markdown 模板。

### 为什么要做

减少“不能用”这种不可定位反馈。

### 参考来源

- GitHub Issue Templates：[Docs](https://docs.github.com/articles/configuring-issue-templates-for-your-repository)

### 涉及模块

`.github/ISSUE_TEMPLATE/`

### 实现建议

字段包含版本、Windows、微信版本、是否锁屏、是否管理员、诊断包。

### 验收标准

用户提交问题时能提供必要排障信息。

### 风险

模板太复杂；必填字段只保留 P0 信息。

## P2 可以做：体验增强

P2 功能提升体验，但不是正式发布阻塞项。

## 开机自启

### 功能说明

提供用户级开机自启开关。

### 为什么要做

自动提醒需要长期运行。

### 参考来源

- PowerToys 常驻工具体验：[Docs](https://learn.microsoft.com/en-us/windows/powertoys/)

### 涉及模块

`tray.py`、`desktop.py`、`scheduler.py`

### 实现建议

默认关闭；开启前提示“需要用户登录，锁屏不保证微信发送”。

### 验收标准

重启登录后程序能启动。

### 风险

用户误以为电脑睡眠也能运行。

## 托盘运行

### 功能说明

最小化到托盘，菜单包含打开控制台、立即检查、退出。

### 为什么要做

正式桌面工具不应一直占用主窗口。

### 参考来源

- PowerToys 托盘常驻体验：[Docs](https://learn.microsoft.com/en-us/windows/powertoys/)

### 涉及模块

`tray.py`、`desktop.py`

### 实现建议

退出时明确停止服务和释放端口。

### 验收标准

托盘菜单可打开/退出，退出后端口释放。

### 风险

多实例冲突；需要单实例锁。

## 自动更新检查

### 功能说明

启动或手动检查 GitHub Release 最新版本。

### 为什么要做

用户可以知道是否有修复版。

### 参考来源

- GitHub Releases：[Docs](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
- GitHub Generated Release Notes：[Docs](https://docs.github.com/repositories/releasing-projects-on-github/automatically-generated-release-notes)

### 涉及模块

`updater.py`、`desktop.py`

### 实现建议

只提示下载链接，不自动替换 EXE。

### 验收标准

网络失败不影响主功能。

### 风险

杀毒/网络拦截；提示保持非阻塞。

## 未来 3 天预报

### 功能说明

日报显示明天和后天，详情页可看未来 3 天趋势。

### 为什么要做

丰富天气信息，但不让微信消息过长。

### 参考来源

- Open-Meteo 多日预报：[Docs](https://open-meteo.com/en/docs)

### 涉及模块

`weather.py`、`desktop.py`

### 实现建议

微信日报保持短，UI 可展示更多。

### 验收标准

地区切换后 3 天趋势变化正常。

### 风险

消息过长；微信发送模板不扩展。

## 小时级降雨概率

### 功能说明

UI 展示更细的小时降雨概率，消息仍按 3 小时段。

### 为什么要做

帮助用户判断短时出行。

### 参考来源

- Open-Meteo 小时级降雨概率：[Docs](https://open-meteo.com/en/docs)

### 涉及模块

`weather.py`、`desktop.py`

### 实现建议

作为天气详情，不改变发送主模板。

### 验收标准

小时数据缺失时不崩溃。

### 风险

数据展示拥挤；需折叠详情。

## AQI 空气质量

### 功能说明

增加空气质量摘要，用于 UI 和可选提醒。

### 为什么要做

天气建议不只看雨和温度。

### 参考来源

- Breezy Weather 空气质量类功能：[GitHub](https://github.com/breezy-weather/breezy-weather)
- Discord WeatherBot AQI：[GitHub](https://github.com/smmhrdmn/WeatherBot)

### 涉及模块

`weather.py`、`config.py`

### 实现建议

先作为可选字段，不进入默认微信日报。

### 验收标准

无 AQI 数据时 UI 显示“暂无”。

### 风险

数据源不同城市覆盖不一致。

## UV 紫外线指数

### 功能说明

加入紫外线强度，用于防晒建议。

### 为什么要做

提升建议质量。

### 参考来源

- Breezy Weather 多指标天气：[GitHub](https://github.com/breezy-weather/breezy-weather)

### 涉及模块

`weather.py`、message template

### 实现建议

先只在 UI 展示，高风险时可加入建议句。

### 验收标准

UV 数据缺失时不影响发送。

### 风险

建议过度打扰；默认不单独补发。

## 主题切换

### 功能说明

支持浅色/深色或系统主题。

### 为什么要做

提升正式软件观感。

### 参考来源

- Windows 工具常见设置体验：[PowerToys Docs](https://learn.microsoft.com/en-us/windows/powertoys/)

### 涉及模块

`desktop.py`、`web_console.html`

### 实现建议

不引入新 UI 框架，只做 ttk 样式和 CSS。

### 验收标准

切换主题不影响布局。

### 风险

Tkinter 深色适配细节多；放 P2。

## 首次启动向导

### 功能说明

干净配置首次启动时引导设置地址、微信目标、会话测试、测试消息。

### 为什么要做

换电脑使用必须走安全设置流程。

### 参考来源

- Windows 工具首次配置体验：[PowerToys Docs](https://learn.microsoft.com/en-us/windows/powertoys/)

### 涉及模块

`setup` API、`desktop.py`、`server.py`

### 实现建议

新电脑不带本机私人目标；只有测试通过后建议开启自动化。

### 验收标准

临时 `%APPDATA%` 启动时显示向导。

### 风险

向导过长；提供“稍后设置”但禁止真实自动发送。

## 设置页重构

### 功能说明

把地址、目标、自动化、消息模板、诊断分组整理。

### 为什么要做

当前配置内容多，小窗口必须可滚动且清晰。

### 参考来源

- PowerToys 设置分组体验：[Docs](https://learn.microsoft.com/en-us/windows/powertoys/)

### 涉及模块

`desktop.py`、`web_console.html`

### 实现建议

保持 Tkinter/ttk，不换框架；优先滚动、分组、默认展开。

### 验收标准

760x560 窗口能滚动到底部。

### 风险

UI 改动影响稳定；分阶段做。

## 安装包引导页优化

### 功能说明

安装器显示安装位置、是否创建快捷方式、首次运行说明和 SmartScreen 提示。

### 为什么要做

别人电脑安装时减少误解。

### 参考来源

- PyInstaller onefile/onedir 发布说明：[Docs](https://pyinstaller.org/en/v5.13.1/operating-mode.html)
- GitHub Release Assets：[Docs](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)

### 涉及模块

`kangkang_weather_installer.py`、README

### 实现建议

不要求管理员，安装到 `%LOCALAPPDATA%\Programs\KangkangWeather`。

### 验收标准

安装/卸载/快捷方式可用。

### 风险

无代码签名仍会有 SmartScreen；文档明确说明。

## P3 未来做：长期扩展

P3 功能需要云服务、账号体系、复杂架构或隐私边界，当前不做。

## 插件化天气源

### 功能说明

把天气源做成插件接口。

### 为什么暂时不做

当前主线是微信发送稳定性，多源插件会扩大测试面。

### 未来条件

P0/P1 稳定，天气源需求明确，有统一数据结构和契约测试。

### 风险

插件质量不可控、打包复杂、错误定位困难。

## 插件化发送渠道

### 功能说明

支持不同发送渠道插件。

### 为什么暂时不做

当前定位是本地微信天气助手，多渠道会稀释主线。

### 未来条件

微信发送稳定后，再考虑邮件/Telegram 等明确渠道。

### 风险

配置、隐私、失败重试逻辑复杂。

## 企业微信

### 功能说明

接入企业微信机器人或应用消息。

### 为什么暂时不做

需要企业微信配置和凭据，用户群不同。

### 未来条件

有明确企业场景，并能安全保存凭据。

### 风险

认证、权限、消息合规。

## 邮件

### 功能说明

通过 SMTP 或邮件 API 发送天气。

### 为什么暂时不做

凭据存储和投递失败原因复杂，和当前微信主线不同。

### 未来条件

配置加密和测试邮件流程完善。

### 风险

邮箱密码泄露、垃圾邮件误判。

## Telegram

### 功能说明

通过 Telegram Bot 发送天气。

### 为什么暂时不做

需要 Bot Token 和网络访问，国内使用场景受限。

### 未来条件

用户明确需要多渠道，且接受 Token 配置。

### 风险

Token 泄露、网络连通性。

## Web 控制台

### 功能说明

独立完整 Web UI。

### 为什么暂时不做

现有内置 Web 控制台已够用，独立 Web 会变成大重构。

### 未来条件

桌面端主流程稳定，API 契约固定。

### 风险

双 UI 维护成本高。

## 云端同步配置

### 功能说明

账号登录后同步地址、目标和自动化配置。

### 为什么暂时不做

涉及账号、后端、隐私和安全。

### 未来条件

有明确多设备需求和合规方案。

### 风险

隐私泄露、服务成本、账号安全。

## 多设备同步

### 功能说明

多台电脑共享配置和状态。

### 为什么暂时不做

微信发送依赖本机登录状态，多设备同步可能导致重复发送。

### 未来条件

有设备主从模型和冲突解决策略。

### 风险

重复提醒、状态冲突。

## 更完整的数据统计

### 功能说明

统计发送成功率、天气源成功率、提醒触发频率。

### 为什么暂时不做

当前历史记录先满足排障，统计不是主线。

### 未来条件

历史数据稳定、脱敏策略明确。

### 风险

误收集隐私数据。

## 多账号微信

### 功能说明

支持多个微信账号或多个微信窗口。

### 为什么暂时不做

官方微信 UI 自动化本身已经脆弱，多账号会显著提高误发风险。

### 未来条件

有可靠账号识别、窗口绑定和强确认机制。

### 风险

发错账号、发错对象、隐私事故。
