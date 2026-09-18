# SQLite Persistence, Canonical Ledger & Resource CAS

状态：Stage 2 SQLite/Alembic、持久化幂等、主体知识隔离、canonical ledger、原子投影重建及资源级 CAS 已实现。C-003E2 的内部信念形成复用既有 KnowledgeAssertion 存储。自动传播、语义检索与世界模拟未实现。产品冻结规则不变，见 [COMMAND_MODEL.md](COMMAND_MODEL.md)、[KNOWLEDGE_ACCESS_MODEL.md](KNOWLEDGE_ACCESS_MODEL.md) 与 [REPLAY_MODEL.md](REPLAY_MODEL.md)。

## C-004A / C-004C1 独立内容库

**Imported Content != Runtime State；CharacterDefinition != Character；WorldContent != World；LoreEntry != WorldTruth；LoreCollection != WorldContent != Runtime World != WorldTruth。**

Alembic head 现为 [0009_llm_accounting](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0009_llm_accounting.py)，down_revision=0008_native_content_packages。0009 只新增独立 AccountingBase 的 operational llm_attempts，不修改 world/content schema 或历史 rows；详见 [LLM_ACCOUNTING.md](LLM_ACCOUNTING.md)。0008 只增加 accepted baseline 与 immutable blob binding 两张本地元数据表；不存 ZIP structure、不修改旧 rows/JSON/hash/audit/runtime。0006 建立五个内容表；0007 只新增集合表与条目归属 FK，不修改 Stage 2 表、事件、回执、cursor、typed/world-scoped IDs 或审计行。下文 Stage 2 的 0005 head 描述保留其阶段语境，不表示当前 head。

| 内容表 | 可直接校验/查询的结构 | 正文边界 |
| --- | --- | --- |
| content_character_definitions | CharacterDefinitionId PK、title、content_version、ContentRevision、semantic_hash | 独立 CharacterDefinition canonical JSON |
| content_worlds | WorldContentId PK、title、content_version、ContentRevision、semantic_hash | 独立 WorldContent canonical JSON |
| content_lore_entries | LoreEntryId PK、collection_id FK（nullable 仅供 legacy）、title（可空串）、content_version、ContentRevision、semantic_hash | 独立 LoreEntry canonical JSON；新条目必属一个集合；正文不能空白 |
| content_lore_collections | LoreCollectionId PK、title/name（可空串）、content_version、ContentRevision、semantic_hash | LoreCollection canonical JSON、有序成员、book metadata、完整来源/兼容表示 |
| content_assets | ContentAssetId PK、media_type、opaque resource_reference | 元数据 JSON，不存图片 bytes，不打开引用 |
| content_raw_imports | RawImportId PK、原文件 SHA-256 | provenance/opaque extensions JSON、完整原 bytes BLOB；不是 asset storage pipeline |

使用独立 [ContentBase / Records](../../services/core/src/livingworld/infrastructure/persistence/content_models.py)，与 runtime Base 完全分离。四种 root 独立表保证 typed 身份边界，没有巨型泛型 JSON 表；正文不用逐文本过度规范化。当前需求按 ID 读取，不为尚不存在的搜索增加索引或 FTS 业务表。DB CHECK 强制 JSON 合法、版本 1、非负整数 revision、hash 长度与必要非空标签；读取重新校验 canonical 数据、完整哈希、独立元数据与 collection_id 一致性。

[SqlAlchemyContentRepository](../../services/core/src/livingworld/infrastructure/persistence/content_repository.py) 使用既有 Database 的 engine/session factory，数据库仍位于 app data；无新存储进程或依赖。ContentDraft 封闭图在应用边界验证 Lore/asset/raw 引用及重复 typed IDs，root references 保留 canonical JSON 中，不使用 polymorphic runtime FK。当前无删除 API，整批创建/编辑/依赖复用同一事务；未来若增加删除/独立依赖修改，须维持该图约束。

