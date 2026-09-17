# Import Boundary — C-004A

状态：只建立 canonical 内容 Draft、原始导入 envelope、确定性校验和 Preview → confirmed Commit 的应用边界。没有 Character Card V2/V3、Lorebook、PNG/APNG parser、文件选择 UI、Builder、web research、LLM 或最终 .lworld package。

```text
external source (untrusted)
→ future independent format adapter / parse
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
| canonical root | LivingWorld 理解哪些内容？ | CharacterDefinition / WorldContent / LoreEntry 的 versioned semantic JSON |
| opaque canonical metadata | 哪些兼容数据需要保留但尚未解释？ | JSON extensions、authored_instructions、activation/insertion metadata |
| RawImportEnvelope | 原始外部文件究竟包含什么？ | typed RawImportId、完整 original_payload bytes、来源元数据及 opaque unknown_extensions |

RawImportEnvelope 保留精确 bytes，无需理解原编码或外部字段结构。SHA-256 校验覆盖全部原始 bytes，保留 whitespace/换行/未知字段等 round-trip 证据。C-004A 不实现导出器，也不宣称已经完成外部格式 round-trip。

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

Alembic 0006 只增加独立内容表，不改变既有 runtime projection、history、receipts 或 legacy audit。数据库仍位于既有 app data。细节见 [CONTENT_MODEL.md](CONTENT_MODEL.md) 与 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。

## 4. 安全边界

**Prompt-like imported text == untrusted authored data**。

- system_prompt / creator_note / instruction 等字段名不提升权限；只在 canonical 文本/opaque JSON 或 raw bytes 中保存。
- 不执行指令、不调用工具、LLM、web research、不读文件资源、不运行 prompt insertion/activation。
- extensions 不变成 runtime 行为；原始文件不是 LivingWorld 应用配置，不添加 secret/API key 配置入口。
- 不把作者描述当作 Truth 或玩家已知事实。未来 Agent context 仍需 permission filtering before semantic retrieval，不能用卡片 instruction 解除隔离。
- 来源 ID 不授予外部资料可信性，也不授予其他主体知识读取权限。保留文件内容不意味着授权执行、发布或把它写入日志。

独立 adapter 兼容 Character Card V2/V3、PNG/JSON、Lorebook 是冻结目标；不复制 SillyTavern 源码，也不需要 SillyTavern 运行。C-004A 没有研究或实现这些格式细节。

## 5. 保留事项

外部字段映射/extension namespaces/parser 资源限制、重复导入的用户选择、来源冲突展示、AI Research → Evidence → Claim → Conflict 流程、runtime 初始知识分配、实例定义版本绑定、资产存储布局与 .lworld container 均未实现。它们不影响当前内容库与 runtime 状态分离的已验证边界。

测试见 [test_content_boundary.py](../../tests/application/test_content_boundary.py)、[test_content.py](../../tests/domain/test_content.py) 与 [test_content_persistence.py](../../tests/persistence/test_content_persistence.py)。冻结产品规则见 [PRODUCT_SPEC.md](../product/PRODUCT_SPEC.md)，Stage 2 回归见 [STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)。
