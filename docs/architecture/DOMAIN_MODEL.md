# LivingWorld 领域概念模型

状态：Stage 0 领域语言保留；Stage 2 已建立领域模型、SQLite 映射、命令事务、知识隔离、canonical ledger、回放及资源级乐观并发。C-003E2 按用户确认增加内部 CharacterBelief 形成路径，复用已有 KnowledgeAssertion；Stage 3 C-004A 新增独立创作内容模型及导入边界。见 [COMMAND_MODEL.md](COMMAND_MODEL.md)、[PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)、[STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md) 和 [CONTENT_MODEL.md](CONTENT_MODEL.md)。其余概念仍是定义；Director、Agent、业务 HTTP API 与世界模拟未实现。

## C-004A 内容与运行状态边界

**Imported Content != Runtime State；CharacterDefinition != Character；WorldContent != World；LoreEntry != WorldTruth。**

Stage 3 新增独立创作模型，不合并或扩展现有运行实体：CharacterDefinition 保存 persona/background/authored instructions；WorldContent 保存 setting/factions/authored locations/rules；LoreEntry 保存正文/trigger/opaque metadata。没有运行 world_id、位置、Memory、Knowledge、关系或 ledger position。prompt-like 导入文本仅为不可信创作数据。

CharacterDefinitionId / WorldContentId / LoreEntryId / ContentAssetId / RawImportId 是独立 typed UUID，不携带运行世界作用域；ContentRevision 表达内容编辑，与 runtime Revision 分离。冻结快照通过新版本支持编辑，未实现完整历史。保存内容不实例化角色、世界或任何知识，不绕过 Stage 2 command/event/projection/receipt。

详细 Purpose / Owns / Does not own / Relationships / Important invariants 见 [CONTENT_MODEL.md](CONTENT_MODEL.md)，Draft/Preview/raw preservation 边界见 [IMPORT_MODEL.md](IMPORT_MODEL.md)。运行实例与定义版本的绑定及初始知识分配仍为后续范围。

## C-003E2 已确认的边界

Stage 2 已建立 canonical ledger、内部回放及资源级乐观并发；Director、Agent、业务 HTTP API 与世界模拟仍未实现。验收见 [STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)。

- mutable projection 各自由 Revision 保护，Presence / CharacterState / 有向 Relationship 独立，无全局 World revision；期待不存在用 None，不等同 Revision(0)。CAS 在基础设施实现，领域继续不知道 SQLAlchemy 或数据库。
- 现有 ConcurrencyConflictError 增加可选内部 resource kind、typed identity、expected/actual Revision 信息；Revision.advance 的既有调用仍有效。
- CharacterBelief 的 canonical 形成入口明确为内部 FormCharacterBelief：新 immutable KnowledgeAssertion、单一 Character owner、optional source/provenance，可无 Truth 或与 Truth 矛盾；没有 expected revision 或自动 Observation。完整语义事件可恢复原身份与所有 metadata。
- AcquireKnowledge 继续按 exposure channel 复制源 proposition，source/provenance 不授予读取源 owner 私有存储的权限。没有推理、自动校正、belief revision、Memory 或智能层。

## 阅读约定

- 本文包含 28 个领域对象。`Owns` 表示概念上负责的内容，不表示数据库字段、存储位置、服务边界或程序类。
- `Important invariants` 中引用的 FR 编号对应 [PRODUCT_SPEC.md](../product/PRODUCT_SPEC.md) 的 24 条冻结产品规则。
- 已冻结规则保持明确约束；尚未冻结的具体语义以“待确认”标出，不在本文中替产品作决定。
- Director 与 Character Agent 是职责角色：Director 改变世界、调度活动；Character Agent 负责自己拥有的记忆、人格表达及与玩家对话。Director 不能直接替 Character Agent 编写最终对玩家台词。
- Event Reservoir 指 World Plan 所关联的候选事件集合及其待执行上下文；在本阶段作为关联概念说明，不新增实现对象。

## C-003A 实现基线

### 双时间决策：已解决

用户已确认严格分离世界逻辑时间与现实时间，时间表示的歧义已解决：

- [`WorldTime`](../../services/core/src/livingworld/domain/values.py) 是独立不可变值对象，用 Python 整数表示相对所属世界逻辑纪元的微秒位置，拒绝浮点、布尔值、字符串和 `datetime`。坐标可位于纪元之前；不选择数据库整数范围。
- `WorldTime` 只表示世界内的时间位置，不是 UTC，不包含世界/分支/事件身份，不隐式转换现实时间。不同分支可以在相同 `WorldTime` 拥有不同历史；事件身份仍由独立 `EventId` 表示。
- 所有现实系统时间字段必须接收 timezone-aware `datetime` 并归一化到 UTC；naive `datetime` 一律拒绝。世界时间与现实时间字段不能互换，也不跨时间轴比较大小。
- `WorldClock` 定义 `logical_time: WorldTime`、`observed_wall_time_utc: datetime`、精确十进制 `time_scale`、`running/paused` 状态和 `Revision`。比例只校验有限且非负，不推导推进、暂停或离线行为。
- `WorldEvent.occurred_at`、知识有效期和 `Observation.observed_at` 使用 `WorldTime`；事件创建时间、可选观察审计时间、命令回执创建/完成时间使用 UTC-aware `datetime`。
- 本任务只定义类型和时钟快照，不实现推进、catch-up、日历、WorldDate、虚构月份、调度或 `Day 17 · 20:43` 转换。P-01 的现实/世界时间映射与离线推进政策仍需后续定义；时间表示的选择已经解决。

