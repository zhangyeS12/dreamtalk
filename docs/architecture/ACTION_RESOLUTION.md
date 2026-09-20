# Deterministic Action Resolution

状态：C-006B 建立 Stage 5 的第一条正式行动结算路径。当前生产 action 只有 `move_player` v1；没有 LLM、Director、Character cognition、对话、Memory、战斗或任意脚本执行。

## 1. Kernel pipeline

```text
ActionProposal
→ authority validation
→ canonical-state/precondition validation
→ allowlisted deterministic resolver
→ ACCEPTED | REJECTED(reason)
→ one transaction:
   projection mutation + ordered WorldEvent(s)
   + event-time Observation snapshot(s)
   + explicit bounded activation/cause work + RequestId receipt
→ commit
```

`ActionProposal != WorldEvent`。Proposal 只表示某个来源希望动作发生；只有 Kernel 接受并完成事务后，WorldEvent 才表示已发生的世界事实。普通拒绝保存 typed result/receipt 以支持幂等，但不产生 projection mutation、WorldEvent、Observation、KnowledgeAssertion 或 Memory。

## 2. Typed contract and registry

`ActionProposal` 包含 WorldId、ActionKind、schema version、typed Proposer、独立 Actor、typed payload，以及可选 SceneId、ActivationId、causation/correlation。payload 不是任意可变 dict。`ActionKindRegistry` 只按显式 `(ActionKind, version)` allowlist 分派；未知版本返回 `REJECTED:unsupported_action`。

持久化 payload 不能选择 callable、module path、SQL、JSON Patch 或 import。相同 proposal、canonical state、revision 和配置产生相同语义结果；UUID 只标识已提交记录，不参与行为选择。

## 3. Authority and agency

`proposer != actor`：Proposer 是请求来源，Actor 是虚构世界中执行动作的主体。

| Proposer | 当前权限 |
| --- | --- |
| PLAYER_INPUT | 只能为与 proposer identity 相同的 Player 提案 |
| CHARACTER_RUNTIME | 保留给未来角色运行时，只能控制自身 Character；C-006B 不实现角色动作 |
| SYSTEM | 不能创作有意义的 Player 选择或冒充角色 |
| DIRECTOR | 仅保留身份边界，不能替 Player/Character 做决定；C-006B 不实现 Director |

payload 中出现 ActorId 不会自动授予权限。角色运行时、System 或 Director 试图移动 Player，以及一个 Character 冒充另一个 Character，均得到 `unauthorized_actor`，没有 canonical 副作用。

## 4. Production proof: move_player v1

生产 proof action 与既有 MovePlayer command 共用 [player_movement.py](../../services/core/src/livingworld/application/player_movement.py) 的 `PlayerPresence.at_location` transition、canonical payload builder 和 Scene-aware CAS apply；没有第二套移动规则。输入包含 destination LocationId 与 expected Presence Revision。resolver 检查 actor/proposer 权限、Player/Presence、同世界目的地、revision，以及可选 Scene 的 OPEN/active membership/physical location 条件。

成功生成现有 `PlayerMoved` v1，CAS 更新唯一 PlayerPresence，并在离开 Scene.Location 时原子结束 active membership。现有 `MovePlayer` command 与 `PlaceCharacter` movement path 也调用同一个 Scene membership 退出能力，不能留下 zombie participant。

移动事件采用显式 occurrence context：`ACTOR_ONLY ∪ origin LOCATION_PRESENT(pre-transition) ∪ destination LOCATION_PRESENT(pre-transition)`。Actor 总是显式包含；目的地中已有的主体可见，移动主体不依赖查询后的状态获得自己动作。当前没有视线、距离、遮挡或听觉模拟。

## 5. Results, failures, idempotency

普通拒绝 reason 是小型稳定 taxonomy：`unauthorized_actor`、`invalid_scene`、`not_present`、`precondition_failed`、`invalid_destination`、`conflict`、`unsupported_action`、`wake_fanout_too_large`。wake fanout 在任何 canonical mutation 前 bounded resolve；超过上限时保存 typed rejection，不做随机截断。DB/CAS/serialization 故障仍是 infrastructure failure，不伪装成虚构失败。

semantic fingerprint 在默认值解析后的 typed proposal 上计算，不含 RequestId 或 wall time。精确 RequestId 重试返回原 ACCEPTED/REJECTED result；不同语义冲突。accepted result 保留原 event IDs/revision，不重复事件、移动或感知。receipt 的 versioned result payload 只保存 typed status/reason/event IDs/revision，不保存原始 action payload。

CAS 使用 world + resource identity + expected revision。结算后状态变化不会被静默覆盖，也不会自动重新解析并改变虚构结果。SQLite `BEGIN IMMEDIATE` 只提供物理 writer 排序，resource CAS/唯一约束仍是正确性依据。

## 6. Privacy and scope

Action service 不记录 payload；事件只保存该 event type 所需的 canonical movement facts。receipt 只保存 SHA-256 fingerprint 和 bounded typed result。日志、Scene 元数据、scheduler diagnostics、receipt 中没有 dialogue、prompt、knowledge、credential 或 rejected raw payload。

ActionProposal 可引用 source ActivationId；accepted action 将该 typed ID 作为 WorldEvent 的安全 provenance 字段保存，供未来 causation tracing，但 C-006B 不消费、完成或改写 Activation。`Activation != ActionProposal != WorldEvent`；消费政策留给后续 Stage 5 runtime 任务。

## 7. C-006C wake integration

`move_player` 只有在 proposal 显式引用 Actor 当前所属 OPEN Scene 时，才使用 `SCENE_CHARACTER_PARTICIPANTS` wake；普通移动保持 `NONE`。Scene wake 只选择发生时仍 active 的 Character members，排除 Player、历史成员和同地点非成员。perception audience 仍按 C-006B 完整计算，activation fanout 不改变 Observation history。

accepted action 先解析 bounded wake targets，再在同一 UoW 中写 projection、WorldEvent、Observations、activation causes 和 receipt。Character event activation 会验证该 Character 已有同事务内的 EVENT_OCCURRENCE Observation。commit 前任何 activation/cause DB failure 会把 mutation、event、Observation、activation/cause 与 receipt 一起回滚；commit 后全部 durable。Activation 不创建知识或 Memory。详见 [Sparse Activation](SPARSE_ACTIVATION.md)。
