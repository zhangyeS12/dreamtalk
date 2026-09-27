# Architecture Review 001：Stage 0 架构基线

```yaml
Review: ARCHITECTURE_REVIEW_001
Date: 2026-09-15
Status: Accepted
Research: W-001
```

## 审查范围

本记录归档 LivingWorld Stage 0 架构审查结论。审查输入为 [LivingWorld Architecture Research W-001](../research/W-001_LIVINGWORLD_ARCHITECTURE_RESEARCH.md)。W-001 的报告正文保持原样；本记录只接受下列明确列出的决策，报告中的其他事实、建议、假设或实现细节不会因此自动成为架构基线。

[PRODUCT_SPEC.md](../product/PRODUCT_SPEC.md) 中的 24 条冻结产品规则继续有效。P-01 至 P-19 继续作为开放问题，本次审查不解决、重写或缩小其范围。

## 已接受决策

1. **local-first / kernel-first / transport-neutral。** 产品以本地优先、世界内核优先和传输层中立为架构方向。
2. **React UI + desktop shell 与 browser 共用 UI。** 桌面壳和浏览器形态复用同一套 React UI；本决策不指定 desktop shell 的具体实现技术。
3. **Python LivingWorld Core。** LivingWorld Core 使用 Python；传输适配器的具体框架不在本次决策范围内。
4. **Director = batch planner only。** Director 只承担批量规划职责，不执行或提交世界事件，也不能直接替 Character Agent 编写最终对玩家台词。
5. **Deterministic World Kernel 是 WorldEvent 唯一提交者。** 所有 WorldEvent 的正式提交只能由确定性 World Kernel 完成。
6. **Hybrid event ledger + projection + CRUD。** 已发生的世界事件使用事件账本；当前状态使用投影；适合可变工作数据的部分使用 CRUD。具体数据结构和字段仍待设计。
7. **Desktop persistence = SQLite WAL + FTS5。** 桌面部署的持久化基线采用 SQLite WAL 与 FTS5。
8. **Server/cloud baseline = PostgreSQL + pgvector。** 服务端和云部署的持久化基线采用 PostgreSQL 与 pgvector。
9. **MySQL + Qdrant 作为后期可选 deployment/benchmark profile。** 该组合不是当前桌面或服务端默认基线。
10. **Redis/Celery 不作为桌面基础依赖。** 后期部署是否引入它们必须由实际需求和验证结果决定。
11. **asyncio 是 Core 并发基础。** Core 的并发基线采用 Python `asyncio`；本决策不预先确定更高层任务框架。
12. **WorldTruth / CharacterBelief / PlayerKnowledge 权限化隔离。** 三者在数据访问和上下文组装层面保持权限边界，不能只依靠 Prompt 约定。
13. **Knowledge retrieval 必须 permission filtering before semantic retrieval。** 任何语义检索只能在调用主体获准访问的数据范围内进行，不能先跨权限检索再隐藏结果。
14. **Builder 使用 Research → Evidence → Claim → Conflict → Draft → Preview → Commit。** Builder 的研究证据、声明、冲突、草稿、预览和提交阶段必须明确分离。
15. **Character Card V2/V3 与 Lorebook 使用独立 adapter 实现兼容，不复制 SillyTavern 源码。** 兼容通过独立实现的格式适配器完成。

决策 15 的独立实现限制后来由产品负责人调整，见 [ADR-0001：优先评估成熟项目复用](ADR/0001_reuse_mature_projects.md)。本记录保留 Stage 0 当时的原始结论。

## Planning Window 默认实验参数

```sql
Default Planning Window = 7 world days
```

该值当前只作为默认实验参数，不是不可改变的架构常量。后续可根据实验结果调整。它不解决 P-05，也不定义 Planning Window“耗尽”的产品语义或“大量计划失效”的判定阈值。

## 保持开放的边界

- P-01 至 P-19 均保持开放，继续以 [PRODUCT_SPEC.md](../product/PRODUCT_SPEC.md) 为准。
- 本次审查不实现业务代码，不设计数据库字段、API 或 UI 功能。
- W-001 中未列入“已接受决策”的具体技术建议，不因报告归档而自动获得 Accepted 状态。
