# Event Model

> 状态：保留 Stage 0 概念边界；Stage 2 已建立不可变事件、命令原子提交、知识隔离、canonical ledger、回放及资源级 CAS。C-006B 增加 deterministic ActionProposal→resolution→WorldEvent 路径和发生时感知快照。日常Director候选计划和Kernel基本活动已实现；2026-10-01增加应用层聊天获知记录、有限公共公告池和Kernel公告发布，完整角色认知／关系／活动成果仍待推进。

规则来源：[PRODUCT_SPEC.md](../product/PRODUCT_SPEC.md) 中的 FR-01、FR-02、FR-04 至 FR-15、FR-22 至 FR-24。规划责任见 [DIRECTOR_MODEL.md](DIRECTOR_MODEL.md)，信息归属见 [KNOWLEDGE_MODEL.md](KNOWLEDGE_MODEL.md)。

## 1. 核心区分

```text
CandidateEvent != WorldEvent
```

**候选事件只有被激活后才成为真正的世界事实。**

CandidateEvent 表达一个可能发生、尚待处理的世界事件；WorldEvent 表达已经实际发生的世界事件。来自候选的 WorldEvent 必须经过激活；玩家即时行动可经 C-006B 的 typed ActionProposal、authority/precondition validation 和 deterministic resolver 成为 WorldEvent，不要求先建立 CandidateEvent。World Plan 与 Event Reservoir 中存在某个候选，不意味着该事件已发生。延期或取消候选也不意味着发生过该候选描述的事情。

| 概念 | Purpose | 事实边界 |
| --- | --- | --- |
| CandidateEvent | 承载可以由传统程序激活、延期或取消的候选安排 | 激活前不是世界事实，不能提前更新角色或玩家对已发生事件的知识。 |
| Event Reservoir | 组织待处理候选，供传统程序处理 | 候选集合不等于已发生事件集合。 |
| World Plan | 提供一批调度安排与候选事件的规划上下文 | 计划不等于事实，也不保证候选必然发生。 |
| WorldEvent | 表达已实际发生的事件及其世界层面影响 | 若源自候选则必须经激活；事实成立不等于玩家或任一角色已获知。 |
| WorldTruth | 表达世界内实际成立的事实 | 不与任何单一主体的 Knowledge 混为一体。 |
| RelationshipEvent | 表达关系变化相关的事件概念 | 后台关系可以变化，但不能因此向普通玩家展示关系数值。 |

WorldEvent、RelationshipEvent 与 WorldTruth 的关系属于概念分工。本文不由这些名字推导数据库表、继承关系、存储模型或事件溯源技术。

## C-003A WorldEvent 合约

实现见 [events.py](../../services/core/src/livingworld/domain/events.py)，时间与世界边界见 [DOMAIN_MODEL.md](DOMAIN_MODEL.md)。

| 成员 | 领域含义 / 当前约束 |
| --- | --- |
| event_id / world_id | 独立 EventId 和所属 WorldId，归属必须相同 |
| event_type | 必填非空事件语义标签；未定义业务事件目录 |
| occurred_at | WorldTime，表示事件在世界内实际发生的逻辑位置 |
| created_at | aware datetime，归一化 UTC，表示软件现实时间中的记录创建时间 |
| payload / payload_version | JSON object 的防御性不可变副本，包括嵌套 object / array；版本必须是正整数，拒绝 bool、非有限数、非 JSON 值与循环结构 |
| causation_id | 可选同世界 EventId 或现有 RequestId，区分事件原因与命令请求 |
| correlation_id | 可选独立 UUID CorrelationId，用于关联一组工作，不等同于事件身份 |
| idempotency_key | 可选非空语义键；本任务不执行去重 |

**双时间表示与推进歧义已解决。** occurred_at 不是 UTC；created_at 不是世界时间。两者刻意允许不同。C-006D 离线 catch-up 只 materialize due Activation，不凭时间流逝生成 WorldEvent；未来 cognition 通过正常 Kernel 路径提交结果时，occurred_at 仍是对应世界坐标，created_at 是较晚的现实创建时间。naive created_at 一律拒绝，aware 的非 UTC 输入统一归一化 UTC，不隐式转换 occurred_at，也不跨轴比较大小。