### 代码范围与职责

领域代码位于 `services/core/src/livingworld/domain/`，只依赖 Python 标准库与本领域包；沿用现有 frozen dataclass 风格。模型为不可变快照，可变概念通过独立版本和新快照表达。

| 模块 | 已实现模型 / 值 | 当前职责 |
| --- | --- | --- |
| [identifiers.py](../../services/core/src/livingworld/domain/identifiers.py) | WorldId、LocationId、PlayerId、CharacterId、EventId、KnowledgeAssertionId、ObservationId、CorrelationId、PrincipalId | UUID 的具体类型；地点/参与者/事件/断言/观察引用携带 WorldId；PrincipalId 为 CharacterId 或 PlayerId |
| [values.py](../../services/core/src/livingworld/domain/values.py) | WorldTime、Revision、不可变 JSON 值、UTC 校验 | 两条时间轴、版本检查、嵌套结构的防御性复制 |
| [world.py](../../services/core/src/livingworld/domain/world.py) | World、WorldClock、Location、LocationConnection | 世界身份、双时间时钟快照、地点及有序拓扑连接；不定义移动耗时或通行策略 |
| [participants.py](../../services/core/src/livingworld/domain/participants.py) | Player、PlayerPresence、Character、CharacterState | 静态定义和运行状态分离；玩家单一位置、activity 与 Busy/Available 独立 |
| [relationships.py](../../services/core/src/livingworld/domain/relationships.py) | Relationship、RelationshipMetrics | 同世界主体的有向关系及版本；C-003C 三项内部整数指标，无普通玩家数值接口 |
| [events.py](../../services/core/src/livingworld/domain/events.py) | WorldEvent | 独立事件身份、双时间、版本化不可变 payload 和因果/关联/幂等元数据 |
| [knowledge.py](../../services/core/src/livingworld/domain/knowledge.py) | KnowledgeAssertion、Observation | scope/owner 约束、结构化断言、世界有效期、来源和显式观察渠道 |
| [commands.py](../../services/core/src/livingworld/domain/commands.py) | CommandReceipt | 复用 [contracts.py](../../services/core/src/livingworld/domain/contracts.py) 的 RequestId，定义未来回执元数据；不执行命令或去重 |
| [errors.py](../../services/core/src/livingworld/domain/errors.py) | DomainInvariantError、CrossWorldReferenceError、InvalidKnowledgeOwnershipError、InvalidPresenceError、ConcurrencyConflictError | 对本任务不变量失败提供明确错误 |

### 已验证的不变量与边界

- 每个世界对象显式关联一个 `WorldId`，自身 ID 及所有世界内引用必须属于该世界。原始 UUID 不能替代具体身份类型；跨世界的地点、主体、因果事件、知识来源、观察目标和回执结果均拒绝。
- `PlayerPresence` 必须持有一个 `LocationId`，拒绝 null、错误身份和多位置集合。inactive 保留物理位置，不自动赋予见证资格；activity 与 Busy/Available 独立。一个快照没有容纳第二物理位置的字段。
- `Character` 仅定义身份/名称，`CharacterState` 独立持有位置和版本；没有目标、日程、记忆或情绪系统。
- `Relationship(source_id, target_id)` 有方向，A→B 与 B→A 独立；允许 Player / Character 主体。C-003C 已确认仅增加内部 affinity、trust、familiarity，不新增群体关系政策。
- 未来可修改的世界/定义/状态/关系/断言/回执带 `Revision`。`Revision.advance(expected)` 只在版本匹配时返回 +1；presence 更新返回重新校验的新快照，失败不改变旧值。不实现数据库并发控制。
- 事件和结构化值防御性复制并深度冻结；事件没有 update/delete 操作。知识 scope/owner 的组合必须合法，错误信念允许与真相冲突。
- ID 校验保证引用类型及世界归属，不查询目标是否已创建，也不维护世界实体注册表。C-003B 通过复合外键与主键加固引用存在性、同世界归属和当前快照唯一性；分支归属与 Kernel 授权仍待后续实现。
- `epistemic_status` 与回执 `status` 为必填非空语义标签，只定义扩展接口，不冻结状态机。`confidence` 为有限 Decimal 的 [0, 1] 或 None；知识有效期只拒绝倒序，不定义查询端点的包含性或自动失效。