C-004C1 新 owned entry 的 collection_id 使用明确内容 FK，集合 references 必须与 Draft 及 DB 实际成员精确一致；新条目 NULL 在 application commit 与 repository 双重拒绝。定义以 lore_collection_ids 引用共享集合，不拥有删除权；无 destructive cascade，条目归属不能通过本任务重新指定。所有成员、定义引用、raw/asset 依赖仍在一个内容事务内写入。

0007 使用原生 ADD COLUMN nullable REFERENCES，旧表不重建；所有旧条目保留为 legacy unbound，旧 canonical JSON/hash/revision、CharacterDefinition / WorldContent 共享引用原样保留。不合成集合、不推断归属、读时不 re-home。Content version=1 的两项 additive legacy 编码见 [CONTENT_MODEL.md](CONTENT_MODEL.md)：缺失 collection_id 与空 lore_collection_ids 保持旧 serializer 输出，不要求存储重写。

创建必须预期 None + revision=0；编辑必须 typed ContentRevision + 下一版本，SQL WHERE 含完整内容身份与预期版本；未变依赖只有精确匹配才保留。Raw/asset 同 ID 不可覆盖不同数据，版本/唯一性/写入失败整批回滚。BEGIN IMMEDIATE 复用现有集中事务 hook，ContentRevision 与 runtime CAS 完全分离；没有 content WorldEvent、runtime receipt 或自动 retry。

内容保存本身是创作编辑，不是 canonical runtime 变更；repository 没有运行时 mutation capability。WorldEvent ledger/rebuild 与内容库相互独立，rebuild 不删除内容。Prompt-like 文本/扩展始终为数据，数据库不会执行或自动传播为 Truth/Knowledge。

迁移 compatibility detector 显式区分 0005 与 0006 的允许表形状；旧 revisions 仍严格验证，不以内容表猜测 cursor。0006 支持空库、valid legacy takeover、完整 0005 升级和重复启动；部分新增内容表/未知列 fail closed。DDL 失败保留 0005 与所有原行，downgrade 要求 review。schema_version=1/migration_history 继续是 legacy audit，只有 alembic_version 选择迁移。

0007 的 compatibility detector 同样按 Alembic cursor 明确区分 0006/0007 表、列和 FK；不能以 NULL/引用猜测版本。失败完整 rollback，保留 0006 和原行/元数据，不留半个集合表。验证见 [test_lorebook_persistence.py](../../tests/persistence/test_lorebook_persistence.py)；实际 app-data 数据库未用于验收。

验证：[test_content_persistence.py](../../tests/persistence/test_content_persistence.py) 证明重启 round-trip、typed ID、原始 bytes、ContentRevision 更新/原子失败、所有 Stage 2 行/审计保留与迁移失败回滚；[test_content_boundary.py](../../tests/application/test_content_boundary.py) 证明内容提交及 runtime replay 保持 Truth/Belief/PlayerKnowledge/ledger 隔离。没有迁移实际用户数据库，没有 GUI smoke。详见 [CONTENT_MODEL.md](CONTENT_MODEL.md)、[IMPORT_MODEL.md](IMPORT_MODEL.md)。

### C-004D2 native snapshot 与本地元数据

| 本地表 | 身份与语义 |
| --- | --- |
| content_import_baselines | unique PK `(content_kind,content_id)`；accepted_semantic_hash、aware UTC accepted_at、optional source_package UUID/hash。LOCAL IMPORT/CONFLICT METADATA，不是 canonical/revision/history/runtime，不导出。 |
| content_asset_blob_bindings | ContentAssetId PK/FK、verified SHA-256 digest、nonnegative size；metadata→app-data hash blob 的不可变关联，不以 filename 为身份。 |

[SqlAlchemyPackageRepository](../../services/core/src/livingworld/infrastructure/persistence/package_repository.py) 是显式 native snapshot acceptance port。DB transaction 重核 local full snapshot + baseline；NEW/REPLACE/接受 IDENTICAL 的 baseline 更新与对应 canonical roots/raw/asset/binding 同事务。KEEP 不更新 baseline，不按 revision 大小选择 winner。不建立 full edit history，不修改普通 ContentRepository 的 absent+revision0/exact-next-revision contract。

