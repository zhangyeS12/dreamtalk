# Event Model

> 状态：保留 Stage 0 概念边界；C-003A 实现不可变 WorldEvent 领域值及不变量。候选激活、Kernel 提交、持久化、ledger、projection、回放和业务事件目录均未实现。

规则来源：[PRODUCT_SPEC.md](../product/PRODUCT_SPEC.md) 中的 FR-01、FR-02、FR-04 至 FR-15、FR-22 至 FR-24。规划责任见 [DIRECTOR_MODEL.md](DIRECTOR_MODEL.md)，信息归属见 [KNOWLEDGE_MODEL.md](KNOWLEDGE_MODEL.md)。

## 1. 核心区分

```text
CandidateEvent != WorldEvent
```

**候选事件只有被激活后才成为真正的世界事实。**

CandidateEvent 表达一个可能发生、尚待处理的世界事件；WorldEvent 表达已经实际发生的世界事件。来自候选的 WorldEvent 必须经过激活；是否所有 WorldEvent 都必须先成为候选、玩家即时行为如何形成事件，仍待确认。World Plan 与 Event Reservoir 中存在某个候选，不意味着该事件已发生。延期或取消候选也不意味着发生过该候选描述的事情。

| 概念 | Purpose | 事实边界 |
| --- | --- | --- |
| CandidateEvent | 承载可以由传统程序激活、延期或取消的候选安排 | 激活前不是世界事实，不能提前更新角色或玩家对已发生事件的知识。 |
| Event Reservoir | 组织待处理候选，供传统程序处理 | 候选集合不等于已发生事件集合。 |
| World Plan | 提供一批调度安排与候选事件的规划上下文 | 计划不等于事实，也不保证候选必然发生。 |
| WorldEvent | 表达已实际发生的事件及其世界层面影响 | 若源自候选则必须经激活；事实成立不等于玩家或任一角色已获知。 |
| WorldTruth | 表达世界内实际成立的事实 | 不与任何单一主体的 Knowledge 混为一体。 |
| RelationshipEvent | 表达关系变化相关的事件概念 | 后台关系可以变化，但不能因此向普通玩家展示关系数值。 |

WorldEvent、RelationshipEvent 与 WorldTruth 的关系属于概念分工。本文不由这些名字推导数据库表、继承关系、存储模型或事件溯源技术。

## C-003A WorldEvent 合约

实现见 [events.py](../../services/core/src/livingworld/domain/events.py)，时间与世界边界见 [DOMAIN_MODEL.md](DOMAIN_MODEL.md)。

| 成员 | 领域含义 / 当前约束 |
| --- | --- |
| event_id / world_id | 独立 EventId 和所属 WorldId，归属必须相同 |
| event_type | 必填非空事件语义标签；未定义业务事件目录 |
| occurred_at | WorldTime，表示事件在世界内实际发生的逻辑位置 |
| created_at | aware datetime，归一化 UTC，表示软件现实时间中的记录创建时间 |
| payload / payload_version | JSON object 的防御性不可变副本，包括嵌套 object / array；版本必须是正整数，拒绝 bool、非有限数、非 JSON 值与循环结构 |
| causation_id | 可选同世界 EventId 或现有 RequestId，区分事件原因与命令请求 |
| correlation_id | 可选独立 UUID CorrelationId，用于关联一组工作，不等同于事件身份 |
| idempotency_key | 可选非空语义键；本任务不执行去重 |

**双时间表示歧义已解决。** occurred_at 不是 UTC；created_at 不是世界时间。两者刻意允许不同，尤其未来离线 catch-up 可记录较早的世界发生位置和较晚的现实创建时间；本任务不实现 catch-up 或持久化。naive created_at 一律拒绝，aware 的非 UTC 输入统一归一化 UTC，不隐式转换 occurred_at，也不跨轴比较大小。

WorldTime 是逻辑坐标，不是全局事件 ID；两个 EventId 可以共享同一 WorldTime，未来分支也可以在同一坐标拥有不同历史。C-003A 不加入日历、调度或分支身份机制。

WorldEvent 是 canonical history 的不可变领域表达，frozen snapshot 没有 update/delete 方法。外部原始 payload 后续修改不会改变事件；事件内部的嵌套结构也不能修改。此处创建 Python 值不意味着事件已由 Kernel 提交或世界事实已落库。只有未来 Deterministic World Kernel 能正式提交 canonical WorldEvent，Director 只提出批量计划。CandidateEvent 没有在 C-003A 实现，更不能通过构造候选提前写入事实。

[CommandReceipt](../../services/core/src/livingworld/domain/commands.py) 定义未来请求幂等性接口：现有 RequestId、world_id、command_type、非空 status 标签、可选同世界结果引用、UTC 创建/完成时间及 Revision。完成时间不能早于创建时间。回执没有执行、保存、重试或去重行为；同一个 key 构造多个事件不会在此层自动合并。

## 2. 候选的语义生命周期

以下词语描述语义，不是已确定的代码状态名或完整状态机。

| 处理 | 含义 | 是否成为该候选描述的世界事实 |
| --- | --- | --- |
| 进入候选集合 | 某个可能事件被纳入 World Plan / Event Reservoir | 否。 |
| 激活 | 候选被传统程序正式转为实际发生的 WorldEvent | 是；事实可见性仍需单独判断。 |
| 延期 | 暂不发生，留待后续处理 | 否；延期本身不证明角色已经执行候选动作。 |
| 取消 | 不执行该候选安排 | 否；不能将被取消的情节写成已发生历史。 |

处理过程可以需要决策 Trace，但“系统处理过候选”的开发者记录，不等于候选描述的剧情已经发生。延期和取消是否还能重新纳入其他计划、何时失效，以及具体状态转换，尚待定义。

