# 上下文分配与本地中文语义检索复用调查

2026-10-03，基线2984c91，用户批准上下文与记忆优化。只修改现有Python/React/Tauri链，不引入另一套Agent框架。

| 来源 | 版本 / 许可 | 采用和取舍 |
| --- | --- | --- |
| [SillyTavern Prompt Manager](https://docs.sillytavern.app/usage/prompts/prompt-manager/)、[向量扩展](https://docs.sillytavern.app/extensions/chat-vectorization/) | 当日官方文档；项目AGPL-3.0 | 参考预留输出、完整近期对话与旧原句有界注入；不复制AGPL源码。复用本项目预算、权限、消息存储和检索接口。 |
| [FastEmbed](https://github.com/qdrant/fastembed/tree/v0.8.1) | 0.8.1 / Apache-2.0 | 直接使用内置中文ONNX模型与CPU推理；jieba/FTS只提供词面匹配，无法单独解决同义表达。当前授权需要本地语义检索，新增模型约95MB、ONNX/NumPy/tokenizer运行库及CPU开销。 |
| [BAAI模型](https://huggingface.co/BAAI/bge-small-zh-v1.5)、[Qdrant导出](https://huggingface.co/Qdrant/bge-small-zh-v1.5) | bge-small-zh-v1.5 / MIT，导出46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59 | 优先中文、FastEmbed原生支持、512维/512输入Token；避免自行实现模型或另加GPU/PyTorch。固定权重官方SHA256，文件随完整便携包，运行时local_files_only，不自动下载或外发文本。 |
| [SQLite FTS5](https://www.sqlite.org/fts5.html)、[RRF](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion) | SQLite公共领域；算法独立实现 | 保留jieba0.42.1/BM25。权限过滤后的独立语义候选与关键词候选合并，两种排名以k60融合；当前问题/前两句权重2/1/1。 |

语义候选不是整个历史：当前角色获准、未遗忘/未替换的最近256条长期记忆，以及获准会话最近256条旧原句；关键词仍可从更早历史筛出最多500条记忆/200条原句。两路分别保留正文空间；每次最多新增128个候选向量，显式聊天/搜索时逐步缓存，部分候选尚未编码会在面板说明。候选正文、向量缓存和并发有硬上限。记忆16条/8KiB、外发旧原句4条/8KiB不扩大。512 Token模型会截断较长候选的编码，不改动被引用的原文。语义相似度不是事实可信度；0.8是保守初始筛选值，未用真实用户对话校准。未引入付费embedding/裁判/逐句摘要API。

上下文分配保留规则、角色设定、玩家问题及当前完整回合、当前活动；按来源单元裁掉较低优先的旁支资料与较早完整回合。原句/公共背景先裁，稳定身份偏好约定和已确认摘要优先。所有调用仍由可信保守上界准入；不把估算当财务保证。无请求计数能力的提供商保留原有模型级预留，不假装删文本能降低固定预留。

“本次参考内容”保存生成前的有限诊断记录，不表示模型确实读懂，也不是账单；可见共同对话原句与记忆，私有活动/episodic知识不展示。0032只给执行记录增加可空列，旧0031形状检查保留。摘要沿用用户触发、增量原文、预览确认，不新增后台付费工作。

验证范围：源码、静态检查、编译、包内容/哈希核对。按AGENTS第20节不运行测试、应用或付费模型，实际召回质量和CPU耗时待用户体验。
