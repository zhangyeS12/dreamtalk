# C-003D：Knowledge Access Isolation

状态：已实现 Python 内部端口、SQL 权限隔离与显式获知事务，C-003E2 增加独立主观信念形成入口。没有业务 HTTP API、Memory、RAG、Director、Agent 或自动推理。

## 1. 能力绑定与信任边界

**EXISTENCE IN DATABASE != KNOWLEDGE OF A PRINCIPAL**。

[应用端口](../../services/core/src/livingworld/application/ports.py) 返回不可变领域 KnowledgeAssertion，不暴露 Session/ORM。三个 reader 均只有 get(assertion_id)、list()，调用时不能传入任意 owner/scope 来扩大范围。

| 能力 | 绑定于 | SQL 条件 |
| --- | --- | --- |
| WorldTruthReader | WorldId；可信权威世界层 | world_id + scope=truth + 两个 owner IS NULL |
| CharacterKnowledgeReader | CharacterId | world_id + scope=character_belief + owner_character_id=绑定角色 + player owner IS NULL |
| PlayerKnowledgeReader | PlayerId | world_id + scope=player_knowledge + owner_player_id=绑定玩家 + character owner IS NULL |

[基础设施实现](../../services/core/src/livingworld/infrastructure/persistence/knowledge_readers.py) 在 SELECT 的 WHERE 中强制条件；get 再增加 assertion_id，不绕过绑定条件。跨世界 typed ID 在发查询前拒绝；相同 UUID 的不同世界仍隔离。已有 owner 索引复用，无新搜索索引。

[Database](../../services/core/src/livingworld/infrastructure/persistence/engine.py) 的 factory 属于可信 composition：未来根据已验证身份绑定 reader 后，只把对应端口交给上下文消费者。当前不实现登录、传输鉴权或 Python 插件沙箱；端口隔离不宣称恶意任意 Python 代码不可访问进程内 Database。内部 exact-source mutation repository 与 read-only snapshot inspection 属权威基础设施能力，不分发给 principal。没有 list_all_knowledge 或全局读取后 Python 过滤路径。

未来 Director/world 层仅因拥有 TruthReader 不会获得私有信念；未来 Agent 只用绑定角色已授权结果。扩展授权要求独立未来决策，本任务不实现。

## 2. 真相写入

AssertWorldTruth 仅由可信内部应用提交，经 [CommandHandler](../../services/core/src/livingworld/application/command_handler.py)：

```text
校验世界和新 AssertionId
→ ordinal 0 WorldTruthAsserted
→ scope=truth / owner=None 的 KnowledgeAssertion
→ CommandReceipt
→ 同一事务 commit
```

subject/predicate/value、明确认知标签、精确 confidence、WorldTime 有效期进入语义事件。provenance_event_id 指向该事件。创建断言本身不向任何角色/玩家赋予知情。

## 3. 显式获知桥梁

### C-003E2：内部形成与暴露渠道分离（已确认）

```text
FormCharacterBelief（可信内部命令，非玩家 API）
→ 世界、现存 Character owner、新 AssertionId、可选同世界 source/provenance 校验
→ ordinal 0 CharacterBeliefFormed
→ KnowledgeAssertion(scope=character_belief, owner=单一 Character)
→ CommandReceipt
→ 同一事务 commit
```

此入口允许没有 source、没有对应 Truth 或与 Truth 矛盾的命题；推断/猜测/误认可由未来调用方提供，当前不实现形成这些判断的算法。复用 subject/predicate/value、现有 epistemic_status 与 Decimal confidence，显式 WorldTime valid_from / 可选 valid_to，optional source/provenance 原样保存，缺省 None。

来源提供时只验证存在且同世界，不要求 proposition 一致；来源的私有 owner 不改变接收角色的权限。显式 provenance 引用必须是既有同世界 event。两类引用不授予来源存储的 reader，事件仍是内部 canonical history。

该 exact provenance 校验由独立内部 EventReferenceReader 完成，不为角色/玩家增加全局事件读取能力；EventAppender 的 append-only API 保持不变。

**FormCharacterBelief 不自动创建 Observation**：内部形成不是默认 exposure channel。断言是新 immutable epistemic record，不引入 expected revision、修改既有信念或自动纠正。AcquireKnowledge 继续保持下述 source → Observation → receiver-owned assertion；它可以将 Alice 的 false belief 转述给 Billy，而不改写 WorldTruth。

