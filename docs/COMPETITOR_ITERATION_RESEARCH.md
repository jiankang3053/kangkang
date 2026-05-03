# Kangkang Weather 同类软件与 GitHub 迭代调研报告

> 调研日期：2026-05-04  
> 当前项目定位：本地微信天气自动提醒助手  
> 当前仓库实际基线：`wechat_weather.config.APP_VERSION = "3.5.0"`，原提示词中的 `v3.1.1` 视为旧描述。  
> 本轮范围：只做调研、归纳、功能池排序和下一轮工程文档，不直接修改核心代码。

## 1. 调研目标

本次调研的目的，是从同类天气应用、天气 Bot、Windows 桌面工具、自动化调度工具、PyInstaller 打包文档和 GitHub 发布规范里，提炼适合 Kangkang Weather 的下一阶段功能和工程路线。

Kangkang Weather 不应被定位成普通天气查询器，也不应做成营销群发工具。它的核心价值是：

- 自动查询指定地区天气。
- 判断是否需要提醒。
- 通过本机已登录的 Windows 微信客户端发送给指定好友或群。
- 记录发送结果、查询历史和失败原因。
- 打包后能在更多 Windows 10/11 电脑上安装、迁移和诊断。

本轮调研尤其关注 P0 风险：微信 UI 自动化依赖真实前台桌面，无法在锁屏、注销、不同权限、UAC 安全桌面、微信未登录、目标窗口不可访问时稳定发送。因此下一版必须优先解决“可运行条件判断、可读失败原因、迁移向导、发送历史和诊断包”，而不是堆叠花哨天气展示。

## 2. 调研来源清单