## 3. 规划与执行责任

1. Director 负责世界事件与宏观剧情调度（FR-02），采用批量 World Plan + Event Reservoir（FR-13）。
2. Event Reservoir 中候选的激活、延期或取消由传统程序完成（FR-14）。
3. 禁止为每个普通小事件单独调用 LLM（FR-13）。
4. Planning Window 耗尽或大量计划失效才触发 Replan（FR-15）。本文不增设其他触发条件，也不自行给出窗口长度或失效阈值。

候选是否可被激活需要保持冻结约束，例如玩家任意时刻只能存在于一个物理地点（FR-06）。激活条件怎样表达、冲突如何解决、失败如何恢复，本阶段均不选择实现方案。

## 4. 发生与获知是两个判断

世界真实事实、Character Knowledge 和 Player Knowledge 分离（FR-04）。因此必须区分：

| 判断 | 回答的问题 |
| --- | --- |
| 事实判断 | 事件是否已经实际发生；若来自候选，是否已激活？ |
| 知识归属判断 | 哪个角色或玩家已经获知了什么？ |
| 玩家展示判断 | 该内容能否向当前玩家展示？ |

后台发生但玩家不知道的事件不能直接展示给玩家（FR-05）。角色也不能因为事件已发生或 Director 知道它，就自动获得相应 Character Knowledge。知识如何经由观察、对话等途径获得，见 [KNOWLEDGE_MODEL.md](KNOWLEDGE_MODEL.md)；具体规则尚待进一步定义。

角色拥有的记忆同样不能直接装入尚未发生候选所描述的经历，见 [MEMORY_MODEL.md](MEMORY_MODEL.md)。本文区分“对未来安排的了解”和“对已发生经历的记忆”，不将两者等同。

### 概念例子：广场相遇

- **候选：** 计划安排两位角色稍后在广场相遇。此时相遇尚未发生。
- **延期或取消：** 如果候选被延期或取消，不能出现“他们已经在广场见过面”的事实或经历记忆。
- **激活：** 候选激活后，相遇成为 WorldEvent；它对世界的影响才属于已经发生的内容。
- **获知：** 玩家不知情时，不能直接向玩家展示这场后台相遇。后续获知的内容与范围必须另外判定。

例子只解释概念，不定义观察距离、传播规则、调度算法或 UI。

## 5. 主动联系相关事件

主动联系属于世界调度的一部分，候选安排仍须经过实际执行与知识边界判断，不能把“计划联系”当作“已经联系”。

- 玩家具有 Busy / Available 状态（FR-08）。Busy 时 Director 不得发起非必要主动联系（FR-09）；Available 时可以安排一个角色或一组角色主动联系（FR-10）。
- 同一个主动联系理由最多主动发送一次，玩家未回复不能持续催促（FR-11）。该规则在候选延期、重新规划或多角色组织时也必须保持，具体身份与计数语义待确认。
- 多角色主动联系围绕统一目的形成 Outreach Episode（FR-12）。Episode 与一个 CandidateEvent、一个 WorldEvent、一个 Conversation 或一条 Message 是否一一对应，尚未确定。
- Director 调度事件与联系目的，不能直接替 Character Agent 编写最终对玩家台词。

是否已安排、是否已发生联系以及哪些 Message 已实际呈现给玩家，是需要区分的概念；本阶段不定义投递机制或失败重试策略。

## 6. 时间线、记录与成本边界

- 世界支持 Checkpoint 与 Timeline Branch（FR-22）。同一个候选在一个分支中的处理，不能仅凭名称被当作另一分支已经发生的事实；分支的继承、恢复和回滚规则仍需明确。
- Developer Mode 能查看 Director、Agent、Memory、LLM 使用等决策 Trace（FR-23）。候选激活、延期、取消与 Replan 的依据属于需要说明的决策范围；Trace 的具体内容和保留方式未确定。
- 产品必须记录 Token、Latency 和 Cost，并支持预算与模型路由（FR-24）。候选执行与 LLM 调用是不同概念，不能将每个普通小事件处理都推导成一次 LLM 调用。

持久化方向见 [Architecture Review 001](ARCHITECTURE_REVIEW_001.md)；C-003A 不实现事件总线、队列、数据库业务、事务提交或持久化。

## 7. 待确认的产品定义

| 问题 | 需要澄清的范围 |
| --- | --- |
| 激活边界 | 何时判定候选已激活、世界影响已成立；执行失败是否允许部分影响。 |
| 事件来源 | 是否所有 WorldEvent 都先进入候选阶段；玩家即时行为如何形成事实。 |
| 候选冲突 | 多个候选争用角色、地点或其他世界条件时的裁决原则；不预设优先级算法。 |
| 延期与取消 | 延期的期限、取消的终局性、候选失效原因，以及重新规划时的衔接方式。 |
| Replan 条件 | Planning Window “耗尽”的含义；“大量计划失效”的范围与阈值。 |
| 事件粒度 | 一次相遇、关系变化、多人联系与 WorldEvent 之间怎样划分。 |
| 主动联系计数 | 同理由身份与作用域；多人 Episode 的一次发送边界；投递失败和未回复如何区分。 |
| Busy 必要性 | 必要联系的定义，以及激活前玩家状态变化的处理。 |
| 事实影响与更正 | 事件影响、关系变化如何对应；错误激活、回滚或更正的产品语义。 |
| Checkpoint / Timeline | 候选、已发生事件、知识、记忆和联系去重记录的继承与恢复范围。 |
| 可观察性 | Trace 中可查看哪些事实和决策，开发者信息怎样与普通玩家可见内容保持边界。 |
