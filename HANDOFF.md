# dreamtalk 工作交接

更新日期：**2026-10-07**。本轮起点：`b2bc43022e5fb4688fa2ddf22de25b05a04a98de`；Desktop **0.1.37**观星室体验版以`v0.1.37`标签定位本轮源码。用户明确授权推送当前版本、公开仓库（含源码及历史）并发布可下载便携包。
前轮应用户要求重新设计启动及世界内界面；本轮同步GitHub、整理下载及首次使用说明、补齐npm生产依赖许可证并发布既有build-only便携包，不修改Core、数据库或系统设置，不运行产品/测试/模型。规则读 [AGENTS.md](AGENTS.md)，逐项完成度读 [PROJECT_STATUS.md](docs/PROJECT_STATUS.md)，产品体验读 [PRODUCT.md](PRODUCT.md)。

## 1. 五分钟了解当前完成度

**项目已有可运行的 Windows 便携版，主要功能链路已实现；当前处于产品体验与验收阶段，尚未达到完整产品发行状态。** 原始愿景尚有缺口，也没有最新版整体验收结论；不编造一个缺少验收分母的完成百分比。

| 分类 | 当前事实 | 接手时的处理 |
| --- | --- | --- |
| 已实现并交付代码/包 | 世界书架与封面、卡/书创作与联网生成、世界/玩家身份、私聊/群聊/流式、模型/额度/恢复、长期记忆/混合RAG、两块事件、日常生命周期/经历召回、相遇/共同休闲、在线/离线主动联系、红点、阵营/头像/三维关系网、Logo启动、世界内四页视觉。 | 按第3节定位实际实现；不能重新列为“待开发”。 |
| 有明确历史使用反馈 | 用户报告卡/书生成、单聊、群聊@及无@正常，认可循环书架；0.1.23连接卡顿和0.1.30已读红点问题获确认解决。 | 反馈只覆盖当时功能/问题，不代表0.1.37全量通过。 |
| 已实现、待最新版验收 | 0.1.37视觉/操作；三维关系网/启动；长期记忆自然表现与权限边界；日常/相遇/共同休闲生命周期；双人共同联系、未回复门禁、离线联动及动态池完整流程。 | 先收集具体现象，按原契约修复；不因未验收就重做系统。 |
| 尚未实现的愿景 | 完整离线演化、更广剧情/关系/知识演化、一键构建完整运行世界/持续资料更新、Checkpoint/Timeline Branch及runtime世界备份。 | 详见第4节。未冻结的产品行为须先讨论，不是默认下一步授权。 |
| 发行未完成 | 最新版整体验收、签名安装/自动更新/正式发布；目前交付Windows便携包。 | 本版已获用户明确发布授权，按预发布体验版交付；构建成功或公开下载不等于产品完工。 |
| 已拒绝/未批准 | 共同委托、巡查、任务奖励、战斗、资产玩法，以及未经决定的云同步/市场。 | 不从历史建议、领域类名或“继续推进”推导新授权。 |

**最近进展：** 上一轮`b2bc430`只整理文档；上一应用版本`e56c7f8`完成0.1.36浅色世界内界面。用户本轮明确表示不满意并授权继续设计，当前0.1.37改为观星室：墨蓝空间、月白正文、银蓝会话、暖金主操作；压缩重复页头，新增本地名字筛选，突出人物档案，统一暗色控件/事件/弹窗。启动重编排20条光轨、1400尘点和两颗真实天体。代码与静态检查已完成，便携交付见第6节，实际体验仍待用户验收。

## 2. 仓库、运行和版本现场

