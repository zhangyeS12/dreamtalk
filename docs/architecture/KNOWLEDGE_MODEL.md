# 知识模型

状态：保留 Stage 0 语义；C-003A/B 建立领域与独立存储，C-003D 实现绑定主体的 SQL 隔离读取、内部 AssertWorldTruth/AcquireKnowledge 命令与独立 ObservationId；C-006B 复用 event-target Observation 记录事件发生时的感知访问。未实现自动传播、推理、Memory 或语义检索。访问与事务细节见 [KNOWLEDGE_ACCESS_MODEL.md](KNOWLEDGE_ACCESS_MODEL.md) 与 [SCENES_AND_PERCEPTION.md](SCENES_AND_PERCEPTION.md)。依据 [PRODUCT_SPEC.md](../product/PRODUCT_SPEC.md) 的 FR-03、FR-04、FR-05、FR-07、FR-17 至 FR-20、FR-22、FR-23，以及已接受的 [Architecture Review 001](ARCHITECTURE_REVIEW_001.md)。

## 1. 三种不同的语义

| 概念 | 含义 | 不能等同于 |
| --- | --- | --- |
| WorldTruth | 世界中真实成立的事实，是“发生了什么、什么为真”的依据 | 所有参与者已经知道的内容 |
| CharacterBelief / Character Knowledge | 归属于某个角色的认知，可以错误或不确定 | 世界的全知视角、其他角色的知识或玩家知识 |
| Player Knowledge | 产品中归属于玩家已知范围的内容 | 后台全部事实、用户在产品外知道的全部信息 |

Knowledge 是知识内容的概念；KnowledgeOwnership 描述知识归属于谁。角色与玩家可以知道同一件事，但一方知道并不自动证明另一方也知道。C-003A 已明确允许 CharacterBelief 与 WorldTruth 冲突，不自动纠正；传闻、不确定认知的获得与纠正政策仍待确认。不能用“某角色相信它”为依据改写 WorldTruth。

## C-003A 领域定义

实现见 [knowledge.py](../../services/core/src/livingworld/domain/knowledge.py)，共享时间与身份见 [DOMAIN_MODEL.md](DOMAIN_MODEL.md)。

### KnowledgeAssertion 与归属

| scope | owner 不变量 |
| --- | --- |
| `truth` | 必须为 None，世界事实没有 Character / Player owner |
| `character_belief` | 必须是一个 CharacterId，不能为 PlayerId、None 或主体集合 |
| `player_knowledge` | 必须是一个 PlayerId，不能为 CharacterId、None 或主体集合 |

断言包含独立 `KnowledgeAssertionId`、`world_id`、scope、owner、subject、predicate、结构化 value、epistemic_status、confidence、valid_from/to、provenance_event_id、source_assertion_id 和 Revision。自身身份、owner、来源事件和来源断言的世界归属必须一致。

subject / predicate 是必填非空语义标签；value 接收有限 JSON 数据并防御性复制、递归冻结，不是自由文本 Memory 列表。epistemic_status 是必填非空扩展标签，不冻结推理状态机。confidence 是有限 Decimal 的 [0, 1] 或 None，不把置信度当作事实权威，也不比较不同主体的值来自动纠正信念。

**时间表示歧义已解决：** `valid_from: WorldTime`、`valid_to: WorldTime | None`，均属于世界时间线，不是 UTC。拒绝 `valid_to < valid_from`；None 表示未指定终点。不实现有效期查询，亦不冻结终点是否包含。不同分支在同一 WorldTime 可有不同认知；C-003A 不实现分支继承。

### Observation

Observation 定义不可变 typed `observation_id: ObservationId`、`world_id`、`principal_id: CharacterId | PlayerId`、`target_id: EventId | KnowledgeAssertionId`、channel、`observed_at: WorldTime`。可选 `created_at` 仅用于系统审计，必须是 aware datetime 并归一化 UTC，拒绝 naive。

channel 必须为 ObservationChannel 的 `witnessed / told / message / news / document / inferred` 之一；不接受未知渠道或未解析的原始字符串。主体与目标必须在同一世界。该对象记录一个显式观察，不自动授予检索权限、不传播/复制断言，也不因 inactive 玩家仍在某地点而创建见证记录。

Observation 身份歧义已解决：自身 ID、主体、目标须同世界；相同 receiver/source/channel/observed_at 可以对应不同 observation_id，坐标不再是 UNIQUE 身份。RequestId 仅保护命令重试，成功重试返回已提交的原 ObservationId。新执行随机生成 UUIDv4；旧行仅在迁移时由原坐标规范序列化后 UUIDv5 回填：**legacy backfill identity != runtime identity generation**。

