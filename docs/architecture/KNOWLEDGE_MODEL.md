# 知识模型

状态：保留 Stage 0 语义；C-003A 实现 KnowledgeAssertion / Observation 领域值与不变量，不实现存储、检索、权限执行或知识传播。依据 [PRODUCT_SPEC.md](../product/PRODUCT_SPEC.md) 的 FR-03、FR-04、FR-05、FR-07、FR-17 至 FR-20、FR-22、FR-23，以及已接受的 [Architecture Review 001](ARCHITECTURE_REVIEW_001.md)。

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

Observation 定义 `world_id`、`principal_id: CharacterId | PlayerId`、`target_id: EventId | KnowledgeAssertionId`、channel、`observed_at: WorldTime`。可选 `created_at` 仅用于系统审计，必须是 aware datetime 并归一化 UTC，拒绝 naive。

channel 必须为 ObservationChannel 的 `witnessed / told / message / news / document / inferred` 之一；不接受未知渠道或未解析的原始字符串。主体与目标必须在同一世界。该对象记录一个显式观察，不自动授予检索权限、不传播/复制断言，也不因 inactive 玩家仍在某地点而创建见证记录。

权限过滤必须先于 semantic retrieval / prompt assembly，这是已接受的架构边界；C-003A 只验证 scope / owner，不实现检索或权限服务。错误所有权抛出 InvalidKnowledgeOwnershipError，跨世界引用抛出 CrossWorldReferenceError。

## 2. 已冻结的边界

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
