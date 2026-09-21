# Stage 5 Acceptance — World Kernel and Simulation Runtime

状态：**Accepted / Frozen after C-006D**。Stage 5 建立最终产品继续沿用的 deterministic simulation substrate；没有 Director、Character cognition、Memory、conversation 或 LLM simulation。

后续状态：C-007A 已在 Stage 5 冻结 substrate 之上新增独立 EpisodicMemory 形成路径；它不修改本页验收语义。见 [EPISODIC_MEMORY.md](EPISODIC_MEMORY.md)。

## C-006A — durable tickless scheduling

- one durable queue per world；顺序固定为 `(due_at, priority, enqueue_position)`；
- one interruptible asyncio scheduler task per active world，不创建 per-trigger/per-Character task；
- bounded `max_items + 1` due drain、crash-safe Trigger→FIRED + Activation transaction；
- trigger 是到期工作，不是 fictional event。

证据：[scheduler architecture](SIMULATION_SCHEDULER.md) 与 [scheduler tests](../../tests/application/test_simulation_scheduler.py)。

## C-006B — deterministic action and perception

- typed ActionProposal 经 authority/precondition/allowlisted resolver 后由 Kernel 提交；
- accepted mutation、WorldEvent、event-time Observation、wake Activation 和 receipt 原子提交；
- Scene 是单 Location 互动上下文，不是物理位置或 Conversation；
- Observation 是发生时访问快照，不自动成为 Knowledge/Memory。

证据：[action resolution](ACTION_RESOLUTION.md)、[scenes/perception](SCENES_AND_PERCEPTION.md)、[action tests](../../tests/application/test_action_resolution.py) 与 [scene tests](../../tests/application/test_scenes.py)。

## C-006C — sparse activation and fidelity

- WORLD/CHARACTER typed targets、normalized cause history、explicit compatible coalescing；
- bounded fanout，WORLD aggregate 不展开人口；PLAYER 不是 autonomous target；
- fidelity 按 selection-time Scene/Presence/attention 推导，并与 queue priority 分离；
- Activation 不执行 cognition、action、knowledge 或 LLM。

证据：[sparse activation](SPARSE_ACTIVATION.md)、[fidelity](SIMULATION_FIDELITY.md) 与 [activation tests](../../tests/application/test_sparse_activation.py)。

## C-006D — realtime/offline reconciliation

- live process 从固定 monotonic base + exact Decimal scale 推进，不受 UTC 跳变影响；
- graceful checkpoint、pause/resume/scale change 先 re-anchor，有 revision CAS；
- restart 以 persisted UTC bridge 计算一次 fixed target，wall regression 零推进且 anchor 不回退；
- durable target 先提交，再按既有 queue 顺序 bounded drain；每批后可 yield，结束前 authoritative re-query；
- `CATCHING_UP` 屏障拒绝外部时序敏感 mutation；失败 world DEGRADED，不伪造 READY；
- restart mid-catch-up 不重复 WorldTime、Trigger、Activation 或 cause；365 天空 gap 不按时间单位循环。

证据：[clock reconciliation](CLOCK_RECONCILIATION.md) 与 [clock/catch-up tests](../../tests/application/test_clock_reconciliation.py)。现有 `world_clocks` schema 已足够；Alembic head 保持 `0013_sparse_simulation_activation`。

## Final causal architecture

```text
Time
→ ScheduledTrigger
→ SimulationActivation
→ future Director/Character cognition
→ ActionProposal
→ deterministic World Kernel
→ WorldEvent
→ event-time Observation
→ future Knowledge / Memory
```

每个箭头是显式边界，不是自动等价或隐式授权。

## Frozen invariants

```text
Time due             != event happened
Activation           != action
ActionProposal       != WorldEvent
WorldEvent           != Perception
Perception           != Knowledge
Fidelity             != Priority
Scene                != Location
Proposer             != Actor
World activation     != activate everyone
Player               != autonomous simulation target
LLM                  != canonical world authority
```

Stage 5 catch-up 可以断定 work 已到期，但不能创作虚构决策结果。后续智能层只能通过 ActionProposal→Kernel 管线使结果成为 canonical WorldEvent。

## Performance and isolation gate

- 10,000 Characters + 3 explicit targets：只创建 3 个 work，无 10,000 tasks；
- 365-day empty gap：一次 reconciliation、一次空 bounded query、零 Character scan；
- large backlog：bounded batches、stable order、无 all-row load；
- 256 witnesses + WORLD wake：一个 aggregate activation；
- 100 compatible causes：一个 pending activation、完整 bounded cause history；
- no provider/API key/network：clock reconciliation 和 catch-up 不依赖 Stage 4 LLM runtime。

Stage 5 到此冻结；Stage 6 后续工作不能改写上述因果与权限边界。
