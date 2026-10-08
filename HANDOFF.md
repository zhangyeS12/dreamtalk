# dreamtalk 工作交接

更新日期：**2026-10-08**。正式仓库`D:\LivingWorld`，分支`codex/world-archive`，本轮起始HEAD为`0e6f2ee`，发布源码提交为`bdf153d`（标签`v0.1.42`），发布后的文档更新以当前Git HEAD为准；Desktop版本 **0.1.42**。0.1.40源码已推送；2026-10-08按用户授权已公开发布当前0.1.42源码及完整Windows便携包，下载见[v0.1.42预发布](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.42)，执行证据见[发布记录](docs/maintenance/2026-10-08-github-release.md)。既有v0.1.37和本地旧包保留。用户确认CCv2卡／World Info JSON导入通过；共同联系继续先等待用户验收。

本轮发布沿用已经完成的build-only程序，更新包内说明、源码链接和校验文件，不运行应用或模型。此前完善四类模型服务同次事件／记忆接线、原生schema的wire副本兼容，以及设置中的超时／能力声明和严格额度提示。用户明确继续保留可信容量硬上限，不用Claude估算或其他Gemini协议计数冒充严格上界；[实现与检查](docs/maintenance/2026-10-08-provider-compatibility.md)。前一步0.1.41完成地点层级、初始范围／锁定、隐藏分支、二维图和严格同地点相遇；[地点维护记录](docs/maintenance/2026-10-07-location-scopes.md)。不执行本轮真实存档迁移、应用／测试／模型验收。0.1.40反馈及0.1.39长历史仍保留具体待验收范围。规则读[AGENTS.md](AGENTS.md)，完成度读[PROJECT_STATUS.md](docs/PROJECT_STATUS.md)。

## 1. 五分钟了解当前完成度

**项目已有可运行的 Windows 便携版，主要功能链路已实现；当前处于产品体验与验收阶段，尚未达到完整产品发行状态。** 原始愿景尚有缺口，也没有最新版整体验收结论；不编造一个缺少验收分母的完成百分比。

| 分类 | 当前事实 | 接手时的处理 |
| --- | --- | --- |
| 已实现并交付代码/包 | 世界书架与封面、卡/书创作与联网生成、世界/玩家身份、私聊/群聊/流式、模型/额度/恢复、长期记忆/混合RAG、两块事件、日常生命周期/经历召回、相遇/共同休闲、在线/离线主动联系、红点、阵营/头像/三维关系网、地点层级／范围／隐藏／锁定及二维位置图、Logo启动、世界内四页视觉。 | 按第3节定位实际实现；不能重新列为“待开发”。 |
| 有明确使用反馈 | 用户报告卡/书生成、单聊、群聊@及无@正常，认可循环书架；0.1.23连接卡顿和0.1.30已读红点问题获确认解决。2026-10-07本轮CCv2角色卡与World Info JSON世界书外部导入获用户确认通过。 | 反馈只覆盖当次功能／资料，不代表最新版全量通过。 |
| 已实现、待最新版验收 | 0.1.42其他厂商同次提取、超时／原生能力保存和严格额度提示；0.1.41地点层级、范围／隐藏／锁定及实际相遇；视觉／三维网／启动；长期记忆自然表现与权限；日常／相遇／共同休闲生命周期；双人共同联系、未回复门禁、离线联动及动态池。 | 先收集具体现象，按原契约修复；不因未验收就重做系统。 |
| 尚未实现的愿景 | 完整离线演化、更广剧情/关系/知识演化、一键构建完整运行世界/持续资料更新、Checkpoint/Timeline Branch及runtime世界备份。 | 详见第4节。未冻结的产品行为须先讨论，不是默认下一步授权。 |
| 发行未完成 | 最新版整体验收、签名安装/自动更新/正式发布；目前交付Windows便携包。 | 0.1.42源码与完整便携预发布已按本轮授权公开交付；构建成功或公开下载不等于产品完工。 |
| 已拒绝/未批准 | 共同委托、巡查、任务奖励、战斗、资产玩法，以及未经决定的云同步/市场。 | 不从历史建议、领域类名或“继续推进”推导新授权。 |

