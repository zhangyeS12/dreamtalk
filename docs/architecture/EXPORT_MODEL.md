# External Content Export — C-004D1

状态：独立离线 JSON export adapter 与应用层导出接口已建立。只生成 bytes，不保存文件、不推进内容 revision、不进入 runtime command/event/receipt 管线。

```text
canonical export != original source bytes
Imported Content != Runtime State
LoreEntry != WorldTruth
```

## 1. 输入、输出与边界

[ExportService / contracts](../../services/core/src/livingworld/application/exports.py) 接受显式 ExportRequest：已验证的封闭 ContentDraft、typed content_id、ExportTarget，以及需要时的 lore selection / CharacterBook version / V3 book policy。应用层不 import 外部 schema 或 ORM；[JsonContentExporter](../../services/core/src/livingworld/infrastructure/exports/json_content.py) 在 infrastructure/export adapter 内解释外部格式。domain 与 runtime 不依赖 exporter。

Draft 可以是未提交快照，也可以由调用方通过现有 ContentRepository.load/load_asset/load_raw_import 读取并显式组装。exporter 没有 repository、数据库、文件系统、Kernel、知识 reader、网络或 shell 能力，不会隐式加载依赖。

ExportResult 包含 target_format、serialized_bytes、application/json、建议 .json、不可变 typed warnings 和 semantic_hash。哈希是生成对象经确定性 UTF-8 JSON 编码后的 SHA-256；不包含调用时钟、随机 ID 或文件名，也不等于输入内容 hash / raw hash。调用方决定后续保存位置，本任务没有 save UI 或 filesystem writer。

每次输出先通过对应格式的结构校验，再通过有限 UTF-8 JSON 校验。复用 C-004B/C1 的纯结构 validators，不重解析原卡片/PNG，不复制 SillyTavern 实现。错误只有稳定 code/path，不包含作者文本、secret 或 original bytes。

## 2. 格式选择

| 显式 target | 输入根与输出 |
| --- | --- |
| character_card_v2 | CharacterDefinition → spec=chara_card_v2 / spec_version=2.0 |
| character_card_v3 | CharacterDefinition → spec=chara_card_v3 / spec_version=3.0 |
| sillytavern_world_info | 一个 LoreCollection → entries object map |
| character_book | 一个 LoreCollection → 可嵌入的 book object；必须明确 CharacterBookVersion.V2 或 V3 |

不按 filename 推断，不隐式 downgrade。原始 bytes 检索仍是现有 load_raw_import 的独立能力；canonical export 始终重新生成当前内容，不返回 raw payload。

## 3. Canonical 优先和兼容合并

每个格式边界独立处理 unknown fields：过滤目标拥有的结构/已知字段路径 → 序列化当前 canonical 值覆盖 → 校验。没有任意递归 deep merge。spec/spec_version/data、name、tags、正文、keys、secondary keys、enabled/order 等不能被 source unknown_data 覆盖；已删除的 optional known semantics 也不会被 stale raw 值恢复。

同格式恢复受控 unknown_top_level / unknown_data / external_extensions 或 book/entry unknown_fields。不同格式不注入 opaque source extensions，发出 target_format_does_not_preserve_source_extension。集合 origin 不能使外来条目的未知 metadata 获得同格式待遇；每个条目也验证自身来源 family。

ST 未被 C-004C1 理解的 position/selectiveLogic 源 enum 在同格式且 canonical 未指定时可原样保留，发出 source_unsupported_semantic_preserved，不解释或选取替代值。可理解字段必须来自当前 canonical；fractional order 的旧源值不会覆盖 canonical integer。

## 4. Character Card

name/description/personality/scenario/creator_notes/tags 使用当前同义字段。first_mes/system_prompt/post_history_instructions/alternate_greetings 使用当前 authored_instructions.character_card；creator/character_version 使用当前 card compatibility state。mes_example 使用当前唯一 example_dialogue block，空集合表示空字符串，不从旧源恢复已删除正文。

canonical 多个 example_dialogue blocks 没有定义到单个外部字符串的拼接规则；返回 typed example_dialogue_serialization_required。调用方须明确准备一个导出 block，exporter 不猜 delimiter、不写回内容库。aliases/background/speech_guidance/legacy lore_entry_ids 等没有已定义外部字段的语义发出损失警告，不私藏于自创 extension。

V3 映射已表示的 nickname、multilingual notes、source、group greetings 和 source dates；不采样当前时间。V2→V3 没有 group greetings 时输出必需的空数组，没有资产时输出空 assets 数组；不创造昵称、URL、日期、资产或多语言备注。V3→V2 省略不能表达的字段并逐字段发出 v3_field_not_representable_in_v2，保留 LivingWorld 内部来源。较新 source V3 version 导出为当前 3.0 时发出 source_schema_version_not_preserved，不伪称保留版本。

