# Provider-Neutral LLM Infrastructure — C-005A through C-005E5

状态：Stage 4 已完成并冻结。C-005A 至 E4 建立 provider-neutral contracts、四种协议 adapter、structured/streaming、retry、accounting/pricing、budget 与 routing；C-005E5 增加严格非秘密配置、OS-native desktop credential host、私有 sidecar control protocol 和单一生产 composition root。验证使用离线 fake/MockTransport；没有真实付费 API。见 [生产组装](LLM_PRODUCTION_COMPOSITION.md)、[Stage 4 验收](STAGE4_ACCEPTANCE.md) 和 [LLM_ACCOUNTING.md](LLM_ACCOUNTING.md)。

生产代码仍保持 `application → ModelGateway port ← infrastructure adapters`。SecretRef 可以序列化，SecretValue 只能在 adapter request 时短暂 reveal。Tauri/keyring 不进入 application；Python session provider 不知道 OS credential API。启动不发 provider 请求，缺 key 不阻止 Core boot。

```text
Provider != Model != Purpose
application → ModelGateway port ← infrastructure provider adapters
usage != price
refusal != transport failure
raw text != validated structured result
```

## 1. 依赖与身份

[llm.py](../../services/core/src/livingworld/application/llm.py) 使用现有 immutable dataclass/Protocol 风格，domain/application 不 import provider SDK、HTTP schema、ORM 或 framework。ModelGateway 不提供 World/knowledge/content/ledger 写入能力；既有世界/内容流程不依赖 LLM adapter。LLM proposals 不成为 canonical facts，Kernel 的 command/event/projection/receipt 路径保持不变。

| 概念 | 身份与边界 |
| --- | --- |
| ProviderId | 明确的能力提供方/配置身份；nonblank opaque string，不是用途或 model name |
| ModelRef | ProviderId + opaque model_id；不包含 capability、price 或 profile，也不解析名称猜行为 |
| LLMPurpose | 开放的 nonblank application use-case 标签；调用方明确指定，不预先冻结所有未来用途 |
| InvocationId | LivingWorld-owned typed UUID，由调用方生成；独立于 provider request ID、RequestId、EventId 和 WorldTime |
| CorrelationId | 复用现有跨工作关联身份，optional；不是 invocation 或 provider identity |

ModelCatalog/ModelRegistry 提供按完整 ModelRef 的显式能力查询，unknown 返回 None，不由 model-name substring 推断。ModelCapabilities 保留 text_generation、streaming、structured_output、vision、tool_calling、reasoning_controls 声明。C-005C1 增加中立 StructuredOutputMode：NONE、NATIVE_JSON_SCHEMA、JSON_OBJECT_LOCAL_VALIDATE；非 NONE 要求 structured_output=true，真实 Chat gateway 同时准确报告布尔和模式。旧布尔声明保留源兼容，但单独 true 不证明原生 schema 保证，不能据此选择 wire 模式。C-005E1 routing 仅读取这些显式事实；online probing 仍未实现。

## 2. 请求与文本内容

LLMRequest 包含 invocation_id、model、purpose、messages、optional 正整数 max_output_tokens、optional temperature，以及 structured_output、stop_sequences、correlation_id、JSON metadata 与 streaming flag。max_output_tokens 缺失表示由 adapter 的显式 model profile 决定；没有显式 default 的必填协议必须在网络前失败。

LLMMessage 使用 LivingWorld 自有 SYSTEM / DEVELOPER / USER / ASSISTANT roles 与 typed TextContent blocks。消息必须有至少一个 block；text 原样保留，作者/消息数组顺序有语义，不自动 trim/merge。当前只实现 text。未来 image/file/tool-result 可通过 closed content union 增加新类型，不能注入任意 provider block，当前也没有 tool execution。

max_output_tokens 表示请求的输出 token 上限，不定义全球统一 tokenizer。stop_sequences 是 ordered nonempty literal text sequences 的停止请求，不是 regex；adapter 必须明确支持或返回 unsupported capability，不能 silently drop。SYSTEM / DEVELOPER translation、token-limit 字段与 finish-code mapping 是 protocol-profile 事实，不假定不同 provider 等价。temperature 是可选请求意图；只有显式 provider/model profile 能证明支持范围时才允许发送，不能 clamp、改写或按模型名猜测。top_p/seed 等 sampling semantics 仍未进入公共契约。

