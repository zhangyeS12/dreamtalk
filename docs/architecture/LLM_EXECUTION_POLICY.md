# LLM Attempt Orchestration, Retry, Backoff & Routing — C-005D1 through C-005E2

状态：provider-neutral sequential retry wrapper 与其上层 deterministic routing 已实现，离线测试使用虚拟时钟、可控 sleeper/jitter、fake gateways 和 MockTransport。没有真实付费 API 验证、production default wiring 或 semantic repair。C-005D2A 增加 accounting，C-005D2B 增加 [预算准入](LLM_BUDGET_GUARD.md)，C-005E1 增加 [显式 fallback](LLM_ROUTING.md)，C-005E2 增加原生 Anthropic 529 与跨协议证明；下文 1–8 节主要保留 D1 单候选 retry policy 语境。

```text
logical invocation != physical attempt
Application → ExecutingModelGateway → single-attempt ModelGateway → provider transport
retry = same provider + same model + same immutable semantic request
structured validation failure != transport retry
```

实现：[llm_execution.py](../../services/core/src/livingworld/application/llm_execution.py)、[failure contracts](../../services/core/src/livingworld/application/llm.py)、[HTTP adapter](../../services/core/src/livingworld/infrastructure/llm/openai_compatible.py)。Application 只依赖标准库/内部 contracts，不 import HTTPX、provider SDK 或 persistence。Provider adapter、SSE parser、HTTP transport 不增加 retry loop。

## 1. 官方依据与责任边界

