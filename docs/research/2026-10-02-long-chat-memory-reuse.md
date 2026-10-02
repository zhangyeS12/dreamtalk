# 长期对话记忆复用调查

2026-10-02，基线bf9f367。用户要求优先交付长期记忆，不再延后到活动成果切片。

- [Mem0自定义提取](https://docs.mem0.ai/open-source/features/custom-instructions)：同类事实和偏好提取、无内容时空数组、按主体限定来源；[当日main许可](https://raw.githubusercontent.com/mem0ai/mem0/main/LICENSE)为Apache-2.0。默认独立提取/更新和embedding服务会增加模型调用与运行依赖；当前官方DeepSeek没有配置embedding服务。本轮不安装其整套运行时，沿用现有正常回复同次结构化提取和SQLAlchemy持久事务。
- [Letta记忆块](https://docs.letta.com/v1-sdk/memory/memory-blocks)：核心信息常驻、档案按需要取用；[当日main许可](https://raw.githubusercontent.com/letta-ai/letta/main/LICENSE)为Apache-2.0。完整Agent运行时会替换当前治理与角色职责，本轮借鉴核心/档案层次，不引入另一Agent循环。
- [SillyTavern摘要](https://docs.sillytavern.app/extensions/summarize/)和[聊天向量化](https://docs.sillytavern.app/extensions/chat-vectorization/)：有界摘要与旧原文召回；单独摘要/embedding可额外调用。AGPL代码不复制，格式行为参考。
- 实际复用已安装SQLAlchemy/Alembic、Pydantic/pydantic-core、SQLite FTS5/BM25、jieba0.42.1、原聊天claim/预算/同次JSON流和原生React dialog。没有新依赖/外部记忆服务/embedding模型。

本轮边界：独立应用层长期对话记忆，只证明在获准对话中说过，保存原句/说话者/会话/消息/时间。不是Observation-only EpisodicMemory的新provenance，不创建世界事实或私有Knowledge。正常回复自动提取最多4条重要身份/偏好/约定/经历；群聊可见来源进入固定成员各自隔离的记忆，私聊只进入对方。可停用、置顶、关闭自动记录；明确改变形成新记录并关联旧记忆。核心偏好常驻，相关档案以授权SQL候选后FTS5排序；不再只扫描近三页聊天。无额外提取API/历史后台付费回填，正常回复增加有限元数据用量。暂不声称同义语义向量检索、Reflection/合并遗忘或完整离线经历已经交付。

用户于2026-10-02明确授权历史原句随其发起的正常聊天外发：当前世界/当前玩家/该角色固定参与会话，最多4条、完整JSON合计8KiB，不后台批量外发、不增加API。旧聊天不需付费回填即可按关键词召回；SQL先授权后筛选最多200条命中且正文合计96KiB，再用既有FTS5排序。停用或被更新记忆的来源消息不参与此档案召回。长期条目另有16条/8KiB上限。非同义语义检索。


## 同轮活动生命周期与近期经历

用户要求生命周期和聊天参考近期经历一并完成。[Concordia当日main](https://github.com/google-deepmind/concordia)（Apache-2.0）复核了Agent提出行动、环境负责裁决和观察的成熟边界；[Temporal Workflow Execution](https://docs.temporal.io/workflow-execution)复核有限生命周期、持久事件与确定性恢复。两者整套运行时会引入另外的模型/服务与调度责任，本项目已经有Kernel事件账本、SQLite物理writer和每世界deadline调度；直接复用这些已有实现，不新增调度/Agent框架，也不复制上游代码。

新增Kernel内settle_routines：active候选在到期/位置revision变动/合法放置中断时一次事务写唯一终止事件及获准Observation，更新候选finished/cancelled；事件ID由candidate稳定派生。start引用必须存在，重复终止拒绝。终止不改CharacterState revision、位置、任务成果或世界知识。运行关闭Director的世界也保留已开始活动的结束deadline；PAUSED不推进，重启不付费重放。原PlaceCharacter在CAS通过后、放置事件前同事务终止旧活动。

Replay校验start链接、角色、活动、原地点、计划时刻、当前presence/revision和单次终止。获准白名单投影支持结束/中断；owner SQL过滤后才选本人6条近期移动/活动，6KiB完整prompt上限，主体与亲历时间不靠名字猜测。聊天仍是自然模型台词，只提供有依据情境，不声称自然语言零幻觉、任务成果、多人相遇或完整离线模拟。