WorldTime 是逻辑坐标，不是全局事件 ID；两个 EventId 可以共享同一 WorldTime，未来分支也可以在同一坐标拥有不同历史。C-003A 不加入日历、调度或分支身份机制。

WorldEvent 是 canonical history 的不可变领域表达，frozen snapshot 没有 update/delete 方法。外部原始 payload 后续修改不会改变事件；事件内部的嵌套结构也不能修改。构造 Python 值不等于提交事实。C-003C 确定性 command handler 承担首批 Kernel 执行职责，正式事实必须随投影和回执原子提交；Director 仍只提出计划。日常活动候选和公共公告候选已有持久运行实现，仍不能通过构造候选提前写入事实。

[CommandReceipt](../../services/core/src/livingworld/domain/commands.py) 保持 RequestId、world_id、command_type、status、同世界结果引用、UTC 创建/完成时间及 Revision。完成时间不能早于创建时间。C-003C 原表新增独立语义指纹和原始结果：相同请求/语义返回旧结果，变更语义显式冲突，回执指向命令最后一个事件；见 [COMMAND_MODEL.md](COMMAND_MODEL.md)。单纯构造领域事件不自动执行去重。

### C-003B 事件持久化边界

[PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md) 定义独立 WorldEventRecord 和显式 mapper。occurred_at 保存有符号 64 位整数微秒，created_at 保存规范 UTC 文本；payload_version、因果 EventId/RequestId 与 CorrelationId 完整还原，payload 返回领域时深度冻结。(world_id, idempotency_key) unique 只提供 DB 去重约束；None 允许多个事件，相同 WorldTime 不限制事件身份。

EventAppender 只有 append，无事件 update/delete API。SQLite UPDATE/DELETE 触发器及 recursive_triggers 防止 INSERT OR REPLACE 绕过只追加边界。生产 snapshot store 只读，底层映射约束测试不能替代 canonical command 事务入口。

### C-003D 知识事件合约

| 事件 / 固定 ordinal | 语义 payload |
| --- | --- |
| WorldTruthAsserted / 0 | 独立 AssertionId、truth/owner=None、subject/predicate/value、epistemic_status/confidence、WorldTime 有效期、provenance_event_id、revision |
| ObservationRecorded / 0 | 独立 ObservationId、typed receiver、source_assertion_id、channel、observed_at WorldTime、created_at UTC |
| KnowledgeAcquired / 1 | 上述 Observation 语义及派生 AssertionId、owner/scope、完整 proposition、独立认知元数据、WorldTime 有效期、source_assertion_id、获知 provenance 与 revision |

WorldTruthAsserted 的 provenance 指自身事件；派生断言 provenance 指 ordinal 1 KnowledgeAcquired。一个 AcquireKnowledge 原子提交两个事件、Observation、派生断言与单个 receipt，固定沿用 request_id:ordinal key 及既有确定性 EventId；ObservationId 则运行时独立 UUIDv4，不能从请求或事件 ID 推导。成功重试从持久化结果返回原 ObservationId，无新事件或观察；不同请求同坐标可独立发生。旧观察确定性 UUIDv5 仅用于迁移回填，见 [知识访问模型](KNOWLEDGE_ACCESS_MODEL.md)。

事件 payload 属内部 canonical history，不直接作为玩家/角色通知。角色获知仅创建自有信念，玩家获知仅创建自有知识；世界真相不因此修改。观察来源指针不是跨主体读取权限。没有自动 inferred 事件、知识广播、Memory 或 RAG。

### C-003E2 CharacterBeliefFormed v1

FormCharacterBelief 固定 ordinal 0 发出此 semantic canonical event。payload 完整保存 assertion_id、scope=character_belief、typed Character owner、subject/predicate/value、epistemic_status、精确 confidence、WorldTime valid_from/to、可空 source_assertion_id / provenance_event_id、revision=0。