**最近进展：** 0.1.42完善其他厂商同次提取、原生wire schema和设置接线，保留用户确认的严格硬上限；[适配记录](docs/maintenance/2026-10-08-provider-compatibility.md)。前序0.1.41地点包保留待验收。以下为之前维护脉络：0.1.37观星室已公开预发布。审查后，本轮更正文档旧状态/迁移head/产品决定表，补主动联系手册与后续打包链接，收拢聊天流程、资料投影、适配器通用处理、幂等回执恢复及迁移版本集合，清理旧CSS与未使用依赖。用户尚未收到共同联系消息，明确先等待；没有主动联系运行或验收结论。随后批准并实现长历史索引/分页召回及200条聊天窗口；详见[长历史维护](docs/maintenance/2026-10-07-long-history-recall.md)，前一步去重/文档记录见[维护记录](docs/maintenance/2026-10-07-code-and-docs.md)。

## 2. 仓库、运行和版本现场

| 项 | 2026-10-08维护现场 / 已发布历史 |
| --- | --- |
| 正式仓库 | `D:\LivingWorld`。`C:\Users\zhang\Documents\ChatGPT\LivingWorld`是本次受限工具的可写工作目录，不是正式仓库搬迁。 |
| 分支/基线 | `codex/world-archive`；0.1.40源码同步前基线`4d280cc`，2026-10-07同步提交包含0.1.38～0.1.40维护，本轮起始HEAD为0e6f2ee，发布源码提交bdf153d；最新版应用源码以v0.1.42标签与发布记录定位，后续说明提交不重建程序或移动标签。既有Release源码标识`v0.1.37`，设计基线`b2bc430`，应用前序`e56c7f8`。实际HEAD每轮重查。 |
| 关键前序提交 | `8d56c99`：主动联系保存/启动最低展示；`42e675c`：Logo/三维启动；`167d5e8`：真三维人物网；`bd90ab3`：阵营/头像；`844259a`：离线门禁提示；`0a1539c`：已读红点修复；`ed5f844`：主动联系/通用未读。 |
| 版本 | 当前Desktop package/Tauri/Cargo与对应锁文件为`0.1.42`，已公开发布地点与模型适配体验版；0.1.37历史包保留。根npm/Web/Core的`0.1.0`为独立包版本，不能一并误改。 |
| 协议/迁移 | [API契约](services/core/src/livingworld/domain/api_contract.json)为`api_protocol=1`，loopback`127.0.0.1`、随机Core端口；迁移源码head`0038_location_policies`，前序0037。0.1.42不新增迁移，本轮不读取或迁移真实存档。 |
| GitHub | `origin=https://github.com/zhangyeS12/dreamtalk.git`。0.1.40同步前fetch核对：main与codex/world-archive均为`4d280cc`；2026-10-07按用户授权快进同步0.1.40源码；本轮已按授权快进推送0.1.42源码至main与codex/world-archive，并公开发布新版便携包，下载见[v0.1.42体验版](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.42)，提交、附件和公开下载证据见发布记录；不强推。 |
| 最新便携入口 | `D:\LivingWorld\artifacts\portable\providers-0142\dreamtalk\dreamtalk-desktop.exe`；build-only结果见模型适配维护记录。Core与完整ZIP在同一便携目录；旧locations-0141包保留，产物ignored，不随Git自动同步。 |
| 存档/启动 | app identifier仍为`app.livingworld.desktop`；开发数据兼容位置为`%LOCALAPPDATA%/LivingWorld/development`。本轮未检查运行进程、用户存档或自启动注册。换包须用户在新版显式“保存并更新启动位置”；启动本身不擅自改注册。 |

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
| 模型、额度、费用、失败恢复 | `ModelSetup.tsx`、`ReplyRecoveryControls.tsx`、`ContextReferencePanel.tsx` | [chat_capacity.py](services/core/src/livingworld/application/chat_capacity.py)、`llm_execution.py`、`llm_preflight.py`、`llm_budget.py`、`persistence/chat_reply_recovery.py`/`chat_context_report.py`：可信容量裁剪、整尝试预算/账本、显式独立新attempt；0031/0032。四类adapter、wire转换在`infrastructure/llm/`，同次附带接线在`bootstrap/llm_runtime.py`，设置序列化在Tauri`llm_config.rs`；0.1.42不新增估算准入。 |
| 长短期记忆/本地RAG/来源 | `LongChatMemoryPanel.tsx`、`ChatHistoryPanel.tsx`、`ConversationMemoryPanel.tsx`、`SourceMessageDialog.tsx` | [long_chat_memory.py](services/core/src/livingworld/infrastructure/persistence/long_chat_memory.py)、[chat_context.py](services/core/src/livingworld/application/chat_context.py)/`group_chat_context.py`、`conversation_memory.py`、[semantic_chat_retrieval.py](services/core/src/livingworld/infrastructure/semantic_chat_retrieval.py)、`chat_retrieval.py`/`local_vector_cache.py`：同次提取、纠正/停用、权限过滤后jieba/FTS5/BM25+BGE融合及DiskCache；SQLite持久全文/向量派生索引；摘要单独预览确认；0024/0029/0037。 |
| 日常/地点/活动生命周期 | 通讯录`LocationWorkspace.tsx`；设置`WorldActivities.tsx` | [director.py](services/core/src/livingworld/application/director.py)、`routine_lifecycle.py`、`character_activity_context.py`、`infrastructure/scheduler_runtime.py`：6小时批量提案，Kernel执行真实移动/休息/工作/自由活动及开始/结束/中断；0025/0026/0038。地点范围、隐藏与锁定共同判定见`location_rules.py`。 |
| 聊天参考本人近况/亲历 | 聊天“本次参考内容”，自然回复 | [observed_events.py](services/core/src/livingworld/infrastructure/persistence/observed_events.py)、[experience_lifecycle.py](services/core/src/livingworld/application/experience_lifecycle.py)：只取发言者获准Observation/本人快照，当前状态优先，同次获准终态替代召回开始，不补造结果。 |
| 相遇/共同休闲 | 设置角色活动，聊天自然提及 | [character_encounters.py](services/core/src/livingworld/application/character_encounters.py)、`encounter_policy.py`、[shared_activities.py](services/core/src/livingworld/application/shared_activities.py)、`persistence/shared_activity_authority.py`：同场/实际活动/授权核验、冷却/持续同场去重，原子事件/Observation/幂等回执；0033/0034。 |
| 在线/双人主动联系、未回复门禁 | `ProactiveContactSettings.tsx`，私聊/固定双人群 | [proactive_contact.py](services/core/src/livingworld/application/proactive_contact.py)、`persistence/proactive_contact.py`、[contact_gate.py](services/core/src/livingworld/infrastructure/persistence/contact_gate.py)：真实休闲理由，双人同一次共同活动/同事由；线上线下共用持久等待回复，不逐机会选人API；0035。 |
| 离线消息/托盘/自启动 | `OfflineContactSettings.tsx`、`BackgroundSettings.tsx`、`useOfflineContact.ts` | [offline_contact.py](services/core/src/livingworld/application/offline_contact.py)、`persistence/offline_contact.py`、[background.rs](apps/desktop/src-tauri/src/background.rs)：恢复达到真实离线阈值后最多一条；剧情时间另存、保留真实生成时间，首次开启不立即发；0027。关机期间不执行。 |
| 通用未读/红点 | `useChatUnread.ts`、聊天目录/底部标签 | [chat_unread.py](services/core/src/livingworld/infrastructure/persistence/chat_unread.py)、`proactive_contact.py` HTTP：对已加载且前台可见的消息保存单调已读位置，失败提示重试并刷新未读；阅读不解除等待回复；0035。 |
| 世界事件 | `WorldEventJournal.tsx`、`WorldNewsSettings.tsx` | [chat_event_annotations.py](services/core/src/livingworld/application/chat_event_annotations.py)、[world_story.py](services/core/src/livingworld/application/world_story.py)/对应persistence：条件邀约同次取原句，主动邀请送达时记录；亲历独立展示；公共动态10条入池、最多5条进行中，绿灰补位、8/10续批；0028。 |
| 阵营/头像/人物网 | `ContactSocial.tsx`、`RelationshipUniverse.tsx`；聊天`useChatAvatars.ts` | [factions.py](services/core/src/livingworld/infrastructure/persistence/factions.py)、`adapters/http/factions.py`：直接成员多重归属、同阵营持久相识、父子不继承；头像本地资产、3d-force-graph/Three.js真三维拾取/相机/漂浮，聊天/Director使用有界相识输入；0036。 |
| Logo、启动/界面材质 | `Brand.tsx`、`StartupSplash.tsx`、`celestialVortex.ts`、`world-terminal.css` | 前台首帧至少1.5秒且Core/书架真实就绪后交接；Three.js真实纵深，隐藏后台停渲染、静态/错误回退；0.1.37观星室四页及双天体星轨；0.1.37视觉切片未改Core，本轮维护另见第6节。 |
| Kernel/知识/持久化基础 | 普通功能经应用接线；开发Inspector独立 | [command_handler.py](services/core/src/livingworld/application/command_handler.py)、`action_resolution.py`、`ledger.py`/`replay.py`、`domain/knowledge.py`、`application/memory.py`、`persistence/unit_of_work.py`：CAS/幂等/事务事件、投影重建、owner授权Observation/EpisodicMemory；不是普通聊天自动写Truth。 |
| 内容包/外部导出基础 | 核心已有能力，不能推定完整用户备份UI | [package_service.py](services/core/src/livingworld/application/package_service.py)、`exports.py`、`infrastructure/packages/`：authored内容依赖闭包、冲突确认、`.lwcontent`及JSON导出；不是runtime存档/Checkpoint。 |

