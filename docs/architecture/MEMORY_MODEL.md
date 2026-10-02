# 记忆模型

状态：C-007A 已实现 Character-owned、evidence-backed、immutable EpisodicMemory 基础。完整执行、授权、持久化与查询契约见 [EPISODIC_MEMORY.md](EPISODIC_MEMORY.md)。

## 1. 已实现边界

```text
WorldTruth != Observation != EpisodicMemory != CharacterBelief != Reflection
```

Memory 表示 Character 明确保留的主观经历，不是世界事实、知识断言、观察本身或未来 Reflection。它可以错误；其 Observation evidence 只证明来源授权与 provenance，不证明内容真实。

C-007A 只允许 Character owner。`EpisodicMemory` 使用 typed `MemoryId`，保存 bounded plain-text content、由 source observations 推导的世界经历区间、当前形成 `WorldTime`、UTC audit、optional explicit salience 与有序 evidence。对象不可变；没有 update/delete/forget API。

## 2. 形成与授权

Observation 不自动形成 Memory。内部 `RecordEpisodicMemory` 必须显式提供至少一个同世界、同 Character principal 的 ObservationId。SQL 在 materialization 前执行 world + Character owner 权限过滤；另一 Character、Player、cross-world 或 missing evidence 统一拒绝。

成功事务原子写入 Memory、normalized evidence 和 RequestId receipt。它不写 WorldEvent、Observation、KnowledgeAssertion、CharacterBelief 或 Activation。相同请求重试返回原 MemoryId；相同来源和文本的新请求可以形成独立 Memory。

## 3. 使用与隐私

读取端口永久绑定 Character，只提供 owner-scoped get/evidence/list。稳定 keyset 分页按经历结束、形成时间和 MemoryId 排序；没有全局 Memory 列表。provenance 查询只返回来源 ID、观察世界时间与 source order，不越权展开其他主体私有数据。

未来 Character Agent 可消费自己的已授权 Memory，但 C-007A 不实现 Agent 或 prompt assembly。Director 不能借 Memory 替 Character Agent 编写最终台词。面向玩家的表达仍须通过知识与可见性边界。

## 4. 回放、内容与生命周期

Memory 不属于 WorldEvent projection，projection rebuild 不重新生成或删除它。它也不是 authored content，不能进入 Character Card、Lorebook 或 `.lwcontent`。

Checkpoint / Timeline Branch 继承、Reflection、consolidation、forgetting、correction、semantic retrieval、embedding、RAG、automatic ingestion 和 LLM summarization 仍待后续任务。Developer Mode 将来展示 Memory trace 时必须继续隔离私有内容。

## 5. 与相邻概念

| 概念 | 回答的问题 | 边界 |
| --- | --- | --- |
| WorldTruth | 世界中什么是真的？ | Memory 不授予或改写 Truth |
| WorldEvent | 什么已经真实发生？ | Event 不自动成为任何主体的 Memory |
| Observation | 谁在何时对某目标有访问？ | 是 evidence；不自动形成 Memory |
| CharacterBelief | Character 相信什么命题？ | Memory 不自动形成、纠正或调和 Belief |
| Conversation / Message | 表达了什么？ | C-007A 不自动摄取对话 |
| Reflection | 从经历推导了什么解释？ | 尚未实现，不能伪装成 EpisodicMemory |


## 应用层长期对话记忆（2026-10-02，桌面0.1.7）

新增long_chat_memories/long_chat_memory_settings（0029），按world/player/character以及来源Conversation/Message隔离。正常回复同次提取最多4条identity/preference/promise/experience，quote必须属于本轮玩家原文或本次reply；只代表自述，不是Observation-only EpisodicMemory新provenance，不创建Knowledge或WorldTruth。核心/置顶/相关条目16条/8KiB，授权的参与会话历史原句4条/8KiB；复用jieba/SQLite FTS5，不额外提取/embedding API。默认自动记录，可停用、置顶与明确更正关联旧条目。详见[普通使用说明](../LONG_TERM_MEMORY.md)和[复用记录](../research/2026-10-02-long-chat-memory-reuse.md)。
