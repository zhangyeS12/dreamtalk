# Anthropic Native Messages Adapter — C-005E2

状态：LivingWorld 已实现可注入、默认未启用的 Anthropic 原生 Messages adapter。实现直接使用 `httpx` 和 `POST /v1/messages`，测试全部使用离线 `MockTransport` 与受控 fixtures；没有 Anthropic SDK、真实 API key、付费调用、在线 model discovery 或 production default wiring。

```text
AdapterKind.ANTHROPIC != AdapterKind.OPENAI_COMPATIBLE
ProviderId = configured provider instance
ModelRef = ProviderId + opaque configured model identity
LivingWorld routing remains authoritative
```

实现：[anthropic_messages.py](../../services/core/src/livingworld/infrastructure/llm/anthropic_messages.py)。协议依据在 2026-09-19 核对当前 Anthropic 官方 [Messages API](https://platform.claude.com/docs/en/api/messages/create)、[API overview](https://platform.claude.com/docs/en/api/overview)、[versioning](https://platform.claude.com/docs/en/api/versioning)、[streaming](https://platform.claude.com/docs/en/build-with-claude/streaming)、[errors](https://platform.claude.com/docs/en/api/errors)、[structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) 与 [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)。LivingWorld 的具体安全边界和已冻结产品决策仍以本文件与工程任务为准。

## 1. HTTP、版本和凭据

adapter 将经过既有 `EndpointConfig` 校验的 base URL 安全追加 `/v1/messages`；未配置 endpoint 时使用 `https://api.anthropic.com`。HTTP client 禁止自动 redirect、禁止环境代理继承、要求 TLS 验证并复用既有 timeout 与 dispatch-state 归一化。每个物理 attempt 在发送前才解析 `SecretRef`，发送：

```http
Authorization: Bearer <ephemeral secret>
anthropic-version: 2023-06-01
content-type: application/json
```

可选 `AnthropicWorkspaceId` 只允许通过 typed safe field 添加 `anthropic-workspace-id`。不存在任意 caller header map，不发送 `x-api-key`、`anthropic-beta` 或 provider-side fallback beta。redirect response 不会把 bearer 转发到其他 origin。完成、失败和取消路径都会移除 adapter-owned wire Authorization、清理 cookie 并关闭 response；Python 字符串不承诺物理擦除，注入 transport 仍必须是可信基础设施。

`request-id` 仅在满足有界安全 identifier 规则且不反射 secret/prompt/stop text 时进入 `ProviderDiagnostics`。InvocationId 始终是 LivingWorld 的权威调用身份。

## 2. 请求翻译和显式 profile

`AnthropicMessagesProfile` 明确声明 streaming、native structured output、assistant prefill、optional default/max output tokens 和 optional temperature interval。行为不从 model name、endpoint 或 ProviderId 推断。

`max_tokens` 是必需 wire 字段：优先使用 `LLMRequest.max_output_tokens`；缺失时只使用 profile 中明确配置的 default；两者都缺失则在凭据/网络前返回 INVALID_REQUEST。超过 profile 声明上限同样本地失败，不 clamp、不选择较便宜值。

LivingWorld role 映射：

- 连续的 SYSTEM prefix 按原序变成 top-level `system` text blocks；
- USER / ASSISTANT 按原消息和 block 顺序映射，不 trim、merge 或重写；
- conversation 开始后的 SYSTEM 会在网络前失败，不能静默前移；
- DEVELOPER 不降级成 system；
- ending assistant prefill 只有 profile 显式支持时才保留；
- temperature 只有 profile 显式声明且值位于声明区间时才发送，不 clamp 或按名称猜测。

最多四个 portable stop sequences 映射到 `stop_sequences`。request metadata、purpose、World/Character identity、local path、SecretRef 和 correlation identity 不进入 provider payload。C-005E2 不发送 tools、server tools、thinking controls、effort、citations、containers、prompt caching、service-tier request、provider user profile 或 server-side fallback。

## 3. 非流式结果、结构化输出和终态

成功 Message 必须是 assistant message、包含安全非空 reported model 和 ordered content blocks。可见 text blocks 按顺序成为 `TextContent`；`thinking` / `redacted_thinking` 块完全忽略，不拼接、记录或持久化。`tool_use` 不执行，也不把 arguments 转成正文；当前返回 typed UNSUPPORTED_CAPABILITY。实际 reported model 保留配置 ProviderId。

终止映射：

| Anthropic stop reason | LivingWorld |
| --- | --- |
| `end_turn`, `stop_sequence` | `FinishReason.STOP` |
| `max_tokens` | `FinishReason.OUTPUT_LIMIT` |
| `model_context_window_exceeded` | `FinishReason.CONTEXT_LIMIT` |
| `refusal` / compatible refusal detail | successful refusal semantics |
| `tool_use`, `pause_turn`, `compaction` | unsupported terminal; no continuation loop |
| unknown safe value | `UNKNOWN` with fixed safe diagnostic |

显式 refusal 是成功 provider round trip，不触发 fallback。结构化请求在 profile 允许时原样发送：

```json
{"output_config":{"format":{"type":"json_schema","schema":{}}}}
```

实际 schema 是调用方的完整原始 Draft 2020-12 schema；adapter 不做 SDK-style schema transformation，不删除约束、不填 `additionalProperties`、不发送旧 `output_format` 或 beta header。成功后仍通过 LivingWorld 现有严格 JSON parser 和原 schema local validator。先判断 refusal、output limit 和 context limit：refusal 不解析 JSON；两种 truncation 都产生带安全 attempt facts 的 structured failure。没有 repair 或隐藏 retry。

## 4. Anthropic 命名 SSE

原生 stream 复用同一个有界 `SSEDecoder`，扩展为保留可选 `event:` 名称；原 `feed()` data-only 行为继续服务 OpenAI-compatible `[DONE]` 流。Anthropic 支持的生命周期是：

```text
message_start
content_block_start
content_block_delta
content_block_stop
message_delta(stop reason + cumulative usage)
message_stop
```

HTTP 200 本身不产生 `StreamStarted`。只有完整验证 `message_start` 后才发 exactly one Started。成功必须同时看到 usable terminal stop semantics 和后续 `message_stop`；Anthropic 不使用 `[DONE]`。missing reason、missing `message_stop`、premature EOF、malformed known event 或 transport break 均只产生 Failed，没有 Completed。

只有 `content_block_delta` 的 `text_delta` 产生 `TextDelta`。thinking/signature 不交付、不缓存；input JSON/tool delta 返回 unsupported。adapter 不累计全文，terminal `LLMStreamCompletion` 只含 model/finish/outcome/usage/latency/safe diagnostics。well-formed unknown future named events 安全忽略，ping 忽略；known event 名称与 payload type/shape 不一致时失败。

HTTP 200 后的 `event: error` 产生 normalized StreamFailed，dispatch state 固定保守为 `DISPATCHED_OR_UNKNOWN`，不虚构 status，也不因该事件自动 replay。调用方取消继续传播 `CancelledError`，不合成 Failed/Completed。

Anthropic 直到 terminal `message_delta` 才提供 refusal stop reason。因此先前实时交付的 TextDelta 不被基础设施回收或缓存；最终 `StreamCompleted.outcome=REFUSAL` 是权威终态。UI/application 可在更高层决定如何呈现或撤回 partial refusal text。

结构化 stream 在 credential/network 前拒绝，Stage 4 不暴露 partial JSON。

## 5. Usage、缓存、thinking 和定价

Anthropic input usage 规范化为：

```text
input_tokens = raw input_tokens
             + cache_creation_input_tokens
             + cache_read_input_tokens

uncached_input_tokens    = raw input_tokens
cached_input_tokens      = cache_read_input_tokens
cache_write_input_tokens = cache_creation_input_tokens
```

`cache_creation.ephemeral_5m_input_tokens` 和 `ephemeral_1h_input_tokens` 分别进入 `cache_write_5m_input_tokens` / `cache_write_1h_input_tokens`。缺失保持 `None`。若 aggregate 与 TTL decomposition 矛盾，保留 aggregate，丢弃不能安全解释的 TTL detail，并附固定 `cache_write_ttl_breakdown_incomplete`；有效可见输出仍成功。

`output_tokens_details.thinking_tokens` 进入 `reasoning_output_tokens`，它是 output 的子集，不能再加到 output 上。实际安全 `service_tier` 只作为 response fact 保存，adapter 不请求或推断 tier。

stream 的 UsageUpdate 与 completion usage 都是 latest factual snapshot，不是 token delta；message_start 的 input facts 与 message_delta 的 cumulative output facts在同一 accumulator 合并，不能把多个 snapshot 相加。

通用 pricing engine 新增 5-minute 与 1-hour cache-write meters。价格仍来自显式 effective-dated catalog，不硬编码 Anthropic 生产价格。选择 TTL-specific rates 但 usage 缺少对应 breakdown 时返回 `PRICING_CONTEXT_INCOMPLETE`，不猜比例。旧 ledger JSON 缺少新增字段时 dataclass default 为 `None`；字段保存在既有 typed facts JSON 中，未改变表结构，因此 C-005E2 不新增 Alembic revision。

## 6. 错误、重试、路由与 accounting

HTTP 400/401/402/403/404/413/429/500/504/529 映射到既有 normalized error categories。错误正文只在 bounded 范围内用于识别公开 error type，message/body 不进入失败、日志或持久化。Retry-After 复用共享 parser；adapter 不 sleep、不 retry。

529 进入 `ExecutingModelGateway` 的显式 transient HTTP set，继续受 candidate-local max attempts、共享 monotonic deadline、dispatch certainty、accounting integrity 和 route policy 限制。每次 adapter call 仍严格只有一个物理 HTTP attempt。E1 route 可在一个候选的安全 transient attempts 耗尽后切换到显式 Anthropic candidate；InvocationId 不变，attempt ordinal 全 route 单调递增，下一候选重新执行 budget admission/reservation/accounting START。`DISPATCHED_OR_UNKNOWN`、refusal 和 accounting/budget integrity failure 不触发跨 provider fallback。provider-side fallback 未启用。

Anthropic 没有独立 ledger 路径。现有 `ExecutingModelGateway` 依次执行 budget authorization → accounting START → physical provider call → accounting FINAL → reservation settlement。requested ModelRef 仍决定 budget ownership；reported concrete model 仅用于 factual diagnostics/pricing mapping。缓存、TTL、reasoning 与 tier facts 通过同一 `LLMUsage` / `AttemptFacts` typed JSON 持久化。

## 7. 离线验证和范围

[Anthropic adapter tests](../../tests/core/test_anthropic_messages.py) 与 [fixtures](../../tests/core/fixtures/llm) 覆盖 text、structured、refusal、cache/thinking usage、429、529、malformed success、named stream lifecycle、ping、usage snapshots、stream refusal、SSE error 和 unknown future event，并验证单字节分片。routing test 证明 OpenAI-compatible transient exhaustion → native Anthropic，保留 InvocationId、global ordinals、fresh admission/finalization；另验证 unknown dispatch 与 refusal 不 fallback。SQLite ledger test 证明 generic accounting/pricing round-trip和 privacy boundary。

canary 检查显式遍历安全对象和 operational storage，API key、prompt、visible response、thinking text、raw SSE/error、private world/path 均不进入正常 logs、routing/budget/accounting diagnostics 或 facts。OpenAI-compatible `[DONE]` tests 与 Stage 0–4 regression 独立继续运行。

未实现 Anthropic SDK、beta API、server-side fallback、tool loop、web search/fetch、thinking controls、prompt caching request generation、files、batch、token counting、model discovery、Gemini、OpenAI Responses 或真实 provider integration test。停止于 C-005E2。
