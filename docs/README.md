# 文档导航

先按任务选入口，不需要通读目录内全部文件。当前版本／完成度统一在[状态清单](PROJECT_STATUS.md)，用户最新决定优先于历史记录。现行手册描述当前源码行为，不保证下载到的旧版安装包具有同样能力；发行边界以状态清单及对应发行说明为准。

| 目的 | 阅读入口 |
| --- | --- |
| 使用、下载、了解产品 | [项目主页](../README.md)、[Windows安装](PORTABLE_WINDOWS.md)、[设置手册](SETTINGS_HANDBOOK.md) |
| 消息编辑、候选、分支／检查点与高级世界书 | [使用与契约](CHAT_PATHS_AND_LORE.md) |
| 接手开发 | [工程规则](../AGENTS.md) → [交接与调用链](../HANDOFF.md) → [状态清单](PROJECT_STATUS.md)；环境见[开发说明](DEVELOPMENT.md) |
| 核对批准行为 | [现行产品约定](../PRODUCT.md)，再读对应模块手册／批准方案；[原始FR规格](product/PRODUCT_SPEC.md)仅用于规则编号追溯 |
| 查架构与实现边界 | [系统概览](architecture/SYSTEM_OVERVIEW.md)、[ADR索引](architecture/ADR/README.md)；其余模型文档按模块选读 |
| 查历史证据 | [历史索引](history/README.md)、相关日期维护记录与Git；[研究索引](research/README.md)用于来源和取舍，不作新任务清单 |
| 核对分发义务 | [许可证](../LICENSE)、[第三方许可](licenses/)、[隐私](PRIVACY.md)、[签名政策](CODE_SIGNING.md) |

## 按功能查手册

| 功能 | 文档 |
| --- | --- |
| 书架、封面、示例 | [书架](WORLD_ARCHIVE.md)、[书本设计与封面](WORLD_COVERS.md)、[校园示例](EXAMPLE_WORLD.md) |
| 聊天、记忆与来源 | [聊天](CHAT_FUNCTIONAL_EXPERIENCE.md)、[长期记忆](LONG_TERM_MEMORY.md)、[上下文与召回](CONTEXT_AND_RECALL.md)、[亲历召回](EXPERIENCE_RECALL.md) |
| 聊天背景、角色立绘与沉浸模式 | [聊天模型与显示契约](architecture/CHAT_MODEL.md#聊天视觉与沉浸模式)、设置页与通讯录角色档案 |
| 玩家设定身份 | [人物绑定、预览确认与逐角色初始认识](PLAYER_PERSONA.md) |
| 地点、日常与相遇 | [地点](ACTIVITY_LOCATIONS.md)、[日常](DIRECTOR_ACTIVITIES.md)、[相遇](CHARACTER_ENCOUNTERS.md)、[共同休闲](SHARED_LEISURE.md) |
| 事件与主动联系 | [世界事件](WORLD_EVENT_JOURNAL.md)、[在线联系](PROACTIVE_CONTACT.md)、[离线联系](OFFLINE_MESSAGES.md)、[背景授权](BACKGROUND_TASK_FEEDBACK.md) |
| 阵营与界面 | [阵营／关系网](CHARACTER_FACTIONS.md)、[世界终端](WORLD_TERMINAL.md)、[开屏](CELESTIAL_STARTUP.md) |
| 配音、表情与图片 | [角色音色](CHARACTER_VOICES.md)、[聊天媒体](CHAT_MEDIA.md) |
| 存档、安装与更新 | [存档](DATA_BACKUPS.md)、[安装](PORTABLE_WINDOWS.md)、[应用更新](WINDOWS_UPDATES.md) |

## 文档范围

| 材料 | 适用方式 |
| --- | --- |
| 根目录入口、功能手册、architecture技术契约、product用户流程／原则 | 现行说明；行为和源码入口须与工作树一致，实现／发行／验收查状态清单。C／Stage编号只保留契约追溯含义。 |
| product/PRODUCT_SPEC.md | 原始FR／问题编号档案；现行批准行为以PRODUCT及模块契约为准，不据旧开放问题重新立项。 |
| maintenance、releases、research、proposals及history的固定快照 | 带日期或版本的证据、研究或决策；旧“本轮”“下一步”“授权”“未实现”不延续到当前任务。方案的有效契约由现行手册承接。 |
| licenses | 第三方分发义务；保留上游原文和版本，不按普通冗余文档改写。 |

## 维护与交接检查

1. 先核对Git分支／HEAD／工作区、当前源码和状态清单。遇到代码与已确认产品规则冲突，记录差异，不能通过改文档给实现补授权。
2. 在对应模块手册更新现行行为、限制和源码入口，直接替换过时结论；不在旧结论后追加一段“最新补充”让读者自行判断。模块迁移编号只说明表的来源，当前head只由状态清单和`migration.py`维护。
3. 实现、工程检查、用户反馈和公开发行分别登记；编译或旧测试结果不能写成当前运行验收。现行手册不保留逐轮授权、旧包启动路径、未来时态的已完成功能或重复的检查日志。
4. 修改影响某个契约时，同时核对PRODUCT、HANDOFF源码定位和状态表对应行；历史原始证据保留日期／范围，经历史索引查阅，不当作当前待办。
5. 交接前搜索相关模块的旧名称、旧入口和互相矛盾的结论，运行`scripts/check-doc-links.py`并检查`git diff --check`。本地链接通过只证明目标存在，内容仍须对照源码审阅。

维护时把行为写入对应手册，把实现／验收写入状态表，把证据过程留在原记录；不追加同内容的入口说明或逐日汇总。第三方许可文件属于分发义务，不能按普通冗余文档删除。
