# Evidence-Backed Episodic Memory

状态：C-007A 已建立 Stage 6 的第一条 Character-owned episodic memory 写入与读取路径。它只记录经授权 Observation 支撑的不可变主观回忆；没有 Reflection、consolidation、forgetting、embedding、semantic retrieval、LLM、Director、Character Agent 或 UI。

## 1. 语义边界

```text
WorldTruth != Observation != EpisodicMemory != CharacterBelief != Reflection
```

- WorldTruth 是世界权威命题。
- Observation 是某主体对 Event 或 Assertion 的一次历史访问/暴露记录。
- EpisodicMemory 是一个 Character 后来明确形成并保留的主观经历表达。
- CharacterBelief 是 Character 自有的 epistemic proposition。
- Reflection 是未来从记忆推导的新解释性产物，C-007A 不实现。

Memory 内容可以主观、片面或错误。Observation evidence 证明 Character 对来源具有已授权的历史访问以及该 Memory 的 provenance；它不证明 Memory 文本为真，也不授予新的 Truth、Belief 或 Knowledge。

## 2. 不可变领域模型

`EpisodicMemory` 使用 world-scoped typed `MemoryId`，并且只允许 `owner_character_id: CharacterId`。C-007A 没有 Player-owned 或 World-owned Memory。

| 字段 | 冻结语义 |
| --- | --- |
| kind / kind_version | `episodic` / 1；future kinds 目前明确拒绝 |
| content | nonblank `plain_text` v1；UTF-8 最多 16 KiB |
| experienced_from / experienced_to | 所有 source Observation 的最小/最大 `observed_at: WorldTime` |
| formed_at | 执行写入时的 effective `WorldTime`；不得早于来源经历 |
| created_at_utc | aware UTC 系统审计时间，不参与世界时间推断 |
| salience | `None` 或显式整数 0..100；0 与未提供不同，不由系统推断 |
| provenance | `observation_evidence` v1 + 1..256 个有序且不重复的 ObservationId |

`WorldTime` 仍只是逻辑坐标。MemoryId 才是记忆实体身份；相同文本和相同 evidence 可以形成多个独立 Memory。没有按文本、时间或来源自动去重。

## 3. 授权与形成事务

唯一受支持的应用入口是内部 `RecordEpisodicMemory`：

```text
RequestId + Character owner + ordered ObservationIds + content + optional salience
→ world/Character existence validation
→ owner-scoped SQL evidence authorization
→ derive experience range and current formed_at
→ insert EpisodicMemory + ordered evidence rows + CommandReceipt
→ one transaction commit
```

授权查询先限定 `world_id`、`principal_kind=character`、绑定 Character 的 principal columns，再读取请求中的 ObservationId。不存在、Player-owned、另一 Character-owned 或跨世界 evidence 均拒绝；拒绝结果不泄露某 Observation 是否存在。不能先 materialize 全局 Observation 再在 Python 过滤。

Memory 写入不创建 WorldEvent、Observation、KnowledgeAssertion、CharacterBelief 或 SimulationActivation。Observation 也不会自动形成 Memory。事务任一步失败时 Memory、evidence 与 receipt 全部回滚。

## 4. 幂等、隐私与读取

RequestId 使用既有全局命令回执。fingerprint 覆盖完整解析后的 Character、ordered evidence、content、salience 及固定的 kind/content/provenance versions；执行时间与随机 MemoryId 不参与。

- 同 RequestId + 同语义重试返回原 MemoryId，不再次写入。
- 同 RequestId + 不同语义显式冲突。
- 完整回滚没有 durable identity，后续合法重试可以生成新 MemoryId。
- receipt 只保存 versioned MemoryId result，不保存私有 Memory 文本。

读取能力 `CharacterMemoryReader` 在构造时永久绑定一个 Character。`get`、`evidence` 和 `list` 的 SQL 都包含 world + owner 条件；没有 global memory list。list 使用稳定 keyset order `(experienced_to DESC, formed_at DESC, memory_id ASC)`，每页最多 100 项；可选时间范围按经历区间 overlap 过滤。evidence API 只返回 ObservationId、observed_at 和原始 source order，不借 provenance 返回 event/assertion payload 或其他主体的知识。

