# 主动联系成熟方案调查（2026-10-04）

| 来源/版本依据 | 可借鉴部分 | 实际选择与许可 |
| --- | --- | --- |
| [SillyTavern Group Chats 当前文档](https://docs.sillytavern.app/usage/core-concepts/groupchats/) | 自动模式在无玩家输入时生成群消息 | AGPL-3.0 项目，不复制源码/不并入分发。其轮流发言不保证共同目的、物理参与或持久等待回复，复用本项目已有群会话和 Director/Kernel。 |
| [Zulip update-message-flags API 当前文档](https://zulip.com/api/update-message-flags) | 阅读标志与对话回复分开 | 仅借鉴公开 API 行为，不引入服务器或源码。SQLite 会话阅读位置满足桌面需要，避免每条历史消息存一个新标志。 |
| [Temporal Python message passing 当前文档](https://docs.temporal.io/develop/python/message-passing) | 持久流程等待外部输入后再推进 | 仅借鉴等待输入的生命周期，不引入 Temporal 服务/SDK。本项目 SQLite 写事务、outreach turn 与已保存玩家消息足以提供相同门禁。 |

本轮按以上网页 2026-10-04 检索到的文档行为评估，没有声称锁定并安装新库版本。没有复制外部源码，没有新增依赖；实际复用既有 SQLAlchemy/Alembic、角色资料投影、共同活动事实、有界生成/用量账本、群聊、React/HTTP 客户端与桌面可见性报告。
