# 共同经历与原文溯源复用调查（2026-10-04）

## 共同活动的生命周期

- [Generative Agents plan.py](https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/cognitive_modules/plan.py)：main查询2026-10-04，未固定commit；_chat_react生成对话及摘要，再为两名角色设置交谈对象、时长和结束时间。[许可Apache-2.0](https://github.com/joonspk-research/generative_agents/blob/main/LICENSE)。采用双方共享时段与状态的思路；不复制它的额外对话/总结模型调用，也不用模型摘要证明Kernel成果。
- [SimPy4.1.1 process interaction](https://simpy.readthedocs.io/en/4.1.1/topical_guides/process_interaction.html)：等待多个过程和显式中断。[项目维护者PyPI信息确认MIT](https://pypi.org/project/simpy/4.1.1/)。已有WorldTime、scheduler和持久候选可覆盖等待/终止，不引入另一时间引擎。
- [transitions](https://github.com/pytransitions/transitions)：master查询2026-10-04，[version.py](https://github.com/pytransitions/transitions/blob/master/transitions/version.py)声明0.9.4，仓库为MIT；条件状态转移、回调及并行状态适合长生命周期。这里只需有限pending/active/terminal，已有Kernel单写事务、同意revision、回执更适合真实持久准入，不安装通用状态机，不以回调绕过事务。

具体首版写入[用户本轮已批准的方案](../proposals/2026-10-04-shared-activities.md)：已经真实碰面两人共同休息/自由活动，明确开始/结束/中断，社交机会合计每批2次、每角色每日一次共同活动、不自动关系推进，正常模型批次外无额外调用。购物/委托的资源和成果契约尚缺，不假装同地等于一起完成任务。

## 已有记忆和聊天获知的原文溯源

[Zulip官方消息链接说明](https://zulip.com/help/link-to-a-message-or-conversation)用稳定消息身份链接具体原话及所在上下文。[仓库main许可Apache-2.0](https://github.com/zulip/zulip/blob/main/LICENSE)，文档查询2026-10-04；这里只采用消息身份定位的体验，不移入Zulip代码/服务或复制原文。引用来源可核对前后文，而不是只有归纳或内部UUID。

DreamTalk已有稳定MessageId、原会话/原文quote、私聊/群聊玩家权限检查和有界消息分页；直接复用这些组件，补按消息ID定位邻近上下文的只读能力，不重新搜索全文或构建第二个索引。沿用React dialog、ChatMessageBody与MessageTime。来源只在用户显式打开时本地读取，不发模型、不生成摘要、不移动角色，不改变关系或将聊天断言变成WorldTruth。无需表/迁移/额外依赖。

用户本轮已明确批准上述共同活动，已按具体契约接入现有Kernel；原文溯源处于已有聊天/记忆体验范围。共同休闲需要0034新增两张表，原文回看本身不新增存储结构。不运行自动测试、应用/GUI/推理或付费调用；原文读取只实现在代码中，不读取用户存档来验收。
