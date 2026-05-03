# KangkangWeather v3.1 用户体验与功能完善工程执行文档

生成时间：2026-05-03  
当前基线：v3.0.0  
目标版本建议：v3.1.0  
执行目标：在 v3.0.0 的可靠性地基上，优先优化普通用户体验、迁移流程、自动化可解释性和长期维护能力。

---

## 1. 本轮调研结论

### 1.1 参考产品与资料

| 来源 | 观察到的迭代方向 | 对 KangkangWeather 的启发 |
|---|---|---|
| [Power Automate Desktop 2024-06 更新](https://www.microsoft.com/en-us/power-platform/blog/power-automate/june-2024-update-of-power-automate-for-desktop/) | 增加 UI 元素识别图片兜底、流程超时设置 | 微信 UI 自动化要有多级识别兜底、超时和失败中止，不应无限等待 |
| [Power Automate Desktop 2206.1 Release Notes](https://learn.microsoft.com/en-us/power-platform/released-versions/power-automate-desktop/2206.1) | 优化 selector 编辑、减少启动错误打扰、增加日志目录 | 控制台要少弹干扰提示，更多通过托盘状态/诊断页表达 |
| [pywinauto Remote Execution Guide](https://pywinauto.readthedocs.io/en/latest/remote_execution.html) | RDP 最小化/断开会破坏 GUI 自动化，锁屏场景天然不稳定 | 必须继续坚持“息屏可以、睡眠/锁屏/注销不强发”的设计边界 |
| [wxauto 常见问题](https://docs.wxauto.org/docs/issues.html) | 明确基于 Windows UI 自动化；最小化会导致 UI 绘制慢；某些场景仍需激活微信 | 文案和诊断必须告诉用户：不是后台 API，而是前台/半前台 UI 自动化 |
| [wxauto GitHub Releases](https://github.com/cluic/wxauto/releases) | 开源项目没有正式 release 包 | 我们的优势应放在安装包、升级包、release notes、诊断包完整性 |
| [GitHub Desktop Releases](https://github.com/desktop/desktop/releases) | Release notes 固定分为 Added / Fixed / Improved，用户一眼知道升级价值 | 后续每版 release notes 也按 Added / Fixed / Improved / Known limits 输出 |
| [GitHub Desktop 更新文档](https://docs.github.com/en/desktop/installing-and-authenticating-to-github-desktop/updating-github-desktop) | 支持手动检查更新，重启后安装更新 | KangkangWeather 需要“检查新版本 / 下载新版 / 保留配置”的升级体验 |
| [Home Assistant 自动化排障](https://www.home-assistant.io/docs/automation/troubleshooting/) | 自动化 trace 显示每一步执行路径、时间线和细节 | KangkangWeather 要做“为什么没发”的可视化 trace，而不是只丢 JSON |
| [Home Assistant 备份与迁移](https://www.home-assistant.io/common-tasks/general/) | 强调备份、迁移到新设备、恢复前检查容量和依赖 | KangkangWeather 要有“迁移包/诊断包/配置导入导出”，跨电脑更稳 |
| [Open-Meteo Docs](https://open-meteo.com/en/docs) | 支持多天气模型、可比较不同模型 | 天气详情页要展示数据源一致性，而不是只显示最终结论 |
| [Open-Meteo GitHub](https://github.com/open-meteo/open-meteo) | 无 Key、开源、多模型、可自托管 | 继续保持无 Key 默认体验，同时为高级用户保留自定义天气源可能性 |

### 1.2 同类产品迭代共性

同类产品每次迭代通常不只是“加功能”，而是围绕以下几个主题滚动优化：

1. **降低首次成功门槛**  
   新手不需要理解底层 UI 自动化，只需要按向导一步步验证。

2. **让失败可解释**  
   用户不应该只看到“失败”，而要看到“哪一步失败、为什么、下一步做什么”。

3. **把自动化执行过程可视化**  
   类似 Home Assistant trace，一次自动化执行应该有完整时间线。

4. **减少打扰**  
   后台异常不要乱弹窗口，优先用托盘颜色、状态卡片、诊断页表达。

5. **升级和迁移友好**  
   软件发给别人后，不能沿用旧电脑目标；升级后不能丢用户配置。

6. **把高风险操作显式化**  
   坐标点击、时间段外发送、真实发送测试都必须有二次确认。

7. **长期运行可观测**  
   需要日志、历史、运行状态、最近失败、下次执行、补偿任务。

---

## 2. 当前 v3.0.0 基线

### 2.1 已具备能力

当前 v3.0.0 已完成：

- 自动发送环境守门器：`wechat_weather/readiness.py`
- 息屏/睡眠检测与插电省电配置：`wechat_weather/power.py`
- 定时任务医生基础接口：`wechat_weather/scheduler.py`
- 固定时间日报 180 分钟补偿窗口：`wechat_weather/monitor.py`
- Web API 接入 readiness / power / scheduler：`wechat_weather/server.py`
- Web 控制台新增入口：`wechat_weather/web_console.html`
- CLI 新增：
  - `readiness`
  - `power-status`
  - `power-apply`
  - `scheduler-status`
  - `scheduler-repair`
- 已生成：
  - `dist/KangkangWeather-v3.0.0.zip`
  - `dist/KangkangWeatherSetup-v3.0.0.exe`
  - `dist/SHA256SUMS-v3.0.0.txt`
- 自动测试：40 个全部通过。

### 2.2 当前体验短板

v3.0.0 的可靠性地基已经有了，但用户体验还不够顺：

1. **诊断信息还是偏工程化**  
   readiness 返回 JSON，普通用户看不懂。

2. **Web 控制台信息结构太散**  
   页面功能多，但用户不知道下一步该点什么。

3. **首次设置和跨电脑迁移没有完整闭环**  
   目前有 setup，但还不是“逐步验证式迁移向导”。

4. **定时任务医生只有接口，没有完整操作 UI**  
   用户不能直观看到任务缺什么、如何修。

5. **固定时间补偿状态不可视化不足**  
   后端已记录 pending/expired，但前端还没有清楚展示时间线。

6. **天气查询记录有了，但没有“数据源健康评分”**  
   用户不知道今天预报是否可信、是否使用缓存、是否多源分歧。

7. **安装包/便携包升级体验仍弱**  
   没有检查更新、备份配置、升级前确认。

8. **用户文案不够像产品**  
   现在更像开发者工具，需要变成“普通人能用”的引导。

---

## 3. v3.1.0 产品目标

v3.1.0 命名建议：

```text
KangkangWeather v3.1.0 - 易用诊断版
```

目标：

1. 用户打开软件后 30 秒内知道：
   - 现在能不能自动发。
   - 下次什么时候发。
   - 如果不能发，为什么不能发。
   - 要点哪个按钮修。

2. 新电脑首次运行必须走向导：
   - 地址选择。
   - 微信目标填写。
   - 文件传输助手测试。
   - 目标会话测试。
   - 测试消息。
   - 省电模式检查。
   - 定时任务创建。
   - 完成。

3. 每一次自动化执行都能追踪：
   - 计划触发。
   - readiness 检查。
   - 天气获取。
   - 微信打开。
   - 消息写入。
   - 发送验证。
   - 成功/失败/等待补偿。

4. 长期运行更省心：
   - 托盘状态明确。
   - 异常少打扰。
   - 失败可重试。
   - 配置可备份迁移。

---

## 4. v3.1.0 重点设计

### 4.1 首页重构为“状态总览”

首页不再先展示大段配置，而是先展示 6 个状态卡片。

#### 卡片 1：自动发送环境

显示：

```text
当前可以自动发送
或
当前不能自动发送：微信未打开
```

按钮：

```text
重新检查
查看修复方法
```

状态颜色：

- 绿色：ready
- 黄色：warning
- 红色：blocked

#### 卡片 2：微信状态

显示：

```text
微信窗口：已找到
当前权限：普通用户
搜索框：可访问
输入框：可访问
```

异常示例：

```text
微信未打开，无法自动发送。
请先打开并登录官方 Windows 微信。
```

#### 卡片 3：省电运行

显示：

```text
屏幕 5 分钟后关闭
睡眠：从不
状态：适合长期运行
```

异常示例：

```text
电脑会在 30 分钟后睡眠，到点可能无法发送。
```

#### 卡片 4：下次发送

显示：

```text
下次完整日报：明天 06:00
补偿截止：09:00
轮询检查：每 120 分钟
```

#### 卡片 5：待补偿任务

显示：

```text
无待补偿任务
```

或：

```text
06:00 天气日报未发送
原因：电脑锁屏
将在 09:00 前恢复后补发
```

#### 卡片 6：最近一次结果

显示：

```text
今天 06:00 已发送成功
```

或：

```text
今天 06:00 未发送：微信未打开
```

### 4.2 首次设置改为分步向导

新增“设置进度条”：

```text
1 地址
2 微信目标
3 省电检查
4 微信测试
5 定时任务
6 完成
```

每一步只做一件事。

#### Step 1：选择天气地址

保留全国省/市/区县选择。

要求：

- 默认推荐最近一次地址。
- 支持搜索。
- 不显示经纬度。
- 显示一句确认文案：

```text
将使用「湖北省 / 咸宁市 / 嘉鱼县」生成天气预报。
```

#### Step 2：填写微信目标

字段：

```text
微信好友/群名称
```

说明：

```text
名称必须和微信搜索结果显示一致。
建议先用文件传输助手完成测试。
```

#### Step 3：省电运行检查

展示：

```text
屏幕可以关闭
睡眠必须关闭
不能注销
锁屏时不会强行发送
```

按钮：

```text
检查省电设置
一键设置为插电不睡眠
```

#### Step 4：微信测试

按钮顺序固定：

```text
打开文件传输助手
发送测试消息到文件传输助手
打开目标会话
发送测试消息到目标
```

未完成前禁止进入下一步。

#### Step 5：定时任务

默认推荐：

```text
固定日报：06:00
补偿窗口：180 分钟
运行时间段：07:00-22:00
```

按钮：

```text
创建定时任务
检查定时任务
```

#### Step 6：完成

展示最终摘要：

```text
天气地址：嘉鱼县
微信目标：微信快存
固定日报：06:00
补偿截止：09:00
省电运行：已配置
定时任务：已创建
```

### 4.3 自动化 Trace 页面

参考 Home Assistant 的 automation trace。

新增页面：

```text
发送时间线
```

每次运行生成一个 `run_id`。

时间线示例：

```text
06:00:00 计划触发：嘉鱼县 -> 微信快存
06:00:01 检查自动发送环境
06:00:01 阻断：电脑处于锁屏状态
06:00:01 已加入补偿队列，截止 09:00
07:18:22 检测到环境恢复
07:18:23 获取天气数据
07:18:25 打开微信目标会话
07:18:27 写入消息
07:18:28 Enter 发送
07:18:29 发送成功
```

每一步字段：

```json
{
  "run_id": "run-20260504-default-0600",
  "step": "check_readiness",
  "status": "blocked",
  "started_at": "...",
  "ended_at": "...",
  "duration_ms": 120,
  "summary": "微信未打开",
  "detail": {}
}
```

### 4.4 诊断改成人话

目前 JSON 保留给高级用户，但默认显示人话。

例子：

```text
问题：微信未打开
为什么会这样：程序没有找到官方 Windows 微信主窗口。
怎么修：
1. 打开微信。
2. 确认已经登录。
3. 不要以管理员权限单独运行微信。
4. 回到这里重新检查。
```

常见分类：

- 电脑会睡眠
- 当前锁屏
- 微信未打开
- 微信未登录
- 权限不一致
- 定时任务不存在
- 定时任务路径失效
- 天气源超时
- 目标会话找不到
- 消息已粘贴但未提交

### 4.5 定时任务医生 UI 完整化

新增专门页面：

```text
定时任务医生
```

显示：

```text
登录启动任务：正常 / 缺失 / 路径失效
周期检查任务：正常 / 缺失 / 路径失效
当前用户：jiank
运行方式：仅当用户登录时运行
权限：普通用户
上次运行：2026-05-03 14:30
上次结果：成功
```

按钮：

```text
一键修复
删除旧任务
立即运行一次
复制诊断信息
```

一键修复前确认：

```text
将创建两个当前用户定时任务：
1. 登录后启动 KangkangWeather
2. 每分钟检查是否有到期或待补偿任务
不会使用 SYSTEM，不会在注销后运行。
```

### 4.6 配置备份与迁移

参考 Home Assistant 的备份/迁移思路。

新增：

```text
导出迁移包
导入迁移包
```

迁移包包含：

```text
config.json
automation_jobs
locations
wechat_targets
message settings
power recommendations
```

迁移包不包含：

```text
微信聊天内容
微信消息正文历史
真实联系人聊天记录
app.log 原文
weather cache 大文件
```

导入后必须重新验证：

```text
微信目标
定时任务
省电运行
```

迁移包文件名：

```text
KangkangWeather-migration-20260503-143000.zip
```

### 4.7 自动更新体验

参考 GitHub Desktop。

新增：

```text
检查新版本
```

实现策略：

- 先不做自动静默更新。
- 只检查 GitHub Release 最新版本。
- 显示：

```text
当前版本：3.1.0
最新版本：3.1.1
更新内容：...
下载新版
```

安装新版前提醒：

```text
升级不会删除你的用户配置。
建议先导出迁移包。
```

### 4.8 天气可信度与数据源体验

基于 Open-Meteo 多模型能力。

天气区域新增：

```text
数据源状态：3/4 成功
预报一致性：存在分歧
使用缓存：否
耗时：2.3 秒
```

简化为三档：

```text
可信度高：多源一致
可信度中：部分源失败
谨慎参考：多源分歧或使用缓存
```

用户文案：

```text
多个天气模型对降雨判断不一致，已按偏高风险提醒。
```

---

## 5. 后端实施任务

### 5.1 新增 Run Trace 数据结构

新增模块建议：

```text
wechat_weather/run_trace.py
```

核心接口：

```python
start_run(job_id, run_type, due_at=None) -> run_id
append_step(run_id, step, status, summary, detail=None)
finish_run(run_id, status, summary)
read_runs(limit=50)
read_run(run_id)
```

存储方式：

v3.1.0 可以先用 JSONL，v3.2.0 再迁 SQLite。

路径：

```text
%APPDATA%\KangkangWeather\run_traces.jsonl
```

每条记录：

```json
{
  "run_id": "run-20260504-default-0600",
  "job_id": "default",
  "type": "fixed_weather",
  "step": "check_readiness",
  "status": "blocked",
  "summary": "微信未打开",
  "detail": {},
  "created_at": "2026-05-04T06:00:01"
}
```

保留策略：

```text
最近 5000 条 step
或最近 30 天
```

### 5.2 接入 Trace 的位置

必须接入：

- `WeatherMonitor.run_due`
- `_send_fixed_weather`
- `_expire_fixed_weather`
- `_check_job`
- `send-weather`
- `test-message`
- `open-target`
- `readiness`
- `weather fetch`

最低要求：

```text
每次固定日报都有 run_id
每次测试消息都有 run_id
每次手动发送都有 run_id
```

### 5.3 新增迁移包模块

新增：

```text
wechat_weather/migration.py
```

接口：

```python
export_migration_package(config_path=None) -> Path
inspect_migration_package(path) -> dict
import_migration_package(path, require_reverify=True) -> dict
```

导入后：

```text
setup_complete = false
wechat_targets[].verified = false
scheduler_verified = false
machine_id = 当前机器
```

### 5.4 微信目标验证字段

配置中新增：

```json
{
  "wechat_targets": [
    {
      "id": "target",
      "name": "微信快存",
      "enabled": true,
      "default": true,
      "verified": true,
      "verified_at": "2026-05-03T14:30:00",
      "last_open_test_at": "...",
      "last_send_test_at": "..."
    }
  ]
}
```

兼容旧配置：

```text
没有 verified 字段时默认为 false
但本机已有 setup_complete=true 时不强制阻断手动发送，只阻断自动发送
```

### 5.5 定时任务状态增强

当前 `scheduler.py` 已有基础状态。

v3.1.0 增强：

- 解析 `schtasks /Query /XML`
- 提取：
  - author
  - user id
  - logon type
  - run level
  - trigger
  - action path
  - arguments
  - start in
  - last run time
  - last task result
  - next run time

返回结构：

```json
{
  "ok": false,
  "tasks": [
    {
      "name": "KangkangWeather-MonitorDue",
      "exists": true,
      "path_ok": false,
      "logon_type_ok": true,
      "run_level_ok": true,
      "last_result": "0x0",
      "fixes": ["action_path"]
    }
  ]
}
```

### 5.6 更新检查

新增：

```text
wechat_weather/updater.py
```

接口：

```python
check_latest_release(repo="jiankang3053/kangkang") -> dict
```

返回：

```json
{
  "current_version": "3.1.0",
  "latest_version": "3.1.1",
  "has_update": true,
  "release_url": "...",
  "assets": []
}
```

失败时：

```text
不影响主程序运行
只显示“检查更新失败”
```

---

## 6. API 变更

### 6.1 新增 API

```http
GET  /api/runs/timeline?limit=50
GET  /api/runs/{run_id}

POST /api/migration/export
POST /api/migration/import
POST /api/migration/inspect

POST /api/wechat/verify-target

GET  /api/update/check
```

### 6.2 调整 API

```http
GET /api/state
```

新增：

```json
{
  "dashboard": {
    "can_send_now": true,
    "next_fixed_send_at": "...",
    "pending_compensations": [],
    "last_run": {},
    "power_recommended": true,
    "scheduler_ok": true
  }
}
```

```http
POST /api/wechat/test-message
```

新增：

```json
{
  "run_id": "...",
  "target_verified": true
}
```

```http
POST /api/send-weather
```

新增：

```json
{
  "run_id": "...",
  "trace_url": "/runs/..."
}
```

---

## 7. 前端实施任务

### 7.1 首页 Dashboard

改造 `wechat_weather/web_console.html`：

新增顶部 dashboard：

```text
自动发送环境
微信状态
省电运行
下次发送
待补偿
最近结果
```

每个卡片有：

- 标题
- 状态徽标
- 一句话结论
- 主操作按钮

### 7.2 向导式首次设置

把当前 setup overlay 改成分步模式。

状态存在前端：

```javascript
setupStep = 1..6
```

完成条件：

```text
Step 1 必须选地址
Step 2 必须填微信目标
Step 3 必须检查 power/readiness
Step 4 必须至少完成文件传输助手测试
Step 5 必须创建或检查定时任务
Step 6 保存
```

### 7.3 发送时间线页面

新增区域：

```text
最近运行
```

展示：

- 运行类型
- 目标
- 状态
- 时间
- 展开详情

展开后显示 step 列表。

### 7.4 诊断人话化

新增前端 formatter：

```javascript
formatHumanDiagnostic(error_analysis, readiness, scheduler)
```

不要默认把 JSON 放最上面。

默认显示：

```text
问题
原因
怎么修
高级信息
```

高级信息折叠。

### 7.5 定时任务医生页面

显示：

```text
任务名
状态
问题
修复按钮
```

缺失或路径错误时：

```text
一键修复
```

### 7.6 迁移包页面

新增：

```text
导出迁移包
导入迁移包
```

导入前预览：

```text
地址数量
微信目标数量
自动化任务数量
是否来自其他电脑
导入后是否需要重新验证
```

---

## 8. 用户体验文案标准

### 8.1 息屏说明

统一文案：

```text
屏幕可以关闭，但电脑不能睡眠。
关闭屏幕只是让显示器变黑，程序和微信还在运行。
睡眠会暂停程序、微信和网络，到点不能直接发送。
```

### 8.2 锁屏说明

```text
锁屏时不会强行操作微信。
如果固定日报到点时电脑锁屏，程序会记录错过，并在补偿窗口内等待你恢复可用环境后再发送。
```

### 8.3 微信说明

```text
本软件控制的是你电脑上已经登录的官方 Windows 微信。
这不是微信后台 API，所以发送时需要微信窗口可访问。
```

### 8.4 定时任务说明

```text
定时任务只在当前用户登录时运行。
这能保证微信窗口存在，也避免在注销或锁屏后台误操作。
```

### 8.5 迁移说明

```text
把软件发给别人电脑后，需要重新选择地址、填写微信目标，并完成测试消息验证。
这是为了避免把消息发到错误的人。
```

---

## 9. 测试计划

### 9.1 自动测试

新增测试文件建议：

```text
tests/test_v31_trace.py
tests/test_v31_migration.py
tests/test_v31_dashboard_api.py
tests/test_v31_scheduler_doctor.py
```

必须覆盖：

- run trace 创建、追加、读取、裁剪。
- 固定日报生成 run_id。
- readiness blocked 时 trace 记录 blocked step。
- 补偿成功时 trace 串联原 due_at。
- 迁移包导出不包含日志和聊天内容。
- 导入迁移包后微信目标变为未验证。
- 定时任务 XML 解析正常。
- `/api/state` 返回 dashboard。
- `/api/update/check` 网络失败时不影响主程序。
- 旧 v3.0 配置可读。

### 9.2 UI 测试

用 Playwright 检查：

- 桌面宽度 1366。
- 小窗口 760x560。
- 手机宽度 390。

页面：

- 首页 dashboard 不重叠。
- 设置向导按钮可见。
- 诊断详情可展开/收起。
- 时间线长内容可滚动。
- 定时任务医生按钮不挤压。

### 9.3 本机真实测试

测试顺序：

1. 微信未打开，首页显示 blocked。
2. 打开微信，首页状态变化。
3. 文件传输助手打开测试。
4. 文件传输助手测试消息。
5. 设置固定时间为当前时间 + 2 分钟。
6. 等待自动发送。
7. 查看 trace。
8. 人为关闭微信，模拟补偿等待。
9. 重新打开微信，确认补偿执行。
10. 导出迁移包。
11. 使用临时 APPDATA 导入迁移包，确认需要重新验证。

### 9.4 打包测试

执行：

```powershell
python -m compileall wechat_weather tests
python -m unittest discover -s tests -v
python -m wechat_weather.cli build-package --config wechat_weather_config.example.json --output-dir dist
```

验收：

```text
KangkangWeather-v3.1.0.zip
KangkangWeatherSetup-v3.1.0.exe
SHA256SUMS-v3.1.0.txt
```

zip 内必须包含：

```text
KangkangWeather.exe
README.md
README_PORTABLE.md
RELEASE_NOTES_v3.1.0.md
config.example.json
```

---

## 10. 执行顺序

建议下一次严格按这个顺序做：

### 第 1 步：备份与版本号

- 创建 `backups/v3.1-start-YYYYMMDD-HHMMSS`
- 版本号改为 `3.1.0`
- 新增 `RELEASE_NOTES_v3.1.0.md`

### 第 2 步：Run Trace

- 新增 `run_trace.py`
- 接入 monitor fixed send
- 接入 manual send/test-message
- 增加 `/api/runs/timeline`
- 测试 trace 写入和读取

### 第 3 步：Dashboard API

- `/api/state` 增加 `dashboard`
- 聚合 readiness/power/scheduler/monitor
- 前端首页卡片使用 dashboard

### 第 4 步：诊断人话化

- 后端统一错误分类。
- 前端新增 human formatter。
- JSON 默认折叠。

### 第 5 步：首次设置向导

- setup overlay 改成 6 步。
- 每步有完成条件。
- 未完成不允许开启自动任务。

### 第 6 步：定时任务医生 UI

- 展示任务状态。
- 增加一键修复。
- 增加立即运行一次。

### 第 7 步：迁移包

- 新增 migration.py。
- 导出/导入 API。
- 导入后强制重新验证目标。

### 第 8 步：更新检查

- 新增 updater.py。
- GitHub Release 检查。
- 前端展示当前/最新版本。

### 第 9 步：测试与打包

- 单元测试。
- UI 测试。
- 本机真实测试。
- 重新打包。

---

## 11. 验收标准

v3.1.0 可以交付的标准：

```text
用户打开首页，一眼知道能不能自动发
微信未打开时，能看到明确修复方法
电脑会睡眠时，能看到明确风险
固定发送错过后，首页能看到待补偿
每次发送有 trace
trace 能解释为什么没发
新电脑首次运行有向导
迁移包导入后不会直接自动发送旧目标
定时任务医生能检查和修复任务
测试全部通过
安装包和便携包都生成
文档写清息屏/睡眠/锁屏边界
```

---

## 12. 不做的事情

v3.1.0 暂不做：

- 不接入微信 Hook。
- 不做协议登录。
- 不做真正后台无窗口发送。
- 不做云端账号系统。
- 不做商业授权。
- 不做多微信账号同时发送。
- 不强制修改锁屏策略。
- 不自动关闭 Windows 安全设置。

---

## 13. 默认决策

下一次执行时默认采用：

```text
版本：3.1.0
trace 存储：JSONL
trace 保留：最近 5000 条 step
迁移包：zip
导入迁移包后：必须重新验证微信目标
更新检查：只检查，不静默安装
默认首页：首页 dashboard
默认诊断：人话优先，JSON 折叠
默认真实测试目标：文件传输助手
默认定时任务：当前用户 InteractiveToken
默认补偿窗口：继续 180 分钟
```