| 项 | 2026-10-07恢复发布时核对 |
| --- | --- |
| 正式仓库 | `D:\LivingWorld`。`C:\Users\zhang\Documents\ChatGPT\LivingWorld`是本次受限工具的可写工作目录，不是正式仓库搬迁。 |
| 分支/基线 | `codex/world-archive` / `b2bc430`；0.1.37代码与发布说明由本轮提交，源码标识`v0.1.37`；应用前序为`e56c7f8`，实际HEAD每轮重查。 |
| 关键前序提交 | `8d56c99`：主动联系保存/启动最低展示；`42e675c`：Logo/三维启动；`167d5e8`：真三维人物网；`bd90ab3`：阵营/头像；`844259a`：离线门禁提示；`0a1539c`：已读红点修复；`ed5f844`：主动联系/通用未读。 |
| 版本 | Desktop package/Tauri/Cargo及本轮EXE元数据均为`0.1.37`。根npm/Web/Core的`0.1.0`为独立包版本，不能一并误改。 |
| 协议/迁移 | [API契约](services/core/src/livingworld/domain/api_contract.json)为`api_protocol=1`，loopback`127.0.0.1`、随机Core端口；迁移源码head`0036_character_factions`，前序0035。没有读取真实存档确认其迁移版本。 |
| GitHub | `origin=https://github.com/zhangyeS12/dreamtalk.git`。本轮已fetch核对：发布前main为`90edd3c`、开发分支为`8d56c99`，均为当前版本祖先；用户授权快进同步main与codex/world-archive。下载见[v0.1.37体验版](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.37)；不强推。 |
| 最新便携入口 | `D:\LivingWorld\artifacts\portable\observatory-0137\dreamtalk\dreamtalk-desktop.exe`；本轮已完成build-only，EXE文件/产品版本均为0.1.37；同级`dreamtalk.zip`可用于完整分发。旧`world-terminal`目录保留。产物ignored，不随Git自动同步。 |
| 存档/启动 | app identifier仍为`app.livingworld.desktop`；开发数据兼容位置为`%LOCALAPPDATA%/LivingWorld/development`。当前运行进程、用户存档与自启动注册未检查。换包须用户在新版显式“保存并更新启动位置”；启动本身不擅自改注册。 |

不要覆盖用户/其他任务改动，不强推、不改写历史。不能用旧便携版打开已升级存档；不要移动或删除DB/WAL。代码head、包版本和实际运行EXE是三种证据，必须分别核对。

## 3. 各部分怎样实现、从哪里接手

### 3.1 调用链与目录

`apps/web`（React/TypeScript/Vite）→ `packages/api-client`（认证HTTP JSON与POST回复流）→ `adapters/http`（FastAPI）→ `application`（业务/上下文/编排）→ `domain`及Kernel动作 → `infrastructure/persistence`（SQLite WAL/FTS5）。

- [App.tsx](apps/web/src/App.tsx)管理连接代次和启动交接；[ProductApp.tsx](apps/web/src/ProductApp.tsx)以React局部状态切换书架/世界/四入口，不额外引入路由或状态管理框架。设置用[SettingsHandbook.tsx](apps/web/src/SettingsHandbook.tsx)。基础样式为style/product及各功能CSS，0.1.37视觉层在[world-terminal.css](apps/web/src/world-terminal.css)，限定于世界内；不重写书架/三维场景。
- [API client](packages/api-client/src/index.ts)校验session/generation；实际回复流为一次认证POST，不自动重连重放生成。[HTTP组装](services/core/src/livingworld/adapters/http/app.py)注册各功能路由。
- [Core组合根](services/core/src/livingworld/bootstrap/cli.py)接线聊天、记忆、Director、事件池、离线/在线联系、Store及调度；[LLM组合](services/core/src/livingworld/bootstrap/llm_runtime.py)配置目的路由。不要只看到一个类或接口就宣称普通用户流程已实现。
- [Tauri host](apps/desktop/src-tauri/src/lib.rs)/[supervisor](apps/desktop/src-tauri/src/supervisor.rs)启动监督Core；[Database](services/core/src/livingworld/infrastructure/database.py)提供Store/Reader；Alembic是唯一迁移authority。

### 3.2 模块实现索引

以下Python短路径均相对`services/core/src/livingworld/`；链接指向实际源文件。具体容量/许可/验收看状态清单和各模块说明。

