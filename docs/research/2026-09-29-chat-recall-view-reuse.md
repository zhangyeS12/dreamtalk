# 聊天回忆界面：成熟组件调查与复用

日期：2026-09-29。接续 `3203dac`；目标是让玩家搜索自己有权阅读的共同对话、核对原文来源，并把引用放回草稿。

## 调查与决定

- [SQLite FTS5](https://sqlite.org/fts5.html) 提供全文检索、MATCH 与 BM25 排序；[许可](https://sqlite.org/copyright.html)为 public domain。本机 Python SQLite 3.50.4（仅读取版本信息）。复用已存在的 Fts5ChatRecallRanker，不重写检索或排序，不添加持久索引。
- [jieba](https://github.com/fxsjy/jieba/blob/master/README.md) 的 cut_for_search 处理中文检索词。继续使用锁定的 0.42.1/MIT 与现有字典、PyInstaller hook、随包原始许可，版本未升级。原始来源和选型详见[前序研究](2026-09-28-chat-recall-reuse.md)。
- [Mem0 v2.2.1 源码](https://raw.githubusercontent.com/mem0ai/mem0/v2.2.1/mem0/memory/main.py) 的 entity parameters、identity metadata filtering 与 _build_filters_and_metadata 可启发后续 user/agent/run 范围设计；[许可证](https://github.com/mem0ai/mem0/blob/main/LICENSE)为 Apache-2.0。本轮只参考，未安装或复制。其自动提取与 embedding/vector runtime 不解决现有 Observation-only 记忆证据语义；不能把其 filter 等同本项目权限证明。
- [Letta legacy V1 memory blocks](https://docs.letta.com/v1-sdk/memory/memory-blocks)展示持久分块、常驻上下文与 read_only；[开源许可](https://github.com/letta-ai/letta/blob/main/LICENSE)为 Apache-2.0。记录的是本日网页/仓库 main，而非锁定 SDK 版本；仅作产品启发，无依赖引入。可编辑共享块不能直接替代当前不可变、按 Character 绑定的私有记忆。
- [浏览器原生 dialog](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog) 的 showModal/close/取消事件用于回忆面板与焦点管理。使用现有 WebView，不新装弹窗库，不复制文档代码。

选择：现有 SQLite + jieba + 授权消息分页 + 浏览器原生 dialog。新增代码只接通应用查询、HTTP/client 和界面，没有新服务或模型调用。成熟框架仍是后续语义召回/摘要的候选，不能仅为显示已有原文重写整个 Agent runtime。

## 已实现契约

- 单聊/群聊顶部新增“聊天回忆”；限当前会话。它展示共同对话原文，不展示角色私有 Observation、Memory 内容或 Developer trace，也不宣称这些就是模型上一轮实际选中的证据。
- authenticated POST `/api/v1/worlds/{world_id}/conversations/{conversation_id}/messages/search`，body 是 query（非空、最多 256 字符）和可选 before_position（strict int 1..signed64 max）；不创建 RequestId/claim/账本/模型请求。POST 避免把查询词拼进 URL；CLI access_log 保持关闭。对话 owner 验证在读取 ChatMessage 文本之前，通过原有 World + 绑定 Player + Conversation 查询。
- 每次读取一页最多 100 条（现有分页额外读一条探测 older），新到旧处理最多 512 KiB UTF-8；单条大于 8 KiB 跳过并计数，ranker 只接受已授权候选。DB 最多仍可能材料化 101 × 64 KiB 消息，512 KiB 是处理/排序预算，不是整个 SQL 材料化的硬内存上限。
- 每批返回最多 8 个 BM25 相关结果、正文合计 32 KiB，并保留原 Message/Turn/Conversation/sender/position/UTC。字面分词 OR 查询、原有功能词过滤和最多 24 个不同词保持不变；不做同义词、指代或语义理解。
- next_before_position 按最后消费的位置或 DB page 继续向前，超过处理预算时不跳过未消费旧消息。UI 明示每批/累计扫描数和结果数，可继续检索更早记录；最多保留 64 条结果，达到上限要求缩小关键词。不是完整全库排序，也不保证返回所有匹配。
- “查看前后文”复用 authenticated page API，limit=7、before_position=命中 position+4；在连续位置记录上最多前三条、命中、后三条，靠近开头/末尾可少于七条。消息身份复核后标明命中记录；正文使用现有安全渲染，较长内容内部滚动。
- “引用这段，继续聊”只追加可编辑草稿，保留已有输入，UTF-8 合计大于 64 KiB 拒绝。没有模型时仍可检索/阅读；生成、待保存或模型不可用时禁用引用。用户确认发送后才走原有 governed chat 路径，不直接写 Knowledge/WorldTruth/Memory。
- 关闭面板或切换会话时 abort 读请求，不接受过期结果；原生 dialog 的 Escape/关闭返回界面，引用后聚焦输入框。仅关闭回忆面板不取消正在进行的角色回复。

## 状态与后续

源码/静态检查和编译允许；按 AGENTS section 20，不新增/修改/运行测试、GUI smoke、provider/credential probes 或真实用户 DB/配置操作。实际中文检索质量、长历史分批、WebView dialog 焦点/Escape、引用和隔离仍待用户验收。既有流式 API 的历史测试 mock 未适配问题未在本轮处理。

当前独立 episodic memory 仍只接受 owner Character 的 Observation evidence。Developer inspector 已有内部查看/记录入口；角色上下文已读取其自己的记录。老 EPISODIC_MEMORY 文档中“Developer UI/Agent consumption 延后”是 C007A 原切片范围，现已注明变化。普通聊天回忆不是新的 Memory provenance，不扩宽私有可见性。

后续优先：确定带 Conversation/Message 来源的摘要写入与修正规则，再评估复用 Mem0/Letta 的适配；涉及新证据语义时独立决策，不自动把所有聊天升为世界事实。其后推进 Director 计划消费/主动世界活动。
