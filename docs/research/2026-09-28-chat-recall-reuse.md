# 较早聊天召回：成熟组件调查与决定

日期：2026-09-28。目标：角色回复能参考最近提示词窗口之外、与本轮玩家话题相关的原始会话记录。

## 调查与选择

- [SQLite FTS5 官方文档](https://sqlite.org/fts5.html)：成熟内置全文检索及 BM25 排序。本项目已经依赖 SQLite，并在数据库初始化时要求 FTS5。unicode61 不自动分开连续中文；trigram 对少于三个 Unicode 字符的词不产生匹配，不能独自满足常见的中文二字人名、地点和话题。复用 FTS5 的查询和排序，不自行实现 BM25。
- [jieba 0.42.1](https://pypi.org/project/jieba/0.42.1/)，MIT；[官方 README](https://github.com/fxsjy/jieba/blob/master/README.md)的 `Tokenizer.cut_for_search` 提供中文搜索分词和子词展开。本轮固定版本并使用已安装包的公开接口，HMM 用于未登录词；不启用 Paddle、不下载模型。README 对应主模块文件 SHA `90f0bcd55ff7042835da8067d5519bb9e5cd7ec5`。通过项目 PyInstaller hook 只打包词典与 finalseg 资源，覆盖默认收集全部数据的 hook，并排除未使用的 lac_small/Paddle；[许可证](https://github.com/fxsjy/jieba/blob/master/LICENSE)文件 SHA `9d7e66b431461c785329a1b52199d4207daefacc`，随便携包提供 `JIEBA_LICENSE.txt`。
- [Mem0 Python v2.2.1](https://github.com/mem0ai/mem0/releases/tag/v2.2.1)，Apache-2.0；[search 源码](https://github.com/mem0ai/mem0/blob/v2.2.1/mem0/memory/main.py) SHA `e750edbf19b4ed20b12d11118f2831ce6d700f6c`：支持 scope filters、向量检索和 rerank。它可启发后续语义检索，但自动提取/存储不能直接代替当前 Observation 证据约束；引入 SDK 和额外 embedding/provider 治理也不是原文词法召回的必要成本。本轮不接入它，不复制源码。
- [BM25S](https://github.com/xhluca/bm25s)提供成熟稀疏 BM25，但要新增 NumPy 等依赖；已有 SQLite 足够承担这一切片，不加入第二个排序系统。

选择：SQLite FTS5 + jieba，少量应用层适配复用现有 SQL 授权分页。jieba 是唯一新增直接依赖；SQLite 无新增服务成本，jieba 增加本地字典/首轮初始化和包体积。没有增加模型调用、embedding 成本、持久字段或迁移。

## 真实实现范围

1. 私聊先解析当前会话及角色；群聊先验证当前世界、绑定玩家、固定成员和当前发言者，再调用召回。现有消息分页在 SQL 中先确认 World + Player + Conversation，排序器只接收此授权会话的候选。不查询其他私聊、其他群或其他世界；既有群内知情窗口保持原实现。
2. 从最近提示词窗口最早 position 严格向前，最多三页、每页 100 条，最多处理 512 KiB 原始文本。单条超过 8 KiB 的文本跳过；已在最近上下文中的完整 turn 不重复召回。保留数据库原记录，不截断或改写原文；仍存在每页最多 100 条（消息写入上限每条 64 KiB）的有限材料化上界。
3. 查询使用当前玩家消息末尾最多 1,024 个字符；jieba 搜索分词后去除一个小型通用功能词集合，取末尾最多 24 个不同词。FTS 参数使用字面词 OR 查询，BM25 原生排序，相同分数优先较近记录。没有同义词、跨语言、指代解析或语义 embedding；仅说“记得那个吗”可能无法召回。
4. 授权后每次建立独立内存 FTS 索引，并在线程中分词和检索；最多两个并行工作，取消时等待有界工作释放资源。索引含该次授权候选的分词，没有共享私有语料统计、持久派生索引、聊天文本缓存或文本日志。jieba 自身的词典缓存仅是公开词典数据。
5. 最多取八个排序结果供预算筛选，最终注入最多四条、原文合计 8 KiB。保持位置顺序，附 message_id、conversation_id、sender_id、player/character 类型、position 和 UTC 时间；上下文组装补当前世界优先的玩家显示名或当前 accepted 角色显示名。原文是带出处的 lower-trust USER 数据，固定 SYSTEM 明确它可能不完整、被纠正或不真实；不是 WorldTruth、Observation、Knowledge 或 EpisodicMemory。
6. 私聊和群聊角色回复共用该组件；群选人器继续只消费既有共享窗口。召回不会反向触发世界书条目，原来的 32 条/96 KiB 最近会话窗口不变，全部最终提示词仍经过原有物理调用 Token 预留与整轮硬上限。

## 验收与后续

遵守用户负责测试的要求：不新增、修改或运行测试，不启动应用、不做提供商调用。源码检查、静态检查与 `--build-only` 编译/打包结果在 HANDOFF.md 记录；打包不能证明召回正确率或运行延迟。

这实现了当前会话的有界词法原文召回，是局部检索增强，不等于无限长期记忆、完整语义 RAG 或自动聊天记忆形成。后续结合真实长对话评估检索噪声、远超三页的历史与同义表达，再调查兼容当前授权/证据边界的语义或持久检索。自动记忆形成仍需要独立的 Observation 证据设计。
