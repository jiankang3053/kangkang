# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ErrorAnalysis:
    category: str
    title: str
    summary: str
    likely_causes: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    severity: str = "error"
    retryable: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def _contains(text: str, *needles: str) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _line_contains(lines: list[str], required: tuple[str, ...], optional: tuple[str, ...]) -> bool:
    for line in lines:
        if _contains(line, *required) and _contains(line, *optional):
            return True
    return False


def analyze_error(detail: str = "", diagnostics: list[str] | None = None, context: str = "wechat") -> ErrorAnalysis:
    diagnostics = diagnostics or []
    lines = [detail, *diagnostics]
    joined = "\n".join(lines)

    if _contains(joined, "没有找到微信主窗口", "找不到微信", "WeChat-like top windows"):
        return ErrorAnalysis(
            category="wechat_window_not_found",
            title="没有找到微信窗口",
            summary="程序没有识别到官方 Windows 微信主窗口。",
            likely_causes=["微信没有启动", "微信未登录", "当前打开的是非官方客户端或窗口被系统权限隔离"],
            next_steps=["先手动打开并登录 Windows 微信", "确认能看到微信主界面后再重试", "如果用管理员权限打开了微信，也用同样权限启动本程序"],
        )

    if _contains(joined, "微信窗口已退出", "窗口已退出", "窗口消失", "window.exists returned False", "ElementNotAvailable"):
        return ErrorAnalysis(
            category="wechat_window_gone",
            title="微信窗口异常退出或不可访问",
            summary="操作过程中微信窗口消失或 UIAutomation 已无法访问，程序已停止后续输入和发送。",
            likely_causes=["微信客户端崩溃或正在更新/重启", "微信与本程序权限级别不一致", "安全软件拦截 UIAutomation 操作", "微信弹窗或异常状态导致控件树失效"],
            next_steps=["重新打开并登录官方 Windows 微信", "确认微信和本程序都用普通权限运行，或都用管理员权限运行", "先对文件传输助手发送测试消息", "失败时导出诊断包，重点查看 app.log、窗口列表和权限状态"],
        )

    if _contains(joined, "搜索框", "search") and _contains(joined, "写入失败", "找不到", "未找到精确匹配", "无法聚焦"):
        return ErrorAnalysis(
            category="wechat_search_failed",
            title="微信搜索目标失败",
            summary="程序没有安全地写入搜索框或没有找到精确匹配的好友/群。",
            likely_causes=["微信搜索框不可用或被弹窗遮挡", "好友/群名称与搜索结果显示名不完全一致", "微信与本程序权限级别不一致", "当前微信版本控件结构变化"],
            next_steps=["在微信里手动搜索目标名称并核对完整显示名", "关闭微信弹窗后重试打开会话测试", "先把目标会话置顶或手动发一条消息让它出现在左侧列表", "用文件传输助手做测试，确认基础发送链路正常"],
        )

    if _contains(joined, "没有成功打开目标会话", "目标是", "搜索不到目标", "好友/群名称"):
        return ErrorAnalysis(
            category="wechat_target_not_found",
            title="没有打开目标会话",
            summary="微信已打开，但目标好友或群没有被精确匹配到。",
            likely_causes=["微信好友/群名称和搜索结果显示名不完全一致", "目标会话搜索结果不是第一项或被企业微信/公众号结果干扰", "目标会话不在当前登录账号里"],
            next_steps=["在微信里手动搜索目标名称并核对显示名", "把目标会话置顶或先手动发一条消息让它出现在左侧列表", "在软件里把微信好友名称改成搜索结果的完整显示名"],
        )

    if _contains(joined, "聊天输入框", "chat input", "chat_input") and _contains(joined, "没有找到", "not found", "无法聚焦"):
        return ErrorAnalysis(
            category="wechat_input_not_ready",
            title="聊天输入框不可用",
            summary="目标聊天可能打开了，但输入区域没有准备好或无法聚焦。",
            likely_causes=["微信窗口还在加载", "当前打开的是订阅号/服务号等不可直接输入页面", "微信弹窗或登录状态遮挡了输入框"],
            next_steps=["手动点一下目标聊天输入框后重试", "关闭微信里的弹窗或更新提示", "确认该会话允许直接发送文本消息"],
        )

    if _contains(joined, "消息已粘贴但没有提交发送", "paste_ok -> enter_failed", "send_key"):
        if _contains(joined, "没有提交发送", "未确认提交", "仍停留在输入框"):
            return ErrorAnalysis(
                category="send_not_submitted",
                title="消息已粘贴但没有发送出去",
                summary="程序已经把消息放进微信输入框，但 Enter/Ctrl+Enter 没有让微信提交发送。",
                likely_causes=["微信输入框焦点被弹窗或表情面板抢走", "当前微信快捷键设置或版本行为异常", "会话输入区处于临时不可发送状态"],
                next_steps=["先手动按一次 Enter 或 Ctrl+Enter，确认微信当前快捷键能发送", "关闭表情面板、弹窗或浮层后重试", "用“打开会话测试”重新切到文件传输助手，再发送测试消息"],
            )

    if _line_contains(lines, ("剪贴板", "clipboard"), ("失败", "无法", "OpenClipboard")):
        return ErrorAnalysis(
            category="clipboard_unavailable",
            title="剪贴板暂时不可用",
            summary="程序没有成功读写 Windows 剪贴板，因此不能安全粘贴消息。",
            likely_causes=["另一个程序正在占用剪贴板", "远程桌面/剪贴板同步正在锁定剪贴板", "安全软件拦截了剪贴板访问"],
            next_steps=["等几秒后重试", "关闭剪贴板管理器或远程桌面剪贴板同步后再试", "确认安全软件没有阻止本程序访问剪贴板"],
        )

    if _contains(joined, "粘贴", "paste", "Ctrl+V") and _contains(joined, "失败", "没有找到明确可点击的发送按钮"):
        return ErrorAnalysis(
            category="paste_or_send_button_failed",
            title="消息没有成功进入输入框",
            summary="程序尝试粘贴消息后，没有确认到可点击的发送按钮。",
            likely_causes=["微信输入框未获得焦点", "当前会话输入框处于不可编辑状态", "微信版本 UI 变化导致发送按钮识别失败"],
            next_steps=["先点“打开会话测试”，确认已切到正确聊天", "手动点击输入框后再点“发送测试消息”", "如果仍失败，把运行结果里的 diagnostics 发给开发者定位"],
        )

    if _contains(joined, "发送按钮", "send_button") and _contains(joined, "点击失败", "未找到"):
        return ErrorAnalysis(
            category="send_button_failed",
            title="发送按钮点击失败",
            summary="消息可能已经在输入框中，但程序没有安全点击到明确的发送按钮。",
            likely_causes=["发送按钮未出现，通常表示消息没有粘贴进去", "微信按钮控件名称变化", "微信窗口缩放或遮挡导致点击失败"],
            next_steps=["查看微信输入框里是否已经有测试消息，必要时手动删除", "把微信窗口恢复到普通大小后重试", "优先用文件传输助手做测试"],
        )

    if _contains(joined, "首次设置未完成"):
        return ErrorAnalysis(
            category="setup_required",
            title="首次设置未完成",
            summary="便携版还没有保存默认天气地址和微信好友/群名称。",
            likely_causes=["第一次在这台电脑运行", "用户配置被删除或换了 Windows 账号"],
            next_steps=["在首次设置里保存天气地址和微信好友/群名称", "先用文件传输助手发送测试消息", "确认测试成功后再发送天气"],
            retryable=False,
        )

    if _contains(joined, "Open-Meteo", "wttr", "天气", "offline", "timeout", "timed out"):
        return ErrorAnalysis(
            category="weather_provider_failed",
            title="天气数据加载失败",
            summary="天气源请求失败或超时。",
            likely_causes=["当前网络访问天气源较慢", "Open-Meteo 或兜底源临时不可用", "本机代理/防火墙阻止请求"],
            next_steps=["稍后重试", "检查网络和代理", "如果页面显示缓存预报，可先使用最近一次预报"],
        )

    return ErrorAnalysis(
        category=f"{context}_unknown_error",
        title="执行失败，原因需要进一步定位",
        summary="程序捕获到了失败，但没有匹配到已知错误类型。",
        likely_causes=["本机微信 UI 状态与预期不一致", "依赖版本或系统权限差异", "目标会话状态特殊"],
        next_steps=["先点“刷新诊断”查看微信窗口和当前会话", "复制运行结果里的 detail、diagnostics 和 error_analysis", "用文件传输助手复现一次，区分是目标问题还是发送链路问题"],
    )
