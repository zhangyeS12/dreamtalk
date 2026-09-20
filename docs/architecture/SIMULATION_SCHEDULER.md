# Durable Tickless Simulation Scheduler

状态：C-006A 已建立 Stage 5 的确定性时间调度与 durable activation 基础。本文只定义 **何时工作到期**；没有 Director、Character Agent、场景结算、知识传播、关系变化、对话、Memory、LLM 调用或离线 catch-up 策略。

## 1. 三种时间

三种时间不可互换：

| 时间 | 责任 |
| --- | --- |
| `WorldTime` | 世界逻辑坐标；世界 epoch 起的有符号整数微秒，是调度和 due 判断的 canonical 时间 |
| aware UTC | `WorldClock` 持久化锚点和创建/触发/取消审计时间；不是单调时钟 |
| runtime monotonic time | 当前 Core 进程内的安全经过时间和 sleep 决策；不持久化，不是世界事实 |

`WorldClock.effective_time(at_utc)` 是无副作用的精确计算：paused 或 scale=0 返回 logical anchor；running 返回 `anchor + floor(max(0, UTC elapsed microseconds) × Decimal scale)`。不使用 float 计算 canonical WorldTime。UTC 回退不会让结果早于持久化 anchor。

`EffectiveWorldTimeSource` 第一次读取或 clock revision 变化时用 aware UTC 建立进程内读数，之后以 monotonic nanoseconds 和同一 Decimal scale 推进，并保证同 revision 的普通读取不后退。显式 clock revision/anchor 变化可以建立新锚点；这不是用 runtime guard 改写历史。

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

**Activation != ActionProposal != WorldEvent**。计时器在 08:00 唤醒“考虑 Billy 的早晨活动”，不等于 Billy 已去咖啡店，也不创建 WorldTruth、CharacterBelief、PlayerKnowledge、Observation 或 Relationship 变化。C-006B 的 ActionProposal 可选保存 source ActivationId 作为后续因果追踪，但 action 的存在、接受或拒绝均不会自动消费、完成或改写 Activation；消费政策仍属于后续 runtime 任务。

一个 one-shot trigger 的 materialization 在一个 `BEGIN IMMEDIATE` transaction 中完成：读取 deterministic due batch，插入唯一 source_trigger_id 的 Activation，并把 Trigger 从 PENDING 改为 FIRED。commit 前失败会整体 rollback，留下 PENDING 且无 Activation；commit 后两者都 durable；重试不产生第二个 Activation。没有容易永久卡住的 RUNNING 状态。

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

当前尚无 Stage-5 clock mutation command；C-006A 暴露并测试了明确 hook，未来 pause/resume/scale/anchor command 在成功 commit 后必须调用它。运行时不会为了发现 revision 每 100ms 轮询 SQLite。

paused World 先 drain 已经 `due_at <= logical anchor` 的工作，然后等待 signal，不 busy-loop。running World 以精确 scale 推导近似 timeout；任何 timeout/signal 后都重读 clock 和 queue。Core composition 持有 runtime manager 并在关闭数据库前 `aclose()`；未 fired trigger 保持 PENDING。世界 session/scheduling action 显式激活 world task，避免把全部持久化世界误当作当前 active world；完整 closed-app progression policy 留给 C-006D。

## 6. SQLite 并发与 schema

[0011_simulation_scheduler](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0011_simulation_scheduler.py) 新增：

| 表 | 责任 |
| --- | --- |
| `simulation_queue_cursors` | 每世界最后分配的 enqueue position |
| `simulation_scheduled_triggers` | durable one-shot queue、状态和安全 payload |
| `simulation_activations` | 到期 work item；`(world_id, source_trigger_id)` UNIQUE |
| `simulation_schedule_receipts` | schedule RequestId fingerprint/result |

due query 使用 `(world_id,status,due_at,priority,enqueue_position)` 索引。SQLite WAL 下 `BEGIN IMMEDIATE` 先取得 writer 资格；唯一约束、状态事务和 source uniqueness 是正确性依据，asyncio Event/Lock 不是。设计不假装 SQLite 支持 PostgreSQL `FOR UPDATE`。

## 7. Observability 与边界

typed diagnostics 只允许 world ID、trigger kind、due WorldTime、WorldTime lag、batch size、activation count 和 scheduler state。`StructuredLogger.emit_scheduler` 没有 payload 参数；普通日志不使用 `repr(payload)`。测试植入 private payload canary 并验证日志中不存在。

测试覆盖精确/暂停/缩放时间、UTC rollback monotonic guard、排序和 10,000 queue sanity、世界隔离、schedule/cancel 幂等、due boundary、bounded drain、flush 后 commit 前 crash rollback、commit/retry uniqueness、双 drainer、cancel race、早期插入 wake、pause/resume/scale revision wake、graceful shutdown、无 LLM 及无世界知识/关系/事件副作用。未来 activation kind 可增加 `director_wakeup`、`character_wakeup`、`scheduled_activity_due` 或 `scene_deadline`，不修改 scheduler 排序；C-006A 不注册或实现这些行为。