形成事件不是 KnowledgeRowInserted，也不声明命题为 WorldTruth。信念可无 source、无对应 Truth 或与之矛盾；source/provenance 有则保存已验证的既有同世界引用，无则保留 None。该命令不发 ObservationRecorded，不创建 exposure。回放按 `(CharacterBeliefFormed, 1)` 恢复所有原身份与元数据，不重新生成 ID、推理或 reconciliation；原 Truth/Acquire 的 self-event provenance 规则保持不变。

Source 指针不赋予 source owner 的知识读取权限。AcquireKnowledge 仍可用该信念作来源，通过原 ObservationRecorded + KnowledgeAcquired 路径复制 false proposition，不修改 Truth。

### C-003C 首批事件目录

所有下列 payload_version=1，显式语义字段不保存完整 ORM/domain dump。world_id、双时间、因果与关联身份位于统一事件 envelope。

| Event | payload 语义 |
| --- | --- |
| WorldCreated | 世界身份/名称、初始 logical_time、观察 UTC、time_scale、clock_state、世界与时钟版本 |
| LocationCreated | 地点身份、名称、初始 revision |
| PlayerCreated | 玩家身份、名称、静态定义初始 revision |
| PlayerPlaced | 玩家身份、初始地点、activity、availability、Presence 初始 revision |
| PlayerMoved | 玩家身份、from/to 地点、保留的 activity/availability、Presence resulting revision |
| PlayerAvailabilityChanged | 玩家身份、切换前后 availability、Presence resulting revision；不修改地点或 activity |
| CharacterCreated | 角色身份、名称、静态定义初始 revision |
| CharacterPlaced | 角色身份、可空原地点、新地点、状态 resulting revision |
| RelationshipChanged | 有类型与世界作用域的 source/target；角色双方额外 source_character_id/target_character_id；edge_existed、before/delta/after 三项指标与 resulting revision |

**玩家创建事件歧义已解决：** CreatePlayer 固定产生 ordinal 0 PlayerCreated、ordinal 1 PlayerPlaced，同一事务中创建 Player/PlayerPresence 和单一回执。不能提交无初始物理位置的正常玩家。

玩家通过设置切换 Busy / Available。状态更新使用 PlayerPresence revision CAS，提交 `PlayerAvailabilityChanged` 以支持确定性重放。它不会自动产生 Observation 或进入普通玩家世界事件流；切换后的状态由设置页读取。

**关系事件语义歧义已解决：** delta 至少一项非零，范围校验不 clamp，缺失边的 before 为 0/0/0，初始 revision=0；应用后 resulting revision=1，反向边独立。指标仅供内部模拟，普通玩家不能获得数值展示。

事件 key 固定 `request_id:ordinal`；EventId 为基于 RequestId/world/ordinal 的 UUIDv5，身份独立于 WorldTime。顶层 causation=RequestId，correlation=CorrelationId(RequestId.value)。occurred_at 来自共享 monotonic WorldTimeSource（创建世界使用初始值），created_at 来自注入 UTC WallClock。多事件 ordinal 是命令内部身份约定，**不是跨命令 canonical replay position**；不按 WorldTime/created_at 选择唯一回放顺序。

只在事件、投影、回执均成功后 commit；异常全部 rollback，同一未提交请求可由调用方明确重试。成功重试包含进程/engine 重启，不产生第二组事件或额外 revision。C-003E1 已建立 canonical 顺序与投影重建，C-003E2 已建立资源级乐观并发；没有自动 semantic retry。

### C-006B Action 与 Perception 合约

`ActionProposal != WorldEvent`。Proposal 只是 typed proposer 请求 actor 执行动作；普通 `REJECTED` 只保存 bounded typed result/receipt，不产生 WorldEvent、projection mutation、Observation、KnowledgeAssertion 或 Memory。当前生产 proof resolver 为 `move_player` v1，成功沿用现有 `PlayerMoved` v1 payload/replay 合约，不创建第二套事件目录或移动语义。

accepted action 在同一个 UoW 中按固定 event ordinal 分配 canonical ledger position、CAS mutation、写 occurrence audience 的 event-target Observation 并保存 receipt。单事件移动的显式 occurrence rule 是 actor、origin location 的 pre-transition present principals、destination location 的 pre-transition present principals之并集；每个 event/principal 最多一条 `witnessed + event_occurrence` Observation。可空 basis 保持普通 Observation 可有相同坐标的独立 occurrence。零 observer 不妨碍 WorldEvent 成为事实。

