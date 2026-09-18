# Lorebook Import & Canonical Normalization — C-004C1

状态：独立离线 import/normalizer、LoreCollection 内容根、typed reference、Preview warning、原子内容提交及 0007 迁移已实现。C-004D1 增加独立 ST World Info / V2/V3 CharacterBook JSON export。没有复制 SillyTavern 实现，也没有运行时激活、scanner、prompt insertion 或 UI。

**LoreCollection != WorldContent != Runtime World != WorldTruth。LoreEntry 是作者内容，不自动成为 CharacterBelief / PlayerKnowledge / Memory，也不自动变成角色已知事实。**

## 1. 规范与支持边界

外部结构核对日期：2026-09-17。公开来源为 [V2 CharacterBook](https://github.com/malfoyslastname/character-card-spec-v2/blob/main/spec_v2.md)、[V3 Lorebook](https://github.com/kwaroran/character-card-spec-v3/blob/main/SPEC_V3.md)、[ST World Info 文档](https://docs.sillytavern.app/usage/core-concepts/worldinfo/) 和 ST release 的 [字段/enum 声明](https://github.com/SillyTavern/SillyTavern/blob/release/public/scripts/world-info.js)。只用声明核对字段和值，不复制 scanner、转换器或其他实现。

| 来源 | 入口与结果 |
| --- | --- |
| Native ST World Info JSON | `LorebookImporter.parse(bytes, imported_at=..., original_name=...)`；root.entries 必须是 object map；生成独立、未绑定角色的 LoreCollection |
| V2/V3 embedded character_book | 先由 CharacterCardImporter 保存来源表示，再调用 `LorebookImporter.normalize_embedded(imported)`；生成集合并更新同一 Draft 的 CharacterDefinition typed reference |
| PNG/APNG embedded book | 使用 C-004B 已保存的对象；normalizer 不重新解析图片、base64 或卡片 bytes |
| standalone V3 lorebook wrapper、其他 import 格式 | 当前入口不宣称支持；不猜测格式或偷偷转成 ST native JSON |
| external JSON export | C-004D1 提供 ST World Info / CharacterBook，详见 [EXPORT_MODEL.md](EXPORT_MODEL.md) |

实现：[lorebooks.py](../../services/core/src/livingworld/infrastructure/imports/lorebooks.py)。[json_input.py](../../services/core/src/livingworld/infrastructure/imports/json_input.py) 与卡片 adapter 共享严格 UTF-8/duplicate-key/有限 JSON/nesting 校验；不重复实现容器解析。默认 JSON 4 MiB、nesting 64、entries 10,000；LorebookLimits 可配置，这是本地资源策略。

## 2. 内容身份、归属和角色引用

LoreCollection 使用独立不可变 LoreCollectionId、ContentRevision、name、description、有序 LoreEntryId references、provenance、opaque extensions 和 book-level activation_metadata。书可无名称或无 canonical 条目，不制造来源名称。ID 沿用内容库 UUID 风格，无 runtime WorldId。

每个新 canonical LoreEntry 必须显式提供 collection_id，且在 Draft 中归属恰好一个 LoreCollection；集合引用列表必须精确对应其 owned entries。外部 uid/id/object-map key 只保存在来源 metadata，不变成 library identity。不同书都有 uid=0 合法；相同 bytes 两次独立导入产生不同 typed IDs，不按 hash 覆盖/合并。

CharacterDefinition.lore_collection_ids 是最小 typed content reference。它允许沿用既有非拥有引用语义：多个定义可明确引用同一集合，不获得删除权限或知识权限。Standalone collection 初始没有角色绑定。原来的 lore_entry_ids 保留兼容，既有 CharacterDefinition / WorldContent 共享旧条目的引用不改写。

当前无删除 API，无 destructive cascade；条目归属不支持本任务内重新指定，集合编辑不能隐式丢弃已持久化成员。编辑沿用 ContentRevision CAS 和完整闭合 Draft；所有依赖必须显式加入。

## 3. ST native entry 映射

| 来源 | Canonical / compatibility 行为 |
| --- | --- |
| key / keysecondary | keywords / secondary_keywords；不 trim、去重、改大小写或改 Unicode；空白 key 仅省略 canonical 并 warning |
| content | 非空白正文原样映射，不 trim；指令、decorator 都是不可信数据 |
| comment | title 与 comment；完整原字段亦保留 |
| disable | enabled 取反；缺失时沿用外部 false 默认，不激活明确禁用的条目 |
| order | 整数值映射 order；缺失时使用已核对的 native 100 默认；合法 fractional 值保留并 warning，canonical integer 使用其自然默认 0 |
| group | 非空白原值映射 group；空白原值只留 compatibility metadata 并 warning |
| selectiveLogic | 0→AND_ANY、1→NOT_ALL、2→NOT_ANY、3→AND_ALL；原整数始终可恢复，未知值保留并 warning，不猜模式 |
| position | 0/1→before_char/after_char；2/3→before_author_note/after_author_note；4→at_depth；5/6→before_examples/after_examples；7→outlet；未知值不选 placement，并 warning |
| depth / role / outletName | insertion metadata；不插入 prompt、不决定消息位置 |
| probability / useProbability | 独立保存数值与开关；不从 100 推断启用，不做随机抽样 |
| constant / selective / vectorized | activation metadata；不创建 scanner、向量或 embedding 工作 |
| scanDepth / caseSensitive / matchWholeWords | 只保存显式值，包括表示继承的 null；不从全局设置猜值 |
| groupOverride / groupWeight / useGroupScoring | 完整数据保留，不做组竞争 |
| excludeRecursion / preventRecursion / delayUntilRecursion | 完整 metadata，不递归激活 |
| sticky / cooldown / delay | 完整 metadata，不创建计时器、消息计数状态或 WorldTime 转换 |
| automationId / triggers / ignoreBudget / characterFilter | 完整 metadata 保留；不运行 automation、工具、脚本或网络 |
| uid / displayIndex / source map key | source_entry 与源身份/顺序 metadata；不成为 canonical ID/默认排序器 |
| unknown fields / extensions | 完整 source entry、unknown_fields、external_extensions 和原始文件中保留；material warning |

没有明确的 position 或 selectiveLogic 时，不添加猜测值。JS slash-regex keys 包括逗号、JS flags 和 named groups 都是精确保留的字符串；不送入 Python regex engine，不校验 regex 是否可执行。

## 4. Embedded CharacterBook 映射

| 来源 | 行为 |
| --- | --- |
| name / description | 集合的同义文本，完整原对象保留 |
| scan_depth / token_budget / recursive_scanning | 只保存显式 book 设置；缺失与显式 0/false 不混同 |
| keys / secondary_keys string array | 同义 canonical keys，保留源顺序与非空白值 |
| enabled | 直接映射，不覆盖来源禁用状态 |
| insertion_order / priority | 可精确表示为整数时映射；fractional 源值不舍入，保留并 warning |
| name / comment / content | title / comment / 原样非空白正文 |
| case_sensitive / constant / selective / V3 use_regex | activation metadata 数据，不执行 |
| before_char / after_char | 已知 symbolic insertion metadata；不实际插入 |
| id / extensions / unknown fields | 完整来源兼容数据，不建立 runtime 身份 |

**V3 secondary_keys 歧义已按用户决定解决：**数组正常映射；单字符串（例如 `"a,b"`）完整保留，不 split、不推断 secondary keys，发出 `lore_secondary_keys_ambiguous_string_preserved`，Commit 允许。V2 已声明的数组类型错误仍是结构错误。

**空正文已按用户决定解决：**合法外部条目若 `content.strip() == ""`，不创建 canonical LoreEntry；完整源条目保留于集合 source_book、原始 envelope，以及卡片原来的 compatibility 表示。发出 `lore_entry_empty_content_omitted_from_canonical`，包含结构路径和实用的来源身份，Commit 允许。非空白正文不改写。仅包含此类条目的书可以形成零 canonical 条目的集合。

## 5. 审阅、保留和错误

安全理解的语义映射 canonical；合法但无法安全表示的语义保存 raw/compatibility 并 warning；结构错误/不安全数据明确失败，不修复任意损坏书。

ImportPreview.lorebooks 返回集合 ID、source_entry_count、canonical_entry_count 和 provenance；warnings 表示省略项、未知/unsupported 及不执行的 activation metadata。warnings、完整来源与 canonical 图均参与既有 preview_hash，确认后不能悄悄更改。

流程为 source → validated external book → ContentDraft → Preview → reviewed hash → confirmed Commit。normalizer 消费尚未提交的 C-004B Draft；成功规范化后移除原来 embedded_lore_deferred 警告；重复 normalize 明确错误，不重复生成集合。没有文件选择 UI、网络研究或 Builder。

缺失/wrong-type entries、非对象 entry、错误 keys/content/已知字段类型、已知非法概率/非负计数范围、duplicate JSON keys、非有限数、孤立 surrogate 和 parser 超限均为 ContentImportError。未知位置或未知字段是保留+warning，不因未来值丢失数据。

## 6. 持久化与 legacy 兼容

[0007_lore_collections](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0007_lore_collections.py) 新增集合独立内容表，给 content_lore_entries 增加 nullable collection_id FK（无 cascade），不重建旧表、不改 canonical JSON/hash/revision/raw/共享引用，也不创建合成集合。Alembic remains authoritative。

`collection_id = NULL` **仅为 deprecated legacy compatibility state**，不是新创建选项。应用 commit 与 repository 双重拒绝新 unbound entry；旧行可以保留/明确编辑，但不能本任务内重归属，也不会读取时自动迁移。future legacy normalization 是独立产品/迁移决定。

内容 version=1 保留两项精确 additive legacy 编码：旧 LoreEntry 没有 collection_id 表示 legacy unbound，旧 CharacterDefinition 没有 lore_collection_ids 表示空引用。serializer 在这两种状态省略对应字段，保持旧 JSON/hash 原样；仅这两项允许缺失，其他未知/缺失 canonical 字段仍 fail closed。

SQLite transaction 同时保存集合、条目、definition reference、raw/asset 依赖。新归属以 FK + closed graph + 持久化成员精确校验约束；版本错误、归属重指定、成员遗漏或任何失败全批回滚。参考 [CONTENT_MODEL.md](CONTENT_MODEL.md)、[IMPORT_MODEL.md](IMPORT_MODEL.md)、[PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。

## 7. 安全证明与后续边界

受控 [fixtures](../../tests/fixtures/lorebooks/README.md)、[import 测试](../../tests/application/test_lorebook_import.py) 和 [persistence/migration 测试](../../tests/persistence/test_lorebook_persistence.py) 验证 native/embedded、 typed IDs、来源/未知 fields、warning/Commit/reload、旧行无损迁移及 rollback。既有 [architecture 测试](../../tests/core/test_architecture.py) 限制 importer 为 content-only 能力。

核心证明：导入 `New Eridu is surrounded by Hollows.` 后 canonical LoreEntry 存在，但 authoritative WorldTruthReader、CharacterKnowledgeReader、PlayerKnowledgeReader 结果和整个 Stage-2 runtime/WorldEvent/receipt/cursor snapshot 均不变，重启后仍保持。regex/network/shell instrumentation 证明导入字符串不进入相应执行入口；未对实际 app-data DB 执行迁移。

## 8. C-004D1 JSON export

当前 canonical owned entries 才进入导出，raw 中的空白正文条目不会复活，legacy unbound rows 不附加到书。ST comment 仅取 canonical comment，title 不同则 warning；source UID 冲突确定性分配并 warning，不泄漏 LoreEntry UUID。CharacterBook 的 known keys/text/enabled/order 以 canonical 优先；V3 secondary_keys 使用 array，原歧义字符串不回填。V3 use_regex 区分 explicit bool / unspecified；未指定且无 caller policy 时返回 typed decision-required error，不看格式/regex-looking strings 猜值。metadata 仅按明确 target 映射，无法表示则 warning，不执行。详见 [EXPORT_MODEL.md](EXPORT_MODEL.md)。

运行时激活、概率/组/递归/timing、vector/semantic retrieval、RAG、prompt assembly、Memory、Director、Agent、Builder、最终 UI、asset layout 均未实现；C-004C2 / C-004D2 未开始。
