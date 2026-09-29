# 已观察事件接入聊天：复用调查与实现边界

2026-09-29，从干净 edc6736 接续。已有世界事件时间线与“聊聊这件事”，缺少具体描述和角色自己的事件输入。本轮补齐这两段，不重复创建话题入口。

## 调查与选择

- [Concordia README](https://raw.githubusercontent.com/google-deepmind/concordia/main/README.md)：当日 main 快照，未固定发行版；[Apache-2.0](https://raw.githubusercontent.com/google-deepmind/concordia/main/LICENSE)。agent / game master / engine 的职责分离、按观察构建角色输入具有参考价值。但其 LLM Game Master、simulation loop 与 associative memory/embedding 接入，会重复已有 Kernel、调度、持久化和受控模型网关；自然语言裁定结果也不能替代本项目的确定性提交。采用职责分离的模式，不安装或复制其运行时。
- [SillyTavern World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)：当日官方文档；release [AGPL-3.0](https://github.com/SillyTavern/SillyTavern/blob/release/LICENSE)。关键词激活和绑定的 lorebook 适用于已开放背景，本项目已有实现；运行世界中的亲历事件需要 owner 授权，不能把世界账本当成所有角色的公共 lorebook。不复制酒馆源码。
- 直接复用已有 SQLAlchemy / SQLite、Observation 历史授权、当前绑定 Player、角色上下文和普通聊天费用治理。成熟模拟框架不能替代项目特有的访问边界；新增的是少量受限查询与确定性中文模板，没有新依赖或另一套 agent runtime。

## 本轮契约

玩家事件列表仍只查询当前 World + 绑定 Player 自有 event-target Observation，最多100条，保留最早获知时间。具体详情额外要求同主体有 witnessed + event_occurrence 记录；仅有普通/旧 basis=NULL Observation 的事件仍只有原有通用标题。角色输入独立查询该角色的同世界亲历记录，最多12条，只加入回复，不加入群聊 selector。不会从玩家事件列表复制给角色。

只投影 PlayerMoved / PlayerPlaced / CharacterPlaced payload v1 的主体和地点 ID。SQL 在 owner 过滤后选择白名单标量，不材料化整个 payload；不输出 activity、availability、revision、activation、关系数值、信念、断言、私人背景或未知事件 body。错误/未知版本保留玩家通用标题，角色跳过无详情记录。名称查询只限该世界已授权事件引用的主体/地点，名称清理并截取160字符；当前名称是可读标签，不是历史名称快照。稳定来源仍为 event ID / ledger position / WorldTime。

详情是已授权观察的展示，不生成新的 KnowledgeAssertion、EpisodicMemory 或 WorldTruth。角色亲历记录作为 lower-trust USER data；不会授予系统指令权限，也不保证模型准确使用。用户发出的事件话题只是一条消息，接收方不会因此获得自动世界知识。无自动模型调用、事件重放或存档写入，没有新迁移。

## 尚未实现

Director 计划、候选消费、活动/相遇及主动联系没有在本轮实现。计划失效、窗口和重规划门槛仍需明确；不能用虚构事件填满时间线。现有正常 UI 尚不提供移动操作，初始放置也不生成亲历 Observation，所以已有存档没有这些记录时，时间线仍可能为空；验收只使用存档中确实存在的记录，不自动补历史授权。

按 AGENTS §20，仅源码审查、lint/type、编译、打包；测试、真实 API、应用运行、隔离与体验由用户验收。
