from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import ssl
import sys
import time
from http import HTTPStatus
from http.client import HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse


HOST = "assets-proxy.anthropic.com"
PROXY_HOSTS = {
    "assets-proxy.anthropic.com",
    "a-cdn.claude.ai",
}
PORT = 443

ROOT = Path(__file__).resolve().parent
WORK_DIR = ROOT.parent
MIRROR_DIR = WORK_DIR / "claude-assets-mirror"
ASSET_DIR = MIRROR_DIR / "claude-ai" / "v2" / "assets" / "v1"
JAVAHT_DIR = WORK_DIR / "javaht-claude-desktop-zh-cn-1.2.8" / "claude-desktop-zh-cn-1.2.8" / "resources"
JYY_DIR = WORK_DIR / "Jyy1529-claude-desktop_win-zh_cn" / "claude-desktop_win-zh_cn-master" / "resources"
CERT_DIR = ROOT / "certs"
HOST_CERT = CERT_DIR / "assets_proxy_cert.pem"
HOST_KEY = CERT_DIR / "assets_proxy_key.pem"
UPSTREAM_IP_FILE = ROOT / "upstream_ip.txt"
UPSTREAM_IPS_FILE = ROOT / "upstream_ips.json"

INDEX_PATCH_MARKER = "ClaudeZhRuntimePatch"


MANUAL_I18N_FIXES = {
    "dNA5vEEsiY": "需要修改？让 Claude 编辑这个文件，而不是新建一个。",
    "mWPGSbK6BB": "今天想让我帮你处理什么？",
    "Wr33QIAXEc": "我能帮你做什么？",
    "HYZvkuDC1e": "新建任务草稿",
    "FehpsDg+98": "所有项目",
    "q5SfWNIhmo": "你的项目",
    "7Rs6WZbci3": "你创建的项目会显示在这里。",
    "1+8tjvOuk5": "创建你的第一个作品",
    "7F5OAaiiBU": "作品",
    "9R4NPWEKk0": "没有匹配“{search}”的作品",
    "DvGGrTvZod": "作品",
    "gAR0atqpRn": "作品",
    "N+zfbFx7nj": "全部作品",
    "rVjiDOZd0Z": "搜索你的作品",
    "stSAN8ehvO": "创建作品后会显示在这里。",
    "z3TvMLm89H": "搜索作品...",
    "ChatCodeExecEnabled": "允许在聊天中执行代码",
    "ChatCodeExecEnabledHint": "允许 Claude 在聊天对话的本地沙箱中运行代码。沙箱只能读取对话附件，不能访问网络。默认关闭。",
}


