# Real Text Streaming — C-005C2

状态：现有 Chat Completions adapter 已实现 opt-in 非结构化文本 SSE streaming。验证使用受控离线 fixtures 与 httpx.MockTransport，不使用真实 key，不调用真实生成 API；未配置 production default。复用 HTTPX，没有新依赖或 migration。

```text
LLMResponse = complete non-streaming generation result
LLMStreamCompletion = streaming terminal metadata
TextDelta = streaming content source of truth

real streaming != buffered generate() split into chunks
partial text != completed answer
UsageUpdate and terminal usage are snapshots, never additive token deltas
```

实现：[application contracts](../../services/core/src/livingworld/application/llm.py)、[Chat adapter](../../services/core/src/livingworld/infrastructure/llm/openai_compatible.py)、[SSE framing](../../services/core/src/livingworld/infrastructure/llm/sse.py)、[offline fake](../../services/core/src/livingworld/infrastructure/llm/fake.py)。Domain/application 无 HTTP/SSE/SDK 依赖，没有世界或 authored-content 写入能力。

## 1. 官方依据与受控 fixtures

2026-09-18 核对 [OpenAI Chat Completions streaming events](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events) 和 [stream options](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)：delta 可以仅含 role、空/null content 或 refusal；include_usage 的最终统计 chunk 可以使用空 choices。finish_reason 独立于文本 delta，缺失 usage 不证明未消耗 token。