**C-006B event perception 不自动创建 KnowledgeAssertion**：`Observation(target_id=EventId, channel=witnessed, basis=event_occurrence)` 只证明该主体在事件发生时具有访问依据。可空 basis 将 Kernel audience snapshot 与普通 Observation occurrence 区分，不改变 C-003D identity。它没有 proposition，也不授予 Truth/Belief/PlayerKnowledge；Stage 6 才能定义如何从事件感知形成认知或记忆。该 event-target Observation 是不可重算的历史授权快照，知识读取器不会因此越权遍历全局 WorldEvent。

Stage 2 验收以 AssertWorldTruth `door=locked` + FormCharacterBelief `Alice: door=unlocked` 创建两条 canonical state，隔离读者在重建前后仍分别返回 locked/unlocked。历史 stale Truth 可成为未来过时认知的一种来源，但不是本验收的 canonical 主观根机制。

AcquireKnowledge 表示权威应用已经确认渠道合法；当前消费者没有自行调用来扩权的公开 API，也不把地点、inactive Presence 或收到消息自动解释为获知证据。

```text
一个既有同世界源断言（truth / CharacterBelief / PlayerKnowledge）
→ 新 ObservationId，接收主体/渠道/源断言/世界观察时间
→ ordinal 0 ObservationRecorded
→ ordinal 1 KnowledgeAcquired
→ Observation + 新主体自有断言
→ CommandReceipt
→ 同一事务 commit
```

派生 assertion_id 显式提供；scope/owner 根据 receiver 的现有 typed ID 决定。保留 proposition；source_assertion_id 指源，provenance_event_id 指本次 KnowledgeAcquired。两个事件含同一 ObservationId；获知事件含完整派生语义元数据。来源私有断言本身不会成为接收方 reader 的可读记录，source 指针不构成权限继承。错误信念仍可与真相冲突，不纠正或晋升为 truth。

最小 deterministic policy：witnessed 默认 observed，其余显式渠道默认 reported，命令构造时解析默认标签再 fingerprint；可显式指定非空标签。confidence 默认 None 或显式有限 Decimal [0,1]，不复制来源置信度；有效期从本次世界逻辑时间开始、valid_to=None。领域仍可表示 inferred，本命令明确拒绝尚未定义推理政策的 inferred 执行。

## 4. 身份、幂等与迁移

ObservationId 标识 occurrence；RequestId 标识命令执行。运行时生成 UUIDv4，不由请求或坐标推导。相同坐标可有不同观察及不同派生断言，没有语义去重。

receipt 保存原 AssertionId、ObservationId 与 revision；相同 RequestId/规范语义直接返回原结果，不再生成 ID 或 INSERT。生成身份和执行时钟不参与 fingerprint；receiver、源/目标断言、渠道及解析后的元数据参与。请求变更语义显式冲突，重启后仍有效。完全回滚则没有成功 receipt 或持久化 ObservationId，合法重试可生成新身份。

0004_observation_identity 仅改变 Observation 身份存储。旧主键 tuple 规范 JSON（排序 key、紧凑 UTF-8、整数时间），固定 namespace UUIDv5；世界参与旧 tuple，UUID 本身仍使用现有编码。旧行语义、FK、CHECK 保留，主键变为 (world_id, observation_id)，没有坐标 UNIQUE。**legacy backfill identity != runtime identity generation**。Alembic 是唯一权威，降级需 review，未用实际用户 DB；详见 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。

## 5. 检索顺序与验证

```text
principal authorization
→ eligible assertion set
→ semantic / FTS / vector retrieval
→ ranking
→ context
```

严禁 global semantic search 后过滤，或全局断言加 Prompt secrecy。当前只实现 SQL 归属读取，不实现后面三层。

[知识集成测试](../../tests/application/test_knowledge_access.py) 保留秘密、私有 canary、SQL WHERE/绑定参数、拒绝 ID 无领域 materialization、角色转述、玩家知识、跨世界与回滚回归。旧隔离/映射测试的私有与矛盾 fixture 不作为 Stage 2 最终验收创建路径。

[信念形成测试](../../tests/application/test_belief_formation.py) 覆盖无源/无 Truth 根、矛盾命题、false belief 转述、optional 私有 source/provenance、完整 metadata 回放、无 Observation、重启幂等与故障回滚。[Stage 2 验收](STAGE_2_ACCEPTANCE.md) 只用受支持命令创建秘密及矛盾信念，证明 replay 前后 owner/world 隔离。[Observation 迁移测试](../../tests/persistence/test_observation_migration.py) 验证旧语义与确定性；[映射测试](../../tests/persistence/test_mapping.py) 验证同坐标不同 occurrence 与 typed ID round-trip。
