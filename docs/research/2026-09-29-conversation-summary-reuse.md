# 已确认会话摘要：复用调查与边界

2026-09-29，从 848e628 接续。用户接受可核对、可确认的长期记忆摘要方案。

## 调查与选择

- [SillyTavern Summarize](https://docs.sillytavern.app/extensions/summarize/)：当日官方文档，release 分支 [AGPL-3.0](https://github.com/SillyTavern/SillyTavern/blob/release/LICENSE)。现有模型、上一摘要＋新消息、手动修改/恢复的产品模式适用。不复制其源码；本项目的世界权限、费用治理、确认提交须由 Core 保留。
- [LangMem summarization](https://github.com/langchain-ai/langmem/blob/main/src/langmem/short_term/summarization.py)：当日 main，pyproject version 0.0.30，[MIT](https://github.com/langchain-ai/langmem/blob/main/LICENSE)。RunningSummary 记录已摘要消息 ID/最后消息，适合增量边界。现成实现依赖 LangChain/LangGraph，近似 Token 计数不满足本项目 hard reservation，直接安装会增加第二套运行时。借鉴增量边界，不复制代码/引入依赖。
- 直接复用已有 governed LLM gateway、可信计数/额度账本、SQLite WAL、SQLAlchemy/Alembic、React/native dialog 和安全 Markdown 展示。内容生成与摘要共用受控调用路径，每个显式任务单独分配有限额度；不继承聊天每轮额度，不重新实现模型/重试协议。

## 本轮契约

这是已确认的 **Conversation summary** 交互记录，不是 Observation-only EpisodicMemory、CharacterBelief、PlayerKnowledge 或 WorldTruth。只在当前会话使用：单聊该角色，群聊固定成员；不传播到其他会话。所有查询先检查 World＋当前绑定 Player＋Conversation，角色 prompt 另检查固定成员。

生成仅由用户点击。上一已确认摘要＋从覆盖位置后最早的连续原文，最多32条/96KiB正文；整条保留，不跳过长消息。摘要最多8KiB。确认后可继续处理后续批次，没有自动摘要/遗忘。用户修改标记为 user_edited；来源表示供核对的输入，不证明每个结论均由原文支持。

Draft → 编辑 → Preview(hash) → Commit。生成 UUID claim 先落库，一次 dispatch；读状态/重开不会重新调用模型。预览 hash 绑定世界、身份、会话、基础版本、来源、覆盖位置和确切内容；保存 CAS，基础版本变化拒绝覆盖。已提交同一 hash 幂等返回原版本。修正新建版本，旧内容及递归基础来源链保留；每版仅新增最多32条来源，查看旧基础版可追溯更早原文，不无界展开。

两张新交互表和 additive 0024 migration；不改旧记忆证据契约。角色仅使用已确认、覆盖位置早于当前消息的摘要作为 lower-trust USER data；新原文/纠正优先，不授予系统指令权威。selector 不读私有记忆。

按 AGENTS §20，只做源码/格式/lint/type/build/package，运行/API/迁移/恢复/隔离验收由用户执行。

## 实现细节与限制

源模型发言人标签来自当前运行角色/Player 的名称（截取160字符），不是历史名称快照。IDs/消息位置才是稳定来源。UI 只读取最近一份草稿，已确认版本通过上一版/下一版逐个读取；未提供无界草稿历史列表。关闭正在生成的对话框中止前端等待，服务端可能仍完成任务；重开后手动读取状态，不承诺取消费用。刷新保留同一草稿尚未预览的本地修改。

模型摘要不保证事实级提取正确，确认与来源浏览用于用户核对；没有把这一模式宣传为全部独立长期记忆完成。新迁移只新增表/索引且不执行任何旧消息 replay；未在真实用户数据上运行。构建时现有可选 hidden-import warnings 单独记录。