native 导入保留原 typed IDs、任意合法 nonnegative imported ContentRevision 与 canonical bytes；显式 REPLACE 也可接受较低 revision，但 stale Preview 仍通过 exact snapshot/baseline precondition 拒绝。owned entries 不可 re-home/隐式删除；跨成员 decisions 破坏闭包或持久化 collection membership 时全部失败。

[FileContentAssetStore](../../services/core/src/livingworld/infrastructure/packages/asset_store.py) 在既有 Database.data_dir 下独立 hash-keyed 文件。先验证/写 staging/发布 immutable blobs，再做 DB transaction；失败 DB 可留不可达 orphan，future GC deferred。只有 committed DB refs 使 blob 语义可达。FS+SQLite **不是单一 ACID transaction**；资产缺失/损坏明确拒绝，不 silent repair。

0008 compatibility detector 仅依据 Alembic cursor 校验历史 0007/当前 0008 的 exact tables/columns/FK/checks，未知/partial state fail closed；DDL failure 连同两表与 cursor 回滚。WorldContent 的空 lore_collection_ids 采用 additive canonical legacy encoding，不需要重写 rows/hash 或新增 JSON字段列。测试见 [package persistence](../../tests/persistence/test_package_persistence.py) 与 [Stage 3](STAGE_3_ACCEPTANCE.md)。

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
| world_events | (world_id, event_id)；(world_id, ledger_position) unique index | 类型、双时间、版本化 JSON payload、因果/关联/幂等信息、不可变正整数 canonical position |
| world_ledger_cursors | world_id，FK worlds | SQLite adapter 的 last_position；非负整数，分配操作与命令同事务 |
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
| [0005_canonical_ledger](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0005_canonical_ledger.py) | 原生 ADD COLUMN 增加 ledger_position 与正整数 CHECK，按每世界旧 rowid 回填，创建 world/position unique index 与世界游标；保留旧事件语义及审计行 |

启动行为：

1. 空 DB：直接 Alembic upgrade head，依次执行 0001 至 0005。
2. 无 Alembic cursor 的 C-002 DB：只接受精确 legacy 表/列/PK/DDL、schema_version=(1,1)、一条匹配名称与 checksum 的历史记录和合法 UTC 审计时间；验证通过后 stamp 0001，再正常 upgrade head。旧迁移不重跑，已有行原样保留。
3. 已有 Alembic cursor：由该 revision 驱动升级；legacy 元数据只做一致性检查。不能用 schema_version 推算或选择待执行迁移。
4. 未知版本、checksum 漂移、缺失/损坏历史、结构差异、部分领域表、cursor 冲突或未知额外 schema 对象：抛出 MigrationCompatibilityError，事务回滚并停止启动；不自动修复、drop/recreate 或 stamp head。

**审计语义转换：** schema_version 继续保留 1，migration_history 保留旧基础迁移记录，即使 Alembic 已到 0005。两表是 C-002 兼容/历史证据，不反映当前领域 schema cursor；本阶段不追加或同步新 Alembic 审计记录。新库的 0001 建立等价基础记录，接管已有库时不改变 applied_at 或任何原有列。

0002 管理的数据库先按该历史 revision 的精确已知形状校验，再由 Alembic 执行 0003；结构检查不能自行选择或猜测迁移版本。部分增加指标或未知差异仍 fail closed。0003 的 downgrade 明确要求 review，因为删除已提交命令指纹会破坏重试安全，不自动丢弃幂等证据。

0002/0003 的历史 observations 形状仍按旧坐标主键校验，再交给 Alembic 执行 0004；0004/0005 要求新身份列及主键。旧 ID 回填仅在迁移中：原 world_id/principal_kind/principal_id/target_kind/target_id/channel/observed_at tuple 使用排序 key、紧凑 UTF-8 JSON，固定 namespace UUIDv5，相同旧行始终得到相同 ID，不随机生成。**legacy backfill identity != runtime identity generation**。0004 的 SQLite batch recreate 只针对 observations，事件触发器不解除，升级与回填/表替换同事务。0004 downgrade 明确要求 review，不能静默丢弃同坐标多 occurrence。

