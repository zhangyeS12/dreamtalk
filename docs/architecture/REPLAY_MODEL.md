# Canonical Ledger & Projection Replay（C-003E1）

状态：内部 canonical reader、纯 versioned fold、世界内原子重建已实现。不增加业务 API、自动启动修复、世界推进、Timeline/Checkpoint、乐观并发命令语义或智能层。

## 1. 顺序与身份

```text
ledger_position != WorldTime != created_at != event_id
legacy migration order != future canonical replay semantics
```

position 是每世界严格递增的 canonical 历史顺序，允许间隙；WorldTime 是世界逻辑坐标；created_at 是 UTC 现实审计时间；EventId 是事件身份。回放仅依赖 position 升序，时间相同或现实时间回退均不改变它。

[CanonicalEvent](../../services/core/src/livingworld/application/ledger.py) 是 immutable event + position envelope；Domain WorldEvent 继续表达事实语义，不包含 SQLite 分配机制。SQLite 的世界游标原子 upsert/RETURNING 与命令事务共享 session；未来 adapter 可替换基础设施实现。新 WorldCreated 固定位置 1，多事件按 handler list 顺序分配，命令失败没有 durable cursor/event/receipt。

0005 使用实施前核验的旧 rowid 追加证据做一次性每世界 1..N 回填，之后 rowid 永远不是回放依据。保留旧 EventId、payload、双时间、因果、幂等 key 和审计记录；缺失可靠旧顺序时停止，无隐式 fallback。迁移细节与保留 DEFAULT 1 的 SQLite 兼容边界见 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。

## 2. 实现前 payload 审计与显式分发

当前 [command_handler.py](../../services/core/src/livingworld/application/command_handler.py) 发出的 11 类 v1 payload 已在编写重建 handler 前逐项审计，均包含恢复当前 Stage 2 状态所需语义。未补写历史 payload，未用当前投影填补事件内容。

| `(event_type, payload_version)` | 从事件恢复 / 校验 |
| --- | --- |
| WorldCreated, 1 | world ID/name、world revision、logical_time、observed UTC、精确 time_scale、clock state/revision；初始 revision=0、位置=1，时轴与 envelope 对应 |
| LocationCreated, 1 | 地点 ID/name/revision，唯一身份、初始 revision=0 |
| PlayerCreated, 1 | 玩家 ID/name/revision，唯一身份、初始 revision=0 |
| PlayerPlaced, 1 | 初始物理地点、activity/availability、presence revision；必须有该世界玩家/地点 |
| PlayerMoved, 1 | player ID、from/to、activity/availability、resulting revision；原地点与前态一致、地点存在、按已有 domain 行为递增 |
| CharacterCreated, 1 | 角色 ID/name/revision，唯一身份、初始 revision=0 |
| CharacterPlaced, 1 | 角色 ID、可空 before location、新地点、state revision；首次放置 0，后续按前态递增 |
| RelationshipChanged, 1 | typed source/target 与角色 ID、edge_existed、before/delta/after 三项 metrics、resulting revision；验证方向、前态、非零 delta、范围及完整 after |
| WorldTruthAsserted, 1 | assertion ID、truth scope/owner、subject/predicate/value、status/confidence、WorldTime 有效期、source/provenance/revision；真相无 owner/source，provenance 指当前 event |
| ObservationRecorded, 1 | 原 ObservationId、typed receiver、source assertion、channel、observed WorldTime、created UTC；来源和主体必须已存在于已回放历史 |
| KnowledgeAcquired, 1 | 完整 assertion + observation payload；owner/scope/source/proposition/validity 与已记录观察一致，provenance 指当前 event，配对 causation 相同 |

[replay.py](../../services/core/src/livingworld/application/replay.py) 只按显式 `(type, version)` 映射调用纯 fold，没有“试着兼容”未知版本。新版本需后续任务明确实现，历史 v1 handler 保持语义。复用已有领域类型、枚举和范围/版本规则，不引入并列领域模型。最终每个正常 Player 都有 Presence；每个 v1 ObservationRecorded 都有且只有一个配对 KnowledgeAcquired。

## 3. 原子重建流程

```text
trusted world-bound rebuild UnitOfWork
→ 同一事务读 canonical ledger，ORDER BY ledger_position ASC
→ 仅清理此世界的可回放投影
→ 纯 fold 按 (type, version) 构造不可变 ProjectionSnapshot
→ 写回、校验 domain invariants / DB CHECK / FK
→ commit
```

