# LLM Budget Guard, Reservations & Routing Admission Facts — C-005D2B / C-005E1

状态：opt-in application budget policy、可信 preflight bounds、SQLite 原子准入/结算、持久化 reservation、安全拒绝事实与 route integration 已实现并离线验证。没有生产价格目录、真实付费 API 测试、预算 UI 或 reconciliation。

**Hard Budget = 对 LivingWorld 可信 estimated upper-bound spend 的硬授权；不是 provider invoice、余额、信用卡或预付费上限保证。**

```text
no trusted upper bound → HARD fails closed
unknown unbounded billing exposure → HARD fails closed
all matching HARD reservations + accounting START → one durable transaction
only after commit → one physical provider attempt
every retry → new authorization
accounting/budget DB failure → never replay provider
```

## 1. 策略、身份与窗口

[llm_budget.py](../../services/core/src/livingworld/application/llm_budget.py) 定义 immutable BudgetId（UUID）、BudgetPolicy、BudgetMode、typed local BudgetAdmissionError、queries 和 safe diagnostics。策略使用既有 Money/ModelRef/LLMPurpose/ProviderId/Revision，不建立世界领域依赖。

BudgetPolicy 包含 enabled、OFF/SOFT/HARD、currency/Decimal limit、explicit aware UTC `[start_utc,end_utc)`、optional exact purpose/provider/model filters、revision 和 UTC audit timestamps。输入 UTC-aware 时间统一归一，naive 拒绝。包含依据为 **attempt START UTC**，不是 finalize 时间或本机时区。ModelRef 自带 provider；model-only filter 在构造时明确解析其 provider，无 substring 匹配。

**所有预算语义只按 requested ModelRef**：准入、历史支出归属、reservation、remaining queries 和 retry authorization。requested alias 与 reported concrete model 独立；后者只用于 factual pricing/diagnostics/analytics。Budget SQL 不复用 ledger analytics 的 `requested OR reported` predicate。

ALL matching enabled HARD policies 必须一起授权；global/purpose/provider/model 可以叠加。历史窗口内的 matching ledger activity 即使早于预算创建也参与计算。修改 limit 只影响下一次准入，不能改写历史金额/快照；policy 更新遵循 expected existence/revision → exact next revision。只提供 disable/更新，不提供 cascade delete 或清理历史。

## 2. OFF / SOFT / HARD

| 模式 | 行为 |
| --- | --- |
| OFF / disabled / unmatched | 不执行预算检查或 bounder，既有 retry/accounting 路径保持；不移除历史 holds |
| SOFT | 超支、不可验证 bound/price、未知暴露、币种不匹配或 integrity 问题仅发固定 warning；不因预算拒绝、改请求、缩 output cap 或换模型 |
| HARD | 只接受 HARD_UPPER_BOUND；缺价格/上下文/可信 bounds、币种不匹配、不可界定历史暴露或 integrity degraded 均在 provider call 前拒绝 |

SOFT/预算关闭不绕过基本 accounting START 故障规则：持久化失败是基础设施错误，仍然零 provider calls。诊断 consumer 必须 non-raising；其异常不能替换 provider outcome。

## 3. Usage upper-bound seam

PreflightUsageBounder 返回 UsageUpperBound 或 None；guarantee 明确区分 HARD_UPPER_BOUND / ESTIMATE_ONLY / UNAVAILABLE。ESTIMATE_ONLY 不是 HARD 保证，SOFT 也发不可保证 warning。没有 char/word guess、tokenizer、count-tokens endpoint 或 model-name inference。

ModelLimitUsageBounder 使用 exact ModelRef → explicitly trusted ModelUsageLimits：max_billable_input_tokens/max_output_tokens。input 为完整 billable input 上界（须覆盖协议封装等）；output 为 request cap（不超过可信 model max）或可信 max。现有 LLMRequest cap 必填；未知 model limits 不建立可信 HARD bound。

配置的 **信任声明还必须覆盖实际 adapter/provider 的 cap 语义和所有 billable output（包括适用的 hidden/reasoning tokens）**。Generic compatible / `max_tokens` 字段名不能自行证明这个保证；不适用的模型不得配置为可信。对动态 alias，limits 必须覆盖所有可达 concrete outcomes。更精确的未来 bounder 通过同一 port 注入，本任务不实现。