### C-003D Observation 身份决策：已解决

ObservationId 是不可变的同世界 typed UUID，沿用现有 world_id + value 的标识符约定，不把 world_id 编码进 UUID。Observation 必须持有自身 observation_id；principal_id、target_id、channel、observed_at 描述发生了什么，不决定 occurrence 身份。两个独立观察可以拥有完全相同的语义坐标但不同 ObservationId。

RequestId 是命令幂等身份，ObservationId 是观察发生身份；运行时新获知执行生成独立 UUIDv4，既不 hash RequestId，也不 hash 坐标。成功提交后重试由回执返回原 ObservationId；完全回滚的身份从未成为 canonical state，后续合法重试可以生成新身份。旧自然键仅用于 0004 的确定性迁移回填，**legacy backfill identity != runtime identity generation**。迁移与查询边界见 [持久化模型](PERSISTENCE_MODEL.md) 和 [知识访问模型](KNOWLEDGE_ACCESS_MODEL.md)。

测试见 [tests/domain](../../tests/domain/)；领域依赖约束由 [架构测试](../../tests/core/test_architecture.py) 验证。详细事件和知识定义见下方相关文档。

## 1. World

### Purpose

承载一个持久化、事件驱动的多角色 AI 世界的整体语境。

### Owns

世界的整体设定、身份和领域范围，以及时间、地点、参与者、事实与历史之间的整体关联。

### Does not own

不代替角色的人格表达，不把全部世界事实自动公开给玩家，也不等同于一次聊天会话。

### Relationships

关联 WorldClock、WorldState、Location、Player、Character、WorldTruth 和 Timeline；由 Director 在既定规则下调度变化。

### Important invariants

- LivingWorld 是持久化、事件驱动的多角色 AI 世界，不是普通聊天机器人（FR-01）。
- 世界真实事实、Character Knowledge 和 Player Knowledge 必须分离（FR-04）。
- AI World Builder 可联网研究作品/世界并生成带来源的 World Draft；自动生成内容必须经过 Draft → Preview → Commit（FR-18、FR-19）。
- 世界支持 Checkpoint 与 Timeline Branch（FR-22）；一个 World 对应多少玩家以及是否支持多人共同参与，待确认。

## 2. WorldClock

### Purpose

提供描述世界时间与事件先后关系的概念基准。

### Owns

世界时间的含义，以及活动、事件和规划相对于世界时间的位置。

### Does not own

不决定角色最终台词，不把现实时间自动等同于世界时间，不自行决定世界暂停或离线推进策略。

### Relationships

为 WorldState、CharacterState、WorldEvent、PlanningWindow 和 Timeline 提供时间语境；时间调度由 Director 负责。

### Important invariants

- Director 负责时间调度（FR-02）。
- 世界逻辑时间采用 WorldTime，现实观察时间采用 UTC-aware datetime；时间表示已确认。映射、推进粒度、离线推进及暂停政策仍待确认，C-003A 不实现推进。
- Checkpoint 与 Timeline Branch 如何影响时钟，以及分支之间如何比较时间，待确认（FR-22）。

## 3. WorldState

### Purpose

描述在指定世界与时间线语境下，世界当前处于什么状态。

### Owns

当前世界状况的整体描述，以及地点、角色活动、玩家所在位置等状态之间的一致性语境。

### Does not own

不替代完整事件历史，不包含尚未发生的候选事件结果，不等同于玩家可见的世界摘要。

### Relationships

关联 World、WorldClock、Location、Player、CharacterState、WorldTruth、WorldEvent 和 Timeline。

### Important invariants

- CandidateEvent 中的计划结果不能提前当作当前世界事实（FR-13、FR-14）。
- 玩家任意时刻只能存在于一个物理地点（FR-06）。
- 状态可在后台变化，但玩家不知道的后台事件不能因此直接展示给玩家（FR-05）。

## 4. Location

### Purpose

表示世界中的物理地点，为角色活动、相遇和玩家存在提供空间语境。

### Owns

地点的概念身份及其与世界空间的关联；空间层级和连通方式的具体表达待确认。

### Does not own

不把远程对话、消息频道或界面页面等同于玩家的物理位置，也不独立决定角色对地点的知情程度。

### Relationships

属于 World 的空间语境；关联 Player、CharacterState、Scene、WorldEvent 和 CandidateEvent 的地点约束。

### Important invariants

- 玩家任意时刻只能存在于一个物理地点（FR-06）。
- Director 负责地点及相关活动、相遇调度（FR-02）。
- 地点层级、移动耗时、可达性与在途状态的产品语义待确认；不得借此允许玩家同时位于多个物理地点。

## 5. Scene

### Purpose

