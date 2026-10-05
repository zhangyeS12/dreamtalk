# dreamtalk 工作交接

更新日期：**2026-10-05**。源码核对基线：`e56c7f8b63a75574c404e7e071ee879ee94fa390`，Desktop **0.1.36**。
本轮只整理文档，不修改应用、版本、数据库、系统设置或便携包，不运行产品/测试/模型。规则读 [AGENTS.md](AGENTS.md)，逐项完成度读 [PROJECT_STATUS.md](docs/PROJECT_STATUS.md)，产品体验读 [PRODUCT.md](PRODUCT.md)。

## 1. 五分钟了解当前完成度

**项目已有可运行的 Windows 便携版，主要功能链路已实现；当前处于产品体验与验收阶段，尚未达到完整产品发行状态。** 原始愿景尚有缺口，也没有最新版整体验收结论；不编造一个缺少验收分母的完成百分比。

| 分类 | 当前事实 | 接手时的处理 |
| --- | --- | --- |
| 已实现并交付代码/包 | 世界书架与封面、卡/书创作与联网生成、世界/玩家身份、私聊/群聊/流式、模型/额度/恢复、长期记忆/混合RAG、两块事件、日常生命周期/经历召回、相遇/共同休闲、在线/离线主动联系、红点、阵营/头像/三维关系网、Logo启动、世界内四页视觉。 | 按第3节定位实际实现；不能重新列为“待开发”。 |
| 有明确历史使用反馈 | 用户报告卡/书生成、单聊、群聊@及无@正常，认可循环书架；0.1.23连接卡顿和0.1.30已读红点问题获确认解决。 | 反馈只覆盖当时功能/问题，不代表0.1.36全量通过。 |
| 已实现、待最新版验收 | 0.1.36视觉/操作；三维关系网/启动；长期记忆自然表现与权限边界；日常/相遇/共同休闲生命周期；双人共同联系、未回复门禁、离线联动及动态池完整流程。 | 先收集具体现象，按原契约修复；不因未验收就重做系统。 |
| 尚未实现的愿景 | 完整离线演化、更广剧情/关系/知识演化、一键构建完整运行世界/持续资料更新、Checkpoint/Timeline Branch及runtime世界备份。 | 详见第4节。未冻结的产品行为须先讨论，不是默认下一步授权。 |
| 发行未完成 | 最新版整体验收、签名安装/自动更新/正式发布；目前交付Windows便携包。 | GitHub push/Release须用户明确批准，构建成功不等于产品完工。 |
| 已拒绝/未批准 | 共同委托、巡查、任务奖励、战斗、资产玩法，以及未经决定的云同步/市场。 | 不从历史建议、领域类名或“继续推进”推导新授权。 |

**上一个开发切片已经结束：** `e56c7f8` 完成0.1.36世界内界面优化，采用深蓝灰外壳、月白阅读面和连续档案层级。聊天复用头像、按日期分隔并收纳工具；通讯录、设置、个人身份和事件统一层级。沿用既有Core和后台开关，未改费用/知识/持久化契约。当前待办是体验验收及有证据的修复，不是继续完成一份未写完的UI代码。

## 2. 仓库、运行和版本现场

| 项 | 2026-10-05只读核对 |
| --- | --- |
| 正式仓库 | `D:\LivingWorld`。`C:\Users\zhang\Documents\ChatGPT\LivingWorld`是本次受限工具的可写工作目录，不是正式仓库搬迁。 |
| 分支/基线 | `codex/world-archive` / `e56c7f8`；本轮开始工作区干净。此哈希是应用实现基线，后续文档提交查`git log`。 |
| 关键前序提交 | `8d56c99`：主动联系保存/启动最低展示；`42e675c`：Logo/三维启动；`167d5e8`：真三维人物网；`bd90ab3`：阵营/头像；`844259a`：离线门禁提示；`0a1539c`：已读红点修复；`ed5f844`：主动联系/通用未读。 |
| 版本 | Desktop package/Tauri/Cargo及现有EXE为`0.1.36`。根npm/Web/Core的`0.1.0`为独立包版本，不能一并误改。 |
| 协议/迁移 | [API契约](services/core/src/livingworld/domain/api_contract.json)为`api_protocol=1`，loopback`127.0.0.1`、随机Core端口；迁移源码head`0036_character_factions`，前序0035。没有读取真实存档确认其迁移版本。 |
| GitHub | `origin=https://github.com/zhangyeS12/dreamtalk.git`。此前0.1.35按用户要求备份，当前本地追踪引用为`8d56c99`；0.1.36只本地提交。本轮不fetch/push，不把追踪引用称为实时远端核对。 |
| 最新便携入口 | `D:\LivingWorld\artifacts\portable\world-terminal\dreamtalk\dreamtalk-desktop.exe`；完整目录与同级`dreamtalk.zip`一起保留。产物ignored，不随Git自动同步。 |
| 存档/启动 | app identifier仍为`app.livingworld.desktop`；开发数据兼容位置为`%LOCALAPPDATA%/LivingWorld/development`。当前运行进程、用户存档与自启动注册未检查。换包须用户在新版显式“保存并更新启动位置”；启动本身不擅自改注册。 |

不要覆盖用户/其他任务改动，不强推、不改写历史。不能用旧便携版打开已升级存档；不要移动或删除DB/WAL。代码head、包版本和实际运行EXE是三种证据，必须分别核对。

