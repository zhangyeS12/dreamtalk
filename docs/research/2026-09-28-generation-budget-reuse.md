# 资料生成独立额度：复用与修复决定

调查日期：2026-09-28；基线 `c1e9730`。用户明确要求解决角色卡/世界书生成被聊天额度拦截的问题。

## 证据与边界

原链路为 ProductApp.tokenCeiling → WorldImports → ContentEditor → research.token_ceiling → ContentBuilder；生成准备将聊天额度减去路由候选的整个可信输入上界，余额小于 1 就拒绝。模型最大输入为 1,000,000 时，最大聊天额度同为 1,000,000，即使本次资料很少也无法生成。

截图中聊天输入框 150,000 与生成区 200,000 的差异来自尚未点击“应用”。新版聊天区显示已应用值；资料生成同时彻底移除这条设置链路。

## 调查与复用选择

| 来源 | 可复用内容 | 决定 |
| --- | --- | --- |
| [DeepSeek Chat Completions 官方协议](https://api-docs.deepseek.com/api/create-chat-completion/) | `max_tokens` 对单次输出设上限，usage 返回实际用量 | 沿用现有 Chat Completions adapter；请求输出至多 8,192，受更低模型设置约束。仅参考公开协议，未复制外部源码 |
| [OpenAI tiktoken 官方示例](https://developers.openai.com/cookbook/examples/how_to_count_tokens_with_tiktoken) | 模型相关的本地分词与消息计数 | 本轮没有当前代理/模型服务端计费和消息框架的一致性证据，不把本地计数推断为跨提供商硬保证；未引入 tokenizer 或 SDK |
| [LiteLLM 官方 token usage 文档](https://docs.litellm.ai/docs/completion/token_usage) | token_counter、custom tokenizer、model metadata | 单为此次隔离问题引入另一套模型框架没有必要，也不能自动证明当前服务端计费上界；未安装、嵌入或复制该实现 |
| 本项目 ModelLimitUsageBounder、ChatTurnTokenBudget、governed gateway/账本/金额 guard（基线现有实现） | 可信上界、逐物理尝试预留、用量结算、共享 retry/fallback、防未知结果重放 | 直接复用，不新增依赖、分词估计或第二套账本 |

仅查询公开文档和现有代码；未使用用户密钥、调用提供商或执行真实联网生成。没有引入外部实现，第三方依赖版本/许可证不变。

## 最终策略

1. 生成请求不传聊天额度。HTTP 的旧 `token_ceiling` 改为可选 deprecated 字段，仅保留旧回执 fingerprint 兼容，不传给生成预算。旧 request ID 仍不会重新 dispatch；新 ID 才是新调用。
2. 生成输出 cap = min(8,192, 当前配置中路由候选的输出上限)。没有可信模型配置仍拒绝调用。
3. 对实际路由候选先执行现有 hard bounder，独立任务容量 = max(候选可信 input + output 预留)。如输入上界 1,000,000、输出 8,192，则本次任务容量为 1,008,192，与聊天设置无关。这是内部保守容量，不是向提供商发送百万 Token，也不是实际收费数。
4. 所有物理 retry/fallback 仍使用同一个有限任务 budget。逐次 START、可信上界、金额预算、账本、未知 usage/超界失败和唯一 claim 均保留，没有将估值当硬上界，也没有取消预算。
5. 检索最多八条摘要、模型一次整理、输出与结构大小限制沿用原实现；结果仍先进入 Draft/Preview，经用户确认才 Commit。

## 验证限制与后续

改动 Python Ruff lint/format、ESLint/TypeScript、Git diff review/check 通过，完整便携包 build-only 成功。没有新增、修改或执行测试套件、smoke、真实 API 搜索/生成。既有硬编码“输入聊天 ceiling 太小应阻止 Builder”的测试预期属于旧交互，按用户测试责任保留；后续授权后再维护。

这次解决的是资料生成与聊天额度的错误关联。没有把所有提供商的最大输入上界改为本次精确 Token 数，聊天本身的保守大上下文门槛仍需单独评估。