为一段有共同情境的活动或互动提供叙事语境；其精确开始、结束与划分标准待确认。

### Owns

场景层面的情境描述及参与者、地点、活动之间的关联。

### Does not own

不替代 Location，不自动决定世界事实或知识归属，也不承担角色最终台词生成职责。

### Relationships

关联 Location、Player、Character、WorldEvent、Conversation；可与 Mission 或 OutreachEpisode 发生联系，具体对应关系待确认。

### Important invariants

- 场景划分不能绕过玩家单一物理地点约束（FR-06）。
- 出现在场景描述中的后台内容仍受玩家知识边界约束（FR-04、FR-05）。
- 一个 Scene 是否跨地点、跨时间，以及 Scene 与 Conversation 的边界，待确认。

## 6. Player

### Purpose

表示玩家在世界中的参与身份，是玩家知识、物理位置和可联系状态的归属主体。

### Owns

玩家参与行为、所在物理地点、Busy / Available 状态，以及 Player Knowledge 的主体归属。

### Does not own

不天然拥有世界全部真实事实或角色私有知识，不直接取得后台关系数值。

### Relationships

参与 World、Scene、Conversation、Mission 和 OutreachEpisode；通过 KnowledgeOwnership 关联 Knowledge，并与 Character 形成 Relationship。

### Important invariants

- 任意时刻只能存在于一个物理地点（FR-06）。
- C-003C 用户确认：成功创建普通 Player 必须同时创建有初始地点的 PlayerPresence；世界/地点存在且同世界，整个命令原子提交。复用 activity/availability 枚举，默认 active/available；玩家创建歧义已解决，静态定义与状态仍分离。
- 具有 Busy / Available 状态；Busy 时 Director 不得发起非必要主动联系，Available 时可以安排一个角色或一组角色主动联系（FR-08、FR-09、FR-10）。
- 普通玩家不能查看关系数值，也不能直接看到其不知道的后台事件（FR-05、FR-07）。
- 状态由谁设置、状态切换何时生效，以及“必要联系”的边界，待确认。

## 7. Character

### Purpose

表示具有角色身份与人格表达的世界参与者，是 Character Agent 所服务的领域主体。

### Owns

角色身份与人格语境，以及自身 Knowledge、Memory、CharacterState 和关系的概念归属。

### Does not own

不承担 Director 的全局时间、地点、世界事件与宏观剧情调度职责，不天然知道世界所有事实。

### Relationships

关联 CharacterState、KnowledgeOwnership、Memory、Relationship、Conversation、Message 和 OutreachEpisode；参与 World 与 Scene。

### Important invariants

- Character Agent 主要负责自己拥有的记忆、人格表达和与玩家对话（FR-03）。
- Director 可以改变世界与调度角色活动，但不能直接替 Character Agent 编写最终对玩家台词（FR-02、FR-03）。
- AI Character Builder 可联网研究角色并生成带来源的角色 Draft；自动生成内容必须经过 Draft → Preview → Commit（FR-17、FR-19）。
- 支持导入格式是冻结产品要求；具体导入信息如何映射到角色概念，待确认（FR-20）。

## 8. CharacterState

### Purpose

描述一个角色在当前世界与时间线语境下的状态，以区分角色身份与随事件变化的状况。

### Owns

角色当前活动、所在情境及与世界变化有关的状态描述；具体状态维度待确认。

### Does not own

不替代角色身份、完整记忆、知识归属或最终对玩家台词，也不承担全世界状态的职责。

### Relationships

属于 Character 的状态语境；关联 WorldState、WorldClock、Location、Scene、WorldEvent 和 RelationshipEvent。

### Important invariants

- Director 负责角色活动、角色相遇和关系变化调度（FR-02）。
- 尚未激活的 CandidateEvent 不能被当作已经发生的角色状态变化（FR-14）。
- 后台角色状态变化不会自动成为 Player Knowledge（FR-04、FR-05）。

## 9. WorldTruth

### Purpose

表示世界中实际成立的真实事实，作为区别“发生了什么”与“谁知道什么”的基准。

### Owns

世界真实事实的概念边界，包括既有世界设定中成立的事实和实际发生事件所形成的事实。

### Does not own

不表示角色或玩家必然知情，不收纳未激活候选事件的预期结果，也不把角色说法自动视为真相。

### Relationships

关联 World、WorldState、WorldEvent 和 Timeline；Knowledge 表达主体的知情内容，KnowledgeOwnership 表达知情归属。

### Important invariants

- WorldTruth、Character Knowledge 与 Player Knowledge 分离（FR-04）。
- 候选事件只有被激活后才成为真正的世界事实（FR-14）。
- 后台事件即使已成为真实事实，玩家不知道时也不能直接展示给玩家（FR-05）。
- 初始设定中的矛盾、后续事实纠正与多来源冲突的裁定方式，待确认。