同日直接 HTTP 读取 [DeepSeek Chat API](https://api-docs.deepseek.com/api/create-chat-completion/)（浏览工具直读失败后使用公开页面），确认当前文档的 usage 位于 `[DONE]` 前的最终 choice chunk，包含非 null finish_reason、没有新增正文；无独立 usage-only chunk。旧文档/兼容服务器也可能发送 usage-only chunk，解析器按结构支持两种位置，不绑定 provider 名称。[DeepSeek keep-alive 文档](https://api-docs.deepseek.com/quick_start/rate_limit/) 的官方检索结果确认 `: keep-alive` SSE comments，作为协议活动忽略。

[OpenAI fixture](../../tests/core/fixtures/llm/openai_stream.sse) 使用 role-only → ordered text → finish → empty-choices usage → `[DONE]`；[DeepSeek fixture](../../tests/core/fixtures/llm/deepseek_stream.sse) 使用 CRLF、comment、private reasoning、ordered text → finish+usage → `[DONE]`。全部是人工构造的协议形状，不冒充真实调用记录，不承诺所有模型/服务器已实测。

[Git attributes](../../.gitattributes) 仅对这些 `.sse` wire fixtures 关闭 text newline conversion，保留 LF/CRLF 原始 bytes；允许协议必需的终止空行和 CR-at-EOL，其余 whitespace 检查继续执行。

## 2. Profile 与唯一请求映射

Immutable ChatCompletionsProfile 增加 `supports_streaming=false`、`supports_stream_usage=false`，默认不声称未验证的能力。usage request support 要求 streaming support；非 bool/不一致配置拒绝。实例 ModelCapabilities.streaming 读取显式 profile，不按 endpoint/provider/model-name 推断。

generate 与 stream 共享 `_payload`：ordered system/user/assistant text、max_output_tokens→max_tokens、最多四个 ordered stop、optional n=1。stream 只改 `stream=true`，profile 声明支持 usage request 时添加 `stream_options.include_usage=true`，否则省略。内部 invocation/purpose/metadata/SecretRef 不发送。结构化 stream 在凭据解析/HTTP 前失败，即使 profile 支持非流式结构化模式；generate 的 C-005B/C1 语义不变。

## 3. 有上限的增量 SSE framing

SSEDecoder 逐片处理网络 bytes，保留最多一条未完成 line 和一个待提交 event，没有事件队列。完整 line 才严格 decode UTF-8，因此 UTF-8 字符、data 字段、JSON、CRLF 或 `[DONE]` 在任意传输边界分片均可正确处理。支持 LF/CRLF、可选初始 UTF-8 BOM、多条 data lines 用换行连接、空行分隔事件、comments 与未使用的 event/id/retry fields；只移除 data 冒号后一个分隔空格，不 trim 正文。

集中 immutable StreamLimits，均为正整数、可注入测试：

| Limit | 默认值 | 边界 |
| --- | --- | --- |
| max_event_bytes | 1 MiB | 收集的 data UTF-8 bytes + 每条 data 的换行计数 |
| max_line_bytes | 256 KiB | 包括 comments 的单条 wire line，不含 LF，含可能的 CR |
| max_error_body_bytes | 64 KiB | HTTP 错误正文解析上限 |
| max_model_bytes | 1024 bytes | stream reported model metadata 上限 |

超限、非法 UTF-8、无效/重复键 JSON、非法 root/chunk/delta/usage structure → normalized MALFORMED_RESPONSE。无 raw data/异常文本进入公开失败。HTTP 错误正文超限时只保留已知 status 的错误语义，不猜正文。Limits 约束 adapter 自己收集的解析状态；transport 当前交付的 byte fragment 仍由 HTTPX/注入 transport 管理。

decoder.feed 本身是 lazy iterator，同一个 HTTP fragment 包含多个 SSE events 时也在 consumer 继续读取后才处理后续 event。没有后台预读 task、greedy queue、全文拼接或 reasoning 历史。HTTPX send 使用 stream=true，不调用 response.read()/generate() 获取完整成功正文。

## 4. 生命周期、choice 和成功条件

```text
preflight / credentials / HTTP / response-type failure → StreamFailed

valid HTTP + acceptable text/event-stream → StreamStarted (exactly once)
→ zero or more TextDelta / UsageUpdate
→ valid choice-0 finish + [DONE] → StreamCompleted (exactly once)

started + broken transport/protocol → StreamFailed (exactly once)
caller cancellation → CancelledError; no synthetic terminal event
```

Started 表示已连接并验证 status/content-type；其 model_used 是请求的 ModelRef。后续 completion 使用 provider reported model，保留配置 ProviderId；首次 reported model 后必须一致。只处理 index=0，可处于 choices 数组任意位置；额外 choices 不合并。重复/缺失 choice 0、模型改变或 finish 后出现新正文/冲突 finish 均失败。允许合法空 choices 的非 null usage chunk。

`[DONE]` 是协议 terminator，不 JSON decode。必须先有可用的 choice-0 finish；不因 TCP EOF 或 partial text 推断 STOP。stop→STOP，length→OUTPUT_LIMIT；未知非空 string→UNKNOWN + 固定 unknown_finish_reason diagnostic，不保留任意 finish 字符串。finish 不是 `[DONE]` 的替代品。终态以后不处理余下事件，没有自动恢复或第二次 HTTP attempt。

## 5. 正文、拒绝、过滤与 usage

每个非空 string content 产生一个 TextDelta，精确保留 provider 顺序、空格和字面值，不拆分/trim/re-tokenize。role-only、空/null content 不产生正文。普通自然语言拒绝句仍是正文，不凭英语推断拒绝。

显式 refusal delta 的 payload 不作为 TextDelta，不累计、不放入 completion；后续 refusal 状态下也不交付普通正文。content_filter/refusal finish 是成功生成语义，需要正常 `[DONE]`。completion 复用既有 REFUSAL finish，并增加最小 StreamOutcome：NORMAL / REFUSAL / CONTENT_FILTERED，区分两种语义，不改变 generate 的 FinishReason 映射。已交付的先前 partial text 不被撤回。

reasoning_content 不生成 TextDelta，不进入 terminal state/日志/持久化，没有隐藏 reasoning buffer。实际 tool/function-call delta 或 finish→UNSUPPORTED_CAPABILITY terminal failure，不执行、不交付 arguments。不存在 tools/reasoning UI。

usage 不受 chunk 位置或 profile 的 include_usage 请求与否限制；只要提供有效非 null usage 就用既有 normalization。相同快照不重复发射；不同快照（包括 provider 报告的计数下降）按原序保留，不计算 token/total/price。没有 usage→None；部分计数缺失仍为 None。

UsageUpdate 和 LLMStreamCompletion 共享 closed numeric/None accounting-counter projection，任意文本 metadata 不进入流式元数据。终态 usage 是成功完成时最新已知事实快照，与最后一次 UsageUpdate 相同；**C-005D 不得将两者相加或双重计量**。partial failure 保留已发射 UsageUpdate；failure.attempt=None，不把 partial stream 伪装成完成的 LLMAttemptSummary。

## 6. Terminal 安全边界、取消与清理

LLMStreamCompletion 为 immutable 独立类型：invocation_id、model_used、finish_reason、typed outcome、optional usage、latency_ms、bounded selected ProviderDiagnostics。diagnostic code 使用固定闭合集合；provider request ID 仅允许至多 128 个安全 identifier characters，并由 adapter 拒绝已知 bearer/prompt 的直接反射。Provider request ID 是诊断信息，InvocationId 始终由 dreamtalk 定义。

该类型没有 content/text/messages/structured payload/reasoning/raw SSE/headers/HTTP response/credentials/provider error body，也没有任意 JSON diagnostic slot。与 LLMAttemptSummary 复用 ModelRef/Usage/FinishReason 和 safe counter helper，**不是同一种 lifecycle 对象**。上层如果需要全文，可以在自己的生命周期/内存政策下显式累计 TextDelta。

latency 使用 monotonic perf_counter，从 HTTP send 开始到读取合法 `[DONE]`，包含 consumer backpressure，排除 credentials resolution/response close；不是独立模型 compute latency。

调用时解析 SecretRef，不缓存明文。所有完成、失败、CancelledError 或 iterator.aclose 路径都先移除 adapter-owned wire Authorization、清除 cookies/本地 secret reference，再关闭 response；资源关闭和 scrub 在 terminal event 交付前完成。HTTPX close failure 归一化，原始异常不进入公开对象。Python 字符串不承诺物理擦除，trusted transport 负责不记录 key/prompt。

CancelledError/GeneratorExit 自然传播，不转换 FAILED/COMPLETED，不等待 `[DONE]`。放弃迭代的调用方必须显式 await iterator.aclose() 或使用 contextlib.aclosing；仅 break 不能被承诺为任意 Python caller 自动及时清理。gateway 复用一个 AsyncClient，调用方先关闭/取消 in-flight streams 再关闭 gateway。

HTTP/status/credential 错误复用 C-005B 分类；read timeout→TIMEOUT，midstream HTTP failure→PROVIDER_UNAVAILABLE，非法流→MALFORMED_RESPONSE。没有 retry、resume 或 background reader。正常 StructuredLogger 只记录固定 started/completed/error category 与本地 trace，不扩展字段来记录原正文、reasoning、prompt、headers 或 raw exceptions。

## 7. 验证与范围

[stream tests](../../tests/core/test_llm_streaming.py) 验证两种 fixtures、多种包括单字节的碎片、multiline/LF/CRLF、protocol/state/error transitions、unknown/duplicate/non-monotonic usage、refusal/filter、reasoning/tools 隔离、前后期 transport failures、超限、secret canaries、cancellation/early close 和一次请求。慢 consumer 测试证明尚未读取后续 bytes 就收到首个 TextDelta；同 fragment 的坏事件不会提前破坏先前正文。full-response constructor/parser/generate 被禁止时流式仍成功；HTTP response 不缓存完整 content。连续交付 2.4 MB 正文时，adapter 测试中的 tracked allocation peak 低于 1 MiB；该预算证明没有 adapter 全文副本，不是全部进程内存承诺。

[fake/contract tests](../../tests/application/test_llm_contracts.py) 与真实 adapter 使用相同 metadata-only completion；fake 不为 stream 构造 full LLMResponse，不交付 refusal payload。C-005B/C1 非流式与完整 Stage 0–3/架构回归继续执行。没有 desktop/UI 变更，无 GUI smoke。

未实测真实 API；结构化 streaming、Responses/WebSocket、tool execution、reasoning persistence、retry/repair/backoff/fallback/routing、pricing/budgets/usage DB、Director/Agent/Memory/Builder 均不在本任务。停止于 C-005C2。


## 8. C-005D1 外层 pre-start orchestration

Direct adapter stream 仍 single-attempt。新增 [ExecutingModelGateway](LLM_EXECUTION_POLICY.md) 只在 application 尚未见到 Started 前按 normalized dispatch/status/Retry-After 重试；将要重试的 Failed 只作为内部决策，旧 iterator 在等待前关闭。最终只交付一个 logical lifecycle；所有 pre-start attempts 失败则单一最终 Failed，后续成功则只有一次 Started。

Started 暴露后永久禁止自动 replay，即使无正文；actual timeout/disconnect、malformed/EOF 都保持一次 Failed/no Completed。没有 prefix resume、multiple-attempt text merging 或 buffer。InvocationId/request/provider/model 不变，ordinal 仅 execution metadata。UsageUpdate/terminal usage 仍同一物理 stream 的事实快照，不求和/不混合隐藏尝试的 usage；missing None。取消在 stream/backoff 直接传播、不产生 synthetic terminal；每次 provider attempt 独立 resolve credentials。没有 per-attempt usage persistence、price 或 routing/fallback。

## 9. C-005E2 Anthropic named SSE

同一 `SSEDecoder` 现在可保留 `event:` 名称；原 OpenAI-compatible data-only `[DONE]` path 保持不变。Anthropic native path 在合法 `message_start` 后才发 Started，只把 `content_block_delta.text_delta` 作为正文，并要求 terminal `message_delta` stop semantics 后出现 `message_stop`。它不接受 `[DONE]`，不累计全文；ping 与 well-formed unknown future event 忽略，known malformed event 失败。

Anthropic refusal 只能在 terminal message_delta 识别。基础设施继续实时交付此前的 TextDelta，最终 `StreamCompleted.outcome=REFUSAL` 决定权威语义；不为了可能的拒绝而缓存全文。SSE error event 产生 `DISPATCHED_OR_UNKNOWN` Failed，无 completion/status/replay。message_start/input 与 message_delta/cumulative output usage 合成 latest factual snapshot，不能相加。完整状态机见 [ANTHROPIC_MESSAGES_ADAPTER.md](ANTHROPIC_MESSAGES_ADAPTER.md)。

## 10. C-005E3 Gemini named SSE

Gemini stream 只在合法 `interaction.created` 后发 Started。`step.start` 可携带首段正文，后续 `step.delta` 继续产生 TextDelta；thought 与 thought summary 不进入 visible content。每个 step index 只能启动一次，stop 必须匹配当前 open step。成功必须收到 `interaction.completed`；`done` 或 EOF 不能代替语义 terminal。

Adapter 增量维护 layout、UTF-8 byte count/hash、thought signature 和整体 visible digest，不保留完整正文副本。StreamCompleted 只携带 terminal metadata、latest factual usage snapshot 和 opaque continuation artifact。SSE `error`、known malformed transitions、unexpected tools/status 产生 Failed 且没有 Completed；well-formed unknown future events有界忽略。CancelledError 继续直接传播。详见 [Gemini adapter](GEMINI_INTERACTIONS_ADAPTER.md)。

## 11. C-005E4 OpenAI Responses named SSE

合法 `response.created` 是唯一 STARTED 边界。只有 `response.output_text.delta` 产生 TextDelta；
`refusal.delta/done`、reasoning text/summary、annotations、encrypted content 和 tool arguments 都不进入
可见正文。Adapter 增量维护每个 output/content index 的 UTF-8 长度/hash 与整体 digest，不保存第二份
完整回答；terminal Response 只用于核对 streamed layout 和取得 opaque continuation metadata。

`response.completed` 且 `status=completed` 才是普通成功。Explicit refusal 返回成功的 REFUSAL
completion；`response.incomplete/max_output_tokens` 返回 OUTPUT_LIMIT；filter/policy reason 返回 filtered
terminal。`response.failed`、known malformed event、unexpected tool、transport failure 和 terminal 前 EOF
只产生 Failed。Well-formed unknown future event 安全跳过。STARTED 后 route 永久锁定；CancelledError
直接传播。UsageUpdate 与 completion usage 是 factual snapshots，不能相加。详见
[OPENAI_RESPONSES_ADAPTER.md](OPENAI_RESPONSES_ADAPTER.md)。
