# 活动回答与自身身份对应：复用调查

2026-10-01，从9aa765d接续；用户要求继续且“回答需要对应角色自身活动”。源码核对发现：已有自身阶段快照，但亲历事件只有描述、时间和出处，未区分行动主体与目击者；直接聊天persona缺少稳定角色ID，改名/同名更容易混淆。回复完整性校验不是所有自然语言事实的证明。

## 成熟实现调查

- [Concordia observation组件](https://raw.githubusercontent.com/google-deepmind/concordia/main/concordia/components/agent/observation.py)、[仓库说明及许可](https://github.com/google-deepmind/concordia)：当日main快照，非固定发行版本；Apache-2.0。其按实体维护并在行动前检索标记Observation的组件分工可复用为模式；引入其memory、embedder、GM或engine会重复当前Kernel/观察持久化/受控网关。本轮沿用当前角色绑定reader，不复制其代码或引入运行时。
- [NVIDIA NeMo Guardrails事实核对文档](https://docs.nvidia.com/nemo/guardrails/configure-guardrails/guardrail-catalog/fact-checking)、[源码许可](https://raw.githubusercontent.com/NVIDIA/NeMo-Guardrails/develop/LICENSE)：当日文档/develop快照，非固定发行版本；Apache-2.0。Self-check通过证据与回复进行模型判定，效果仍依赖模型；AlignScore等是额外检测模型。可作为未来语义核对组件候选，但会引入额外推理/模型用量、等待和对台词表达的误判边界。本轮不另造关键词拦截器，也不引入未明确范围的额外裁判调用。
- 直接复用当前SQLAlchemy授权投影、领域PrincipalId/RoutineActivity、时间快照、私聊/群聊上下文和费用/stream治理。增加主体元数据与枚举对应检查，共用生成约束；不新建Agent框架、事实数据库或第二套解析器。

## 实现与限制

KnownWorldEvent追加默认None的内部subject；仅在原白名单版本、实际授权witnessed/event_occurrence、引用和描述均可用时，投影可信PrincipalId。subject跨World会拒绝进入角色资料；actor仅在typed subject等于当前Character时成立。普通玩家HTTP明确返回既有字段，不序列化整个dataclass。

CharacterActivitySnapshot追加默认None的RoutineActivity；最新已提交的自身开始在原SQL标量白名单同时提取activity，应用再次核对subject等于owner与合法enum。speaker与actor ID一起进入最多2KiB资料，观察主体信息一起计入8KiB。旧schema无需迁移；没有未来计划、他人私有状态、自动记忆或知识写入。

统一ACTIVITY_GROUNDING_INSTRUCTIONS供私聊/群聊共用；近况以自身事实为依据，目击者不能扮作行动主体，角色卡/公共背景/聊天说法不是实际活动替代品。不要求把所有聊天写成事实清单，允许人格、情绪和想法自然表达；不替换或按关键词过滤模型台词。

没有接入语义输出裁判，不把输入身份检查称为所有台词都已事实校验。保留原流式和自然文本协议，所有供应商走原网关，新增资料纳入正常Token预算；没有额外模型任务。本轮只做静态与构建/文件核对，真实台词/并发/隔离由用户验收。