## 10. Knowledge

### Purpose

表达某个主体所知道的内容，使角色知识与玩家知识可以独立于世界真实事实存在。

### Owns

知情内容的概念表达，以及该内容与被获知事实、事件或信息来源的关联。

### Does not own

不裁定世界真实事实，不默认向所有主体共享，不替代主体经历及人格化记忆。

### Relationships

通过 KnowledgeOwnership 关联 Player 或 Character；可关联 WorldTruth、WorldEvent、Conversation、Message 和 Memory。

### Important invariants

- Character Knowledge、Player Knowledge 与世界真实事实必须分离（FR-04）。
- 某角色知道某事，不意味着玩家或另一角色也知道（FR-04、FR-05）。
- C-003A 以 CharacterBelief 表达角色信念，允许与 WorldTruth 冲突且不自动纠正。传闻/推测的具体获得与纠正机制仍待确认，不能取消知识隔离。

## 11. KnowledgeOwnership

### Purpose

表达“谁拥有哪份知识”的归属关系，防止跨主体知情状态混用。

### Owns

Knowledge 与其知情主体之间的归属边界，以及判断某内容是否属于该主体知识的概念责任。

### Does not own

不定义数据库权限机制，不代替知识内容或世界真相，不因后台系统可以读取信息而授予玩家知情。

### Relationships

连接 Knowledge 与 Player、Character；为 Memory 使用和 Message 内容边界提供知情语境。

### Important invariants

- 必须区分角色知识归属与玩家知识归属（FR-04）。
- 共享一段 Conversation 或 Scene 不等于自动获得其中所有后台信息（FR-05）。
- C-003D 以可信内部 AcquireKnowledge 显式建立一个主体自有断言；来源与 provenance 不授予源存储读取权限。观察、转述、阅读的自动触发时机与群组共享知识仍待确认。

## 12. Memory

### Purpose

表示角色所拥有的记忆，为经历的延续、人格表达和对话提供背景。

### Owns

角色记忆内容及其与角色经历、互动、知识和关系变化的关联。

### Does not own

不成为世界事实的权威替代，不提供读取其他角色私有知识的通道，也不把尚未发生的计划结果当作经历。

### Relationships

归属于 Character；关联 Knowledge、WorldEvent、RelationshipEvent、Conversation、Message、Checkpoint 和 Timeline。

### Important invariants

- Character Agent 主要负责自己拥有的记忆（FR-03）。
- 记忆使用必须保持世界事实、Character Knowledge 与 Player Knowledge 分离（FR-04、FR-05）。
- Memory 决策应纳入 Developer Mode 可查看的 Trace 范围（FR-23）。
- 记忆分类、遗忘、压缩、修正及 Checkpoint / Branch 的记忆继承边界，待确认。

## 13. Relationship

### Purpose

表示参与者之间在后台持续存在的关系状况。

### Owns

关系的有向身份、参与方、版本及不可变 RelationshipMetrics。C-003C 用户确认 affinity（态度）、trust（信任）为 [-100,100] 的整数，familiarity（熟悉程度）为 [0,100] 的整数；关系状态表示歧义已解决，不增加其他维度。

### Does not own

不直接向普通玩家输出后台关系数值，不替代某次关系变化的事件记录，也不决定角色最终台词。

### Relationships

关联 Player、Character、RelationshipEvent、Memory、WorldEvent 和 Director 的关系变化调度。

### Important invariants

- 关系后台存在，但不能向普通玩家展示数值（FR-07）。
- Director 负责关系变化调度（FR-02）。
- C-003A 已确认关系有方向，A→B 与 B→A 独立，不假定对称。群体关系与可感知的非数值反馈方式仍待确认。
- C-003C ChangeRelationship 至少一个整数 delta 非零；通过领域逻辑相加并校验结果，超范围明确拒绝，不 clamp。缺失边从三项 0、revision=0 开始，应用后保存 revision=1；不创建或改变反向边。
- 指标仅用于内部模拟，未来 Developer/debug 可查看，不能成为普通玩家的好感分数。

## 14. RelationshipEvent

### Purpose

表示已经发生的、涉及关系变化的事件，用于将关系当前状况与变化经过区分开来。

### Owns

关系变化这一事件的语义及其与参与者、原因和关系的关联。

### Does not own

不替代 Relationship 的整体状态，不预先兑现候选关系变化，不自动向玩家公开后台关系细节。

### Relationships

关联 Relationship、Player、Character、Memory 和 WorldEvent；与 WorldEvent 是分类关系还是关联关系，待确认。

### Important invariants

- Director 负责关系变化调度，关系数值不能展示给普通玩家（FR-02、FR-07）。
- 预期中的关系变化在相应候选事件被激活前不能成为真实事实（FR-14）。
- 后台关系事件同样受玩家知识边界约束（FR-04、FR-05）。

## 15. WorldEvent