## 4. 独立 preflight pricing bound

[llm_preflight.py](../../services/core/src/livingworld/application/llm_preflight.py) 的 PreflightPricingEngine 与 D2A historical PricingEngine 分开。使用注入的 trusted PricingCatalog、UsageUpperBound、requested ModelRef、START UTC 和显式 known processing tier，返回 content-free MoneyUpperBound 或 None（Unverifiable）。

- 每个 target 必须在 START UTC 有一个可信 schedule；缺失、多个生效 schedule、input rule gap/overlap、未知 required tier 或 reachable currency 不统一均不可验证。
- UTC windows 使用已知时间；input 的全部 integral range `[0,input_upper]` 必须覆盖，每段恰好一个规则。对每个可达 variant 计算保守上界，再选最大金额；不只选 cheap variant 或最大 context 所落的 variant。
- 未知必需 tier fail closed。可通过 narrow RequestedPricingEnvelope 显式提供已知 tier；不猜 response 将使用什么 tier。
- partition 总量受 input/output bound 约束，按各组最大单位 rate 界定，不将 reasoning 作为额外 output。使用 precision=100 Decimal context、向上取整到 1e-9；分区额外保守 rounding allowance 防止 D2A per-line rounding 超过 aggregate bound。上界可以偏宽，不是期望费用。
- 不进行 FX；single EUR preflight 对 USD HARD policy 为 typed currency denial，多个 reachable currencies 不形成一个安全 envelope。

### Requested alias

RequestedPricingEnvelope 是显式可信、完整、有限的 `requested → possible priced targets` reference data，可包含多个 exact ModelRef。取所有 reachable target costs 的最大值。D2A ModelAlias 的一个便宜映射不自动证明它是 exhaustive；无 envelope 的 catalog alias 无法 HARD 准入。Opaque model name 不用于识别 alias；直接 exact schedule 本身由 trusted configuration 声明适用。C-005E1 registry 可引用该既有 envelope，但不自动解析 alias 或抓取价格。

最终历史估价仍可使用 reported model 的安全映射，但 settlement 只作用于 requested scope 原先创建的 reservations。Missing reported price 保留 hold，不回退猜价格或重定义预算归属。完整 preflight schedules/usage bound/context 与 policy snapshot 持久化为安全 operational evidence。

## 5. 原子准入与并发

[SqlAlchemyBudgetGuard](../../services/core/src/livingworld/infrastructure/persistence/llm_budget_repository.py) 借用既有 app-data Database/session factory。`Database.llm_budget_guard(...)` 显式注入 bounds/catalog/envelopes/diagnostics；`ExecutingModelGateway(budget_guard=..., wall_clock=..., accounting_diagnostics=...)` 是 opt-in composition，不能同时传另一个 accounting sink。

```text
BEGIN IMMEDIATE
→ re-read matching enabled policies
→ compute pure trusted preflight bound
→ read historical cost + holds + integrity
→ all matching HARD capacity checks
→ insert accounting START + all reservations
→ COMMIT
→ provider
```

Pure bound/config calculation没有 provider/network IO；当前置于持有 SQLite write transaction 期间，policy/state 不可能用 stale read 准入。5000ms busy_timeout/集中 BEGIN hook 沿用基础设施；不新增 process-local lock 或 provider retry。任何 START/reservation 写入失败整笔回滚，零外部调用，抛本地 AccountingInfrastructureError；budget denial 是独立 typed local error，不成为 ProviderUnavailable。

每项新 logical execution 必须使用新的 InvocationId。admit 拒绝既有 physical START；它不是 generation replay cache。普通 D2A observer delivery 的幂等 START/FINALIZE 保留在独立 UsageLedger。

SQLite DB 与外部 provider 不是一个 ACID transaction；持久化 pre-dispatch hold 正是为了覆盖 commit 后 crash 的未知 exposure。

## 6. Exposure 与 queries

预算视图提供 policy/matched scope、known estimated spend、held Money、safe remaining（无法保证时 None）、unbounded exposure/currency/integrity flags。所有窗口成本只用 requested scope SQL。多币种不合计。剩余额度为非负展示值；limit/历史金额不自动增改。

