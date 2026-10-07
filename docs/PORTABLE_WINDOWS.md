# dreamtalk 0.1.37 · Windows 观星室体验版

这是一款以聊天为中心的本地 AI 持久世界应用。0.1.37 更新启动星轨、聊天、通讯录、设置与个人资料的观星室界面；当前为预发布体验版，尚未完成最新版整体验收。

## 下载与启动

1. 从 [GitHub Release](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.37) 下载 **dreamtalk-0.1.37-windows-x64.zip**。不要下载 Source code 代替程序。
2. 完整解压到一个固定目录，再打开 `dreamtalk/dreamtalk-desktop.exe`。请勿在压缩包里直接运行，也不要只复制 EXE；同目录的 `core/` 必须保留。
3. 使用 Windows 10/11 x64，并安装 [Microsoft WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)。无需安装 Python、uv、Node 或 Rust。
4. 启动动画结束后进入世界书架，选择空白书创建世界，再明确进入世界。

程序尚未签名，Windows 可能显示未知发布者提示；请从项目 Release 获取完整包并核对随附 `SHA256SUMS.txt`。不用关闭系统安全防护。暂不提供 macOS/Linux 便携包或自动更新。

## 第一次聊天

1. 在书架页“模型设置”或世界内“设置”配置自己的模型服务和 API Key。DeepSeek 为当前优先适配方向；选择模型、核对容量和回复额度后保存。保存配置本身不会测试密钥或生成内容。
2. 进入世界并填写自己的身份。在“通讯录 → 添加角色卡”手动创建、导入 PNG/JSON，或使用联网生成。查看资料并预览确认后，角色出现在当前世界的通讯录。
3. 选择角色，点击“打开会话”即可聊天。Enter 发送，Shift+Enter 换行。聊天目录也可以新建群聊，使用 `@角色名` 指定下一位发言者。
4. 世界书在书架“管理 / 导入世界书”中创建、导入或编辑。背景条目默认隐藏；需要作为公共背景使用的条目须由你逐条确认公开。

程序不附带 API Key、个人存档或商业角色内容。角色对话、联网生成和启用后的后台模型任务可能产生服务商费用。自动活动、相遇、共同休闲、世界动态及主动联系按各自开关与许可运行，新世界默认关闭；开启前请阅读页面费用说明。

## 更新旧版

1. 从旧版托盘选择“退出并停止后台运行”，再解压并打开完整新版。仅关闭窗口可能仍在后台运行，单实例机制会继续显示旧进程。
2. 应用数据存放在本机用户的 Tauri app-data 目录，Windows 默认对应 `%APPDATA%/app.livingworld.desktop`，不在解压目录。开发版兼容路径另为 `%LOCALAPPDATA%/LivingWorld/development`。重要数据先在程序完全退出后备份；本产品尚无完整运行存档导出/恢复界面。
3. 新版首次启动可能升级旧存档；升级后不要用旧程序打开同一存档。本轮0.1.37没有新增迁移，迁移源码仍到0036。
4. 如需开机自启动新目录，在新版“设置 → 后台运行”显式点击“保存并更新启动位置”。启动本身不会擅自修改注册。

## 已有功能与体验边界

已有世界书架、独立世界和玩家身份、私聊/群聊、长期聊天记忆与有界本地检索、世界事件、受约束日常/相遇/共同休闲、在线及离线主动联系、阵营/头像和三维关系网。完整离线生活重建、自动关系成长、完整 World Builder、运行世界备份/分支仍未实现。

关闭程序或电脑关机后不会执行本地模型任务。记忆召回有容量和权限边界，不保证覆盖全部历史。主动联系需有合法理由且受未回复门禁限制，开启后不一定立即收到消息。

本包基于已完成的 lint/类型检查、CSS静态检查和 build-only 编译；发布阶段只核对源码、包内容、哈希与下载。未代替用户运行产品、自动测试、真实存档迁移或付费模型验收。构建存在JS体积、STATIC_VCRUNTIME弃用、PyInstaller可选hidden import及jieba语法提示，详见源码 `HANDOFF.md`。

## 帮助与反馈

随包 `docs/` 包含完整说明：`WORLD_TERMINAL.md`（新版界面）、`SETTINGS_HANDBOOK.md`（设置）、`CONTEXT_AND_RECALL.md`（记忆）、`PROACTIVE_CONTACT.md`（主动联系）、`OFFLINE_MESSAGES.md`（后台与离线）。

请通过 [GitHub Issues](https://github.com/zhangyeS12/dreamtalk/issues) 提供版本、Windows版本、操作步骤、预期和实际表现；可附脱敏截图。不要上传 API Key、完整私聊或个人数据库。

源码采用 Apache-2.0，见随包 `LICENSE`。第三方组件许可及通知在 `third-party-licenses/` 和 `docs/licenses/`；本轮补充锁定npm生产依赖的原许可文本。联网生成资料应在保存前核对来源及创作建议。
