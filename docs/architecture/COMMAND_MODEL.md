# Command Transaction, Idempotency & Concurrency（C-003C～C-003E2）

状态：Stage 2 命令事务、持久化幂等、主体知识隔离、canonical ledger、回放及资源级乐观并发已实现。C-006B 复用同一事务/receipt/CAS 约定建立 action resolution 和 Scene lifecycle；C-006D 为外部 time-sensitive mutation 增加 catch-up barrier，并从共享 monotonic WorldTimeSource 捕获发生时间。业务 HTTP API、Director、Agent 与自动知识传播未实现。系统 API 与桌面协议不变。综合验证见 [STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)、[ACTION_RESOLUTION.md](ACTION_RESOLUTION.md) 与 [CLOCK_RECONCILIATION.md](CLOCK_RECONCILIATION.md)。

## 1. 唯一生产变更入口

```text
Command
→ application handler
→ domain validation
→ WorldEvent
→ projection mutation
→ CommandReceipt
→ single transaction commit
```

[CommandHandler](../../services/core/src/livingworld/application/command_handler.py) 是本阶段确定性世界变更入口，承担首批 Kernel 执行职责；没有引入另一个模拟框架。生产 snapshot store 只读，原 C-003B 原始写入工具已移至 [测试辅助](../../tests/persistence/snapshot_support.py)，仅用于映射与数据库约束验证。LLM、Director 或外部提案不能直接提交事实。

所有事件、当前状态和成功回执同处一个 SQLAlchemy session/transaction。flush 不代表提交。CreateWorld 因事件的 world FK 必须先在同一事务内写入 World/WorldClock，之后追加事件；任一步失败仍全部回滚，没有提前提交。

## 2. 命令及已解决语义

[commands.py](../../services/core/src/livingworld/application/commands.py) 使用现有 RequestId 与具体领域身份。创建目标 ID 由调用方提供，每个命令携带 world_id。

| Command | 校验与变更 | 事件及固定 ordinal |
| --- | --- | --- |
| CreateWorld | 创建 World 和独立双时间 WorldClock；不隐式创建其他实体 | 0: WorldCreated |
| CreateLocation | 世界存在，目标身份未使用，同世界 | 0: LocationCreated |
| CreatePlayer | 世界与初始地点存在且同世界；原子创建 Player 与 PlayerPresence | 0: PlayerCreated；1: PlayerPlaced |
| MovePlayer | legacy compatibility command；适配为 `PLAYER_INPUT` 的 `move_player` v1 ActionProposal，由 ActionResolution 统一验证并 CAS 更新唯一位置 | 0: PlayerMoved（仅由 action pipeline 提交） |
| SetPlayerAvailability | 更新当前世界玩家的 Busy / Available；需要 expected_presence_revision，保留地点/activity，revision CAS | 0: PlayerAvailabilityChanged |
| CreateCharacter | 建立角色静态身份，目标身份未使用 | 0: CharacterCreated |
| PlaceCharacter | 必填 expected_state_revision: Revision \| None；None 期待不存在，首次 revision=0；已有状态 CAS +1 | 0: CharacterPlaced |
| ChangeRelationship | 必填 expected_relationship_revision: Revision \| None；仅改变 source→target，缺失边须显式期待不存在 | 0: RelationshipChanged |
| AssertWorldTruth | 可信内部调用；世界存在，断言 ID 未使用，scope=truth/owner=None | 0: WorldTruthAsserted |
| FormCharacterBelief | 可信内部调用；新断言仅归属一个现存同世界 Character；可无 source、可与 Truth 矛盾；无自动 Observation | 0: CharacterBeliefFormed |
| AcquireKnowledge | 可信内部合法渠道；世界/接收方/源断言存在且同世界，派生 ID 未使用 | 0: ObservationRecorded；1: KnowledgeAcquired |