MANUAL_UI_REPLACEMENTS = {
    "Need changes? Ask Claude to edit the file instead of making a new one.": "需要修改？让 Claude 编辑这个文件，而不是新建一个。",
    "Design": "设计",
    "Claude Design": "Claude 设计",
    "Research preview": "研究预览",
    "Recent": "最近",
    "Your designs": "你的设计",
    "Design systems": "设计系统",
    "Examples": "示例",
    "Search designs": "搜索设计",
    "Make something new": "新建设计",
    "Design system:": "设计系统：",
    "Design system": "设计系统",
    "Design System": "设计系统",
    "Start anywhere": "从任意位置开始",
    "Add a file and design": "添加文件并创建设计",
    "Slides": "幻灯片",
    "Decks & reviews": "演示稿与评审",
    "Prototype": "原型",
    "Clickable & interactive": "可点击、可交互",
    "Product wireframe": "产品线框图",
    "Lo-fi screens & flows": "低保真界面与流程",
    "Doc": "文档",
    "Resumes, PDFs, etc": "简历、PDF 等",
    "Animatic": "动画分镜",
    "Animation": "动画",
    "Motion": "动效",
    "Designs": "设计",
    "Name": "名称",
    "Last viewed": "上次查看",
    "Owner": "所有者",
    "You": "你",
    "Back": "返回",
    "Add": "添加",
    "browse": "浏览",
    "Blank": "空白",
    "Start from scratch": "从空白开始",
    "Motion & video": "动效与视频",
    "Start": "开始",
    "Continue to generation": "继续生成",
    "Continue to generation →": "继续生成 →",
    "Set up your design system": "设置你的设计系统",
    "Tell us about your company and attach any design resources you have.": "介绍你的公司，并附上你已有的设计资源。",
    "Company name and blurb": "公司名称和简介",
    "(or name of design system)": "（或设计系统名称）",
    "e.g. Mission Impastabowl: fast-casual pasta restaurant with in-store touchscreen kiosk, mobile app and website": "例如：Mission Impastabowl：一家快餐意面餐厅，拥有店内触控点餐机、移动应用和网站",
    "Provide examples of your design system and products": "提供你的设计系统和产品示例",
    "(all optional)": "（全部可选）",
    "What works best: code and designs for your design system and your code products.": "最有效的是：设计系统和代码产品的代码与设计。",
    "Link code from GitHub": "关联 GitHub 代码",
    "Link code from your computer": "关联本机代码",
    "Drag a folder here or browse": "拖入文件夹或浏览",
    "This doesn’t upload the whole codebase; Claude will copy selected files. For large codebases, we recommend attaching a frontend-focused subfolder.": "这不会上传整个代码库；Claude 会复制选中的文件。大型代码库建议附加聚焦前端的子文件夹。",
    "This doesn't upload the whole codebase; Claude will copy selected files. For large codebases, we recommend attaching a frontend-focused subfolder.": "这不会上传整个代码库；Claude 会复制选中的文件。大型代码库建议附加聚焦前端的子文件夹。",
    "What's the presentation about?": "这个演示文稿是关于什么的？",
    "Upload a doc, share your notes, or an existing presentation to start from.": "上传文档、分享笔记，或从已有演示稿开始。",
    "Upload a doc": "上传文档",
    "Paste your notes": "粘贴笔记",
    "Existing deck": "已有演示稿",
    "Deck options": "演示稿选项",
    "Optimize for Google Slides": "针对 Google Slides 优化",
    "Only use Google Fonts": "仅使用 Google 字体",
    "Add speaker notes": "添加演讲者备注",
    "Include talking points with each slide": "为每页幻灯片加入讲稿要点",
    "Design Files": "设计文件",
    "Untitled": "未命名",
    "Share": "分享",
    "New sketch": "新草图",
    "Paste": "粘贴",
    "Edit": "编辑",
    "Discard": "放弃",
    "Save": "保存",
    "Reload": "重新加载",
    "Present": "演示",
    "Mark up": "标注",
    "Comments": "评论",
    "Simple": "简单",
    "Pro": "专业版",
    "Add something with the tools above (R · F · O · T), paste, or drop an image onto the canvas.": "使用上方工具添加内容（R · F · O · T），或粘贴/拖入图片到画布。",
    "Creations will appear here": "生成内容会显示在这里",
    "Start with a blank canvas": "从空白画布开始",
    "DROP FILES HERE": "拖放文件到这里",
    "Images, docs, references, Figma links, or folders — Claude will use them as context.": "图片、文档、参考资料、Figma 链接或文件夹，Claude 会将它们作为上下文。",
    "Describe what you want to create...": "描述你想创建的内容...",
    "Make a deck": "制作演示稿",
    "Make a doc": "制作文档",
    "Send": "发送",
    "Choose design systems": "选择设计系统",
    "Selected": "已选择",
    "Available": "可用",
    "Set up a design system": "设置设计系统",
    "Import brand, code, and assets": "导入品牌、代码和素材",
    "Drag selected design systems to reorder — the one at the top takes precedence.": "拖动已选择的设计系统以重新排序，最上方的优先。",
    "Browse": "浏览",
    "Browse Design System": "浏览设计系统",
    "Claude reads the whole design system on its own.": "Claude 会自行读取整个设计系统。",
    "No assets in Design System": "设计系统中没有素材",
    "No assets in 设计系统": "设计系统中没有素材",
    "This design system hasn't been set up yet — finish onboarding to add code, Figma files, and brand assets.": "这个设计系统尚未设置，请完成引导流程以添加代码、Figma 文件和品牌素材。",
    "Create new design system": "新建设计系统",
    "Teach Claude your brand and product": "让 Claude 了解你的品牌和产品",
    "Published": "已发布",
    "Only you can view these settings.": "只有你可以查看这些设置。",
    "Use this prompt": "使用此提示词",
    "Globe loader": "地球加载器",
    "Prototype a loading indicator that shows the globe spinning with real country outlines, full monochrome, no text, 200×200 centered on off-white background. Add a whirl effect around it.": "制作一个加载指示器原型：地球以真实国家轮廓旋转，整体单色，无文字，200×200，居中放在米白色背景上，并在周围加入旋转效果。",
    "Iridescent card": "虹彩卡片",
    "Create a monochromatic playing card. Display it on the page with a rich perspective hover effect and glow. The bright areas should be iridescent; there should be a subtle noise texture and a hint of depth.": "创建一张单色扑克牌，并在页面上展示丰富的透视悬停效果和光晕。亮部应带有虹彩质感，同时加入细微噪点纹理和层次感。",
    "What's the doc about?": "这个文档是关于什么的？",
    "Talking it out works great — ramble, and the doc takes shape.": "随便说说也可以，内容会逐渐成形。",
    "Upload a PDF or notes": "上传 PDF 或笔记",
    "Drag to pin": "拖动以固定",
    "Menu": "菜单",
    "Mode": "模式",
    "Group by": "分组依据",
    "Filter": "筛选",
    "Get apps and extensions": "获取应用和扩展",
    "Connect Gmail": "连接 Gmail",
    "Connect Google Drive": "连接 Google Drive",
    "Connect Slack": "连接 Slack",
    "Connect Google Calendar": "连接 Google Calendar",
    "Connect Notion": "连接 Notion",
    "Connect Microsoft 365": "连接 Microsoft 365",
    "Connect Atlassian": "连接 Atlassian",
    "Connect Canva": "连接 Canva",
    "Add to favorites": "添加到收藏",
    "Duplicate": "复制",
    "Delete Project": "删除项目",
    "Files": "文件",
    "Attach file": "附加文件",
    "Reference another project": "引用另一个项目",
    "Connect GitHub": "连接 GitHub",
    "Link local code...": "链接本地代码...",
    "Upload .fig file": "上传 .fig 文件",
    "Learn how": "了解方法",
    "Skills": "技能",
    "Manage connectors": "管理连接器",
    "Start with context": "从上下文开始",
    "Designs grounded in real context turn out better.": "基于真实上下文的设计效果更好。",
    "Screenshot": "截图",
    "Codebase": "代码库",
    "Hi-fi design": "高保真设计",
    "Interactive prototype": "交互式原型",
    "What's the story?": "故事是什么？",
    "A storyboard, a script, or image assets set the direction.": "故事板、脚本或图片素材会决定方向。",
    "Drop a storyboard or images": "拖入故事板或图片",
    "Paste a script": "粘贴脚本",
    "Animated video": "动画视频",
    "What are we wireframing?": "我们要画什么线框图？",
    "Lo-fi moves fast — a screenshot or rough notes is plenty.": "低保真推进很快，一张截图或粗略笔记就够了。",
    "Add a screenshot": "添加截图",
    "Wireframe": "线框图",
    "Signed in as": "登录身份",
    "Organization": "组织",
    "Docs": "文档",
    "Tutorial": "教程",
    "Give feedback": "提交反馈",
    "Sign out": "退出登录",
    "just now": "刚刚",
    "Delete project?": "删除项目？",
    "Delete \"Untitled\"? This cannot be undone.": "删除“未命名”？此操作无法撤销。",
    "Add a design system": "添加设计系统",
    "Design systems teach Claude your brand. How would you like to start?": "设计系统会让 Claude 了解你的品牌。你想如何开始？",
    "teach Claude your brand. How would you like to start?": "会让 Claude 了解你的品牌。你想如何开始？",
    "Create here": "在这里创建",
    "Connect to Figma or GitHub, or upload slides and assets.": "连接 Figma 或 GitHub，或上传幻灯片和素材。",
    "Create using Claude Code": "使用 Claude Code 创建",
    "BEST FIDELITY": "最佳保真度",
    "Best fidelity if you have React components.": "如果你有 React 组件，效果最佳。",
    "None": "无",
    "New blank canvas": "新建空白画布",
    "Describe what you want to create…": "描述你想创建的内容...",
    "Chat": "聊天",
    "Cowork": "协作",
    "Code": "代码",
    "New task": "新建任务",
    "Projects": "项目",
    "Artifacts": "作品",
    "Artifact": "作品",
    "artifact": "作品",
    "Work": "作品",
    "工作": "作品",
    "New artifact": "新建作品",
    "New Artifact": "新建作品",
    "新神器": "新建作品",
    "Create chat Artifact": "新建聊天作品",
    "Create chat artifact": "新建聊天作品",
    "Create chat 作品": "新建聊天作品",
    "Create Cowork Artifact": "新建协作作品",
    "Create Cowork artifact": "新建协作作品",
    "Create Cowork 作品": "新建协作作品",
    "Search artifacts...": "搜索作品...",
    "搜索工作...": "搜索作品...",
    "搜索工件...": "搜索作品...",
    "Create your first Artifact": "创建你的第一个作品",
    "Create your first artifact": "创建你的第一个作品",
    "创建你的第一个Artifact": "创建你的第一个作品",
    "Create your first": "创建你的第一个",
    "No artifacts match this filter.": "没有符合此筛选条件的作品。",
    "No artifacts matching “{search}”": "没有匹配“{search}”的作品",
    "All artifacts": "全部作品",
    "Your artifacts will be listed here once you create one.": "创建作品后会显示在这里。",
    "Scheduled": "计划任务",
    "Scheduled tasks": "计划任务",
    "Dispatch": "Dispatch",
    "Customize": "自定义",
    "Settings": "设置",
    "Recents": "最近",
    "Starred": "已收藏",
    "Search": "搜索",
    "Search chats": "搜索聊天",
    "Search projects": "搜索项目",
    "What's new": "更新内容",
    "Give Claude context from your apps and services": "连接应用和服务，为 Claude 提供上下文",
    "View more": "查看更多",
    "2× more usage until July 5": "7月5日前可多用 2 倍",
    "Learn how to use Cowork safely.": "了解如何安全使用 Cowork。",
    "Act": "行动",
    "Labs": "实验",
    "Default": "默认",
    "Communications": "通信",
    "Default device": "默认设备",
    "Communications device": "通信设备",
    "Microphone": "麦克风",
    "Press and hold to record": "按住录音",
    "Release to send": "松开发送",
    "Release to cancel": "松开取消",
    "Ask before acting": "操作前询问",
    "Claude pauses so you can approve each action.": "Claude 会暂停，等你批准每一步操作。",
    "Act without asking": "无需询问直接执行",
    "Claude works without pausing for approval.": "Claude 会直接执行，不再暂停等待批准。",
    "Act without asking?": "无需询问直接执行？",
    "Act without asking is on.": "已开启无需询问直接执行。",
    "Claude works, uses connectors, and browses the web without pausing for approval.": "Claude 会直接工作、使用连接器并浏览网页，不再每一步都暂停等待确认。",
    "Claude will work and use your connectors without pausing for approval. This can put your data at risk.": "Claude 将直接工作并使用你的连接器，不再暂停等待批准。这可能带来数据风险。",
    "You can turn off individual connectors in the Add menu.": "你可以在添加菜单里单独关闭某个连接器。",
    "You can turn 关 individual connectors in the Add menu.": "你可以在添加菜单里单独关闭某个连接器。",
    "See safe use tips": "查看安全使用提示",
    "Don't show again": "不再显示",
    "BETA": "测试版",
    "Beta": "测试版",
    "beta": "测试版",
    "High risk": "高风险",
    "risk": "风险",
    "risk:": "风险：",
    "Claude can act anywhere on the internet, which could put your data at risk.": "Claude 可以在互联网上任意位置执行操作，可能会让你的数据面临风险。",
    "Claude can act anywhere on the internet, which": "Claude 可以在互联网上任意位置执行操作，",
    "could put your data at risk.": "可能会让你的数据面临风险。",
    "High risk: Claude can act anywhere on the internet, which could put your data at risk.": "高风险：Claude 可以在互联网上任意位置执行操作，可能会让你的数据面临风险。",
    "risk: Claude can act anywhere on the internet, which could put your data at risk.": "风险：Claude 可以在互联网上任意位置执行操作，可能会让你的数据面临风险。",
    "Connectors": "连接器",
    "No connectors are enabled for this conversation.": "没有为此会话启用连接器。",
    "Can browse and act on sites without pausing for approval": "可直接浏览网站并执行操作，无需等待批准",
    "Claude can browse and act on sites without pausing for approval.": "Claude 可以直接浏览网站并执行操作，无需等待批准。",
    "Yes, continue": "是的，继续",
    "Token total": "令牌总数",
    "Token 总数": "令牌总数",
    "The Little Prince": "《小王子》",
    "Animal Farm": "《动物农场》",
    "The Great Gatsby": "《了不起的盖茨比》",
    "The Hobbit": "《霍比特人》",
    "Pride and Prejudice": "《傲慢与偏见》",
    "Moby-Dick": "《白鲸》",
    "The Lord of the Rings": "《魔戒》",
    "War and Peace": "《战争与和平》",
    "Opus 4.8 (256k context)": "Opus 4.8（256k 上下文）",
    "Claude Fable 5 is currently unavailable.": "Claude Fable 5 当前不可用。",
    "Learn more": "了解更多",
    "This conversation could not be found.": "未找到这个对话。",
    "Send a message...": "发一条消息...",
    "Try: draft an email · summarize a doc · plan your week": "试试：写邮件、总结文档、规划本周",
    "What can I take off your plate?": "今天想让我帮你处理什么？",
    "What can I help you with?": "我能帮你做什么？",
    "How can Claude help you today?": "今天想让 Claude 帮你做什么？",
    "Ask Claude": "问 Claude",
    "Message Claude": "给 Claude 发消息",
    "Send": "发送",
    "Attach": "添加附件",
    "Add files": "添加文件",
    "Get started": "开始使用",
    "Continue": "继续",
    "Cancel": "取消",
    "Try again": "重试",
    "Go to home": "回到首页",
    "Claude will return soon": "Claude 很快回来",
    "Claude is currently experiencing a temporary service disruption.": "Claude 当前遇到临时服务中断。",
    "We’re working on it, please check back soon.": "我们正在处理，请稍后再试。",
    "We're working on it, please check back soon.": "我们正在处理，请稍后再试。",
    "Still not working? You can reach out to support with this error code:": "仍然无法使用？你可以带着这个错误码联系支持：",
    "support": "支持",
    "Create": "创建",
    "Delete": "删除",
    "Rename": "重命名",
    "Share": "分享",
    "Copy": "复制",
    "Open": "打开",
    "Close": "关闭",
    "Done": "完成",
    "Back": "返回",
    "Next": "下一步",
    "Retry": "重试",
    "Refresh": "刷新",
    "Upgrade": "升级",
    "Profile": "个人资料",
    "Appearance": "外观",
    "Language": "语言",
    "Notifications": "通知",
    "Privacy": "隐私",
    "Account": "账号",
    "Help": "帮助",
    "New chat": "新建聊天",
    "All chats": "所有聊天",
    "No chats yet.": "还没有聊天。",
    "No projects yet.": "还没有项目。",
    "Try Claude Code": "试试 Claude Code",
    "Set up Cowork": "设置 Cowork",
    "Duplicate project": "复制项目",
    "Duplicate Project": "复制项目",
    "Delete project": "删除项目",
    "Delete Project": "删除项目",
    "No assets in": "暂无素材",
    "Upload a .fig file": "上传 .fig 文件",
    "Drop .fig here": "将 .fig 拖到这里",
    "Parsed locally in your browser — never uploaded.": "只在你的浏览器本地解析，不会上传。",
    "get a .fig file": "获取 .fig 文件",
    "Add fonts, logos and assets": "添加字体、Logo 和素材",
    "Drag files here": "将文件拖到这里",
    "Any other notes?": "还有其他说明吗？",
    "Set up design system": "设置设计系统",
    "Nothing here yet.": "这里还没有内容。",
    "Continue generation": "继续生成",
    "Shader wallpapers": "着色器壁纸",
    "Organic loaders": "有机加载动画",
    "Text streaming": "文字流式动画",
    "App onboarding": "应用引导页",
    "Text particle effects": "文字粒子效果",
    "Globe loader": "地球加载器",
    "Iridescent card": "虹彩卡片",
    "Hover to preview": "悬停预览",
    "Describe what you want to create...": "描述你想创建的内容...",
    "Describe what you want to create…": "描述你想创建的内容...",
    "Wireframe": "线框图",
    "Hi-fi design": "高保真设计",
    "Interactive prototype": "交互式原型",
    "Start with context": "从上下文开始",
    "Designs grounded in real context turn out better.": "基于真实上下文的设计效果更好。",
    "What are we wireframing?": "要做哪类线框图？",
    "Lo-fi moves fast — a screenshot or rough notes is plenty.": "低保真推进很快，一张截图或粗略笔记就够了。",
    "Add a screenshot": "添加截图",
    "Paste notes": "粘贴笔记",
    "Screenshot": "截图",
    "Codebase": "代码库",
    "Create new design system": "创建新的设计系统",
    "Teach Claude your brand and product": "让 Claude 了解你的品牌和产品",
    "Published": "已发布",
    "Only you can view these settings.": "只有你可以查看这些设置。",
    "Create here": "在这里创建",
    "Create using Claude Code": "使用 Claude Code 创建",
    "Use Claude Code to upload your components": "使用 Claude Code 上传你的组件",
    "Your system already lives in code, so there's nothing to set up here. Open your design-system package in Claude Code and run /design-sync — it reads your tokens and React components directly.": "你的设计系统已经在代码中，因此这里无需额外设置。请在 Claude Code 中打开你的设计系统包并运行 /design-sync，它会直接读取你的 tokens 和 React 组件。",
    "Your system already lives in code, so there's nothing to set up here.": "你的设计系统已经在代码中，因此这里无需额外设置。",
    "Open your design-system package in Claude Code and run": "请在 Claude Code 中打开你的设计系统包并运行",
    "it reads your tokens and React components directly.": "它会直接读取你的 tokens 和 React 组件。",
    "Claude can create new design systems or update an existing system.": "Claude 可以创建新的设计系统，也可以更新现有设计系统。",
    "When it finishes, your system appears under 设计系统 for everyone in your org.": "完成后，你的系统会显示在“设计系统”下，组织中的所有人都可以使用。",
    "When it finishes, your system appears under": "完成后，你的系统会显示在",
    "for everyone in your org.": "下，组织中的所有人都可以使用。",
    "Don't have Claude Code?": "还没有 Claude Code？",
    "Install it": "安装它",
    "Best fidelity if you have React components.": "如果你有 React 组件，保真度最高。",
    "BEST FIDELITY": "最高保真度",
    "e.g. We use a warm, earthy color palette with rounded corners. Our brand voice is playful but professional...": "例如：我们使用温暖、自然的配色和圆角。品牌语气活泼但专业...",
    "Imagine you're creating a wallpaper for a futuristic operating system. We want it to feel interactive and fun to fidget with. Create five different interactive shader wallpapers that react to mouse position, and maybe clicks.": "想象你正在为一个未来感操作系统制作壁纸。希望它有互动感，也适合随手把玩。创建五种会响应鼠标位置，甚至点击的交互式着色器壁纸。",
    "Imagine you’re creating a wallpaper for a futuristic operating system. We want it to feel interactive and fun to fidget with. Create five different interactive shader wallpapers that react to mouse position, and maybe clicks.": "想象你正在为一个未来感操作系统制作壁纸。希望它有互动感，也适合随手把玩。创建五种会响应鼠标位置，甚至点击的交互式着色器壁纸。",
    "Prototype 20 simple, tasteful indeterminate loading indicators that fit in a 200×200 space, on a wrapping grid. All black and white, no text. All should have an organic, blobby feeling.": "制作 20 个简洁、有品味的不确定进度加载指示器原型，放在自动换行网格中的 200×200 区域内。全黑白、无文字，整体要有有机、柔软的形态感。",
    "On a responsive grid, animate 10 different text-streaming animations for a chat app; sample each one in a 300×300 cell; show a user question and stream a response below. Loop it. Monochrome.": "在响应式网格中，为聊天应用制作 10 种不同的文字流式动画；每种放在 300×300 单元格内展示；显示一个用户问题，并在下方流式输出回答。循环播放，单色风格。",
    "Create a simple iOS signup flow for a bikesharing app. Show screens on a canvas. Blue + orange modern color scheme.": "为共享单车应用创建一个简洁的 iOS 注册流程。在画布上展示多个界面，使用蓝色加橙色的现代配色。",
    "Create a very large editable text box, pre-filled with sample text.": "创建一个很大的可编辑文本框，并预填示例文字。",
    "No design system selected": "未选择设计系统",
    "Pick one on the left to give Claude a visual style to follow.": "从左侧选择一个设计系统，让 Claude 遵循对应的视觉风格。",
    "Cosmic scale animation": "宇宙尺度动画",
    "Create a sprite-based animation": "创建一个基于精灵图的动画",
    "gives fun facts about the distance and sizes of celestial bodies": "展示有关天体距离和大小的趣味知识",
    "Mix abstract animations using circles of various sizes as celestial bodies with text-based animation.": "用不同尺寸的圆形代表天体，将抽象动画和文字动画结合起来。",
    "Use a monochrome, helvetica palette.": "使用单色 Helvetica 风格。",
    "Calculator construction kit": "计算器构建套件",
    "Create a “Calculator construction kit”": "创建一个“计算器构建套件”",
    "Create a \"Calculator construction kit\"": "创建一个“计算器构建套件”",
    "a simple calculator UI with a LOT of tweaks": "一个简洁的计算器界面，带大量可调选项",
    "do not use the normal tweaks system; keep these tweaks onscreen at all times": "不要使用常规调节系统；这些调节项要始终显示在屏幕上",
    "Use a two-column layout.": "使用双栏布局。",
    "Provide a ton of visual + layout options.": "提供丰富的视觉和布局选项。",
    "No design system selected": "未选择设计系统",
    "Pick one on the left to give Claude a visual style to follow.": "从左侧选择一个设计系统，让 Claude 遵循对应的视觉风格。",
    "Cosmic scale animation": "宇宙尺度动画",
    "Create a sprite-based animation that gives fun facts about the distance and sizes of celestial bodies. Mix abstract animations using circles of various sizes as celestial bodies with text-based animation. Use a monochrome, helvetica palette.": "创建一个基于精灵图的动画，展示有关天体距离和大小的趣味知识。用不同尺寸的圆形代表天体，将抽象动画和文字动画结合起来。使用单色 Helvetica 风格。",
    "Calculator construction kit": "计算器构建套件",
    "Create a “Calculator construction kit” — a simple calculator UI with a LOT of tweaks (do not use the normal tweaks system; keep these tweaks onscreen at all times). Use a two-column layout. Provide a ton of visual + layout options.": "创建一个“计算器构建套件”：一个简洁的计算器界面，带大量可调选项（不要使用常规调节系统；这些调节项要始终显示在屏幕上）。使用双栏布局，并提供丰富的视觉和布局选项。",
    "Create a \"Calculator construction kit\" — a simple calculator UI with a LOT of tweaks (do not use the normal tweaks system; keep these tweaks onscreen at all times). Use a two-column layout. Provide a ton of visual + layout options.": "创建一个“计算器构建套件”：一个简洁的计算器界面，带大量可调选项（不要使用常规调节系统；这些调节项要始终显示在屏幕上）。使用双栏布局，并提供丰富的视觉和布局选项。",
}