### Purpose

表示世界中实际发生的事件，与尚待发生的规划候选明确区分。

### Owns

已发生事件的事实语义及其与世界时间、地点、参与者和后果的关联。

### Does not own

不表示未来承诺，不自动赋予玩家知情，不承担 Character Agent 的最终台词生成职责。

### Relationships

关联 WorldClock、Location、WorldTruth、WorldState、CharacterState、RelationshipEvent、Knowledge 和 Timeline；可源自 CandidateEvent 的激活。

### Important invariants

- `CandidateEvent != WorldEvent`；候选事件只有被激活后才成为真正的世界事实（FR-14）。
- 事件已经发生与玩家已经知道是两个不同判断（FR-04、FR-05）。
- 是否所有真实事件都必须先经过候选阶段，以及玩家即时行为如何形成事件，待确认。

## 16. CandidateEvent

### Purpose

表示规划中的候选事件，供后续依据条件决定是否实际发生。

### Owns

候选意图、预期情境与激活所需约束的概念描述，以及等待激活、延期或取消的候选语义。

### Does not own

不拥有已发生事实，不提前更改 WorldTruth、角色已发生经历或玩家知识，也不为每个普通小事件独立触发 LLM 调用。

### Relationships

由 WorldPlan 组织并置于 Event Reservoir；受 PlanningWindow 及世界状态约束；经激活形成实际的 WorldEvent。

### Important invariants

- `CandidateEvent != WorldEvent`。候选事件只有被激活后才成为真正的世界事实。
- Event Reservoir 中的候选事件由传统程序激活、延期或取消（FR-14）。
- 禁止为每个普通小事件单独调用 LLM（FR-13）。
- 延期与取消本身不意味着候选中的预期事件已经发生；激活冲突、过期判断及失败处理细节待确认。

## 17. WorldPlan

### Purpose

表示 Director 面向一段规划范围批量制定的世界活动与事件计划。

### Owns

规划目标、候选事件之间的安排及其所属 PlanningWindow；关联 Event Reservoir 中待执行的候选事件。

### Does not own

不把预期结果当作真实事实，不替代传统程序的候选激活、延期或取消职责，也不直接编写最终对玩家台词。

### Relationships

关联 PlanningWindow、CandidateEvent、WorldState、DirectorProfile、OutreachEpisode 和 LLMUsage；Event Reservoir 为候选执行提供集合语境。

### Important invariants

- Director 使用批量 World Plan + Event Reservoir，禁止为每个普通小事件单独调用 LLM（FR-13）。
- 候选事件由传统程序激活、延期或取消（FR-14）。
- Planning Window 耗尽或大量计划失效才触发 Replan（FR-15）。
- 自动生成内容必须经过 Draft → Preview → Commit（FR-19）；该流程与运行时 WorldPlan 的具体衔接待确认，不能自行假定豁免或审批粒度。

## 18. PlanningWindow

### Purpose

界定一个 WorldPlan 所覆盖的规划范围，并为判断是否需要 Replan 提供语境。

### Owns

规划窗口的覆盖含义，以及“耗尽”和计划失效判断所需的概念边界。

### Does not own

不代替 WorldClock，不自行创造普通事件级 LLM 调用，也不预设固定时间长度或失效阈值。

### Relationships

关联 WorldPlan、WorldClock、CandidateEvent、Event Reservoir 和 Director 的 Replan 决策。

### Important invariants

- Planning Window 耗尽或大量计划失效才触发 Replan（FR-15）。
- 不能把每个普通小事件都变成重新规划或单独调用 LLM 的理由（FR-13、FR-15）。
- 窗口以时间、事件数量或其他尺度定义，“耗尽”与“大量失效”的准确标准，待确认。

## 19. OutreachEpisode

### Purpose

表示围绕一个统一目的组织的多角色主动联系活动。

### Owns

本次主动联系的统一目的、参与角色的协同语境，以及主动联系理由的一致性约束。

### Does not own

不把多个无关目的包装成同一联系，不允许用更换角色来重复发送同一理由，也不替角色编写最终对玩家台词。

### Relationships

关联 Director、Player、Character、WorldPlan、Conversation 和 Message；是否让单角色主动联系也采用 OutreachEpisode，待确认。

### Important invariants

- 多角色主动联系必须围绕一个统一目的，形成 Outreach Episode（FR-12）。
- Busy 时 Director 不得发起非必要主动联系；Available 时可安排一个角色或一组角色主动联系（FR-09、FR-10）。
- 同一个主动联系理由最多主动发送一次；玩家未回复不能持续催促（FR-11）。
- 多角色协同如何对应“一次主动发送”、同一理由的判定范围、Episode 结束条件与必要联系例外，待确认；这些细节不能取消上述冻结约束。

## 20. Mission

### Purpose

暂作为组织某项目标或持续活动的领域概念占位；具体产品含义尚未冻结。

