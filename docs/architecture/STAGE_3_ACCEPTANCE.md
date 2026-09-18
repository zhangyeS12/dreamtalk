# Stage 3 — Authored Content Final Acceptance

Stage 3 建立持久化 canonical authored-content、独立外部兼容 adapter 与 portable `.lwcontent` package；它们与 Stage 2 的 canonical runtime ledger/knowledge/receipts 保持隔离。

## 1. 验收生态与流程

受控 [package fixtures](../../tests/package_fixtures.py) 在内存生成一个 WorldContent、两个 CharacterDefinitions、CCv3-origin 与 ST-origin LoreCollections、shared character/world lore references、完整来源与两个共享 bytes 的 local test Asset IDs。包含非零 authored revisions、reference-only V3 资产、unknown external metadata；无网络下载或巨型提交 binary。

[综合验收测试](../../tests/application/test_native_content_package.py) 执行：

```text
Stage-2 commands → runtime world/player/character state/relationship
               → WorldTruth/private CharacterBelief/PlayerKnowledge
authored ecosystem → canonical JSON → atomic content persistence → restart
→ external export → .lwcontent export → secure parse → Preview → explicit Commit
→ clean DB/store → canonical comparisons → CCv3/ST external export/re-import
```

native importer 保留 typed IDs、revisions、bindings、provenance、raw bytes、未知 metadata、asset references 与 verified blobs。多个 canonical references 指向同一个 shared collection；两个 Asset IDs 的同 bytes 在物理 store/ZIP 中只一个 blob。选择 roots 后只包含闭包，不带无关 library 内容。

## 2. 主要不变量

| 证明 | 验证方式 |
| --- | --- |
| canonical semantic equivalence | 全部 root、asset、raw snapshot 往返及 preview_hash 比较，非零 revisions 原样 |
| backward-compatible WorldContent refs | 缺字段→空 refs→原 JSON/hash；非空 refs typed round-trip；direct-entry refs 共存 |
| restart | 新 database/store composition 重新加载并再次生成相同 semantic manifest/member data |
| external→native→external | CCv3 understood fields/embedded book/same-format unknown 及 ST exportable semantics 相同，沿用 C-004D1 决策规则 |
| six-way conflict evidence | NEW/IDENTICAL/LOCAL_MODIFIED/INCOMING_DIFFERENT/DIVERGED/DIFFERENT_NO_BASELINE，通过真实 persisted baseline/local edits |
| baseline acceptance | NEW/IDENTICAL 建立，REPLACE 更新，KEEP_LOCAL 不变；local metadata 不进入 export/canonical hash |
| no stale overwrite | Preview 后修改本地 snapshot，提交失败；不按 higher revision 自动选择 |
| DB graph atomicity | 中途 asset failure 不提交；baseline INSERT failure 回滚所有内容/source/binding/baseline，orphan bytes 不可达 |
| asset integrity/dedup | 实算 SHA-256/size、并发 exact reuse、different bytes separation、损坏/缺失不可 silent repair |
| container fail-closed | traversal/drive/UNC/backslash/NUL、duplicate manifest/member、symlink/special、超限/ratio/stream、hash corruption、缺失与额外 member |
| version discrimination | malformed/unknown native semantics 明确拒绝；newer version 包含未来 fields 仍明确 unsupported |
| runtime untouched | 原环境 World/Clock/Player/Presence/CharacterState/Relationship/Knowledge/Observation/Event/Receipt/cursor 完整 snapshot 不变 |
| clean import is content only | 新库所有 Stage-2 runtime tables 行数均为零；不 Create World/Character/Knowledge |
| raw secret canary exclusion | canaries 只置于 private Belief、PlayerKnowledge、credential-like env setting 与 runtime log；扫描实际 ZIP bytes 和全部 member bytes 均不出现 |
| inert authored text | template/decorator/regex/assets 是数据；network/shell instrumentation 阻止任何访问；architecture 限制 capability |

## 3. 测试与迁移

完整回归包含既有 Stage 2、C-004A/B/C1/D1 与新增 native package、blob store、0008 compatibility/rollback、architecture tests。测试使用 OS 临时数据库和 app-data store，不迁移实际用户库；没有 GUI smoke、下载或 desktop rebuild。

[0008_native_content_packages](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0008_native_content_packages.py) 为当前 Alembic head，down_revision=0007_lore_collections；AcceptedImportBaseline 与 blob binding 两表是本地元数据。旧 WorldContent 空 refs 的 canonical bytes/hash、旧所有 rows 与 legacy audit 不重写。重复启动只依 Alembic cursor；未知/部分 schema fail closed，注入 DDL failure 完整 rollback。

最终运行测试数量与命令结果见本任务完成报告，不以本文件替代实际执行证据。既有 AnyIO/Starlette dependency deprecation warning 独立于内容架构。

## 4. 已知边界与 deferred work

`.lwcontent` 是 authored content package，**不是 backup、running world 或 `.lworld`**。hash integrity **不是 publisher authentication**。filesystem blobs 与 SQLite **不是同一个 ACID transaction**；failed DB commit 的不可达 immutable orphan 可保留，future GC deferred。

当前只 closure-contained canonical graph；不做 unresolved external dependency、arbitrary field merge、IMPORT_AS_COPY、destructive entry deletion/re-homing、签名/PKI 或任意源文件路径读取。existing legacy unbound dependencies typed fail，不能自动造集合。已有资产引用不自动下载或解码成 blob。

Stage 3 未实现：runtime content instantiation / Create World from WorldContent / CharacterDefinition→Runtime Character；automatic Lore→Truth/Belief；runtime lore activation；prompt assembly；Memory/RAG；Director；Character Agent；LLM；AI Builder；checkpoint/branch；`.lworld` runtime package；cloud sync；marketplace；final UI。Stage 4 未开始。

细节：[CONTENT_MODEL.md](CONTENT_MODEL.md)、[IMPORT_MODEL.md](IMPORT_MODEL.md)、[EXPORT_MODEL.md](EXPORT_MODEL.md)、[NATIVE_CONTENT_PACKAGE.md](NATIVE_CONTENT_PACKAGE.md)、[PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)；运行架构不变量见 [STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)。