| 模块 | 用户入口与前端 | 后端与实际实现方式 |
| --- | --- | --- |
| 世界、身份、时钟 | `ProductApp.tsx`、`ProfileEditor.tsx`，设置时间/“我” | [world_settings.py](services/core/src/livingworld/application/world_settings.py)、`player_onboarding.py`、`local_profile.py`、`simulation_clock.py`：世界隔离、绑定Player、从家进入，通用/世界描述与暂停/倍率。 |
| 书架/封面 | `WorldArchivePage.tsx`、`WorldShelf.tsx`、`WorldCoverEditor.tsx`、`BookFaces.tsx` | [world_covers.py](services/core/src/livingworld/application/world_covers.py)、`infrastructure/persistence/world_covers.py`：Embla循环至少12位/空白创建；本地三面图/文字标题、资产校验和裁剪；0030。 |
| 卡/书创建、编辑、导入、联网生成 | 通讯录`WorldContent.tsx`/`ContentEditor.tsx`管理角色，书架管理世界书 | [content_builder.py](services/core/src/livingworld/application/content_builder.py)、`content_authoring.py`、`infrastructure/content_research.py`、`infrastructure/imports/`、`persistence/world_content.py`：检索摘要/证据/冲突→可编辑草稿→预览确认→世界内容；0023。 |
| 公共背景 | `WorldContent.tsx`、`PublicBackgroundReadiness.tsx` | [lore_activation.py](services/core/src/livingworld/application/lore_activation.py)：逐条公开且enabled，再按场景、常驻/关键词/次级条件及容量筛选。未变条目编辑保留范围，新增/修改重新确认；0022。 |
| 私聊/群聊/流式/分页 | `ChatTranscript.tsx`、`GroupChat.tsx`、`useReplyStream.ts`、`useTranscriptPages.ts` | [chat_reply.py](services/core/src/livingworld/application/chat_reply.py)、[group_chat_reply.py](services/core/src/livingworld/application/group_chat_reply.py)、`chat_messages.py`、`chat_conversations.py`：持久回合、一次认领、校验后提交；唯一@选下一位，无@独立调度；0018～0021。 |
| 模型、额度、费用、失败恢复 | `ModelSetup.tsx`、`ReplyRecoveryControls.tsx`、`ContextReferencePanel.tsx` | [chat_capacity.py](services/core/src/livingworld/application/chat_capacity.py)、`llm_execution.py`、`llm_preflight.py`、`llm_budget.py`、`persistence/chat_reply_recovery.py`/`chat_context_report.py`：可信容量裁剪、整尝试预算/账本、显式独立新attempt及参考来源；0031/0032。四类provider adapter在`infrastructure/llm/`，DeepSeek优先。 |
| 长短期记忆/本地RAG/来源 | `LongChatMemoryPanel.tsx`、`ChatHistoryPanel.tsx`、`ConversationMemoryPanel.tsx`、`SourceMessageDialog.tsx` | [long_chat_memory.py](services/core/src/livingworld/infrastructure/persistence/long_chat_memory.py)、[chat_context.py](services/core/src/livingworld/application/chat_context.py)/`group_chat_context.py`、`conversation_memory.py`、[semantic_chat_retrieval.py](services/core/src/livingworld/infrastructure/semantic_chat_retrieval.py)、`chat_retrieval.py`/`local_vector_cache.py`：同次提取、纠正/停用、权限过滤后jieba/FTS5/BM25+BGE融合及DiskCache；摘要单独预览确认；0024/0029。 |
| 日常/地点/活动生命周期 | 设置`WorldLocations.tsx`、`CharacterActivitySetup.tsx`、`WorldActivities.tsx` | [director.py](services/core/src/livingworld/application/director.py)、`routine_lifecycle.py`、`character_activity_context.py`、`infrastructure/scheduler_runtime.py`：6小时批量提案，Kernel执行真实移动/休息/工作/自由活动及开始/结束/中断；0025/0026。 |
| 聊天参考本人近况/亲历 | 聊天“本次参考内容”，自然回复 | [observed_events.py](services/core/src/livingworld/infrastructure/persistence/observed_events.py)、[experience_lifecycle.py](services/core/src/livingworld/application/experience_lifecycle.py)：只取发言者获准Observation/本人快照，当前状态优先，同次获准终态替代召回开始，不补造结果。 |
| 相遇/共同休闲 | 设置角色活动，聊天自然提及 | [character_encounters.py](services/core/src/livingworld/application/character_encounters.py)、`encounter_policy.py`、[shared_activities.py](services/core/src/livingworld/application/shared_activities.py)、`persistence/shared_activity_authority.py`：同场/实际活动/授权核验、冷却/持续同场去重，原子事件/Observation/幂等回执；0033/0034。 |
| 在线/双人主动联系、未回复门禁 | `ProactiveContactSettings.tsx`，私聊/固定双人群 | [proactive_contact.py](services/core/src/livingworld/application/proactive_contact.py)、`persistence/proactive_contact.py`、[contact_gate.py](services/core/src/livingworld/infrastructure/persistence/contact_gate.py)：真实休闲理由，双人同一次共同活动/同事由；线上线下共用持久等待回复，不逐机会选人API；0035。 |
| 离线消息/托盘/自启动 | `OfflineContactSettings.tsx`、`BackgroundSettings.tsx`、`useOfflineContact.ts` | [offline_contact.py](services/core/src/livingworld/application/offline_contact.py)、`persistence/offline_contact.py`、[background.rs](apps/desktop/src-tauri/src/background.rs)：恢复达到真实离线阈值后最多一条；剧情时间另存、保留真实生成时间，首次开启不立即发；0027。关机期间不执行。 |
| 通用未读/红点 | `useChatUnread.ts`、聊天目录/底部标签 | [chat_unread.py](services/core/src/livingworld/infrastructure/persistence/chat_unread.py)、`proactive_contact.py` HTTP：对已加载且前台可见的消息保存单调已读位置，失败提示重试并刷新未读；阅读不解除等待回复；0035。 |
| 两块世界事件 | `WorldEventJournal.tsx`、`WorldNewsSettings.tsx` | [chat_event_annotations.py](services/core/src/livingworld/application/chat_event_annotations.py)、[world_story.py](services/core/src/livingworld/application/world_story.py)/对应persistence：回复同次取具体事件/原句/时间；公共动态10条入池随机发布，手动经历/跳过达8/10续批；0028。 |
| 阵营/头像/人物网 | `ContactSocial.tsx`、`RelationshipUniverse.tsx`；聊天`useChatAvatars.ts` | [factions.py](services/core/src/livingworld/infrastructure/persistence/factions.py)、`adapters/http/factions.py`：直接成员多重归属、同阵营持久相识、父子不继承；头像本地资产、3d-force-graph/Three.js真三维拾取/相机/漂浮，聊天/Director使用有界相识输入；0036。 |
| Logo、启动/界面材质 | `Brand.tsx`、`StartupSplash.tsx`、`celestialVortex.ts`、`world-terminal.css` | 前台首帧至少1.5秒且Core/书架真实就绪后交接；Three.js真实纵深，隐藏后台停渲染、静态/错误回退；0.1.37观星室四页及双天体星轨；本轮未改Core源码。 |
| Kernel/知识/持久化基础 | 普通功能经应用接线；开发Inspector独立 | [command_handler.py](services/core/src/livingworld/application/command_handler.py)、`action_resolution.py`、`ledger.py`/`replay.py`、`domain/knowledge.py`、`application/memory.py`、`persistence/unit_of_work.py`：CAS/幂等/事务事件、投影重建、owner授权Observation/EpisodicMemory；不是普通聊天自动写Truth。 |
| 内容包/外部导出基础 | 核心已有能力，不能推定完整用户备份UI | [package_service.py](services/core/src/livingworld/application/package_service.py)、`exports.py`、`infrastructure/packages/`：authored内容依赖闭包、冲突确认、`.lwcontent`及JSON导出；不是runtime存档/Checkpoint。 |