2026-09-18 核对 [OpenAI rate limits/retry guidance](https://developers.openai.com/api/docs/guides/rate-limits)：暂时性限流可使用有界 jitter/backoff；有效 Retry-After 是最早重试边界，需限制次数和总等待窗口，避免嵌套重试。失败请求也可能占用 quota；超时不是 provider 未执行的证明。

[DeepSeek errors](https://api-docs.deepseek.com/quick_start/error_codes/) 将 429、500、503 与认证/参数/余额错误区分；[当前 rate-limit/isolation 文档](https://api-docs.deepseek.com/quick_start/rate_limit/) 说明账户 concurrency 超限返回 429，以及保留连接/SSE comments 的机制。限流页面经公开 HTTP 直读核对，浏览工具直读失败。没有实现 concurrency scheduler、user_id、改消息/参数或切换提供方。

这些指导不是所有 compatible 服务已实测的承诺。dreamtalk 通过 normalized dispatch/status 和明确 policy 判断，保守拒绝 uncertain replay；不解析任意 provider message 猜恢复策略，不采用 SDK 隐藏重试。

## 2. Invocation 与 attempt

调用方提供 InvocationId；一个 wrapper 调用是一项 logical operation。第一次物理尝试 ordinal=1，后续依次 2、3。所有尝试接收同一个 immutable LLMRequest 对象；不生成新 InvocationId、不替换 provider/model，不修改 messages、output budget、schema、stop、metadata。Ordinal 不进入外部 wire body 或角色消息。

Ordinal 和每次决策通过 optional observer 的 closed RetryRecord 提供，包含 InvocationId、ordinal、RetryDecision、optional normalized failure code/dispatch/status。成功也记录当前 ordinal。没有响应正文、model/prompt 自由字符串、usage 汇总或 credentials。它是执行诊断，不是 durable accounting；调度 oversleep 会产生同 ordinal 的停止决策，不能把决策条数当作尝试次数。

## 3. Dispatch-state contract

LLMFailure 新增 typed DispatchState、optional http_status 和 optional retry_after_seconds（有限非负秒数），没有 raw headers/body/HTTPX exception。旧调用者未提供 dispatch 时默认 DISPATCHED_OR_UNKNOWN，不能被误认为安全。

| DispatchState | 意义与 Chat adapter 归一化 |
| --- | --- |
| NOT_DISPATCHED | 本地 preflight/凭据失败；或未收到 response 时 HTTPX pool/connect timeout、ConnectError，能证明 provider generation request 尚未发送 |
| DISPATCHED_OR_UNKNOWN | read/write timeout/error、remote/proxy/未知 transport failure，或 response/stream 读取中断；不能证明 provider 没有执行 |
| HTTP_RESPONSE_RECEIVED | 明确 HTTP error response；或成功 response 的内容/structured postprocessing failure，携带实际 status |

收到 stream headers 后读取中断仍归 UNKNOWN：headers 不能证明生成失败或未计费。Structured 完成后失败保留原 LLMAttemptSummary 和 detail，不复制 full LLMResponse；它不是 transient candidate。直接 adapter 调用仍只有一次 HTTP send。

## 4. 默认 eligibility

| 条件 | 决策 |
| --- | --- |
| RATE_LIMITED + explicit HTTP 429 | 可重试 |
| PROVIDER_UNAVAILABLE + explicit HTTP 500/502/503/504 | 可重试；没有把 501/505/未知 5xx 认定为暂时性 |
| TIMEOUT + explicit HTTP 408 | 可重试 |
| TIMEOUT / PROVIDER_UNAVAILABLE + proven NOT_DISPATCHED | 可重试 |
| DISPATCHED_OR_UNKNOWN | 默认不重放；provider 可能已生成/计费 |
| Authentication/configuration/invalid/unsupported/context/cancelled | 不重试 |
| Malformed successful response | 不重试 |
| JSON/schema/empty/truncation postprocessing failure | 不重试，保留 completed-attempt facts |
| Successful response、refusal/filter | 立即返回成功，不再尝试 |
| Started stream 的任何失败 | 不重试 |

四类 transient 候选有独立显式 enable flags。Eligibility 不等于立即发送，仍须通过次数/时间/Retry-After bounds。没有允许 ambiguous replay 的开关或 semantic repair；C-005E1 的上层 fallback 只复用安全分类。默认 429 分类沿用已有 HTTP status normalization；未实现 provider-specific quota/billing code taxonomy，当前没有 production wiring。

## 5. Backoff、Retry-After 与预算

Immutable RetryPolicy 默认：max_attempts=3（包括第一次）、initial_backoff_seconds=0.5、max_backoff_seconds=8、max_elapsed_seconds=30、FULL jitter。所有界限有限；elapsed 必须正值，backoff 非负且 max≥initial。四类 transient flags 默认 true。

ExponentialBackoff 的第 n 次失败使用 ceiling=min(max_backoff, initial×2^(n−1), remaining_elapsed)。Full jitter 从 [0, ceiling] 选择延迟；可注入 unit-random source，测试不使用不可控随机。显式 NONE 只用于调用方选择的无 jitter 策略。超大 ordinal 的指数计算不会溢出。

```text
required_delay = max(normalized Retry-After, jittered policy backoff)
```

Adapter 支持标准整数 delta-seconds 和 timezone-aware HTTP-date；date 在 infrastructure 使用 UTC wall time 归一化一次为 duration，之后编排只用 monotonic time。无效 hint→None；负数/过去 date→0；特别大的合法整数仍提供禁止提前发送的长等待。只对 429/408/5xx 携带 hint，不缓存原 header，也不在 adapter sleep。

Retry-After 不受 max_backoff 缩短；如果无法在 remaining elapsed 内等待并开始下一次尝试，返回最新失败，零次额外发送。Policy delay 也不能触达 deadline；最多尝试次数和 elapsed window 必须同时满足。Sleep 后重新检查 monotonic deadline，scheduler oversleep 不触发迟到发送。

Elapsed window 从 wrapper 调用开始，包括首尝试、凭据查找和所有等待；它控制**开始后续尝试**，不强行取消已进行的 generation/成功响应。HTTPX per-phase timeout 仍控制每次 transport；这不是整个 logical operation 的硬 cancellation deadline。

## 6. Generate、structured 与 stream

generate：success 立即原样返回；failure→单一 decide_retry→optional wait→同请求下一次。最终抛出最新 normalized LLMFailure，不保留前一次 exception/context。已完成 structured failure 的 factual usage/model/finish/latency 留在安全 attempt summary；JSON repair、重播 hoping-for-different-output 均不存在。

```text
attempt 1: pre-start transient FAILED (internal)
→ close attempt iterator → backoff
attempt 2: STARTED → TEXT_DELTA / USAGE_UPDATE → COMPLETED or FAILED
```

Pre-start 可重试失败不向 application 暴露 Failed/Started。所有候选耗尽只交付一个最终 Failed。成功的后续尝试只暴露一次 Started；**Started 一旦暴露，即使尚无正文也永久禁止重放**。Post-start timeout/disconnect/EOF/malformed chunk→一次 Failed，无 Completed。没有 prefix matching、resumption、合并多次尝试正文或全文 buffer。

TextDelta 仍是 streaming content source of truth；LLMStreamCompletion 仍仅为 terminal metadata。UsageUpdate 和 terminal usage 是当前物理流的 factual snapshots，不能相加或跨 attempts 累积；缺失 None，不虚构 zero。不会丢弃 completed-attempt accounting facts 后重试，因为已完成 summary 本身不可重试。C-005D2 将定义 durable per-attempt accounting；本任务没有自造 cumulative usage。

## 7. Cancellation、资源和安全诊断

CancelledError 在 provider await 和 backoff sleep 自然传播，不改成 failure、不再尝试。Stream 取消没有 synthetic Failed/Completed。Wrapper 使用 aclosing，在等待前关闭失败 attempt；放弃 wrapper iterator 的调用方也必须显式 aclose/aclosing。Wrapper 借用 gateway，不接管共享 HTTP client 的关闭责任；调用方先结束 in-flight operations 再关闭 adapter。

每次物理尝试通过 adapter 的 CredentialProvider.resolve；orchestrator 不读取/缓存明文。Adapter 的 Authorization/cookie scrub 保持，旧 direct single-attempt tests 继续验证。Optional observer 只获取上述闭合安全诊断，正常日志可使用现有 StructuredLogger 的固定 reason label + InvocationId trace；没有扩展 arbitrary log payload fields，ordinal 通过 observer 直接检查。稳定原因包括 rate_limited、transient_http_failure、not_dispatched_transport_failure、ambiguous_dispatch_not_replayed、attempt_limit_reached、elapsed_budget_exhausted、retry_after_exceeds_budget、permanent_failure、started_stream_not_replayable 和 success。

Retry/fallback 可能增加 provider quota/paid attempt 消耗，不能把 logical invocation 当作唯一计费尝试。C-005E1 没有新增 database migration，也没有 repair、circuit breaker、parallel/hedged execution、tools、Director/Agent/Memory 或真实 API tests。

## 8. 离线证明

[test_llm_execution.py](../../tests/core/test_llm_execution.py) 覆盖 explicit 429/503、proven connect vs uncertain read/write、same invocation/request、late credentials、attempt/time caps、Retry-After 两种语法/无效/过去/超长值、jitter/cap、cancel/oversleep，以及真实 adapter 的 pre-start hidden retry 与 post-start 无重放。Structured generation 经 429 后的 parse/schema/empty/truncation failure 仍保留实际 usage；refusal/filter 原样成功。序列化 closed records、repr 和 StructuredLogger logs 排除 credential/prompt/output/reasoning/raw-body canaries。

C-005A/B/C1/C2 和完整 Stage 0–3/architecture regressions 继续执行。新测试没有真实 sleep seconds 或外部网络。没有 UI/desktop 改动、无需 GUI smoke。没有新增依赖、migration 或 accounting persistence；真实提供方兼容性仍未实测。

## C-005D2A：独立 accounting lifecycle

ExecutingModelGateway 接受 AttemptAccountingSink、injected UTC wall clock 与 non-raising safe diagnostic consumer。每个实际 ordinal 先 durable START 再调用 single-attempt gateway，terminal 后 FINALIZE；包括 logical stream 隐藏的 pre-Started failures。RetryRecord 仍是 retry decision metadata，不用它计数 attempts。Streaming 只保留 latest factual usage snapshot，不保存 TextDelta，不累加 snapshots；structured post-processing failure 使用 content-free LLMAttemptSummary。

START write failure → AccountingInfrastructureError → 零 provider calls。FINALIZE write failure → 原 outcome/对象与 cancellation 保持 → 固定 accounting_persistence_incomplete CRITICAL operational event → 禁止 attempt N+1（包括 429/503 和 hidden streaming retry）。没有因为 ledger failure 而重放 generation 或改 provider。未 final 的 START 保持 INCOMPLETE 与 unknown possible exposure；restart 不自动 repair/replay。Logical terminal 单独观察，backoff cancellation 不修改最后一次物理 FAILED。详见 [accounting](LLM_ACCOUNTING.md)。D2A historical pricing 独立于 D2B preflight upper bounds 和 HARD admission。

## C-005D2B：预算优先于 retry permission

ExecutingModelGateway 的 budget_guard 参数替代 accounting sink，不能同时配置二者，以保证 reservation + START 同事务。每 ordinal 在 provider 前 admit，同 requested ModelRef、同 immutable request、同 InvocationId，独立 reservation。Denied attempt 无 START/provider call，终止为 typed local BudgetAdmissionError，不是 LLMFailure/provider retry；保留已有 physical outcome，retry denial 的 logical terminal 为 LOCAL_ERROR。

含 hidden pre-STARTED attempts 在内，每次 retry 重新授权。Unknown first exposure 保留 hold；proven NOT_DISPATCHED 可释放。FINALIZE/settlement failure 或 bound violation 原样保留 response/failure/completion/cancellation，安全 severe diagnostic 表达 integrity degradation并禁止下一 attempt；本地 DB failure 永远不是 provider replay 理由。STARTED 后 no retry、TextDelta 内容边界、latest snapshot 非 additive 不变。无匹配 enabled budget 时不要求 bounder，D1 行为保持。详见 [LLM_BUDGET_GUARD.md](LLM_BUDGET_GUARD.md)。
## C-005E1：retry 与 fallback 的组合

Retry 是同一 candidate；fallback 是显式 RoutePolicy 中的下一 candidate。两者复用本文件的 typed failure classifier，router 不复制 HTTP heuristics。Candidate 有独立 max-attempt/backoff counter，但一个 routed Invocation 共用 monotonic deadline 与全局 ordinal：A1/A2→B3。

Fallback 不重置 deadline。Deadline 只限制启动新 attempt，不强制取消已经 dispatch 的调用。某 candidate 的 Retry-After 无法放进剩余窗口时，停止该 candidate retry；在 route deadline 仍有效且 policy 允许时，可立即尝试 unrelated candidate。完整 eligibility 和 stream STARTED lock 见 [LLM_ROUTING.md](LLM_ROUTING.md)。

## C-005E2：529 与 Anthropic stream dispatch

显式 transient HTTP set 现在包含 529。Anthropic adapter 只报告 status、normalized error 和 Retry-After；sleep/retry 仍完全由 ExecutingModelGateway 控制，并受 attempt cap 与共享 route deadline 限制。每次 adapter 调用只执行一个 HTTP attempt。

HTTP 200 后的 Anthropic SSE `error` 没有可证明的 HTTP response status，归一化为 `DISPATCHED_OR_UNKNOWN`；因此不自动 replay，也不跨 provider fallback。合法 `message_start` 暴露 Started 后继续沿用既有永久 route lock。terminal refusal 是成功 completion。详见 [ANTHROPIC_MESSAGES_ADAPTER.md](ANTHROPIC_MESSAGES_ADAPTER.md)。

## C-005E3：Gemini execution classification

Gemini adapter 每次 generate/stream 调用只做一个 HTTP attempt；outer execution/routing policy 仍唯一决定 retry/fallback。稳定 machine code 区分 rate limit 与 provider-proven quota exhaustion。Quota exhaustion 不对同 candidate retry；只有 `REJECTED_BEFORE_EXECUTION` 的 safe PROFILE policy 才能切候选。429/5xx/timeout 继续走既有 dispatch-aware retry classifier。

Gemini SSE `error`、EOF before semantic completion 和 protocol/state failure 不会产生 StreamCompleted。SSE error dispatch 为 unknown，Started 一旦交付永久锁定 candidate。Policy/content filter 是成功 terminal，不触发 retry/fallback。Continuation tamper 是本地 `CONTINUATION_STATE_INVALID`，在 credential resolve 和 HTTP 之前失败。

## C-005E4：OpenAI Responses execution classification

OpenAIResponsesGateway 每次 generate/stream 调用只发送一个 `POST /v1/responses`。HTTP status 与
documented machine type/code 归一化 authentication、permission/configuration、invalid/context、rate、
quota/billing、timeout 和 availability；sleep/retry/fallback 仍只由通用 execution/router 决定。

Continuation digest/layout mismatch 是本地 `CONTINUATION_STATE_INVALID`，发生于 secret resolve 与
network 前。Explicit refusal/filter 是成功 terminal；structured parse/schema failure 是 completed
post-processing failure，均不重试或 fallback。Streaming 在合法 `response.created` 后暴露 STARTED，
之后的 SSE error、failed/incomplete protocol violation、malformed known event、tool output 或 EOF 都不能
重放。Provider-proven pre-execution quota rejection 可按已有 policy 考虑下一 candidate；ambiguous
dispatch、accounting/budget integrity degradation 和 STARTED lock 始终优先终止。

## C-005E5：production execution ownership

生产 composition 只把 single-attempt adapters 注入通用 execution/router。HTTP clients 按 configured model 创建一次并由 runtime 关闭；adapter 不自行 retry。一次 routed Invocation 继续共享 deadline 与 global ordinal；每个 candidate/retry 重新执行 credential precheck、budget admission/reservation 和 accounting START。启动、config load 与 credential sync 不生成 provider request。可选真实 smoke 必须显式 opt-in，正常测试与 CI 没有付费流量。详见 [LLM_PRODUCTION_COMPOSITION.md](LLM_PRODUCTION_COMPOSITION.md)。
