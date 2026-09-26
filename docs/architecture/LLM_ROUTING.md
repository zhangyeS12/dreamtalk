# Model Registry, Purpose Routing & Safe Provider Fallback — C-005E1

状态：已实现 provider-neutral、deterministic、opt-in 的 operational Model Registry 与路由层；C-005E2 已用独立 Anthropic 原生 Messages adapter 验证不同协议可以进入同一路由管线。全部验证使用 offline fixtures、可控 gateway 和临时 SQLite；没有真实 provider 调用、production default registry 或新 migration。

```text
Application → immutable RoutePlan → routed invocation context
→ ExecutingModelGateway (retry/accounting/budget)
→ one configured ModelGateway → provider adapter
```

## 1. 身份与配置边界

`ProviderId` 是 configured provider **instance**，例如 `openai-main`、`deepseek-main`、`local-lmstudio`。`AdapterKind` 是 protocol family，例如 `openai-compatible`、`anthropic`、`gemini`。多个 provider instances 可以共享同一个 adapter kind；二者不相等，也不改写历史 accounting identity。

`ModelRegistry` 是 immutable/read-oriented operational configuration：registered provider、exact `ModelRef`、enabled state、既有 `ModelCapabilities`、optional trusted `ModelUsageLimits` 和 optional existing `RequestedPricingEnvelope` reference。Registry 不保存 secret、client、endpoint、price table、prompt、world/content/knowledge/runtime state，也不进入 `.lwcontent` 或 WorldEvent。Gateway client 通过独立 `ConfiguredGateways`/`GatewayResolver` 注入，由 infrastructure/bootstrap 管理生命周期。

Registry 只做 exact typed lookup，不解析 model/provider 名称，不调用 discovery API。`ANTHROPIC` / `GEMINI` adapter-kind seam 不等于已实现这些 adapter。PricingCatalog 继续拥有价格事实；registry 只复用 D2B 已有 limits/envelope contract。

## 2. Profile、purpose 与 RoutePlan

`FAST` / `BALANCED` / `BEST` 是安装配置的产品 policy labels，不是 dreamtalk 对模型速度或质量的客观排名。每个 `PurposePolicy` 明确给出 open `LLMPurpose`、profile、ordered candidates、policy identity 与允许的 fallback reasons。缺 purpose-specific policy 时仅可使用显式配置的 default policy；engine 不制造候选链。

显式 `ModelRef` 选择默认只有该 exact model。只有调用方同时提供以该 model 为首项的 explicit fallback policy，才可改变 model。Profile selection 明确授权使用对应配置链。

`resolve_route` 是纯 deterministic resolution，不调用 provider。它形成 immutable `RoutePlan`：InvocationId、purpose、selection/profile、policy identity、ordered eligible candidates、typed requirements、allowed reasons 和 pre-execution skips。同 registry、configuration、request requirements 产生同 plan。

Capability filtering 使用 explicit `ModelCapabilities`：text generation、streaming 和 `StructuredOutputMode`。结构化请求可声明接受 native schema / JSON-object local validation 的集合；structured streaming 仍然拒绝。Unknown、disabled、non-streaming 或 structured-mode-incompatible model 在 provider 调用前被排除，不创建 accounting attempt。没有 model-name heuristic。

## 3. Retry、fallback 与 invocation identity

```text
retry    = same candidate, same semantic request
fallback = next explicitly configured candidate
```

两者共享 C-005D1 的 normalized failure classifier，router 不复制 HTTP status heuristics。每个候选拥有独立 retry count/backoff sequence；一个 routed call 只有一个 monotonic deadline 和一个 invocation-global attempt ordinal：

```text
Candidate A: physical attempts 1, 2
Candidate B: physical attempt 3
```

Fallback 不重置 deadline。Deadline 只阻止启动新 attempt，不强制取消已经 dispatch 的 generation。Candidate A 的 Retry-After 无法放进剩余窗口时停止 A 的 retry；只要 route deadline 仍有效，policy 可以立即尝试 unrelated candidate B。