PARTIAL_UI_REPLACEMENTS = {
    "Need changes? Ask Claude to edit the file instead of making a new one.": "需要修改？让 Claude 编辑这个文件，而不是新建一个。",
    "Duplicate project": "复制项目",
    "Duplicate Project": "复制项目",
    "Delete project": "删除项目",
    "Delete Project": "删除项目",
    "No assets in": "暂无素材",
    "No assets in ": "暂无素材：",
    "so anyone can create consistent designs and assets.": "，让任何人都能创建一致的设计和素材。",
    " so anyone can create consistent designs and assets.": "，让任何人都能创建一致的设计和素材。",
    "Upload a .fig file": "上传 .fig 文件",
    "Drop .fig here": "将 .fig 拖到这里",
    "Parsed locally in your browser — never uploaded.": "只在你的浏览器本地解析，不会上传。",
    "never uploaded.": "不会上传。",
    "get a .fig file": "获取 .fig 文件",
    "Add fonts, logos and assets": "添加字体、Logo 和素材",
    "Drag files here": "将文件拖到这里",
    "Any other notes?": "还有其他说明吗？",
    "Set up design system": "设置设计系统",
    "Nothing here yet.": "这里还没有内容。",
    "Continue generation": "继续生成",
    "Hover to preview": "悬停预览",
    "Describe what you want to create...": "描述你想创建的内容...",
    "Describe what you want to create…": "描述你想创建的内容...",
    "Wireframe": "线框图",
    "Hi-fi design": "高保真设计",
    "Interactive prototype": "交互式原型",
    "Start with context": "从上下文开始",
    "Designs grounded in real context turn out better.": "基于真实上下文的设计效果更好。",
    "What are we wireframing?": "要做哪类线框图？",
    "Lo-fi moves fast — a screenshot or rough notes is plenty.": "低保真推进很快，一张截图或粗略笔记就够了。",
    "Add a screenshot": "添加截图",
    "Paste notes": "粘贴笔记",
    "Screenshot": "截图",
    "Codebase": "代码库",
    "Shader wallpapers": "着色器壁纸",
    "Organic loaders": "有机加载动画",
    "Text streaming": "文字流式动画",
    "App onboarding": "应用引导页",
    "Text particle effects": "文字粒子效果",
    "Globe loader": "地球加载器",
    "Iridescent card": "虹彩卡片",
    "Create new design system": "创建新的设计系统",
    "Teach Claude your brand and product": "让 Claude 了解你的品牌和产品",
    "Only you can view these settings.": "只有你可以查看这些设置。",
    "Create here": "在这里创建",
    "Create using Claude Code": "使用 Claude Code 创建",
    "Use Claude Code to upload your components": "使用 Claude Code 上传你的组件",
    "Your system already lives in code": "你的设计系统已经在代码中",
    "so there's nothing to set up here.": "因此这里无需额外设置。",
    "so there’s nothing to set up here.": "因此这里无需额外设置。",
    "Open your design-system package in Claude Code and run": "请在 Claude Code 中打开你的设计系统包并运行",
    "it reads your tokens and React components directly.": "它会直接读取你的 tokens 和 React 组件。",
    "it reads your tokens and React components directly": "它会直接读取你的 tokens 和 React 组件",
    "Claude can create new design systems or update an existing system.": "Claude 可以创建新的设计系统，也可以更新现有设计系统。",
    "When it finishes, your system appears under": "完成后，你的系统会显示在",
    "for everyone in your org.": "下，组织中的所有人都可以使用。",
    "Don't have Claude Code?": "还没有 Claude Code？",
    "Install it": "安装它",
    "Best fidelity if you have React components.": "如果你有 React 组件，保真度最高。",
    "BEST FIDELITY": "最高保真度",
    "Claude Design": "Claude 设计",
    "Research preview": "研究预览",
    "Your designs": "你的设计",
    "Design systems": "设计系统",
    "Search designs": "搜索设计",
    "Make something new": "新建设计",
    "Design system:": "设计系统：",
    "Start anywhere": "从任意位置开始",
    "Add a file and design": "添加文件并创建设计",
    "Decks & reviews": "演示稿与评审",
    "Clickable & interactive": "可点击、可交互",
    "Product wireframe": "产品线框图",
    "Lo-fi screens & flows": "低保真界面与流程",
    "Resumes, PDFs, etc": "简历、PDF 等",
    "Last viewed": "上次查看",
    "Design System": "设计系统",
    "Continue to generation": "继续生成",
    "Set up your design system": "设置你的设计系统",
    "Tell us about your company": "介绍你的公司",
    "Company name and blurb": "公司名称和简介",
    "or name of design system": "或设计系统名称",
    "Provide examples of your design system and products": "提供你的设计系统和产品示例",
    "all optional": "全部可选",
    "What works best": "最有效的是",
    "Link code from GitHub": "关联 GitHub 代码",
    "Link code from your computer": "关联本机代码",
    "Drag a folder here": "拖入文件夹",
    "This doesn’t upload the whole codebase": "这不会上传整个代码库",
    "This doesn't upload the whole codebase": "这不会上传整个代码库",
    "What's the presentation about?": "这个演示文稿是关于什么的？",
    "Upload a doc, share your notes": "上传文档、分享笔记",
    "Upload a doc": "上传文档",
    "Paste your notes": "粘贴笔记",
    "Existing deck": "已有演示稿",
    "Deck options": "演示稿选项",
    "Optimize for Google Slides": "针对 Google Slides 优化",
    "Only use Google Fonts": "仅使用 Google 字体",
    "Add speaker notes": "添加演讲者备注",
    "Include talking points": "加入讲稿要点",
    "Design Files": "设计文件",
    "New sketch": "新草图",
    "Creations will appear here": "生成内容会显示在这里",
    "Start with a blank canvas": "从空白画布开始",
    "DROP FILES HERE": "拖放文件到这里",
    "Add something with the tools above": "使用上方工具添加内容",
    "paste, or drop an image onto the canvas.": "或粘贴/拖入图片到画布。",
    "Images, docs, references": "图片、文档、参考资料",
    "Describe what you want to create": "描述你想创建的内容",
    "Make a deck": "制作演示稿",
    "Make a doc": "制作文档",
    "Choose design systems": "选择设计系统",
    "Set up a design system": "设置设计系统",
    "Import brand, code, and assets": "导入品牌、代码和素材",
    "Drag selected design systems": "拖动已选择的设计系统",
    "the one at the top takes precedence": "最上方的优先",
    "Browse Design System": "浏览设计系统",
    "Claude reads the whole design system on its own.": "Claude 会自行读取整个设计系统。",
    "No assets in Design System": "设计系统中没有素材",
    "No assets in 设计系统": "设计系统中没有素材",
    "This design system hasn't been set up yet": "这个设计系统尚未设置",
    "finish onboarding to add code, Figma files, and brand assets": "请完成引导流程以添加代码、Figma 文件和品牌素材",
    "Create new design system": "新建设计系统",
    "Teach Claude your brand and product": "让 Claude 了解你的品牌和产品",
    "Published": "已发布",
    "Only you can view these settings.": "只有你可以查看这些设置。",
    "Use this prompt": "使用此提示词",
    "Globe loader": "地球加载器",
    "Prototype a loading indicator": "制作一个加载指示器原型",
    "Iridescent card": "虹彩卡片",
    "Create a monochromatic playing card": "创建一张单色扑克牌",
    "What's the doc about?": "这个文档是关于什么的？",
    "Talking it out works great": "随便说说也可以",
    "Upload a PDF or notes": "上传 PDF 或笔记",
    "Figma links": "Figma 链接",
    "Claude will use them as context": "Claude 会将它们作为上下文",
    "Drag to pin": "拖动以固定",
    "Click collapse": "点击折叠",
    "Group by": "分组依据",
    "Get apps and extensions": "获取应用和扩展",
    "Connect Gmail": "连接 Gmail",
    "Connect Google Drive": "连接 Google Drive",
    "Connect Slack": "连接 Slack",
    "Connect Google Calendar": "连接 Google Calendar",
    "Connect Notion": "连接 Notion",
    "Connect Microsoft 365": "连接 Microsoft 365",
    "Connect Atlassian": "连接 Atlassian",
    "Connect Canva": "连接 Canva",
    "Add to favorites": "添加到收藏",
    "Delete Project": "删除项目",
    "Attach file": "附加文件",
    "Reference another project": "引用另一个项目",
    "Connect GitHub": "连接 GitHub",
    "Link local code": "链接本地代码",
    "Upload .fig file": "上传 .fig 文件",
    "Learn how": "了解方法",
    "Manage connectors": "管理连接器",
    "Start with context": "从上下文开始",
    "Designs grounded in real context turn out better.": "基于真实上下文的设计效果更好。",
    "Hi-fi design": "高保真设计",
    "Interactive prototype": "交互式原型",
    "What's the story?": "故事是什么？",
    "A storyboard, a script, or image assets set the direction.": "故事板、脚本或图片素材会决定方向。",
    "Drop a storyboard or images": "拖入故事板或图片",
    "Paste a script": "粘贴脚本",
    "Animated video": "动画视频",
    "What are we wireframing?": "我们要画什么线框图？",
    "Lo-fi moves fast": "低保真推进很快",
    "a screenshot or rough notes is plenty": "一张截图或粗略笔记就够了",
    "Add a screenshot": "添加截图",
    "Wireframe": "线框图",
    "Signed in as": "登录身份",
    "Organization": "组织",
    "'s Organization": " 的组织",
    "Give feedback": "提交反馈",
    "Sign out": "退出登录",
    "just now": "刚刚",
    "Delete project?": "删除项目？",
    "This cannot be undone.": "此操作无法撤销。",
    "Add a design system": "添加设计系统",
    "teach Claude your brand. How would you like to start?": "会让 Claude 了解你的品牌。你想如何开始？",
    "Create here": "在这里创建",
    "Connect to Figma or GitHub": "连接 Figma 或 GitHub",
    "upload slides and assets": "上传幻灯片和素材",
    "Create using Claude Code": "使用 Claude Code 创建",
    "BEST FIDELITY": "最佳保真度",
    "Best fidelity if you have React components.": "如果你有 React 组件，效果最佳。",
    "New blank canvas": "新建空白画布",
    "Describe what you want to create…": "描述你想创建的内容...",
    "What's new": "更新内容",
    "Artifact": "作品",
    "Artifacts": "作品",
    "创建你的第一个Artifact": "创建你的第一个作品",
    "Search artifacts": "搜索作品",
    "搜索工作": "搜索作品",
    "搜索工件": "搜索作品",
    "No artifacts match this filter.": "没有符合此筛选条件的作品。",
    "No artifacts matching": "没有匹配的作品",
    "All artifacts": "全部作品",
    "2× more usage until July 5": "7月5日前可多用 2 倍",
    "Give Claude context from your apps and services": "连接应用和服务，为 Claude 提供上下文",
    " Labs": " 实验",
    "Default -": "默认 -",
    "Communications -": "通信 -",
    "Default device": "默认设备",
    "Communications device": "通信设备",
    "Ask before acting": "操作前询问",
    "Act without asking": "无需询问直接执行",
    "Token 总数": "令牌总数",
    " token ": " 令牌 ",
    "The Little Prince": "《小王子》",
    "Animal Farm": "《动物农场》",
    "The Great Gatsby": "《了不起的盖茨比》",
    "The Hobbit": "《霍比特人》",
    "Pride and Prejudice": "《傲慢与偏见》",
    "Moby-Dick": "《白鲸》",
    "The Lord of the Rings": "《魔戒》",
    "War and Peace": "《战争与和平》",
    "(256k context)": "（256k 上下文）",
    "Act without asking is on.": "已开启无需询问直接执行。",
    "Claude works, uses connectors, and browses the web without pausing for approval.": "Claude 会直接工作、使用连接器并浏览网页，不再每一步都暂停等待确认。",
    "Claude will work and use your connectors without pausing for approval. This can put your data at risk.": "Claude 将直接工作并使用你的连接器，不再暂停等待批准。这可能带来数据风险。",
    "Claude works without pausing for approval.": "Claude 会直接执行，不再暂停等待批准。",
    "Claude pauses so you can approve each action.": "Claude 会暂停，等你批准每一步操作。",
    "Claude can browse and act on sites without pausing for approval.": "Claude 可以直接浏览网站并执行操作，无需等待批准。",
    "You can turn off individual connectors in the Add menu.": "你可以在添加菜单里单独关闭某个连接器。",
    "You can turn 关 individual connectors in the Add menu.": "你可以在添加菜单里单独关闭某个连接器。",
    "See safe use tips": "查看安全使用提示",
    "High risk": "高风险",
    "risk:": "风险：",
    "Claude can act anywhere on the internet, which could put your data at risk.": "Claude 可以在互联网上任意位置执行操作，可能会让你的数据面临风险。",
    "Claude can act anywhere on the internet, which": "Claude 可以在互联网上任意位置执行操作，",
    "could put your data at risk.": "可能会让你的数据面临风险。",
    "High risk: Claude can act anywhere on the internet, which could put your data at risk.": "高风险：Claude 可以在互联网上任意位置执行操作，可能会让你的数据面临风险。",
    "risk: Claude can act anywhere on the internet, which could put your data at risk.": "风险：Claude 可以在互联网上任意位置执行操作，可能会让你的数据面临风险。",
}