## 4. 未完成与必须保留的范围边界

### 4.1 已有能力的限制

- **记忆不是无限覆盖**：长期提示最多16条/8KiB；授权相关历史原句最多4条/8KiB；持久FTS5和派生历史向量分页，移除当前聊天的最近8192引用截止；每通道补齐页64条、向量页512条，每次最多128新编码；历史扫描及候选工作各有3秒等待，超时/冷索引部分覆盖，DiskCache目标256MiB仍为加速缓存。自动同次提取可漏记。停用/纠正不删除原聊天或当前短期上下文。
- **亲历不是全知**：本人近期最多6条/6KiB；亲历从近128条获准观察选最多12条/8KiB。同次终态只能从已有授权窗口关联；只见开始者不能获得隐藏结束。普通自述、摘要、计划与WorldTruth/EpisodicMemory分开。
- **公共不等于本次触发**：背景仍须enabled、提供条件/关键词/容量。聊天、日常和动态池各用自己的场景；范围数量不能证明当次有材料。活动开始/结束、公开动态和手动“经历”不认证任务成果/传闻真值。
- **主动联系不保证一开就发**：合法实际休闲/许可/间隔/计划/门禁同时满足；双人须同一真实共同休闲、同一邀请目的。所有角色共享未回复限制，阅读/开关/重启不能释放；只在收到联系的会话回复才解锁。
- **节奏固定**：Director常规6小时批次；原批至少2条且50%日常失效才提前重规划。每批问候+共同开始合计最多2次，首次见面每角色24世界小时最多一个新对象；共同开始每角色24小时一次，同对6小时冷却、15～30世界分钟。
- **本地运行有限**：退出/关机不调用API；托盘仍运行不等于离线。恢复不补造错过的移动/相遇/共同成果。WorldTime是整数微秒逻辑时间，UTC是真实时间，不能隐式互换。
- **模型兼容有限**：四类adapter和同次事件／记忆接线已有；原生能力需具体模型确认，未知型号/代理及各厂商效果未全面验收。Claude/Gemini继续可信容量预留；聊天所有选人/回复/retry共用上限。资料/后台有独立预算，失败不自动付费重放。