所有模型 defensively copy/freeze 输入集合与有限 JSON。非 typed role/block、未知 object/SDK/credential 值、非法预算等明确失败，错误仅包含 structural label。Prompt/content/metadata/schema/stop text 默认隐藏于 repr。

[llm_serialization.py](../../services/core/src/livingworld/application/llm_serialization.py) 是显式、closed-field 的本地 request round-trip codec：typed text blocks 与身份可转为 JSON-compatible data，再严格重建；不是 provider wire schema、公开 HTTP API 或 canonical content 格式。它不会通用 dataclass/asdict 任意配置对象。显式序列化会包含请求消息，**不得用作正常 structured logs**。

## 3. 结果、usage 与结构化生成

LLMResponse 包含 invocation_id、model_used、typed content、normalized FinishReason、optional usage、validated structured_result、selected ProviderDiagnostics 和 latency_ms。TextContent 与 response repr 默认不展开原模型文本。latency_ms 为非负整数/None；测量口径由未来真实 adapter 明确，fake 的零值仅是 synthetic fixture。

LLMUsage 的 input_tokens / output_tokens / total_tokens 是 nonnegative integer 或 None。None 表示未报告，不等于 zero；不虚构 total 或用假定的 advanced-category 关系校正提供方数据。details 为有限 immutable JSON，保留可选 cached/reasoning 等 provider fact metadata。**不包含价格表、cost calculation 或 currency policy**；C-005D 决定费用和记录持久化。

StructuredOutputRequest 携带 schema_name 与 JSON Schema document，包含的 `$schema` 等声明可原样保留。C-005A 仅检查有限 JSON/类型，不验证 schema dialect、schema 正确性或 generated instance。小测试 schema 不包含 Director/Builder 业务定义。

ValidatedStructuredResult 是可信 validator 的 typed output claim，含 schema_name 与防御性冻结的 JSON value。它与 raw model text 分离；构造这个值本身**不执行或证明 schema validation**。C-005C1 真实 adapter 仅在严格解析和显式 Draft202012Validator 验证后构造；fake 不创建此 claim。Tests 手工创建受控 claim 仅验证类型边界。看起来是 JSON 的文本不能直接写 canonical 世界状态。

FinishReason 为 STOP / OUTPUT_LIMIT / REFUSAL / CONTEXT_LIMIT / UNKNOWN。**模型内容/政策拒绝是正常 round trip 的 REFUSAL response**，可保留 usage/latency，不能改成 transport exception；REFUSAL 不允许携带 validated structured result。CONTEXT_LIMIT 与普通 stop/output budget 不混淆。

## 4. 流、错误与取消

```text
await gateway.generate(nonstreaming_request) → LLMResponse / LLMError
gateway.stream(streaming_request) → AsyncIterator[LLMStreamEvent]
```

冻结结果边界：

```text
LLMResponse = complete non-streaming generation result
LLMStreamCompletion = streaming terminal metadata
TextDelta = streaming content source of truth
```

typed StreamStarted → ordered TextDelta / UsageUpdate → exactly one StreamCompleted(completion) 或 StreamFailed(failure)。LLMStreamCompletion 只包含 invocation、model、finish、最小 typed StreamOutcome（NORMAL / REFUSAL / CONTENT_FILTERED）、usage、latency 和 bounded safe diagnostics，没有全文或 prompt/reasoning/raw SSE/HTTP objects。TextDelta 是正文的权威来源；adapter 不为终态累计全文，上层可自行明确选择累计政策。Fake 使用相同新契约；generate 仍返回完整 LLMResponse。

UsageUpdate 是 provider factual snapshot；completion.usage 是成功 `[DONE]` 时最新已知快照。二者不是 additive delta，不能累加或双重计量；缺失保持 None。流式元数据复用 closed numeric accounting-counter projection，不携带任意文本 metadata。partial failure 不存在 completion，也不创建完成的 LLMAttemptSummary。显式 refusal/filter 是成功 terminal semantics，不是 broken transport；两个结果以 typed StreamOutcome 区分，复用既有 REFUSAL finish。

真实 streaming、`[DONE]`/finish 条件、bounded framing、explicit profile、资源清理和离线证明详见 [LLM_STREAMING.md](LLM_STREAMING.md)。没有 partial JSON 自动验证或 tool deltas。

