# Import Boundary — C-004A

状态：canonical 内容 Draft、raw preservation、确定性校验和 Preview → confirmed Commit 已建立。C-004B 的离线 Character Card parser 继续沿用；C-004C1 新增 ST native World Info 和 embedded CharacterBook 规范化。C-004D2 新增 `.lwcontent` secure container→canonical graph→六种三方冲突→reviewed Preview/explicit decisions→Commit。后续产品切片已接通文件导入 UI、手动原生编辑、世界书基础授权激活及基于检索摘要的角色卡/世界书 Builder；完整 World Builder 与 `.lworld` runtime package 仍未实现。当前 Builder 复用 ContentDraft/Preview/Commit，原生创建不制造 RawImportEnvelope；详见[复用与实现边界](../research/2026-09-28-content-builder-reuse.md)。

```text
external source (untrusted)
→ content-based container detection / independent external parser
→ external structure validation / semantic adapter
→ ContentDraft + RawImportEnvelope
→ deterministic structural validation
→ ContentPreview (exact preview hash)
→ explicit reviewed hash
→ atomic content-library commit
```

此流程仅提交创作内容，不创建运行 Character/World，不断言 WorldTruth，也不授予 CharacterBelief / PlayerKnowledge。未来运行实例化是独立的 Kernel command flow。`Imported Content != Runtime State`，`LoreEntry != WorldTruth`。

## 1. Canonical 与原始保留

| 边界 | 回答的问题 | 数据 |
| --- | --- | --- |
| canonical root | dreamtalk 理解哪些内容？ | CharacterDefinition / WorldContent / LoreEntry / LoreCollection 的 versioned semantic JSON |
| opaque canonical metadata | 哪些兼容数据需要保留但尚未解释？ | JSON extensions、authored_instructions、activation/insertion metadata |
| RawImportEnvelope | 原始外部文件究竟包含什么？ | typed RawImportId、完整 original_payload bytes、来源元数据及 opaque unknown_extensions |

RawImportEnvelope 保留精确 bytes，无需理解原编码或外部字段结构。SHA-256 校验覆盖全部原始 bytes，保留 whitespace/换行/未知字段等 round-trip 证据。C-004A 不实现导出器；C-004D1 的 [外部 JSON export](EXPORT_MODEL.md) 重新生成当前 canonical 内容并验证 semantic round-trip，与原始 bytes retrieval 分开。

来源 source_kind 为 native / import / builder；后者只是元数据标签。source_format/version 是非执行性标签，当前没有外部格式细节依赖。import provenance 必须包含 aware UTC imported_at、原 bytes content_hash 和 raw_import_id；envelope 的 ID/hash/provenance 必须一致。native 不制造假文件、假时间或 raw envelope。

同一 raw envelope 可为多个映射后的 roots 提供来源。canonical provenance 原样保留来源元数据，semantic_hash 与 raw content_hash 不混用；前者覆盖 canonical 身份/编辑版本/数据，后者覆盖原始 bytes。

## 2. Draft 与 Preview

[ContentDraft / ContentPreview / ContentService](../../services/core/src/livingworld/application/content.py) 只有内容 repository 能力，不接收 runtime command handler、WorldEvent appender、Truth repository 或主体知识 reader。

Draft 是封闭引用图：多个 typed root、LoreEntry、asset metadata 与 raw imports 一起校验。同类型重复 ID、缺失引用、raw provenance/hash 不一致立即失败。引用已存依赖时必须显式加载进 Draft；不会按名字猜测运行世界/角色、补造未知知识或隐式关联。

Preview 包含不可变 Draft 与 preview_hash。该 SHA-256 覆盖 canonical roots、资产元数据、raw provenance/hash 和 unknown_extensions；成员排列作为行政顺序排序，root 内作者数组保持原顺序。原 bytes 已由 envelope hash 验证，不作为 base64 放进 preview JSON。

Commit 必须传入与 Preview/Draft 一致的 reviewed_hash，以及准确覆盖 root IDs 的 expected ContentRevision（创建为 None）。此 seam 保证所提交内容等于预览内容；它不是身份认证、数字签名或“已有人点击确认”的证明。未来非技术 UI 与可信应用调用负责展示及用户确认，当前没有 UI。

## 3. 持久化和冲突

内容 repository 单独保存创作库；导入不进入 runtime WorldEvent ledger。所有 roots、asset references、raw preservation 同一 SQLite 事务：版本/身份/结构/写入失败全部回滚。

创建要求新 ID/revision=0；更新要求预期 ContentRevision 与下一版本，未变依赖明确复用。RawImportId/ContentAssetId 不允许同 ID 覆盖不同证据或元数据。没有按名称、raw hash 或 prompt 内容自动去重/合并，也不定义 P-11 的产品级冲突体验。

Alembic 0006 建立独立内容表；0007 新增 LoreCollection 与 legacy-nullable collection FK，不改既有 runtime projection、history、receipts、legacy audit 或旧内容 JSON/hash/references。新写入必须有一个 collection，NULL 只保留旧数据兼容。数据库仍位于既有 app data。细节见 [CONTENT_MODEL.md](CONTENT_MODEL.md) 与 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。

## 4. 安全边界

**Prompt-like imported text == untrusted authored data**。