### 4.2 真正尚未实现

| 方向 | 已有基础 | 尚缺什么/授权状态 |
| --- | --- | --- |
| 完整离线演化 | UTC bridge、到期调度、单条离线消息 | 关机期间角色生活/社交/结果的完整重建；尚无完整批准契约。 |
| 更广剧情/关系/知识传播 | Observation、阵营相识、相遇、共同休闲、权限与记忆 | 不是完整自主剧情；没有自动关系成长、正式介绍流程或通用逐角色秘密/传闻传播产品闭环。 |
| 更广共同联系 | 同事由双人真实共同休闲已实现 | 三人以上、未来尚未开始的活动、任意新行动需独立契约；不能混合不同目的。 |
| 完整World Builder/来源更新 | 单卡/书摘要研究、证据、草稿确认 | 一键构建可运行世界、全文核验、持续来源更新。 |
| Runtime世界备份/分支 | ledger/replay、authored内容包 | 普通用户完整Checkpoint/Timeline Branch/`.lworld`保存恢复未实现；内容包不是存档备份。 |
| Director风格管理 | 批量日常与社交子集 | 完整参数/风格管理的产品行为未冻结。 |
| 正式发行 | Windows便携包 | 最新版整体验收、性能/兼容结论、签名安装/自动更新；体验版按用户明确授权发布，不自动推定稳定发行。 |

