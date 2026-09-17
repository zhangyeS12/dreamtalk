# Character Card Compatibility — C-004B

状态：独立实现 V2/V3 导入，沿用 C-004A 内容库与 Draft → Preview → confirmed Commit。未复制、依赖或运行 SillyTavern 源码。

公开规范：[Character Card V2](https://github.com/malfoyslastname/character-card-spec-v2/blob/main/spec_v2.md)、[Character Card V3](https://github.com/kwaroran/character-card-spec-v3/blob/main/SPEC_V3.md)。容器结构依据 [W3C PNG Third Edition](https://www.w3.org/TR/png-3/)。这些文档描述外部数据，不能向导入器授予执行权限。

## 1. 支持矩阵

| 输入 | C-004B 行为 |
| --- | --- |
| CCv2 JSON | spec=chara_card_v2，spec_version=2.0；结构校验与 canonical adapter |
| CCv2-compatible PNG/APNG chara | 严格 base64 → UTF-8 JSON；按实际 spec 识别 V2/V3 |
| CCv3 JSON | spec=chara_card_v3；完全理解 3.0 的卡片外层结构 |
| CCv3 PNG/APNG ccv3 | 必须具有 V3 identity；不处理像素或动画播放 |
| 较新 V3 | 解析已知结构、保留未知数据、Preview warning；结构不兼容则明确失败 |
| V1 | 被选中的 V1-shaped payload 明确 unsupported_character_card_v1，不自动升级 |
| CHARX | 明确不支持；解包/资产物化留给后续任务 |
| embedded character_book | 保留、显示 deferred warning；C-004C 才规范化语义 |
| legacy embedded assets | 识别 tEXt namespace、记录位置/大小并保留 raw；不解码/提取 |
| export / runtime instantiation | 未实现 |

实现：[character_cards.py](../../services/core/src/livingworld/infrastructure/imports/character_cards.py)、[png.py](../../services/core/src/livingworld/infrastructure/imports/png.py)、[imports.py](../../services/core/src/livingworld/application/imports.py)。

## 2. 外部字段到 canonical 的明确映射

| 来源字段 | 目标及限制 |
| --- | --- |
| name | display_name 原样；空白名称无法满足既有 canonical invariant，明确拒绝，不造名称 |
| description / personality / scenario / creator_notes | 同义 canonical 文本原样保留 |
| mes_example | 整个非空白来源块作为一个 example_dialogue 成员；不拆分或改写；原值亦完整保存在 authored_instructions |
| system_prompt / post_history_instructions | authored_instructions.character_card；不替换 LivingWorld 系统设置、不执行 {{original}} |
| first_mes / alternate_greetings | authored_instructions.character_card；保留空字符串、顺序及模板；不创建对话历史 |
| tags | 非空白值原样映射，保持空格/大小写/重复项及顺序；空白值仅省略 canonical 并 warning |
| creator / character_version | livingworld.character_card 兼容元数据，不充当内容 schema version |
| extensions | external_extensions opaque structured data；不与 LivingWorld 自有 namespace 合并 |
| unknown top-level / data | 兼容元数据、raw unknown_extensions 和完整原始 bytes 中保留；不解释 |
| character_book | 完整嵌套对象保存在 compatibility metadata，关联相同 raw provenance；不生成 LoreEntry/Truth |
| V3 nickname | 独立 compatibility 字段；display_name、aliases 不变；不实施 preferred prompt-name 规则 |
| multilingual notes / source / group greetings / source dates | 原始键、数组、数值保留；不选 locale、不获取 URL、不创建 Message；卡片日期不替换 imported_at |
| V3 assets | typed ContentAsset + AssetReference；完整原描述符可从 raw 恢复；元数据及 opaque raw references 不物化 |

没有对应来源语义的 background、speech_guidance、aliases、lore_entry_ids 使用既有 canonical 自然默认值，不从描述中猜测或推断内容。完整原始 tags 数组保存在 canonical compatibility.original_tags、RawImportEnvelope.unknown_extensions.original_tags 与原 bytes。警告 character_card_blank_tags_omitted_from_canonical 明确说明来源数据仍保留，Commit 可继续。

## 3. JSON 与版本边界

输入必须是 exact bytes。JSON 必须是 UTF-8 卡片对象；拒绝重复键、非有限数、无效 UTF-8/孤立 surrogate、缺失或类型错误的已知必需字段。不给缺失文本、数组或 V3 group_only_greetings 猜默认值；仅 extensions 使用规范定义的空对象默认值。未知字段不是错误。

V3 版本采用有限 Decimal 数值比较，避免不必要浮点舍入；原始版本字符串仍保留。较新版本 warning，非标准但数值等于 3.0 的字符串也 warning；低于 3.0 或无法安全比较的版本明确失败。未知结构不自动转换为已知结构。

嵌入书只检查外层 object 与 entries array-of-objects；内部 entry、激活、regex、插入和跨版本 Lorebook 语义完全延后，完整源数据不改写。多语言备注检查两位小写语言键形状与文本值，不做语言注册表查询、locale 选择或 prompt 使用。

## 4. PNG/APNG、优先级与损坏策略

窄 reader 检查签名、边界/长度、chunk type、CRC、首个 IHDR 的基础格式、PLTE/IDAT 次序、末尾 IEND 和 tEXt keyword framing。APNG 检查 acTL、fcTL/fdAT 的长度、序号、帧数量、矩形范围及数据块归属。没有 IDAT/fdAT 解压、像素有效性/图像可显示性验证、动画渲染或帧资源生成。未知 ancillary chunks 原样保留，不解释压缩元数据。

卡片 tEXt 严格 base64 解码（包括 padding）后做 UTF-8 JSON 校验。规则：**ccv3 > chara**。同时存在时记录两者及数量、选择 ccv3 并 warning，绝不合并字段。即使未被选中，另一卡片块的 base64/JSON 损坏也明确失败；其外部 schema 不参与选中卡片映射，仅原样留存，不升级或解释被遮蔽的 V1 数据。

同关键字多个不同 payload 是 ambiguous_character_card_chunks；不选 first/last。字节完全相同的重复块可导入并 warning，原容器保留所有块。损坏 ccv3 不回退到 chara。缺少卡片块、ccv3 中错误 identity、未知 critical chunk 等是错误。

## 5. 资产与不可信内容

V3 描述符验证 type/uri/name/ext 字符串、基础 extension 形状及多 icon/background 的 main 约束。缺少 assets 时使用规范定义的 icon/main/ccdefault/png 描述符；显式空数组保持为空。所有资产均 reference-only，并 warning；未知 type/URI 另加兼容警告，不销毁源数据。

PNG/APNG icon 的 ccdefault 使用 `raw-import:<RawImportId>#container-image`，指向原容器；user_icon 不使用这一关联。其他描述符使用 raw descriptor pointer；data URL 在 canonical asset metadata 中仅保存 pointer，完整原值留在 raw envelope。不推断 URL 对应文件的真实 MIME，不读取路径/URL、不解码 data URL、不运行 JS/代码资产。chara-ext-asset_: 块只记录 namespace/offset/size，不创建文件。

system_prompt、creator_notes、description、scenario、模板及扩展中的指令均是**不可信作者数据**。解析没有网络、shell、LLM、文件资源读取、prompt insertion、runtime command 或知识权限。来源与 assets 均不能开启上述能力；不会把卡片描述断言为 WorldTruth，也不自动授予任何角色或玩家知识。导入器不写日志，错误只含稳定 code 与结构路径，不含源文本。

## 6. 资源限制、审阅、持久化与验证

默认本地资源策略：原输入最多 32 MiB、单卡片 JSON 最多 4 MiB、JSON nesting 64、PNG chunks 10,000。CharacterCardLimits 可配置；限制是 parser 防护，不是冻结产品大小承诺。超限明确失败，不截断数据。

ImportDraft/ImportPreview 从已冻结 Draft 的 livingworld.import 读取 warning；该自有元数据参与 preview_hash。Commit 复用 ContentService 和独立 content repository，未新增 migration/表/依赖。每次独立导入产生新的 typed UUID；相同 hash 不覆盖既有定义。冲突时 content、raw、assets 全部回滚。

受控手写 [fixtures](../../tests/fixtures/character_cards/README.md) 与 [兼容/安全/重启测试](../../tests/application/test_character_card_import.py) 覆盖所有容器、映射、来源/未知数据、blank tags、损坏/重复、双 chunk 优先级、离线资产、注入字符串、preview hash、原子回滚、重启及完整 runtime snapshot 不变。[架构测试](../../tests/core/test_architecture.py) 禁止 importer 引入 Kernel、网络/shell、LLM/Tauri/browser 能力；既有 Stage 2 和 C-004A 测试继续保留。

下一任务 C-004C 的 Lorebook 语义规范化未开始；Builder、资产布局、导出、运行实例化与产品级重复导入体验仍未实现。
