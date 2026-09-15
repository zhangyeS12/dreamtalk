# LivingWorld 产品规格

## 文档状态与适用范围

- 阶段：Stage 0 — 产品和架构定义。
- 本文记录已冻结的产品规则，以及尚待澄清的边界；这些要求不代表功能已经实现。
- C-001 交付工程仓库与设计文档骨架，不实现 Agent、Director、数据库业务或 UI 功能，不决定应用框架、数据库或其他实现技术。
- 下列 `FR-01` 至 `FR-24` 为冻结规则原文。其他文档通过这些编号引用规则；概念解释、示例和待确认问题不得改写或扩大冻结规则。

## 冻结规则

### FR-01

LivingWorld 是持久化、事件驱动的多角色 AI 世界，不是普通聊天机器人。

### FR-02

Director 负责时间、地点、世界事件、角色活动、角色相遇、关系变化和宏观剧情调度。

### FR-03

Character Agent 主要负责自己拥有的记忆、人格表达和与玩家对话。

### FR-04

世界真实事实、Character Knowledge 和 Player Knowledge 分离。

### FR-05

后台发生但玩家不知道的事件不能直接展示给玩家。

### FR-06

玩家任意时刻只能存在于一个物理地点。

### FR-07

关系后台存在，但不能向普通玩家展示数值。

### FR-08

玩家具有 Busy / Available 状态。

### FR-09

Busy 时 Director 不得发起非必要主动联系。

### FR-10

Available 时 Director 可以安排一个角色或一组角色主动联系。

### FR-11

同一个主动联系理由最多主动发送一次；玩家未回复不能持续催促。

### FR-12

多角色主动联系必须围绕一个统一目的，形成 Outreach Episode。

### FR-13

Director 使用批量 World Plan + Event Reservoir，禁止为每个普通小事件单独调用 LLM。

### FR-14

Event Reservoir 中的候选事件由传统程序激活、延期或取消。

### FR-15

Planning Window 耗尽或大量计划失效才触发 Replan。

### FR-16

Director 有用户可配置风格面板。

### FR-17

AI Character Builder 可以联网研究角色并生成带来源的角色 Draft。

### FR-18

AI World Builder 可以联网研究作品/世界并生成带来源的 World Draft。

### FR-19

自动生成内容必须经过 Draft → Preview → Commit。

### FR-20

支持 Character Card V2/V3、PNG/JSON 和 Lorebook 导入。

### FR-21

UI 必须面向非技术用户，高级模型参数隐藏到 Advanced/Developer Settings。

### FR-22

世界支持 Checkpoint 与 Timeline Branch。

### FR-23

Developer Mode 能查看 Director、Agent、Memory、LLM 使用等决策 Trace。

### FR-24

产品必须记录 Token、Latency 和 Cost，并支持预算与模型路由。

## 文档职责

| 文档 | 定义范围 |
| --- | --- |
| [PRODUCT_PRINCIPLES.md](PRODUCT_PRINCIPLES.md) | 冻结规则对应的产品原则与审阅边界 |
| [USER_FLOWS.md](USER_FLOWS.md) | 未来产品的概念流程、禁止的越界与待确认分支 |
| [SYSTEM_OVERVIEW.md](../architecture/SYSTEM_OVERVIEW.md) | 系统职责划分和概念协作 |
| [DOMAIN_MODEL.md](../architecture/DOMAIN_MODEL.md) | 领域对象的概念职责、关联和不变量 |
| [DIRECTOR_MODEL.md](../architecture/DIRECTOR_MODEL.md) | 世界调度、批量规划与角色表达边界 |
| [EVENT_MODEL.md](../architecture/EVENT_MODEL.md) | 候选事件与实际世界事件的区分 |
| [KNOWLEDGE_MODEL.md](../architecture/KNOWLEDGE_MODEL.md) | 世界事实、角色知识和玩家知识的区分 |
| [MEMORY_MODEL.md](../architecture/MEMORY_MODEL.md) | 记忆的概念职责与知识边界 |
| [research/README.md](../research/README.md) | 尚待开展的研究与证据记录方式 |

## 待确认的产品边界

