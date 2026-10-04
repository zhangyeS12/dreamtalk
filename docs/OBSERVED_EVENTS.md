# dreamtalk：世界事件与聊天

桌面0.1.5的“世界事件”分为“聊天获知”和“世界动态”，详见[使用说明](WORLD_EVENT_JOURNAL.md)。前者记录角色在正常私聊／群聊告知的具体活动、计划、传闻、邀请和变更，保留原句及获知时间；后者来自已授权公共世界书的批量动态，隐藏事件池逐条发布，由用户手动标记经历／跳过，整批80%处理后续批。

聊天 → 左侧置顶“世界事件” → 查看记录。公共动态可“聊聊这件事” → 选择已有私聊／群聊 → 核对输入草稿 → 手动发送，不会自动发送话题。

原来当前玩家亲历事件仍在“我亲历的活动记录”折叠区域。详情来自当前世界、当前绑定玩家的授权观察，角色回复另读它自己的记录。没有亲历的角色不能因为后台存在记录而自动知情。角色聊天说法不是WorldTruth，公共公告发布也不证明正文中的计划／传闻已经完成或证实。

亲历详情采用移动／放置／日常活动等受支持事件的有限中文模板；未知版本不猜测。名称是当前实体标签而非历史名称快照。玩家亲历列表最多100条，角色亲历输入仍最多12条／8KiB。聊天获知每页100条可读取更早记录；已发布动态保留全部未处理条目及有界近期历史，待发布内容不暴露。

Director基本自动活动和离线联系已在此前版本实现；此前本文“尚未实现”和“无新表”的文字是旧切片状态，与实际代码不符，本版已更正。日常计划、离线联系与公共动态独立开关。新迁移0028增加五张应用数据表，未运行于用户存档；用户启动新版后按既有流程升级。

按AGENTS§20，本轮只源码／静态检查、编译和包内字节核对，未新增／执行测试、启动应用、调用真实API或操作用户存档。运行效果和权限隔离由用户验收。无亲历记录时该折叠列表为空是预期，不应伪造活动或回填授权。

## CharactersMet v1（0.1.25，已获用户批准）

由独立EncounterKernel消费Director候选，同一Kernel写事务复核授权、计划、WorldTime、双方active rest/leisure、地点和presence revision后提交。不可变载荷白名单是first_character_id/second_character_id/location_id、双方routine_id/revision、candidate_id/purpose=brief_greeting、encounter_due_at/encounter_end_at。保留实际发生时间和创建UTC，不回填离线相遇；仅描述短暂见面，不创建对话、任务成果或关系变化。两位参与者与授权在场观察者获得witnessed/event_occurrence；其他主体无自动观察。投影保留participants和participant/witness区分，不暴露全量payload。候选与回执原子完成，重放验证来源活动、时间窗口、同地点、revision、去重与六小时冷却。见[批准方案](proposals/2026-10-03-character-encounters.md)。

## 0.1.26持续同场与熟悉边界

CharactersMet v1观察投影明确encounter_stage=brief_greeting、relationship_effect=none，不将名字显示解释为交换姓名，不从普通问候升级正式介绍/共同经历/关系；已有独立授权的熟识背景仍可使用。Kernel按实际离开账本结束同场段，持续停留不重复普通问候。活动开始/结束/中断等真实变化仍正常记录，不把本次去重解释为所有见闻只留一条。无新观察类型、事件版本或自动记忆写入，既有owner/participant/witness与字节边界保持。见[使用说明](CHARACTER_ENCOUNTERS.md)。
