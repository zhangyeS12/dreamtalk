# dreamtalk 0.1.42 · Windows 地点与模型适配体验版

这是一款以聊天为中心的本地AI持久世界应用。0.1.42完善其他模型服务的同次事件／记忆、原生schema副本兼容、超时与能力设置，并按用户选择保留严格Token硬上限；[检查记录](maintenance/2026-10-08-provider-compatibility.md)。继承0.1.41地点层级／范围／隐藏／锁定及二维图，以及前序维护；[地点手册](ACTIVITY_LOCATIONS.md)。用户已授权本版源码与完整便携预发布，发布状态见[发布记录](maintenance/2026-10-08-github-release.md)与Release页面；具体模型效果、体验／升级仍待用户验收。

## 下载与启动

1. 在 [0.1.42 Release](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.42) 下载 **dreamtalk-0.1.42-windows-x64.zip**。这是完整Windows x64便携包；不要下载 Source code 代替程序。旧Release和本地providers-0142／locations-0141包保留。
2. 完整解压到一个固定目录，再打开 `dreamtalk/dreamtalk-desktop.exe`。请勿在压缩包里直接运行，也不要只复制 EXE；同目录的 `core/` 必须保留。
3. 使用 Windows 10/11 x64，并安装 [Microsoft WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)。无需安装 Python、uv、Node 或 Rust。
4. 启动动画结束后进入世界书架，选择空白书创建世界，再明确进入世界。

程序尚未签名，Windows 可能显示未知发布者提示；请使用完整便携目录或ZIP。公开Release另附 `SHA256SUMS.txt`。不用关闭系统安全防护。暂不提供 macOS/Linux 便携包或自动更新。

## 第一次聊天

1. 在书架页“模型设置”或世界内“设置”配置自己的模型服务和 API Key。支持OpenAI Responses、Claude、Gemini及兼容Chat Completions服务；具体型号／代理仍需核对容量、流式／原生能力与整轮额度。高级设置可调整请求超时；[设置手册](SETTINGS_HANDBOOK.md)。保存配置本身不会测试密钥或生成内容。
2. 进入世界并填写自己的身份。在“通讯录 → 添加角色卡”手动创建、导入 PNG/JSON，或使用联网生成。查看资料并预览确认后，角色出现在当前世界的通讯录。
3. 选择角色，点击“打开会话”即可聊天。Enter 发送，Shift+Enter 换行。聊天目录也可以新建群聊，使用 `@角色名` 指定下一位发言者。
4. 世界书在书架“管理 / 导入世界书”中创建、导入或编辑。背景条目默认隐藏；需要作为公共背景使用的条目须由你逐条确认公开。

程序不附带 API Key、个人存档或商业角色内容。角色对话、联网生成和启用后的后台模型任务可能产生服务商费用。自动活动、相遇、共同休闲、世界动态及主动联系按各自开关与许可运行，新世界默认关闭；开启前请阅读页面费用说明。

前一步0.1.39新增0037可重建本地全文／向量派生索引，首次启动不扫描／编码全部历史；冷索引随正常聊天／明确搜索逐步补齐，尚未覆盖时保留关键词回退。历史召回、老存档升级与大规模耗时待用户验收，见[记忆说明](CONTEXT_AND_RECALL.md)。旧0.1.38／0.1.39包保留。

## 更新旧版

1. 从旧版托盘选择“退出并停止后台运行”，再解压并打开完整新版。仅关闭窗口可能仍在后台运行，单实例机制会继续显示旧进程。
2. 应用数据存放在本机用户的 Tauri app-data 目录，Windows 默认对应 `%APPDATA%/app.livingworld.desktop`，不在解压目录。开发版兼容路径另为 `%LOCALAPPDATA%/LivingWorld/development`。重要数据先在程序完全退出后备份；本产品尚无完整运行存档导出/恢复界面。
3. 新版首次启动可能升级旧存档；升级后不要用旧程序打开同一存档。0.1.41追加0038地点配置表，不回写旧位置或账本，继承0037派生索引；工程端未执行真实存档迁移。
4. 如需开机自启动新目录，在新版“设置 → 后台运行”显式点击“保存并更新启动位置”。启动本身不会擅自修改注册。

## 已有功能与体验边界

已有世界书架、独立世界和玩家身份、私聊/群聊、长期聊天记忆与有界本地检索、世界事件、受约束日常/相遇/共同休闲、在线及离线主动联系、阵营/头像和三维关系网。完整离线生活重建、自动关系成长、完整 World Builder、运行世界备份/分支仍未实现。

关闭程序或电脑关机后不会执行本地模型任务。记忆召回有容量和权限边界，不保证覆盖全部历史。主动联系需有合法理由且受未回复门禁限制，开启后不一定立即收到消息。

本包采用 `--build-only` 编译打包，不启动程序或触发共同联系。已完成的源码/lint/类型与文档检查不代替用户运行产品、自动测试、真实存档迁移或付费模型验收；实际构建结果及告警见随包 `HANDOFF.md`。

## 帮助与反馈

随包 `docs/` 包含使用说明：[新版界面](WORLD_TERMINAL.md)、[设置](SETTINGS_HANDBOOK.md)、[记忆](CONTEXT_AND_RECALL.md)、[主动联系](PROACTIVE_CONTACT.md)、[后台与离线](OFFLINE_MESSAGES.md)。

本次0.1.42发布包保留根交接／产品规则，源码和测试引用转成发布提交的GitHub版本链接，需联网查看；链接基线记录在 `SOURCE_REVISION.txt`，`BUILD_INFO.json`标明源码提交和程序哈希。包内文档是该提交的快照，发布后仓库记录可有后续更新。旧 `v0.1.37` Release ZIP 保留原发布快照。

请通过 [GitHub Issues](https://github.com/zhangyeS12/dreamtalk/issues) 提供版本、Windows版本、操作步骤、预期和实际表现；可附脱敏截图。不要上传 API Key、完整私聊或个人数据库。

源码采用 Apache-2.0，见随包 `LICENSE`。第三方组件许可及通知在 `third-party-licenses/` 和 `docs/licenses/`；本轮补充锁定npm生产依赖的原许可文本。联网生成资料应在保存前核对来源及创作建议。