### 0005 legacy 顺序核验与回填

实施前只读检查的开发/桌面 app-data 库均只有 C-002 元数据。隔离临时库运行 C-003D 命令后确认：world_events 是普通 rowid 表；正常追加顺序与 rowid 一致；0002 建表后，0003/0004 未重建事件表，生产路径只追加、无 VACUUM/重排路径。未对真实 app-data 库执行迁移。

迁移先拒绝 WITHOUT ROWID、rowid 别名遮蔽、不可区分的 rowid 或追加保护不匹配。每世界按旧 `_rowid_ ASC` 回填 1..N，游标初始化为该世界已回填最大值，无事件世界为 0。**legacy migration order != future canonical replay semantics**：这只采纳已核验的旧插入证据；以后只能 `ORDER BY ledger_position ASC`，绝不以 WorldTime、created_at 或 UUID 补救未知旧顺序。

原生 ADD COLUMN 保留旧 rowid 和原列。SQLite 为该非空新列保留 DEFAULT 1；它只是迁移兼容值，生产 appender 始终显式赋予事务分配值，不能把默认值当作分配器。为写入新列，迁移在同一 DDL 事务内暂时替换 UPDATE 触发器并立即恢复；DELETE 保护保持存在。竞争写事务不能观察中间状态，任一步失败连同列、回填、触发器及 Alembic cursor 全部回滚。**回放从不解除追加保护**。0005 downgrade 明确要求 review，不自动丢弃 canonical 顺序。

Repeat startup 正常调用 Alembic upgrade head，不重放 revision、不重新 stamp、不重复插入审计记录。迁移接管与 DDL 同处一个事务，失败时旧库保持原状；不涉及实际用户库的自动修复工具。

## 5. 约束与低层 adapter

- Presence 与 CharacterState 的主键限制每世界/主体只有一条当前状态；location 非空、须属于该世界。inactive 不删除位置，不产生自动见证。
- Relationship 的有序复合主键保证方向性与唯一性；主体类型、存在性和世界归属用 CHECK + typed composite FK 加固。三项指标非空，CHECK 要求 integer 且 affinity/trust 在 [-100,100]、familiarity 在 [0,100]；旧行迁移为 0，领域 delta 超范围拒绝而不 clamp。
- WorldEvent 仅插入；(world_id, idempotency_key) unique，None 不参与理由去重。UPDATE/DELETE 触发器直接拒绝，recursive_triggers=ON 防止本 engine 的 INSERT OR REPLACE 绕过删除触发器。EventAppender 无 update/delete/merge 路径；生产事件随 command→projection→receipt 原子提交。
- Knowledge 的 truth 没有 owner；character_belief 必须且只能有 Character owner；player_knowledge 必须且只能有 Player owner。来源与 owner 复合 FK 保持世界隔离，有效期不能倒序。错误信念与事实可以分别存储，不自动纠正或传播。
- Observation 的渠道 CHECK 与同世界主体/目标 FK 保留明确观察语义，不自动授予知识或查询权限。
- Receipt 沿用 (world_id, request_id) 主键、完整结果引用 CHECK 和完成时间检查。新命令 fingerprint/result_payload 成对保存且要求 committed、完成时间与事件引用。旧回执没有指纹时不视为可验证成功；新管线全局查找 RequestId，相同语义返回原结果，变化语义显式冲突。
- Revision 在 DB 中非负。C-003E2 的 focused repository 使用完整 PK + expected revision 的 SQL UPDATE；rowcount=0 明确 ConcurrencyConflictError，不 merge 或无条件覆盖。期待缺失使用 INSERT，PK/UNIQUE 竞争明确归类为该领域冲突，不把 FK/CHECK 失败误判为竞争。