LLMErrorCode 区分 authentication、configuration、unsupported capability、invalid request、rate limited、provider unavailable、timeout、context limit、malformed response 与 cancelled。LLMFailure 关联 invocation 和 selected diagnostics，单一 LLMError exception 只输出稳定 code；不携带原 HTTP/SDK exception、headers/body 或任意 exception 文本。ProviderDiagnostics 只接受非 secret 的 provider request ID/diagnostic code，默认隐藏 repr；真实 adapter 负责安全挑选，禁止写入 credential/prompt。

合法 typed request 的 preflight/HTTP pre-start failure 只产生一个 StreamFailed，无 Started；start 后的 normalized failure 也以 StreamFailed 终止。结构性错误类型仍可 raise LLMContractError。外部 asyncio Task.cancel() 的 CancelledError 自然传播，不转换成 LLMError、不吞取消或继续消费。CANCELLED code 留给显式 normalized cancellation outcome，不替代 asyncio task cancellation。停止消费时调用 iterator.aclose() / context-managed closing；没有自定义线程取消或后台任务。

## 5. 配置与凭据边界

[llm_config.py](../../services/core/src/livingworld/application/llm_config.py) 分离 ProviderConfig 的 provider identity、optional EndpointConfig、SecretRef、default ModelRef、timeout_ms 和 TLS verification。Local provider 可没有 endpoint/secret；default model 必须属于该 provider。HTTP descriptor 支持 http/https，拒绝 userinfo/query/fragment、非法 host/port/control characters，TLS verification 不允许关闭；没有 arbitrary headers、transport object 或实际网络访问。

SecretRef 是 opaque UUID reference，不能塞入明文 key、env value 或文件路径。CredentialProvider.resolve(reference) 是未来 infrastructure 获取 ephemeral SecretValue 的 seam；没有 OS keychain、env loader、file storage 或数据库持久化实现。

SecretValue 默认 repr/str redacted，没有 dataclass/__dict__/自动 JSON 编码，只有显式 reveal_for_adapter() 可取值。它不能放进正常 ProviderConfig、LLMRequest metadata/schema/usage JSON 或 canonical 项目对象。配置只拥有 reference；ModelGateway 请求不包含 provider config 或 auth headers。

有限 JSON 校验阻止 credential/config/SDK **对象**被自动展开；它不能识别调用方故意复制成普通字符串的 secret，也不能保证任意模型文本/外部 authored source 不含敏感文字。调用方与未来 adapter 必须遵守不把 credentials 放进 prompt/metadata/diagnostics 的边界，不能把 repr redaction 当作万能 sanitizer。正常 [StructuredLogger](../../services/core/src/livingworld/infrastructure/logging.py) 仍只接受 allowlisted fields，默认不写 token/secret/prompt/conversation。

Provider configuration 不进入 CharacterDefinition、WorldContent、WorldEvent 或 `.lwcontent`；C-005A 不修改 canonical serialization、native package、运行状态或 migration。引用 package 的 security tests 以独立 controlled canary 证明能力隔离，不能借机改包语义。

## 6. Fake、验证与后续范围

[FakeModelGateway / StaticModelCatalog](../../services/core/src/livingworld/infrastructure/llm/fake.py) 是显式可注入的 offline test adapter，无 production default wiring。配置固定 text chunks、synthetic usage、FinishReason 或 normalized error；同请求得到相同结果与 ordered stream，回显调用方 invocation/model，响应不生成新 ID。包含标准 asyncio cancellation points，无人为真实延迟。

Fake 可返回 JSON-looking text，却不 validate schema/instance、tokenize、执行 stop/sampling、模拟真实 output budget、翻译 roles 或证明任何 provider capability。Catalog 是显式 immutable snapshot，未知 identity 没有猜测。它们服务未来 application tests，无 API key、network、SDK、world/content repository、pricing 或 usage persistence。

测试：[test_llm_contracts.py](../../tests/application/test_llm_contracts.py)、[architecture tests](../../tests/core/test_architecture.py)。覆盖请求 round-trip/immutability、raw vs validated claim、unknown usage、refusal vs failures、fake determinism/stream order/cancellation、explicit capabilities、credential repr/JSON/metadata/config isolation，以及实际 `.lwcontent` bytes/member canary 排除。完整 Stage 0–3 Python 回归继续执行。

