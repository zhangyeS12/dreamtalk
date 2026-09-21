# Sparse Simulation Activation

状态：C-006C 已建立 Stage 5 的稀疏、定向、可合并 simulation attention substrate。它只产生 durable work，不执行 Director、Character cognition、动作、知识形成、Memory、对话或 LLM 调用。

## 1. 基本边界

```text
canonical world state
→ concrete typed cause
→ bounded target resolution
→ durable ActivationRequest
→ optional compatible coalescing
→ bounded due selection
```

默认没有角色思考。系统不按世界轮询全部 Character，不为每个 Character 创建 asyncio task，也不因为角色存在就生成周期工作。`SimulationActivation != ActionProposal != WorldEvent`：Activation 只是“有原因需要处理的工作”，不是动作，更不是已经发生的事实。

`Perception != Activation`。Observation 记录谁在事件发生时拥有访问；wake policy 独立决定谁立即获得工作。感知可以很多而激活为零、少量 Character，或一个 WORLD aggregate。Activation 本身不创建 Observation、KnowledgeAssertion、CharacterBelief、PlayerKnowledge 或 Memory，也不授予对其原因事件的访问。

## 2. Typed target 与 cause

`ActivationTarget` 只有：

| target | 含义 |
| --- | --- |
| `WORLD` | 一个世界级工作单元，供未来编排、广域事件或 catch-up 聚合使用 |
| `CHARACTER` | 一个明确 Character 的定向工作 |

`PLAYER` 不是 activation target；LivingWorld 不创建“Player AI”。WORLD 也不表示“激活所有角色”。

`ActivationCause` 是 immutable typed union：

- `SCHEDULED_TRIGGER`：必须且只能引用同世界 TriggerId；
- `WORLD_EVENT`：必须且只能引用同世界 EventId；Character target 还必须已有该事件的 `EVENT_OCCURRENCE` Observation；
- `SCENE_ACTIVITY`：引用同世界 SceneId、typed activity 和 source RequestId；
- `EXPLICIT_SYSTEM`：使用 source RequestId 表示受信 application seam 的审计身份。

原因行只保存 typed IDs、kind/version、WorldTime 与安全审计数据，不复制 WorldEvent payload，也不保存 dialogue、prompt、model output、private memory 或 secret。非 scheduled request 必须使用 typed cause references，payload 必须为空；C-006A scheduled activation 只沿用其既有 bounded safe trigger payload contract。

## 3. Wake specification 与 fanout

`EventWakeSpec` 支持 `NONE / ACTOR / SCENE_CHARACTER_PARTICIPANTS / EXPLICIT_CHARACTERS / WORLD`。ACTOR 只有在 actor 是 Character 时才产生 Character target。Scene wake 只查询该 OPEN Scene 的当前 active Character participants；它排除 Player、历史参与者和仅在相同 Location 的其他 Character。

每个直接 Character fanout 都有 hard bound。超过上限时，在任何 activation/cause 写入前返回 typed `ActivationFanoutTooLargeError`；不会按数据库顺序截断，也不会随机采样。只有 originating policy 明确选择 WORLD 时才生成 aggregate，不会由基础设施偷偷改写 policy。

## 4. Compatible coalescing

只有全部以下字段相同的 PENDING work 才能合并：

```text
WorldId
typed target kind + target identity
ActivationKind + version
explicit coalescing_key
status = PENDING
```

`coalescing_key = None` 表示不合并。不同 kind（例如 `character_reaction` 与 `character_schedule_due`）即使目标相同也保持独立。合并规则是 `due_at = min(existing,new)`、`priority = min(existing,new)`；priority 数值越小越紧急。原有 `enqueue_position` 保持不变，因此顺序仍由持久化 `(due_at, priority, enqueue_position)` 决定，不用原因 UUID 作选择。

每个兼容流内，typed source identity 是幂等原因。精确重试返回原 activation；相同原因身份配不同语义明确冲突。同一个 WorldEvent 可合法成为多个不同 Character target 的原因，因此 source identity 不是全世界单例。并发 writer 由 SQLite `BEGIN IMMEDIATE` 串行化，partial unique pending-coalescing index 与 activation 内 cause 主键提供最终加固；结果是一条兼容 PENDING activation 加全部唯一原因。

原因采用 normalized `simulation_activation_causes`，按每 activation 单调 `position` 稳定排序。读取必须给出正整数 limit，可带 offset，并返回 `more_causes`；调用方不需要把全部因果历史载入内存。

## 5. Kind registry 与选择

`ActivationKindRegistry` 只接受显式 `(ActivationKind, version, target kind)`：当前保留 `world_orchestration`、`character_reaction`、`character_schedule_due`、`scene_activity` v1。持久化值不能选择 Python import、callable 或 handler。C-006C 没有 handler execution。

selection 只按 world、PENDING、due boundary 和 bounded limit 读取，固定顺序为 `(due_at, priority, enqueue_position)`。WORLD candidate 的 fidelity 为 `None`；Character candidate 在同一个 UoW snapshot 内从当前 Scene/Presence/CharacterState 推导 fidelity，见 [Simulation Fidelity](SIMULATION_FIDELITY.md)。

## 6. C-006A 与 C-006B 集成

C-006A 的 trigger 现在显式携带 activation target、kind/version、coalescing key 与 attention。到期 materialization 复用同一 generalized repository，同时保留：

- Trigger `FIRED` 与 activation/cause 同事务；
- `(world_id, source_trigger_id)` audit linkage 与唯一性；
- commit 前 crash 全回滚，commit 后 durable；
- retry 不重放；
- 旧 0011 activation 迁移为 WORLD / `world_orchestration` v1，并 deterministic backfill `SCHEDULED_TRIGGER` cause。

C-006B accepted action 可带明确 wake policy。Kernel 先 bounded resolve targets，再在一个 command transaction 内提交 projection mutation、WorldEvent、全部 event-time Observations、activation/cause 与 receipt。Character `WORLD_EVENT` activation 只有在同事务中已经拥有对应 Observation 时才可写入。任何一步失败会一起 rollback。

## 7. Scale、privacy 与 deferred scope

验证场景包括 10,000 Characters 中只有 3 个明确目标时只产生 3 条 work，且不创建 per-character tasks；100 个兼容原因合并为 1 条 character_a activation、保留 100 条 cause，并可按 20 条分页；256 个合法 witnesses 的 event 使用 WORLD policy 时只有 1 条 WORLD activation。

C-006C 不实现 consumption lifecycle、distributed leasing、Director importance、随机抽样、Character goal/emotion/plan/dialogue、Memory/RAG、LLM 或 speaker loop。C-006D 已复用 bounded due selection、coalescing 与 WORLD aggregation 完成 deterministic catch-up，没有把 missed cause 扩张成角色 cognition call；实际 activation consumption 仍属于后续阶段。
