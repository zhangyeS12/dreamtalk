# dreamtalk 工作交接

本页只提供接手导航。当前版本与全部功能状态统一见[状态清单](docs/PROJECT_STATUS.md)，长期工程规则见[AGENTS.md](AGENTS.md)，现行产品约定见[PRODUCT.md](PRODUCT.md)。

## 1. 五分钟了解当前完成度

- 项目已有完整Windows体验版，聊天、资料、记忆／检索、有限世界活动及媒体链路均有实现；完成实现、工程检查通过和用户验收是三种证据。
- [已通过](docs/PROJECT_STATUS.md#用户已通过的具体场景)只收录明确使用反馈；[待验收](docs/PROJECT_STATUS.md#已实现但仍待验收)不是待开发列表；[未实现](docs/PROJECT_STATUS.md#尚未实现)不自动成为新需求。
- 文档整理、双人联系及协调层整改已交付，接手路径见[协调边界](docs/architecture/SYSTEM_OVERVIEW.md#组合与协调的源码边界)。离线容量及六项容量边界优化入口为 application/input_budget.py、content_editor_pages.py、persistence/director_background.py、character_lineage.py、chat_unread.py、proactive_contact.py 及前端 contentEditorPages.ts；本轮又加入聊天会话精确读取和后台任务诊断，实际检查见[状态表](docs/PROJECT_STATUS.md#已有工程检查通过的部分)。0.1.91源码、便携包、安装器、GitHub Release 和更新频道均已完成，完整证据见[发行记录](docs/maintenance/2026-10-26-release-0191.md)；当前工作树另有未发布的角色卡建议来源元数据和上述优化改动，真实升级及后台运行仍待用户验收。
- 共同联系此前由用户决定先等待；没有新故障证据时，不主动触发、放宽门禁或调用模型排查。

## 2. 仓库、运行和版本现场

- 正式仓库为D:\LivingWorld；分支／HEAD／工作区以Git现场为准，不从旧工作日志推断。源码、发行标签、安装包和实际运行程序分别核对。
- 用户入口为artifacts/local-desktop/dreamtalk-desktop.exe，依赖仓库开发环境；对外完整包包含Core及资源，两者用途不同。该入口的版本／摘要回执在同目录entry.json，必要编译规则见[验证责任](AGENTS.md#20-current-verification-responsibility)。
- 本机入口通过仓库现有环境加载Core源码；当前工作树包含角色扮演、回复格式、提示编排及通讯录世界风格／台词高亮，以及最新的[聊天路线与高级世界书](docs/CHAT_PATHS_AND_LORE.md)。界面变化需沿规定入口重新编译，完全退出旧应用后重开生效；世界风格源码入口为application/world_style.py、persistence/world_style.py、adapters/http/world_style.py及前端WorldStyleEditor.tsx／dialogueHighlight.ts；玩家专用卡入口为application/player_card.py、player_persona.py及PlayerPersonaEditor.tsx，独立资料不走通讯录／NPC／地点初始化；迁移与检查证据见状态清单。该入口不是可搬运的完整便携包，工程检查不代表真实模型或安装升级验收。
- 更新继续沿原应用标识、公钥和频道。不得用旧程序打开已升级存档，不移动／删除DB或WAL，不改真实API、启动项或已安装应用。
- 开屏及更新失败修复的实际限制见[可靠性记录](docs/maintenance/2026-10-17-reliability-hardening.md)；发行完整性与用户运行结果见状态表的不同栏目。

## 3. 各部分怎样实现、从哪里接手

| 任务 | UI → 宿主／API → Core入口 | 按需阅读 |
| --- | --- | --- |
| 世界书架、角色卡／世界书、卡内动态版本、身份 | WorldArchivePage.tsx／WorldContent.tsx／ProfileEditor.tsx → packages/api-client → adapters/http → application/content.py、world_content.py、infrastructure/persistence/character_evolution.py | [产品入口](PRODUCT.md)、[导入契约](docs/architecture/IMPORT_MODEL.md)、[聊天契约](docs/architecture/CHAT_MODEL.md) |
| 设定身份与逐角色初始认识 | PlayerPersonaEditor.tsx → player_persona.py的预览／确认 → 世界范围持久化；直接／群聊及主动联系在输入前过滤 | [身份契约](docs/PLAYER_PERSONA.md) |
| 消息编辑、候选与聊天路线；高级世界书 | ChatPathTools.tsx／LoreAdvancedControls.tsx → chat_paths.py／lore_activation.py → chat_path_queries.py／chat_lore.py；0057迁移（当前源码 head 为0059，公开包 head 为0058） | [入口与契约](docs/CHAT_PATHS_AND_LORE.md) |
| 私聊、群聊与流式 | ProductApp.tsx／ChatTranscript.tsx／GroupChat.tsx／useReplyStream.ts → application/chat_reply.py、group_chat_reply.py | [聊天模型](docs/architecture/CHAT_MODEL.md)、[恢复说明](docs/CHAT_FUNCTIONAL_EXPERIENCE.md) |
| 模型配置、费用和硬额度 | ModelSetup.tsx → Tauri llm_config.rs／凭据管道 → bootstrap/llm_runtime.py、application/chat_capacity.py、llm_execution.py | [生产组装](docs/architecture/LLM_PRODUCTION_COMPOSITION.md)、[账本](docs/architecture/LLM_ACCOUNTING.md) |
| 记忆与RAG | LongChatMemoryPanel.tsx／ConversationMemoryPanel.tsx → long_chat_memory.py → persistence/long_chat_memory.py、semantic_chat_retrieval.py、recall_index.py | [上下文与召回](docs/CONTEXT_AND_RECALL.md)、[亲历召回](docs/EXPERIENCE_RECALL.md) |
| 活动、地点、相遇、共同休闲 | WorldActivities.tsx／LocationWorkspace.tsx → Director／scheduler → Kernel、routine_lifecycle.py、character_encounters.py、shared_activities.py | [地点手册](docs/ACTIVITY_LOCATIONS.md)、[共同休闲](docs/SHARED_LEISURE.md) |
| 世界事件与主动联系 | WorldEventJournal.tsx及后台设置 → world_story.py、chat_event_annotations.py、offline_contact.py、主动联系应用服务 | [世界事件](docs/WORLD_EVENT_JOURNAL.md)、[批准的主动联系](docs/proposals/2026-10-04-proactive-contact.md) |
| 阵营、头像和人物网 | ContactSocial.tsx／RelationshipUniverse.tsx → factions持久化及受权社交上下文 | [阵营与关系网](docs/CHARACTER_FACTIONS.md) |
| 配音和图片／表情 | SpeechPlayback.tsx／CharacterVoice.tsx／ChatMedia.tsx → 私有媒体／凭据管道 → application/speech.py、chat_media.py；本地服务由Tauri监督 | [配音](docs/CHARACTER_VOICES.md)、[聊天媒体](docs/CHAT_MEDIA.md) |
| 五位置存档与更新保护 | SaveSlots.tsx → Tauri save_slots.rs → 离线--storage-request → infrastructure/save_slots.py／save_safety.py | [存档说明](docs/DATA_BACKUPS.md)、[批准方案](docs/proposals/2026-10-17-save-slots.md) |
| 启动与应用内更新 | App.tsx／DesktopUpdates.tsx → Tauri lib.rs、supervisor.rs、updater.rs → bootstrap/cli.py、application/update_maintenance.py；安装入口scripts/build-installer.py | [Windows更新](docs/WINDOWS_UPDATES.md)、[系统概览](docs/architecture/SYSTEM_OVERVIEW.md) |

前端位于apps/web/src，宿主位于apps/desktop/src-tauri/src，Core相对路径均在services/core/src/livingworld。目录是定位提示，改动前仍须确认实际文件／调用链；不能仅凭文档判断实现正确。

## 4. 接续顺序

1. 先看状态清单对应能力，确认当前任务是修复、验收还是新产品选择。
2. 真实安装／更新及存档连续性仍是首要验收缺口；工程运行需对应具体授权，不能把排错交给普通用户。
3. 记忆、活动、事件、主动联系和媒体按具体场景验收；保留用户先等待共同联系的决定，不自动生成付费任务。
4. 只修复有现象／源码证据的问题；完整离线演化等未冻结方向继续独立记录，不自动开工。
5. 本轮三项协调整改已实现，真实 old→new 安装／失败恢复自动验证按用户决定暂不做；用户从正常入口验收更新。后续全仓类型化及其他大文件仍是独立维护事项，不把组件回归当真实更新成功。

## 6. 交付与证据

最新发行、精确提交CI、静态载荷／签名／匿名下载结果统一见[工程检查](docs/PROJECT_STATUS.md#已有工程检查通过的部分)。历史运行问题、研究和旧阶段验收从[历史索引](docs/history/README.md)按需查询；不把历史成功扩大到最新版整体验收，也不要求接手者通读所有记录。