C-006B 明确使用 `target_id=EventId`、`channel=witnessed`、`basis=event_occurrence` 表示主体在 WorldEvent 发生时具备感知访问。可空 basis 只标记 Kernel occurrence audience；basis=None 的既有/普通 Observation 继续允许相同语义坐标的独立 occurrence。它只记录 event-time access/provenance，不复制事件 payload，不自动生成 KnowledgeAssertion 或 Memory。无观察者的 WorldEvent 合法；未入 audience 的主体没有 Observation，不能用“所有人可读事件再由 Prompt 保密”代替该授权边界。已经提交的 event-target Observation 不随当前 Presence/Scene 重算。

权限过滤必须先于 semantic retrieval / prompt assembly；C-003D 在 SQL 中执行世界/scope/owner 条件。错误所有权抛出 InvalidKnowledgeOwnershipError，跨世界引用抛出 CrossWorldReferenceError。

### C-003B 存储约束

详见 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)。KnowledgeAssertionRecord 以 CHECK 强制上述 scope/owner 组合，复合外键保证 owner、来源事件和来源断言存在于同一 world；valid_from/to 保存整数 WorldTime，拒绝倒序。confidence 使用精确 Decimal 文本，value 以 JSON 保存并在返回领域时冻结；不同主体可保留相互冲突的认知。

ObservationRecord 使用具体 principal/target 类型分支及同世界 FK，channel 限制为已定义枚举，observed_at 保存 WorldTime，可选 created_at 保留 aware UTC 语义。0004 改为 (world_id, observation_id) 主键，保留旧语义字段、所有行和 FK/CHECK，取消坐标唯一性。0012 增加可空 basis，只对 `event_occurrence` event-target rows 增加每 event/principal 唯一，并增加主体历史索引；basis=None 及 assertion-target occurrence 仍可独立存在。单独保存 Observation 不授予知识；AcquireKnowledge 原子建立接收方自有断言。数据库 ownership CHECK 与 SQL 读取授权共同保持边界。

### C-003D 显式获知与读取

**EXISTENCE IN DATABASE != KNOWLEDGE OF A PRINCIPAL**。

WorldTruthReader 仅返回绑定世界的 truth；CharacterKnowledgeReader 仅返回绑定角色自有 character_belief；PlayerKnowledgeReader 仅返回绑定玩家自有 player_knowledge。list/get 均在 SQL 加世界、scope 和 owner 条件，不先读全集再过滤。知道来源 ID 不授予访问源断言、源主体其他断言或同 subject 断言的权限。

可信内部 AssertWorldTruth 建立无 owner 的 truth。可信内部 AcquireKnowledge 读取一个同世界源断言，通过显式渠道创建 Observation 与新的角色信念/玩家知识；源可为 truth、CharacterBelief 或 PlayerKnowledge。subject/predicate/value 保留，身份、owner/scope、认知元数据与获知 provenance 独立，来源指针保留。事件、投影、回执同事务；玩家/角色没有自行授予知识的 HTTP API。

最小政策：witnessed 默认 epistemic_status=observed，其他显式渠道默认 reported；允许调用方显式提供非空标签。confidence 默认 None，允许明确有限 Decimal [0,1]，不从来源继承或自动算概率，不把 observed/reported 当作真相权威。派生有效期从本次 WorldClock.logical_time 开始、终点未指定；来源的有效期不自动复制，也不据此实现有效期搜索。inferred 仍可表示领域观察，当前获知命令明确拒绝，推理政策留待后续。

未来顺序必须是：**principal authorization → eligible assertion set → semantic/FTS/vector retrieval → ranking → context**。当前仅实现隔离读取；不实现搜索或上下文组装。未来 Director 可获内部 TruthReader，不因此读取私有信念；未来 Character Agent 只能接收其绑定 reader 的已授权结果，不能拿全局断言加“不要泄密”的 Prompt。

## 2. 已冻结的边界

### C-003E2：独立 CharacterBelief 形成歧义已解决

FormCharacterBelief 是可信内部 application command，复用 KnowledgeAssertion，scope=character_belief，owner 恰为一个现存同世界 Character；没有 Player owner、WorldTruth 写入或自动 Observation。完整 proposition / epistemic metadata / validity / 可选 source/provenance 经 fingerprint、canonical CharacterBeliefFormed、投影、receipt 同事务提交。