共同委托/巡查、奖励/战斗不是以上愿景的默认实现方法；用户已明确否定自行添加。完整SillyTavern行为兼容也未实现，现有卡/书格式兼容不等于概率/递归/脚本等全兼容。

## 5. 接下来从哪一步继续

1. **先接收0.1.42模型适配体验**：四类服务普通／流式私聊与群聊、同次事件／记忆、超时／原生能力保存读回与严格额度提示。0.1.41地点优化验收继续：多层包含、父节点停留与返回、隐藏祖先逐角色开放、锁定立即返回、头像／右侧初始－当前位置、严格同地点相遇。原0.1.40反馈验收范围继续保持：通讯录资料／阵营主区是否更宽高；条件邀约是否保留条件；亲历记录是否易区分；动态先5条、处理2条补2条，绿灰历史与旧版过量记录是否有序。保留0.1.39长历史验收范围及原视觉／草稿／未读边界。没有新反馈时不要把已有实现重新登记为未完成代码。
2. **验收尚未确认的关键链路**（共同联系目前由用户先等待，不主动触发或排查）：记忆纠正/停用和旧事召回、活动真实终态/权限、动态池公共背景→生成→逐条发布→标记、在线单人/双人同事由→等待回复→原会话回复→合法下次机会、离线联动。主动联系失败先查保存状态/前提/终端原因，不靠反复开关或自动重放API排查。
3. **只按证据修复**：记录现象、版本、受影响模块和可观察完成条件；新功能先调查成熟实现并确认新增范围。用户仍负责测试；未获新许可不运行自动测试、GUI smoke、真实存档/模型诊断。
4. **新方向先讨论**：将4.2中的愿景与当前功能验收分开；0.1.42已获本轮公开预发布授权，后续版本发行仍须相应批准。现在没有等待补写的共同委托，也没有需要重新搭建的记忆底座。

各功能操作/验收手册： [聊天恢复](docs/CHAT_FUNCTIONAL_EXPERIENCE.md)、[记忆与上下文](docs/CONTEXT_AND_RECALL.md)、[经历终态](docs/EXPERIENCE_STATE_RECALL.md)、[日常](docs/DIRECTOR_ACTIVITIES.md)、[相遇](docs/CHARACTER_ENCOUNTERS.md)、[共同休闲](docs/SHARED_LEISURE.md)、[主动联系](docs/PROACTIVE_CONTACT.md)、[离线消息](docs/OFFLINE_MESSAGES.md)、[事件](docs/WORLD_EVENT_JOURNAL.md)、[阵营](docs/CHARACTER_FACTIONS.md)、[启动](docs/CELESTIAL_STARTUP.md)。

