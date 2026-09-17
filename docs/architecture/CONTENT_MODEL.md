# Canonical Content Model — C-004A

状态：Stage 3 的标准库内容模型、确定性 canonical JSON、校验及独立 SQLite 内容库已建立。C-004B 增加独立 Character Card V2/V3 JSON/PNG/APNG 导入适配器；Lorebook 语义规范化、Builder、LLM、prompt assembly、运行时实例化和最终 UI 尚未实现。

```text
Imported Content != Runtime State
CharacterDefinition != Character
WorldContent != World
LoreEntry != WorldTruth
Prompt-like imported text == untrusted authored data
```

实现：[models.py](../../services/core/src/livingworld/domain/content/models.py)、[identifiers.py](../../services/core/src/livingworld/domain/content/identifiers.py)、[serialization.py](../../services/core/src/livingworld/domain/content/serialization.py)。导入边界见 [IMPORT_MODEL.md](IMPORT_MODEL.md)，Stage 2 不变量见 [STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)。

## 1. 内容与运行实例

CharacterDefinition 描述创作人格与素材，Character 是某个运行世界中的参与身份。未来可以从一个定义实例化多个世界中的角色；C-004A 不增加 runtime definition FK、不修改 CharacterCreated、不实现实例化流程，也不把导入名称自动绑定到现存角色。

WorldContent 描述创作设定，World 是一个运行时间线。保存内容不会创建 World、Location、Character、WorldEvent、WorldTruth、CharacterBelief、PlayerKnowledge 或 Observation。未来实际实例化及事实断言必须通过 Kernel 的 command/event/projection/receipt 管线，不能借内容 repository 绕过。

## 2. 主要内容对象

| 对象 | Purpose | Owns | Does not own | Relationships | Important invariants |
| --- | --- | --- | --- | --- | --- |
| CharacterDefinition | 角色的创作定义 | display_name、aliases、description、personality、background、scenario、speech_guidance、creator_notes、authored_instructions、example_dialogue、tags、assets、lore_entry_ids、extensions、provenance | 运行地点、Memory、Knowledge、关系指标、运行 projection revision | 引用 LoreEntry 与 ContentAsset，未来供 Character 实例化 | 独立 CharacterDefinitionId；非空名称；prompt-like 文本只为数据；没有 world_id |
| WorldContent | 世界的创作素材 | title、description、setting、rules、factions、locations、lore_entry_ids、tags、assets、extensions、provenance | 运行 WorldClock、Truth、ledger、参与者状态 | 引用 LoreEntry 与 ContentAsset，未来供 World 实例化 | 独立 WorldContentId；title 非空；地点/阵营 key 在各自集合内唯一；rules 不执行 |
| LoreEntry | 独立可引用的 lore 素材 | title、comment、content、keywords、secondary_keywords、enabled、priority、order、scope、category、group、activation_metadata、insertion_metadata、extensions、provenance | WorldTruth、检索、激活、prompt insertion | 可被多个 CharacterDefinition / WorldContent 引用 | 独立 LoreEntryId；即使 disabled，正文也不能为空；secondary keys 需要 primary keys；metadata 不触发行为 |
| ContentAsset | 资产引用元数据 | asset_id、media_type、resource_reference、可选 content_hash、opaque extensions | 图片处理、文件读取、二进制存储、package layout | AssetReference 通过 ID 与 role 引用 | typed ID；非空 media type/reference；相同 ID 的已存元数据不可覆盖 |
| ContentProvenance | 创作/导入来源记录 | source_kind、source_format、source_format_version、original_name、source_identifier、imported_at、content_hash、raw_import_id | 来源真假判定、copyright policy、凭证、运行知识权限 | 导入来源指向 RawImportEnvelope | imported_at 必须 aware 并归一化 UTC；hash 为小写 SHA-256；不采样时间或联网 |

AuthoredPlace / AuthoredFaction 仅包含局部 key、name、description、opaque extensions，不是 runtime LocationId 或阵营模拟。AssetReference 包含 ContentAssetId 与用途 role；不把资产 bytes/base64 内嵌正常 canonical JSON。

## 3. 身份、版本与编辑

- 内容库 ID 沿用独立不可变 typed UUID 风格，只有 value，不携带 runtime WorldId；没有世界作用域可编码。同一 UUID 在不同 typed 内容对象中可共存，同类型重复 ID 拒绝。不得使用 CharacterId 作为 CharacterDefinitionId。
- CharacterDefinition、WorldContent、LoreEntry 各自拥有 ContentRevision，初始非负整数 0。它不等于 Stage 2 Revision、WorldEvent ledger_position、canonical schema version 或来源格式版本。
- 内容对象是防御性冻结的快照；编辑产生同 ID 的新快照，数据库要求当前预期版本与恰好下一版本。未来编辑不是永久禁止；当前只保留最新版本，没有协作编辑或 revision history。
- Draft 内不变依赖可按其实际 ContentRevision 明确保留；同 ID 改正文却不推进版本、期待创建但已有 ID、版本过期均显式失败。没有自动覆盖、去重、合并或循环重试。
- RawImportEnvelope 与 ContentAsset 是保留证据/引用记录，同 ID 仅可复用完全相同数据；替换元数据需新 ID。内容 revision 不充当资产存储历史。

