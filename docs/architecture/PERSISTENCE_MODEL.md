# SQLite Persistence Mapping & C-003D Knowledge Isolation

状态：C-003B 建立 SQLite/Alembic，C-003C 建立命令事务和持久化幂等，C-003D 增加 SQL 主体知识隔离、显式获知事务和用户确认的 ObservationId。未实现完整乐观并发执行、回放、自动传播、语义检索或世界模拟。产品冻结规则不变，见 [COMMAND_MODEL.md](COMMAND_MODEL.md) 与 [KNOWLEDGE_ACCESS_MODEL.md](KNOWLEDGE_ACCESS_MODEL.md)。

## 1. 边界与生命周期

```text
domain（标准库、不可变领域快照）
  ↑
application
  ↑
infrastructure.persistence（SQLAlchemy / aiosqlite / Alembic）
  ↑
bootstrap（创建、初始化、最终释放 Database）
```

[models.py](../../services/core/src/livingworld/infrastructure/persistence/models.py) 中的 ORM Record 与领域 dataclass 完全分离。[mapping.py](../../services/core/src/livingworld/infrastructure/persistence/mapping.py) 对每个对象显式转换，重建具体 WorldId / CharacterId / PlayerId / EventId / KnowledgeAssertionId、Revision 和枚举；领域构造器再次校验并冻结 JSON。Domain 没有 SQLAlchemy、Alembic、SQLite 或 HTTP 依赖，由 [架构测试](../../tests/core/test_architecture.py) 保证。

[engine.py](../../services/core/src/livingworld/infrastructure/persistence/engine.py) 是唯一 AsyncEngine 与 async_sessionmaker 创建位置。Core 持有一个 Database，初始化成功后才发布 readiness，服务器关闭后 dispose。数据目录须为绝对 app-data 路径，源码/安装包资源目录拒绝使用；测试只使用隔离临时目录。

