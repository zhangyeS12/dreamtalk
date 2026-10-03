# 角色经历召回复用调查（2026-10-03）

本轮开始前查阅官方研究与代码，解决已有亲历事件只按最近12条进入聊天的问题。真正的相遇动作还需要单独确认，不把已有目击记录改成社交事实。

| 来源 | 当前核对范围与许可证 | 采用方式 |
| --- | --- | --- |
| [Generative Agents检索实现](https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/cognitive_modules/retrieve.py)及[许可证](https://github.com/joonspk-research/generative_agents/blob/main/LICENSE) | 2026-10-03查阅main；Apache-2.0；没有作为依赖或复制源码，不以main代指固定发布版 | 借鉴按关注话题检索事件并兼顾近期记录的组织方式，不照搬全量记忆遍历、远程embedding和重要性评分 |
| [Generative Agents论文](https://arxiv.org/abs/2304.03442) | 2023原论文；架构参考，不引入论文/仓库素材 | 区分经历来源、检索和后续表达；不会因为模型叙述就创建真实相遇或关系 |
| [SQLite JSON标量](https://www.sqlite.org/json1.html)及[查询规划](https://www.sqlite.org/queryplanner.html) | 官方文档，2026-10-03核对；使用既有运行时，没有新增数据库依赖 | 保留现有owner-first SQL与JSON白名单投影，不读取全局事件正文再过滤 |
| 本项目Fts5ChatRecallRanker | 已有jieba0.42.1（MIT）与SQLite FTS5；[jieba许可证](../licenses/jieba-0.42.1.txt) | 直接复用分词、停用词、安全MATCH字符串、BM25、多问题RRF和有界线程槽；与聊天回忆共用同一个实例 |

不引入另一个Agent/RAG框架：它不能替代本项目Kernel、观察权限和时间语义，而且当前缺口是已有数据的选择。无新供应商、embedding、联网、后台摘要或模型裁判调用。费用仍是一次正常聊天的输入/输出，最多12条/8KiB；同类条目选择改变，实际Token随内容变化。

读流程：先同世界、owner、witnessed/event_occurrence限定，投影最多最近128条支持的真实事件；仅规范描述进入本地临时FTS语料，至多256KiB。当前问题权重2、前两句各1。保留最近8条，再补最多4条较早相关项；不足用近期补足、按EventId去重、最后按世界时间呈现。小limit按比例保留近期，生产仍为12。数据库会按既有索引/查询执行，128是返回候选数量上界，不声称SQL只扫描128行。FTS任务前释放数据库会话。

检索提示保留发生时间、获知时间、主体与actor/witness身份；不读其他角色当前状态、私人记忆、未来计划或隐藏世界书。自己的活动快照仍靠近当前问题，不让旧命中覆盖近况。仅已有观察可作为亲历，群聊不是同场；未检索到不能证明没发生。

当前局限：只在近128条已授权事件内作词法召回，不能保证同义改写、准确自然语言日期过滤或全部远历史。没有自动Observation→EpisodicMemory、共同剧情、任务成果、关系推进；新相遇消费者见[待确认方案](../proposals/2026-10-03-character-encounters.md)。本轮静态检查与编译不等于模型效果验收。