- system_prompt / creator_note / instruction 等字段名不提升权限；只在 canonical 文本/opaque JSON 或 raw bytes 中保存。
- 不执行指令、不调用工具、LLM、web research、不读文件资源、不运行 prompt insertion/activation。
- extensions 不变成 runtime 行为；原始文件不是 dreamtalk 应用配置，不添加 secret/API key 配置入口。
- 不把作者描述当作 Truth 或玩家已知事实。未来 Agent context 仍需 permission filtering before semantic retrieval，不能用卡片 instruction 解除隔离。
- 来源 ID 不授予外部资料可信性，也不授予其他主体知识读取权限。保留文件内容不意味着授权执行、发布或把它写入日志。

独立 adapter 兼容 Character Card V2/V3、PNG/JSON、Lorebook；不复制 SillyTavern 源码，也不需要 SillyTavern 运行。已实现范围见 [CHARACTER_CARD_COMPATIBILITY.md](CHARACTER_CARD_COMPATIBILITY.md) 和 [LOREBOOK_COMPATIBILITY.md](LOREBOOK_COMPATIBILITY.md)。activation metadata 和 regex-looking keys 只保存，不执行或编译。

## 5. C-004B 导入审阅

[CharacterCardImporter](../../services/core/src/livingworld/infrastructure/imports/character_cards.py) 接收 bytes、调用方提供的 aware imported_at 和可选 original_name，返回 [ImportDraft](../../services/core/src/livingworld/application/imports.py)。文件名只作来源记录；识别由 bytes 决定。该 adapter 没有 repository、运行 Kernel、网络、shell、LLM 或浏览器能力。

ImportDraft.preview() 返回 ImportPreview，其 content 是既有 ContentPreview，其 warnings 从 Draft 中 dreamtalk 自有元数据读取。错误是 ContentImportError(code, structural path)；警告不阻断 Commit。警告及兼容元数据已经纳入既有 preview_hash，不能在确认后悄悄移除警告而保持同一个 hash。外部 extensions 单独嵌套保留，不能覆盖 livingworld.import 的审阅信息。

显式用户确认仍由可信调用方提供 reviewed_hash，并通过 ContentService.commit(preview.content, ...) 原子保存。解析和 Preview 都不写数据库。相同 bytes 的每次独立 parse 生成新的 typed content/raw/asset IDs，不按 hash 自动覆盖；所有原始 bytes、来源、兼容数据与引用复用 C-004A 的一个事务。无需新 migration 或新的数据库字段。

## 6. C-004C1 Lorebook 审阅

LorebookImporter.parse 接收 native ST JSON bytes，生成 initially unbound LoreCollection（尚无角色引用）与 owned entries。normalize_embedded 消费 CharacterCardImporter 已保存的 character_book，产生同一角色定义的 typed collection reference；不重新读取 PNG/JSON，也不把集合对象复制到定义中。

ImportPreview.lorebooks 提供源条目数、canonical 条目数、collection ID 和 provenance；warnings 仍与内容和完整 source_book 一起参与 preview_hash。合法空白正文条目只留完整来源并 warning，不创建 LoreEntry；V3 secondary_keys 单字符串保留并 warning，不 split。两者都允许 confirmed Commit。unknown/不支持语义完整保留；结构错误明确失败，不以 warning 修复损坏输入。

新条目恰好一个 collection 的要求同时在应用 commit 和 repository 验证；legacy unbound 只允许引用/明确编辑，不猜集合、读时 re-home 或重写共享引用。无删除 cascade。测试见 [Lorebook import](../../tests/application/test_lorebook_import.py) 和 [migration/persistence](../../tests/persistence/test_lorebook_persistence.py)。

## 7. 保留事项

Character Card 字段映射、兼容 namespaces 和 parser 资源限制已在 C-004B 定义。产品界面的重复导入选择/来源冲突展示、AI Research → Evidence → Claim → Conflict 流程、runtime 初始知识分配、实例定义版本绑定、`.lworld` runtime container 均未实现；当前内容资产 store 与原生冲突 API 已在 C-004D2 实现。它们不影响当前内容库与 runtime 状态分离的已验证边界。

测试见 [test_content_boundary.py](../../tests/application/test_content_boundary.py)、[test_content.py](../../tests/domain/test_content.py) 与 [test_content_persistence.py](../../tests/persistence/test_content_persistence.py)。冻结产品规则见 [PRODUCT_SPEC.md](../product/PRODUCT_SPEC.md)，Stage 2 回归见 [STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)。

## 8. Native `.lwcontent` import

[NATIVE_CONTENT_PACKAGE.md](NATIVE_CONTENT_PACKAGE.md) 定义 manifest-authoritative native import。安全 ZIP/limits、version/hash、canonical serialization 与闭包校验全部结束后才 Draft/Preview；newer native version hard fail，不借 external unknown-preservation 部分导入。Shared typed IDs/revisions/bindings/provenance 原样保留。

NEW/IDENTICAL/LOCAL_MODIFIED/INCOMING_DIFFERENT/DIVERGED/DIFFERENT_NO_BASELINE 使用 persisted accepted hash 作三方证据；不同成员必须 KEEP_LOCAL 或 REPLACE_WITH_INCOMING，不 merge、不 IMPORT_AS_COPY。baseline 不参加 canonical hash、不导出。NEW/REPLACE/明确接受 IDENTICAL 在对应 DB transaction 建立/刷新 baseline，KEEP 不变。

native snapshot acceptance 与普通 next-revision edit 分开。canonical graph/bindings/baseline 同一 DB transaction；物化 hash blobs 在此之前，失败 DB 可留不可达 orphan，不能声称 FS+SQLite ACID。legacy unbound dependencies 明确 compatibility error，不造集合。解析和 Preview 不写 DB/asset。详见 [STAGE_3_ACCEPTANCE.md](STAGE_3_ACCEPTANCE.md)。