V3 ContentAsset 使用当前 descriptor/reference。data URL 的明确 raw pointer 只从已提供 envelope 的 preserved descriptors 恢复；不下载、读取、解码或物化资产。JSON 不能携带 PNG container-image / embedded-file 资源，保留 descriptor 并发出 export_asset_reference_not_packaged。无已知 descriptor 的 generic asset 省略并 warning，不猜 URI/type。

## 5. 嵌入集合选择

0 linked collections：不写 character_book；尚未规范化的旧 raw book 不代替 canonical 集合，发出 warning。

1 linked collection：自动嵌入该集合。多个 linked collections：没有 selection 时省略并发出 multiple_lore_collections_require_selection；显式选择必须属于当前定义的 lore_collection_ids，且只嵌入选中的集合。不 merge，不注入 legacy unbound entries。

## 6. Lorebook 和已接受的三项规则

只序列化集合 owned canonical entries，按集合成员引用解析；完整来源中因空白正文省略的条目不会复活。keys/secondary keys、正文、enabled、order 等使用当前 canonical；regex-looking 字符串不编译、改写或翻译。

**V3 use_regex：**当前 activation_metadata 中明确的 bool 表示 explicit true/false；键缺失表示 unspecified。历史 source_entry 或未知 source fields 不是已删除/current metadata 的回填来源。明确值优先于 caller policy；unspecified 必须由 V3CharacterBookOptions(use_regex=bool) 提供显式导出决策，否则抛 ExportDecisionRequiredError(code=v3_use_regex_decision_required, path=...)。选项只用于该 V3 book 中 unspecified entries，不是全局设置；使用 policy 时逐条发出 v3_use_regex_supplied_by_export_policy，不改 canonical state。格式、斜线和 regex-looking keys 不能推断 bool。

**V3 secondary_keys：**遵循 typed-array 定义，输出 canonical array 的原顺序，包括空数组；ambiguous source string 不 split、不 join、不重新插入 known field。

**ST comment：**只取 canonical comment。title != comment（包括 title-only）时发出 lore_title_not_representable_in_st_world_info；不拼接、不提升 title、不创建私有 target field/extension。

ST 将已知 symbolic logic/position 映回公开 numeric enum；activation metadata 的 probability/useProbability、groups、timed effects、vectorized、case/match/scan、recursion、automation 等只保存显式值。CharacterBook 只映射其已知支持字段；不支持的 activation/position/group 等逐项 warning，结构错误明确失败。current case_sensitive / caseSensitive 若同时存在且值冲突，返回明确错误，不按来源或 dict 顺序猜测优先级。

## 7. External identity、顺序与确定性

ST uid / CharacterBook id 为 export-local 整数，不使用 LoreEntryId UUID。符合 source family、非负 JS-safe integer、无书内 collision 的源 ID 可保留；否则从最小未占用非负整数确定性分配，先保留全部候选 ID，避免覆盖后续条目。无法保留已有源 ID 时发出 source_uid_reassigned；从无来源的新内容分配 ID 不伪称来源。

JSON object keys 排序、紧凑编码，作者数组保持顺序，无 NaN/Infinity。相同快照/target/options 产生相同 bytes/hash/warnings；warnings 按 path/code/message 排序去重，不依赖 dict insertion order。ST object-map 的排序可能不能保留 canonical administrative member order；发生时发出 lore_member_order_not_preserved_by_st_object_map，entry.order 本身仍保持 canonical 值。不会为保存源 UID 而覆盖条目。

## 8. 验证与未实现范围

[Export tests](../../tests/application/test_content_export.py) 验证 V2/V3/ST semantic round-trip、embedded book、known edit/delete 优先、same-format unknown 保留、跨格式损失、三项已接受规则、selection、UID、重启，以及有真实非空 Truth/Belief/PlayerKnowledge 的完整 SQLite 表与 ledger/receipt 快照不变。[Architecture tests](../../tests/core/test_architecture.py) 限制出口 capability；network/shell/file/regex instrumentation 验证导出文本惰性。

没有新增 dependency、migration、表或 runtime event。没有 GUI smoke、PNG/APNG writer、CHARX、asset materialization/download、native archive/.lworld、backup/restore、lore activation、prompt assembly、LLM、Memory、Director、Agent 或 final UI。C-004D2 未开始。

公开规范核对日期：2026-09-17：[V2](https://github.com/malfoyslastname/character-card-spec-v2/blob/main/spec_v2.md)、[V3](https://github.com/kwaroran/character-card-spec-v3/blob/main/SPEC_V3.md)、[ST World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)、[ST public field/enum declarations](https://github.com/SillyTavern/SillyTavern/blob/release/public/scripts/world-info.js)。V3 secondary_keys 的 interface/prose 冲突按用户确认采用 array。
