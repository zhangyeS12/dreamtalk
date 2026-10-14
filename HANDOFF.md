# dreamtalk 工作交接

更新日期：**2026-10-14**。公开基线Desktop **0.1.76**／发行源码fcd2a05，API1、迁移head0050_sticker_library_freshness、配音revision7。配音、表情与聊天图片大更新已发布，完整Windows安装包／便携ZIP与原update-preview清单已完成静态及匿名下载核对，见[记录](docs/maintenance/2026-10-14-major-release.md)。用户已确认角色发表情、新增公共表情识别及此前本地配音的具体效果；免费云端最新版、付费API和其他运行／升级场景仍待确认。

前轮用户已明确授权四次最近失败案例的本机GPT对照，读取范围仅该台词／参考录音；未生成WAV、不试听／转写／外发或改存档。前轮诊断后原0.1.67服务已经恢复；该反馈更新轮仅整理文档；此前表情首版未启动应用、运行配音修复器或调用模型。详见[修复记录](docs/maintenance/2026-10-13-speech-candidate-sampling-fix.md)。 已有0.1.68包继续保留原交付快照，0.1.70另建产物，不覆盖旧包。

## 1. 五分钟了解当前完成度

**项目已有可运行的 Windows 便携版，主要功能链路已实现；当前处于产品体验与验收阶段，尚未达到完整产品发行状态。** 原始愿景尚有缺口，也没有最新版整体验收结论；不编造一个缺少验收分母的完成百分比。

| 分类 | 当前事实 | 接手时的处理 |
| --- | --- | --- |
| 已实现并交付代码/包 | 世界书架与封面、资料创作／导入／联网生成、身份、私聊／群聊／流式、模型／额度／恢复、记忆／检索、事件、活动／相遇／共同休闲、主动联系、阵营／头像／人物网、层级地点与移动；新增角色轮换、群聊解散、世界删除、资料及聊天导出、阵营联系选择与社交上下文改进。 | 0.1.49～0.1.52 已公开；0.1.53 本次发布基线，按标签核对交付，不重新列为待开发。 |
| 有明确使用反馈 | 2026-10-14用户确认可以发表情；2026-10-13用户在0.1.68交付后反馈本地配音效果良好；用户报告卡/书生成、单聊、群聊@及无@正常，认可循环书架；0.1.23连接卡顿和0.1.30已读红点问题获确认解决。2026-10-07本轮CCv2角色卡与World Info JSON世界书外部导入获用户确认通过。 | 反馈只覆盖当次功能／资料，不代表最新版全量通过。 |
| 已实现、待最新版验收 | 新增三库表情、媒体附件、可设频率与一次搜索、可选图片分析；配音三路线、六小时缓存、独立候选试听替换、一键服务修复；本地效果已有本次用户确认。 | 免费云端最新版和付费API未测试、待确认；缓存、替换、修复及其他场景不推定全通过。 |
| 尚未实现的愿景 | 完整离线演化、更广剧情/关系/知识演化、一键构建完整运行世界/持续资料更新、Checkpoint/Timeline Branch及runtime世界备份。 | 详见第4节。未冻结的产品行为须先讨论，不是默认下一步授权。 |
| 发行未完成 | 当前发布基线为 0.1.53，前序 0.1.52 已公开；正式稳定版和新版完整运行验收尚未完成。 | 全面更新仍按预发布交付，不推定稳定。 |
| 范围规则 | 只推进已批准需求和有证据的修复。 | 不从历史建议、领域类名或“继续推进”推导新授权。 |

**最近进展：** v0.1.76大更新已公开；三库、附件、联网／可选分析、不限表情频率、六小时配音缓存、重新配音试听替换和一键服务修复纳入完整安装／便携发布。签名安装器只解包核对，匿名下载摘要与本机资产相同；未运行测试／模型／安装器或修改真实存档，见[发布记录](docs/maintenance/2026-10-14-major-release.md)。

## 2. 仓库、运行和版本现场