## 6. 交付与证据

### 当前模型适配（2026-10-08，Desktop0.1.42）

- 四类服务同次事件／记忆、厂商wire schema副本、超时／原生能力保存与严格额度说明完成；用户明确保留可信容量硬上限。具体代码、研究、检查与待验收见[适配记录](docs/maintenance/2026-10-08-provider-compatibility.md)。
- build-only退出0，EXE文件／产品版本均0.1.42；入口providers-0142，旧包保留。ESLint／TypeScript、修改Python的Ruff／格式／AST、Rust格式和版本核对通过；未运行自动测试、应用、真实模型或迁移；适配构建结束时尚未提交／推送／发布，本轮公开交付状态见发布记录。

### 前序体验反馈修复（2026-10-07，Desktop0.1.40）

- 用户确认三次薇薇安主动联系之间均在原会话回复；没有未回复门禁失效证据。在线共同活动优先／批内稳定排序、离线模型按资料理由选人均无轮换保证，具体存档入选原因未读取确认；未修改选人或共同联系条件。
- 通讯录压缩重复标题与操作区，桌面名单220px，资料／阵营主区前移并减少头像留白。条件邀约提示明确保留条件；在线邀请与离线`invite_chat`同事务保存原话，无新增API。亲历记录独立；用户所贴四条同文休息开始时间不同，不能按文案删除不同事实。
- 用户确认世界动态最多5条进行中／绿灰补位／红占位；Kernel按可用时间有界补位，旧已发布记录保留并依次展示，历史折叠，8/10续批／费用／知识权限不变。暂无新迁移。
- 实际检查／交付证据与完成条件见[本轮维护记录](docs/maintenance/2026-10-07-experience-feedback.md)，用户仍负责运行验收。
- build-only退出0，EXE文件／产品版本均0.1.40；ESLint／TypeScript、Ruff、5个Python格式／AST、3个SELECT源码编译、349条CSS规则解析与868个本地文档目标0断链通过。日志／告警与最终ZIP清单见维护记录；没有产品运行／迁移／模型／测试结论。

### 前一步长历史改进（2026-10-07，Desktop0.1.39）

- 用户批准三项改进，复用现有组件：持久全文索引、历史向量分页召回、200条页面窗口及返回最新。没有增加付费API/自动摘要，也没有触发共同联系。
- 0037只新增派生表/FTS5/触发器，保留源授权和纠正/停用；冷索引逐步建立并保留关键词回退。没有实际运行迁移、测试、模型或应用。
- ESLint/type、Ruff、7个Python格式/AST、SQLite DDL/SELECT源码编译、Git差异与858个本地文档目标/0断链通过。build-only退出0，EXE版本0.1.39，旧包保留；大chunk/可选依赖/弃用告警见记录。
- 检查、构建及入口详见[长历史维护记录](docs/maintenance/2026-10-07-long-history-recall.md)；源码未提交或公开。0.1.38与公开0.1.37保持原快照。

### 前一步文档/代码维护（2026-10-07，Desktop0.1.38）