def find_claude_resource_dir() -> Path | None:
    root = Path(r"C:\Program Files\WindowsApps")
    matches = sorted(
        root.glob(r"Claude_*__pzs8sxrjxfjjc\app\resources\ion-dist"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    return matches[0] if matches else None


CLAUDE_RESOURCE_DIR = find_claude_resource_dir()


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def normalize_artifact_terms(value: str) -> str:
    if value.strip() == "工作":
        return value.replace("工作", "作品", 1)
    value = value.replace("Create chat 作品", "新建聊天作品")
    value = value.replace("Create Cowork 作品", "新建协作作品")
    value = value.replace("Create chat Artifact", "新建聊天作品")
    value = value.replace("Create Cowork Artifact", "新建协作作品")
    value = value.replace("Create chat artifact", "新建聊天作品")
    value = value.replace("Create Cowork artifact", "新建协作作品")
    value = value.replace("实时 Artifacts", "实时作品")
    value = value.replace("实时 Artifact", "实时作品")
    value = value.replace("新神器", "新建作品")
    value = value.replace("神器", "作品")
    value = re.sub(r"(?<![-_/])\bArtifacts\b(?![-_/])", "作品", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<![-_/])\bArtifact\b(?![-_/])", "作品", value, flags=re.IGNORECASE)
    return value


def normalize_i18n_map(data: dict[str, str]) -> dict[str, str]:
    return {key: normalize_artifact_terms(value) for key, value in data.items() if isinstance(value, str)}


def merged_frontend_i18n() -> dict[str, str]:
    local = (CLAUDE_RESOURCE_DIR / "i18n" / "zh-CN.json") if CLAUDE_RESOURCE_DIR else Path()
    base = load_json(local, {})
    if not base:
        base = load_json(JYY_DIR / "frontend-zh-CN.json", {})

    javaht = load_json(JAVAHT_DIR / "frontend-zh-CN.json", {})
    if isinstance(base, dict) and isinstance(javaht, dict):
        for key, value in javaht.items():
            if not isinstance(value, str):
                continue
            current = base.get(key)
            if not isinstance(current, str) or (has_cjk(value) and not has_cjk(current)):
                base[key] = value

    if not isinstance(base, dict):
        base = {}
    base.update(MANUAL_I18N_FIXES)
    return normalize_i18n_map(base)


def merged_dynamic_i18n() -> dict[str, str]:
    paths = [
        (CLAUDE_RESOURCE_DIR / "i18n" / "statsig" / "zh-CN.json") if CLAUDE_RESOURCE_DIR else Path(),
        JYY_DIR / "statsig-zh-CN.json",
        JAVAHT_DIR / "statsig-zh-CN.json",
    ]
    merged: dict[str, str] = {}
    for path in paths:
        data = load_json(path, {})
        if isinstance(data, dict):
            merged.update({k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)})
    return normalize_i18n_map(merged)


def iter_simple_hardcoded_pairs() -> Iterable[tuple[str, str]]:
    data = load_json(JAVAHT_DIR / "frontend-hardcoded-zh-CN.json", [])
    if not isinstance(data, list):
        return
    for item in data:
        if not (isinstance(item, list) and len(item) == 2):
            continue
        source, target = item
        if not (isinstance(source, str) and isinstance(target, str)):
            continue
        source = source.strip()
        target = target.strip()
        if source.startswith('"') and source.endswith('"') and target.startswith('"') and target.endswith('"'):
            source = source[1:-1]
            target = target[1:-1]
        if (
            source
            and target
            and len(source) <= 140
            and len(target) <= 180
            and ":" not in source
            and "{" not in source
            and "`" not in source
            and has_cjk(target)
        ):
            yield source, target


def ui_replacement_pairs() -> list[tuple[str, str]]:
    pairs: dict[str, str] = {}
    for source, target in iter_simple_hardcoded_pairs() or []:
        pairs[source] = target
    pairs.update(MANUAL_UI_REPLACEMENTS)
    return sorted(pairs.items(), key=lambda pair: (-len(pair[0]), pair[0]))


def partial_replacement_pairs() -> list[tuple[str, str]]:
    return sorted(PARTIAL_UI_REPLACEMENTS.items(), key=lambda pair: (-len(pair[0]), pair[0]))


def runtime_js() -> bytes:
    pairs = ui_replacement_pairs()
    js_pairs = json.dumps(pairs, ensure_ascii=False, separators=(",", ":"))
    js_partial_pairs = json.dumps(partial_replacement_pairs(), ensure_ascii=False, separators=(",", ":"))
    script = f"""
;(() => {{
  const marker = "__{INDEX_PATCH_MARKER}__";
  if (window[marker]) return;
  window[marker] = true;
  try {{
    localStorage.setItem("spa:locale", "zh-CN");
  }} catch {{}}
  const serverLocale = "en-US";
  function rewriteLocaleString(value) {{
    return typeof value === "string" ? value.replaceAll("zh-CN", serverLocale) : value;
  }}
  function rewriteLocaleBody(body) {{
    if (typeof body === "string" && body.includes("zh-CN")) {{
      return rewriteLocaleString(body);
    }}
    if (body instanceof FormData) {{
      try {{
        if (body.get("locale") === "zh-CN") body.set("locale", serverLocale);
      }} catch {{}}
    }}
    return body;
  }}
  try {{
    const originalFetch = window.fetch?.bind(window);
    if (originalFetch && !window.__ClaudeZhFetchPatched) {{
      window.__ClaudeZhFetchPatched = true;
      window.fetch = (input, init) => {{
        let patchedInput = input;
        let patchedInit = init ? {{ ...init }} : init;
        if (typeof patchedInput === "string") patchedInput = rewriteLocaleString(patchedInput);
        else if (patchedInput instanceof URL) patchedInput = new URL(rewriteLocaleString(patchedInput.toString()));
        if (patchedInit?.body) patchedInit.body = rewriteLocaleBody(patchedInit.body);
        return originalFetch(patchedInput, patchedInit);
      }};
    }}
    const originalOpen = XMLHttpRequest.prototype.open;
    if (originalOpen && !XMLHttpRequest.prototype.__ClaudeZhOpenPatched) {{
      XMLHttpRequest.prototype.__ClaudeZhOpenPatched = true;
      XMLHttpRequest.prototype.open = function(method, url, ...rest) {{
        return originalOpen.call(this, method, rewriteLocaleString(url), ...rest);
      }};
    }}
    const originalSend = XMLHttpRequest.prototype.send;
    if (originalSend && !XMLHttpRequest.prototype.__ClaudeZhSendPatched) {{
      XMLHttpRequest.prototype.__ClaudeZhSendPatched = true;
      XMLHttpRequest.prototype.send = function(body) {{
        return originalSend.call(this, rewriteLocaleBody(body));
      }};
    }}
  }} catch {{}}
  const pairs = {js_pairs};
  const map = new Map(pairs);
  const partialPairs = {js_partial_pairs};
  const knownSources = pairs.map(([source]) => source).filter((source) => source && source.length <= 80);
  const blocked = "SCRIPT,STYLE,TEXTAREA,INPUT,PRE,CODE";
  const attrs = [
    "placeholder",
    "title",
    "aria-label",
    "aria-description",
    "aria-valuetext",
    "data-placeholder",
    "data-title",
    "data-tooltip",
    "data-tooltip-content",
    "alt"
  ];
  const safeFixedUiTexts = new Set([
    "DROP FILES HERE",
    "New blank canvas",
    "New sketch",
    "Paste",
    "Edit",
    "Discard",
    "Save",
    "Reload",
    "Present",
    "Mark up",
    "Comments",
    "Simple",
    "Pro",
    "Add something with the tools above (R · F · O · T), paste, or drop an image onto the canvas."
  ]);
  let changedCount = 0;
  let reportCount = 0;
  let lastReport = "";
  const observedRoots = new WeakSet();
  function report(stage) {{
    try {{
      const text = (document.body?.innerText || "").slice(0, 200000);
      const found = [];
      for (const source of knownSources) {{
        if (text.includes(source)) {{
          found.push(source);
          if (found.length >= 30) break;
        }}
      }}
      const untranslated = [];
      const seenUntranslated = new Set();
      function addUntranslated(value) {{
        if (!value || typeof value !== "string") return;
        const item = value.replace(/\\s+/g, " ").trim();
        if (!item || item.length < 3 || item.length > 180) return;
        if (!/[A-Za-z]/.test(item)) return;
        if (/^[A-Za-z]:/.test(item) || /^https?:\\/\\//i.test(item)) return;
        if (map.has(item)) return;
        if (seenUntranslated.has(item)) return;
        seenUntranslated.add(item);
        untranslated.push(item);
      }}
      for (const line of text.split(/\\n+/)) addUntranslated(line);
      try {{
        document.querySelectorAll("[placeholder],[title],[aria-label],[data-placeholder]").forEach((el) => {{
          for (const attr of attrs) addUntranslated(el.getAttribute(attr));
        }});
      }} catch {{}}
      const sample = untranslated.slice(0, 80).join("|");
      const signature = stage + "|" + changedCount + "|" + found.join("|") + "|" + sample;
      if (signature === lastReport && reportCount > 12) return;
      lastReport = signature;
      reportCount++;
      fetch(`https://assets-proxy.anthropic.com/claude-zh-cn/report?stage=${{encodeURIComponent(stage)}}&changed=${{changedCount}}&found=${{encodeURIComponent(found.join("|"))}}&untranslated=${{encodeURIComponent(sample)}}`, {{ cache: "no-store", mode: "no-cors" }}).catch(() => {{}});
    }} catch {{}}
  }}
  function translateText(value) {{
    if (!value) return value;
    const trimmed = value.trim();
    const translated = map.get(trimmed);
    if (!translated || translated === trimmed) return value;
    const start = value.match(/^\\s*/)?.[0] || "";
    const end = value.match(/\\s*$/)?.[0] || "";
    return start + translated + end;
  }}
  function translateDynamicValue(value) {{
    if (!value || typeof value !== "string") return value;
    const normalized = value.replace(/[\\u200b-\\u200f\\ufeff]/g, "").trim();
    if (normalized === "工作") {{
      const start = value.match(/^\\s*/)?.[0] || "";
      const end = value.match(/\\s*$/)?.[0] || "";
      return start + "作品" + end;
    }}
    let next = value;
    next = next.replace(/Create chat\\s+作品/gi, "新建聊天作品");
    next = next.replace(/Create Cowork\\s+作品/gi, "新建协作作品");
    next = next.replace(/Create chat\\s+Artifacts?/gi, "新建聊天作品");
    next = next.replace(/Create Cowork\\s+Artifacts?/gi, "新建协作作品");
    next = next.replace(/实时\\s+Artifacts?/gi, "实时作品");
    next = next.replace(/新神器/g, "新建作品");
    next = next.replace(/神器/g, "作品");
    next = next.replace(/(?<![-_/])\\bArtifacts\\b(?![-_/])/gi, "作品");
    next = next.replace(/(?<![-_/])\\bArtifact\\b(?![-_/])/gi, "作品");
    next = next.replace(/\\b(\\d[\\d.,]*[kKmM]?)\\s+in\\s+·\\s+(\\d[\\d.,]*[kKmM]?)\\s+out\\b/g, "$1 输入 · $2 输出");
    next = next.replace(/\\bjust now\\b/gi, "刚刚");
    next = next.replace(/\\b(\\d+)\\s*m(?:in)?\\s+ago\\b/gi, "$1 分钟前");
    next = next.replace(/\\b(\\d+)\\s*h(?:our)?s?\\s+ago\\b/gi, "$1 小时前");
    next = next.replace(/\\b(\\d+)\\s*d(?:ay)?s?\\s+ago\\b/gi, "$1 天前");
    const monthMap = {{Jan:"1月",Feb:"2月",Mar:"3月",Apr:"4月",May:"5月",Jun:"6月",Jul:"7月",Aug:"8月",Sep:"9月",Oct:"10月",Nov:"11月",Dec:"12月"}};
    next = next.replace(/\\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\\s+(\\d{{1,2}})\\b/g, (_, mon, day) => monthMap[mon] + day + "日");
    return next;
  }}
  function translateValue(value) {{
    const exact = translateText(value);
    if (exact !== value) return exact;
    if (!value || typeof value !== "string") return value;
    let next = translateDynamicValue(value);
    if (next !== value) return next;
    for (const [source, target] of partialPairs) {{
      if (next.includes(source)) next = next.split(source).join(target);
    }}
    return next;
  }}
  function allowed(node) {{
    const parent = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    if (!parent || parent.closest(blocked)) return false;
    const editable = parent.closest("[contenteditable='true']");
    if (!editable) return true;
    return !!parent.closest("button,[role='button'],[aria-label],[data-testid]");
  }}
  function isEditablePlaceholderNode(node) {{
    const parent = node?.parentElement;
    if (!parent?.closest?.("[contenteditable='true']")) return false;
    const text = (node.nodeValue || "").trim();
    return text === "Describe what you want to create..." ||
      text === "Describe what you want to create…" ||
      text === "Write a message..." ||
      text === "Send a message...";
  }}
  function isSafeEditablePlaceholderValue(value) {{
    const text = (value || "").trim();
    return text === "Describe what you want to create..." ||
      text === "Describe what you want to create…" ||
      text === "Write a message..." ||
      text === "Send a message...";
  }}
  function isSafeFixedUiValue(value) {{
    const text = (value || "").trim();
    return isSafeEditablePlaceholderValue(text) || safeFixedUiTexts.has(text);
  }}
  function patchFormControlValue(el) {{
    if (!el?.matches?.("input,textarea")) return;
    const value = el.value;
    if (isSafeFixedUiValue(value)) {{
      const translated = translateValue(value);
      if (translated && translated !== value) {{
        el.value = translated;
        el.defaultValue = translated;
        changedCount++;
      }}
    }}
  }}
  function patchElement(el) {{
    const hasSafeEditablePlaceholder = el?.closest?.("[contenteditable='true']") &&
      attrs.some((attr) => isSafeFixedUiValue(el.getAttribute?.(attr)));
    const attrAllowed = el?.matches?.("input,textarea")
      ? !el.closest("SCRIPT,STYLE,PRE,CODE")
      : allowed(el) || hasSafeEditablePlaceholder;
    if (!attrAllowed) return;
    for (const attr of attrs) {{
      const value = el.getAttribute?.(attr);
      const translated = translateValue(value);
      if (translated && translated !== value) {{
        el.setAttribute(attr, translated);
        changedCount++;
      }}
    }}
    patchFormControlValue(el);
    if (el.shadowRoot) {{
      observeRoot(el.shadowRoot);
      walk(el.shadowRoot);
    }}
    if (el.tagName === "IFRAME") {{
      try {{
        const doc = el.contentDocument;
        if (doc) {{
          observeRoot(doc.documentElement);
          walk(doc);
        }}
      }} catch {{}}
    }}
  }}
  function patchTextNode(node) {{
    if (!allowed(node) && !isEditablePlaceholderNode(node) && !isSafeFixedUiValue(node.nodeValue)) return;
    const translated = translateValue(node.nodeValue);
    if (translated !== node.nodeValue) {{
      node.nodeValue = translated;
      changedCount++;
    }}
  }}
  function walk(root) {{
    if (!root || !document.documentElement) return;
    if (root.nodeType === Node.TEXT_NODE) {{
      patchTextNode(root);
      return;
    }}
    if (
      root.nodeType !== Node.ELEMENT_NODE &&
      root.nodeType !== Node.DOCUMENT_NODE &&
      root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE
    ) return;
    if (root.nodeType === Node.ELEMENT_NODE) patchElement(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {{
      if (node.nodeType === Node.TEXT_NODE) patchTextNode(node);
      else patchElement(node);
    }}
  }}
  function observeRoot(root) {{
    if (!root || observedRoots.has(root)) return;
    observedRoots.add(root);
    try {{
      new MutationObserver((mutations) => {{
        for (const mutation of mutations) {{
          if (mutation.type === "characterData") patchTextNode(mutation.target);
          for (const node of mutation.addedNodes) schedule(node);
          if (mutation.type === "attributes") patchElement(mutation.target);
        }}
      }}).observe(root, {{
        childList: true,
        subtree: true,
        characterData: true,
        attributes: true,
        attributeFilter: attrs
      }});
    }} catch {{}}
  }}
  let pending = false;
  function schedule(root = document.body) {{
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {{
      pending = false;
      walk(root || document.body);
      if (root !== document.body) walk(document.body);
      report("scan");
    }});
  }}
  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", () => schedule(document.body), {{ once: true }});
  }} else {{
    schedule(document.body);
  }}
  observeRoot(document.documentElement);
  report("load");
  ["click", "pointerdown", "pointerup", "focusin", "keydown"].forEach((eventName) => {{
    document.addEventListener(eventName, () => setTimeout(() => schedule(document.body), 0), true);
  }});
  setInterval(() => schedule(document.body), 800);
}})();
""".strip()
    return script.encode("utf-8")


def patch_index_js(text: str) -> str:
    text = text.replace(
        'const U2={"en-US":"en","de-DE":"de","fr-FR":"fr","ko-KR":"ko","ja-JP":"ja","es-419":"es","es-ES":"es","it-IT":"it","hi-IN":"en","pt-BR":"pt_BR","id-ID":"id"};',
        'const U2={"en-US":"en","de-DE":"de","fr-FR":"fr","ko-KR":"ko","ja-JP":"ja","es-419":"es","es-ES":"es","it-IT":"it","hi-IN":"en","pt-BR":"pt_BR","id-ID":"id","zh-CN":"zh"};',
    )
    text = text.replace(
        'const DDt="spa:locale",PDt=dS([(()=>{try{return localStorage.getItem(DDt)}catch{return null}})(),...navigator.languages]);',
        'const DDt="spa:locale";try{localStorage.setItem(DDt,"zh-CN")}catch{}const PDt=dS(["zh-CN",(()=>{try{return localStorage.getItem(DDt)}catch{return null}})(),...navigator.languages]);',
    )
    text = text.replace(
        "queryFn:()=>s.apiClient.fetchExperiences(n,e,t)",
        'queryFn:()=>s.apiClient.fetchExperiences(n,e,"zh-CN"===t?"en-US":t)',
    )
    text = text.replace(
        "fetch(`/i18n/${e}.json`)",
        "fetch(`https://assets-proxy.anthropic.com/claude-zh-cn/i18n/${e}.json`)",
    )
    text = text.replace(
        "fetch(`/i18n/dynamic/${e}.json`)",
        "fetch(`https://assets-proxy.anthropic.com/claude-zh-cn/i18n/dynamic/${e}.json`)",
    )
    text = text.replace(
        "fetch(`/i18n/${e}.overrides.json`)",
        "fetch(`https://assets-proxy.anthropic.com/claude-zh-cn/i18n/${e}.overrides.json`)",
    )
    if INDEX_PATCH_MARKER not in text:
        text += (
            "\n;(()=>{try{const s=document.createElement('script');"
            "s.src='https://assets-proxy.anthropic.com/claude-zh-cn/runtime.js';"
            "s.defer=true;document.head.appendChild(s)}catch(e){}})();"
        )
    return text


def patch_cec_js(text: str) -> str:
    return text.replace(
        "locale:GK.includes(e.locale)?e.locale:HK",
        'locale:"zh-CN"===e.locale?HK:GK.includes(e.locale)?e.locale:HK',
    ).replace(
        "locale:o.locale,",
        'locale:"zh-CN"===o.locale?HK:o.locale,',
    )


def maybe_patch_asset(path: Path, body: bytes) -> bytes:
    name = path.name
    if name.startswith("index-") and name.endswith(".js"):
        return patch_index_js(body.decode("utf-8", errors="replace")).encode("utf-8")
    if name.startswith("cec18ad9a-") and name.endswith(".js"):
        return patch_cec_js(body.decode("utf-8", errors="replace")).encode("utf-8")
    return body


def inject_runtime_into_html(text: str) -> str:
    if INDEX_PATCH_MARKER in text:
        return text
    snippet = (
        f'<script data-codex="{INDEX_PATCH_MARKER}" '
        f'src="https://{HOST}/claude-zh-cn/runtime.js" defer></script>'
    )
    lower = text.lower()
    for tag in ("</head>", "</body>"):
        idx = lower.find(tag)
        if idx >= 0:
            return text[:idx] + snippet + text[idx:]
    return text + snippet


def maybe_patch_upstream_response(host: str, path: str, body: bytes, content_type_header: str | None) -> bytes:
    content_type_header = content_type_header or ""
    if "text/html" in content_type_header:
        return inject_runtime_into_html(body.decode("utf-8", errors="replace")).encode("utf-8")
    if "javascript" in content_type_header or path.endswith(".js"):
        patched = body
        name = Path(urlparse(path).path).name
        if name.startswith("index-"):
            patched = patch_index_js(body.decode("utf-8", errors="replace")).encode("utf-8")
        elif name.startswith("cec18ad9a-"):
            patched = patch_cec_js(body.decode("utf-8", errors="replace")).encode("utf-8")
        return patched
    return body


def content_type(path: str) -> str:
    if path.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if path.endswith(".json"):
        return "application/json; charset=utf-8"
    if path.endswith(".css"):
        return "text/css; charset=utf-8"
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


class FixedIPHTTPSConnection(HTTPSConnection):
    def __init__(self, host: str, upstream_ip: str, *args, **kwargs):
        super().__init__(host, *args, **kwargs)
        self.upstream_ip = upstream_ip

    def connect(self) -> None:
        sock = socket.create_connection((self.upstream_ip, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class ClaudeZhHandler(BaseHTTPRequestHandler):
    server_version = "ClaudeZhProxy/1.0"

    def log_message(self, fmt: str, *args) -> None:
        log = ROOT / "proxy.log"
        try:
            with log.open("a", encoding="utf-8") as fh:
                fh.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))
        except Exception:
            pass

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "https://claude.ai")
        self.send_header("Access-Control-Allow-Methods", "GET,HEAD,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Vary", "Origin")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_HEAD(self) -> None:
        self.handle_request(send_body=False)

    def do_GET(self) -> None:
        self.handle_request(send_body=True)

    def do_POST(self) -> None:
        self.handle_request(send_body=True)

    def do_PUT(self) -> None:
        self.handle_request(send_body=True)

    def do_PATCH(self) -> None:
        self.handle_request(send_body=True)

    def do_DELETE(self) -> None:
        self.handle_request(send_body=True)

    def send_bytes(self, body: bytes, path: str, status: int = 200, send_body: bool = True) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type(path))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def handle_request(self, send_body: bool) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            body = self.local_response(path)
            if body is not None:
                self.send_bytes(body, path, send_body=send_body)
                return
            self.proxy_upstream(send_body=send_body)
        except Exception as exc:
            self.log_message("request failed for %s: %s", path, exc)
            message = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_bytes(message, "error.json", status=502, send_body=send_body)

    def local_response(self, path: str) -> bytes | None:
        if path == "/claude-zh-cn/health":
            return b'{"ok":true}'
        if path == "/claude-zh-cn/report":
            parsed = urlparse(self.path)
            self.log_message("runtime-report %s", parsed.query[:5000])
            return b'{"ok":true}'
        if path == "/claude-zh-cn/runtime.js":
            return runtime_js()
        if path.startswith("/claude-zh-cn/i18n/dynamic/") and path.endswith(".json"):
            return json.dumps(merged_dynamic_i18n(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if path.startswith("/claude-zh-cn/i18n/") and path.endswith(".overrides.json"):
            return b"{}"
        if path.startswith("/claude-zh-cn/i18n/") and path.endswith(".json"):
            return json.dumps(merged_frontend_i18n(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        rel = path.lstrip("/")
        if ".." in Path(rel).parts:
            return b""
        file_path = MIRROR_DIR / rel
        if file_path.exists() and file_path.is_file():
            return maybe_patch_asset(file_path, file_path.read_bytes())
        return None

    def proxy_upstream(self, send_body: bool) -> None:
        host = (self.headers.get("Host") or HOST).split(":", 1)[0].lower()
        if host not in PROXY_HOSTS:
            raise RuntimeError(f"unsupported host: {host}")
        upstream_ip = self.upstream_ip_for(host)
        if not upstream_ip:
            raise RuntimeError(f"missing upstream IP for {host}")
        request_body = self.read_request_body()
        last_error: Exception | None = None
        for attempt in range(3):
            conn = None
            try:
                context = ssl.create_default_context()
                conn = FixedIPHTTPSConnection(host, upstream_ip, timeout=30, context=context)
                headers = {
                    key: value
                    for key, value in self.headers.items()
                    if key.lower() not in {"host", "connection", "accept-encoding", "content-length"}
                }
                headers["Host"] = host
                headers["Accept-Encoding"] = "identity"
                if request_body is not None:
                    headers["Content-Length"] = str(len(request_body))
                conn.request(self.command, self.path, body=request_body, headers=headers)
                resp = conn.getresponse()
                body = resp.read()
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.25 * (attempt + 1))
            finally:
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass
        else:
            raise RuntimeError(f"upstream fetch failed: {last_error}")

        content_encoding = resp.getheader("Content-Encoding")
        content_type_header = resp.getheader("Content-Type")
        if resp.status == 200 and not content_encoding:
            body = maybe_patch_upstream_response(host, self.path, body, content_type_header)
        self.cache_upstream_asset(host, resp.status, body, content_encoding)
        self.send_response(resp.status)
        excluded = {"transfer-encoding", "connection", "content-length", "vary"}
        if resp.status == 200 and not content_encoding:
            excluded.update({"content-security-policy", "content-security-policy-report-only"})
        for key, value in resp.getheaders():
            lower_key = key.lower()
            if lower_key not in excluded and not lower_key.startswith("access-control-"):
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def read_request_body(self) -> bytes | None:
        length = self.headers.get("Content-Length")
        if not length:
            return None
        try:
            size = int(length)
        except ValueError:
            return None
        if size <= 0:
            return b""
        return self.rfile.read(size)

    def upstream_ip_for(self, host: str) -> str:
        if UPSTREAM_IPS_FILE.exists():
            try:
                data = json.loads(UPSTREAM_IPS_FILE.read_text(encoding="utf-8"))
                value = data.get(host)
                if isinstance(value, str) and value and value != "127.0.0.1":
                    return value
            except Exception:
                pass
        if host == HOST and UPSTREAM_IP_FILE.exists():
            return UPSTREAM_IP_FILE.read_text(encoding="ascii").strip()
        return ""

    def cache_upstream_asset(self, host: str, status: int, body: bytes, content_encoding: str | None = None) -> None:
        if host != HOST:
            return
        if status != 200 or not body:
            return
        if content_encoding:
            self.log_message("skip compressed cache for %s: %s", self.path, content_encoding)
            return
        parsed = urlparse(self.path)
        path = unquote(parsed.path).lstrip("/")
        if not path.startswith("claude-ai/v2/assets/v1/") or ".." in Path(path).parts:
            return
        target = MIRROR_DIR / path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(body)
        except Exception as exc:
            self.log_message("cache failed for %s: %s", path, exc)


def main() -> int:
    if not HOST_CERT.exists() or not HOST_KEY.exists():
        print("Certificate files are missing. Run setup_claude_zh_proxy.py first.", file=sys.stderr)
        return 2
    os.chdir(ROOT)
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), ClaudeZhHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(HOST_CERT), str(HOST_KEY))
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    (ROOT / "proxy.pid").write_text(str(os.getpid()), encoding="ascii")
    print(f"Claude zh proxy listening on https://{HOST}:{PORT}", flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
