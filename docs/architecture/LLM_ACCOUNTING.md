# LLM Accounting — C-005D2A through C-005E2

状态：已实现离线验证的物理 attempt 账本、effective-dated pricing、费用估算、invocation 汇总，以及跨 routed candidates 的共同 lifecycle。C-005E2 增加 Anthropic cache-read/cache-write TTL/reasoning facts，但仍使用同一账本。没有 production catalog、真实付费 API 验证、在线价格抓取或 UI；实现复用现有 SQLAlchemy/Alembic/SQLite，无新增依赖。

## 1. 永久边界

```text
usage fact != price configuration
estimated cost != provider invoice
logical invocation != physical attempt
missing usage != zero usage
reasoning tokens are not automatically additive
historical pricing uses a persisted immutable price snapshot
```

未知使用量、部分使用量和可能计费暴露必须保持可见。历史费用估算不是 hard spend limiter；preflight trusted upper bounds/reservations/enforcement 已在 C-005D2B 实现，见 [LLM_BUDGET_GUARD.md](LLM_BUDGET_GUARD.md)。

## 2. 生命周期与失败语义

[ExecutingModelGateway](../../services/core/src/livingworld/application/llm_execution.py) 接受独立的 [AttemptAccountingSink](../../services/core/src/livingworld/application/llm_accounting.py)、注入的 UTC wall clock 和安全诊断 consumer。既有 RetryRecord 仍是重试决策，不是物理 attempt 记录；backoff deadline 复查可能为同一个 ordinal 产生多个 RetryRecord。Accounting 只在实际 attempt 前 START，完成后 FINALIZE，包括被 logical stream 隐藏的 pre-Started attempts。

```text
durable START(INCOMPLETE)
→ one single-attempt provider execution
→ durable FINALIZE(safe facts + estimate/snapshot)
→ retry decision or logical invocation termination
```

| 故障 | 行为 |
| --- | --- |
| START 写入失败 | 零 provider 调用；抛出 AccountingInfrastructureError(accounting_start_persistence_failed)，不是 LLM/provider failure；不重试、不切换 provider/model |
| FINALIZE 写入失败 | 不重放请求；原样返回原 LLMResponse、原 StreamCompleted 或原 normalized failure；CancelledError 继续传播；禁止下一次自动 attempt |
| START durable，FINALIZE 未 durable | 保持 INCOMPLETE、无 final facts、无 estimated money；可能计费，禁止当作零费用或成功 |
| process crash / restart | 不自动补写 success/failure/zero，不重放 provider；incomplete reconciliation deferred |

Provider/application outcome 与 accounting integrity 是独立维度。SUCCESS + DEGRADED 有效。Immutable response/failure/completion 不被替换，也不将本地故障塞进 provider diagnostics；通过独立 AccountingDiagnostic consumer 发出固定的 `accounting_persistence_incomplete` CRITICAL 结构化事件。START 使用 `accounting_start_persistence_failed`。诊断只有固定 event、typed invocation identity/ordinal；基础设施日志输出 timestamp/level/component/event/trace_id，不接受 SQL exception、连接信息、prompt、output、credentials 或 HTTP data。Consumer 由 trusted composition 提供，契约要求 non-raising；其异常也不能替换 provider outcome 或触发 provider retry。

同一 InvocationId 的所有 attempts 使用独立、顺序 ordinal。调用方必须为每次新的 logical execution 创建新的 InvocationId；observer delivery 幂等不是 generation-request 重放缓存。Ledger 拒绝向已终止 invocation 增加新 ordinal。重复 START/FINALIZE delivery 必须具有相同事实，否则 typed conflict；不会覆盖历史 rows。

`complete_invocation` 在最后一个 attempt 行的独立 nullable `invocation_outcome` 中记录 logical terminal outcome，重复同值幂等。它不改变物理 outcome、usage 或价格。在 backoff 中取消时，物理 attempt 可仍是 FAILED，而 logical outcome 是 CANCELLED；不能把最后一次 attempt 的状态直接当作 invocation 结果。Logical terminal persistence failure 也独立诊断，缺失 terminal 保持 unresolved。FINALIZE 失败后不再尝试补写 logical terminal。

