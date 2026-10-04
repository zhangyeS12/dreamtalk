# 相遇节奏与持续同场去重：复用调查（2026-10-04）

用户接受了每批1～2次普通相遇、每角色24小时最多新增一位见面对象、持续同场不反复问候及熟悉阶段不能自动升级的建议。本轮落实为可选0～2次、滚动24小时WorldTime、同场段去重；沿用已批准的六小时pair冷却。没有固定概率实验，限额不是实测概率或必定相遇承诺。

## 已核对的成熟实现

| 项目/版本或查询时点 | 一手资料与发现 | 许可、采用边界 |
| --- | --- | --- |
| Generative Agents，main，2026-10-04查询，未声明固定commit | [plan.py](https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/cognitive_modules/plan.py)在决定交谈前排除休息/等待/已交谈状态并检查对方的chatting_with_buffer；[scratch.py](https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/memory_structures/scratch.py)保存缓冲状态。[perceive.py](https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/cognitive_modules/perceive.py)只将近期事件集合里未出现的三元组加入记忆。缓冲数值是模拟步数，不解释为现实分钟。 | [Apache-2.0](https://github.com/joonspk-research/generative_agents/blob/main/LICENSE)。采用本地先验冷却和感知去重思路；不复制代码、不接入它的额外交谈/总结/重要性/embedding调用或私密历史输入。 |
| Mesa 3.5.1；stable事件教程查询于2026-10-04 | [3.5.1 activation教程](https://mesa.readthedocs.io/v3.5.1/tutorials/2_agent_activation.html)说明激活顺序；[stable事件调度教程](https://mesa.readthedocs.io/stable/tutorials/3_event_scheduling.html)提供到时的一次性事件与可取消调度。stable页面不声称固定属于3.5.1。 | [Apache-2.0](https://github.com/mesa/mesa/blob/v3.5.1/LICENSE)。现有scheduler、TemporalMutationBarrier、Kernel单写事务已有这些能力，直接复用，不增加第二套agent框架或运行时。 |

## 采用的最小改动

- Director schema与提示均可选最多2次；0次有效，不强制凑满。Kernel也检查当前plan已成功执行数，因此旧版本持久化的8候选计划同样不会继续超过新上限；已经提交的旧事实不撤销。
- 每个角色滚动24小时WorldTime内最多一个首次实际记录的见面对象。双方都受限；任意一方已用掉新对象额度，整次候选取消。同一对曾成功问候的重逢不花新增对象额度，但仍受同场去重、六小时冷却及每批2次约束。这限制的是运行时新记录的对象，不把世界书已有亲缘/同事设定抹成陌生人。
- 复用director_encounters中finished记录、现有pair索引和world_events不可变ledger_position。上一次实际碰面的账本位置之后，一方出现CharacterPlaced或CharacterRoutineStarted且location_id确实不同，才表示两人曾分开；同地换活动/revision变化不算。用账本顺序可区分同一WorldTime内离开再回来，不用UTC或消息时间冒充世界时间。
- 最新相遇账本锚点不可用时拒绝再次问候，不猜分离。JSON字段在SQL内安全提取，只向调用者返回固定原因；不加载原始账本正文或其他人的记忆给Director。已有位置/活动/授权核验、单写事务与幂等回执仍负责最终事实准入。
- 每批是plan_id对应的已接受计划；提前或手动重新规划产生新批次，不宣称这是全世界滚动六小时总额度。每日新增对象及同对冷却不因重启、切换批次或关闭再开启重置。
- 已授权聊天观察增加brief_greeting与relationship_effect=none，明确只证明短暂问候。角色名用于定位记录，不证明交换姓名；亲缘/熟识若有独立授权依据则保留。未提供正式介绍/共同经历证据，不升级关系。不增加关系字段、新事实类型、后台自然语言裁判或自动Observation→EpisodicMemory。

限额属于本项目经用户接受的产品策略，并非上游提供的概率数值。执行取消不自动调用模型补选，不进入日常半批失效门槛。真实工作/休息/移动变更仍沿原记录路径保留，本次只去重普通问候，未承诺不再产生其他日常见闻。

无新增依赖、表、Alembic迁移或CharactersMet v1格式；保留0033与既有UUID/幂等身份。历史账本重放只复核原事实契约，不用新准入策略追溯否认旧合法事实。只做源码/静态/编译/字节核对；实际SQL运行、连续同场、重启与模型表达均待用户验收，不读取现有存档或代发API。
