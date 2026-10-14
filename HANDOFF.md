# dreamtalk 工作交接

更新日期：**2026-10-14**。当前源码Desktop **0.1.77**、API1、迁移head0051_media_frequency_kind、配音revision8，v0.1.77审查修复版已公开，发行源码e192331。当前范围、检查和发布结果见[本轮记录](docs/maintenance/2026-10-14-review-fixes-release.md)。用户前轮已确认本地配音、角色发送和新增公共表情识别；免费云端最新版／付费API及其他升级、媒体场景继续待验收。

## 1. 五分钟了解当前完成度

**项目已有可运行的 Windows 便携版，主要功能链路已实现；当前处于产品体验与验收阶段，尚未达到完整产品发行状态。** 原始愿景尚有缺口，也没有最新版整体验收结论；不编造一个缺少验收分母的完成百分比。

| 分类 | 当前事实 | 接手时的处理 |
| --- | --- | --- |
| 已实现并交付代码/包 | 世界书架与封面、资料创作／导入／联网生成、身份、私聊／群聊／流式、模型／额度／恢复、记忆／检索、事件、活动／相遇／共同休闲、主动联系、阵营／头像／人物网、层级地点与移动；新增角色轮换、群聊解散、世界删除、资料及聊天导出、阵营联系选择与社交上下文改进。 | 0.1.76大更新已公开，0.1.77为本轮审查修复，按对应标签核对交付，不重新列为待开发。 |
| 有明确使用反馈 | 2026-10-14用户确认可以发表情；2026-10-13用户在0.1.68交付后反馈本地配音效果良好；用户报告卡/书生成、单聊、群聊@及无@正常，认可循环书架；0.1.23连接卡顿和0.1.30已读红点问题获确认解决。2026-10-07本轮CCv2角色卡与World Info JSON世界书外部导入获用户确认通过。 | 反馈只覆盖当次功能／资料，不代表最新版全量通过。 |
| 已实现、待最新版验收 | 新增三库表情、媒体附件、可设频率与一次搜索、可选图片分析；配音三路线、六小时缓存、独立候选试听替换、一键服务修复；本地效果已有本次用户确认。 | 免费云端最新版和付费API未测试、待确认；缓存、替换、修复及其他场景不推定全通过。 |
| 尚未实现的愿景 | 完整离线演化、更广剧情/关系/知识演化、一键构建完整运行世界/持续资料更新、Checkpoint/Timeline Branch及runtime世界备份。 | 详见第4节。未冻结的产品行为须先讨论，不是默认下一步授权。 |
| 发行未完成 | 0.1.77预发布交付完成；正式稳定版和新版整体验收尚未完成。 | 全面更新仍按预发布交付，不推定稳定。 |
| 范围规则 | 只推进已批准需求和有证据的修复。 | 不从历史建议、领域类名或“继续推进”推导新授权。 |

**最近进展：** 0.1.77修复配音累计任务上限、媒体间隔、原图多余读取、图片凭据积累和TXT媒体导出，合并重复凭据实现并收敛文档；详细范围和证据见[本轮记录](docs/maintenance/2026-10-14-review-fixes-release.md)。

## 2. 仓库、运行和版本现场

本轮完整便携入口为artifacts/portable/review-0177/dreamtalk/dreamtalk-desktop.exe，安装器在artifacts/installers/review-0177；完整构建、静态载荷及匿名下载核对已完成，结果见本轮记录；包内文档保留发行源码准备快照，发布完成回执在main更新，不改标签或附件。源码开发体验入口保持apps/desktop/src-tauri/target/debug/dreamtalk-desktop.exe，不能把旧debug输出当作新发行版。先从托盘退出旧程序再体验；工程端不启动新产物。

| 项 | 当前事实与边界 |
| --- | --- |
| 正式仓库 | D:\LivingWorld，开发分支codex/world-archive；当前HEAD／main以Git实际状态核对。源码发布快进同步，不改写旧历史。 |
| 版本／协议 | Desktop0.1.77，Core／Web0.1.0，API1，配音revision8；既有标识app.livingworld.desktop保持。 |
| 迁移 | 源码head0051_media_frequency_kind，只追加可空发送类型；旧0050和更早形状校验保留。不读取聊天正文回填，不执行真实迁移。 |
| GitHub | 最新公开[v0.1.77](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.77)；完整安装／便携版及原update-preview频道已同版更新，不改变旧附件或频道说明。 |
| 配音／图片模型 | 独立Git忽略环境和权重，不进入Core／安装包。登记路径并保存启用配置后随dreamtalk启动，模型按需加载；已有开机后台入口使登录后运行，不是关机期间运行。 |
| 数据／系统入口 | 本轮不读取真实存档、聊天、原图或音频，不注册／修改自启动、快捷方式或进程。旧对照／元数据读取许可不复用。 |
| 检查责任 | 用户负责测试和最终验收；日常不打包，本次GitHub发布为具体例外，仅--build-only和静态载荷核对。 |

