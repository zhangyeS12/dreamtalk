# Gemini Native Interactions Adapter

Status: **C-005E3 implemented; offline contract validation only**
Research snapshot: **2026-09-19**

## 1. 作用域与官方 wire contract

`GeminiInteractionsGateway` 是 Google Gemini 稳定 v1 Interactions API 的原生 text-only adapter：

```http
POST https://generativelanguage.googleapis.com/v1/interactions
x-goog-api-key: <ephemeral credential>
```

它不调用 `generateContent`、OpenAI-compatible Gemini endpoint 或 Google SDK。每次 adapter 调用只有一次 HTTP attempt；retry、fallback、budget reservation、accounting START/FINALIZE 继续由通用 execution/routing 层负责。实现没有 production default wiring，也没有真实付费 API 测试。

每个请求都显式发送：

```json
{
  "store": false,
  "background": false,
  "generation_config": {"thinking_summaries": "none"}
}
```

请求不使用 `previous_interaction_id`，不请求 tools、agents、Google Search、URL context、code execution、computer use 或 image/audio/video output。API key 只在 request-time 解析，并仅放在 `x-goog-api-key` header；URL、payload、日志、diagnostics、repr 和持久化记录均不得出现 key。

## 2. Provider-neutral continuation seam

`ProviderContinuationArtifact` 是 immutable operational protocol state，包含：

- `AdapterKind` 与 configured `ProviderId`；
- artifact schema version；
- hidden opaque bytes；
- visible assistant text 的 SHA-256 integrity digest。

它不是 Character Memory、Conversation 历史、WorldEvent、Knowledge、authored content、checkpoint 或 generic LLM transcript。它不会进入 accounting、budget、routing trace、世界表、`.lwcontent`，也没有新 migration。只有显式 local request codec 可以 round-trip artifact，以便调用方在自己的短生命周期内传递它。

Gemini artifact v1 只保存有序 step layout、thought signatures、model-output UTF-8 block byte lengths 与 hashes。它不复制 assistant visible text；恢复时使用 `LLMMessage.content` 中已经存在的 visible text 按精确 byte boundaries 重建 `model_output` blocks，并校验总 digest 与每块 digest。错误版本、malformed payload、篡改正文或边界不一致在 credential lookup 与 HTTP 之前返回 `CONTINUATION_STATE_INVALID`。

只有相同 Gemini adapter kind + 相同 configured ProviderId 会消费 artifact。不同 provider instance 或不同 adapter family 将 artifact 当作不适用并按普通 assistant text 映射。`RequestId`、InvocationId、provider interaction ID 和 continuation identity 不混用。相同 provider 内的 reported model 变化不靠模型名 heuristic 禁止 continuation；wire compatibility 由 Gemini protocol signature 自身负责。

## 3. 请求映射

LivingWorld message 顺序原样映射：

| LivingWorld | Interactions step |
| --- | --- |
| leading SYSTEM（最多一个） | top-level `system_instruction` string |
| USER | `user_input` + ordered text content |
| ASSISTANT | `model_output` + ordered text content，或通过 artifact 恢复原 thought/model steps |

连续同 role 消息保持不同 steps。多个 system、非 leading system、DEVELOPER、空 text block 与未知 block 在网络前失败。若最后一条消息是 ASSISTANT，只有 model profile 显式 `supports_assistant_prefill=True` 且不是 structured request 时才允许；默认 false。

Portable fields：

- `max_output_tokens` → `generation_config.max_output_tokens`；
- ordered `stop_sequences` → `generation_config.stop_sequences`；
- `temperature`：2026-09-19 的稳定 v1 reference 未定义此字段，因此当前 fail closed，不 clamp、不猜 model support；
- thinking level 不覆盖 provider/model default。

Non-stream structured request 使用：

```json
{
  "response_format": {
    "type": "text",
    "mime_type": "application/json",
    "schema": "<original LivingWorld schema>"
  }
}
```

schema 不被改写；既有 Draft 2020-12 local validator 在 provider call 前检查 schema，在完成 response 后解析和校验 instance。Structured streaming 继续在网络前拒绝。

## 4. Non-stream response semantics

Adapter 直接解析 `Interaction` resource 的 ordered `steps`：

- `model_output.content[type=text]` 是唯一 visible output，按 provider 顺序无分隔拼接；
- `thought.signature` 只进入 hidden artifact；thought summary 不进入正文；
- function/tool/agent/server-tool/multimodal step 返回 `UNSUPPORTED_CAPABILITY`，不执行动作；
- reported model 保留 configured ProviderId，只将 provider 返回的 model string 作为 model id；
- interaction ID 是 bounded safe diagnostic，不是 canonical identity、continuation handle 或 storage key。

`completed` 是 STOP；`incomplete` 是 OUTPUT_LIMIT。Structured incomplete 明确成为 `STRUCTURED_OUTPUT_FAILED / OUTPUT_TRUNCATED`，不会误报 JSON parse failure。`requires_action` 是 unsupported，`failed` 使用 typed provider failure，`cancelled` 是 provider-normalized cancellation。已识别 policy/content block 是成功 refusal/filter terminal，不触发 JSON parse、retry 或 fallback。

## 5. Streaming state machine