## 7. C-005B Chat Completions adapter

[OpenAICompatibleChatGateway](../../services/core/src/livingworld/infrastructure/llm/openai_compatible.py) 实现 generate port 的 non-streaming 子集：caller base path + `/chat/completions`、一次 async HTTP request、调用时 CredentialProvider.resolve、explicit timeout、禁止自动 redirect/retry。仅 system/user/assistant、max_output_tokens→max_tokens、最多 4 个 ordered stop；immutable profile 显式声明 n=1、C-005C1 structured mode，以及 C-005C2 streaming/stream-usage 支持。developer、nontext 与 structured stream 拒绝；NONE 拒绝结构化请求。不按模型名猜能力、不把 reasoning_content 作为 assistant text。

校验最小 success schema，选择第一项 choice，实际 reported model 保留配置 ProviderId；InvocationId 仍为本地身份。Refusal 是成功响应；usage 缺失保持未知，advanced token counts 只取 allowlist，不计算 price。HTTP/credential errors 转为既有 LLMError，原 exceptions 不保留 context/cause，正常日志只记录固定 category 与本地 trace，finally 清除 wire Authorization。详见 [契约证据、映射与限制](OPENAI_COMPATIBLE_ADAPTER.md) 和 [离线测试](../../tests/core/test_openai_compatible.py)。

本 adapter 未配置为 production default；真实网络兼容性未实测。后续章节记录已完成的 Anthropic、Gemini 与 OpenAI Responses native adapters；structured streaming、repair、production catalog、incomplete reconciliation、keychain、Prompt/context assembly、Director/Character Agent/Memory/AI Builder、tool execution 和最终 UI 均未实现。相关边界：[SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)、[STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)、[STAGE_3_ACCEPTANCE.md](STAGE_3_ACCEPTANCE.md)。

## 8. C-005C1 结构化结果与安全失败计量

中立契约增加单一 STRUCTURED_OUTPUT_FAILED category 与 StructuredFailureDetail.reason（JSON_PARSE_FAILED / SCHEMA_VALIDATION_FAILED / OUTPUT_TRUNCATED / EMPTY_OUTPUT）。有界 instance/schema path 的键名隐藏为 `*`，保留数组索引和 validator keyword；不携带 library ValidationError、schema/instance 或原异常。LLMError 仍只有稳定 code。

LLMFailure.attempt 默认 None、隐藏 repr，类型为 immutable LLMAttemptSummary。只包含 ModelRef、usage、FinishReason、latency_ms 和 optional actual processing_tier；ModelRef 已包含 provider identity，不重复定义。Usage 复制标准 token 计数，仅保留既有闭合 accounting-counter allowlist（cached/audio/reasoning/prediction/cache-hit/miss），值限定非负整数/None；任意 metadata 被丢弃。摘要没有 content、structured payload、prompt、secret、headers、HTTP objects 或 provider error body，即使显式遍历所有字段也不会展开模型内容。当前不保留可选 provider request ID，避免反射内容；结构化后处理 failure diagnostics 也保持空。

完成生成后的 JSON/schema/empty/truncation failure 保留实际 usage/model/finish/latency；没有 usage 就保持 None。Auth/transport/timeout 等前置失败不虚构 attempt。Refusal/filter 保持 LLMResponse 和 usage，不解析。成功结果仍保留 raw TextContent 与独立 validated claim。无价格、retry storage 或 repair context；详见 [STRUCTURED_GENERATION.md](STRUCTURED_GENERATION.md)。


## 9. C-005C2 真实流式传输

Chat gateway 的 stream 与 generate 共享 request translation、late credentials、HTTP client 和错误归一化；只在 profile 支持时请求 stream=true，可选 include_usage。SSE framing 增量、限额、pull-driven，不将非流式结果拆段。合法 HTTP/type 后 Started，choice-0 finish 后的 `[DONE]` 才能 Completed；中断/非法流 Failed，取消直接传播并关闭资源。reasoning/refusal payload 不成为 visible TextDelta。所有 terminal metadata 已排除正文，详见 [LLM_STREAMING.md](LLM_STREAMING.md) 和 [focused tests](../../tests/core/test_llm_streaming.py)。无新增依赖、usage persistence 或世界/内容/migration 改动。


## 10. C-005D1 Attempt orchestration

