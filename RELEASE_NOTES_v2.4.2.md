# Kangkang Weather v2.4.2

## 重点更新

- 微信发送改为键盘提交优先：粘贴成功后先 `Enter`，失败再 `Ctrl+Enter`。
- 默认关闭发送按钮坐标点击兜底，避免误点表情、加号或其他微信控件。
- 发送失败诊断改进：消息已经粘贴但没有提交时，会归类为“消息已粘贴但没有发送出去”，不再误判为剪贴板不可用。
- 天气日报改为“今日分时段提醒 + 明天/后天简报”，并支持保存发送前缀。
- 默认配置新增 `wechat_send_strategy: "enter_first"` 和 `allow_send_button_coordinate_fallback: false`。
- 保留全国地址选择、天气查询记录、自动化任务和安装/便携两种交付方式。

## 交付物

- `KangkangWeather-v2.4.2.zip`：便携版。
- `KangkangWeatherSetup-v2.4.2.exe`：安装版，不需要管理员权限。
- `SHA256SUMS-v2.4.2.txt`：文件校验信息。

## 已知限制

- 仅支持 Windows 10/11 + 官方 Windows 微信客户端，且微信必须已登录。
- 目标好友或群名称必须和微信搜索结果显示名一致。
- 如果微信当前快捷键或输入框状态阻止 `Enter/Ctrl+Enter` 提交，程序会停止并保留诊断，不会再默认坐标点击发送按钮。
- 安装包没有代码签名，Windows SmartScreen 可能提示风险。