`WorldEvent != Perception != Knowledge != Memory`。WorldEvent 回答发生了什么；Observation(EventId) 回答当时谁有访问依据。后者不带 proposition，不自动授予知识。已经提交的 audience 是不可变历史快照，后续 movement/Scene/relationship/clock 变化和 projection replay 均不得依据当前状态重算。详见 [SCENES_AND_PERCEPTION.md](SCENES_AND_PERCEPTION.md)。

## C-003E1 Canonical Ledger Position

C-003E2 再次审计 PlayerMoved、CharacterPlaced、RelationshipChanged：此前 fold 提供 previous revision，现有 resulting revision 与前态字段足以验证转换，保留 v1 不改写历史。随后加入信念和 PlayerAvailabilityChanged 后，当前目录共 13 类 v1。并发 loser 不进入 ledger，winner 重建结果等于已提交状态；完整验收见 [STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)。CAS 或 INSERT 冲突时，事件、分配游标、投影和成功 receipt 同事务完整回滚，不发“attempted but conflicted” canonical event。

`ledger_position != WorldTime != created_at != event_id`。

- 每世界独立正整数、唯一、不可变、严格递增，canonical 追加时赋值；允许间隙。
- 新世界 WorldCreated 的位置为 1，游标初始化和事件、投影、回执同事务；失败无残留。
- 多事件命令遵循 handler 的固定 event list 顺序：PlayerCreated 在 PlayerPlaced 前，ObservationRecorded 在 KnowledgeAcquired 前；ordinal 是命令内部身份，position 是世界内历史顺序。
- 读取/重建只能 `ORDER BY ledger_position ASC`，不得按逻辑时间、现实时间或 UUID 排序；相同时间坐标及回退的现实时间均不改变 canonical 顺序。
- 位置保存在 persistence record 和不可变 [CanonicalEvent envelope](../../services/core/src/livingworld/application/ledger.py)；Domain 不获得分配器，EventId 仍是独立事件身份。
- 旧历史经核验普通 SQLite rowid 与追加路径后，每世界 `_rowid_ ASC` 一次性回填 1..N。**legacy migration order != future canonical replay semantics**；未知旧顺序明确失败，无 timestamp/UUID fallback。
- 原 UPDATE/DELETE/REPLACE 保护覆盖位置；重建从不修改事件或解除触发器，也不产生回执。

13 类已发出的 v1 payload 均已在实现前逐项核验，可以从 ledger 恢复已有 Stage 2 状态，不依赖当前投影。知识命令产生的 assertion-target Observation 身份、owner/source/provenance、值与时间直接来自 payload，ObservationId 保留，不重新生成。C-006B event-target Observation 不是从事件 payload 重建的投影，而是原子提交并原样保留的发生时授权记录。按 `(event_type, payload_version)` 显式分发，未知类型/版本、非法 payload、顺序或约束失败会完整回滚。审计目录和重建边界见 [REPLAY_MODEL.md](REPLAY_MODEL.md)，迁移与原子分配见 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。

## 2. 候选的语义生命周期

以下词语描述语义，不是已确定的代码状态名或完整状态机。

| 处理 | 含义 | 是否成为该候选描述的世界事实 |
| --- | --- | --- |
| 进入候选集合 | 某个可能事件被纳入 World Plan / Event Reservoir | 否。 |
| 激活 | 候选被传统程序正式转为实际发生的 WorldEvent | 是；事实可见性仍需单独判断。 |
| 延期 | 暂不发生，留待后续处理 | 否；延期本身不证明角色已经执行候选动作。 |
| 取消 | 不执行该候选安排 | 否；不能将被取消的情节写成已发生历史。 |

处理过程可以需要决策 Trace，但“系统处理过候选”的开发者记录，不等于候选描述的剧情已经发生。延期和取消是否还能重新纳入其他计划、何时失效，以及具体状态转换，尚待定义。

## 3. 规划与执行责任

