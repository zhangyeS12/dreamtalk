# 记忆可靠性与回复恢复复用调查

2026-10-03，基线8303d32。先核对成熟方案，再修改现有实现；不新增框架、服务或模型下载。

| 方案与来源 | 核对版本与许可 | 本轮采用与理由 |
| --- | --- | --- |
| [jieba](https://github.com/fxsjy/jieba)、[SQLite FTS5](https://www.sqlite.org/fts5.html) | 现有jieba0.42.1 MIT；SQLite随现有Python运行时，公共领域 | 直接复用已安装中文分词和数据库BM25；权限先过滤后建立私有内存索引，不增加embedding API。SQLite实际运行版本未在本轮启动核对。 |
| [RRF原论文](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)、[官方公式说明](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion) | SIGIR2009算法论文；不复制实现或论文全文 | 当前问题与前两句分别检索后按排名融合，k=60，当前问题权重2、前两句各1；这是项目的有界权重选择，尚未实测效果，不将论文结果当本项目验收。 |
| [SillyTavern Data Bank](https://docs.sillytavern.app/usage/core-concepts/data-bank/)、[package.json](https://raw.githubusercontent.com/SillyTavern/SillyTavern/release/package.json) | 当日release显示1.19.0，AGPL-3.0；vectra ^0.2.2、transformers2.14.6 | 参考有界旧原文召回。整套向量扩展需要embedding服务或本地模型；不复制AGPL代码，不引入另一个Node记忆运行时。 |
| [Mem0](https://github.com/mem0ai/mem0)、[实现](https://raw.githubusercontent.com/mem0ai/mem0/main/mem0/memory/main.py) | 当日main快照，Apache-2.0；非固定release | 参考事实提取/纠正，直接沿用现有同次回复memories和SQLAlchemy。整套提取/更新与embedding不适合本轮免额外API要求。未安装。 |
| [FastEmbed](https://github.com/qdrant/fastembed)、[pyproject](https://raw.githubusercontent.com/qdrant/fastembed/main/pyproject.toml) | 当日main声明0.8.1、Apache-2.0 | 本地ONNX向量是后续可选方案，但增加模型下载、运行库和中文模型选择。先解决确定的核心条目挤占与补充误覆盖；本轮没有声称语义检索完成。 |
| [Temporal执行生命周期](https://docs.temporal.io/workflow-execution)、[MDN幂等性](https://developer.mozilla.org/en-US/docs/Glossary/Idempotent) | 当日官方文档；只参考生命周期/幂等语义 | 复用原claim、SQLAlchemy写事务、请求ID、模型网关和费用预算。旧调用不能重放，新尝试保留来源；不安装Temporal服务或另写模型SDK。 |

长期记忆由现有身份/偏好/约定分桶候选、置顶、相关档案组成；同主题不再自动覆盖，明确replaces才沿原句指纹更新群成员各自获准副本。长期条目仍16条/8KiB、历史原句仍4条/8KiB，检索工作仍有候选和正文上限。不是所有历史都能同时进入提示，重要条目建议置顶。

回复恢复沿用已批准的[独立新尝试方案](../proposals/2026-10-03-reply-recovery.md)。无额外提取/修复/裁判API；用户明确点击的生成仍有正常模型用量。原世界真值、知识隔离、活动生命周期和日志隐私边界不变。