Known matching historical money + active/uncertain holds + proposed upper bound 必须不超过 limit。多条 HARD policy 对同一 physical attempt 的 holds 是同一暴露；计算每项 physical exposure 时取可信 holds 的最大值一次，避免 duplicate reservation charge。新建/扩展预算可以使用 matching attempt 已有的同币种可信 hold 界定未知暴露；不必假装它是零，也不因缺少“本 policy 的 hold”而拒绝已被安全界定的未知成本。

没有可信 hold 的 INCOMPLETE / possible billed / cost unknown activity 为 BUDGET_STATE_UNCERTAIN。读取也复核 evidence、reserved amount、original requested identity、accepted policy 和 terminal/settlement 一致性；无法证明 integrity 时 HARD fail closed。

## 7. 结算、crash 与 integrity

| durable final facts | reservation |
| --- | --- |
| final known priced cost ≤ reserved，same currency | SETTLED，记录最终 estimated amount；unused capacity 释放 |
| proven NOT_DISPATCHED | RELEASED；不伪造 zero usage |
| unknown / partial usage / unknown price / interrupted stream | HELD_UNCERTAIN，完整 reserved amount 保持 |
| known cost > reserved | BOUND_VIOLATION；不释放、不造负金额、不调 limit |
| final price currency drift / invalid evidence | INTEGRITY_DEGRADED；hold 保留，future HARD 拒绝 |
| atomic FINALIZE/settlement transaction failure | rollback；START INCOMPLETE + original HELD；safe CRITICAL diagnostic |

账务与 settlement 在同一 BEGIN IMMEDIATE transaction 中提交。若控制场景留下 finalized accounting + stale hold，queries 检出 incomplete reconciliation，future HARD 为 integrity degraded。有可信 hold 的正常 unknown START 则仍是 bounded exposure，不能自动释放，也不必一律封锁剩余安全容量。

Bound violation 的 durable reservation status 是 integrity evidence。原预算和与其 scope 重叠的策略持续封锁 HARD；新 budget ID、window 或 restart 不恢复信任。没有自动 trust reset、expiry 或 reconciliation API。

Provider/application outcome 与 accounting/budget integrity 独立：success/LLMFailure/StreamCompleted 原对象保持，CancelledError 继续传播；所有 finalization/integrity failure 禁止 attempt N+1，含 hidden pre-STARTED retry。安全 CRITICAL event 为 budget_finalization_incomplete / budget_bound_violation，不包含异常文本、SQL/connection details 或模型内容。

## 8. 重试与 streaming

每个 physical retry 新建 reservation/admission；attempt 1 的 unknown hold 保留，attempt 2 必须独立 fit。Denied retry 终止为本地 BudgetAdmissionError，不能改回 latest provider failure 或偷偷执行 hidden retry。成功释放的 proven NOT_DISPATCHED attempt 可让下一次 fit。

Stream 在 transport 前建立 reservation。STARTED 后既有 no retry 不变；completion 使用 latest/final factual usage，不加 UsageUpdate snapshots。Partial/cancel/abandon 保留完整 hold；TextDelta/response/prompt/reasoning 永不进入 budget storage。

## 9. Schema、验证与范围

[0010_llm_budget_guard](../../services/core/src/livingworld/infrastructure/persistence/migrations/versions/0010_llm_budget_guard.py)，down_revision=0009_llm_accounting，只新增 AccountingBase 的 llm_budgets / llm_budget_reservations。后者以 `(budget_id,invocation_id,attempt_ordinal)` 为 PK，FK RESTRICT 连接 policy/START；money 使用 Decimal TEXT，timestamps 为 UTC VARCHAR，包含 status/settlement/ordinal/audit CHECK 和 queries indexes。旧 attempts、audit、world/content rows 不改写；migration detector 按 cursor 校验 0009/0010，partial schema fail closed。Downgrade 要求单独 review。

