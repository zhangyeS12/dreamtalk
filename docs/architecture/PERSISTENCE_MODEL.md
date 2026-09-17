# C-003B：SQLite Persistence Mapping

状态：已实现 C-003A 领域快照的 SQLite schema、显式 ORM 映射、低层插入/读取和 Alembic 迁移接管。未实现 Command handler、Kernel 提交、乐观并发命令执行、事件回放、知识传播、检索权限服务或世界模拟。产品冻结规则与 P-01～P-19 不变。

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
| relationships | (world_id, source_kind, source_id, target_kind, target_id) | 有向主体边、Revision；A→B 与 B→A 独立 |
| world_events | (world_id, event_id) | 类型、双时间、版本化 JSON payload、因果/关联/幂等信息 |
| knowledge_assertions | (world_id, assertion_id) | scope/owner、subject/predicate/value、认知标签、confidence、世界有效期、来源、Revision |
| observations | (world_id, principal_kind, principal_id, target_kind, target_id, channel, observed_at) | 显式观察及可选 UTC 审计时间 |
| command_receipts | (world_id, request_id) | 类型、status、可选结果引用、UTC 创建/完成时间、Revision |

Observation 沿用 C-003A 无独立 ObservationId 的形状：完整观察坐标形成自然键，相同主体/目标/渠道/世界时间的重复记录不会形成第二行。没有新增观察身份、历史 presence、Timeline 或分支政策。

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

启动行为：

1. 空 DB：直接 Alembic upgrade head，依次执行 0001 与 0002。
2. 无 Alembic cursor 的 C-002 DB：只接受精确 legacy 表/列/PK/DDL、schema_version=(1,1)、一条匹配名称与 checksum 的历史记录和合法 UTC 审计时间；验证通过后 stamp 0001，再正常 upgrade head。旧迁移不重跑，已有行原样保留。
3. 已有 Alembic cursor：由该 revision 驱动升级；legacy 元数据只做一致性检查。不能用 schema_version 推算或选择待执行迁移。
4. 未知版本、checksum 漂移、缺失/损坏历史、结构差异、部分领域表、cursor 冲突或未知额外 schema 对象：抛出 MigrationCompatibilityError，事务回滚并停止启动；不自动修复、drop/recreate 或 stamp head。

**审计语义转换：** schema_version 继续保留 1，migration_history 保留旧基础迁移记录，即使 Alembic 已到 0002。两表是 C-002 兼容/历史证据，不反映当前领域 schema cursor；本阶段不追加或同步新 Alembic 审计记录。新库的 0001 建立等价基础记录，接管已有库时不改变 applied_at 或任何原有列。

Repeat startup 正常调用 Alembic upgrade head，不重放 revision、不重新 stamp、不重复插入审计记录。迁移接管与 DDL 同处一个事务，失败时旧库保持原状；不涉及实际用户库的自动修复工具。

## 5. 约束与低层 adapter

- Presence 与 CharacterState 的主键限制每世界/主体只有一条当前状态；location 非空、须属于该世界。inactive 不删除位置，不产生自动见证。
- Relationship 的有序复合主键保证方向性与唯一性；主体类型、存在性和世界归属用 CHECK + typed composite FK 加固。
- WorldEvent 仅插入；(world_id, idempotency_key) unique，None 不参与理由去重。UPDATE/DELETE 触发器直接拒绝，recursive_triggers=ON 防止本 engine 的 INSERT OR REPLACE 绕过删除触发器。低层 adapter 无 update/delete/merge 路径；这不等同于已经实现 Kernel 授权或 Command 幂等执行。
- Knowledge 的 truth 没有 owner；character_belief 必须且只能有 Character owner；player_knowledge 必须且只能有 Player owner。来源与 owner 复合 FK 保持世界隔离，有效期不能倒序。错误信念与事实可以分别存储，不自动纠正或传播。
- Observation 的渠道 CHECK 与同世界主体/目标 FK 保留明确观察语义，不自动授予知识或查询权限。
- Receipt 的 (world_id, request_id) 主键、完整结果引用 CHECK 和完成时间检查为后续任务提供存储基础，不运行 executor。
- Revision 在 DB 中非负。没有 expected-revision UPDATE、冲突重试或乐观并发执行。

额外索引仅有 world_events 的 (world_id, occurred_at, event_id)、事件幂等 unique，以及 knowledge 的 world/scope/character-owner、world/scope/player-owner；当前状态通过主键查找。未创建向量、Memory 或计划表。

[PersistenceStore](../../services/core/src/livingworld/infrastructure/persistence/store.py) 只提供 add(snapshot) 与 reload(snapshot)：每次插入拥有独立低层事务，reload 按快照的身份读取并返回新领域值。World 插入携带其 clock，reload 可单独读取 clock。接口返回领域值/None，不向 application/domain 暴露 Record 或 Session。这是映射证明 adapter，不是最终 Command repository 或 UnitOfWork。

## 6. 验证与后续边界

验证见 [迁移兼容性测试](../../tests/persistence/test_migrations.py)、[映射测试](../../tests/persistence/test_mapping.py)、[DB 约束测试](../../tests/persistence/test_constraints.py)、[其他边界测试](../../tests/persistence/test_additional_invariants.py) 与 [C-002 bootstrap 回归](../../tests/core/test_bootstrap.py)。用临时数据库证明无损接管、原子回滚、跨世界 FK、知识归属、事件不可变、精确双时间、typed ID 与重启读取。开发者实际 app-data DB 不用于测试。

权限过滤必须先于 semantic retrieval / prompt assembly 的架构规则保持不变；存储 owner CHECK 不等于查询授权服务。Command→event→projection→receipt 原子执行、replay、Timeline/Checkpoint、预算与智能层留待明确任务，本阶段没有实现。