C-006B 的 `ResolveAction` 不是并列的 mutation engine：typed proposal 经 allowlisted deterministic resolver 后，复用同一 WorldEvent、ledger allocator、repository CAS、ObservationAppender 和 CommandReceipt transaction。Q-001A 起，当前 `move_player` v1 是普通 Player fictional movement 的唯一 commit path；legacy `MovePlayer` 只做输入/结果兼容适配，不再拥有 event/projection write。`CreatePlayer` 的 initial placement 仍是 setup，不被重定义为玩家行动。Scene create/join/leave/end 使用相同 RequestId fingerprint/receipt convention，但作为内部 runtime state 操作不伪造 player-visible WorldEvent。

**玩家创建歧义已解决：** 成功创建的普通玩家必须有初始物理地点。命令接收 initial_location_id、activity_state、availability_state，复用 PlayerActivity/PlayerAvailability；默认 active/available。inactive 保留地点，不自动产生见证。指纹使用默认值解析后的完整语义值。

**关系变化歧义已解决：** RelationshipMetrics 是不可变整数值：affinity、trust 范围 [-100,100]，familiarity 范围 [0,100]，分别表示态度、信任、熟悉程度。仅供内部模拟，普通玩家不获得好感分数 UI。

ChangeRelationship 携带三个整数 delta，至少一个非零；领域逻辑相加后重新校验范围，不静默 clamp。不存在的有向边以三项 0、revision=0 为初态，应用 delta 后保存 revision=1。反向边独立，不自动创建或修改。无额外维度、标签、恋爱或评分系统。

## 3. 返回结果与持久化幂等

[CommandResult](../../services/core/src/livingworld/application/results.py) 包含 request_id、command_type、具体实体引用（关系使用双方有向引用）、resulting_revision、replayed。replayed=False 表示本次新提交；True 表示返回已有回执结果。调用方不接触 ORM/session，也无需查询实现表重建结果。

RequestId 标识一次命令操作。新管线全局查找回执；跨命令类型或跨世界复用同一 RequestId 也需匹配完整语义。DB 为具有 command_fingerprint 的新回执建立 request_id partial unique index；旧 C-003B 审计快照保持原状。旧回执没有可验证指纹或存在歧义时，显式 IdempotencyConflictError，不伪装成已执行成功。

[fingerprints.py](../../services/core/src/livingworld/application/fingerprints.py) 对明确列举的语义输入生成带 fingerprint_version=1 的 canonical JSON，再计算 SHA-256。包含命令类型、世界、具体目标身份、名字、位置/状态或 delta；ID 保留类型和世界作用域。Decimal 用精确十进制标准形式，1 与 1.000 具有相同语义。JSON 按 key 排序、紧凑 UTF-8、拒绝非有限浮点数。

指纹排除 RequestId 自身、生成的现实时间、session、内存地址和当前可变投影。相同请求且指纹相同，直接返回持久化原始结果；即使后续独立命令改变当前状态，返回的仍是原结果。相同请求但指纹不同，显式 IdempotencyConflictError，不写新事件或投影。

回执沿用领域 CommandReceipt。0003 在原表增加独立 command_fingerprint 和 versioned result_payload；指纹不藏在结果引用中。产生事件的命令 result_reference 指向最后一个事件，原始实体/版本结果另行保存；多事件属于同一回执。0012 允许 typed rejected action 和 Scene result 在 completed receipt 中没有虚构事件引用；这不会把拒绝或 engine lifecycle 伪装成 WorldEvent。

C-003D 结果新增 KnowledgeAssertionId 实体引用和可选 ObservationId，versioned JSON 保存原 ID；旧结果没有 observation_id key 时兼容为 None。ObservationId 不从 RequestId 推导，运行时由每次新执行生成独立 UUIDv4；成功重试先读取 receipt，不生成新 occurrence。完全回滚可在后续合法执行生成新身份。

知识指纹包含完整源/目标/接收方、渠道、已解析认知标签和明确 confidence；真相指纹还包含冻结 proposition 和有效期输入。witnessed 默认 observed，其余显式渠道默认 reported，构造命令时解析后再 fingerprint；confidence 默认 None。运行时生成的 ObservationId 不参与指纹。真相 valid_from 未提供时在新执行取现有世界逻辑时间；指纹记录“采用执行时世界时钟”的 None 输入，不读取当前时钟来重算已提交请求指纹。知识政策与权限边界见 [KNOWLEDGE_ACCESS_MODEL.md](KNOWLEDGE_ACCESS_MODEL.md)。

