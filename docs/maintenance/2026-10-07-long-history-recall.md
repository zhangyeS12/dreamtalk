# 2026-10-07 长历史检索与聊天页面维护

本文件保留该维护／构建阶段的历史现场；其中“未提交／发布”指当时状态。后续0.1.40源码同步与外部导入验收见[记录](2026-10-07-github-source-sync.md)。

基线4d280cc，分支codex/world-archive，本轮未提交/推送/发布。用户在比较OpenAI与SillyTavern之后明确“批准”三项改进：持久全文索引、较早授权历史参与语义检索、聊天页面加载/渲染有界。保留原架构、知识与费用边界，继续等待用户共同联系验收。

## 调查、复用与许可

| 来源 | 版本/许可 | 实际处理 |
| --- | --- | --- |
| [SQLite FTS5官方文档](https://sqlite.org/fts5.html#external_content_tables) | Python内置SQLite，FTS5；公共领域 | 复用external-content表及官方同步触发器规则，持久分词全文；不新增数据库服务。构建Python内置SQLite3.50.4，版本读取未打开数据库。 |
| [SQLAlchemy分页/流式官方文档](https://docs.sqlalchemy.org/en/20/orm/queryguide/api.html#fetching-large-result-sets-with-yield-per) | 锁定2.0.54，MIT | 复用现有async Session/stream/partitions，每页512向量；Alembic仍唯一迁移authority。 |
| jieba / FastEmbed / NumPy / DiskCache | 0.42.1 MIT / 0.8.1 Apache-2.0 / 2.5.3 BSD-3-Clause及附带许可 / 5.6.3 Apache-2.0 | 继续使用现有组件和随包许可；分词、BGE编码、分批精确评分和加速缓存，不引入新依赖。 |
| BAAI/bge-small-zh-v1.5 | MIT，模型SHA1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38 | 沿用本地512维模型，2000字符编码，不运行新模型下载或推理核验。 |
| [OpenAI检索](https://developers.openai.com/api/docs/guides/retrieval)、[会话状态](https://developers.openai.com/api/docs/guides/conversation-state)、[压缩](https://developers.openai.com/api/docs/guides/compaction) | 2026-10-07官方API文档，行为参考 | 存档、检索和有限提示分层；不采用云文件上传/服务端compaction，不推定ChatGPT内部算法与API相同。 |
| [SillyTavern历史存储](https://github.com/SillyTavern/SillyTavern/blob/1.19.0/src/endpoints/chats.js)、[向量扩展](https://docs.sillytavern.app/extensions/chat-vectorization/)、[摘要](https://docs.sillytavern.app/extensions/summarize/) | 1.19.0，AGPL-3.0 | 参考增量向量与摘要行为，不复制/并入源码，不把酒馆的全聊天数组改成我们的存储底座。 |

已有许可见[semantic inventory](../licenses/semantic-runtime-inventory.json)、[BGE许可](../licenses/bge-model-LICENSE.txt)、[jieba](../licenses/jieba-0.42.1.txt)、[DiskCache](../licenses/diskcache-5.6.3-LICENSE.txt)。未新增框架、云存储或自动摘要语义。

## 实现与可观察结果

- [0037迁移](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0037_persistent_chat_recall.py)仅新增派生recall_documents、FTS5及同步触发器；迁移严格校验纳入新表，同时保留0036及更早版本形状。没有实际运行任何数据库迁移。
- [索引存储](../../services/core/src/livingworld/infrastructure/persistence/recall_index.py)按当前授权和源版本读取；每次补最多64条较早记录，冷索引保持关键词候选回退；保存前独立短事务复核，重复无变化不重写。源消息、停用/纠正和canonical ledger保持权威。
- [长期聊天存储](../../services/core/src/livingworld/infrastructure/persistence/long_chat_memory.py)把全文候选、近期候选、渐进页和历史语义命中合并后排序；生成用的历史路径移除最近8192引用限制。最终条目/原句容量不变。
- [语义检索](../../services/core/src/livingworld/infrastructure/semantic_chat_retrieval.py)流式512向量一页，最多三个问题，每问保留前16，融合返回最多24个历史ID；历史扫描总等待3秒，候选编码工作也保留既有3秒等待。超时/未索引标记部分覆盖，不宣称无限容量下固定耗时或永不遗忘。
- [聊天分页](../../apps/web/src/useTranscriptPages.ts)在私聊/群聊保留最多200条，旧页继续按原游标访问，“返回最新消息”恢复末页，发送时切回最新。轮询不混入正在阅读的旧页，保留未读规则和滚动锚点；不删除聊天。

索引增加本地磁盘占用；向量负载每条2080字节，全文分词及索引另计。没有在界面新增清空/重建功能。亲历Observation的近128条边界、本轮未授权的自动摘要/反思、runtime备份/分支均保持原范围。

## 检查与交付

- ESLint/TypeScript、Ruff源码及7个本轮Python文件格式通过；7文件AST解析、SQLite ORM表DDL及全文/向量SELECT语句静态编译完成，没有数据库连接。git diff --check通过；Git提示既有工作文件行尾会规范为LF，不是检查失败。
- 仓库文档链接检查：858个本地目标，0断链；随包512个本地目标，0断链；最终产物清单保留这些结果。API协议仍1；Desktop五处版本字段均0.1.39，根npm/Web/Core独立0.1.0不变。
- 构建命令：`.\.venv\Scripts\python.exe scripts/build-portable.py --build-only --output-name history-recall-0139`，退出码0；Core冻结与Web/Desktop release编译完成，未执行脚本smoke分支。EXE FileVersion/ProductVersion均0.1.39。
- 新入口`artifacts/portable/history-recall-0139/dreamtalk/dreamtalk-desktop.exe`，完整ZIP`artifacts/portable/history-recall-0139/dreamtalk.zip`。Desktop SHA256 `c371d4f68650e7b364eb91751c819ad668f06ad0f93bc3dfc4f52c58e0b2a910`；Core SHA256 `81edcd37c896bb6d0ad5cc072bb528c87ca0558b90385f5a65b4afa77f6c7396`；最终ZIP/文档清单见ignored的`artifacts/history-recall-0139-build.json`。
- 构建告警：主JS717.61kB、Three587.98kB、关系网817.51kB超过建议chunk大小；STATIC_VCRUNTIME弃用；PyInstaller可选tzdata/pysqlite2/MySQLdb未找到；jieba转义SyntaxWarning。运行路径没有借构建进行验收。
- 没有启动应用、读取真实存档、执行迁移、自动测试、embedding推理或付费模型。共同联系仍等待用户验收，未触发或改变门禁。

运行行为、老存档升级、大规模性能与模型表现仍由用户验收。Desktop0.1.39仅本地便携交付，GitHub公开Release仍0.1.37，原0.1.38包保留。本轮未提交源码；随包源码链接使用Git基线4d280cc，不能表示这些本地改动或新文件已公开，新文件远程链接可能不可用。