## 4. 未完成与必须保留的范围边界

### 4.1 已有能力的限制

- **记忆不是无限覆盖**：长期提示最多16条/8KiB；授权相关历史原句最多4条/8KiB；本地每通道最多8192引用、每次最多128新编码、缓存目标256MiB、语义等待3秒后关键词回退。自动同次提取可漏记。停用/纠正不删除原聊天或当前短期上下文。
- **亲历不是全知**：本人近期最多6条/6KiB；亲历从近128条获准观察选最多12条/8KiB。同次终态只能从已有授权窗口关联；只见开始者不能获得隐藏结束。普通自述、摘要、计划与WorldTruth/EpisodicMemory分开。
- **公共不等于本次触发**：背景仍须enabled、提供条件/关键词/容量。聊天、日常和动态池各用自己的场景；范围数量不能证明当次有材料。活动开始/结束、公开动态和手动“经历”不认证任务成果/传闻真值。
- **主动联系不保证一开就发**：合法实际休闲/许可/间隔/计划/门禁同时满足；双人须同一真实共同休闲、同一邀请目的。所有角色共享未回复限制，阅读/开关/重启不能释放；只在收到联系的会话回复才解锁。
- **节奏固定**：Director常规6小时批次；原批至少2条且50%日常失效才提前重规划。每批问候+共同开始合计最多2次，首次见面每角色24世界小时最多一个新对象；共同开始每角色24小时一次，同对6小时冷却、15～30世界分钟。
- **本地运行有限**：退出/关机不调用API；托盘仍运行不等于离线。恢复不补造错过的移动/相遇/共同成果。WorldTime是整数微秒逻辑时间，UTC是真实时间，不能隐式互换。
- **模型兼容有限**：四类adapter已有，DeepSeek优先；未知型号/代理及各厂商结构化事件/记忆效果未全面验收。聊天尝试内部所有选人/回复/retry共用上限；资料/后台任务有独立预算，失败不自动付费重放。