以下问题不修改冻结规则，也不阻止 C-001 文档初始化。当前没有为这些问题选择默认产品策略。

| 编号 | 待确认问题 | 关联规则 |
| --- | --- | --- |
| P-01 | 世界时间如何推进？玩家离线、Busy 和暂停世界之间是什么关系？ | FR-01、FR-02、FR-08 |
| P-02 | Busy / Available 由玩家手动切换、系统推断还是两者结合？“必要主动联系”的定义、判定主体和允许形式是什么？ | FR-08、FR-09 |
| P-03 | “同一个主动联系理由”如何判定，作用域如何跨角色、时间、Timeline 和重试计算？一次主动发送与多角色 Episode 内消息的关系是什么？ | FR-10、FR-11、FR-12 |
| P-04 | Outreach Episode 的结束、参与者退出、玩家回复后继续互动，以及同时存在多个 Episode 的规则是什么？ | FR-10、FR-11、FR-12 |
| P-05 | “普通小事件”“Planning Window 耗尽”和“大量计划失效”的业务口径与阈值是什么？ | FR-13、FR-14、FR-15 |
| P-06 | 玩家通过哪些观察、交谈或其他途径获得知识？传闻、误解、遗忘、纠错及玩家已知事件的展示范围如何定义？ | FR-04、FR-05 |
| P-07 | 地点层级和移动过程如何定义？远程对话、同时参与多个 Conversation 与物理地点有何关系？ | FR-02、FR-06 |
| P-08 | 普通玩家可以看到哪些非数值关系表达？Developer Mode 是否可查看关系数值或玩家未知的世界事实，访问边界是什么？ | FR-05、FR-07、FR-23 |
| P-09 | Director 风格面板包含哪些配置项、可调范围，何时对已有计划生效？ | FR-16 |
| P-10 | Builder 来源的展示粒度、可信度处理及冲突解决方式是什么？Preview 和 Commit 由谁确认，Commit 的生效范围是什么？ | FR-17、FR-18、FR-19 |
| P-11 | Character Card V2/V3、PNG/JSON 和 Lorebook 的兼容范围是什么？导入如何处理冲突、不支持内容与来源缺失，是否统一进入 Draft → Preview → Commit？ | FR-19、FR-20 |
| P-12 | Checkpoint 包含什么，恢复与分支复制哪些状态？知识、记忆、候选事件、未完成 Episode 和已发送联系记录如何随 Timeline 处理？ | FR-04、FR-11、FR-22 |
| P-13 | Token、Latency 和 Cost 的统计范围、货币和计费口径是什么？预算耗尽、模型不可用、路由失败时采取什么产品行为？ | FR-24 |
| P-14 | Mission 的玩家体验与生命周期是什么？哪些目标对玩家可见，如何与世界调度和角色互动衔接？ | FR-02、FR-04、FR-05；任务要求中的领域对象 |
| P-15 | Developer Mode 的访问方式、Trace 详细程度、保留范围及其与普通玩家视图的隔离如何定义？ | FR-05、FR-21、FR-23 |
| P-16 | “自动生成内容”的适用对象边界是什么？运行时台词、World Plan、事件生成与记忆摘要如何衔接 Draft → Preview → Commit，预览和提交按什么粒度进行？不能自行将 FR-19 缩窄为仅适用于 Builder。 | FR-13、FR-17、FR-18、FR-19 |
| P-17 | 所有 WorldEvent 是否必须先成为 CandidateEvent；玩家即时行为如何形成事实？候选激活冲突、部分失败、延期、取消与事实更正如何处理？ | FR-01、FR-02、FR-13、FR-14 |
| P-18 | 除 Character 外是否需要其他 Memory 拥有者？记忆的写入、摘要、合并、遗忘与修正如何定义，以及如何影响 Knowledge？ | FR-03、FR-04、FR-05、FR-22 |
| P-19 | 一个 World 的玩家数量与多人参与范围是什么？ | FR-01、FR-06；任务要求中的领域对象 |

后续澄清应记录结论与对应问题编号；涉及冻结规则变更时，应明确提出变更并由产品负责人确认，不能通过示例或实现默认值隐式变更。
