# Stage 2 Final Acceptance — C-003E2

## 范围

Stage 2 建立正式世界状态基础：标准库不可变领域模型、双时间、typed/world-scoped IDs、SQLite/Alembic 独立映射、原子 command/event/projection/receipt、主体知识权限、canonical ledger、内部纯回放、资源级乐观并发。冻结产品规则不变。

**本阶段没有 Director、Character Agent、Memory retrieval、世界模拟、catch-up、LLM 集成或最终 UI。** 没有自动推理、misinformation 检测、belief revision/reconciliation、Observation→Belief 自动形成、Checkpoint/Timeline 或新增业务 HTTP API；这些均为后续范围。本任务不开始 Stage 3。

## Canonical mutation path

```text
internal typed Command
→ canonical semantic fingerprint
→ existing committed CommandReceipt first
→ world/reference/existence + resource expected revision validation
→ domain transition / immutable assertion
→ semantic WorldEvent(s), transaction-local ledger_position allocation
→ projection CAS / expected-absent INSERT / creation
→ CommandReceipt(original result)
→ single atomic commit
```

CreatePlayer 原子创建静态 Player 与唯一 Presence，并发出 PlayerCreated / PlayerPlaced。inactive/offline 保留物理地点，不自动成为见证。Relationship 仅改变有向 source→target，内部三指标范围严格校验，超范围不 clamp，普通玩家没有数值 API。

## 版本、存在与并发

| 命令 | 必填 precondition | 成功版本 |
| --- | --- | --- |
| MovePlayer | expected_presence_revision: Revision | 现存 Presence R→R+1 |
| PlaceCharacter | expected_state_revision: Revision 或 None | None 期待缺失，首次 0；已有状态 R→R+1 |
| ChangeRelationship | expected_relationship_revision: Revision 或 None | None 期待缺失，首次 delta 后 1；已有边 R→R+1 |
| 创建 World/Location/Player/Character、AssertWorldTruth、FormCharacterBelief、AcquireKnowledge | 无 expected revision | 保留既有创建版本 |

None != Revision(0)。版本属于 mutable projection，不是全局 World revision。基础设施 UPDATE 的 WHERE 包含 world、完整主键与 expected revision，rowcount=1 才成功；0 为 ConcurrencyConflictError。期待缺失采用 INSERT，真正 PK/UNIQUE 竞争映射到同一现有错误。错误提供资源类型/身份/预期版本；CAS 失败不为实际版本额外查询。

SQLite writer 物理串行是允许的：命令 UoW 首次读前通过集中 begin hook 使用 BEGIN IMMEDIATE，避免 deferred snapshot 的 read→write 升级问题。各资源仍以 SQL CAS 决定语义成功，独立版本不会因为同世界另一种变更而过期；知识 reader 和只读 store 不取得 command writer。未来数据库 adapter 必须保留 CAS 保障，不能把当前 SQLite 的单 writer 当作唯一正确性条件。

## 幂等、竞争与回滚

- 已提交相同 RequestId + 完整语义（含 expected revision）优先返回原结果，即使 revision 已过期或进程重启。
- 同 RequestId 修改任何语义，包括 precondition，仍是 IdempotencyConflictError。
- 两个独立真实 UoW 同时执行完全相同命令，仅一组事件、一次投影变更、一个 receipt；结果身份/版本一致，其中一个结果标记 replayed。
- 若 lookup 与 event/receipt/资源唯一性竞争相撞，loser 必须先 rollback，再 **一次** fresh receipt 查询：匹配返回原结果，不匹配幂等冲突，无 receipt 保留原失败。绝不重新执行 mutation 或循环重试。
- CAS / INSERT 冲突时，游标分配、已 flush 的事件、投影和成功回执全部回滚。失败命令不留下 WorldEvent 或成功历史。

## Ledger、存储与回放

每世界正整数 ledger_position 唯一、不可变、严格递增，允许间隙；新世界 WorldCreated 从 1 开始，多事件固定 ordinal 顺序获得位置。WorldTime、created_at 与 EventId 都不是 canonical 顺序。append-only UPDATE/DELETE/REPLACE 保护保持；allocator 与命令同一事务。

既有 mutable v1 payload 已重新核验：此前 fold 提供 previous revision，现有前态/edge_existed 与 resulting revision 足够验证递增。没有历史 payload 改写或补偿当前投影。新增 CharacterBeliefFormed v1 后共 12 类受支持 v1 事件。

ProjectionRebuilder 仅从目标世界按 position 升序的事件进行纯 fold，恢复 World/WorldClock、Locations、Player/Presence、Characters/State、Relationships、KnowledgeAssertions 和 Observations。ID、逻辑时间、UTC、owner/source/provenance/metadata 全部来自事件，不采样 clock 或生成新 ID。事件、receipt、cursor、legacy audit 和 Alembic cursor 原样保留。失败完整回滚；World A 重建不影响 B。

Persistence 继续 SQLite WAL + FTS5、复合同世界 FK、ownership/range CHECK、精确 Decimal/JSON/WorldTime 编码。**没有 C-003E2 schema 变更，Alembic head=0005_canonical_ledger**；旧 schema_version/migration_history 仅兼容审计，Alembic 是唯一执行权威。

## Epistemic isolation 与主观根