1. Director 负责世界事件与宏观剧情调度（FR-02），采用批量 World Plan + Event Reservoir（FR-13）。
2. Event Reservoir 中候选的激活、延期或取消由传统程序完成（FR-14）。
3. 禁止为每个普通小事件单独调用 LLM（FR-13）。
4. Planning Window 耗尽或大量计划失效才触发 Replan（FR-15）。本文不增设其他触发条件，也不自行给出窗口长度或失效阈值。

候选是否可被激活需要保持冻结约束，例如玩家任意时刻只能存在于一个物理地点（FR-06）。激活条件怎样表达、冲突如何解决、失败如何恢复，本阶段均不选择实现方案。

## 4. 发生与获知是两个判断

世界真实事实、Character Knowledge 和 Player Knowledge 分离（FR-04）。因此必须区分：

| 判断 | 回答的问题 |
| --- | --- |
| 事实判断 | 事件是否已经实际发生；若来自候选，是否已激活？ |
| 知识归属判断 | 哪个角色或玩家已经获知了什么？ |
| 玩家展示判断 | 该内容能否向当前玩家展示？ |

后台发生但玩家不知道的事件不能直接展示给玩家（FR-05）。角色也不能因为事件已发生或 Director 知道它，就自动获得相应 Character Knowledge。知识如何经由观察、对话等途径获得，见 [KNOWLEDGE_MODEL.md](KNOWLEDGE_MODEL.md)；具体规则尚待进一步定义。

角色拥有的记忆同样不能直接装入尚未发生候选所描述的经历，见 [MEMORY_MODEL.md](MEMORY_MODEL.md)。本文区分“对未来安排的了解”和“对已发生经历的记忆”，不将两者等同。

### 概念例子：广场相遇

- **候选：** 计划安排两位角色稍后在广场相遇。此时相遇尚未发生。
- **延期或取消：** 如果候选被延期或取消，不能出现“他们已经在广场见过面”的事实或经历记忆。
- **激活：** 候选激活后，相遇成为 WorldEvent；它对世界的影响才属于已经发生的内容。
- **获知：** 玩家不知情时，不能直接向玩家展示这场后台相遇。后续获知的内容与范围必须另外判定。

例子只解释概念，不定义观察距离、传播规则、调度算法或 UI。

## 5. 主动联系相关事件

主动联系属于世界调度的一部分，候选安排仍须经过实际执行与知识边界判断，不能把“计划联系”当作“已经联系”。

- 玩家具有 Busy / Available 状态（FR-08）。Busy 时 Director 不得发起非必要主动联系（FR-09）；Available 时可以安排一个角色或一组角色主动联系（FR-10）。
- 同一个主动联系理由最多主动发送一次，玩家未回复不能持续催促（FR-11）。该规则在候选延期、重新规划或多角色组织时也必须保持，具体身份与计数语义待确认。
- 多角色主动联系围绕统一目的形成 Outreach Episode（FR-12）。Episode 与一个 CandidateEvent、一个 WorldEvent、一个 Conversation 或一条 Message 是否一一对应，尚未确定。
- Director 调度事件与联系目的，不能直接替 Character Agent 编写最终对玩家台词。

是否已安排、是否已发生联系以及哪些 Message 已实际呈现给玩家，是需要区分的概念；本阶段不定义投递机制或失败重试策略。

## 6. 时间线、记录与成本边界

- 世界支持 Checkpoint 与 Timeline Branch（FR-22）。同一个候选在一个分支中的处理，不能仅凭名称被当作另一分支已经发生的事实；分支的继承、恢复和回滚规则仍需明确。
- Developer Mode 能查看 Director、Agent、Memory、LLM 使用等决策 Trace（FR-23）。候选激活、延期、取消与 Replan 的依据属于需要说明的决策范围；Trace 的具体内容和保留方式未确定。
- 产品必须记录 Token、Latency 和 Cost，并支持预算与模型路由（FR-24）。候选执行与 LLM 调用是不同概念，不能将每个普通小事件处理都推导成一次 LLM 调用。