集中常量为 [LIVINGWORLD_CONTENT_VERSION](../../services/core/src/livingworld/domain/content/__init__.py)=1。每个 root 显式包含 content_version，反序列化拒绝未知版本。

```text
content_version != api_protocol != Alembic revision != world_package_format
ContentRevision != runtime Revision != ledger_position
```

即使不同版本轴恰好都是 1，也没有联动。最终 .lworld archive/container 留给 C-004D。

## 4. Canonical JSON 与哈希

root envelope 为 `{ "kind": "character_definition|world_content|lore_entry", "data": ... }`。data 包含该类型全部 canonical 字段；UUID 保存小写 32 字符 hex，ContentRevision 保存整数，现实时间保存固定微秒精度 aware UTC ISO-8601，集合保存 JSON array。

JSON object keys 排序，紧凑 separators，UTF-8，无非有限数。作者数组顺序有语义，保留不排序；opaque extensions 深度冻结并往返。serialize → deserialize 保持 canonical 相等；semantic_hash 是完整 canonical UTF-8 JSON 的 SHA-256，包含 typed kind、ID、revision、provenance 与正文。因此它不是跨身份内容去重器，也不等于原文件哈希。

该格式定义 LivingWorld 当前 Python canonical 编码，不宣称 RFC 8785 或跨语言浮点归一化。内容不做 Unicode 文本改写；无效 UTF-8 surrogate 明确拒绝。原始文件排版、编码及未知顶层字段通过 raw preservation 保留，不能靠 canonical JSON 恢复原文件 bytes。

canonical 反序列化仅解释 LivingWorld 格式，不解析外部 Character Card。重复 JSON object keys、未知 canonical kind/version/字段、错误 typed ID、naive 时间、错误 trigger/引用结构均 fail closed。未知外部字段放 opaque extensions 或原始 envelope，不能注入 canonical runtime 字段。

## 5. 校验、持久化与安全

ContentDraft 是包含 roots、assets、raw_imports 的封闭引用图。校验同类型重复 ID、缺失 LoreEntry/asset/raw 引用、来源 hash/metadata 不一致等局部可判定结构；不会打开资源路径、检查图片 bytes 或执行 metadata。需要引用已存依赖时，可信应用先加载并明确加入 Draft，不悄悄补全。

内容保存使用独立 [ContentRepository](../../services/core/src/livingworld/application/content.py)，没有 runtime UoW、event appender 或知识写入端口。SQLite 的三个 typed root 表分别保存 ID、title、content_version、ContentRevision、semantic_hash 及 canonical JSON；资产引用与原始导入各有独立表。详见 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。当前无删除 API，引用图在校验与整批事务内建立；正文与引用不做不必要的逐字段/逐文本规范化。

所有导入文本、creator notes、authored_instructions、rules 及扩展都是不可信创作数据。字段名 system_prompt / instruction 不授予 application/system 权限。当前没有执行、prompt assembly、LLM 或知识读取效果；未来上下文组装仍须先做主体权限过滤。Provenance 不存 API key/secret；原始文件只作为内部保留证据，不写日志或自动展示给玩家。

## 6. 验证与后续边界

- [内容领域测试](../../tests/domain/test_content.py)：身份/时间/版本分离、冻结、三个 root round-trip、哈希与拒绝无效结构。
- [导入边界测试](../../tests/application/test_content_boundary.py)：Draft/Preview/确认、opaque bytes/extensions、内容提交不改变真实事件或各主体知识，runtime rebuild 不影响内容库。
- [内容持久化测试](../../tests/persistence/test_content_persistence.py)：重启、原始 bytes/provenance/typed ID、原子编辑/回滚、旧 schema 升级及失败回滚。

C-004B 的外部格式映射和 parser 见 [CHARACTER_CARD_COMPATIBILITY.md](CHARACTER_CARD_COMPATIBILITY.md)。canonical 类型和 content_version 保持不变：非空源标签原样映射（不 trim、不改大小写、不去重），空白标签仅从 canonical tags 中省略，完整数组仍保留在来源兼容数据与 raw envelope，并显示非阻断 Preview warning。名称仍须满足既有非空约束，不发明缺省名称。

卡片 greeting、system/post-history 文本是 authored_instructions 中的来源数据；不是 Message/Conversation，也不执行模板或替换系统权限。昵称独立保存在 compatibility metadata，不替换 display_name，不推断 aliases。嵌入 character_book 保留完整来源对象及角色卡 provenance，尚不生成 LoreEntry。

V3 ContentAsset 只保存 descriptor/reference 元数据。PNG/APNG icon 的 ccdefault 指向 raw envelope 的 container-image，data URL 的原值通过 raw descriptor 恢复，不在 canonical asset JSON 内复制二进制 base64；无文件物化、网络读取或资产运行效果。

C-004D 才处理 archive/asset layout。初始知识分配、运行实例与定义版本绑定、产品级重复导入/冲突展示、Builder 来源评价和编辑历史仍是后续设计范围，未通过本任务隐式解决。
