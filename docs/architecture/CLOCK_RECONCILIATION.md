# World Clock Reconciliation and Catch-up

状态：C-006D 已冻结 Stage 5 的 realtime/offline 时间语义。本文描述确定性时间基础设施；不实现 Director、Character cognition、Memory、LLM catch-up、叙事摘要、calendar 或 recurrence。

## 1. 三种时间

```text
WorldTime              = canonical fictional chronology
UTC                    = durable audit/offline bridge
process monotonic time = live-process elapsed-time authority
```

三者不可互换。`WorldTime` 仍是整数微秒逻辑坐标，不是 UTC 或 EventId；`time_scale` 仍是有限、非负 `Decimal`。进程内有效时间从一个固定 runtime base 计算：

```text
runtime_base_world_time
+ floor((monotonic_now_ns - monotonic_base_ns) * exact_scale / 1000)
```

每次读取都从同一个 base 计算，不累计上次取整结果，因此亚微秒余数不会在频繁读取中永久丢失。UTC 前跳、回退、NTP 或手工改时不改变存活进程的模拟速度。monotonic 值不持久化，也不能跨进程比较。

## 2. Durable anchor 与 clock mutation

持久化 `WorldClock` 已足够表达 crash-safe anchor：`logical_time`、`observed_wall_time_utc`、精确 scale、RUNNING/PAUSED 和 Revision。C-006D 无 schema migration。

`WorldClockService` 是 effective-time 和 re-anchor 的唯一 application authority。pause、resume、scale change 和 graceful checkpoint 都先从当前 monotonic base 计算有效 `WorldTime`，然后以 resource revision CAS 替换一个完整 anchor。旧 scale 只作用于 mutation 前的 elapsed；新 scale 从新 base 开始。paused elapsed 永不进入 `WorldTime`。

durable wall anchor 永不后退：

```text
new_wall_anchor = max(previous_wall_anchor, observed_utc)
```

这是异常恢复政策，不宣称 UTC 单调。clock checkpoint 不创建 `WorldEvent`；单纯时间流逝不是 fictional occurrence。

## 3. Startup offline bridge

每个世界启动时只捕获一次 startup UTC。RUNNING world 以持久化 anchor 计算：

```text
offline_elapsed = max(0, startup_utc - persisted_wall_anchor)
target = persisted_logical_time + floor(offline_elapsed_us * persisted_scale)
```

PAUSED world 的 target 始终为 persisted logical time；当前坐标已经 due 的 trigger 仍可 materialize。若 startup UTC 早于 durable anchor，advancement 为零、target 不后退、wall anchor 不回退，并报告 `WALL_CLOCK_REGRESSION`。没有 NTP、网络时间或补偿性虚构事件。

大幅正向 UTC gap 按实际正 elapsed 桥接，不静默 cap 或丢弃 fictional time。处理成本取决于 due trigger 数量，而不是 gap 中的秒、分钟或 Character 数。

计算 target 后，Core **先持久化 re-anchor，再 drain**。若此事务失败，catch-up 不开始。若提交后崩溃，target 已 durable，未处理 trigger 仍是 PENDING，下一次启动不会重复计时。

## 4. Fixed-target bounded catch-up

一次 pass 固定一个 target `T`，复用 C-006A 的 `drain_due(world, T, max_batch)`：

```text
durable re-anchor to T
→ CATCHING_UP
→ bounded batches ordered by (due_at, priority, enqueue_position)
→ cooperative async yield between non-final batches
→ authoritative re-query for newly committed due work <= T
→ fresh monotonic base at T
→ READY or PAUSED
```

不会逐 tick、逐秒、逐分钟、逐 Character 模拟。365 天且零 trigger 的 gap 是一次 clock reconciliation 和一次空 bounded query。大量 backlog 不全量加载。trigger materialization 继续使用相同 sparse activation、coalescing、WORLD aggregation、cause provenance 和原子 Trigger→FIRED 规则。

Stage 5 catch-up 只确定 **哪些 work 已到期**。它不执行 Character/Director cognition，也不编造“角色去了某地”等结果。`READY` 只表示所有 `due_at <= fixed target` 的 trigger 已 durable materialize/cancel；不表示未来 cognition backlog 已消费。

## 5. Temporal barrier 与 lifecycle

per-world operational state 是 `STARTING / CATCHING_UP / READY / PAUSED / DEGRADED / STOPPING`，不是 WorldTruth。CATCHING_UP 时，外部时序敏感 command/ActionResolution 通过 typed `WORLD_CATCHING_UP` 拒绝；只读 inspection 和 catch-up 自身的 clock/trigger/activation 写入仍允许。这样不会先提交 target-time 玩家动作，再补写更早 overdue work。

startup 逐世界处理，catch-up task ownership 有界；一个 world 失败只把该 world 标为 DEGRADED，其他 world 仍可到 READY/PAUSED。shutdown 在 batch 间可中断；已提交工作保留，未处理 trigger 保持 PENDING，不伪造 FIRED。READY/PAUSED world graceful shutdown 在 scheduler transaction 结束后 checkpoint 当前 effective time，再关闭 persistence。

运行期 `CreateWorld` 在 canonical transaction 成功提交后，经 application `WorldRuntimeRegistrar` port 加入同一 runtime。`register_world` 按 WorldId 串行且幂等，执行正常 startup reconciliation，再激活 tickless scheduler。若该后提交 lifecycle 步骤失败，World 与 `WorldCreated` event/receipt 仍保持 durable，runtime state 进入 DEGRADED；CreateWorld 结果不能被改报为回滚。精确重试不会重放 world/event，但会重新尝试尚未 READY/PAUSED 的 runtime 注册。

## 6. Crash semantics

- graceful shutdown：checkpoint logical/UTC anchor，下一次启动只桥接关闭后的 UTC gap；
- crash before checkpoint：旧 anchor 留存，下一次 UTC bridge 同时覆盖未 checkpoint 的前进和关闭期 downtime；
- crash after startup re-anchor but mid-drain：target 不重复累计，已 FIRED trigger/activation/cause 保留，剩余 PENDING 继续按同一顺序 drain；
- repeated startup without additional UTC elapsed：`WorldTime` 不再次前进；
- paused restart：无论 gap 多大都不前进。

## 7. Diagnostics and privacy

`CatchUpReport` 只包含 WorldId、from/target WorldTime、nonnegative UTC gap、batch/trigger/distinct-activation counts、typed anomaly flags、more_due/completed 和 monotonic runtime duration。日志接口不能接收 trigger payload、cause private content、prompt、conversation、credential 或 raw exception/SQL details。报告无需持久化。

## 8. Extension seam

未来 Director、Character runtime 和 Memory consolidation 可消费 durable activation，但不能改写 clock reconciliation。Activation 仍不自动完成；Stage 5 不因缺少 handler 把 pending cognition work 标为 done。

```text
Time
→ Trigger
→ Activation
→ future cognition
→ ActionProposal
→ deterministic Kernel
→ WorldEvent
→ Observation
→ future Knowledge/Memory
```
