# WeChat Weather Sender

这个小适配器把天气预报生成和微信发送拆开：

- 默认 dry-run，只打印将要发送的内容。
- 加 `--real` 后才会调用 `wxauto.SendMsg` 发送到 Windows 微信。
- 默认联系人是 `湘楠`，测试时会先切到这个会话再发送。

## 安装依赖

`wxauto` 官方文档标注支持 Python 3.9-3.12。当前机器默认是 Python 3.14，所以如果安装失败，建议单独安装 Python 3.12 后用 `py -3.12` 执行下面命令。

```powershell
python -m pip install requests wxauto
```

当前目录已经有 `requests` 和 `pywinauto`，但本机这次未成功安装 `wxauto`。真实发送前需要先确认：

```powershell
python -c "import wxauto; print(wxauto)"
```

## 预览天气

```powershell
python -m wechat_weather.cli send-weather --config .\wechat_weather_config.example.json
```

## 真实发送到湘楠

```powershell
python -m wechat_weather.cli send-weather --config .\wechat_weather_config.example.json --real --backend pywinauto-session
```

如果 `wxauto` 暂时不可用，但微信窗口已经打开到目标聊天，可以使用备用后端发送到当前聊天窗口：

```powershell
python -m wechat_weather.cli send-text --contact 当前聊天 --text "微信自动化测试" --real --backend pywinauto-active
```

这个备用后端不会自动搜索或切换联系人，只会给当前微信主窗口正在打开的聊天发送消息。如果你传入的是具体联系人名，它会先检查当前聊天标题是否一致，不一致就取消发送。

更推荐的 Windows 微信备用后端是 `pywinauto-session`，它会先点击左侧可见会话，再校验标题：

```powershell
python -m wechat_weather.cli send-weather --contact 湘楠 --real --backend pywinauto-session
```

服务启动后会每 2 小时轮询天气。第一次轮询只建立基准；后续只有降雨、天气级别或气温出现明显变化时，才会自动补发短提醒。

## 发送普通文本

```powershell
python -m wechat_weather.cli send-text --contact 文件传输助手 --text "微信自动化测试" --real
```

## 诊断环境

```powershell
python -m wechat_weather.cli diagnostics
```

## 启动本地软件页面

```powershell
python -m wechat_weather.cli serve --config .\wechat_weather_config.example.json --window-handle 199668
```

打开浏览器访问：

```text
http://127.0.0.1:8765/
```

## 每天定时发送

确认真实发送可用后，可以用 Windows 任务计划程序创建每日任务。命令主体类似：

```powershell
C:\Python314\python.exe -m wechat_weather.cli send-weather --config D:\网页设计1\wechat_weather_config.example.json --real --backend pywinauto-session
```

注意：个人微信自动化依赖桌面客户端状态。发送时 Windows 需要已登录微信，微信窗口和系统输入法状态也可能影响稳定性。