## 3. 各部分怎样实现、从哪里接手

### 3.1 调用链与目录

`apps/web`（React/TypeScript/Vite）→ `packages/api-client`（认证HTTP JSON与POST回复流）→ `adapters/http`（FastAPI）→ `application`（业务/上下文/编排）→ `domain`及Kernel动作 → `infrastructure/persistence`（SQLite WAL/FTS5）。

- [App.tsx](apps/web/src/App.tsx)管理连接代次和启动交接；[ProductApp.tsx](apps/web/src/ProductApp.tsx)以React局部状态切换书架/世界/四入口，不额外引入路由或状态管理框架。设置用[SettingsHandbook.tsx](apps/web/src/SettingsHandbook.tsx)。基础样式为style/product及各功能CSS，0.1.36覆盖在[world-terminal.css](apps/web/src/world-terminal.css)，限定于世界内；不重写书架/三维场景。
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
| Logo、启动/界面材质 | `Brand.tsx`、`StartupSplash.tsx`、`celestialVortex.ts`、`world-terminal.css` | 前台首帧至少1.5秒且Core/书架真实就绪后交接；Three.js真实纵深，隐藏后台停渲染、静态/错误回退；0.1.36统一四页，Core与0.1.35包相同。 |
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

1. **先接收0.1.36体验反馈**：聊天/通讯录/设置/我，重点头像更新、会话工具、滚动、未读、草稿/保存、窄窗口；完成条件见[世界内界面](docs/WORLD_TERMINAL.md)。没有新反馈时不要把这轮实现重新登记为未完成代码。
2. **验收尚未确认的关键链路**：记忆纠正/停用和旧事召回、活动真实终态/权限、动态池公共背景→生成→逐条发布→标记、在线单人/双人同事由→等待回复→原会话回复→合法下次机会、离线联动。主动联系失败先查保存状态/前提/终端原因，不靠反复开关或自动重放API排查。
3. **只按证据修复**：记录现象、版本、受影响模块和可观察完成条件；新功能先调查成熟实现并确认新增范围。用户仍负责测试；未获新许可不运行自动测试、GUI smoke、真实存档/模型诊断。
4. **新方向先讨论，发行最后决定**：将4.2中的愿景与当前功能验收分开；发布须用户明确批准。现在没有等待补写的共同委托，也没有需要重新搭建的记忆底座。

各功能操作/验收手册： [聊天恢复](docs/CHAT_FUNCTIONAL_EXPERIENCE.md)、[记忆与上下文](docs/CONTEXT_AND_RECALL.md)、[经历终态](docs/EXPERIENCE_STATE_RECALL.md)、[日常](docs/DIRECTOR_ACTIVITIES.md)、[相遇](docs/CHARACTER_ENCOUNTERS.md)、[共同休闲](docs/SHARED_LEISURE.md)、[主动联系](docs/PROACTIVE_CONTACT.md)、[离线消息](docs/OFFLINE_MESSAGES.md)、[事件](docs/WORLD_EVENT_JOURNAL.md)、[阵营](docs/CHARACTER_FACTIONS.md)、[启动](docs/CELESTIAL_STARTUP.md)。

## 6. 交付与证据

### 最新应用交付：0.1.36（2026-10-04）

- 实现提交`e56c7f8`；此前前端ESLint/TypeScript、静态CSS语法/288规则范围、9组基础文字色值最低6.25:1、文档链接和Git差异检查通过；`--build-only --output-name world-terminal`完成。**这些是前轮检查/构建记录，不是本轮重跑或用户整体验收。**
- 便携目录`artifacts/portable/world-terminal/dreamtalk`，ZIP为同级`dreamtalk.zip`；EXE元数据FileVersion/ProductVersion本轮只读核对仍为0.1.36。静态清单在`artifacts/world-terminal-source-audit.json`（ignored）。Desktop SHA256记录为`80051e373bd316f41dac2e6c242129481d574d6074093f96abf0f252d6c4299f`，Core为`2d7bc064f1af15e7525108e4465bb492ea89e308889e95b8c9e152f3a43baa94`；本轮未重新全量hash。前轮清单记录Core与0.1.35相同。
- 构建保留非阻塞告警：主chunk713.56kB、共享Three.js587.98kB、人物网817.51kB及STATIC_VCRUNTIME弃用；不能宣称帧率/全平台兼容已验收。
- 包内文档为2026-10-04打包快照；**本轮2026-10-05文档只更新源码仓库，不重打包/重写原ZIP及哈希**。接手看仓库根的当前规则；不能说现有包的文档与此次新文档字节相同。

### 历史与本轮证据

0.1.35主动联系JSON头/UUID适配及启动至少1.5秒、0.1.33真三维关系网、0.1.30红点修复、0.1.29主动联系的完整构建记录/哈希保留在Git基线：`git show e56c7f8:HANDOFF.md`。更早根文件原文在[历史索引](docs/history/README.md)，不从旧排期推导新工作。

本轮只读核对Git、版本/迁移源码、UI接线、Core组合根/HTTP路由、记忆限制及现有静态清单；本轮文档链接检查：749个本地目标、0断链；Git差异格式检查通过，32个未涉及修改的编号规则章节与原文一致，变更仅4份Markdown。337个外部URL仅计数，未联网探测。提交哈希查本轮git log。没有启动产品、自动测试、付费模型、数据库升级或用户存档读取，没有核对当前运行EXE或自启动注册。

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