Application 使用 [ports.py](../../services/core/src/livingworld/application/ports.py) 的 world-bound CanonicalEventReader / ProjectionRebuildUnitOfWork；该重建端口不授予 events/receipts append 能力。基础设施在 [persistence/replay.py](../../services/core/src/livingworld/infrastructure/persistence/replay.py) 实现清理、插入和校验。

fold 的中间状态只来自先前 canonical event。它不读取数据库当前状态、不调用命令 handler、system clock、UUID generator、网络、LLM、filesystem、notification 或 Tauri。UUID 构造仅解析事件中现有身份，UTC datetime/Decimal 构造仅解码事件值。观察身份、owner、source、provenance 不重新生成，也不自动推断未明确获知的知识。

世界 identity 行保留作为 immutable ledger/receipt/cursor 的 FK anchor，其完整 mutable name/revision 与 WorldClock 均从 WorldCreated 恢复。临时 defer 外键使投影父项可在同事务内恢复；foreign_keys 和追加保护始终有效。最终检查该世界的完整引用，commit 前不能留下悬空关系。

空 ledger、跨世界 entry、位置非严格递增、重复事件/投影身份、未知类型/版本、非法 payload、缺失来源、领域错误或 DB 约束失败：不提交，所有清理/写回完整回滚，旧投影可继续读取。错误消息不输出 payload 内容。没有 best-effort 跳过、部分 commit 或自动重试。

## 4. 可回放边界

| 范围 | 重建行为 |
| --- | --- |
| World / WorldClock | 从 WorldCreated 恢复既有可变状态；不采样时钟、推进或 catch-up |
| Location | 重建地点身份/name/revision |
| Player / PlayerPresence | 恢复身份、唯一物理位置、active/inactive、busy/available、revision |
| Character / CharacterState | 恢复身份和已明确放置的状态；未放置角色不虚构位置 |
| Relationship | 恢复有向边与内部三项 metrics/revision，不生成反向边或玩家评分展示 |
| KnowledgeAssertion | 恢复 Truth / CharacterBelief / PlayerKnowledge 及原 owner/source/provenance、有效期/值/认知元数据 |
| Observation | 保留原 ObservationId 及完整语义，允许同坐标独立 occurrence |
| WorldEvent / CommandReceipt / ledger cursor | 全部保持原样，**CommandReceipt 不从事件重建** |
| Alembic / legacy audit / runtime metadata | 全部保持原样 |
| LocationConnection | 当前没有 canonical 创建事件，保持原样；无法恢复其引用时失败，而非复制旧地点补救 |

每条清理/覆盖语句限定 world_id；重建 World A 不更改 World B 的投影、事件、回执或序列。Knowledge reader 继续在 SQL 中先筛选 world/scope/owner；内部 ledger/source 能力不授予玩家/角色，上游 source ID 不变也不形成权限。Billy/Banyue 的秘密不会因 rebuild 或 source traversal 自动暴露给 Belle 或玩家。

## 5. 验证

[重建集成测试](../../tests/application/test_replay.py) 通过真实普通命令构造覆盖 11 类事件的完整世界，比较原始投影与重建后的语义状态，连续重建两次，验证观察身份与来源、重复请求原结果、事件/回执/游标/审计不变。另验证 Presence 删除/损坏及 World/Clock 损坏修复、未知类型/版本/错误 payload/关系语义/不完整获知失败回滚、写回后故障、FK 校验、坏 reader 契约、多世界及秘密隔离。

[账本测试](../../tests/application/test_ledger.py) 验证新世界位置 1、多事件稳定顺序、世界内递增、并发事务分配、命令失败完整回滚、正整数/唯一约束、UPDATE/DELETE/REPLACE 保护、间隙及反向现实时间不改变回放顺序。

[迁移测试](../../tests/persistence/test_ledger_migration.py) 运行真实 0004 schema 与旧 appender 的测试复现，按相同插入历史确定性回填，保留所有原列/rowid/回执/审计，后续追加越过 migrated max；另验证空库、重复启动、DDL/backfill 故障完整回滚及 WITHOUT ROWID 明确失败。

架构测试禁止 replay 外部副作用、command dispatch 和 canonical mutation capability。既有 C-002 至 C-003D Python 回归继续运行；本任务不需要 GUI/Desktop smoke。不进入 C-003E2。
