# 活动经历状态召回与共同委托调查（2026-10-04）

## 已确认问题与本轮范围

0.1.27的观察检索在当前角色已授权的近128条事件中排名，提供最近8条和最多4条相关旧经历。开始和结束/中断是独立事件，排名可只选入较早开始，或者让同一次活动重复占名额。自身最新活动快照已经检查实际终态，本轮完善历史经历检索；没有把这个静态发现称为用户遇到过的已证实运行故障。

## 成熟方案与选择

| 调查对象/版本 | 一手证据与许可 | 适合复用的能力 | 本轮选择 |
| --- | --- | --- | --- |
| LangChain ParentDocumentRetriever；master，查询2026-10-04，未固定commit | [源码](https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain_classic/retrievers/parent_document_retriever.py)、[MIT许可](https://github.com/langchain-ai/langchain/blob/master/LICENSE) | 稳定父子ID把命中的片段关联到同一源资料，避免断开上下文 | 采用来源关联思路，直接复用现有jieba/FTS5多查询排名与SQL授权投影，不另写检索器、不引入其VectorStore/DocStore。这里需要有界世界事件最新阶段而非取整个父文档；添加完整框架仍需自写权限/生命周期适配，维护成本更高。未复制第三方源码。 |
| ink 1.2.1 | [发行页](https://github.com/inkle/ink/releases)、[主仓库/许可MIT](https://github.com/inkle/ink) | 分支叙事、选择及故事状态存取 | 适合未来用户编写支线，不能替代Kernel证明物品/任务成果；此轮不集成叙事运行时。 |
| Yarn Spinner；3.x官方文档，仓库main查询2026-10-04，未固定commit | [Dialogue Runner](https://docs.yarnspinner.dev/components/dialogue-runner)、[状态单一来源建议](https://www.yarnspinner.dev/docs/faq/)、[MIT许可](https://github.com/YarnSpinnerTool/YarnSpinner/blob/main/LICENSE.md) | 台词、命令和变量存储分离，应用掌握实际状态 | 继续用角色生成台词、Kernel写事实，不创建第二份任务真值。未安装.NET/Unity组件。 |
| SpiffWorkflow 3.0.0文档；许可主仓库main | [执行/等待/人工任务](https://spiff.works/docs/spiffworkflow/bpmn/workflows)、[LGPL-3.0许可](https://github.com/sartography/SpiffWorkflow/blob/main/COPYING) | 明确等待条件、可执行步骤及完成状态 | 共同委托应参考事实驱动步骤。现有WorldTime、候选、单写事务、回执足以处理首版，不引入BPMN引擎/脚本执行或另一调度器。 |

LangChain参考页本次返回不支持的text/markdown，随后读取同项目源码；旧Spiff文档地址不可访问，改读项目自己的3.0.0文档。没有据失败页面推断行为。以上是源代码/文档查询，不是安装、运行或效果基准。

## 本轮具体实现

SQL仍先按世界、Character owner和event_occurrence witnessed过滤。只从v1已知日常/共同活动终态投影start_event_id这一标量，内部KnownWorldEvent增加可选关联字段，普通HTTP DTO不新增字段。原事实、回执、观察和迁移保持。

在这次最多128条已获准投影内，匹配稳定来源ID、同世界/同事件族、本人或双方身份、世界时间与账本顺序；唯一终态和开始可作为一组。本地排名文本可同时含两阶段描述，提供给模型的仍仅是实际终态投影及其实际event_id/时间，不伪造合成事件。原始历史不删除、不覆盖，不按名字或模糊时间猜活动关联。

两阶段只占一个选择名额，为其他经历留下空间。缺少来源、未见开始、主体错位、多终态冲突都保持独立；只知道开始的旁观者不能读取不获准的结束。不额外按ID查全局账本/候选或跨128窗口补终态。近128的界限意味着更远或当事角色未观察到的变化仍无法证明。

最近8个名额和最多4条旧话题候选、最终最多12条/8KiB保持；不足可由其他近期记录填齐。无关键词/检索器时同一128条权限窗口做只读状态去重并返回最多12条。自身当前快照/6KiB、长期记忆/历史原句边界、当前模型/预算/用量结算保持；没有额外API或新的历史外发类别。

## 下一步共同委托需要的具体决定

当前只有日常、短暂问候和共同休闲。共同工作时段结束仍不能证明调查发现、购物付款或委托成功。成熟叙事/工作流组件没有替DreamTalk定义这些事实；必须先选可核验目标、失败/中断与成果类型，再接入既有Kernel。

推荐从明确的两角色共同巡查行程开始：已有地点的往返和实际协作时段可由canonical账本核验；只记行程阶段，不能编造“环境已安全”或物品/报酬。若产品需要战斗、交付物、支付或玩家加入，则先定义相关实体和动作。属于AGENTS第22/24/26节尚未批准的新动作/持久化契约，本轮只调查记录，没有偷偷把共同休闲改成任务成功。

## 验证边界

本轮只允许源码/lint/type/AST声明和必要build-only打包；没有自动测试、应用/GUI/Core运行、数据库升级、真实存档/密钥访问、模型推理或付费API。真实聊天表达、过去经历命中和旁观者边界由用户验收。