[ExecutingModelGateway / RetryPolicy](../../services/core/src/livingworld/application/llm_execution.py) 外包现有 single-attempt gateway，logical invocation != physical attempt。重试复用原 immutable request、provider/model/InvocationId，ordinal 是 execution metadata，不进入 wire。Failure 增加 typed DispatchState、HTTP status 和 normalized Retry-After duration；未知 dispatch 默认不重放。已完成 structured failure 不属于 transport retry；refusal/filter 原样成功。

默认最多 3 次尝试、30 秒 retry-start window，bounded exponential full jitter，次数/monotonic elapsed 双重界限；Retry-After 是最早重试边界，无法满足就停止。Stream 只在暴露 Started 前允许 hidden retry；暴露后失败只交付一次 Failed，不重播或合并正文。Usage snapshots 不相加，retry 可能消耗额外 quota/cost，但没有 pricing/accounting persistence。取消在 attempt/backoff 直接传播；每次独立 resolve credentials，安全 observer 仅提供 closed execution facts。完整 policy/默认 eligibility/限制和离线证明见 [LLM_EXECUTION_POLICY.md](LLM_EXECUTION_POLICY.md)。

## C-005D2A：usage facts 与 accounting

LLMUsage 保留 input/output/total，新增 optional cached_input/cache_write_input/uncached_input/reasoning_output；None 不补零，reasoning 默认是 output 子集。Safe summaries/completions/UsageUpdate 的闭合 numeric projection 保留这些事实，拒绝不可能的 partition，排除任意 raw metadata。LLMResponse、LLMAttemptSummary 与 LLMStreamCompletion 可保留 documented actual response processing tier，无 pricing config。

[物理 attempt accounting](LLM_ACCOUNTING.md) 位于独立 application port / infrastructure repository，不在 provider adapter；RetryRecord != attempt record。START 失败抛本地 AccountingInfrastructureError 且零 provider 调用；FINALIZE 失败原样保留 response/failure/completion/cancellation，通过独立固定 severe diagnostics 表达 degradation，禁止下一 attempt。Ledger INCOMPLETE 不解释为零费用。Pricing catalogs 是 trusted explicit reference data，historical exact Decimal estimates 使用持久化 immutable snapshots；usage != pricing config，estimated cost != invoice。Unknown exposure 与多币种不能隐藏或合并。C-005D2B 已增加独立 opt-in [Budget Guard](LLM_BUDGET_GUARD.md)。

## C-005D2B：estimated-spend authorization

[Budget policy/bounds ports](../../services/core/src/livingworld/application/llm_budget.py)、[preflight pricing](../../services/core/src/livingworld/application/llm_preflight.py) 在 application；operational persistence 通过 [SqlAlchemyBudgetGuard](../../services/core/src/livingworld/infrastructure/persistence/llm_budget_repository.py) 实现，provider adapter 无 DB/budget/world 能力。可信 ModelUsageLimits/exhaustive requested-alias PricingEnvelope 由 composition 显式注入；不猜 tokenizer/model/provider 语义，缺可信 bounds/context/prices 的 HARD 零调用 fail closed。

HARD 授权 LivingWorld trusted estimated upper-bound spend，不承诺 invoice/余额。SOFT warning 不改变请求、模型/output cap。Budget scope/admission/history/query/retry 统一 exact requested ModelRef；reported metadata 独立用于实际 pricing/analytics。START/reservation 与 final accounting/settlement 各共享 SQLite write transaction；crash/partial/unknown 保留 holds，没有自动 expiry/reconcile。本地 failure 不重放 provider，outcome/cancellation 保持。没有 production default wiring/catalog、routing/UI/智能层。详见 [LLM_BUDGET_GUARD.md](LLM_BUDGET_GUARD.md)。
## C-005E1：registry 与 routing

[Model Registry 与 Routing](LLM_ROUTING.md) 位于 application 层、provider adapters 之上。ProviderId 继续表示 configured provider instance；AdapterKind 独立表示 openai-compatible / anthropic / gemini / openai-responses protocol family。Registry 使用 exact ModelRef 和显式 ModelCapabilities，不按名字猜测、不发现在线模型，也不保存 secret、client 或价格表。