### Owns

待确认的目标语境及参与活动之间的概念关联；本阶段不规定任务类型、状态、奖励或完成规则。

### Does not own

不默认等同于游戏任务系统，不替代 Director 的宏观剧情调度，也不与 OutreachEpisode 的联系目的自动画等号。

### Relationships

可能关联 Player、Character、Scene、WorldEvent、WorldPlan、Conversation 和 OutreachEpisode；必要关系与对应方式待确认。

### Important invariants

- Mission 不能绕过世界事实与知识分离、玩家单一物理地点或主动联系规则（FR-04 至 FR-12）。
- Mission 是否由玩家主动接受、是否对玩家可见、如何创建及结束，均待确认。

## 21. Conversation

### Purpose

表示参与者之间持续交流的语境，用于组织相关 Message。

### Owns

对话参与关系及消息所属的交流上下文；会话划分与结束方式待确认。

### Does not own

不替代物理地点或整个世界，不保证参与者拥有相同知识，也不让 Director 取得角色最终台词职责。

### Relationships

关联 Player、Character、Message、Scene、Memory 和 Knowledge；可承接 OutreachEpisode 的交流。

### Important invariants

- Character Agent 主要负责与玩家对话，Director 不能直接替 Character Agent 编写最终对玩家台词（FR-02、FR-03）。
- 对话不得直接展示玩家不知道的后台事件（FR-05）。
- 参与远程或多人对话不能使玩家同时处于多个物理地点（FR-06）。
- 对话渠道、群体成员变化、Busy 对既有对话的影响及阅读何时形成 Player Knowledge，待确认。

## 22. Message

### Purpose

表示一段实际交流内容，使已表达内容与调度意图、世界事实区分开来。

### Owns

消息的表达内容、发言主体与所在交流语境的概念关联。

### Does not own

不将发言内容自动升级为 WorldTruth，不把 Director 的联系意图直接当作角色最终台词，也不定义传输协议或 UI 组件。

### Relationships

属于 Conversation 的交流语境；关联 Player、Character、Knowledge、Memory，并可关联 OutreachEpisode 的主动联系理由。

### Important invariants

- Director 不得直接替 Character Agent 编写最终对玩家台词（FR-02、FR-03）。
- 发给玩家的消息必须遵守后台未知事件不能直接展示的规则（FR-05）。
- 同一个主动联系理由最多主动发送一次；玩家未回复不能持续催促（FR-11）。
- 消息送达、阅读、重复发送和多角色表达如何构成“一次主动发送”，待确认。

## 23. Checkpoint

### Purpose

表示世界演进过程中可供保存、恢复或建立分支参考的检查点概念；具体操作语义待确认。

### Owns

检查点所对应的世界与时间线位置，以及需要保持一致的世界上下文范围的定义责任。

### Does not own

不预设快照存储技术，不默认回退所有外部交互或已产生费用，也不自行规定知识与记忆的恢复边界。

### Relationships

关联 World、WorldClock、WorldState、Timeline、WorldTruth、Knowledge、Memory、WorldPlan 和 LLMUsage 的恢复语境。

### Important invariants

- 世界支持 Checkpoint 与 Timeline Branch（FR-22）。
- Checkpoint 的保存与恢复范围、恢复后已有消息如何处理，以及知识、记忆、候选计划与费用的边界，待确认。
- Checkpoint 不能成为向普通玩家直接公开未知后台事件或关系数值的途径（FR-05、FR-07）。

## 24. Timeline

### Purpose

表示世界的一条演进历史语境，并承载 Timeline Branch 的分支概念。

### Owns

历史演进的归属语境、分支之间的来源关系，以及区分不同演进路径的概念责任。

### Does not own

不预设分支合并、跨分支传递知识、自动覆盖历史或存储策略，也不默认与现实时间相同。

### Relationships

关联 World、WorldClock、WorldState、WorldEvent 和 Checkpoint；为 Knowledge、Memory、WorldPlan 提供历史语境。

### Important invariants

- 世界支持 Timeline Branch（FR-22）。
- 某条分支中的事实与其他分支如何隔离、分支是否能合并，以及切换分支后的玩家认知如何解释，待确认。
- 分支行为仍须遵守世界事实与角色、玩家知识分离，以及玩家单一物理地点约束（FR-04、FR-06）。
- WorldTime 是逻辑坐标，不是历史身份；不同分支在同一坐标可以有不同事件，不能按时间坐标合并 EventId。C-003A 不实现 Timeline 或分支归属。

## 25. DirectorProfile

### Purpose

表示用户可配置的 Director 风格偏好，为世界调度提供风格语境。

### Owns

Director 风格的配置含义及其对规划和调度的偏好表达；具体可调维度待确认。

### Does not own

不承担 Character 人格或最终台词，不改写冻结产品规则，也不把高级模型参数作为普通用户风格设置的默认内容。

