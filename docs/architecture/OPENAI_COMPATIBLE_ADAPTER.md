# OpenAI-Compatible Chat Adapter — C-005B / C-005C1 / C-005C2 / C-005D1 / C-005D2A

状态：已实现 infrastructure adapter，使用受控官方契约形状的离线 fixtures 验证。没有真实 API key、真实提供方调用或 production default wiring；fixture 通过不等于所有模型/兼容服务器已经实测。

```text
ModelGateway.generate → preflight → CredentialProvider.resolve
→ one POST <configured base>/chat/completions → validated LLMResponse / LLMError
OpenAI-compatible Chat adapter != OpenAI-native Responses adapter
```

实现：[openai_compatible.py](../../services/core/src/livingworld/infrastructure/llm/openai_compatible.py)。应用继续只依赖 [LLM 基础契约](LLM_INFRASTRUCTURE.md)，不接收 HTTPX/provider message objects。Adapter 没有世界、知识、内容、ledger 或 receipt 的写入能力。

## 1. 官方契约与限定范围

2026-09-18 核对：[OpenAI Create chat completion](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)、[OpenAI Chat response types](https://developers.openai.com/api/reference/resources/chat)、[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)、[DeepSeek base URL](https://api-docs.deepseek.com/)。这些链接是契约证据，自动测试不会访问它们。

共同字段 `max_tokens` 表示生成 completion 的 token 上限。OpenAI 标明该字段已弃用、不兼容 o-series，并另有包含 reasoning 的 `max_completion_tokens`；C-005B **只发送 max_tokens**，不会重试、换字段或按 model-name 推断能力。调用方必须选择支持本子集的目标。预算不承诺统一 tokenizer、可见文本长度或最低输出长度。

两方都支持 system/user/assistant 文本和 stop；OpenAI 最多 4 个 stop，DeepSeek 最多 16 个。本子集限制为 4 个，超出返回 UNSUPPORTED_CAPABILITY，不截断或忽略。角色 developer 不在共同子集中，拒绝而不转换权限。

Immutable profile 保留 `ChatCompletionsProfile.supports_n`：默认 false；调用方验证目标支持后设置 true，发送 `n=1`。C-005C1 增加 explicit structured_output_mode，默认 NONE；实例 capabilities 准确报告 text 与 structured mode，不依赖 hostname、provider ID 或模型名称。旧纯文本 fixture 配置继续有效。

## 2. Endpoint、传输与生命周期

| Caller base URL | 请求 URL |
| --- | --- |
| `https://api.deepseek.com` | `https://api.deepseek.com/chat/completions` |
| `https://api.openai.com/v1` | `https://api.openai.com/v1/chat/completions` |
| `http://127.0.0.1:43210/v1/` | `http://127.0.0.1:43210/v1/chat/completions` |

移除 base URL 尾部 `/` 后直接追加 `/chat/completions`；不添加 `/v1`，不移除已有中间路径。复用 EndpointConfig 验证，再拒绝空 port、非法 DNS labels/percent escapes、dot path segments 等会歧义化或改变路径的形状。只接受 http/https；拒绝 URL userinfo、query、fragment、空 host、非法 port、control/whitespace/backslash。允许 localhost/private IP，HTTPS verification 不可关闭。

每个 gateway 拥有一个复用的 httpx.AsyncClient；支持注入 AsyncBaseTransport，gateway 同时拥有该 transport 的关闭责任。`async with` / `await aclose()` 释放客户端；调用方应先取消/等待 in-flight invocations，再关闭 gateway。没有全局 singleton 或每消息创建 client。

`trust_env=False`，不读取环境代理/netrc；`follow_redirects=False` 同时设置在 client 和 send。没有 auth retry、transport retry 配置、sleep、fallback 或第二次调用。3xx 作为 CONFIGURATION failure，不读取 Location 后再次发送 bearer。Config timeout_ms 用于 HTTPX connect/read/write/pool 各阶段，不宣称是覆盖凭据查找的整体 deadline。

## 3. 凭据与请求映射

ProviderConfig 只保留 SecretRef。Preflight 和本地配置检查通过后，每次 generate/stream 才调用 CredentialProvider.resolve；不缓存解析结果。缺失 reference 是 CONFIGURATION，解析失败/错误值/非法 bearer token 是 AUTHENTICATION，不调用 HTTP。取消凭据查找或 HTTP await 的 CancelledError 直接传播。

明文仅作为临时 transport-boundary 值构造 Authorization，不放入 config/request/response/diagnostics。finally 删除 wire request 的 Authorization、清空临时 provider cookies、关闭 response 并释放本地 secret reference；client default headers 不存 bearer，后续请求不发送 cookie。Python 字符串不被宣称为可保证物理内存擦除。Injected transport 属于可信边界，负责不记录凭据或消息。

| dreamtalk | 外部请求 |
| --- | --- |
| model.model_id | model，原样 opaque ID |
| ordered messages / ordered TextContent blocks | 同角色消息，block text 按顺序无分隔符连接 |
| max_output_tokens | max_tokens，原数值 |
| stop_sequences | 非空时发送 ordered stop array |
| nonstreaming | stream=false |
| profile.supports_n=true | n=1 |
| purpose / invocation / correlation / metadata / SecretRef | 不发送 |

没有中性 temperature 参数，所以不制造 temperature/top_p/seed。未声明支持的 streaming、structured stream、未来 nontext blocks 及 NONE 下的 StructuredOutputRequest 均在解析凭据前拒绝。C-005C2 的真实文本 stream 使用同一 request mapper，stream=true 和显式 profile 控制的 include_usage；详见下文。C-005C1 的两个显式结构化模式只添加 response_format，不改写消息或附加 schema 提示词，不按自然语言里的 JSON 字样检查能力。store/previous-response IDs、provider-side conversation state、tools、thinking/reasoning controls 不启用。此层 stateless 不构成云端数据保留政策承诺。

## 4. 响应、拒绝与 usage

要求合法 JSON object、`object=chat.completion`、nonblank model、非空 choices；只选择**数组第一项**，验证 nonnegative integer index、assistant message 和 content/refusal/finish 类型。多个 choice 不拼接，不排序、不产生多个应用结果；其余 choice 不作为选择结果。finish 缺失/null 可映射 UNKNOWN；message.content 必须存在且为 string/null。无明确 refusal 的 null text 通常是 MALFORMED_RESPONSE；结构化请求的 length/null 例外，先归类 OUTPUT_TRUNCATED。不会用 reasoning_content 替代文本。

保留提供方报告的实际 model string，但 ProviderId 和 InvocationId 始终来自本地 request。Content 是 TextContent，不返回外部 message dict；`reasoning_content`、annotations、tool arguments、raw payload 均不透传。若提供方把本次 bearer 直接反射入 model/output，拒绝该响应。

| 外部语义 | dreamtalk |
| --- | --- |
| stop | STOP |
| length | OUTPUT_LIMIT |
| content_filter / refusal finish 或非空 message.refusal | REFUSAL，成功 response |
| tool_calls / function_call finish 或实际 tool payload | UNSUPPORTED_CAPABILITY，不执行 |
| 未知字符串 / 缺失 finish | UNKNOWN + bounded selected diagnostic |

普通文本含 “I can't help with that.” 不构成 refusal 推断。REFUSAL 仍保留 usage/latency；content 非 null 时保留 content，null 时使用显式 refusal text，content_filter 没有文本时保留空输出。Refusal 不创建 ValidatedStructuredResult。其他结构化响应按 C-005C1 本地验证后才可创建该 claim。

usage 可 absent/null；保持 None，不生成零值或假想总数。prompt_tokens/completion_tokens/total_tokens 映射 input/output/total，各字段可未知，已报告值要求 nonnegative integer（不接受 bool）。只保留 allowlisted cached/audio/reasoning/prediction token counts 和 DeepSeek cache-hit/miss counts，未知详情不复制；不计算价格。latency_ms 用 monotonic perf_counter 测量一次 HTTP send 的 round trip，包含读取响应，不包含凭据查找或 response normalization。

## 5. 错误、诊断与日志

| 失败 | LLMErrorCode |
| --- | --- |
| 401 / 403 | AUTHENTICATION |
| 429 | RATE_LIMITED |
| 408 / HTTPX timeout | TIMEOUT |
| 5xx / HTTPX transport failure | PROVIDER_UNAVAILABLE |
| 400 / 422 | INVALID_REQUEST |
| 400 / 422 且 error.code/type 明确为 context_length_exceeded/context_window_exceeded | CONTEXT_LIMIT |
| malformed successful JSON/schema | MALFORMED_RESPONSE |
| 不支持的请求或 tool response | UNSUPPORTED_CAPABILITY |
| 3xx / 其他配置不兼容 HTTP status | CONFIGURATION |

不分析英语 message 猜 context limit；未知结构化 code 不猜测。错误携带 normalized code、InvocationId 与 selected diagnostics；结构化后处理失败额外携带安全 attempt summary 和 typed detail。原 HTTPX/credential exceptions 不保留在 LLMError.__context__/__cause__。

Selected provider_request_id 优先 x-request-id，其次 body.id；允许最多 128 个 `[A-Za-z0-9_.:-]` 字符，并拒绝本次 bearer 和完整已知 message/stop 的直接反射。未知 finish 同样筛选，安全时保留 `finish:<value>`，否则仅 `unknown_finish_reason`。这不是任意字符串/编码敏感数据的万能 sanitizer。HTTP error diagnostic 仅 `http:<status>`，不复制 provider message、raw body、headers、URLs 或 Retry-After。C-005A 的 ProviderDiagnostics 只有 request ID/code，没有 typed retry timing slot；本任务不扩展 application 契约来承载时序元数据，不重试，后续任务处理。

复用 StructuredLogger allowlist：timestamp/level/component/event/trace_id。trace_id 使用本地 InvocationId，event 只取固定 completed/normalized category；不展开 provider diagnostics、prompt/response/private reasoning、token、SecretValue 或 exception text。可选 provider/model/purpose/latency logging 未扩展，避免另造日志字段管线。

## 6. 离线证明与后续边界

[测试](../../tests/core/test_openai_compatible.py) + [OpenAI fixture](../../tests/core/fixtures/llm/openai_chat.json) + [DeepSeek fixture](../../tests/core/fixtures/llm/deepseek_chat.json) 使用 httpx.MockTransport。Fixture 的 model/ID/text 是人工受控值，形状依据上述官方文档；不冒充真实调用记录。

覆盖正确 base paths、安全 endpoint/redirect、late credential resolve、header/cookie cleanup、role/content/stop/profile 映射、内部字段排除、usage unknown/advanced counts、explicit refusal、unknown finish、malformed success、status/context/transport errors、cancellation、single-request/no-retry、structured logs 与 synthetic canary 排除，以及已有 fake/架构和 Stage 0–3 回归。

没有修改 domain/application contracts、canonical content/hash/package、command/ledger/replay、知识权限或 migration。httpx 从 dev 提升为直接 runtime dependency，uv.lock 继续锁定 0.28.1；没有新增 SDK。Responses、其他 provider、SSE streaming、schema validation、retry/backoff、routing/fallback、pricing/usage persistence、真实 key storage、Director/Agent/Memory/Builder 和 final UI 均不在 C-005B。停止于本任务。

以上依赖/范围说明记录 C-005B 基线。C-005C1 的 contract 扩展和本地验证如下；世界、内容、knowledge、ledger 和 migration 均不变。

## 7. C-005C1 显式结构化模式

| Profile mode | response_format | 保证边界 |
| --- | --- | --- |
| NONE | 不发送；结构化请求在凭据/HTTP 前拒绝 | 普通文本 |
| NATIVE_JSON_SCHEMA | `{type: json_schema, json_schema: {name, strict: true, schema}}` | 明确选择的提供方 schema 子集 + 本地验证 |
| JSON_OBJECT_LOCAL_VALIDATE | `{type: json_object}` | 提供方 JSON object syntax；schema 仅在本地 |

Native发送schema_name及面向strict子集的wire副本，原始schema仍作为本地校验authority。0.1.42补齐closed object／全部required、移除wire中的default／方言声明，字符串长度限制保留说明与本地验证；不注入消息、不修改原schema，不实现完整schema编译器。两种transport均要求显式`type: object`，native拒绝root anyOf；更宽的union/$ref-only/array/scalar root在凭据/HTTP前按UNSUPPORTED_CAPABILITY拒绝，动态map等不支持的native副本按INVALID_REQUEST拒绝。通用本地validator不受这些wire限制；提供方400/422仍归类INVALID_REQUEST。见[适配记录](../maintenance/2026-10-08-provider-compatibility.md)。

先检查 schema/dialect/local refs，再一次 HTTP 生成，再依次处理 refusal/filter → length → strict parse → schema validation。Refusal/filter 返回 LLMResponse，无 claim；length 返回 OUTPUT_TRUNCATED，哪怕文本恰好是合法 JSON。Parse/schema/empty failure 使用 STRUCTURED_OUTPUT_FAILED + typed reason，保留不含 response 的 attempt accounting summary。成功仅在本地验证后保留 raw text + validated claim。自动重试、repair、prompt 修改和价格均未实现。

官方证据、精确 dialect/format/$ref policy 和受控结构化 fixtures 见 [STRUCTURED_GENERATION.md](STRUCTURED_GENERATION.md)。C-005B 的纯文本回归仍执行。


## 8. C-005C2 Real Text Streaming

新增 profile.supports_streaming / supports_stream_usage（默认 false，usage support 要求 streaming），实例 capabilities.streaming 如实读取显式配置。`stream()` 使用同一 `_payload`、`_secret`、AsyncClient 和 `_status_failure`，一次 stream=true HTTP attempt；只在声明支持时发送 stream_options.include_usage=true，不猜 hostname/model/provider。不调用 generate/完整 response parser，不缓存完整 HTTP content 或累计答案。

SSEDecoder 按 LF/CRLF、blank line 和多 data lines 增量 framing；UTF-8 分片安全，comments 忽略，StreamLimits 集中限制 line/event/error body/model metadata。每个合法非空 choice-0 content 原样产生一个 TextDelta；role/空/null 无假正文；extra choices 不合并。reasoning_content 和 refusal payload 不交付、不留 growing buffer；tools 不执行并明确失败。

HTTP/type 成功才 Started。usable finish + `[DONE]` 才 Completed；EOF、missing finish、malformed event/chunk、midstream timeout/disconnect→单一 normalized Failed，无 completion 或 automatic retry。Refusal/filter 保持成功 completion，以最小 StreamOutcome 区分，既有非流式 mapping 不变。未知 finish 只保留固定 unknown_finish_reason code。

StreamCompleted 携带 content-free LLMStreamCompletion；TextDelta 是唯一正文来源。UsageUpdate 与 terminal usage 是同一最新事实快照，未知 None，不求和；失败后不虚构完成的 attempt summary。latency 从 send 到 `[DONE]`，包括 consumer backpressure。safe provider request ID 仍仅为诊断。

finally 在 terminal 交付前 scrub wire Authorization/cookies/secret reference 并关闭 response，关闭的 HTTPX failure 也归一化。CancelledError 与 explicit iterator.aclose 释放资源，不转为 synthetic Failed/Completed；放弃 iterator 时使用 aclosing。没有 greedy reader/queue。日志继续固定 allowlist，不写正文/prompt/reasoning/HTTP exceptions。

详细限额/生命周期/官方证据/限制见 [LLM_STREAMING.md](LLM_STREAMING.md)；离线验证见 [stream tests](../../tests/core/test_llm_streaming.py)、[OpenAI SSE](../../tests/core/fixtures/llm/openai_stream.sse)、[DeepSeek SSE](../../tests/core/fixtures/llm/deepseek_stream.sse)。C-005B/C1 generate regressions 保持执行，无新增依赖和 migration，真实 API 兼容性仍未实测。


## 9. C-005D1 Dispatch / Retry-After normalization

Adapter 仍每次 generate/stream 只发起一次 HTTP send，无 backoff/sleep/retry loop。新增 failure dispatch_state / http_status / retry_after_seconds；explicit HTTP 429/408/5xx 保留 normalized status 和有效 standard Retry-After duration（delta-seconds / HTTP-date），不保留 header。Local preflight/credentials 为 NOT_DISPATCHED；pool/connect timeout 和 ConnectError 在没有 response 时为 proven NOT_DISPATCHED；read/write/unknown transport failure 为 DISPATCHED_OR_UNKNOWN。HTTP response 后的 malformed/structured failure 标为 HTTP_RESPONSE_RECEIVED，结构化 summary 不变；read interruption 仍未知，不因 headers 200 就认为可以重放。

[_status_failure / _transport_failure](../../services/core/src/livingworld/infrastructure/llm/openai_compatible.py) 是唯一 concrete normalization 边界；[_failure_error](../../services/core/src/livingworld/infrastructure/llm/openai_compatible.py) 转交全部安全 typed facts。仅 [外层 ExecutingModelGateway](LLM_EXECUTION_POLICY.md) 决定相同 provider/model/request 的下一次 attempt。旧 direct no-retry/credential/scrub/structured/stream tests 继续执行。没有 SDK、dependency、migration 或 production wiring；该段记录 C-005D1；C-005D2A accounting 见下文，C-005D2B 未开始。

## C-005D2A：factual usage normalization

2026-09-18 官方 [OpenAI caching](https://developers.openai.com/api/docs/guides/prompt-caching) / [Chat usage](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) 与 [DeepSeek usage](https://api-docs.deepseek.com/api/create-chat-completion/) 支持 optional normalized cached/cache-write/uncached/reasoning 明细。OpenAI ordinary=input-cached-write 仅全部相关事实已知时推导；缺 cache-write 不补零。DeepSeek hit/miss 直接使用 provider counters；全部已知时 hit+miss=input，同时 cached/hit 要一致。Impossible partition 拒绝、不 clamp。Reasoning 是 output 子集，不自动另收费。Generate、structured attempt summaries、stream UsageUpdate/completion 均保留 normalized facts，snapshots 不求和。

Actual response service_tier 仅从 documented default/flex/scale/priority/fast 闭合值保留；不发送新增 tier preference、不推断 model billing tier，auto/unknown 为 None。Structured failure summary 保留该 safe accounting fact；stream state 仍有界、没有累计正文。Adapter 仍不接收 ledger/catalog、不写 SQLite、不算价格；[执行 observer / pricing / operational accounting](LLM_ACCOUNTING.md) 在外层。Price pages mutable，fixtures 非 production catalog。
