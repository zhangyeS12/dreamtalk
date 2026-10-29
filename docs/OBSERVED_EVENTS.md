# 亲历事件、聊天获知与话题

本页说明普通界面的事件可见性；聊天获知和世界动态的完整规则见[世界事件手册](WORLD_EVENT_JOURNAL.md)，当前版本及验收见[状态清单](PROJECT_STATUS.md)。

聊天列表置顶“世界事件”展示聊天获知、世界动态及折叠的玩家亲历记录。“聊聊这件事”把引用加入选定已有会话的草稿，由用户核对并手动发送，不自动联系或调用模型。

## 玩家与角色各自读取

亲历详情先按当前世界、本地绑定玩家的 Observation 授权，再关联真实事件，只返回支持类型的有限中文投影，不返回全量 payload、隐藏关系数值或其他角色观察。没有绑定／获准观察时列表可以为空。名称取当前实体标签，不是历史名称快照；未知事件版本不猜测。

玩家亲历列表最多100条；角色另读自己的观察，按[亲历召回](EXPERIENCE_RECALL.md)的窗口和容量进入输入。聊天获知每页100条可读更早记录；未发布的世界动态候选不暴露给普通界面。角色聊天说法、玩家标记和公共公告均不直接认证正文为 WorldTruth。

## 已支持的真实经历

移动、放置、日常开始／结束／中断、CharactersMet及共同休闲通过既有事件投影展示。初始设置不等于目击历史，实际可见性以事件发生时记录的主体和渠道为准，不从当前地点重新推导旧观众。

相遇须 Kernel 复核授权、计划、真实同场、活动、时段及 presence revision，原子写入事件、获准观察、候选结果和幂等回执。投影区分 participant／witness；`brief_greeting`、`relationship_effect=none` 不证明正式介绍、私下对话或新关系。持续同场不重复普通问候，离开／返回及冷却见[相遇说明](CHARACTER_ENCOUNTERS.md)。共同休闲及终态见[共同休闲](SHARED_LEISURE.md)与[状态召回](EXPERIENCE_STATE_RECALL.md)。

## 源码与证据

源码为 `services/core/src/livingworld/application/player_event_feed.py`、`application/observed_events.py`、`infrastructure/persistence/player_event_feed.py`及`observed_events.py`。HTTP和聊天分别绑定当前玩家与发言角色，不共享一个全知结果集。

迁移编号仅说明各表／投影的创建来源，完整链以状态清单和 `migration.py` 为准。没有对应真实记录时不补造活动或回填授权；工程检查、真实存档诊断和模型表现分别记录。
