# C-003D：Knowledge Access Isolation

状态：已实现 Python 内部端口、SQL 权限隔离与显式获知事务；没有业务 HTTP API、Memory、RAG、Director、Agent 或自动推理。

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

[知识集成测试](../../tests/application/test_knowledge_access.py) 验证 Billy/Banyue/Belle/Player 秘密、私有 canary、SQL WHERE/绑定参数及拒绝 ID 无领域 materialization、角色转述、矛盾信念、玩家知识、跨世界、事件只追加、多个 flush 后故障回滚与重启幂等。[Observation 迁移测试](../../tests/persistence/test_observation_migration.py) 验证旧语义无损、确定性、迁移表替换后故障回滚；[映射测试](../../tests/persistence/test_mapping.py) 验证同坐标不同身份共存及 typed ID round-trip。私有/矛盾信念初始数据为隔离测试 fixture，不增加生产写入 API。