**本机直接体验入口：** 发布便携包为`artifacts/portable/major-0176/dreamtalk/dreamtalk-desktop.exe`，也可使用GitHub安装包。先退出旧程序，再打开完整新版；打包核对不代表已运行此包。原源码体验入口apps/desktop/src-tauri/target/debug/dreamtalk-desktop.exe保留。部署的配音／视觉环境和权重仍独立，不随分发包提供。

自2026-10-13起，用户要求除明确获准发布到GitHub外，不再在本机打包；便携包、安装器、ZIP及`--build-only`打包均适用。日常继续源码、差异、格式／lint／类型、文档链接及必要编译核对。本轮打包计划已取消，不再等待此前格式／打包合并请求的批准；没有新增发布、测试、模型或真实存档操作授权。长期规则见[AGENTS第20节](AGENTS.md#20-current-verification-responsibility)。

用户追加授权本机视觉模型部署：独立环境与模型存放在Git忽略的artifacts/image-runtime，手动启动且只监听本机；完整模型已按官方SHA256核验并接入，服务0.40.3和模型vision能力元数据已核对；设置填写方式及部署证据见[部署记录](docs/maintenance/2026-10-13-local-image-model-deployment.md)。不重打应用包、不改版本或真实设置，0.1.70包内文档保留原快照；图片效果由用户验收。

| 项 | 当前证据与范围 |
| --- | --- |
| 正式仓库 | `D:\LivingWorld`；临时目录与正式源码分开，保留全部既有未提交改动。 |
| 分支／提交 | codex/world-archive与main已快进同步；v0.1.76发行源码为fcd2a058a5c0d5840821d1f6568a28e61ae20f9d。发布完成记录的后续文档提交不改变发行代码／标签，当前Git HEAD以实际仓库为准。 |
| 应用／协议 | Desktop及锁文件0.1.76，Core／Web仍0.1.0，API1、推理revision7。完整Windows发行资产已编译、签名并公开；工程端没有启动产物或调用模型验收。 |
| 迁移 | 源码head0050_sticker_library_freshness，公开0.1.53为0044；本轮获准只读当前存档版本亦为0050。0050仅追加可空导入UTC，0049回执来源列兼容保持，本轮无新增迁移／存档写入。 |
| 最新本地包 | 0.1.76完整便携目录artifacts/portable/major-0176/dreamtalk、同级dreamtalk.zip；完整签名安装器在artifacts/installers/major-0176。旧0.1.70及以前包保持，本轮没有清理或改写。 |
| GitHub | [v0.1.76大更新](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.76)为预发布，六项下载资产已核对；原update-preview的windows.json已更新到0.1.76。main／开发分支已同步，不改变仓库公开状态、频道说明或旧版本附件。 |
| 模型环境 | Git忽略的artifacts/voice-runtime/index-tts，独立Python3.11.9／torch2.8.0+cu128；不进入Core或安装包。服务自动启动的路径配置在本机，模型首次任务才加载。 |
| 数据／系统入口 | identifier保持app.livingworld.desktop。最新授权仅最近回复对应世界的表情元数据只读诊断；未读取聊天／说明正文／原图、未修改存档或系统入口。已识别Codex MSIX旧副本重定向，固定读取器使用已核对桌面上下文；不移动／删除DB或WAL。历史配音对照许可不复用。 |

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
| 角色配音 | 设置“角色配音”、通讯录“角色音色”、消息播放／停止／重新配音、下方试听和替换选择；SpeechSettings／CharacterVoice／SpeechPlayback | speech.py → speech_providers.py → 独立serve-indextts.py → Store／播放器；0045音色、0046缓存、0047候选。Tauri监督服务／保管凭据；任务沿UpdateMaintenance治理。见[手册](docs/CHARACTER_VOICES.md)与[本轮记录](docs/maintenance/2026-10-12-speech-regenerate-preview.md)。 |
| 世界、身份、时钟 | `ProductApp.tsx`、`ProfileEditor.tsx`，设置时间/“我” | [world_settings.py](services/core/src/livingworld/application/world_settings.py)、`player_onboarding.py`、`local_profile.py`、`simulation_clock.py`：世界隔离、绑定Player、从家进入，通用/世界描述与暂停/倍率。 |
| 书架/封面 | `WorldArchivePage.tsx`、`WorldShelf.tsx`、`WorldCoverEditor.tsx`、`BookFaces.tsx` | [world_covers.py](services/core/src/livingworld/application/world_covers.py)、`infrastructure/persistence/world_covers.py`：Embla循环至少12位/空白创建；本地三面图/文字标题、资产校验和裁剪；0030。 |
| 卡/书创建、编辑、导入、联网生成 | 通讯录`WorldContent.tsx`/`ContentEditor.tsx`管理角色，书架管理世界书 | [content_builder.py](services/core/src/livingworld/application/content_builder.py)、`content_authoring.py`、`infrastructure/content_research.py`、`infrastructure/imports/`、`persistence/world_content.py`：检索摘要/证据/冲突→可编辑草稿→预览确认→世界内容；0023。 |
| 公共背景 | `WorldContent.tsx`、`PublicBackgroundReadiness.tsx` | [lore_activation.py](services/core/src/livingworld/application/lore_activation.py)：逐条公开且enabled，再按场景、常驻/关键词/次级条件及容量筛选。未变条目编辑保留范围，新增/修改重新确认；0022。 |
| 私聊/群聊/流式/分页 | `ChatTranscript.tsx`、`GroupChat.tsx`、`useReplyStream.ts`、`useTranscriptPages.ts` | [chat_reply.py](services/core/src/livingworld/application/chat_reply.py)、[group_chat_reply.py](services/core/src/livingworld/application/group_chat_reply.py)、`chat_messages.py`、`chat_conversations.py`：持久回合、一次认领、校验后提交；唯一@选下一位，无@独立调度；0018～0021。 |
| 模型、额度、费用、失败恢复 | `ModelSetup.tsx`、`ReplyRecoveryControls.tsx`、`ContextReferencePanel.tsx` | [chat_capacity.py](services/core/src/livingworld/application/chat_capacity.py)、`llm_execution.py`、`llm_preflight.py`、`llm_budget.py`、`persistence/chat_reply_recovery.py`/`chat_context_report.py`：可信容量裁剪、整尝试预算/账本、显式独立新attempt；0031/0032。四类adapter、wire转换在`infrastructure/llm/`，同次附带接线在`bootstrap/llm_runtime.py`，设置序列化在Tauri`llm_config.rs`；0.1.42不新增估算准入。0.1.43按请求／任务世界选快照，`world_model_config.py`＋`production_config.py`／`llm_runtime.py`接线默认及覆盖；Tauri命令增加可选世界与恢复默认。 |
| 长短期记忆/本地RAG/来源 | `LongChatMemoryPanel.tsx`、`ChatHistoryPanel.tsx`、`ConversationMemoryPanel.tsx`、`SourceMessageDialog.tsx` | [long_chat_memory.py](services/core/src/livingworld/infrastructure/persistence/long_chat_memory.py)、[chat_context.py](services/core/src/livingworld/application/chat_context.py)/`group_chat_context.py`、`conversation_memory.py`、[semantic_chat_retrieval.py](services/core/src/livingworld/infrastructure/semantic_chat_retrieval.py)、`chat_retrieval.py`/`local_vector_cache.py`：同次提取、纠正/停用、权限过滤后jieba/FTS5/BM25+BGE融合及DiskCache；SQLite持久全文/向量派生索引；摘要单独预览确认；0024/0029/0037。 |
| 日常/地点/活动生命周期 | 通讯录`LocationWorkspace.tsx`；设置`WorldActivities.tsx` | [director.py](services/core/src/livingworld/application/director.py)、`routine_lifecycle.py`、`character_activity_context.py`、`infrastructure/scheduler_runtime.py`：6小时批量提案，Kernel执行真实移动/休息/工作/自由活动及开始/结束/中断；0025/0026/0038/0039。共同准入见`location_rules.py`，全部角色有限批次随机轮换见 persistence/director.py（0041）；地点总量不限制、同父名称唯一见 world_locations.py（0044）。纯移动选择与持久门禁分别见application及persistence的`character_mobility.py`，Director claim保存路线、Kernel提交真实到达。本地维护改为单次分类，地点页串行轮询并复用未变化快照。 |
| 聊天参考本人近况/亲历 | 聊天“本次参考内容”，自然回复 | [observed_events.py](services/core/src/livingworld/infrastructure/persistence/observed_events.py)、[experience_lifecycle.py](services/core/src/livingworld/application/experience_lifecycle.py)：只取发言者获准Observation/本人快照，当前状态优先，同次获准终态替代召回开始，不补造结果。 |
| 相遇/共同休闲 | 设置角色活动，聊天自然提及 | [character_encounters.py](services/core/src/livingworld/application/character_encounters.py)、`encounter_policy.py`、[shared_activities.py](services/core/src/livingworld/application/shared_activities.py)、`persistence/shared_activity_authority.py`：同场/实际活动/授权核验、冷却/持续同场去重，原子事件/Observation/幂等回执；0033/0034。 |
| 在线/双人主动联系、未回复门禁 | `ProactiveContactSettings.tsx`，私聊/固定双人群 | [proactive_contact.py](services/core/src/livingworld/application/proactive_contact.py)、`persistence/proactive_contact.py`、[contact_gate.py](services/core/src/livingworld/infrastructure/persistence/contact_gate.py)：真实休闲理由，双人同一次共同活动/同事由；线上线下共用持久等待回复，不逐机会选人API；0035。 |
| 离线消息/托盘/自启动 | `OfflineContactSettings.tsx`、`BackgroundSettings.tsx`、`useOfflineContact.ts` | [offline_contact.py](services/core/src/livingworld/application/offline_contact.py)、`persistence/offline_contact.py`、[background.rs](apps/desktop/src-tauri/src/background.rs)：恢复达到真实离线阈值后最多一条；剧情时间另存、保留真实生成时间，首次开启不立即发；0027。关机期间不执行。 |
| 通用未读/红点 | `useChatUnread.ts`、聊天目录/底部标签 | [chat_unread.py](services/core/src/livingworld/infrastructure/persistence/chat_unread.py)、`proactive_contact.py` HTTP：对已加载且前台可见的消息保存单调已读位置，失败提示重试并刷新未读；阅读不解除等待回复；0035。 |
| 世界事件 | `WorldEventJournal.tsx`、`WorldNewsSettings.tsx` | [chat_event_annotations.py](services/core/src/livingworld/application/chat_event_annotations.py)、[world_story.py](services/core/src/livingworld/application/world_story.py)/对应persistence：条件邀约同次取原句，主动邀请送达时记录；亲历独立展示；公共动态10条入池、最多5条进行中，绿灰补位、8/10续批；0028。 |
| 阵营/头像/人物网 | `ContactSocial.tsx`、`RelationshipUniverse.tsx`；聊天`useChatAvatars.ts` | [factions.py](services/core/src/livingworld/infrastructure/persistence/factions.py)、`adapters/http/factions.py`：直接成员多重归属、相识来源区分、退出可选择切断／保留，真实相遇和其他共享阵营保护；父子不继承；头像本地资产、3d-force-graph/Three.js真三维拾取/相机/漂浮，聊天/Director使用有界相识输入；0036。 |
| Logo、启动/界面材质 | `Brand.tsx`、`StartupSplash.tsx`、`celestialVortex.ts`、`world-terminal.css` | 前台首帧至少1.5秒且Core/书架真实就绪后交接；Three.js真实纵深，隐藏后台停渲染、静态/错误回退；0.1.37观星室四页及双天体星轨；0.1.37视觉切片未改Core，本轮维护另见第6节。 |
| Kernel/知识/持久化基础 | 普通功能经应用接线；开发Inspector独立 | [command_handler.py](services/core/src/livingworld/application/command_handler.py)、`action_resolution.py`、`ledger.py`/`replay.py`、`domain/knowledge.py`、`application/memory.py`、`persistence/unit_of_work.py`：CAS/幂等/事务事件、投影重建、owner授权Observation/EpisodicMemory；不是普通聊天自动写Truth。 |
| Windows应用更新 | [使用说明](docs/WINDOWS_UPDATES.md) | `DesktopUpdates.tsx` → Rust `updater.rs` → Core `update_maintenance.py`；完整资源由 `build-installer.py`／NSIS hooks交付，`updater-signing.ps1`仅保管发布私钥。版本Release和update-preview频道须另获发布授权；旧无清单包需一次手动安装。 |
| 内容包/外部导出基础 | 资料管理导出／会话菜单；`FileExportDialog.tsx` | [world_content_export.py](services/core/src/livingworld/application/world_content_export.py)、[chat_export.py](services/core/src/livingworld/application/chat_export.py)、[file_exports.py](services/core/src/livingworld/adapters/http/file_exports.py)：角色 V2/V3 JSON、World Info JSON、完整已保存聊天 TXT/JSON，桌面另存为。旧 `.lwcontent` 基础继续存在；导出不是运行世界备份，不含运行状态／头像包，聊天无导入 UI。 |

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
| Runtime世界备份/分支 | ledger/replay、authored内容包、资料／聊天导出 | 普通用户完整Checkpoint/Timeline Branch/`.lworld`保存恢复未实现；内容包不是存档备份。 |
| Director风格管理 | 批量日常与社交子集 | 完整参数/风格管理的产品行为未冻结。 |
| 正式发行 | Windows便携包 | 最新版整体验收、性能/兼容结论、签名更新的频道部署／跨版验收；体验版按用户明确授权发布，不自动推定稳定发行。 |

完整SillyTavern行为兼容也未实现，现有卡/书格式兼容不等于概率/递归/脚本等全兼容。

## 5. 接下来从哪一步继续

0. **配音按路线维护验收状态**：本地效果已有2026-10-13用户确认；免费云端最新版和付费API尚未测试、待确认。其他缓存／试听替换／服务修复场景仍由用户验收。前轮四次GPT对照许可已经用完，不自动新增模型或付费服务调用；见[当前手册](docs/CHARACTER_VOICES.md)。

1. **继续验收0.1.76正式下载与升级**：确认完整安装／便携包的Core、设置、0050旧存档升级、缓存／试听替换／服务修复及模型效果；云端免费／付费配音仍待确认。继承地点、阵营、记忆、世界动态、后台与权限等未确认场景，不由发布完成代替验收。工程端不运行产品、模型或真实迁移。
2. **验收尚未确认的关键链路**（共同联系目前由用户先等待，不主动触发或排查）：记忆纠正/停用和旧事召回、活动真实终态/权限、动态池公共背景→生成→逐条发布→标记、在线单人/双人同事由→等待回复→原会话回复→合法下次机会、离线联动。主动联系失败先查保存状态/前提/终端原因，不靠反复开关或自动重放API排查。
3. **只按证据修复**：记录现象、版本、受影响模块和可观察完成条件；新功能先调查成熟实现并确认新增范围。用户仍负责测试；未获新许可不运行自动测试、GUI smoke、真实存档/模型诊断。
4. **新方向先讨论**：将4.2中的愿景与当前功能验收分开；0.1.53已获本轮全面预发布授权，未来发行仍须相应批准。已有记忆底座不需要重新搭建。

各功能操作/验收手册： [聊天恢复](docs/CHAT_FUNCTIONAL_EXPERIENCE.md)、[记忆与上下文](docs/CONTEXT_AND_RECALL.md)、[经历终态](docs/EXPERIENCE_STATE_RECALL.md)、[日常](docs/DIRECTOR_ACTIVITIES.md)、[相遇](docs/CHARACTER_ENCOUNTERS.md)、[共同休闲](docs/SHARED_LEISURE.md)、[主动联系](docs/PROACTIVE_CONTACT.md)、[离线消息](docs/OFFLINE_MESSAGES.md)、[事件](docs/WORLD_EVENT_JOURNAL.md)、[阵营](docs/CHARACTER_FACTIONS.md)、[启动](docs/CELESTIAL_STARTUP.md)。

## 6. 交付与证据

### 当前媒体接口修复（Desktop 0.1.70）

用户反馈设置读取失败；源码确认0.1.69媒体router漏了API前缀，已统一修正设置、表情库、图片和显式分析入口，并补充加载状态及具体错误提示。无新迁移、依赖或模型调用；检查与独立便携包见[本轮记录](docs/maintenance/2026-10-13-chat-media-settings-route-fix.md)。实际设置读取／保存、导入和图片显示仍待用户验收。

### 当前本地配音（Desktop 0.1.68）

原参考的3个独立采样候选在受限GPT对照中均正常结束；源码已改为三候选采样和完成候选评分，保持原参考、BF16、最大容量及整段规则。源码／格式核对通过，build-only退出0，285份Core源码与桥接／帮助程序逐字节一致；最终包摘要见artifacts/voices-0168-delivery.json。四次模型对照仅到GPT返回；用户随后确认本次本地效果良好，免费云端和付费API待确认，其他流程不推定全部通过；原0.1.67服务已恢复，临时台词／参考文件已删除。见[本轮修复](docs/maintenance/2026-10-13-speech-candidate-sampling-fix.md)。未提交或发布。

### 前轮本地配音（Desktop 0.1.67）

源码／Ruff／格式／AST、前端ESLint／TypeScript及Rust格式核对通过；build-only退出0。设置内一键修复与受控服务更新见[本轮记录](docs/maintenance/2026-10-13-local-speech-one-click-repair.md)；未运行修复器、服务、模型、测试或真实迁移。

### 前轮本地配音（Desktop 0.1.66）

源码／Ruff／格式／AST、前端ESLint／TypeScript及Rust格式核对通过；build-only退出0。参考编码复用、解码数值日志及失败提示见[本轮记录](docs/maintenance/2026-10-13-speech-reference-cache-fix.md)；未运行模型、声音、测试或真实迁移。

### 前轮本地配音（Desktop 0.1.65）

源码／Ruff／格式／AST、前端ESLint／TypeScript及Rust格式核对通过；build-only退出0。新增重新配音候选、下方试听与播放结束后替换／保留，六小时保存期限保持。本轮没有运行应用、模型、声音、测试或真实迁移，见[本轮记录](docs/maintenance/2026-10-12-speech-regenerate-preview.md)。

### 前轮本地配音（Desktop 0.1.64）

手动缓存数值诊断与实际播放时钟已build-only交付，实际音频仍未取得，见[原轮记录](docs/maintenance/2026-10-12-speech-signal-diagnostics.md)。

### 前轮本地配音（Desktop 0.1.63）

源码／Ruff／格式／AST、前端ESLint／TypeScript及Rust格式核对通过；build-only退出0。未运行模型、测试、声音或真实迁移，见[本轮记录](docs/maintenance/2026-10-12-speech-capacity-packing.md)。

用户随后在官方免费云端遇到约4分钟等待及第一句话后无声、“正在播放”仍在。只读发现960秒整体期限、全局单任务门禁、前端停止不取消后台，以及HF默认输出1500上限警告仍可保存WAV的路径；这不证明本次原因。用户允许有限音频分析，但已定位默认库没有配音表，未取得音频或执行波形分析，见[诊断](docs/maintenance/2026-10-12-free-cloud-speech-diagnosis.md)。当前包仍为原build-only快照，本轮不重打包。

### 前轮本地配音（Desktop 0.1.62）

两份Python Ruff／格式／AST、ESLint／TypeScript及Rust格式通过，完整build-only退出0；无迁移变更，未运行模型或声音。最新结果见[本轮记录](docs/maintenance/2026-10-12-speech-sentence-segmentation.md)。

### 前轮本地配音（Desktop 0.1.61）

源码／Ruff／格式、ESLint／TypeScript、Rust格式，以及10份Python AST、6条SQL和0046离线DDL编译通过，没有打开数据库或执行SQL。完整build-only退出0，EXE版本0.1.61；包内283份Core源码及桥接脚本逐字节一致，最新结果见[本轮记录](docs/maintenance/2026-10-12-speech-cache-retry.md)。

### 前轮本地配音（Desktop 0.1.60）

本轮0.1.60完成Python Ruff／格式、前端ESLint／TypeScript、Rust格式和完整build-only；282份Core源码及桥接脚本逐字节一致，EXE版本0.1.60，1283项程序清单一致。用户已确认0.1.59能够出声，但较长台词不完整、偏慢；新分段／解码和失败治理仍待验收，见[完整性修复](docs/maintenance/2026-10-12-speech-completeness-fix.md)。

前轮0.1.59完成ESLint／TypeScript、完整build-only与载荷隐私检查；EXE版本0.1.59，1282项清单逐文件一致，282份Core源码一致，新增媒体来源策略已核对存在于EXE。原消息缓存重播及声音质量由用户验收，见[播放修复记录](docs/maintenance/2026-10-12-speech-playback-fix.md)。

前轮0.1.58完成ESLint／TypeScript、Rust格式／cargo check与完整build-only；282份旁置Core源码逐字节一致，EXE版本0.1.58，构建／载荷静态隐私检查通过。完整摘要及计数见artifacts/voices-0158-delivery.json；保留已有大chunk、STATIC_VCRUNTIME弃用、jieba转义与可选依赖警告。不能把这些检查当作实际启动、推理或声音验收。

用户随后在0.1.58截图报告已生成但播放器未能启动，前端已进入播放失败阶段；本轮0.1.59修复媒体来源权限缺口，仍待用户确认真实声音与完整性。本轮只读诊断及范围清理见[记录](docs/maintenance/2026-10-12-speech-diagnosis.md)，不启动应用或模型、不生成新声音；0.1.59包内说明同步本轮交付，既有包保持原快照。原轮0.1.54～0.1.58的实现、环境、诊断与检查通过[配音接手说明](docs/maintenance/2026-10-12-speech-latency-handoff.md)索引，以下公开0.1.53及更早内容为历史证据。

本地旧包、重复发布副本与构建缓存已于2026-10-08按用户授权清理；以下旧路径、旧哈希及“保留”描述记录当时交付事实，不是当前本地入口。清理轮仅保留0.1.43；后续增加0.1.44～0.1.46，0.1.43因自启动暂留。旧工作源码压缩保护，用户数据保持；清理范围与最终核对见[清理记录](docs/maintenance/2026-10-08-local-cleanup.md)。

### 当前全面更新（Desktop 0.1.53）

该公开版源码与用户说明同版；签名完整安装／便携构建和发布已完成，随包 SOURCE_REVISION.txt 指向标签对应提交。具体检查、最终附件摘要和发布结果保存在 artifacts/release-0153；当前审查后维护不在这些旧附件中。不以源码／lint／类型、离线 DDL／SQL 编译、静态包核对代替运行或真实数据验证。

关键实现：social_context_text 与 owner 相关 SQL 投影按有效关系提供上下文；保留相遇／其他阵营依据；作者地点总量无固定上限，本地合法路线取全目录，模型仅取本批已确定地点；0044 只调整同父名称唯一，不支持毁损同名数据的降级。无新依赖或新模型调用。

### 历史更新清单修复（Desktop 0.1.48）

构建清单针对实际NSIS主程序，打包后静态解压逐文件核对；0.1.46／0.1.47严格原包修复工具只改变清单，运行时校验保持。本轮构建／发布／本机修复证据见[记录](docs/maintenance/2026-10-08-update-manifest-fix.md)。

### 前轮删除与发布交付（Desktop 0.1.47）

入口：通讯录角色资料底部／角色卡管理“当前世界已保存”的删除按钮；地点编辑“删除此地点”；编辑阵营“删除阵营”。迁移 head 0040；身份过滤、聊天只读、后续活动与联系核验统一接线。发布结果与待验收见[记录](docs/maintenance/2026-10-08-authored-deletion.md)。

### 前轮Windows更新交付（2026-10-08，Desktop0.1.46）

- 完整签名NSIS安装器`artifacts/installers/updates-0146/dreamtalk_0.1.46_x64-setup.exe`及便携`artifacts/portable/updates-0146/dreamtalk.zip`已build-only构建，具体摘要、静态文件核对、日志与告警见[本轮记录](docs/maintenance/2026-10-08-desktop-updates.md)。
- 1,224个程序文件摘要及258个Core源文件一致，随包无发布私钥；启动更新提示、静音、任务排空、安装／恢复、入口迁移及清理由用户验收。公钥已配置，发布私钥已按批准DPAPI保管，导出／导入工具未运行验收。
- 0.1.46 构建完成时未发布；后续用户明确授权随 0.1.47 发布，当前结果见删除发布记录。最终交付证据在构建后补录，包内文档仍为构建时快照。

### 前序封面缓存修复（2026-10-08，Desktop0.1.45）

- useWorldCovers在外观提交后清理不再引用的URL，保护当前显示及当前封面加载使用的digest；保存／刷新使迟到结果失效，无新依赖／数据库迁移／磁盘资产清理。
- 检查和build-only交付见[记录](docs/maintenance/2026-10-08-cover-cache.md)，频繁编辑和连续保存的运行效果待用户验收，未提交／推送／发布。

### 前序移动优化（2026-10-08，Desktop0.1.44）

- 地区标记、常驻倾向、距离衰减、本地批次路线与持久远行门禁接线完成；0039只加配置／调度状态。具体检查和完整入口见[记录](docs/maintenance/2026-10-08-character-mobility.md)，运行／升级／模型效果待用户验收，未提交／推送／发布。

### 前序世界独立模型（2026-10-08，Desktop0.1.43）

- 书架默认、世界覆盖、继承状态与恢复默认；全部生成按实际世界接线，凭据引用并集同步与按引用清理，旧v1作为默认／新增v2容器，无数据库迁移。
- 本轮lint／类型／源码检查及build-only已通过；253个Core源码逐文件一致，EXE版本0.1.43。详细证据和入口见[独立模型记录](docs/maintenance/2026-10-08-world-model-config.md)；未提交／推送／发布，不运行应用、测试、真实模型或真实存档迁移。

### 前序模型适配（2026-10-08，Desktop0.1.42）

- 四类服务同次事件／记忆、厂商wire schema副本、超时／原生能力保存与严格额度说明完成；用户明确保留可信容量硬上限。具体代码、研究、检查与待验收见[适配记录](docs/maintenance/2026-10-08-provider-compatibility.md)。
- build-only退出0，EXE文件／产品版本均0.1.42；入口providers-0142，旧包保留。ESLint／TypeScript、修改Python的Ruff／格式／AST、Rust格式和版本核对通过；未运行自动测试、应用、真实模型或迁移；适配构建结束时尚未提交／推送／发布，本轮公开交付状态见发布记录。

### 前序体验反馈修复（2026-10-07，Desktop0.1.40）

- 用户确认某角色三次主动联系之间均在原会话回复；没有未回复门禁失效证据。在线共同活动优先／批内稳定排序、离线模型按资料理由选人均无轮换保证，具体存档入选原因未读取确认；未修改选人或共同联系条件。
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

需要源码检查时使用`npm run lint`。自2026-10-13起，除明确获准GitHub发布外，不进行本机打包；必要编译可用既有`build:desktop`（调试、`--no-bundle`），不调用便携／安装器脚本。仅获准发布时使用`npm run build:portable -- --build-only`；默认打包包含自检，不得遗漏`--build-only`。用户直接体验入口为`apps/desktop/src-tauri/target/sticker-reply-0173/debug/dreamtalk-desktop.exe`，不改为启动脚本或让用户自行编译；开发入口仍为`dev:desktop`/`dev:web`/`dev:core`，UI端口1420不是Core端口。文档任务不启动这些入口，保留现有tests/CI，历史测试或单次诊断许可不授权本轮自动运行。

每次改动同步：AGENTS只记录长期规则/新决定，PROJECT_STATUS更新对应能力与验收，HANDOFF保留当前基线/现场/接续。不要追加第二个“最新”、虚报完成率或把历史包写成当前入口。用户反馈按原话/问题/版本归档；没有具体反馈不能升级为全量验收。
