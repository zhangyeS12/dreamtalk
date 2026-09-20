# Scenes and Event-Time Perception

状态：C-006B 建立 persistent Scene、typed participation history 和 event-time perception snapshot。Scene 不是对话引擎；Observation 不自动成为知识或 Memory。

## 1. Scene and Presence

`Scene` 是同一 Location 内的有界互动上下文，包含 typed SceneId/WorldId/LocationId、OPEN/CLOSED、started/ended WorldTime、Revision 和 UTC creation audit。Location 创建后不可改变；所谓“移动 Scene”必须结束旧 Scene 并新建一个。

`Scene != Location`。Location、PlayerPresence、CharacterState 是物理位置权威；Scene membership 不放置或传送主体。创建 Scene 至少有一个 initial participant，所有初始成员必须在 Scene.Location。OPEN Scene 可 join；CLOSED Scene 不可 join或重开。end 在一个 transaction 中关闭 Scene 并以同一 WorldTime 结束全部 active membership；最后一人离开不会自动关闭 Scene。

`SceneParticipant` 使用独立 SceneParticipantId、typed PlayerId/CharacterId、joined_at 与可空 left_at。离开只写 left_at，不删除历史。SQLite partial unique index 保证 `(world, principal kind, principal id)` 最多一条 active membership；PlayerId 与 CharacterId 即使 UUID bytes 相同也不碰撞。

任何 physical movement 离开 Scene.Location，都与 Presence/CharacterState mutation 同事务结束 active membership并推进 Scene revision。Scene 可保持 OPEN 且暂时无人。Create/join/leave/end 是内部 runtime 操作，不创建虚构 WorldEvent 或 KnowledgeAssertion。

## 2. Perception boundary

```text
WorldEvent  = what happened
Observation = who had access to that event at occurrence time
Knowledge   = what a principal understood or believed
Memory      = later retained/processed experience
```

现有 `Observation` 已能以 `target_id: EventId | KnowledgeAssertionId` 表达该边界，因此 C-006B 复用它，不新增 perception table。事件感知保存为 `Observation(channel=WITNESSED, target_id=EventId, basis=EVENT_OCCURRENCE)`；可空 basis 是最小 provenance 标记，用于区分 Kernel occurrence audience 与 Stage 2 允许独立重复 occurrence 的普通 Observation。它没有 proposition，不写 WorldTruth、CharacterBelief、PlayerKnowledge 或 Memory。Stage 6 决定感知如何成为知识/信念/记忆。

## 3. Typed audience selectors

resolver 只能产生 allowlisted selectors：

| selector | event-time meaning |
| --- | --- |
| NONE | 没有 observer；WorldEvent 仍然有效 |
| ACTOR_ONLY | typed Actor（若存在） |
| SCENE_PARTICIPANTS | 当时仍 active 的该 OPEN Scene 成员，不含已离开成员或同地点非成员 |
| LOCATION_PRESENT | 该 Location 的当前 CharacterState 与 active PlayerPresence；inactive Player 的存储位置不会自动造成见证 |
| EXPLICIT_PRINCIPALS | resolver 提供的 bounded typed 集合；必须存在且同世界 |

多 selector 取确定性 union，并按 typed kind/UUID 排序；同一主体每个 Event 最多一条 EVENT_OCCURRENCE Observation。数据库 partial unique index `(world_id,target_event_id,principal_kind,principal_id) WHERE target_kind='event' AND basis='event_occurrence'` 最终加固去重，同时保持 C-003D 普通 Observation 的独立 occurrence 语义。Scene 与 Location 查询分别只使用 active-membership/current-presence 索引，不扫描 World 全体，也不为每个主体创建 asyncio task。

## 4. Occurrence snapshot and atomicity

每个 resolved event 显式携带 occurrence audience context。单事件移动在 mutation 前读取 origin/destination witness sets并显式包含 actor，然后在同一 UoW 中：

```text
append WorldEvent / allocate ledger_position
CAS projection mutation
end incompatible active Scene membership
insert event-target Observations
insert RequestId receipt
commit
```

任一步在 commit 前失败会整体 rollback；不会出现 event 已存在而 witness rows 消失。commit 后所有事实一起 durable。多个事件的未来 resolver 必须按固定 ordinal 逐个定义 occurrence point/audience；不能把一个最终状态反推给全部事件。

## 5. Historical immutability and replay

event perception 是发生时快照。之后 move、join、leave、relationship 或 clock 变化不得重写旧 Observation；新成员不会自动获得旧事件，已离开成员不会丢失曾经的访问记录。没有 observer 的 offscreen WorldEvent 合法。

Projection rebuild 继续按 ledger_position 重建 replayable projections，但不会用当前 Presence/Scene 重算 event-target Observations。rebuild 只清理并恢复由知识事件产生的 assertion-target Observation；event-target rows作为 authoritative historical access record 原样保留，因此不会重复插入或改变 audience。

## 6. Persistence

[0012_action_scenes_perception](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0012_action_scenes_perception.py) 新增 `scenes`、`scene_participants`、active/history/status/current-location 索引，为 observations 增加可空 basis、EVENT_OCCURRENCE event/principal unique 与 principal history 索引，并扩展现有 command receipt CHECK 以保存无 WorldEvent 的 typed rejected action/Scene result。Alembic 仍是唯一迁移权威；0011 rows、events、receipts 与 legacy audit 原样保留，旧 Observation 的 basis 为 NULL。

没有新的 Knowledge table、Memory table、消息、对话、Director 或 Agent 状态。
