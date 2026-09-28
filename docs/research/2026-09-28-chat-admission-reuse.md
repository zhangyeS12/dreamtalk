# 2026-09-28 聊天准入与 Token 预留调查

用户问题：两条“你是谁”已保存，但艾莲无回复；检查状态显示 pending。

## 已定位的链路

`DirectChatReplyService.reply` 在 claim/provider 之前从整轮 ceiling 扣除可信输入预留。当前生产 composition 使用 `ModelLimitUsageBounder`，输入预留是配置的 `max_billable_input_tokens`，不是实际短消息的 Token 数。按用户前序截图的输入 1,000,000 / 输出 50,000 / 聊天 200,000，回复空间为 -800,000；必定在调用前拒绝。可留至少 1 Token 的最小 ceiling 是 1,000,001；完整保留一次 50,000 输出需 1,050,000。多次调用、fallback、群选人及后续发言仍共享整轮额度，后两项数字不是所有整轮完成的保证。

另有确定的 UI bug：ProductApp 的输入、应用和 localStorage 恢复均限制 ceiling <=1,000,000。配置允许输入上界 1,000,000，但 UI 无法为它留任何回复空间。`checkReply` 又用通用 pending 文案覆盖本轮真实错误，并建议继续发送。

## 成熟组件核对与复用决定

- [DeepSeek 官方 Token 说明](https://api-docs.deepseek.com/quick_start/token_usage/)：公开比例是估算，实际用量由 API 返回。本轮不把估算乘数作为 HARD_UPPER_BOUND。
- [deepseek-ai/deepseek-recipe](https://github.com/deepseek-ai/deepseek-recipe)，[Python metadata](https://raw.githubusercontent.com/deepseek-ai/deepseek-recipe/main/deepseek-recipe-python/pyproject.toml)、[PyPI metadata](https://pypi.org/pypi/deepseek-recipe/json)：2026-09-28 核对版本 0.1.1，MIT；提供官方请求转换和 V4/V4.1 prompt encoding。当前发布文件只有 macOS/Linux wheel；Windows 源构建另需 Rust/OpenCV/Clang。本轮未安装、复制或集成它。
- [官方 tokenizer 文档](https://github.com/deepseek-ai/deepseek-recipe/blob/main/docs/tokenizer.md) 与 [tokenizer 来源许可](https://github.com/deepseek-ai/deepseek-recipe/blob/main/static/tokenizers/README.md)：模板、model revision、特殊 token 及 reasoning framing 需要一起确认，不能仅按 API model ID 假定能提供硬保证。精确/保守逐请求 bound 的 Windows 分发与 API 一致性尚未确认；按 AGENTS 的 timebox 停止本轮这条分支，不虚构已解决。

具体复用：沿用现有 registry、ModelLimitUsageBounder、ChatTurnTokenBudget、HTTPException/CoreRequestError 和 React feedback；无需新依赖或持久化 schema。保留当前 hard admission；修复 UI ceiling 限制、可信预留提示、固定拒绝分类与检查状态时的错误保留。

## 实现与边界

- 可用性查询新增 optional `input_token_reservation` / `max_output_tokens`，从已配置 route 的限额取得；仅用于界面提示，最终授权仍由原 bounder/gateway 决定。兼容客户端不依赖新增字段。
- UI ceiling 范围与 JavaScript safe integer 一致，服务器既有 int64 接口不变；不自动提高用户额度。
- 生产配置不能留回复空间时，私聊/群聊提前提示具体值，不再先保存新消息再发现相同配置错误；不主动探测 key/provider。
- `chat_turn_token_limit_exceeded`、`chat_input_bound_unavailable` 是固定安全原因；费用准入拒绝保留原通用分类。已存在的 pending turn 不改 ceiling、不自动重放。
- 本轮 error 说明只保留在当前会话组件内；重启/重挂载后，当前配置的预留提示仍可重建，历史未知原因不伪造。没有新增历史失败持久化语义。

后续：在 Windows 可分发且能证明完整协议 framing / billable 语义后，才通过现有 bounder port 引入成熟逐请求组件；chat preflight 与 financial guard 必须使用同一可信 bound，所有物理尝试继续共用整轮授权。