## 5. 持久化、回放与内容隔离

Alembic `0014_episodic_memory` 新增：

- `character_memories`：不可变 Memory 行、Character/world 复合外键、版本/内容/时间/salience/provenance CHECK 与 owner chronology indexes；
- `episodic_memory_observation_sources`：normalized ordered evidence、Observation/world 复合外键、每 Memory/Observation 唯一约束和 reverse provenance index。

0013→0014 不改写已有 runtime、ledger、knowledge、observation、receipt 或 legacy audit rows。Alembic 仍是唯一 migration cursor；失败 DDL 整体回滚到 0013。

Projection replay 只重建既有 replay-owned projections，不删除或重新生成 Memory。EpisodicMemory 是运行时私有状态，不属于 authored content；Character Card、Lorebook 和 `.lwcontent` import/export 不包含它。

## 6. 研究方向与延后范围

C-007A 采用 episodic record、explicit evidence、temporal coordinates、optional salience 和多来源 provenance 这些基础概念，但不复制任何外部项目的固定评分公式。未来 retrieval quality、temporal updates、abstention 和 evidence-aware ranking 必须单独设计并验证。

延后：Reflection、consolidation、forgetting、correction、memory update/delete、embedding/FTS/vector/RAG、automatic Observation→Memory、Conversation/Message ingestion、LLM summarization、checkpoint/branch inheritance、Developer UI、Director/Agent consumption。任何未来派生步骤都不得把 evidence 错当作真值证明，也不得绕过 owner-first permission filtering。

验证见 [domain tests](../../tests/domain/test_memory.py)、[application tests](../../tests/application/test_episodic_memory.py) 和 [migration tests](../../tests/persistence/test_memory_migration.py)。

## 2026-09-29 实际接续状态

上方“延后”的清单记录 C007A 当时的切片范围，不代表当前全部代码。现有 DeveloperInspectorService 已能在开发者模式中按 owner 查看/记录 episodic memory；聊天上下文已消费该角色自己的记忆。release 普通界面不能因此读取其私有内容。

本日新增的普通“聊天回忆”只检索当前玩家有权访问的共同 Conversation/Message 原文，并允许查看前后文与追加草稿。[实现边界](../research/2026-09-29-chat-recall-view-reuse.md)。未增加 Memory provenance、自动聊天摘要、写入/合并/遗忘/修正或新的 WorldTruth/Knowledge；Observation-only 证据约束仍有效。


## 2026-09-29 已确认会话摘要的独立存储

前段记录的是聊天回忆切片当时的范围。本次新增独立 `conversation_memory_revisions` / `conversation_memory_drafts` 交互表（0024），不是 `character_memories` 的新 kind/provenance；Observation-only EpisodicMemory 约束仍未改变。普通玩家只预览、确认、修正自己当前绑定身份在本会话内的共同聊天摘要。确认版本及 Conversation/Message 来源形成递增链，8KiB摘要与32条新增来源有界；角色仅在该会话授权后读取已确认摘要。没有更改 Knowledge、WorldTruth、Reflection、Consolidated 或遗忘语义。详见 [CHAT_MODEL.md](CHAT_MODEL.md) 与 [复用记录](../research/2026-09-29-conversation-summary-reuse.md)。


## 与自动对话记忆的边界（2026-10-02）

桌面0.1.7的自动长期聊天记忆是另一应用层模型，保存真实对话来源但不把说过的话认证为亲历。原Observation-only约束不变。活动结束/中断新增Canonical WorldEvent与实际获准Observation，聊天按owner消费近期经历；尚没有自动把这些Observation总结写入EpisodicMemory、Reflection或Consolidated。见[MEMORY_MODEL.md](MEMORY_MODEL.md)。


## 桌面0.1.24经历召回

已有授权亲历现在可按当前话题检索，保留近期并补最多4条旧相关项，最终仍12条/8KiB；仅近128条词法召回，无额外API、事件/知识写入或自动Observation→EpisodicMemory。当前活动快照保持优先，目击不等于相遇剧情。见[体验说明](../EXPERIENCE_RECALL.md)。真实模型效果待用户验收。