## 3. 安全事实和 normalized usage

AttemptStart：InvocationId、ordinal、现有开放 LLMPurpose、requested ModelRef、aware UTC start。

AttemptFacts：aware UTC finish、monotonic physical-attempt latency、typed outcome/dispatch/failure/finish/stream outcome、实际 reported ModelRef（若已知）、normalized usage/completeness、实际 processing tier（若已知）。不保留 request metadata、messages、content、structured payload、reasoning 或 HTTP objects。可选 provider request ID 的类型有界，本实现刻意不持久化该字符串，避免未知 gateway 反射正文。

| 使用量 | 规则 |
| --- | --- |
| input/output/total | 原字段保留，未报告为 None，不补算 total |
| cached_input_tokens | OpenAI cached_tokens 或 DeepSeek factual cache-hit |
| cache_write_input_tokens | OpenAI factual cache_write_tokens；缺失为 None |
| uncached_input_tokens | DeepSeek factual cache-miss；OpenAI 仅在 input、cached、cache-write 都已知时计算 input-cached-write |
| reasoning_output_tokens | factual completion reasoning breakdown，通常是 output 的子集 |

不接受负数/bool，不 clamp 或修复不可能的 partition。DeepSeek hit+miss 在全部已知时必须等于 input；同时报告的 cached/hit 必须一致。已知 input 分区之和不可超过 input；完整分区必须匹配。Reasoning 不得超过已知 output。Allowlisted numeric details 可保留，任意 provider dictionaries/private metadata 被丢弃。空 usage/只有不可信 metadata 的 usage 仍视为未知。

| Completeness | 含义 |
| --- | --- |
| FINAL | 完成的 provider generation/stream，有 factual terminal/latest usage；包括 refusal/filter 和 completed structured post-processing failure |
| PARTIAL | 中断/取消/消费者关闭前观察到 factual usage snapshot，未证明其为完整 terminal usage |
| UNKNOWN | 未报告可信 usage；没有 fabricated zeros |

UsageUpdate 是 snapshot，不是 additive delta。Stream 仅保留最新 snapshot，completion.usage 优先；terminal 无新 snapshot 时可以使用最近 snapshot。账本不会保存或累积 TextDelta。中断无 completion；取消不因 accounting 变成 FAILED/COMPLETED。LLMAttemptSummary 与 LLMStreamCompletion 保持不同 lifecycle 类型，前者给 completed non-streaming post-processing failure 提供安全事实。

## 4. 价格配置和确定性估算

[llm_pricing.py](../../services/core/src/livingworld/application/llm_pricing.py) 定义 PricingCatalog、PricingSchedule、PricingVariant、RateLine、PriceQuote/Snapshot 和 Money。InMemoryPricingCatalog 的数据由调用方显式传入；空 catalog 产生 PRICE_UNKNOWN，fixture 不是隐含 production catalog。Provider adapter 不计算或持久化价格；ModelRef/LLMResponse 没有 price 配置。

Schedule 由完整 provider/model identity、schedule/version ID、currency、aware UTC half-open effective interval、source/provenance label 和 immutable variants 构成。历史选择使用记录的 **attempt START UTC**，不调用当前 wall clock，不使用本机本地时区。UTC windows 由显式 weekdays（Monday=0）与 half-open 分钟区间组成，可组合多个区间，不支持隐式跨午夜或 pricing DSL。

Variant 仅支持 factual input-token min/max-exclusive、实际 processing tier 和显式 UTC windows。缺少必要输入量/tier/meter 时返回 PRICING_CONTEXT_INCOMPLETE；不由字符串长度估算 tokens，不由 model name/request preference 猜 tier。Adapter 只接受文档中的实际 response tier：default/flex/scale/priority/fast；auto/未知字符串为 None，不隐式转换 alias。Tier 的计价匹配由 catalog 明确配置。