每次 fallback 只替换 request 的 `model`。InvocationId、purpose、messages、schema、stop、output cap、correlation 和 metadata 保持不变。没有 prompt repair、parameter downgrade、parallel/hedged execution、score、randomness、load balancing 或 circuit breaker。

### Fallback eligibility

| 当前结果 | RoutePolicy 可允许下一个候选？ |
| --- | --- |
| explicit HTTP 408/429/approved 5xx，当前候选已耗尽 retry | 是，typed reason |
| proven NOT_DISPATCHED timeout/unavailable | 是，typed reason |
| configured gateway missing before attempt | 是，typed candidate-unavailable reason |
| candidate pre-filtered disabled/capability mismatch | 不调用；记录 plan skip，exact-only selection 失败 |
| DISPATCHED_OR_UNKNOWN | 否 |
| success / refusal / content filter | 否，成功终态 |
| JSON parse/schema/empty/truncation failure | 否 |
| authentication/configuration/invalid/context/malformed/unsupported | 否 |
| accounting start/finalize failure | 否 |
| budget state uncertain/integrity degraded/bound violation | 否 |
| cancellation | 否 |

Missing configured gateway 是 local routing configuration state，不伪装成 provider HTTP failure。Exact selection 不会因为缺 gateway 偷换 model；profile 或 explicit chain 也必须明确允许 `CANDIDATE_UNAVAILABLE`。

## 4. Budget admission facts 与 route policy

Budget repository 只返回 transaction-local facts，不决定 model routing。成功结果确认 admission/atomic reservations 是否已提交；拒绝时 `BudgetAdmissionSummary` 证明没有 START/reservation commit。两种结果都包含全部 matching HARD policies 的安全 typed facts：budget identity/scope、reason、currency/limit、known spend、held、remaining、requested upper bound、unbounded exposure 和 integrity state。没有 messages、response、reasoning、credentials、raw SQL/exception。

准入会评估全部 matching HARD policies；integrity degraded 和 uncertain exposure 优先于 ordinary affordability。拒绝事务不写 START 或 reservation。只有 PROFILE routing 且 policy 明确允许时，`EXCEEDED` / `UNVERIFIABLE` / `CURRENCY_UNSUPPORTED` 可以切候选。Global/purpose scope 本身不禁止 fallback：下一候选仍以自身 requested `ModelRef` 重新执行完整 upper bound、pricing、all-budget admission、reservation 与 accounting START transaction。没有复用 reservation，也没有跳过 global policy。

`STATE_UNCERTAIN`、`INTEGRITY_DEGRADED`、bound violation、persistence/finalize failure 都终止 invocation。缺 complete admission summary 的 legacy/custom sink fail closed。

## 5. Streaming visibility boundary

Pre-STARTED candidate failures可隐藏并 fallback。Application 只看到一个 logical stream：一个 `StreamStarted`、ordered `TextDelta`/usage snapshots 和一个 terminal。`STARTED` 一旦暴露即锁定 route；之后的 failure 原样交付，不换 provider、不合并正文。Refusal/content-filter completion 是成功 terminal。Cancellation 立即传播并关闭 borrowed iterator。

## 6. Safe diagnostics

`RoutingRecord` 是 non-persistent typed trace：InvocationId、purpose/profile/policy、candidate ModelRefs、selected/skip/fallback reason、hop count。它没有 request、prompt、output、schema、reasoning、credentials 或 raw provider data；observer failure 不改变执行结果。Registry/route trace 不新增数据库表。

## 7. Deferred scope

Anthropic Messages、Gemini Interactions 和 OpenAI Responses native adapters 已分别在 C-005E2/E3/E4 实现；tools、vision、provider discovery、online pricing、dynamic ranking、circuit breaker、semantic repair、Director、Agent、Memory 或 UI 仍未实现。Production registry loading/bootstrap composition 留给后续任务。