额外索引有 world_events 的 (world_id, occurred_at, event_id)、事件幂等 unique、knowledge 的 world/scope/character-owner 与 world/scope/player-owner，以及 C-003C 新回执 request_id partial unique；当前状态通过主键查找。未创建向量、Memory 或计划表。

[PersistenceStore](../../services/core/src/livingworld/infrastructure/persistence/store.py) 在 C-003C 仅提供 reload(snapshot)，返回新领域值/None，不暴露 Record/Session。原逐对象写入工具移至 [测试辅助](../../tests/persistence/snapshot_support.py)，保持 C-003B 无损映射/约束测试意图。生产变更由 [SqlAlchemyUnitOfWork](../../services/core/src/livingworld/infrastructure/persistence/unit_of_work.py) 实现 focused repository 和单一 command 事务；见 [COMMAND_MODEL.md](COMMAND_MODEL.md)。

## 6. 验证与后续边界

验证见 [迁移兼容性测试](../../tests/persistence/test_migrations.py)、[映射测试](../../tests/persistence/test_mapping.py)、[DB 约束测试](../../tests/persistence/test_constraints.py)、[其他边界测试](../../tests/persistence/test_additional_invariants.py) 与 [C-002 bootstrap 回归](../../tests/core/test_bootstrap.py)。用临时数据库证明无损接管、原子回滚、跨世界 FK、知识归属、事件不可变、精确双时间、typed ID 与重启读取。开发者实际 app-data DB 不用于测试。

权限过滤必须先于 semantic retrieval / prompt assembly；C-003D 的 list/get SQL 强制 world/scope/owner 条件，见 [knowledge_readers.py](../../services/core/src/livingworld/infrastructure/persistence/knowledge_readers.py)。内部 exact-source repository 与 snapshot inspection 不分发给角色/玩家；返回 source_assertion_id 也不授予源读取权限。CommandReceipt 的 versioned JSON 结果新增可选 typed ObservationId，兼容旧结果无此 key，不需额外回执 schema 迁移。

C-003C 回归见 [命令集成测试](../../tests/application/test_commands.py) 和 [0003 迁移回归](../../tests/persistence/test_command_migration.py)；C-003D 验证见 [知识访问集成测试](../../tests/application/test_knowledge_access.py) 和 [Observation 迁移回归](../../tests/persistence/test_observation_migration.py)。C-003E1 见 [ledger 测试](../../tests/application/test_ledger.py)、[0005 迁移测试](../../tests/persistence/test_ledger_migration.py) 与 [重建测试](../../tests/application/test_replay.py)。C-003E2 的竞争/回滚和完整验收见 [STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)。Timeline/Checkpoint、预算与智能层仍未实现。

## 7. Canonical 分配与投影重建

`ledger_position != WorldTime != created_at != event_id`。WorldEventRecord 保存 position，CHECK 要求正整数，world/position unique index 保证世界内唯一；原 UPDATE/DELETE/REPLACE 保护同时覆盖新列。位置由 EventAppender 的单条 SQLite INSERT ... ON CONFLICT UPDATE ... RETURNING 分配，读取/更新游标与事件、投影、回执共享同一 AsyncSession/事务；不使用运行时 MAX+1，也不向 Domain 暴露 allocator。WorldCreated 首次分配 1；失败没有 durable cursor，成功幂等重试不重新分配。允许间隙，世界之间无共享序列。

内部 [CanonicalEvent](../../services/core/src/livingworld/application/ledger.py) 用不可变 envelope 保留事件及 position，Domain WorldEvent 继续表达事件语义；canonical reader 总是携带 position 并按它排序。诊断 snapshot reload 仍返回领域值，不是 canonical 顺序读取端口。读取 ledger 的内部能力不分发给角色/玩家知识上下文。

重建 adapter 在同一事务读取 ledger、仅清理目标世界的 replayable projections、写回纯 fold 的值并验证约束。世界 identity 行保留为事件/回执/游标的 FK anchor，但其 name/revision 和整个 WorldClock 从事件恢复，绝不借用旧状态补偿 payload。事务临时 defer 外键检查，foreign_keys 始终 ON；最终检查目标世界，包括保留的回执和地点连接引用。所有表清理均有 world_id 条件，任何失败回滚。