- 基线`4d280cc`；原文档/代码维护完成后，按用户新入口要求将Desktop及对应锁文件改为0.1.38，在独立目录完成build-only打包。API协议、schema、用户存档和启动注册不改；未提交、推送或公开发布。
- 共同联系已有实现，用户尚未收到消息，明确先等待并自行验收；未触发联系、放宽条件或补造故障结论。
- ESLint/TypeScript、Ruff源码及18个改动Python格式、CSS解析和Web编译通过；仓库文档841个本地目标/0断链，独立文档打包499个/0断链。全仓格式有一条未修改主动联系文件的既有行尾告警，Web有大chunk告警；具体变化/检查及剩余维护项见[维护记录](docs/maintenance/2026-10-07-code-and-docs.md)。
- 原公开Release ZIP保留原样，本轮修正文档与后续打包脚本不意味着原ZIP断链已替换。
- 构建命令：`.\.venv\Scripts\python.exe scripts\build-portable.py --build-only --output-name maintenance-0138`，退出码0；Core重新冻结，Desktop release编译完成，没有执行脚本中的smoke分支。EXE FileVersion/ProductVersion均为0.1.38；Desktop SHA256 `573e06c24222a04bbc5ce86fe79fd6fdd4a391a2c9b5ce51966a95f387e8be57`，Core SHA256 `9d483c18acfe90d27cc72a655d90f45281dcddc723b5ab1fee6ab78460cf2028`。
- 新入口位于`artifacts/portable/maintenance-0138/dreamtalk/dreamtalk-desktop.exe`，完整ZIP为`artifacts/portable/maintenance-0138/dreamtalk.zip`。构建结束后同步本轮最终交接/状态与便携说明，再重新压缩文档；哈希/文件清单记录在`artifacts/maintenance-0138-build.json`（ignored）。随包源码链接仍以Git基线为准，未提交的新文件远程链接可能不可用，不以本地打包推定其已公开。
- 本轮构建告警：主JS chunk716.04kB、Three.js587.98kB、关系网817.51kB；STATIC_VCRUNTIME弃用；PyInstaller可选hidden import缺少tzdata/pysqlite2/MySQLdb及jieba转义SyntaxWarning。构建成功不代表这些运行路径已验收。

### 历史0.1.37观星室（2026-10-05）

- 实现基于`b2bc430`，公开源码以`v0.1.37`标签定位；Desktop版本0.1.37；无Core/API/迁移改动，无新依赖，原Logo字节未改。
- 本轮`npm run lint`（ESLint/TypeScript）通过；CSS静态解析世界内346条/启动40条规则；10组代表性配色计算最低5.60:1。这不是渲染验证、全页面对比度认证或用户验收。
- build-only完成：`.\.venv\Scripts\python.exe scripts\build-portable.py --build-only --output-name observatory-0137`。常规npm/uv入口因本机uv缓存目录拒绝访问未开始构建；改用已安装PyInstaller6.22.3的仓库虚拟环境调用同一脚本完成。没有修改构建脚本、安装依赖或绕开build-only。
- 独立便携目录`artifacts/portable/observatory-0137/dreamtalk`与同级ZIP已生成，EXE FileVersion/ProductVersion均为0.1.37。Desktop SHA256 `87fc2f6f23b8c18d06b0f6c24caad61bbbf52de8c0b7fb198a86d92ff46674aa`；Core SHA256 `2d7bc064f1af15e7525108e4465bb492ea89e308889e95b8c9e152f3a43baa94`，与0.1.36记录一致。最终ZIP/源码/资产清单在`artifacts/observatory-source-audit.json`（ignored）。
- 本轮文档链接751个本地目标/0断链；Git差异格式无错误，Git提示部分text=auto文件在后续操作时转换CRLF。包内docs在构建结束后同步本轮最终交付说明并重新压缩，仅影响这个新包。
- 构建非阻塞告警：主chunk717.72kB、Three.js587.98kB、关系网817.51kB；STATIC_VCRUNTIME弃用；PyInstaller缺少tzdata/pysqlite2/MySQLdb的hidden import及jieba转义SyntaxWarning。未据此新增依赖，也未宣称运行兼容通过。
- 未运行自动测试、GUI smoke、模型、真实存档或迁移；未更改系统启动注册。构建/运行/用户接受分别记录。
- 设计方案和验收入口：[世界内界面](docs/WORLD_TERMINAL.md)、[启动](docs/CELESTIAL_STARTUP.md)、[成品复用](docs/research/2026-10-05-observatory-design.md)。

### 已完成公开体验发布（2026-10-07恢复完成）

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
