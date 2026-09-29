# Director 批量规划：成熟实现调查

2026-09-29；基线 bd50a3c；用户确认上一轮体验无问题，继续推进 Director。调查先于实现；其后用户明确批准推荐方案，实施范围见交接与已批准提案。

## 已查看的主源

| 项目 | 版本与许可 | 有用部分 | 接入判断 |
| --- | --- | --- | --- |
| [Generative Agents plan.py](https://raw.githubusercontent.com/joonspk-research/generative_agents/main/reverie/backend_server/persona/cognitive_modules/plan.py) | 当日 main，未固定发行版；[Apache-2.0](https://raw.githubusercontent.com/joonspk-research/generative_agents/main/LICENSE) | long-term daily/hourly plan，再按情境分解和调整 | 可参考粗粒度计划。当前实现按 persona 多次生成/分解并写 associative memory、依赖 maze/scratch；不能直接替代一次世界批量规划、Kernel、可信预留和 owner 过滤。未复制或安装。 |
| [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) / [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | 当日 main pyproject 1.2.12，[MIT](https://raw.githubusercontent.com/langchain-ai/langgraph/main/LICENSE) | 持久检查点、明确暂停/恢复、恢复重跑前的副作用必须幂等 | 现有 SQLite/Alembic、durable UUID claim、CAS、receipt 已提供关键边界。直接换 runtime 会重复状态、引入 LangChain/checkpoint/sdk 等依赖；仅为顺序“生成→校验→存候选”安装完整图运行时没有当前收益。未安装或重写。 |
| [Concordia](https://github.com/google-deepmind/concordia) | 前轮已记录当日 main/Apache-2.0 | 角色观察与环境执行的职责分离 | 前轮调查沿用；自然语言 Game Master 不能成为 canonical mutation 权威，独立 engine 不替换现有 tickless scheduler。 |

## 建议复用

继续使用已有受控模型网关、多供应商 adapter、可信 Token/金额预留、SQLite/SQLAlchemy/Alembic、Pydantic、typed scheduler、Kernel action/receipt 和 Observation。新增的部分应只承担本项目特有的 WorldPlan/Candidate 契约及审批后的执行权限，而不是再实现模型客户端、调度器、记忆库或所有角色常驻循环。

框架不会替产品确定“何时自动付费规划”“计划需不需要逐批确认”“Director 可以让哪个角色移动”。这些是现有文档明确未定的规则，不能用第三方默认值偷偷替代。具体推荐见 [Director 运行方案](../proposals/2026-09-29-director-runtime.md)。

调查基线源码事实：ActionKind 当时只有 move_player，Direct/Group selector 与 WorldPlan 无关，scheduler 当前仅将 Trigger materialize 为 Activation；没有 Director 候选消费者。已有 PlaceCharacter 是可信 canonical setup/placement 命令，不能把它当成已通过权限校验的 Director 活动接口。

实现采用原有受控有界任务 helper（新增通用名generate_bounded_text，保留authoring兼容名）、同一每世界 scheduler、SQLAlchemy/Alembic/Pydantic/Kernel。没有安装框架或复制第三方源码。新增部分是本项目特有的授权、候选契约与Kernel动作；复用了已经成熟的网关/预算/存储/调度/Observation。
