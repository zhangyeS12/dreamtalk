# Model Registry, Purpose Routing & Safe Provider Fallback — C-005E1

状态：已实现 provider-neutral、deterministic、opt-in 的 operational Model Registry 与路由层。全部验证使用 offline fake、可控 gateway 和临时 SQLite；没有真实 provider 调用、production default registry 或新 migration。

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

`FAST` / `BALANCED` / `BEST` 是安装配置的产品 policy labels，不是 LivingWorld 对模型速度或质量的客观排名。每个 `PurposePolicy` 明确给出 open `LLMPurpose`、profile、ordered candidates、policy identity 与允许的 fallback reasons。缺 purpose-specific policy 时仅可使用显式配置的 default policy；engine 不制造候选链。

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

没有 Anthropic/Gemini/Responses adapter、tools、vision、provider discovery、online pricing、dynamic ranking、circuit breaker、semantic repair、Director、Agent、Memory 或 UI。Production registry loading/bootstrap composition 留给后续任务；C-005E1 只建立可验证的中立 contract 和 deterministic execution baseline。