### Relationships

关联 Director、WorldPlan、PlanningWindow 和 OutreachEpisode；与 ModelProfile、预算及路由策略的关系待确认。

### Important invariants

- Director 有用户可配置风格面板（FR-16）。
- UI 面向非技术用户，高级模型参数隐藏到 Advanced/Developer Settings（FR-21）。
- 风格配置仍须遵守 Busy / Available、主动联系去重和批量规划约束（FR-08 至 FR-15）。

## 26. LLMProvider

### Purpose

表示提供 LLM 能力的来源，供后续模型配置、路由和使用记录关联。

### Owns

模型能力提供方的概念身份及其与可用模型的关联。

### Does not own

不决定具体供应商、网络协议、部署方式或技术框架，不承担世界事实、知识归属和产品规则裁定。

### Relationships

关联 ModelProfile、LLMUsage，以及未来预算与模型路由的概念责任。

### Important invariants

- 产品必须记录 Token、Latency 和 Cost，并支持预算与模型路由（FR-24）。
- 本阶段不选择供应商或模型；提供方切换、失败处理与费用来源的产品约定待确认。

## 27. ModelProfile

### Purpose

表示某种模型使用配置的概念描述，为模型路由和不同任务的模型使用提供依据。

### Owns

模型使用配置的含义，以及配置与提供方、任务需求和使用约束之间的关联。

### Does not own

不预设模型名称、具体参数、路由算法或框架，不替代 DirectorProfile 的用户风格含义，也不绕过领域规则。

### Relationships

关联 LLMProvider、LLMUsage 及预算和路由语境；可供 Director、Character Agent、AI Character Builder 与 AI World Builder 的模型使用关联，具体分配待确认。

### Important invariants

- 产品支持预算与模型路由（FR-24）。
- 高级模型参数隐藏到 Advanced/Developer Settings（FR-21）。
- 模型配置不能允许为每个普通小事件单独调用 LLM（FR-13）。
- 任务如何分配模型、失败如何切换以及预算如何限制选择，待确认。

## 28. LLMUsage

### Purpose

表示 LLM 使用与运行表现的记录概念，为费用观察、预算和模型路由提供依据。

### Owns

Token、Latency 和 Cost 的使用记录含义，以及这些使用记录与模型和决策语境的关联。

### Does not own

不预设数据库计量字段、供应商价格或结算方式，不替代完整决策 Trace，也不自行设定预算超限时的产品行为。

### Relationships

关联 LLMProvider、ModelProfile，以及 Director、Character Agent、Builder 的调用和 Developer Mode 的决策 Trace 语境。

### Important invariants

- 产品必须记录 Token、Latency 和 Cost，并支持预算与模型路由（FR-24）。
- Developer Mode 能查看 Director、Agent、Memory、LLM 使用等决策 Trace（FR-23）。
- Token 统计口径、Latency 测量范围、Cost 实际值与估算值、预算周期、超限行为，以及分支/恢复后的费用归属，待确认。

## 待确认问题索引

以下内容只记录缺口，不增加或变更冻结规则。跨文档统一问题列表见 [PRODUCT_SPEC.md](../product/PRODUCT_SPEC.md)。

1. World 的玩家数量与多人参与范围；WorldClock 的推进、暂停、离线与分支时间语义。
2. Location 的移动与在途语义；Scene、Mission、Conversation 的边界及相互关系。
3. Busy / Available 的控制方式；“必要主动联系”的范围；同一理由、一次发送与多角色 Episode 的对应关系。
4. Planning Window 的尺度、耗尽判定和“大量失效”阈值；候选激活冲突与失败的处理边界。
5. Draft → Preview → Commit 的适用对象边界：运行时台词、WorldPlan、事件生成及记忆摘要等是否适用，以及如何衔接、按什么粒度审核；不能自行将原规则缩窄到 Builder。
6. Knowledge 的获得、传闻与修正（错误 CharacterBelief 已明确允许）；Memory 的分类、遗忘和修正；Relationship 的非数值反馈（方向已确认为有向）。
7. Checkpoint 的恢复范围、Timeline Branch 的隔离/合并/切换语义，以及知识、记忆、消息、候选计划和费用的归属。
8. DirectorProfile 的风格维度；模型路由、预算超限行为与 Token / Latency / Cost 的统计口径。

## 相关文档

- [系统概览](SYSTEM_OVERVIEW.md)：逻辑职责与协作边界。
- [Director 模型](DIRECTOR_MODEL.md)：调度、规划、主动联系与角色表达边界。
- [事件模型](EVENT_MODEL.md)：候选、激活、实际事件与可见性。
- [知识模型](KNOWLEDGE_MODEL.md)：事实、角色知识与玩家知识分离。
- [记忆模型](MEMORY_MODEL.md)：记忆归属与待确认生命周期。