| 编号 | 项目/文档名称 | 类型 | 链接 | 主要功能 | 迭代特点 | 对 Kangkang Weather 的借鉴价值 |
|---|---|---|---|---|---|---|
| 1 | Breezy Weather | 天气展示类 | [GitHub](https://github.com/breezy-weather/breezy-weather) | 多天气源、小时/多日预报、空气质量、花粉、预警、可视化 | 多源、多指标、移动端成熟天气体验 | 借鉴“多源分歧、空气质量、UV、预警分层”，但不照搬复杂 UI |
| 2 | wttr.in | 天气服务/CLI | [GitHub](https://github.com/chubin/wttr.in) | 文本天气、城市查询、命令行友好输出 | 轻量、容错、适合兜底 | 继续作为天气兜底源，消息格式保持文本友好 |
| 3 | Open-Meteo Forecast API | 天气数据源 | [Docs](https://open-meteo.com/en/docs) | 无 Key 天气预报、小时级数据、多模型 | 开箱可用、适合桌面工具 | 继续作为主源；重点做超时、缓存、多模型一致性 |
| 4 | Open-Meteo Geocoding API | 地址搜索 | [Docs](https://open-meteo.com/en/docs/geocoding-api) | 地理编码与位置搜索 | 简单 API，适合地址搜索补充 | 全国地址选择之外，保留搜索兜底 |
| 5 | RainViewer API Example | 天气雷达示例 | [GitHub](https://github.com/rainviewer/rainviewer-api-example) | 雷达瓦片、地图叠加 | 专注短临降水可视化 | 可作为 P3 雷达/降雨趋势参考，不进入 P0 |
| 6 | MMM-RAIN-MAP | 天气 Widget | [GitHub](https://github.com/jalibu/MMM-RAIN-MAP) | MagicMirror 雨雷达模块，可按未来降雨显示 | 只有雨时展示，减少噪音 | 借鉴“只在有价值时提醒”，不做持续骚扰 |
| 7 | Discord WeatherBot | 天气 Bot | [GitHub](https://github.com/smmhrdmn/WeatherBot) | 多地点保存、5 日预报、空气质量、命令式管理 | 多地点、多命令、JSON 存储 | 借鉴多城市/多对象绑定、对象管理、清晰命令结果 |
| 8 | Telegram Weather Forecast Bot | 天气提醒脚本 | [GitHub](https://github.com/artur-sannikov/weather-forecast-bot-on-Telegram) | 每日天气、下雨带伞提醒 | 简单订阅脚本，强调日常提醒 | 借鉴“日常简报 + 雨具建议”的消息定位 |
| 9 | Weatherbot hurricane alert | 天气预警系统 | [PyPI](https://pypi.org/project/weatherbot/) / [GitHub](https://github.com/nathanramoscfa/weatherbot) | 飓风/NWS 预警、多级告警、报告 | 多级风险、告警历史、测试命令 | 借鉴风险等级、告警测试、历史记录；不引入 AI/云 |
| 10 | Microsoft PowerToys | Windows 工具 | [Docs](https://learn.microsoft.com/en-us/windows/powertoys/) / [Releases](https://github.com/microsoft/PowerToys/releases) | 多工具集合、设置页、托盘、升级发布 | 稳定性修复、设置体验、明确系统要求 | 借鉴正式工具体验、开机自启、设置备份/恢复 |
| 11 | PowerToys Awake | Windows 工具 | [Docs](https://learn.microsoft.com/en-sg/windows/powertoys/awake) | 防止电脑睡眠，保留显示器开关 | 明确说明锁屏时不工作 | 直接借鉴“可保持唤醒但不承诺锁屏可自动化”的表述 |
| 12 | GitHub Desktop | Windows/macOS 桌面工具 | [Releases](https://github.com/desktop/desktop/releases) / [Docs](https://docs.github.com/en/desktop) | 自动更新、Release Notes、已知问题 | Added/Fixed/Improved 分类清晰 | 借鉴发布说明结构和“已知问题/修复项” |
| 13 | ShareX | Windows 工具 | [Releases](https://github.com/ShareX/ShareX/releases) / [Changelog](https://getsharex.com/changelog) | 安装包/便携包、历史、设置项、自动化 | Release 资产带 SHA256，变更日志细 | 借鉴安装版 + 便携版 + 校验值 + 详细 changelog |
| 14 | AutoHotkey | Windows 自动化工具 | [GitHub](https://github.com/AutoHotkey/AutoHotkey) / [Docs](https://www.autohotkey.com/docs/v2/) | Windows 自动化脚本、热键、窗口操作 | 文档强调版本差异和兼容 | 借鉴自动化文档、版本迁移说明、脚本安全边界 |
| 15 | Microsoft UI Automation | Windows UIA 文档 | [Docs](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview) | 控件树、辅助功能、UI 自动化 | 真实桌面控件依赖 | 解释为什么必须识别微信窗口和控件 |
| 16 | Power Automate UIPI Issues | UI 自动化故障文档 | [Docs](https://learn.microsoft.com/en-us/troubleshoot/power-platform/power-automate/desktop-flows/ui-automation/uipi-issues) | 锁屏、UAC、RDP、高权限导致 UI 自动化失败 | 官方列出常见失败原因 | 用于 Kangkang 的 P0 就绪检查和用户提示 |
| 17 | Microsoft SendInput | Windows 输入注入 | [Docs](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput) | 键鼠输入注入，受 UIPI 约束 | 权限级别影响输入 | 说明 Kangkang 和微信必须同级权限 |
| 18 | Window Stations / Desktops | Windows 桌面模型 | [Window Stations](https://learn.microsoft.com/en-us/windows/win32/winstation/window-stations)、[Desktops](https://learn.microsoft.com/en-us/windows/win32/winstation/desktops) | 交互式窗口站、桌面隔离 | 锁屏/UAC 是不同桌面 | 解释锁屏/注销不能可靠发送 |
| 19 | schtasks | Windows 计划任务 | [Docs](https://learn.microsoft.com/en-us/windows/win32/taskschd/schtasks) | 计划任务、交互式运行 | `/IT` 只在用户登录时交互运行 | 自动化任务应选择“用户已登录时运行” |
| 20 | APScheduler | 自动化任务工具 | [User Guide](https://apscheduler.readthedocs.io/en/stable/userguide.html) | job store、executor、misfire、coalescing | 任务错过/合并/执行器模型成熟 | 借鉴任务状态、错过补偿、并发控制 |
| 21 | schedule | Python 定时库 | [Docs](https://schedule.readthedocs.io/en/stable/index.html) | 简单 Python 定时 | 文档明确不适合精确定时，`run_pending()` 不补跑错过任务 | Kangkang 不能只依赖简单轮询，要显式记录 missed job |
| 22 | PyInstaller Runtime | 打包发布文档 | [Docs](https://pyinstaller.org/en/stable/runtime-information.html) | `sys.frozen`、`sys._MEIPASS`、资源路径 | onefile/onedir 路径差异 | 必须做运行模式、资源路径、用户路径自检 |
| 23 | PyInstaller Operating Mode | 打包发布文档 | [Docs](https://pyinstaller.org/en/v5.13.1/operating-mode.html) | onefile/onedir、临时目录、调试差异 | onefolder 更易排障，onefile 启动慢 | 发布应保留 installer、portable、onedir debug 三形态 |
| 24 | PyInstaller Usage | 打包发布文档 | [Docs](https://www.pyinstaller.org/en/stable/usage.html) | Windows manifest、资源、UAC 选项 | 权限 manifest 影响运行 | 不默认请求管理员权限，避免和微信权限错层 |
| 25 | GitHub Releases | 发布规范 | [Docs](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases) | Release Notes、资产下载、API | 二进制资产适合放 Release | EXE/zip/setup 不应长期进源码仓库 |
| 26 | GitHub Large Files | 发布规范 | [Docs](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) | 大文件限制 | 50 MiB 警告、100 MiB 阻止 | 安装包走 Release Asset，源码仓库保持轻 |
| 27 | GitHub Issue Templates | 项目治理 | [Docs](https://docs.github.com/articles/configuring-issue-templates-for-your-repository) | Bug/Feature 模板、issue forms | 降低反馈成本 | 建立诊断包字段化问题反馈 |
| 28 | GitHub Generated Release Notes | 发布规范 | [Docs](https://docs.github.com/repositories/releasing-projects-on-github/automatically-generated-release-notes) | 自动 Release Notes | PR/贡献者/标签分类 | 后续用标签生成发布说明，再人工补用户版摘要 |
| 29 | Keep a Changelog | 版本日志规范 | [Docs](https://keepachangelog.com/en/1.1.0/) | Added/Changed/Deprecated/Removed/Fixed/Security | 面向人类可读 | 建立 `CHANGELOG.md`，不要只堆技术日志 |
| 30 | Semantic Versioning | 版本号规范 | [Docs](https://semver.org/) | MAJOR.MINOR.PATCH | patch/minor/major 语义清晰 | v3.5.x 用于兼容升级，v4 才做架构断裂 |
| 31 | pywinauto | Windows UI 自动化库 | [Docs](https://pywinauto.readthedocs.io/en/latest/) | Windows GUI 自动化 | UIA/win32 后端 | 继续作为当前发送后端的工程依据 |
| 32 | wxauto | 微信客户端自动化参考 | [GitHub](https://github.com/cluic/wxauto) | Windows 微信客户端 UIAutomation 发/收消息 | 微信 UIA 路线成熟参考 | 可做可选后端，不在 P0 强制替换 |

## 3. 同类项目迭代做了什么

### 天气展示类

同类天气应用逐步从“显示今天温度”扩展到“多源、多指标、风险可视化”：

- 小时级预报：Breezy Weather、Open-Meteo、Discord WeatherBot 都强调小时或 5 日预报。
- 多日预报：多日趋势是天气工具基础能力，但 Kangkang 当前日报只需要明后天简报，避免过长。
- AQI/UV/花粉：Breezy Weather 和 Discord WeatherBot 都加入空气质量；这对 Kangkang 可作为 P2，不应抢 P0。
- 降雨概率：Kangkang 已经具备 3 小时段降雨概率，继续强化阈值和突增判断。
- 天气预警：Weatherbot 的多级预警思路适合 Kangkang 的“短风险补发”，但要保持少打扰。
- 多城市：Bot 类项目通常允许保存多个地点；Kangkang 更适合“每个微信对象绑定一个城市”。
- 缓存机制：Open-Meteo 超时和 wttr 兜底已有基础，下一步要让缓存状态更可读。
- 卡片 UI：可借鉴信息分层，不要大换 UI 框架。

### 天气通知类

天气 Bot 的共同点不是“群发”，而是“订阅对象、触发条件、发送历史、失败重试”：

- 每日订阅：固定时间发送完整日报。
- 多接收对象：每个对象保存目标名、城市、启用状态、测试状态。
- 异常天气触发：下雨、降温、高温、大风、空气差、UV 强时短提醒。
- 发送失败重试：只重试可恢复错误，例如焦点失败、网络超时；目标不存在不重试。
- 发送历史：按批次记录，不只记录“成功/失败”。
- 接口限流：多个城市/对象发送时使用缓存和错峰，避免短时间重复请求天气源。
- 错峰发送：多个目标之间留间隔，减少微信 UI 自动化压力。

### Windows 工具类

成熟 Windows 小工具的迭代重点通常是“设置、诊断、发布、可迁移”：

- 设置备份/恢复：PowerToys 类工具重视配置可迁移；Kangkang 应提供导出配置、导入配置、自动备份、配置损坏恢复。
- 开机自启与托盘：属于正式工具体验，但不能凌驾于 P0 发送稳定性。
- 快速开关：自动化开关、发送对象启用/禁用、开发者模式开关。
- 诊断日志：ShareX、GitHub Desktop 的问题反馈和 Release Notes 都是低支持成本的关键。
- 首次启动向导：迁移到别人电脑时，不能继承本机私人联系人；必须先设置地址和目标，再测试。
- 更新检查：P2，先只提示新版本，不做自动替换 EXE。

### 自动化任务类

自动化工具强调任务状态、锁、错过任务处理和历史：

- APScheduler 提供 job store、executor、misfire grace time 和 coalescing 的思路。
- schedule 文档明确简单轮询不补跑错过任务，说明 Kangkang 必须自己记录固定发送点是否已发送。
- UI 自动化必须串行：同时两个任务操作微信会造成误点、粘贴错位、会话切换。
- 固定发送点和轮询检查要分开：固定点发完整日报，轮询只发短风险提醒。
- 睡眠/锁屏后错过任务要有补偿窗口，超过窗口不补，避免下午补早报。

### 打包发布类

Windows 发布不是只产一个 EXE：

- PyInstaller onefile 适合普通用户，但启动慢、临时目录和杀软误报风险更高。
- onedir 更适合排障，能看清依赖和资源缺失。
- installer 适合普通用户，portable zip 适合测试和迁移。
- 用户配置、日志、缓存必须在 `%APPDATA%\KangkangWeather`，不要写到安装目录。
- 二进制资产应上传 GitHub Release，源码仓库只保留源码、测试、文档和构建脚本。
- Release 需要 `SHA256SUMS`、用户版说明、开发者变更、已知限制。

## 4. 可借鉴功能总表

| 功能 | 来源依据 | 对本软件价值 | 实现难度 | 风险 | 推荐优先级 | 是否进入 v3.5.0 |
|---|---|---|---|---|---|---|
| 多对象发送列表 | Discord WeatherBot、Bot 订阅模型 | 支持多个好友/群，但不做营销群发 | 中 | 发错对象、重复发送 | P0 | 是，已部分完成，需补 UI/验证 |
| 对象启用/禁用 | PowerToys 快速开关、Bot 订阅管理 | 不删除配置也能临时停发 | 低 | UI 状态误解 | P0 | 是 |
| 单对象测试 | GitHub Desktop 支持流程、Kangkang 现有打开会话测试 | 迁移电脑前先验证 | 低 | 测试消息误发 | P0 | 是，需更清晰结果 |
| 批量测试 | Bot 多订阅对象 | 多对象上线前降低风险 | 中 | 微信 UI 压力 | P0 | 是，默认 dry-run 或文件传输助手 |
| 发送批次记录 | ShareX 历史、Bot 发送历史 | 能定位哪一个对象失败 | 中 | 历史泄露目标名 | P0 | 是，需脱敏策略 |
| 只重试失败对象 | 自动化/RPA 重试策略 | 减少重复打扰 | 中 | 状态恢复复杂 | P0 | 是 |
| 全局发送锁 | APScheduler executor、RPA 串行控制 | 防止手动/定时同时操作微信 | 中 | stale lock | P0 | 是，需 TTL |
| 微信环境自检 | Microsoft UIPI、UIA、SendInput | 解释锁屏/权限/未登录问题 | 中 | 检测不全 | P0 | 是 |
| 可读错误码 | Power Automate 故障文档、GitHub issue 模板 | 普通用户知道下一步 | 中 | 错误分类维护 | P0 | 是 |
| 配置版本与迁移 | PowerToys 设置、SemVer | 跨版本/跨电脑稳定 | 中 | 迁移丢字段 | P0 | 是 |
| 配置损坏恢复 | Windows 工具配置实践 | 避免一个坏 JSON 让软件打不开 | 低 | 备份过多 | P0 | 是，已部分完成 |
| 查询/发送历史 | ShareX 历史、Weatherbot alert history | 支持诊断和回溯 | 中 | 隐私脱敏 | P0 | 是 |
| 开发者模式折叠 JSON | GitHub Desktop/PowerToys 设置体验 | 普通用户界面更像软件 | 中 | 隐藏排障信息 | P1 | 否，下一轮 |
| 自动化状态卡片 | APScheduler job 状态 | 显示下次执行、上次结果 | 中 | 状态复杂 | P1 | 部分进入 |
| 配置备份/恢复 | PowerToys 设置迁移 | 解决换电脑使用 | 中 | 导入不兼容 | P1 | 建议进入 v3.5.x |
| 多城市绑定 | WeatherBot 多地点 | 群 A 发武汉、群 B 发嘉鱼 | 中 | 天气缓存错配 | P1 | 部分进入 |
| 错峰发送 | Bot 限流/RPA 稳定性 | 降低微信崩溃和接口压力 | 低 | 总耗时变长 | P1 | 是 |
| 异常天气提醒 | MMM-RAIN-MAP、Weatherbot | 高价值提醒，少打扰 | 中 | 阈值误判 | P1 | 已有基础，继续 |
| 更新检查 | GitHub Desktop、ShareX | 用户知道新版 | 中 | 网络失败/安全提示 | P2 | 不进 P0 |
| AQI/UV | Breezy Weather、WeatherBot | 更完整的天气建议 | 中 | 数据源差异 | P2 | 不进 P0 |
| 托盘运行 | PowerToys | 正式桌面工具体验 | 中 | 退出/端口残留 | P2 | 已有基础，完善 |
| 开机自启 | PowerToys/Windows 工具 | 自动化长期运行 | 中 | 锁屏误解 | P2 | 已有基础，需文档 |
| 插件化天气源 | Breezy Weather 多源 | 长期扩展 | 高 | 架构膨胀 | P3 | 否 |
| 云端同步配置 | 多设备工具常见 | 多设备迁移 | 高 | 隐私和账号体系 | P3 | 否 |
| 企业微信/Telegram/邮件 | 多渠道通知工具 | 扩展渠道 | 中-高 | 偏离本地微信定位 | P3 | 否 |

## 5. 不适合当前加入的功能

| 功能 | 为什么不适合当前阶段 | 风险 | 建议放到哪个阶段 |
|---|---|---|---|
| 云端账号系统 | 当前核心是本地工具，账号系统会引入后端、认证、隐私合规 | 数据泄露、维护成本高 | P3 以后，除非有明确用户规模 |
| 大型数据库 | JSON/JSONL 足够承载配置、历史、诊断 | 迁移复杂、打包变重 | P3，除非历史数据量明显增长 |
| Web 控制台重写 | 现有 Tkinter + 内置 HTTP 已能跑 | 分散主线，拖慢稳定性 | P3 或单独 UI 版本 |
| 多账号微信 | 官方微信窗口和账号状态复杂 | 发错账号、隐私风险 | P3，不建议近期做 |
| 群成员管理 | 需要读取群结构或聊天信息 | 隐私和误用风险 | 不建议做 |
| 聊天内容读取 | 与天气提醒定位无关 | 隐私风险高 | 禁止 |
| 微信营销群发 | 与产品定位冲突 | 账号风险、骚扰风险 | 禁止 |
| 复杂 AI 对话 | 不是天气自动提醒主线 | 云端依赖、成本、隐私 | P3，且需用户明确要求 |
| 强行重写 UI 框架 | 当前风险在自动化和发布，不在框架 | 破坏已验证能力 | 不进入 v3.x |
| 插件市场 | 需要生态、权限、签名和安全策略 | 复杂度过高 | P3+ |

## 6. 对 Kangkang Weather 的定位修正

Kangkang Weather 当前不应只是“天气查询器”。普通天气 App 已经很多，它的独特价值在于“本地微信天气自动提醒”：

- 天气展示增强可以做，但只能服务于提醒质量。
- 自动化稳定性必须优先于 UI 炫技。
- 多对象发送必须以“用户自用提醒”为边界，不做营销群发。
- 微信自动化必须诚实说明限制：官方 Windows 微信没有公开本地发消息 API；本项目只能控制已登录、可交互、同权限层级的真实微信窗口。
- 下一版应围绕“多对象发送 + 自动化状态机 + 诊断中心 + 迁移可用 + 正式发布”推进。

## 7. 推荐下一版功能池

### P0：必须做

- 多对象发送列表、启用/禁用、单对象测试、批量测试。
- 发送批次、发送历史、只重试失败对象、防重复锁。
- 手动发送和定时发送冲突处理。
- 微信环境自检、目标会话检测、锁屏/权限/未登录判断。
- 配置版本号、旧配置迁移、配置损坏备份恢复。
- 日志增强、诊断包增强、打包路径自检。
- 发送失败错误码、用户可读错误提示。

### P1：应该做

- 自动化状态卡片：运行中/已跳过/失败/下次执行。
- 下次发送时间、上次发送结果、最近发送历史页面。
- 开发者模式折叠 JSON。
- 配置备份/恢复和换电脑迁移向导。
- 多城市绑定、错峰发送、异常天气提醒。
- 天气接口失败缓存兜底的可视化。
- README、FAQ、TROUBLESHOOTING、CHANGELOG、Bug report 模板。

### P2：可以做

- 开机自启、托盘运行体验优化。
- 自动更新检查。
- 未来 3 天预报、小时级降雨概率增强。
- AQI、UV、主题切换。
- 首次启动向导视觉优化。
- 设置页和安装包引导页进一步重构。

### P3：未来做

- 插件化天气源。
- 插件化发送渠道。
- 企业微信、邮件、Telegram。
- Web 控制台独立化。
- 云端同步配置、多设备同步。
- 更完整的数据统计。
- 多账号微信。