### 4.2 真正尚未实现

| 方向 | 已有基础 | 尚缺什么/授权状态 |
| --- | --- | --- |
| 完整离线演化 | UTC bridge、到期调度、单条离线消息 | 关机期间角色生活/社交/结果的完整重建；尚无完整批准契约。 |
| 更广剧情/关系/知识传播 | Observation、阵营相识、相遇、共同休闲、权限与记忆 | 不是完整自主剧情；没有自动关系成长、正式介绍流程或通用逐角色秘密/传闻传播产品闭环。 |
| 更广共同联系 | 同事由双人真实共同休闲已实现 | 三人以上、未来尚未开始的活动、任意新行动需独立契约；不能混合不同目的。 |
| 完整World Builder/来源更新 | 单卡/书摘要研究、证据、草稿确认 | 一键构建可运行世界、全文核验、持续来源更新。 |
| Runtime世界备份/分支 | ledger/replay、authored内容包 | 普通用户完整Checkpoint/Timeline Branch/`.lworld`保存恢复未实现；内容包不是存档备份。 |
| Director风格管理 | 批量日常与社交子集 | 完整参数/风格管理的产品行为未冻结。 |
| 正式发行 | Windows便携包 | 最新版整体验收、性能/兼容结论、签名安装/自动更新/发布；不能自动创建Release。 |

共同委托/巡查、奖励/战斗不是以上愿景的默认实现方法；用户已明确否定自行添加。完整SillyTavern行为兼容也未实现，现有卡/书格式兼容不等于概率/递归/脚本等全兼容。

## 5. 接下来从哪一步继续

1. **先接收0.1.37体验反馈**：聊天/通讯录/设置/我，重点头像更新、会话工具、滚动、未读、草稿/保存、窄窗口；完成条件见[世界内界面](docs/WORLD_TERMINAL.md)。没有新反馈时不要把这轮实现重新登记为未完成代码。
2. **验收尚未确认的关键链路**：记忆纠正/停用和旧事召回、活动真实终态/权限、动态池公共背景→生成→逐条发布→标记、在线单人/双人同事由→等待回复→原会话回复→合法下次机会、离线联动。主动联系失败先查保存状态/前提/终端原因，不靠反复开关或自动重放API排查。
3. **只按证据修复**：记录现象、版本、受影响模块和可观察完成条件；新功能先调查成熟实现并确认新增范围。用户仍负责测试；未获新许可不运行自动测试、GUI smoke、真实存档/模型诊断。
4. **新方向先讨论**：将4.2中的愿景与当前功能验收分开；0.1.37已获公开体验发布授权，后续版本发行仍须相应批准。现在没有等待补写的共同委托，也没有需要重新搭建的记忆底座。

各功能操作/验收手册： [聊天恢复](docs/CHAT_FUNCTIONAL_EXPERIENCE.md)、[记忆与上下文](docs/CONTEXT_AND_RECALL.md)、[经历终态](docs/EXPERIENCE_STATE_RECALL.md)、[日常](docs/DIRECTOR_ACTIVITIES.md)、[相遇](docs/CHARACTER_ENCOUNTERS.md)、[共同休闲](docs/SHARED_LEISURE.md)、[主动联系](docs/PROACTIVE_CONTACT.md)、[离线消息](docs/OFFLINE_MESSAGES.md)、[事件](docs/WORLD_EVENT_JOURNAL.md)、[阵营](docs/CHARACTER_FACTIONS.md)、[启动](docs/CELESTIAL_STARTUP.md)。

## 6. 交付与证据

### 本轮0.1.37观星室（2026-10-05）

