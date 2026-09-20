# Simulation Fidelity Tiers

状态：C-006C 定义并实现 Character activation 的当前 operational fidelity 推导。Fidelity 是执行规划上下文，不是 WorldTruth、角色能力、剧情重要性或队列 priority；C-006C 不按 tier 调用 LLM。

## 1. Tiers

| tier | 当前判定 | 后续政策意图（尚未实现） |
| --- | --- | --- |
| `DORMANT` | Character 没有当前 CharacterState/physical placement | 无 autonomous cognition baseline |
| `BACKGROUND` | 已放置，但没有 active Scene，也没有受信 ACTIVE attention | 优先粗粒度、确定性处理 |
| `ACTIVE` | 已放置且 pending activation 带受信 ACTIVE attention，但不在 active Scene | 可参与 offscreen cognition |
| `SCENE_ACTIVE` | 是 OPEN Scene 的 active Character participant，Scene 中没有 active Player participant | 可参与互动场景 cognition |
| `PLAYER_FACING` | 是 OPEN Scene 的 active Character participant，且同一 Scene 有 active Player participant | 最高互动 fidelity 与 latency sensitivity |

PLAYER_FACING 必须共享实际 active Scene。与 Player 处于相同 Location、曾参与同一 Scene、拥有 Player 的 Observation 或仅有高 priority 都不满足。

## 2. Current state is authoritative

Fidelity 不在 activation 创建时冻结。selection 在一个有效 canonical DB snapshot 内查询当前 CharacterState、OPEN Scene active membership 和同 Scene Player membership：

- activation 创建时 BACKGROUND，Player 随后加入同 Scene，选择时为 PLAYER_FACING；
- activation 创建时 PLAYER_FACING，Player 在处理前离开，选择时降为 SCENE_ACTIVE；
- Character 在 Scene 结束或离开后按当前 placement/attention 降级；
- WORLD target 返回 `fidelity = None`，不会伪装成 Character。

并发 Scene join/leave 可按事务排序看到前态或后态，但不会组合出“Player 不在 Scene 却只因半读状态得到 PLAYER_FACING”的不可能快照。

## 3. Fidelity 与 priority 永久分离

队列 priority 只控制持久化 work ordering：

```text
HIGH=-1, NORMAL=0, LOW=1
```

Fidelity 描述当前交互上下文。BACKGROUND work 可以比 PLAYER_FACING work 更早 due 或 priority 更高；selection 仍按 `(due_at, priority, enqueue_position)` 排序，并在返回 candidate 时另行附上 fidelity。没有隐藏的 `PLAYER_FACING => priority 0` 规则。

低 fidelity 也不放宽 Kernel legality。未来 tier 只能影响 intent 如何生成、允许使用多少 cognition/context；同一动作仍必须通过相同 authority、precondition、CAS 和 canonical event rules。

## 4. Explicit ACTIVE promotion seam

`promote_character_active` 是受信 application seam。调用方必须提供同世界 CharacterId、source RequestId、due WorldTime 和显式 priority。它创建/合并一条 `CHARACTER_REACTION` activation，保存 `EXPLICIT_SYSTEM` cause，并把 attention 提升为 ACTIVE；相同 source identity 可安全重试。

该 seam 有以下边界：

- 只影响 bounded targeted work，不设置永久 Character flag；
- 不扫描 world，不创建 Character task；
- 不设置 PLAYER_FACING；Scene canonical state始终覆盖 attention 得到更高或更低的当前 tier；
- 不创建 Action、WorldEvent、Knowledge、Memory、对话或 LLM 调用；
- cause history 提供审计，不保存私密 payload。
