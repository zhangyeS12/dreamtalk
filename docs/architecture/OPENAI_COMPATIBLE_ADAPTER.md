# OpenAI-Compatible Chat Adapter — C-005B

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

唯一 immutable profile 选项是 `ChatCompletionsProfile.supports_n`：默认 false；调用方验证目标支持后设置 true，发送 `n=1`。OpenAI fixture 使用 true；DeepSeek 当前文档没有该参数，其 fixture 使用默认 profile。选择不依赖 hostname、provider ID 或模型名称。文本生成能力声明为 true，其余 ModelCapabilities 为 false。

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

ProviderConfig 只保留 SecretRef。Preflight 和本地配置检查通过后，每次 generate 才调用 CredentialProvider.resolve；不缓存解析结果。缺失 reference 是 CONFIGURATION，解析失败/错误值/非法 bearer token 是 AUTHENTICATION，不调用 HTTP。取消凭据查找或 HTTP await 的 CancelledError 直接传播。

明文仅作为临时 transport-boundary 值构造 Authorization，不放入 config/request/response/diagnostics。finally 删除 wire request 的 Authorization、清空临时 provider cookies、关闭 response 并释放本地 secret reference；client default headers 不存 bearer，后续请求不发送 cookie。Python 字符串不被宣称为可保证物理内存擦除。Injected transport 属于可信边界，负责不记录凭据或消息。

| LivingWorld | 外部请求 |
| --- | --- |
| model.model_id | model，原样 opaque ID |
| ordered messages / ordered TextContent blocks | 同角色消息，block text 按顺序无分隔符连接 |
| max_output_tokens | max_tokens，原数值 |
| stop_sequences | 非空时发送 ordered stop array |
| nonstreaming | stream=false |
| profile.supports_n=true | n=1 |
| purpose / invocation / correlation / metadata / SecretRef | 不发送 |

没有中性 temperature 参数，所以不制造 temperature/top_p/seed。StructuredOutputRequest、streaming、未来 nontext blocks 均在解析凭据前明确拒绝；不降级成提示词、不伪造流。store/previous-response IDs、provider-side conversation state、tools、response_format、thinking/reasoning controls 均不启用。此层 stateless 不构成云端数据保留政策承诺。

## 4. 响应、拒绝与 usage

要求合法 JSON object、`object=chat.completion`、nonblank model、非空 choices；只选择**数组第一项**，验证 nonnegative integer index、assistant message 和 content/refusal/finish 类型。多个 choice 不拼接，不排序、不产生多个应用结果；其余 choice 不作为选择结果。finish 缺失/null 可映射 UNKNOWN；message.content 必须存在且为 string/null。未提供明确 refusal 时，null text 是 MALFORMED_RESPONSE，不把 reasoning_content 当作替代文本。

保留提供方报告的实际 model string，但 ProviderId 和 InvocationId 始终来自本地 request。Content 是 TextContent，不返回外部 message dict；`reasoning_content`、annotations、tool arguments、raw payload 均不透传。若提供方把本次 bearer 直接反射入 model/output，拒绝该响应。

| 外部语义 | LivingWorld |
| --- | --- |
| stop | STOP |
| length | OUTPUT_LIMIT |
| content_filter / refusal finish 或非空 message.refusal | REFUSAL，成功 response |
| tool_calls / function_call finish 或实际 tool payload | UNSUPPORTED_CAPABILITY，不执行 |
| 未知字符串 / 缺失 finish | UNKNOWN + bounded selected diagnostic |

普通文本含 “I can't help with that.” 不构成 refusal 推断。REFUSAL 仍保留 usage/latency；content 非 null 时保留 content，null 时使用显式 refusal text，content_filter 没有文本时保留空输出。不创建 ValidatedStructuredResult。

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

不分析英语 message 猜 context limit；未知结构化 code 不猜测。错误只携带 normalized code、InvocationId 与 selected diagnostics；原 HTTPX/credential exceptions 不保留在 LLMError.__context__/__cause__。

Selected provider_request_id 优先 x-request-id，其次 body.id；允许最多 128 个 `[A-Za-z0-9_.:-]` 字符，并拒绝本次 bearer 和完整已知 message/stop 的直接反射。未知 finish 同样筛选，安全时保留 `finish:<value>`，否则仅 `unknown_finish_reason`。这不是任意字符串/编码敏感数据的万能 sanitizer。HTTP error diagnostic 仅 `http:<status>`，不复制 provider message、raw body、headers、URLs 或 Retry-After。C-005A 的 ProviderDiagnostics 只有 request ID/code，没有 typed retry timing slot；本任务不扩展 application 契约来承载时序元数据，不重试，后续任务处理。

复用 StructuredLogger allowlist：timestamp/level/component/event/trace_id。trace_id 使用本地 InvocationId，event 只取固定 completed/normalized category；不展开 provider diagnostics、prompt/response/private reasoning、token、SecretValue 或 exception text。可选 provider/model/purpose/latency logging 未扩展，避免另造日志字段管线。

## 6. 离线证明与后续边界

[测试](../../tests/core/test_openai_compatible.py) + [OpenAI fixture](../../tests/core/fixtures/llm/openai_chat.json) + [DeepSeek fixture](../../tests/core/fixtures/llm/deepseek_chat.json) 使用 httpx.MockTransport。Fixture 的 model/ID/text 是人工受控值，形状依据上述官方文档；不冒充真实调用记录。

覆盖正确 base paths、安全 endpoint/redirect、late credential resolve、header/cookie cleanup、role/content/stop/profile 映射、内部字段排除、usage unknown/advanced counts、explicit refusal、unknown finish、malformed success、status/context/transport errors、cancellation、single-request/no-retry、structured logs 与 synthetic canary 排除，以及已有 fake/架构和 Stage 0–3 回归。

没有修改 domain/application contracts、canonical content/hash/package、command/ledger/replay、知识权限或 migration。httpx 从 dev 提升为直接 runtime dependency，uv.lock 继续锁定 0.28.1；没有新增 SDK。Responses、其他 provider、SSE streaming、schema validation、retry/backoff、routing/fallback、pricing/usage persistence、真实 key storage、Director/Agent/Memory/Builder 和 final UI 均不在 C-005B。停止于本任务。
