# Durable Tickless Simulation Scheduler

状态：C-006A 已建立确定性时间调度，C-006C 将到期结果接入 typed sparse activation，C-006D 复用同一 queue 完成 realtime/offline reconciliation。本文只定义 **何时工作到期**；没有 Director、Character Agent、知识传播、对话、Memory 或 LLM 调用。定向/合并/fidelity 见 [Sparse Activation](SPARSE_ACTIVATION.md) 和 [Simulation Fidelity](SIMULATION_FIDELITY.md)，offline bridge 见 [Clock Reconciliation](CLOCK_RECONCILIATION.md)。

## 1. 三种时间

三种时间不可互换：

| 时间 | 责任 |
| --- | --- |
| `WorldTime` | 世界逻辑坐标；世界 epoch 起的有符号整数微秒，是调度和 due 判断的 canonical 时间 |
| aware UTC | `WorldClock` 持久化锚点和创建/触发/取消审计时间；不是单调时钟 |
| runtime monotonic time | 当前 Core 进程内的安全经过时间和 sleep 决策；不持久化，不是世界事实 |

`WorldClock.effective_time(at_utc)` 是无副作用的精确计算：paused 或 scale=0 返回 logical anchor；running 返回 `anchor + floor(max(0, UTC elapsed microseconds) × Decimal scale)`。不使用 float 计算 canonical WorldTime。UTC 回退不会让结果早于持久化 anchor。

`EffectiveWorldTimeSource` 在 startup reconciliation 后显式建立 process-monotonic base；之后每次都从原 base 与总 monotonic elapsed 计算，避免逐次 floor 造成累计漂移。raw revision 首次出现时可用一次 aware UTC 建立 fallback base，但生产 startup/pause/resume/scale/checkpoint 均由集中 `WorldClockService` 显式 re-anchor。UTC 前后跳不改变存活进程的模拟速度。

sleep delay 是 `world delta / scale` 的近似控制值。唤醒后必须重读 DB 中的 WorldClock 和队首，旧 delay 没有 canonical 权威。当前 `WorldClock` 已允许非负 finite scale；scale=0 沿用现有语义：逻辑时间不从现实时间推进，scheduler 等待控制信号。

## 2. Tickless queue

没有固定 10ms/100ms/1s simulation tick，也没有按 Character 轮询。每个显式 active World 最多一个 asyncio task：读取 clock、drain 已到期工作、peek 下一个 trigger，然后等待 timeout 或 wake signal。10,000 个 trigger 仍是一个世界任务和数据库队列，不是 10,000 个 asyncio task。

持久化 `ScheduledSimulationTrigger` 包含 typed TriggerId/WorldId、due WorldTime、priority、world-scoped enqueue position、allowlisted kind/version、最大 16 KiB 的 immutable JSON object、PENDING/FIRED/CANCELLED、aware UTC 审计时间和 Revision。payload 不允许 pickle、callable、import path、表达式、prompt、model output 或 credential；数据库中的 kind/version 只能由显式 `TriggerKindRegistry` 解释，未知项 typed fail closed，不 dynamic import。

唯一排序规则是：

```text
(due_at ASC, priority ASC, enqueue_position ASC)
```

priority 是 `HIGH=-1 / NORMAL=0 / LOW=1` 的小型机械枚举，数值越小越先执行。它不表达角色、关系或剧情重要性。enqueue_position 由每世界 `simulation_queue_cursors` 的单条 SQLite UPSERT/RETURNING 分配；与 scheduling transaction 同 commit，严格递增且不会并发重复。

`enqueue_position != WorldEvent.ledger_position`。前者只排序待处理工作，后者是已经提交的 fictional history canonical 顺序。

## 3. Trigger、Activation 与 WorldEvent

```text
ScheduledSimulationTrigger = 未来某项工作何时到期
SimulationActivation       = 该工作已到期且可被后续系统消费
ActionProposal             = typed 来源请求某个动作发生
WorldEvent                 = fictional world 中已经被 Kernel 接受并提交的事实
```

**Activation != ActionProposal != WorldEvent**。计时器在 08:00 唤醒“考虑 character_a 的早晨活动”，不等于 character_a 已去 location_a，也不创建 WorldTruth、CharacterBelief、PlayerKnowledge、Observation 或 Relationship 变化。C-006B 的 ActionProposal 可选保存 source ActivationId 作为后续因果追踪，但 action 的存在、接受或拒绝均不会自动消费、完成或改写 Activation；消费政策仍属于后续 runtime 任务。

一个 one-shot trigger 的 materialization 在一个 `BEGIN IMMEDIATE` transaction 中完成：读取 deterministic due batch，通过 generalized activation repository 插入/合并 Activation 与 typed `SCHEDULED_TRIGGER` cause，并把 Trigger 从 PENDING 改为 FIRED。直接 `source_trigger_id` 仍保留首个历史 linkage，normalized cause history 保留所有合并来源。commit 前失败会整体 rollback，留下 PENDING 且无 Activation/cause；commit 后全部 durable；重试不重复来源。没有容易永久卡住的 RUNNING 状态。

Trigger 明确携带 activation target、ActivationKind/version、可选 coalescing key 与 attention。默认保持 C-006A 的 WORLD / `world_orchestration` v1 / non-coalescing 语义；Character schedule 必须显式使用 typed Character target 和 registry 支持的 kind。PLAYER 不是 target。