同一 `/v1/interactions` endpoint 发送 `stream=true`。adapter 使用 shared bounded pull-driven SSE decoder，并要求 named `event:` 与 JSON `event_type` 一致：

```text
interaction.created
→ interaction.status_update*
→ (step.start → step.delta* → step.stop)*
→ interaction.completed
→ optional done / [DONE]
```

只有验证通过 `interaction.created` 后才发 `StreamStarted`；此时 provider interaction 已建立，router 永久锁定，不再换 candidate。`step.start` 可带初始 model-output text，必须先于后续 delta 发出。只有 open `model_output` step 的 `text` delta 能成为 `TextDelta`；thought signature 被增量收进 artifact，thought summary 被忽略，未知 tool/action delta fail closed。

语义成功必须看到合法 `interaction.completed`。`[DONE]` 是可选 transport terminator，不能替代 completion；completion 后 EOF 合法，completion 前 EOF 是 `MALFORMED_RESPONSE`。HTTP 200 SSE `error` 保守标为 `DISPATCHED_OR_UNKNOWN`，不 replay。外部 `CancelledError` 自然传播，不合成 Failed/Completed。成功流只产生一个 completion，失败流没有 completion，adapter 不为 terminal metadata 累积 visible full text。

## 6. Usage、pricing 与 budget

Gemini usage 映射：

| Gemini | LLMUsage |
| --- | --- |
| `total_input_tokens` | `input_tokens` |
| `total_cached_tokens` | `cached_input_tokens` |
| input - cached（两者一致时） | `uncached_input_tokens` |
| `total_output_tokens` | `output_tokens` |
| `total_thought_tokens` | `reasoning_output_tokens` |
| `total_tokens` | factual `total_tokens`，不用于重建计费分区 |

不虚构 cache-write。缺失保持 `None`。`ReasoningTokenRelation.ADDITIVE_TO_OUTPUT` 表示 Gemini thought tokens 在当前 pricing 语义下额外于 visible output；OpenAI-compatible 与 Anthropic 使用 `INCLUDED_IN_OUTPUT`；旧持久化记录缺该字段时加载为 `UNKNOWN`。

`GENERATED_OUTPUT` pricing meter 的 exact quantity：included → output；additive → output + reasoning；unknown 或缺必需计数 → `PRICING_CONTEXT_INCOMPLETE`。Gemini hard-budget 的 `max_output_tokens` 是一个 combined generated-output envelope，preflight 对 `GENERATED_OUTPUT` 只应用同一个 output upper bound，不能再额外叠加 guessed thought allowance。实际结算仍可用安全映射的 reported model pricing，但 reservation/budget 归属保持 requested ModelRef。

## 7. Error、retry 与 fallback

Google stable machine code 优先于 message text，HTTP status 只作为辅助。Normalized categories 区分 invalid/out-of-range、authentication、permission、not found、rate limit、quota exhausted、failed precondition、service/internal/API unavailable、deadline 和 unimplemented。原 provider message/body/exception/header 不进入 failure。

`QUOTA_EXHAUSTED` 不做 same-candidate retry。只有 provider 的 explicit quota admission rejection 才标为 `REJECTED_BEFORE_EXECUTION`，可在 RoutePolicy 显式允许 `FallbackReason.QUOTA_EXHAUSTED` 时尝试下一候选；下一候选必须重新做完整 budget admission、reservation 与 accounting START。普通 429 仍是 rate limit。SSE error、started stream、policy block、accounting/budget integrity failure 不 fallback。

## 8. 验证与 deferred

离线 fixtures 与 tests 覆盖 native payload/header、system/message rules、stateless continuation round-trip/tamper/foreign adapter、structured success/parse/schema/truncation/filter、usage/pricing/preflight、machine-code errors、arbitrary SSE fragmentation、initial start text、thought signature、unknown event、tool rejection、EOF/error/cancellation，以及 OpenAI → Anthropic → Gemini 单一 invocation/global attempt ordinals。没有真实网络。

Deferred：production registry/default wiring、API-key secret backend、live conformance certification、dynamic model discovery、multimodal、tools/agents/search、managed state、continuation persistence、structured streaming、billing reconciliation、Director、Character Agent、Memory、RAG 与 prompt/context assembly。

## 9. 研究来源

以下官方页面于 2026-09-19 读取；它们会变化，production enablement 前必须重新验证：

- [Gemini Interactions API v1 reference](https://ai.google.dev/api/interactions-api-v1)
- [Interactions overview](https://ai.google.dev/gemini-api/docs/interactions-overview)
- [Streaming interactions](https://ai.google.dev/gemini-api/docs/streaming)
- [Text generation and stateless continuation](https://ai.google.dev/gemini-api/docs/text-generation)
- [Thinking and thought signatures](https://ai.google.dev/gemini-api/docs/thinking)
- [Structured output](https://ai.google.dev/gemini-api/docs/structured-output)
- [API errors](https://ai.google.dev/gemini-api/docs/api-errors)
- [API keys](https://ai.google.dev/gemini-api/docs/api-key)
- [Token counting](https://ai.google.dev/gemini-api/docs/tokens)
- [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Billing](https://ai.google.dev/gemini-api/docs/billing)
