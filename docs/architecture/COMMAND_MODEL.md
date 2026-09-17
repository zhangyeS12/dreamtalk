# C-003C：Command Transaction & Idempotency Pipeline

状态：已实现 Python application 层命令及 SQLite 事务管线。业务 HTTP API、replay、完整乐观并发冲突处理、Director、Agent、知识变更和 catch-up 未实现。系统 API 与桌面协议不变。

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
| MovePlayer | 玩家、当前 Presence 与同世界目标地点存在；替换唯一位置并递增 Presence revision | 0: PlayerMoved |
| CreateCharacter | 建立角色静态身份，目标身份未使用 | 0: CharacterCreated |
| PlaceCharacter | 同世界角色与地点存在；首次建立状态 revision=0，后续替换递增版本 | 0: CharacterPlaced |
| ChangeRelationship | 双方存在且同世界；仅改变 source→target 的内部指标 | 0: RelationshipChanged |

**玩家创建歧义已解决：** 成功创建的普通玩家必须有初始物理地点。命令接收 initial_location_id、activity_state、availability_state，复用 PlayerActivity/PlayerAvailability；默认 active/available。inactive 保留地点，不自动产生见证。指纹使用默认值解析后的完整语义值。

**关系变化歧义已解决：** RelationshipMetrics 是不可变整数值：affinity、trust 范围 [-100,100]，familiarity 范围 [0,100]，分别表示态度、信任、熟悉程度。仅供内部模拟，普通玩家不获得好感分数 UI。

ChangeRelationship 携带三个整数 delta，至少一个非零；领域逻辑相加后重新校验范围，不静默 clamp。不存在的有向边以三项 0、revision=0 为初态，应用 delta 后保存 revision=1。反向边独立，不自动创建或修改。无额外维度、标签、恋爱或评分系统。

## 3. 返回结果与持久化幂等

[CommandResult](../../services/core/src/livingworld/application/results.py) 包含 request_id、command_type、具体实体引用（关系使用双方有向引用）、resulting_revision、replayed。replayed=False 表示本次新提交；True 表示返回已有回执结果。调用方不接触 ORM/session，也无需查询实现表重建结果。

RequestId 标识一次命令操作。新管线全局查找回执；跨命令类型或跨世界复用同一 RequestId 也需匹配完整语义。DB 为具有 command_fingerprint 的新回执建立 request_id partial unique index；旧 C-003B 审计快照保持原状。旧回执没有可验证指纹或存在歧义时，显式 IdempotencyConflictError，不伪装成已执行成功。

[fingerprints.py](../../services/core/src/livingworld/application/fingerprints.py) 对明确列举的语义输入生成带 fingerprint_version=1 的 canonical JSON，再计算 SHA-256。包含命令类型、世界、具体目标身份、名字、位置/状态或 delta；ID 保留类型和世界作用域。Decimal 用精确十进制标准形式，1 与 1.000 具有相同语义。JSON 按 key 排序、紧凑 UTF-8、拒绝非有限浮点数。

指纹排除 RequestId 自身、生成的现实时间、session、内存地址和当前可变投影。相同请求且指纹相同，直接返回持久化原始结果；即使后续独立命令改变当前状态，返回的仍是原结果。相同请求但指纹不同，显式 IdempotencyConflictError，不写新事件或投影。

回执沿用领域 CommandReceipt。0003 在原表增加独立 command_fingerprint 和 versioned result_payload；指纹不藏在结果引用中。result_reference 指向该命令最后一个事件，原始实体/版本结果另行保存；多事件属于同一回执。

## 4. 事件身份、因果与双时间

每个事件 payload_version=1，显式保存语义事实，不能倾倒整个领域/ORM 对象。事件目录和 payload 见 [EVENT_MODEL.md](EVENT_MODEL.md)。

- key = `request_id:ordinal`，ordinal 对命令固定，创建玩家稳定为 0、1。
- EventId 用 RequestId UUID 作为 UUIDv5 namespace，world_id 与 ordinal 构成名称；失败重试不更换事件身份。身份不是 WorldTime，也不是回放顺序。
- causation_id = RequestId；correlation_id = CorrelationId(RequestId.value)，关联顶层操作，不引入分布式追踪系统。
- occurred_at 来自现有 WorldClock.logical_time；CreateWorld 使用其初始 WorldTime。
- created_at 与回执 UTC 时间来自注入的 WallClock；实现集中在 [SystemWallClock](../../services/core/src/livingworld/infrastructure/clock.py)，拒绝 naive，aware 输入归一化 UTC。

时间戳不作为唯一 canonical sequence。未实现世界时间推进、日历、catch-up 或分支归属。

## 5. UnitOfWork 与原子失败

[ports.py](../../services/core/src/livingworld/application/ports.py) 定义 World/Location/Player/Character/Relationship repository、EventAppender、CommandReceiptRepository、WallClock 和 UnitOfWork。仅暴露任务需要的操作，没有通用 save(anything)、SQL execute 或 session。

[SqlAlchemyUnitOfWork](../../services/core/src/livingworld/infrastructure/persistence/unit_of_work.py) 从 Database 的集中 session factory 创建一次执行的 session，所有能力共享它。handler 仅在事件、投影和回执均写入后显式 commit；异常或未提交退出 rollback，最后关闭 session。

事件 append 后、投影完成后、回执写入后、commit 前均可失败。真实 SQLite 故障注入测试重新打开 session/engine 后验证：没有部分事件、部分投影或成功回执。未提交 RequestId 不被占用，相同命令可合法重试；成功后重试（包括 engine/Core 重启）不增加事件、投影或 revision。

## 6. 明确的后续边界

当前表是 projections/current state；Replay is not implemented yet. Full optimistic concurrency enforcement is not implemented yet.

领域 Revision.advance 保持已有版本检查，MovePlayer/关系变更递增当前状态版本。DB 层 expected-revision 条件更新、并发冲突分类/重试和 canonical replay order 留给 C-003E；本阶段的当前快照写入不是最终 last-write-wins 政策。并发数据库写入失败显式失败并回滚，不自动重试或把不同命令当成成功。

迁移与只追加触发器见 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。测试见 [命令集成测试](../../tests/application/test_commands.py) 和 [迁移回归](../../tests/persistence/test_command_migration.py)。本阶段不增加业务 HTTP API、知识命令、Director、Agent、检索、UI 或模拟。
