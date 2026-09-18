# Provider-Neutral LLM Infrastructure — C-005A

状态：Stage 4 首个任务只建立标准库 application contracts、配置/凭据引用边界和 deterministic offline fake。没有真实 provider adapter、SDK、HTTP 调用、API key、credential storage、usage persistence 或 migration。

```text
Provider != Model != Purpose
application → ModelGateway port ← infrastructure provider adapters (future)
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

ModelCatalog 提供按完整 ModelRef 的显式能力查询，unknown 返回 None，不由 model-name substring 推断。ModelCapabilities 的 text_generation、streaming、structured_output、vision、tool_calling、reasoning_controls 是独立声明；布尔 false 表示未声明支持，不意味着 C-005A 实现这些功能。Routing、探测与 provider translation 留待后续。

## 2. 请求与文本内容

LLMRequest 包含 invocation_id、model、purpose、messages、必填正整数 max_output_tokens，以及 optional structured_output、stop_sequences、correlation_id、JSON metadata 与 streaming flag。

LLMMessage 使用 LivingWorld 自有 SYSTEM / DEVELOPER / USER / ASSISTANT roles 与 typed TextContent blocks。消息必须有至少一个 block；text 原样保留，作者/消息数组顺序有语义，不自动 trim/merge。当前只实现 text。未来 image/file/tool-result 可通过 closed content union 增加新类型，不能注入任意 provider block，当前也没有 tool execution。

max_output_tokens 表示请求的输出 token 上限，不定义全球统一 tokenizer。stop_sequences 是 ordered nonempty literal text sequences 的停止请求，不是 regex；未来 adapter 必须明确支持或返回 unsupported capability，不能 silently drop。SYSTEM / DEVELOPER 的 provider translation、token-limit 字段与 finish-code 映射需在 C-005B/C 基于实际能力验证，不假定不同 provider 等价。temperature/top_p/seed 等 sampling semantics 尚不在本契约中，避免提前承诺不可证明的跨提供方映射。

所有模型 defensively copy/freeze 输入集合与有限 JSON。非 typed role/block、未知 object/SDK/credential 值、非法预算等明确失败，错误仅包含 structural label。Prompt/content/metadata/schema/stop text 默认隐藏于 repr。

[llm_serialization.py](../../services/core/src/livingworld/application/llm_serialization.py) 是显式、closed-field 的本地 request round-trip codec：typed text blocks 与身份可转为 JSON-compatible data，再严格重建；不是 provider wire schema、公开 HTTP API 或 canonical content 格式。它不会通用 dataclass/asdict 任意配置对象。显式序列化会包含请求消息，**不得用作正常 structured logs**。

## 3. 结果、usage 与结构化生成

LLMResponse 包含 invocation_id、model_used、typed content、normalized FinishReason、optional usage、validated structured_result、selected ProviderDiagnostics 和 latency_ms。TextContent 与 response repr 默认不展开原模型文本。latency_ms 为非负整数/None；测量口径由未来真实 adapter 明确，fake 的零值仅是 synthetic fixture。

LLMUsage 的 input_tokens / output_tokens / total_tokens 是 nonnegative integer 或 None。None 表示未报告，不等于 zero；不虚构 total 或用假定的 advanced-category 关系校正提供方数据。details 为有限 immutable JSON，保留可选 cached/reasoning 等 provider fact metadata。**不包含价格表、cost calculation 或 currency policy**；C-005D 决定费用和记录持久化。

StructuredOutputRequest 携带 schema_name 与 JSON Schema document，包含的 `$schema` 等声明可原样保留。C-005A 仅检查有限 JSON/类型，不验证 schema dialect、schema 正确性或 generated instance。小测试 schema 不包含 Director/Builder 业务定义。

ValidatedStructuredResult 是未来可信 validator 的 typed output claim，含 schema_name 与防御性冻结的 JSON value。它与 raw model text 分离；构造这个值本身**不执行或证明 schema validation**。只有未来 C-005C validated-generation 流程应在验证后构造；当前 fake 永远不创建此 claim。Tests 手工创建受控 claim 仅验证表达与类型边界，不能作为真实结构化验证证据。看起来是 JSON 的文本仍只有 raw content，不能直接写 canonical 世界状态。

FinishReason 为 STOP / OUTPUT_LIMIT / REFUSAL / UNKNOWN。**模型内容/政策拒绝是正常 round trip 的 REFUSAL response**，可保留 usage/latency，不能改成 transport exception；REFUSAL 不允许携带 validated structured result。未知 provider finish code 的翻译留待真实 adapter。

## 4. 流、错误与取消

```text
await gateway.generate(nonstreaming_request) → LLMResponse / LLMError
gateway.stream(streaming_request) → AsyncIterator[LLMStreamEvent]
```

流使用 typed StreamStarted、TextDelta、UsageUpdate、StreamCompleted(response)、StreamFailed(failure)。顺序是 start → ordered text deltas / usage updates → exactly one terminal completed/failed。Completion 的完整 response 是最终结果；usage update 是 cumulative snapshot，不能逐条求和。拒绝的 terminal 是 completed REFUSAL。没有 provider SSE packets、网络 stream、partial JSON 自动验证或 tool deltas。

LLMErrorCode 区分 authentication、configuration、unsupported capability、invalid request、rate limited、provider unavailable、timeout、context limit、malformed response 与 cancelled。LLMFailure 关联 invocation 和 selected diagnostics，单一 LLMError exception 只输出稳定 code；不携带原 HTTP/SDK exception、headers/body 或任意 exception 文本。ProviderDiagnostics 只接受非 secret 的 provider request ID/diagnostic code，默认隐藏 repr；真实 adapter 负责安全挑选，禁止写入 credential/prompt。

进入 stream 前的非法请求可 raise LLMError；start 后的 normalized failure 以 StreamFailed 终止。外部 asyncio Task.cancel() 的 CancelledError 自然传播，不转换成 LLMError、不吞取消或继续消费。CANCELLED code 留给显式 normalized cancellation outcome，不替代 asyncio task cancellation。停止消费时调用 iterator.aclose() / context-managed closing；没有自定义线程取消或后台任务。

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

真实 provider adapters/SDK/HTTP、structured validation/retry、fallback/routing/rate-limit scheduler、pricing/budgets/persistence、keychain、Prompt/context assembly、Director/Character Agent/Memory/AI Builder、tool execution 和最终 UI 均未实现。下一任务 C-005B 未开始。相关边界：[SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)、[STAGE_2_ACCEPTANCE.md](STAGE_2_ACCEPTANCE.md)、[STAGE_3_ACCEPTANCE.md](STAGE_3_ACCEPTANCE.md)。