信念不要求匹配 Truth，甚至可无对应 Truth 或 source。提供 source/provenance 时只要求既有同世界合法引用并原样保存，不继承源主体私有知识读取权限，也不要求源 proposition 等于当前信念。未提供时保存 None，不生成伪观察或 provenance。新 immutable 断言无 expected revision。

AcquireKnowledge 不变：既有源 → 显式渠道 Observation → 接收方派生 assertion，复制 source proposition。false belief 因而可被转述，但不会变成 Truth。Stage 2 的矛盾验收使用 AssertWorldTruth `door=locked` 与 FormCharacterBelief `Alice: door=unlocked`，重建前后各 reader 返回自身 scope/owner 的命题，不覆盖或自动调和。历史 stale Truth 不是这一路径的替代。

仅明确 canonical 主观入口；自动 inference、误导检测、belief revision/reconciliation、Observation→Belief 推断和后续产品呈现均未实现。测试和完整验收见 [STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)。

1. 世界真实事实、Character Knowledge 和 Player Knowledge 分离（FR-04）。
2. 后台发生但玩家不知道的事件不能直接展示给玩家（FR-05）。
3. Character Agent 主要负责自己拥有的记忆、人格表达和与玩家对话（FR-03）；不能仅因 Director 知道某事实，就把该事实视作角色已知内容。
4. 关系后台存在，但不能向普通玩家展示数值（FR-07）。知道一段关系或一次关系变化，不等于获得查看关系数值的权限。

## 3. 获知与展示的概念流程

1. 世界事实存在，或者候选事件被激活成为 WorldEvent。
2. 确定某参与者是否有获知依据；亲历、被告知等是需要细化的获知情境。
3. 按拥有者区分获得的 Knowledge，避免自动广播给所有角色与玩家。
4. 对面向玩家的呈现，依据 Player Knowledge 检查是否可以直接展示该事实。

“看见”“听说”“收到但未阅读消息”各在何时计入玩家已知，以及是否表达来源和不确定性，仍待产品确认。这里不预先选择判定算法。角色通过对话告知玩家可以是获知情境，但不能以此跳过角色自身的知识边界。

### 例子：后台相遇

角色甲与乙在广场相遇。若相关候选事件尚未激活，这只是计划；激活后，相遇成为世界事实。甲、乙的获知范围应依据参与情境确定，未在场且尚未获知此事的玩家不能直接收到一段把相遇当作已知事实展示的后台剧情。未来若玩家通过合适情境获知，再处理 Player Knowledge 的变化。

## 4. 与其他模型的关系

- **事件**：[EVENT_MODEL.md](EVENT_MODEL.md) 决定候选何时变成真实发生的事件；知识模型处理谁知道，不负责把候选变成事实。
- **记忆**：[MEMORY_MODEL.md](MEMORY_MODEL.md) 处理拥有者如何保留与理解经历。知识与记忆相关，但并非每条知识都已确定要对应一条独立记忆。
- **Director / Agent**：Director 的世界调度上下文与 Character Agent 的对话上下文具有不同职责；本文不规定其进程、接口或存储隔离方式。
- **Builder / 导入**：角色或作品的外部研究来源不自动等于运行世界中的事实，更不自动等于每个角色或玩家已知。自动生成内容仍须 Draft → Preview → Commit；提交时的初始知识归属与导入映射待确认。
- **Checkpoint / Timeline**：知识所属的时间线和恢复范围需要明确；不能在尚未确认继承规则时，假设另一条分支的知识已在当前分支成立。
- **Developer Mode**：FR-23 要求决策 Trace；开发者查看能力如何与玩家身份和剧情信息隔离仍待确认，不能据此放宽普通玩家的展示限制。

## 5. 待确认事项

| 问题 | 需要明确的边界 |
| --- | --- |
| 玩家何时算“知道” | 在场、收到、阅读、转述等情境如何处理 |
| 传闻、谎言和误认 | 错误 CharacterBelief 已允许；获得、转述、来源及呈现政策仍待明确 |
| 知识修正与遗忘 | 新证据、错误消息、记忆变化是否及如何影响已知内容 |
| 初始知识 | World / Character Draft 与导入内容如何分配给各拥有者 |
| 跨分支知识 | Checkpoint 恢复、Timeline Branch 和玩家产品外记忆的边界 |
| 开发者权限 | Trace 可见范围是否会影响玩家视角与后续体验 |

本任务不为以上问题作默认产品决定。