SQL permission filtering 先于任何语义检索：WorldTruthReader 仅绑定世界 truth，CharacterKnowledgeReader 仅绑定角色 belief，PlayerKnowledgeReader 仅绑定玩家 knowledge。Source/provenance 不授予来源私有存储读取权。

按用户确认，内部 FormCharacterBelief 复用 KnowledgeAssertion，创建新 immutable character_belief、单一 Character owner、无 Player owner。可无 Truth、可与 Truth 矛盾、可无 source；提供 source/provenance 时验证已存在且同世界，原样保存。此路径不创建 Observation 或 expected revision。

AcquireKnowledge 保持 source → Observation → 自有派生 assertion，可复制 false belief，而不提升为 truth。没有自动 inference/reconciliation。矛盾验收是两条 canonical 命令：AssertWorldTruth `door=locked` 与 FormCharacterBelief `Alice: door=unlocked`，不是 stale 历史 Truth 或直接 projection fixture。

## 验收世界与证据

[综合集成测试](../../tests/application/test_stage_2_acceptance.py) 只以应用命令创建全部状态：

1. world_a：三个地点、一个 inactive/busy 玩家、character_a/character_b/character_c/character_d 四角色、首次及再次放置、有向关系及逆向关系、Truth、两种独立 belief root、显式角色及玩家获知。
2. character_b met character_c 的 Truth：仅 character_b/character_c 显式获知；character_d/Player 的绑定 reader 在重建前后都不可读，权威 reader 可读。
3. door locked 的 Truth 与 Alice unlocked 的 belief：同世界共存，重建前后分别由隔离 reader 返回，所有认知元数据一致，不覆盖或调和。optional 私有 source/provenance 不授予权限。
4. World B 重用 A 的 raw UUID，构建独立地点、玩家、角色/状态、关系、Truth、belief 和获知。所有引用仍 typed/world-scoped；B 的序列独立从 1 开始。
5. 两个独立 session 的 Presence 竞争只有一个赢家；unrelated MovePlayer / Relationship 并发均成功；完全相同 MovePlayer 并发只一次变更。A 的竞争不改变 B。
6. 重启重复请求返回原 result；修改语义冲突；跨世界引用拒绝。每个成功命令的 receipt 与固定 ordinal 事件一致，loser 无事件或成功 receipt。
7. UPDATE/DELETE 历史明确失败；保存语义投影后分别 rebuild A/B，全部投影等价、事件/回执/游标/审计不变，秘密与矛盾信念隔离保持。

| 主要性质 | 测试证据 |
| --- | --- |
| 精确 typed revision、stale retry 优先、None 与零版本分离 | [test_concurrency.py](../../tests/application/test_concurrency.py)：exact_expected_revision / absent_and_revision_zero |
| 独立 session 同版本 Move、状态/关系创建竞争，winner replay | 同文件：two_independent_mutations_have_one_winner_and_replay |
| 真并发 duplicate，单事件/多事件与 ObservationId 原结果 | 同文件：concurrent_exact_duplicate_has_one_durable_outcome |
| SQL CAS=0 在事件 flush 后完整回滚；唯一性冲突归类 | 同文件：cas_zero_after_events / optional_insert_constraint_collision |
| event/receipt collision 先 rollback 再一次 fresh resolution | 同文件：event_collision / receipt_unique_collision |
| 逆向关系独立、无全局语义 revision | 同文件：unrelated_resources；综合验收 |
| 主观根无 Truth/source/Observation，完整 payload 回放 | [test_belief_formation.py](../../tests/application/test_belief_formation.py)：belief_root / optional_private_source |
| canonical 矛盾 belief 与 false 信息转述保持 Truth | 同文件：contradictory_root_and_false_information_propagation；综合验收 |
| owner/world 隔离、坏引用/metadata/version 回滚 | 同文件：missing_belief_references / cross_world / invalid_belief_event；[知识回归](../../tests/application/test_knowledge_access.py) |
| 不可变顺序、旧 schema 兼容接管、DDL 失败回滚 | [ledger](../../tests/application/test_ledger.py)、[迁移](../../tests/persistence/test_ledger_migration.py)、[tests/persistence](../../tests/persistence/) |
| 既有 replay 等价、坏历史与写回故障回滚 | [test_replay.py](../../tests/application/test_replay.py) |
| Domain/Application 无 ORM/framework、replay 无副作用、端口能力边界 | [test_architecture.py](../../tests/core/test_architecture.py) |

测试使用 fresh 隔离临时 SQLite 数据库，barrier 同步真正并发调用，不用 sleep 作为主同步机制。无实际用户数据迁移，无 GUI/Desktop smoke；这些不计为本任务已验证内容。

验证命令（仓库根目录）：

```powershell
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest
uv run --frozen python scripts/check-doc-links.py
git diff --check
```

模型细节见 [DOMAIN_MODEL.md](DOMAIN_MODEL.md)、[COMMAND_MODEL.md](COMMAND_MODEL.md)、[PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)、[EVENT_MODEL.md](EVENT_MODEL.md)、[KNOWLEDGE_ACCESS_MODEL.md](KNOWLEDGE_ACCESS_MODEL.md) 和 [REPLAY_MODEL.md](REPLAY_MODEL.md)。