## 4. 事件身份、因果与双时间

每个事件 payload_version=1，显式保存语义事实，不能倾倒整个领域/ORM 对象。事件目录和 payload 见 [EVENT_MODEL.md](EVENT_MODEL.md)。

- key = `request_id:ordinal`，ordinal 对命令固定，创建玩家稳定为 0、1。
- EventId 用 RequestId UUID 作为 UUIDv5 namespace，world_id 与 ordinal 构成名称；失败重试不更换事件身份。身份不是 WorldTime，也不是回放顺序。
- causation_id = RequestId；correlation_id = CorrelationId(RequestId.value)，关联顶层操作，不引入分布式追踪系统。
- occurred_at 来自共享 WorldTimeSource 对当前 WorldClock 的 monotonic effective time；CreateWorld 使用其初始 WorldTime。同一 command 的全部事件/观察/投影使用一次 captured 值。
- created_at 与回执 UTC 时间来自注入的 WallClock；实现集中在 [SystemWallClock](../../services/core/src/livingworld/infrastructure/clock.py)，拒绝 naive，aware 输入归一化 UTC。

时间戳不作为唯一 canonical sequence。C-006D 已实现 clock progression 与 trigger catch-up；日历、recurrence、Timeline 分支归属和 cognition catch-up 未实现。

## 5. UnitOfWork 与原子失败

[ports.py](../../services/core/src/livingworld/application/ports.py) 定义 World/Location/Player/Character/Relationship/Scene focused repository、内部 exact-source KnowledgeMutationRepository、ObservationAppender、EventAppender、CommandReceiptRepository、WallClock 和 UnitOfWork。主体查询另用只读绑定 reader，不获得内部 mutation repository。仅暴露任务需要的操作，没有通用 save(anything)、SQL execute 或 session。

[SqlAlchemyUnitOfWork](../../services/core/src/livingworld/infrastructure/persistence/unit_of_work.py) 从 Database 的集中 session factory 创建一次执行的 session，所有能力共享它。handler 仅在事件、投影和回执均写入后显式 commit；异常或未提交退出 rollback，最后关闭 session。

事件 append 后、投影完成后、回执写入后、commit 前均可失败。真实 SQLite 故障注入测试重新打开 session/engine 后验证：没有部分事件、部分投影或成功回执。未提交 RequestId 不被占用，相同命令可合法重试；成功后重试（包括 engine/Core 重启）不增加事件、投影或 revision。

## 6. 资源级乐观并发

```text
resolved command semantics / fingerprint（包含 typed expected revision）
→ 已提交 receipt 检查（优先于版本检查）
→ 验证资源自己的存在性与版本
→ 领域新快照 + canonical events
→ SQL CAS / 期待缺失的 INSERT
→ receipt
→ atomic commit
```

Presence、CharacterState、Relationship 各有自己的 Revision；没有全局 World revision 来裁决这些命令。普通创建和不可变知识断言创建不接收 expected revision。

- MovePlayer 必须提供 Revision；不能传 raw int 或 None。
- PlaceCharacter / ChangeRelationship 必须显式提供 None 或 Revision。None 只代表期待缺失；Revision(0) 期待已有的零版本，不能冒充缺失。
- expectation 不匹配抛出现有 ConcurrencyConflictError，包含 resource kind / typed identity / expected revision；已读出的 actual 可附带。CAS rowcount=0 不额外查询 actual。
- 更新 SQL 的 WHERE 同时包含完整同世界主键和 revision=expected，只有 rowcount=1 成功；resulting revision 必须恰好 +1。缺失创建使用 INSERT，真实 PK/UNIQUE 竞争归类为同一 ConcurrencyConflictError。
- 不自动重读新版本并重新执行语义命令。事件、游标分配、投影、成功回执在冲突时全部回滚；不会生成“尝试失败” WorldEvent。反向关系独立。

