# 普通用户界面与事件知情边界

## 导航

普通用户界面使用聊天、通讯录、设置、我四个底部入口；开发者检查器仍为独立调试界面。聊天列表始终把“世界事件”置顶。点击后进入独立时间线，按 `WorldEvent.occurred_at` 和稳定 `ledger_position` 排序，显示最近 100 条当前玩家获知的事件。没有获知事件时显示空状态，不编造事件。

## 本地玩家身份

当前桌面/本地 Core 的 app-data 目录代表一个本地用户；该用户可在每个 World 选择一个已有 Player 作为“我”。`local_player_bindings` 是本地产品身份元数据，不是 canonical WorldEvent、Player Knowledge、事件回放输入或世界业务事实。绑定必须引用同一个 World 中已存在的 Player。世界中可以存在其他 Player；当前绑定不会删除或改写他们。多人身份认证和同一 World 的玩家数量仍由 P-19 后续定义，不能把当前本地会话规则推广为云端权限模型。

## “世界事件”读取

普通用户 HTTP 端点先以当前 World 的本地绑定 Player 过滤 `Observation`，只允许 `target_kind=event`，再关联真实 `WorldEvent`。没有绑定时结果为空；角色自己的 Observation、其他 Player 的 Observation、无 Observation 的后台事件都不能进入结果。重复观察同一事件只显示一条，获知时间取首次观察。返回值只含安全的中文展示标题、事件/获知世界时间及稳定排序信息；canonical payload、内部关系数值、其他主体的知识和开发者 Trace 均不返回。

当前安全标题仅对明确支持的事件类型作有限展示；未知类型使用通用标题，不根据内部 payload 猜测或生成剧情。后续要展示更丰富的可见事件叙述，必须建立经过审查的逐类型展示投影，仍按 Player 的知情范围授权。

当前选择器只能绑定**已经通过 canonical CreatePlayer 创建**的 Player。普通世界刚创建但尚无地点/Player 时，界面不会伪造默认地点、玩家或事件。

## 世界内容版本

用户已确认：同一份角色卡或世界书进入不同世界后，各世界保留自己确认过的版本。后续修改必须在目标世界再次预览确认才生效，不能传播到其他世界。世界专属内容副本仍是创作素材；引用与确认本身不授予 WorldTruth、CharacterBelief 或 PlayerKnowledge。