持久化方向见 [Architecture Review 001](ARCHITECTURE_REVIEW_001.md)，存储细节见 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)，事务见 [COMMAND_MODEL.md](COMMAND_MODEL.md)，内部投影回放见 [REPLAY_MODEL.md](REPLAY_MODEL.md)。事件总线、队列与候选执行未实现。

## 7. 待确认的产品定义

| 问题 | 需要澄清的范围 |
| --- | --- |
| 激活边界 | 何时判定候选已激活、世界影响已成立；执行失败是否允许部分影响。 |
| 事件来源 | 是否所有 WorldEvent 都先进入候选阶段；玩家即时行为如何形成事实。 |
| 候选冲突 | 多个候选争用角色、地点或其他世界条件时的裁决原则；不预设优先级算法。 |
| 延期与取消 | 延期的期限、取消的终局性、候选失效原因，以及重新规划时的衔接方式。 |
| Replan 条件 | Planning Window “耗尽”的含义；“大量计划失效”的范围与阈值。 |
| 事件粒度 | 一次相遇、关系变化、多人联系与 WorldEvent 之间怎样划分。 |
| 主动联系计数 | 同理由身份与作用域；多人 Episode 的一次发送边界；投递失败和未回复如何区分。 |
| Busy 必要性 | 必要联系的定义，以及激活前玩家状态变化的处理。 |
| 事实影响与更正 | 事件影响、关系变化如何对应；错误激活、回滚或更正的产品语义。 |
| Checkpoint / Timeline | 候选、已发生事件、知识、记忆和联系去重记录的继承与恢复范围。 |
| 可观察性 | Trace 中可查看哪些事实和决策，开发者信息怎样与普通玩家可见内容保持边界。 |


## 2026-09-29 当前实现核对

上方 Stage 0 概念范围不是当前代码的完整能力清单。ActionResolution 已有确定性 PlayerMoved 与原子 event-time Observation；scheduler/activation 与 Scene 的实现见各自架构文档。本轮只新增已授权观察的有限中文展示和角色回复输入，沿用现有时间线及聊天话题入口，没有提交新事件或消费 Activation/CandidateEvent。PlayerPlaced/CharacterPlaced 的详情模板只有存在合法亲历记录时才使用；setup 不自动创建这种记录。

WorldPlan、EventReservoir、候选批量消费、自动角色活动与 Outreach 尚未实现。事件展示不意味着这些能力已经完成，也不改变窗口/失效/重规划和主动联系计数待确认的规则。

## 当前日常候选（2026-09-29）

早期“Director/候选未实现”的状态只指当时切片。当前新增独立 operational director_plans/director_candidates 和 `CharacterRoutineStarted` v1，经已批准权限的 typed Kernel action 变成真实事件。未来候选不会进入普通事件 UI 或角色亲历；开始事件不证明任务成果或完成。本轮仍没有相遇剧情、主动联系或关系变化消费者。

## 离线消息与事实时间

离线补生成的私聊属于通信记录，不是历史WorldEvent。剧情显示时间不覆盖真实created_at_utc，不改变世界账本顺序，不补造活动成果或知情。该时间严格位于持久离线区间，来自离线前受限输入；迟到资料/新玩家消息使结果失效。

## 2026-10-01：聊天记录与公共公告

chat_story_entries是当前玩家从聊天中获知的有出处说法，记录原句、类别、获知双时间及原话时间。保存／批注／隐藏不会发WorldTruth、Knowledge、Observation或Memory事件。普通聊天台词及用户绿色标记不是Kernel物理状态授权。

world_news_candidates是有限未发布公告候选；随机时序、公开背景引用和暂停状态由现有scheduler／Kernel验证。PublicWorldEventPublished v1表示这条公告已实际发布；payload只含entry_id、batch_id、player_id、title、body、time_text，双时间在事件envelope。EventAppender和候选发布状态在同一事务，使用由候选ID推导的稳定事件／请求／幂等键。回放核对同世界玩家及字段而不改变物理状态／知识／记忆。正文中传闻、邀请、未来活动仍只是公开信息内容，不借公告事件宣称其结果已发生。用户的already-experienced／skipped是带revision的应用数据处理状态，不是canonical世界经历。

具体范围见[已批准方案](../proposals/2026-10-01-world-event-journal.md)。