SQLite adapter 在命令 UoW 首次读取前使用 BEGIN IMMEDIATE 取得物理写入资格，避免 deferred read→write 的 BUSY_SNAPSHOT；read-only store / knowledge reader 仍用普通 BEGIN。SQLite 物理写入可串行，但 unrelated resource 的 expected revisions 不相互失效。正确性仍由 SQL CAS 保证，不只依赖 SQLite 的单 writer；未来其他 adapter 需保留 CAS 和冲突分类。

成功请求再次提交其原 expected revision 即使现已过期，也先由 receipt 返回原结果；同 RequestId 改动 expected revision 或其他语义仍是 IdempotencyConflictError。新字段纳入这些 mutable command 的显式语义指纹，其他创建/知识命令指纹保持原定义。旧的无 precondition 指纹不被猜测转换为新命令语义；旧回执、结果和事件原样保留。

## 7. 并发重复请求的有限碰撞解析

独立 UoW 执行相同请求时只允许一组事实及一个回执。正常路径第二个 SQLite writer 从已提交 receipt 返回原结果。若初次 lookup 与唯一性/版本竞争相撞，失败 UoW 必须先退出并 rollback，再开一个 fresh UoW **仅执行一次 receipt.existing(request_id, fingerprint)**：匹配则返回原结果，不匹配则幂等冲突，仍无回执则保留原冲突。

该分支不会调用第二次 mutation，不产生新身份/事件，不使用循环或自动 semantic retry。Event/Receipt 身份竞争、可选状态 INSERT 竞争和显式创建目标竞争均可经此有限查证；FK/CHECK 等其他 IntegrityError 不伪装成 expected concurrency。

## 8. 内部信念形成路径（已确认）

provenance 查证使用独立可信 EventReferenceReader，仅有 exists(EventId)，没有全局 list/history query；只交给内部 command UoW，不分发给 principal。EventAppender 继续只有 append，read/write 能力不混合。

FormCharacterBelief 使用现有 KnowledgeAssertionId、CharacterId、WorldTime、Decimal 和 JSON value。必填 proposition / epistemic_status / valid_from，confidence、valid_to、source_assertion_id、provenance_event_id 可选。缺省 source/provenance 保留 None，显式引用必须同世界且已存在。

命令建立新的 immutable `character_belief`，owner 恰为给定角色，没有 player owner。Truth 不要求存在，不匹配也不拒绝或自动调和；源断言可私有，保留引用不赋予读取源存储的权限。显式 provenance 完整保存，不改写成形成事件身份。CharacterBeliefFormed 保存全部断言语义并与投影/回执原子提交，结果 ObservationId=None。

AcquireKnowledge 继续是 source → Observation → 自有派生 assertion，保留源 proposition。它可转述 false belief，但不能升级成 truth；inferred acquisition 的既有拒绝政策不变。没有自动推理或 Observation→Belief 联动。

## 9. 明确的后续边界

当前表是 projections/current state；内部 ProjectionRebuilder 只从 canonical ledger 恢复可回放投影，不是第二个世界事实写入口，不调用命令 handler、不生成事件/回执。CommandReceipt 保持原样以继续保证成功请求重试。见 [REPLAY_MODEL.md](REPLAY_MODEL.md)。

既有 v1 mutable event payload 已再次审计：PlayerMoved/CharacterPlaced 的原位置及 resulting revision，RelationshipChanged 的 edge_existed、before/delta/after 及 resulting revision，配合此前 ledger fold 足以恢复 previous revision 和验证递增。保留原 payload_version=1，不改写历史。Canonical order 由每世界事务游标提供，事件按 handler ordinal 顺序获得位置；成功幂等重试不再分配。

迁移与只追加触发器见 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。测试见 [命令集成测试](../../tests/application/test_commands.py)、[知识事务测试](../../tests/application/test_knowledge_access.py) 和 [迁移回归](../../tests/persistence/test_command_migration.py)。本阶段不增加业务 HTTP API、Director、Agent、语义检索、UI 或模拟。