测试：[budget invariants](../../tests/core/test_llm_budget.py)、[populated knowledge/content isolation](../../tests/application/test_llm_accounting_isolation.py)。证明 $1/.40/.20/.30 准入后 .20 拒绝；两独立 engines 并发只有一次 provider call；多预算原子 START、retry/stream、unknown/crash/finalize、broken bounds、alias scope、raw SQLite/diagnostic canaries、DDL rollback 和 prior-row preservation。完整 Python Stage 0–3、C-005A/B/C1/C2/D1/D2A 回归继续执行。

预算是 operational metadata，不产生 WorldEvent、authored content/knowledge/memory，不进入 `.lwcontent`。没有新增依赖、付费 API 验证、online prices、FX、tokenizer/count APIs、expiry、reconciliation、max-token mutation、UI、Director/Agent/Memory。C-005E1 提供 deterministic fallback integration；production wiring/catalog、dynamic ranking 和 richer registry loading deferred。
## C-005E1：完整拒绝事实与 routing

Admission transaction 返回 immutable BudgetAdmissionSummary；成功时确认 admission/reservations 的 atomic commit，拒绝时证明没有 reservation 或 accounting START。它包含全部 matching HARD policies 的 budget identity/scope、typed reason、currency/limit、known spend、held、remaining、requested upper bound、unbounded exposure 与 integrity state。没有 prompt/output/reasoning/credential/SQL error。Integrity degraded/state uncertain 优先于 ordinary affordability。

Repository 只报告事实，不选择模型。只有 PROFILE RoutePolicy 明确允许且 summary 证明健康时，EXCEEDED / UNVERIFIABLE / CURRENCY_UNSUPPORTED 可切换候选。Global/purpose budget 也对下一候选的独立 upper bound 重新做原子检查，因此较低 bound 可被授权而没有绕过 global policy。下一候选不复用 reservation。

STATE_UNCERTAIN、INTEGRITY_DEGRADED、bound violation 和 accounting/budget persistence/finalization failure 都终止 route。缺完整 typed summary 的 custom denial fail closed。C-005E1 没有新表或 migration；head 仍是 0010。

## C-005E3：Gemini combined output bound

Gemini 的 `GENERATED_OUTPUT` pricing 把 visible output 与 additive thought tokens 作为一个 output budget meter。HARD preflight 使用请求中单一 `max_output_tokens` 作为该 combined generated-output cap；不能分别对 visible/thought 各套一次 cap，也不能猜测 reasoning 比例。缺可信 model limit、requested-alias pricing envelope 或 GENERATED_OUTPUT rate 时仍在 provider 前 `BUDGET_UNVERIFIABLE`。

被稳定 machine code 证明为 quota exhaustion 且 provider 明确在 execution 前拒绝的 attempt 可释放 reservation；若 RoutePolicy 允许，下一候选必须重新执行完整 admission/reservation/START。未知 dispatch、已执行 exposure 或任何 accounting/budget integrity degradation 继续保留 hold 并终止 route。

## C-005E4：OpenAI combined output bound

OpenAI Responses 的 `max_output_tokens` 同时覆盖 visible output 和包含在 output count 中的 reasoning
tokens。HARD preflight 使用一个可信 combined generated-output cap，不建立独立 reasoning allowance，
也不把 `output_tokens + reasoning_tokens` 作为最终 spend。Requested ModelRef 仍决定 budget scope；
reported model 只用于可安全映射的 actual pricing。

缺 model limit、requested-alias envelope 或可信 rate 仍在 provider 前 fail closed。每个 routed/retried
candidate 建立自己的 reservation 与 accounting START。Responses continuation ciphertext、Response ID
和 reasoning text 不进入 budget evidence。Provider-proven quota/billing pre-execution rejection 可以沿用
现有 safe fallback 规则；unknown dispatch 和任何 integrity failure 继续终止 route。

## C-005E5：production admission wiring

ProductionLLMRuntime 从严格配置加载 trusted model limits、pricing schedules/aliases/envelopes，并将 registry bounder、catalog 和 SQLite repositories 注入真实 Budget Guard。所有四个 adapter 通过相同 routed/executing path；不存在 provider-specific bypass。价格缺失不被猜测：普通 policy 沿用既有行为，HARD monetary guarantee 在网络前 fail closed。配置价格是 source-labelled Decimal data，不是 source-code model-name branch。C-005E5 无 migration。