可回放 World/WorldClock、Location、Player/Presence、Character/State、Relationship、KnowledgeAssertion、Observation；**CommandReceipt 不从事件重建**。world_events、world_ledger_cursors、审计与迁移表、运行元数据不重建。location_connections 当前没有 canonical 创建事件，保持原样；引用若无法由 ledger 恢复，显式失败，不复制旧 Location 补救。详见 [REPLAY_MODEL.md](REPLAY_MODEL.md)。

## 8. C-003E2 并发与信念存储

三个 mutable repository 的端口显式接收 typed expected revision；Presence 要求 Revision，CharacterState / Relationship 接收 Revision 或 None。更新 WHERE 必须限定 world、完整资源身份和 expected revision，写入恰好下一版本。状态首次 revision=0，有向关系首次 delta 后 revision=1；不存在与零版本严格区分。没有全局 World revision。

SQLite command UoW 在读取前通过集中 begin hook 的 `livingworld_write_intent` execution option 使用 BEGIN IMMEDIATE；其他连接仍 BEGIN。连接取得写入资格前失败会关闭 session。此举处理 SQLite 物理 writer contention，不改变资源级语义、不自动重试，也不能替代 CAS；未来非 SQLite adapter 必须实现等价 CAS 和身份竞争归类。busy_timeout 仍为既有 5000ms，超过等待限度的非语义运行故障不宣称命令成功。

失败 transaction 先 rollback/close，handler 才可使用一次新事务查证原 RequestId 的已提交 receipt。无回执则仍失败；有不同 fingerprint 则幂等冲突；匹配返回原结果。不会重新运行 command。位置分配仍和 event/projection/receipt 同事务，CAS=0 或 INSERT 冲突均不会遗留 cursor advance、事件或成功回执。

FormCharacterBelief 不需要新表、列或索引：复用 knowledge_assertions 的 ownership CHECK、source/provenance 同世界 FK、Decimal/JSON/WorldTime 编码。新断言 revision=0，source/provenance 可 SQL NULL，提供时原样保存；不要求对应 Truth 或 Observation。没有 semantic 去重、命题唯一约束或自动调和。

**C-003E2 无 schema 变更，Alembic head 保持 0005_canonical_ledger；不创建 0006。** schema_version=1 和旧 migration_history 仍为兼容审计证据，Alembic 是唯一 cursor；旧事件、回执和审计不改写，实际 app-data 数据库未用于验收。

## C-005D2A：独立物理 attempt accounting

[llm_attempts](../../services/core/src/livingworld/infrastructure/persistence/llm_models.py) 以 (InvocationId, attempt_ordinal) 为 PK，START/FINALIZE 使用 app-data Database 的独立事务。Durable START 缺失 final facts 为 INCOMPLETE + POSSIBLY_BILLED_UNKNOWN，estimated money=NULL；重复 delivery 同事实幂等，冲突拒绝，restart 不自动补写或重放 generation。Logical terminal outcome 单独记录，允许物理 FAILED 与 invocation CANCELLED（例如 backoff 取消）同时存在。Exact Decimal 以 TEXT 保存，price snapshot 保存 effective schedule/selected variant/context/rates/source/line items，更新 catalog 不改历史。Migration detector 按 Alembic cursor 区分 0008/0009 的 exact shape，失败回滚，不利用 schema_version 再选择迁移。

[Usage ledger repository](../../services/core/src/livingworld/infrastructure/persistence/llm_repository.py) 只接收 closed safe accounting facts，不接收 request/response/credential objects，不写 world/knowledge/content、WorldEvent 或 package。Raw rows/SQLite canary、duplicate delivery、历史快照、crash/restart 和 0008→0009 rollback 见 [accounting tests](../../tests/core/test_llm_accounting.py)。Usage fact != price config；estimated cost != invoice；未知费用不是零；预算限制与 incomplete reconciliation deferred。