Reported model 有有效映射时优先；explicit exact ModelAlias 可以配置映射。Unknown reported model 不自动回退 requested；只有明确 `allow_requested_fallback` alias policy 允许该回退。没有 substring heuristics。零匹配 PRICE_UNKNOWN；多个匹配抛 PricingConfigurationError(ambiguous_pricing_variants)，不 first-match。缺失 context 可能影响唯一选择时不猜。

Meters 包括 INPUT(total)、UNCACHED_INPUT、CACHED_INPUT、CACHE_WRITE_INPUT、CACHE_WRITE_5M_INPUT、CACHE_WRITE_1H_INPUT、OUTPUT(total)。总 input 与其分区不可并列收费；aggregate cache-write 与 TTL cache-write meters 不可并列收费；TTL pricing 必须同时定义 5m/1h 两种 rate。总 output 与 reasoning/non-reasoning 分区不可并列收费。只有显式选择 NON_REASONING_OUTPUT + REASONING_OUTPUT 的 schedule 才将输出分区分别估价，NON_REASONING_OUTPUT 使用 factual output-reasoning。通常仅 OUTPUT 收费，reasoning 是诊断明细。

每个 line item 保留 meter、quantity、精确 rate、unit_tokens、currency/subtotal。Money 为 currency + Decimal，持久化 SQLite TEXT，禁止 float。金额/费率最多 9 位小数、40 位有效数字；计算和跨 attempt 汇总使用独立 precision=100 Decimal context，不受外部 context 影响。每行按 `quantity * rate / unit_tokens` 计算，**ROUND_HALF_EVEN 到 1e-9**，总额为已取整行金额之和。同货币相加，不同 currency 分组，绝不自动汇兑。

成功 PRICED 的行持久化完整 immutable schedule、selected variant、recorded UTC/input/tier context、rates、source/version、line items 与 total。读取历史行无需当前 catalog 或网络，重复 FINALIZE 不重新计价。

## 5. 状态、查询与汇总

| CostStatus | estimated money |
| --- | --- |
| PRICED | 明确 currency + 估价，允许 factual rounding 后的零 |
| PRICE_UNKNOWN / PRICING_CONTEXT_INCOMPLETE | None |
| USAGE_UNKNOWN（HTTP response received、无 usage） | None，未知暴露仍在 summary 中可见 |
| POSSIBLY_BILLED_UNKNOWN（dispatch unknown 或 INCOMPLETE） | None，可能计费 |
| USAGE_PARTIAL | None；保存 partial facts，不冒充 settled estimate |
| NOT_DISPATCHED | None + 明确无 provider-generation exposure，不伪造 usage/price |

LedgerQuery 支持 InvocationId、UTC since-inclusive/until-exclusive、provider、requested 或 reported model、现有 LLMPurpose。`summarize` 给出 physical attempt count、known input/output totals（全部未知为 None）、known estimated money by currency、partial/unknown usage、unknown cost、possible billing exposure、incomplete attempts 和 durable logical terminal outcome。跨多个 invocation 的 generic 汇总不声称有一个共同 final outcome。Known $0.04 + unknown attempt 必须展示 known money 与 unknown/exposure flags，不能声称 confident total=$0.04。

## 6. 持久化与隔离

[0009_llm_accounting](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0009_llm_accounting.py) 是唯一新增迁移，down_revision=0008_native_content_packages。独立 AccountingBase 的 `llm_attempts` 以 (invocation_id, attempt_ordinal) 为 composite PK，存 START/FINALIZE facts、logical terminal metadata、cost status、exact money 与 pricing snapshot，具有 lifecycle/estimate/ordinal/status CHECK 和 time/purpose/provider-model indexes。SQLite NULL 表示尚未形成 facts/snapshot，区别于 JSON null。

[SqlAlchemyUsageLedger](../../services/core/src/livingworld/infrastructure/persistence/llm_repository.py) 使用已有 app-data Database/session factory、独立 BEGIN IMMEDIATE transaction 与 closed typed codec。没有 world/content foreign keys、provider IO、startup reconciliation 或第二迁移引擎。0008→0009 失败全部回滚；兼容 detector 只按 Alembic cursor 验证形状，保留所有历史兼容审计行。Downgrade 必须另行 review。