每条连接配置 WAL、foreign_keys=ON、recursive_triggers=ON 和 busy_timeout=5000；启动探测 FTS5，不创建搜索业务表。通过 sync_engine 的 connect/begin hooks 禁用驱动的隐式旧事务行为并显式发出 BEGIN，确保迁移 DDL 也参与外层事务。做法依据 [SQLAlchemy SQLite transaction control](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#enabling-non-legacy-sqlite-transactional-modes-with-the-sqlite3-or-aiosqlite-driver)。

SQL echo 默认关闭，hide_parameters=True；结构化日志继续沿用 allowlist，不记录 SQL 参数、secret、token、prompt 或会话内容。

## 2. 当前 schema

所有世界内引用用复合外键携带 world_id；无级联删除。主键的 world_id 前缀同时支持世界内查找，不重复建立同列索引。

| 表 | 身份 / 唯一性 | 持久化范围 |
| --- | --- | --- |
| worlds | world_id | 名称、Revision |
| world_clocks | world_id，FK worlds | WorldTime、UTC 观察时间、精确 time_scale、running/paused、Revision |
| locations | (world_id, location_id) | 名称、Revision |
| location_connections | (world_id, source_id, target_id) | 有序地点连接、Revision；两端须存在于同一世界 |
| players | (world_id, player_id) | 名称、Revision |
| player_presences | (world_id, player_id) | 唯一当前位置、active/inactive、busy/available、Revision |
| characters | (world_id, character_id) | 静态身份/名称、Revision |
| character_states | (world_id, character_id) | 唯一当前位置、Revision；与静态定义分离 |
| relationships | (world_id, source_kind, source_id, target_kind, target_id) | 有向主体边、Revision、内部 affinity/trust/familiarity；A→B 与 B→A 独立 |
| world_events | (world_id, event_id) | 类型、双时间、版本化 JSON payload、因果/关联/幂等信息 |
| knowledge_assertions | (world_id, assertion_id) | scope/owner、subject/predicate/value、认知标签、confidence、世界有效期、来源、Revision |
| observations | (world_id, observation_id) | 独立 occurrence 身份、显式观察坐标及可选 UTC 审计时间 |
| command_receipts | (world_id, request_id)；新命令 request_id partial unique | 类型、status、结果事件引用、UTC 创建/完成时间、Revision、独立语义指纹与原始结果 |

Observation 身份歧义已按用户确认解决：独立 typed ObservationId 沿用世界作用域 UUID 风格，不将 world_id 编码到 UUID。principal/target/channel/observed_at 仅描述语义坐标，不是 UNIQUE 身份；不同 ID 的同坐标记录可共存。运行时 UUIDv4 独立于 RequestId；成功重试从回执返回原 ID。没有历史 presence、Timeline 或分支政策。

主体与结果引用使用 kind + ID，并以专用 nullable FK 列区分 Character/Player、Event/Assertion。CHECK 要求选中 FK 非空、等于该 ID，其他分支为空，防止 SQLite CHECK 的 NULL 行为绕过引用验证。静态角色与角色状态只保存已有领域字段。

## 3. 双时间与其他精确编码

[types.py](../../services/core/src/livingworld/infrastructure/persistence/types.py) 定义统一编码：

- WorldTime：SQLite BIGINT/INTEGER，保存有符号 64 位整数微秒 `[-2^63, 2^63-1]`。绑定拒绝超范围值，不裁剪、不舍入、不转 float；CHECK typeof(...)=integer 与读取类型检查阻止非整数进入领域。Python WorldTime 本身仍无数据库范围限制，这是 SQLite adapter 的容量边界。
- 现实时间：保存 ISO-8601 TEXT，固定微秒精度和 `+00:00`。写入拒绝 naive 并归一化 UTC；读取拒绝 naive、无效或非 UTC 存储值，返回 aware UTC datetime，绝不静默补时区。可选时间保留 None。
- UUID：32 字符 hex 文本，读取还原 UUID，再由 mapper 恢复具体身份类型及世界作用域。相同 UUID 的 CharacterId 与 PlayerId 不合并。
- Decimal：十进制 TEXT，避免 SQLite 浮点转换损失 time_scale/confidence 精度。
- JSON：有限 JSON 的规范文本；JSON null 与 SQL NULL 区分，领域 value=None 可完整往返；事件 payload 与 knowledge value 在返回领域时递归冻结。

WorldTime 是逻辑坐标，不是 UTC，也不是事件唯一键；相同 WorldTime 可存储多个不同 EventId。没有日历、推进、catch-up 或现实/世界时间转换。SQLite 存储类型限制参考 [SQLite datatypes](https://www.sqlite.org/datatype3.html)。

## 4. Alembic 接管与审计语义

[migration.py](../../services/core/src/livingworld/infrastructure/persistence/migration.py) 仅属于 infrastructure/bootstrap。Alembic 是唯一迁移执行器，alembic_version 是唯一权威 cursor；原 C-002 Migration/migrate 自定义 runner 已移除。通过 AsyncConnection.run_sync 将已有事务连接交给 Alembic，参考 [Alembic asyncio integration](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic)。

| revision | 作用 |
| --- | --- |
| [0001_legacy_runtime_foundation](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0001_legacy_runtime_foundation.py) | 精确表示 C-002 schema_version / migration_history；保留旧 DDL 的 PK/nullability/CHECK 形状 |
| [0002_world_domain_persistence](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0002_world_domain_persistence.py) | 创建 13 个领域表、复合 FK、CHECK、必要索引和不可变事件触发器；草稿经人工审查，历史迁移只使用原生 SQL 类型 |
| [0003_command_pipeline](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0003_command_pipeline.py) | 原生 ADD COLUMN 增加关系三项指标、integer/range CHECK，旧行默认 0；原回执增加可空指纹/原始结果与配对 CHECK、新命令 RequestId partial unique index；不触碰事件及旧审计行 |
| [0004_observation_identity](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0004_observation_identity.py) | 仅增加 ObservationId 并确定性回填，SQLite batch 替换原坐标主键为 (world_id, observation_id)，保留所有语义列、行、FK/CHECK；无坐标 UNIQUE |

启动行为：

1. 空 DB：直接 Alembic upgrade head，依次执行 0001、0002、0003 与 0004。
2. 无 Alembic cursor 的 C-002 DB：只接受精确 legacy 表/列/PK/DDL、schema_version=(1,1)、一条匹配名称与 checksum 的历史记录和合法 UTC 审计时间；验证通过后 stamp 0001，再正常 upgrade head。旧迁移不重跑，已有行原样保留。
3. 已有 Alembic cursor：由该 revision 驱动升级；legacy 元数据只做一致性检查。不能用 schema_version 推算或选择待执行迁移。
4. 未知版本、checksum 漂移、缺失/损坏历史、结构差异、部分领域表、cursor 冲突或未知额外 schema 对象：抛出 MigrationCompatibilityError，事务回滚并停止启动；不自动修复、drop/recreate 或 stamp head。

**审计语义转换：** schema_version 继续保留 1，migration_history 保留旧基础迁移记录，即使 Alembic 已到 0004。两表是 C-002 兼容/历史证据，不反映当前领域 schema cursor；本阶段不追加或同步新 Alembic 审计记录。新库的 0001 建立等价基础记录，接管已有库时不改变 applied_at 或任何原有列。

0002 管理的数据库先按该历史 revision 的精确已知形状校验，再由 Alembic 执行 0003；结构检查不能自行选择或猜测迁移版本。部分增加指标或未知差异仍 fail closed。0003 的 downgrade 明确要求 review，因为删除已提交命令指纹会破坏重试安全，不自动丢弃幂等证据。

0002/0003 的历史 observations 形状仍按旧坐标主键校验，再交给 Alembic 执行 0004；0004/head 要求新身份列及主键。旧 ID 回填仅在迁移中：原 world_id/principal_kind/principal_id/target_kind/target_id/channel/observed_at tuple 使用排序 key、紧凑 UTF-8 JSON，固定 namespace UUIDv5，相同旧行始终得到相同 ID，不随机生成。**legacy backfill identity != runtime identity generation**。本次 SQLite batch recreate 只针对 observations，事件触发器不解除，升级与回填/表替换同事务。0004 downgrade 明确要求 review，不能静默丢弃同坐标多 occurrence。

Repeat startup 正常调用 Alembic upgrade head，不重放 revision、不重新 stamp、不重复插入审计记录。迁移接管与 DDL 同处一个事务，失败时旧库保持原状；不涉及实际用户库的自动修复工具。

## 5. 约束与低层 adapter

- Presence 与 CharacterState 的主键限制每世界/主体只有一条当前状态；location 非空、须属于该世界。inactive 不删除位置，不产生自动见证。
- Relationship 的有序复合主键保证方向性与唯一性；主体类型、存在性和世界归属用 CHECK + typed composite FK 加固。三项指标非空，CHECK 要求 integer 且 affinity/trust 在 [-100,100]、familiarity 在 [0,100]；旧行迁移为 0，领域 delta 超范围拒绝而不 clamp。
- WorldEvent 仅插入；(world_id, idempotency_key) unique，None 不参与理由去重。UPDATE/DELETE 触发器直接拒绝，recursive_triggers=ON 防止本 engine 的 INSERT OR REPLACE 绕过删除触发器。EventAppender 无 update/delete/merge 路径；生产事件随 command→projection→receipt 原子提交。
- Knowledge 的 truth 没有 owner；character_belief 必须且只能有 Character owner；player_knowledge 必须且只能有 Player owner。来源与 owner 复合 FK 保持世界隔离，有效期不能倒序。错误信念与事实可以分别存储，不自动纠正或传播。
- Observation 的渠道 CHECK 与同世界主体/目标 FK 保留明确观察语义，不自动授予知识或查询权限。
- Receipt 沿用 (world_id, request_id) 主键、完整结果引用 CHECK 和完成时间检查。新命令 fingerprint/result_payload 成对保存且要求 committed、完成时间与事件引用。旧回执没有指纹时不视为可验证成功；新管线全局查找 RequestId，相同语义返回原结果，变化语义显式冲突。
- Revision 在 DB 中非负。没有 expected-revision UPDATE、冲突重试或乐观并发执行。

额外索引有 world_events 的 (world_id, occurred_at, event_id)、事件幂等 unique、knowledge 的 world/scope/character-owner 与 world/scope/player-owner，以及 C-003C 新回执 request_id partial unique；当前状态通过主键查找。未创建向量、Memory 或计划表。

[PersistenceStore](../../services/core/src/livingworld/infrastructure/persistence/store.py) 在 C-003C 仅提供 reload(snapshot)，返回新领域值/None，不暴露 Record/Session。原逐对象写入工具移至 [测试辅助](../../tests/persistence/snapshot_support.py)，保持 C-003B 无损映射/约束测试意图。生产变更由 [SqlAlchemyUnitOfWork](../../services/core/src/livingworld/infrastructure/persistence/unit_of_work.py) 实现 focused repository 和单一 command 事务；见 [COMMAND_MODEL.md](COMMAND_MODEL.md)。

## 6. 验证与后续边界

验证见 [迁移兼容性测试](../../tests/persistence/test_migrations.py)、[映射测试](../../tests/persistence/test_mapping.py)、[DB 约束测试](../../tests/persistence/test_constraints.py)、[其他边界测试](../../tests/persistence/test_additional_invariants.py) 与 [C-002 bootstrap 回归](../../tests/core/test_bootstrap.py)。用临时数据库证明无损接管、原子回滚、跨世界 FK、知识归属、事件不可变、精确双时间、typed ID 与重启读取。开发者实际 app-data DB 不用于测试。

权限过滤必须先于 semantic retrieval / prompt assembly；C-003D 的 list/get SQL 强制 world/scope/owner 条件，见 [knowledge_readers.py](../../services/core/src/livingworld/infrastructure/persistence/knowledge_readers.py)。内部 exact-source repository 与 snapshot inspection 不分发给角色/玩家；返回 source_assertion_id 也不授予源读取权限。CommandReceipt 的 versioned JSON 结果新增可选 typed ObservationId，兼容旧结果无此 key，不需额外回执 schema 迁移。

C-003C 回归见 [命令集成测试](../../tests/application/test_commands.py) 和 [0003 迁移回归](../../tests/persistence/test_command_migration.py)；C-003D 验证见 [知识访问集成测试](../../tests/application/test_knowledge_access.py) 和 [Observation 迁移回归](../../tests/persistence/test_observation_migration.py)。replay、完整乐观并发、Timeline/Checkpoint、预算与智能层仍未实现。
