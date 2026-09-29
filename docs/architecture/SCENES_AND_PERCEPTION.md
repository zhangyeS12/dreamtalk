# Scenes and Event-Time Perception

状态：C-006B 建立 persistent Scene、typed participation history 和 event-time perception snapshot；C-007A 允许 Character 通过独立显式命令把自己的 Observation 用作 EpisodicMemory evidence。Scene 不是对话引擎；Observation 仍不自动成为 Knowledge 或 Memory。

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

现有 `Observation` 已能以 `target_id: EventId | KnowledgeAssertionId` 表达该边界，因此 C-006B 复用它，不新增 perception table。事件感知保存为 `Observation(channel=WITNESSED, target_id=EventId, basis=EVENT_OCCURRENCE)`；可空 basis 是最小 provenance 标记，用于区分 Kernel occurrence audience 与 Stage 2 允许独立重复 occurrence 的普通 Observation。它没有 proposition，不写 WorldTruth、CharacterBelief、PlayerKnowledge 或 Memory。C-007A 的 `RecordEpisodicMemory` 是另一个显式步骤：只有同一 Character 自有 Observation 可作为 evidence，且 Memory 仍不会反向授予知识或证明内容真实。详见 [Episodic Memory](EPISODIC_MEMORY.md)。

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

## 6. Perception 与 activation

`Perception != Activation`。Observation 是历史访问事实；Activation 是当前/未来 bounded work。事件可以有 500 个合法 witnesses，而 wake policy 明确选择 `NONE`、bounded Character targets 或一个 WORLD aggregate。fanout bound 只限制立即 work，不删除或截断 Observation。

Character `WORLD_EVENT` activation 必须已有同世界该 WorldEvent 的 `EVENT_OCCURRENCE` Observation；Activation 自身不能绕过访问隔离，也不会反向创建 Observation。Scene activity wake 只面向 OPEN Scene 当前 active Character members，不包括 Player、历史成员或同地点非成员。`PLAYER_FACING` fidelity 也只来自实际共享 active Scene，同 Location 不足以成立。详见 [Sparse Activation](SPARSE_ACTIVATION.md) 与 [Simulation Fidelity](SIMULATION_FIDELITY.md)。

## 7. Persistence

[0012_action_scenes_perception](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0012_action_scenes_perception.py) 新增 `scenes`、`scene_participants`、active/history/status/current-location 索引，为 observations 增加可空 basis、EVENT_OCCURRENCE event/principal unique 与 principal history 索引，并扩展现有 command receipt CHECK 以保存无 WorldEvent 的 typed rejected action/Scene result。Alembic 仍是唯一迁移权威；0011 rows、events、receipts 与 legacy audit 原样保留，旧 Observation 的 basis 为 NULL。

0012 本身没有新增 Knowledge 或 Memory table。当前 Alembic head 0014 的 Memory tables 属于后续 C-007A，未改变本页的 event-time audience 规则；消息、对话、Director 与 Agent 状态仍未实现。


## 2026-09-29 亲历事件接入（历史切片）

上方0014/未实现聊天的描述属于C-007A历史切片；本节记录亲历事件接入时的0024阶段，当时会话与聊天已接入，还没有后续Director runtime。event-target Observation保留为历史访问记录，不从当前地点重新推导观众。玩家时间线和角色回复只读各自已授权记录；中文详情额外要求 witnessed + event_occurrence，白名单v1主体/地点字段和辅助字段均受同一授权条件限制。

## 当前补充状态

0025已接入默认关闭、首次授权费用的批量Director及Kernel角色日常/移动，0026增加本地手动地点目录。上述event-time audience规则保持；新增地点不自动给任何主体获知事件，也不改变玩家位置。前面的0024说明不能用作当前Director尚未实现的结论。见[Director活动](../DIRECTOR_ACTIVITIES.md)及[手动地点](../ACTIVITY_LOCATIONS.md)。

## 后台界面可见性

0027桌面启动先清空操作性local_session_visibility。Native窗口可见且聚焦、UI当前世界/身份的短期在线心跳才允许本地绑定Player被at_location选为现场见证者；失焦/隐藏立即撤回，到期也失效。序号阻止迟到旧请求覆盖新状态。其他世界的绑定Player不因为保存的位置而成为见证者。未绑定Player和角色规则保持；显式玩家行为的结果、既有Observation不重写。操作性界面状态不移动Player、不改availability、不造WorldEvent。