Accounting 是 operational metadata，不是 WorldEvent/WorldTruth/CharacterBelief/PlayerKnowledge/Memory/authored content。没有 canonical command、世界变化或 prompt context 能力，不进入 `.lwcontent`，未来 `.lworld` 默认也不得包含。验证通过 raw accounting rows/SQLite 文件 canary 扫描、[populated knowledge isolation](../../tests/application/test_llm_accounting_isolation.py) 的 world/knowledge/content 无变化与 closed codec 拒绝 request/response/credential 类型证明。

## 7. 来源与受控算例

2026-09-18 阅读官方 [OpenAI pricing](https://developers.openai.com/api/docs/pricing)、[prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)、[Chat usage/tier reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)、[DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing)、[DeepSeek Chat usage](https://api-docs.deepseek.com/api/create-chat-completion/)。这些页面可变化；访问日期不是生产费率生效声明。Tests 无网络。DeepSeek 文档通过官方 public HTTP 读取，未调用生成 API。

受控 [accounting tests](../../tests/core/test_llm_accounting.py) 使用测试 provider/model identity 和 source-dated rate examples，不部署 production catalog：

- OpenAI 示例 ordinary/cache-read/cache-write/output 每百万 USD 4/0.4/5/20；700/200/100 输入分区与 50 output（含 20 reasoning）→ estimated **USD 0.004380000**。Long 示例 8/0.8/10/30，9700/200/100 + 50 output → **USD 0.080260000**。测试阈值 10000 是受控边界，不声称为官方 context threshold。
- DeepSeek Flash 示例 cache-miss/cache-hit/output：peak 每百万 USD 0.3/0.006/1.2、off-peak 0.15/0.003/0.6。800 miss + 200 hit + 50 output → peak **USD 0.000301200**，off-peak **USD 0.000150600**。UTC Monday–Friday 01:00–04:00、06:00–10:00 为 source-dated peak examples，其他时间 off-peak；测试边界/周末。
- Retry 429 无 usage + priced successful generation → 两个 records，known USD 0.004380000 + unknown exposure=true；三个 priced attempts 分别 USD/USD/EUR → known USD 0.008760000、EUR 0.004380000，不合并货币。

## 8. Deferred

C-005D2B 已实现可信 usage/cost bounds、persistent reservations 与 opt-in enforcement；C-005E1 已实现 deterministic routing/fallback。Production catalog publication/update、incomplete reconciliation、billing/balance APIs、repricing workflows、dashboard、semantic repair、Director/Agent/Memory 全部 deferred。不进行真实付费模型验证，不设置 production default accounting/gateway/registry wiring。

## C-005D2B：同事务预算边界

Budgeted execution 使用 SqlAlchemyBudgetGuard.admit，ALL matching HARD reservations + START 同一 BEGIN IMMEDIATE transaction；不能叠加另一个独立 accounting sink。Final accounting + settlement 同事务；失败 rollback，START 保持 INCOMPLETE、hold 保持，原 response/failure/completion/cancellation 不改写、不 replay/retry。Known final accounting + stale held state 为 integrity degraded，future HARD fail closed；正常可信 unknown hold 是 bounded exposure，不能解释为 zero。详见 [LLM_BUDGET_GUARD.md](LLM_BUDGET_GUARD.md)。

Budget matching/window queries **只用 requested ModelRef**。LedgerQuery 的 requested OR reported 筛选保留为 analytics，不能复用为准入 SQL。Reported model 可安全映射 actual pricing，但不重新归属预算；alias HARD 需要 exhaustive trusted pricing envelope。当前 head 为 [0010_llm_budget_guard](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0010_llm_budget_guard.py)；0009/旧 accounting rows 与 audit 原样保留，operational budgets 不进入 WorldEvent/content/knowledge/package。
## C-005E1：跨候选的一个 logical lifecycle

Route context 延迟 logical terminal，直到整个 route 成功或最终失败；candidate failure 不会提前关闭 ledger。Retry 与 fallback 共用 InvocationId 和 invocation-global ordinal，所以 A1/A2→B3 继续满足 (invocation_id, attempt_ordinal) uniqueness。每个 START 的 requested ModelRef 是实际 dispatched candidate，预算归属不会被 reported model 重定义。

Disabled/capability-ineligible/missing-policy/budget-denied candidates 不形成 fake zero-cost attempt。每个 admitted attempt 独立 START/FINALIZE；accounting persistence 或 integrity degradation 立即锁定 route，禁止下一个 candidate。

## C-005E2：Anthropic usage facts

Anthropic raw input、cache creation 与 cache read 规范化为 common total input，同时分别保存 uncached、cached 和 cache-write partitions。5-minute/1-hour cache creation 是 optional 子分区；`thinking_tokens` 是 output 子集。TTL detail 缺失或与 aggregate 矛盾时不猜：aggregate 可继续保存，TTL-specific pricing 返回 PRICING_CONTEXT_INCOMPLETE。UsageUpdate 与 terminal snapshot 仍不可相加。

这些字段进入既有 `LLMUsage` 和 `AttemptFacts` typed JSON。`llm_attempts` schema 无新列；旧 JSON 不含字段时 dataclass defaults 为 None，不解释为 zero，因此 Alembic head 仍是 0010。原生 adapter 的 physical attempt 继续由通用 budget reservation、START、FINALIZE 和 settlement 管线管理，见 [Anthropic adapter](ANTHROPIC_MESSAGES_ADAPTER.md)。

## C-005E3：Gemini reasoning/output accounting

Gemini `total_input_tokens`、`cached_input_tokens`、`total_output_tokens`、`total_thought_tokens` 和 `total_tokens` 映射到既有 `LLMUsage`。`ReasoningTokenRelation.ADDITIVE_TO_OUTPUT` 明确 generated output 为 visible output + thought tokens；它与 OpenAI-compatible/Anthropic 的 included 语义不同，不能使用相同的减法假设。`UsageUpdate` 与 terminal usage 仍是 snapshots，不相加。

Pricing 增加 `GENERATED_OUTPUT` meter：included 取 output，additive 取 output + reasoning，UNKNOWN/missing 则 `PRICING_CONTEXT_INCOMPLETE`。Provider continuation artifact 不写入 attempt/accounting typed JSON；closed codec 仍拒绝 request/response/artifact。新增 relation 依靠 typed-JSON default 兼容旧 rows，没有 Alembic migration，head 仍为 0010。

## C-005E4：OpenAI Responses usage facts

Responses usage 归一化 `input_tokens`、`input_tokens_details.cached_tokens`、`output_tokens`、
`output_tokens_details.reasoning_tokens` 和 `total_tokens`。Input/cached 同时存在且一致时，uncached 为
两者之差；未报告事实保持 None。OpenAI reasoning relation 固定为 `INCLUDED_IN_OUTPUT`，因此普通
output/GENERATED_OUTPUT pricing 不再加一次 reasoning breakdown。

每个 Responses physical attempt 继续经过通用 accounting START/FINALIZE；adapter 内部不重试。
Response/refusal/stream completion 的 factual usage 正常结算，失败的 safe attempt summary 不包含正文。
Reasoning text、summary、encrypted content、prompt、raw SSE、Response body 和 continuation artifact 都不
进入 ledger。`x-request-id`/Response ID 仅为有界 diagnostics，InvocationId 与 global attempt ordinal
仍是本地 accounting identity。没有 schema migration。

## C-005E5：production composition

生产 routed gateway 总是注入同一 SQLite `AccountingRepository`/`SqlAlchemyBudgetGuard` 组合；没有 provider-specific accounting shortcut。Provider config、SecretRef availability 和 credential control messages 不形成 attempt。只有获得 fresh admission 并 durable START 的实际物理调用才进入 ledger。配置、API key、prompt、response、reasoning 和 continuation artifact 仍不持久化。C-005E5 无 migration，head 保持 `0010_llm_budget_guard`。见 [生产组装](LLM_PRODUCTION_COMPOSITION.md)。