FAST/BALANCED/BEST 是配置的 policy labels，不是模型客观排名。RoutePlan 纯解析、无 provider IO。Explicit model 默认不换模型；profile 使用配置的 ordered chain。一个 routed Invocation 共享 deadline 与 invocation-global ordinal；candidate-local retry 不重置 deadline。Fallback 仅更改 execution target，messages/purpose/schema/stop/output cap/metadata 保持。Ambiguous dispatch、refusal/filter、structured postprocessing、accounting/budget integrity 和 STARTED 后的 stream 都禁止 fallback。

## C-005E2：Anthropic 原生 Messages adapter

[AnthropicMessagesGateway](../../services/core/src/livingworld/infrastructure/llm/anthropic_messages.py) 是独立的 `AdapterKind.ANTHROPIC` transport，不经过 OpenAI compatibility endpoint。它直接映射 `/v1/messages`、top-level system blocks、required max_tokens、原生 `output_config.format`、Anthropic named SSE、`message_stop` 和独有 usage/cache facts；不使用 `[DONE]`、SDK、beta、tool loop、thinking controls 或 provider-side fallback。详细 contract、限制和离线证据见 [ANTHROPIC_MESSAGES_ADAPTER.md](ANTHROPIC_MESSAGES_ADAPTER.md)。

LLMUsage 增加 optional 5-minute/1-hour cache-write facts；FinishReason 增加 CONTEXT_LIMIT。两者均为 provider-neutral value，不让 application/domain import Anthropic schema。旧 persisted usage 缺少新 JSON fields 时保持 None；无表结构变化或新 migration。

## C-005E3：Gemini 原生 Interactions adapter

[GeminiInteractionsGateway](../../services/core/src/livingworld/infrastructure/llm/gemini_interactions.py) 使用稳定 `POST /v1/interactions`、`x-goog-api-key` late authentication、`store=false` 和 `background=false`。它不使用 OpenAI compatibility、SDK、server-side history、tools、Search、Agent 或 provider fallback。完整 wire contract、限制和离线证据见 [GEMINI_INTERACTIONS_ADAPTER.md](GEMINI_INTERACTIONS_ADAPTER.md)。

Provider-neutral `ProviderContinuationArtifact` 只保存 adapter kind、ProviderId、schema version、opaque bytes 和 visible-content digest。Gemini payload 只含 step layout、thought signatures 以及 visible text 的 byte length/hash，不复制正文；外来 adapter/provider artifact 被忽略，本 adapter 的篡改在 credential/network 前失败。它是 stateless provider continuation metadata，不是 Memory、World state、authored content、accounting 或 routing state。

`LLMUsage.reasoning_token_relation` 明确 `UNKNOWN`、`INCLUDED_IN_OUTPUT` 和 `ADDITIVE_TO_OUTPUT`。OpenAI-compatible/Anthropic 规范化为 included；Gemini `thought_tokens` 规范化为 additive。旧 persisted typed JSON 缺字段时为 UNKNOWN；没有表结构变化或新 migration。

## C-005E4：OpenAI 原生 Responses adapter

[OpenAIResponsesGateway](../../services/core/src/livingworld/infrastructure/llm/openai_responses.py)
是独立的 `AdapterKind.OPENAI_RESPONSES`，不复用或替换
`AdapterKind.OPENAI_COMPATIBLE`。它直接调用 `POST /v1/responses`，每次 invocation 只有一个
HTTP attempt，固定 `store=false`、`background=false`、`truncation=disabled`，不发送
`previous_response_id`、Conversation resource、tools 或 arbitrary metadata。

Responses 原生保留 system/developer/user/assistant 的消息次序和原文。普通结果只暴露 ordered
`output_text`；explicit refusal 是成功语义。Native JSON Schema 使用原 schema 和稳定安全 wire name，
provider terminal 分类完成后再进行本地 Draft 2020-12 校验。Reasoning text/summary 永不成为公开
content；optional encrypted reasoning 只进入短生命周期 `ProviderContinuationArtifact`，不是 memory、
knowledge、content 或 durable accounting state。

`ProviderDiagnostics` 可分别携带经过 allowlist 校验的 `x-request-id` 和 Response ID；二者都不是
LivingWorld identity 或 conversation identity。OpenAI usage 将 reasoning tokens 标记为
`INCLUDED_IN_OUTPUT`，防止 output pricing 二次计费。完整契约和证据见
[OPENAI_RESPONSES_ADAPTER.md](OPENAI_RESPONSES_ADAPTER.md)。无 migration、SDK 或新依赖。