不要覆盖其他任务改动，不强推、不移动或删除DB/WAL，不以旧EXE打开已经升级的存档。源码head、包版本和实际运行EXE分别核对。

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
| 正式发行 | Windows便携包 | 最新版整体验收、性能/兼容结论、签名更新的跨版验收；体验版按用户明确授权发布，不自动推定稳定发行。 |

完整SillyTavern行为兼容也未实现，现有卡/书格式兼容不等于概率/递归/脚本等全兼容。

## 5. 接下来从哪一步继续

0. **配音按路线维护验收状态**：本地效果已有2026-10-13用户确认；免费云端最新版和付费API尚未测试、待确认。其他缓存／试听替换／服务修复场景仍由用户验收。前轮四次GPT对照许可已经用完，不自动新增模型或付费服务调用；见[当前手册](docs/CHARACTER_VOICES.md)。

1. **继续验收0.1.77下载与升级**：确认完整安装／便携包的Core、设置、0051旧存档升级、缓存／试听替换／服务修复及模型效果；云端免费／付费配音仍待确认。继承地点、阵营、记忆、世界动态、后台与权限等未确认场景，不由发布完成代替验收。工程端不运行产品、模型或真实迁移。
2. **验收尚未确认的关键链路**（共同联系目前由用户先等待，不主动触发或排查）：记忆纠正/停用和旧事召回、活动真实终态/权限、动态池公共背景→生成→逐条发布→标记、在线单人/双人同事由→等待回复→原会话回复→合法下次机会、离线联动。主动联系失败先查保存状态/前提/终端原因，不靠反复开关或自动重放API排查。
3. **只按证据修复**：记录现象、版本、受影响模块和可观察完成条件；新功能先调查成熟实现并确认新增范围。用户仍负责测试；未获新许可不运行自动测试、GUI smoke、真实存档/模型诊断。
4. **新方向先讨论**：将4.2中的愿景与当前功能验收分开；0.1.77已获本轮审查修复预发布授权，未来发行仍须相应批准。已有记忆底座不需要重新搭建。

各功能操作/验收手册： [聊天恢复](docs/CHAT_FUNCTIONAL_EXPERIENCE.md)、[记忆与上下文](docs/CONTEXT_AND_RECALL.md)、[经历终态](docs/EXPERIENCE_STATE_RECALL.md)、[日常](docs/DIRECTOR_ACTIVITIES.md)、[相遇](docs/CHARACTER_ENCOUNTERS.md)、[共同休闲](docs/SHARED_LEISURE.md)、[主动联系](docs/PROACTIVE_CONTACT.md)、[离线消息](docs/OFFLINE_MESSAGES.md)、[事件](docs/WORLD_EVENT_JOURNAL.md)、[阵营](docs/CHARACTER_FACTIONS.md)、[启动](docs/CELESTIAL_STARTUP.md)。

## 6. 交付与证据

本轮0.1.77检查、构建和GitHub完成回执统一在[审查修复记录](docs/maintenance/2026-10-14-review-fixes-release.md)；不把计划当成功，不将静态检查扩为运行验收。

历史完整HANDOFF查[收敛前Git快照](https://github.com/zhangyeS12/dreamtalk/blob/f1964d150d6702f4273bdf23d1ae181ee3156582/HANDOFF.md)，各轮维护／哈希记录仍在[历史索引](docs/history/README.md)和维护文档。近期重点：

- [0.1.76大更新发布](docs/maintenance/2026-10-14-major-release.md)。
- [新增表情摘要位置修复](docs/maintenance/2026-10-14-sticker-context-position.md)和[频率／最新库摘要](docs/maintenance/2026-10-14-sticker-library-freshness.md)。
- [有限角色表情测试](docs/maintenance/2026-10-14-sticker-delivery-test.md)，七次许可已结束。
- [本地配音采样修复](docs/maintenance/2026-10-13-speech-candidate-sampling-fix.md)，四次对照许可已结束。
- [模型自动启动／本地次数](docs/maintenance/2026-10-13-local-model-startup-and-limits.md)和[一键服务修复](docs/maintenance/2026-10-13-local-speech-one-click-repair.md)。

历史版本、耗时、入口和打包哈希保留当时事实，不用作当前入口或最新版性能结论；旧资产不随文档整理改写。

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

需要源码检查时使用`npm run lint`。自2026-10-13起，除明确获准GitHub发布外，不进行本机打包；必要编译可用既有`build:desktop`（调试、`--no-bundle`），不调用便携／安装器脚本。仅获准发布时使用`npm run build:portable -- --build-only`；默认打包包含自检，不得遗漏`--build-only`。用户直接体验入口为`apps/desktop/src-tauri/target/debug/dreamtalk-desktop.exe`，不改为启动脚本或让用户自行编译；开发入口仍为`dev:desktop`/`dev:web`/`dev:core`，UI端口1420不是Core端口。文档任务不启动这些入口，保留现有tests/CI，历史测试或单次诊断许可不授权本轮自动运行。

每次改动同步：AGENTS只记录长期规则/新决定，PROJECT_STATUS更新对应能力与验收，HANDOFF保留当前基线/现场/接续。不要追加第二个“最新”、虚报完成率或把历史包写成当前入口。用户反馈按原话/问题/版本归档；没有具体反馈不能升级为全量验收。