## 8. C-005E2 跨协议证明

Registry 用 `AdapterKind.ANTHROPIC` 标识协议族，ProviderId 仍是配置实例身份，capabilities 来自显式 Anthropic profile。受控 route 证明 OpenAI-compatible candidate 的 503/529 类安全 transient attempts 耗尽后，可按 policy 切换到 Anthropic native candidate；同一 InvocationId 延续，global ordinal 不重置，每个 candidate 都重新执行 budget admission、accounting START/FINAL 和 settlement。

Anthropic SSE `event: error` 使用 `DISPATCHED_OR_UNKNOWN`，不会触发 provider shopping；terminal refusal 是成功结果，也不会 fallback。Anthropic adapter 明确禁用 server-side fallback，避免 provider 在 dreamtalk budget/attempt identity 之外更换执行目标。协议细节见 [ANTHROPIC_MESSAGES_ADAPTER.md](ANTHROPIC_MESSAGES_ADAPTER.md)。

## 9. C-005E3 Gemini quota 与三协议 route

Gemini quota exhaustion 只有在稳定 machine code 明确表示 quota、`dispatch_state=REJECTED_BEFORE_EXECUTION`、没有 completed attempt facts，且 PROFILE `RoutePolicy` 显式允许时，才可作为 `QUOTA_EXHAUSTED` 切换候选。同 candidate 不 retry；429 rate limiting 与 quota exhaustion 保持不同语义。任何 unknown dispatch、已暴露 Started、accounting/budget integrity failure 或非安全 denial 仍终止 route。

OpenAI-compatible → Anthropic → Gemini 的离线 route 证明继续使用一个 InvocationId、共享 monotonic deadline 和 invocation-global ordinals。Gemini 候选独立执行 pricing/budget admission、reservation、accounting START/FINALIZE；前一候选的 reservation、Retry-After 或 continuation artifact 不会被复用。Gemini continuation 绑定 ProviderId 而不绑定 model alias，因此同 configured provider 内显式模型切换仍可 stateless 重建；其他 protocol family 只把它视为 opaque metadata。

## 10. C-005E4 四协议 route

Registry 新增显式 `AdapterKind.OPENAI_RESPONSES`。它与 openai-compatible、Anthropic、Gemini
并列；router 仍只解析 exact ProviderId/ModelRef/AdapterKind 配置，不从 model name 推断协议。

离线 route 覆盖
`openai-compatible → anthropic → gemini → openai-responses`：同一个 InvocationId 延续，physical
attempt ordinal 为 1/2/3/4，每个 candidate 重新执行 budget admission、reservation、accounting START
和 finalization。Responses adapter 没有 routing-specific branch；retry/fallback 继续只依据通用 typed
failure、shared deadline、dispatch certainty、budget/accounting integrity 和 STARTED lock。

Response ID 只是 provider diagnostic，不参与 route identity，也不能替代 dreamtalk-managed history。
完整协议边界见 [OPENAI_RESPONSES_ADAPTER.md](OPENAI_RESPONSES_ADAPTER.md)。

## 11. C-005E5 production wiring

严格配置 v1 将 exact ModelRef、AdapterKind、capabilities、route order 与 allowed fallback 建入真实 registry/router。生产应用只接收 `RoutedModelGateway`，不存在按 model-name 猜 provider 或绕过 budget/accounting 的直接 client。缺 credential 是 provider 前的 `CREDENTIAL_UNAVAILABLE`；explicit selection 不换模型，profile route 仅按显式 policy 处理 locally unavailable candidate。Production registry/bootstrap 已完成；dynamic ranking、hot reload、provider discovery、tools、Director、Agent、Memory 与 settings UI 仍 deferred。详见 [生产组装](LLM_PRODUCTION_COMPOSITION.md) 与 [Stage 4 验收](STAGE4_ACCEPTANCE.md)。