## 4. Application contract

应用服务提供 `schedule_trigger`、`cancel_trigger`、`get_trigger`、`peek_next`、`list_due`、`materialize_due` 和 `drain_due`。所有 ID 和错误有明确类型，ORM 对象不越过 adapter。

schedule 使用独立 `simulation_schedule_receipts` 记录 RequestId、canonical semantic fingerprint 和 TriggerId。精确重试返回原 Trigger；同 RequestId 的不同 world/ID/due/priority/kind/version/payload/correlation 明确 IdempotencyConflict。它不伪造 CommandReceipt 或 WorldEvent。

cancel 是幂等状态转换：PENDING→CANCELLED；再次取消返回同一结果；FIRED 返回 typed `TriggerAlreadyFiredError`，不会删除或否认已经存在的 Activation。cancel 与 materialize 由 SQLite writer transaction 排序，合法赢家只能是 CANCELLED+无 Activation，或 FIRED+恰好一个 Activation。

due 统一定义为 `due_at <= through_world_time`。drain 必须提供正整数 max_items，只读取 `max_items + 1` 判定 `more_due`，不会把全部 overdue queue 载入内存。C-006D 必须复用这一独立于 wall sleep 的 primitive，不建立第二套 catch-up scheduler。

## 5. Runtime wake、暂停与关闭

`SchedulerWakeSignal` 是 single-Core 的进程内控制优化，DB 始终是事实来源。以下变化会 set per-world Event 并重算：

- 新 trigger（包括更早 due）提交；
- trigger 取消；
- future clock mutation path 调用 `clock_changed(world_id)`；
- graceful shutdown。

C-006D 的 `WorldClockService` 统一实现 checkpoint、pause、resume、scale change：先按 monotonic elapsed re-anchor，再提交新 state/scale；成功后唤醒 scheduler。运行时不会为了发现 revision 每 100ms 轮询 SQLite。

startup 对每个 persisted world 先按固定 target 进行 bounded catch-up；READY/PAUSED 后才激活 normal tickless task。paused World drain `due_at <= logical anchor` 后等待 signal；running World 以精确 scale 推导近似 timeout。graceful shutdown 先停止外部 simulation mutation、join scheduler transaction，再 checkpoint effective WorldTime 并关闭 DB；未 fired trigger 保持 PENDING。

## 6. SQLite 并发与 schema

[0011_simulation_scheduler](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0011_simulation_scheduler.py) 新增：

| 表 | 责任 |
| --- | --- |
| `simulation_queue_cursors` | 每世界最后分配的 enqueue position |
| `simulation_scheduled_triggers` | durable one-shot queue、状态和安全 payload |
| `simulation_activations` | typed WORLD/CHARACTER work item；source trigger audit linkage、due/priority/enqueue 与可选 coalescing identity |
| `simulation_activation_causes` | normalized typed cause history；每 activation 稳定 position 与 bounded query |
| `simulation_schedule_receipts` | schedule RequestId fingerprint/result |

due query 使用 `(world_id,status,due_at,priority,enqueue_position)` 索引；另有 typed target、pending coalescing、cause identity 与 cause order 索引。SQLite WAL 下 `BEGIN IMMEDIATE` 先取得 writer 资格；唯一约束、状态事务和 source uniqueness 是正确性依据，asyncio Event/Lock 不是。设计不假装 SQLite 支持 PostgreSQL `FOR UPDATE`。

## 7. Observability 与边界

typed diagnostics 只允许 world ID、trigger kind、due WorldTime、WorldTime lag、batch size、activation count 和 scheduler state。`StructuredLogger.emit_scheduler` 没有 payload 参数；普通日志不使用 `repr(payload)`。测试植入 private payload canary 并验证日志中不存在。

测试覆盖精确/暂停/缩放时间、UTC rollback monotonic guard、排序和 10,000 queue sanity、世界隔离、schedule/cancel 幂等、due boundary、bounded drain、flush 后 commit 前 crash rollback、commit/retry uniqueness、双 drainer、cancel race、早期插入 wake、pause/resume/scale revision wake、graceful shutdown、无 LLM 及无世界知识/关系/事件副作用。未来 activation kind 可增加 `director_wakeup`、`character_wakeup`、`scheduled_activity_due` 或 `scene_deadline`，不修改 scheduler 排序；C-006A 不注册或实现这些行为。

## Director 日常工作源（2026-09-29）

既有单 World task 在 drain Trigger→Activation 后消费日常候选，并从队首与 Director 的下一候选/占用结束/window_end 取最早 deadline，继续既有 monotonic WorldTime→wall delay/wake。没有另一个世界轮询循环或每角色 task。模型 I/O 是最多两个有限规划 task；持久 claim 先于调用，失败/重启不重放。候选来自独立 typed plan，不伪装成已消费的其他 Activation；此前 Trigger materialization 行为不变。

恢复时从 durable plan/candidate/receipt 恢复：已经原子提交的 active 不再执行；未执行但已过 end 的候选 expire，仍有效者只在当前逻辑时间执行。当前不重建关闭期间已经错过的活动历史，不把“到期”当作发生事实。窗口结束才续批，不反复追补离线多个窗口。暂停/关闭按已批准方案抑制新工作。