- 实现基于`b2bc430`，公开源码以`v0.1.37`标签定位；Desktop版本0.1.37；无Core/API/迁移改动，无新依赖，原Logo字节未改。
- 本轮`npm run lint`（ESLint/TypeScript）通过；CSS静态解析世界内346条/启动40条规则；10组代表性配色计算最低5.60:1。这不是渲染验证、全页面对比度认证或用户验收。
- build-only完成：`.\.venv\Scripts\python.exe scripts\build-portable.py --build-only --output-name observatory-0137`。常规npm/uv入口因本机uv缓存目录拒绝访问未开始构建；改用已安装PyInstaller6.22.3的仓库虚拟环境调用同一脚本完成。没有修改构建脚本、安装依赖或绕开build-only。
- 独立便携目录`artifacts/portable/observatory-0137/dreamtalk`与同级ZIP已生成，EXE FileVersion/ProductVersion均为0.1.37。Desktop SHA256 `87fc2f6f23b8c18d06b0f6c24caad61bbbf52de8c0b7fb198a86d92ff46674aa`；Core SHA256 `2d7bc064f1af15e7525108e4465bb492ea89e308889e95b8c9e152f3a43baa94`，与0.1.36记录一致。最终ZIP/源码/资产清单在`artifacts/observatory-source-audit.json`（ignored）。
- 本轮文档链接751个本地目标/0断链；Git差异格式无错误，Git提示部分text=auto文件在后续操作时转换CRLF。包内docs在构建结束后同步本轮最终交付说明并重新压缩，仅影响这个新包。
- 构建非阻塞告警：主chunk717.72kB、Three.js587.98kB、关系网817.51kB；STATIC_VCRUNTIME弃用；PyInstaller缺少tzdata/pysqlite2/MySQLdb的hidden import及jieba转义SyntaxWarning。未据此新增依赖，也未宣称运行兼容通过。
- 未运行自动测试、GUI smoke、模型、真实存档或迁移；未更改系统启动注册。构建/运行/用户接受分别记录。
- 设计方案和验收入口：[世界内界面](docs/WORLD_TERMINAL.md)、[启动](docs/CELESTIAL_STARTUP.md)、[成品复用](docs/research/2026-10-05-observatory-design.md)。

### 本轮公开体验发布（2026-10-07恢复完成）

- 用户明确授权GitHub推送，并确认将当前私有仓库设为公开，包含源码与提交历史；不以此补造最新版整体验收结论。
- 源码同步main与codex/world-archive，版本标签`v0.1.37`；[Release入口](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.37)提供`dreamtalk-0.1.37-windows-x64.zip`与`SHA256SUMS.txt`。
- 使用前轮已构建的EXE/Core，源码哈希与原构建记录一致；本轮只更新包内说明和许可证并重新压缩，不运行应用或重建程序。发布资产记录保存在`artifacts/release-0137/`（ignored）。
- 随包README改为当前0.1.37上手/升级说明，不再把0.1.27称为最新；补充锁定npm生产依赖的原许可证/通知文本。
- 保留既有测试/CI定义；发布提交用`[skip ci]`遵守本轮不运行自动测试的约定，不据此声称CI通过。
- 发布前检查Git历史中2563个文本blob及包内文件名，命中项为离线测试的synthetic凭据；未发现匹配规则的真实密钥或用户数据文件。此为有界发布检查，不宣称覆盖所有敏感信息。
- 本轮说明见[0.1.37发布说明](docs/releases/0.1.37.md)；恢复后再次核对GitHub仍为私有且无Release，按已有授权完成发布。本轮链接检查743个本地目标/0断链，与前轮构建记录分别保留。

### 历史交付

- 0.1.36 `e56c7f8`完成浅色世界内UI与build-only便携包；2026-10-05用户反馈不满意，已被本轮新视觉方案接续。旧包`artifacts/portable/world-terminal/dreamtalk`保留。
- 0.1.35主动联系保存/至少1.5秒启动、0.1.33三维关系网、0.1.30红点验收及更早构建记录查Git（`git show b2bc430:HANDOFF.md`、`git show e56c7f8:HANDOFF.md`）和[历史索引](docs/history/README.md)。
- 上一文档轮749个本地目标/0断链等是历史检查，本轮结果另行记录，不推定本轮功能验收。

## 7. 接手操作与维护规则

先读当前用户要求、AGENTS/HANDOFF/状态，再检查：

```powershell
git status --short
git log --oneline -8
git diff --stat
git diff --cached --stat
git diff --check
.\.venv\Scripts\python.exe scripts\check-doc-links.py
```

需要源码检查时使用`npm run lint`；构建属于开发任务时用`npm run build:portable -- --build-only`。默认打包包含自检，不得遗漏`--build-only`。开发入口为`dev:desktop`/`dev:web`/`dev:core`，UI端口1420不是Core端口；文档任务不启动这些入口。保留现有tests/CI，历史测试或单次诊断许可不授权本轮自动运行。

每次改动同步：AGENTS只记录长期规则/新决定，PROJECT_STATUS更新对应能力与验收，HANDOFF保留当前基线/现场/接续。不要追加第二个“最新”、虚报完成率或把历史包写成当前入口。用户反馈按原话/问题/版本归档；没有具体反馈不能升级为全量验收。
