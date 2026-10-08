# Structured Generation & Local Schema Validation — C-005C1

状态：已实现opt-in非流式结构化生成，历史测试使用人工fixtures／httpx.MockTransport。0.1.42已接入桌面显式原生能力配置及wire副本适配，本轮不运行测试或真实模型；历史“无production wiring”的阶段结论不代表当前设置入口。见[适配记录](../maintenance/2026-10-08-provider-compatibility.md)。

```text
valid provider text != valid JSON != schema-valid value
provider-side schema enforcement != dreamtalk local trust boundary
completed generation + unusable result still consumes factual reported usage
```

实现：[中立契约](../../services/core/src/livingworld/application/llm.py)、[Chat adapter](../../services/core/src/livingworld/infrastructure/llm/openai_compatible.py)、[集中验证模块](../../services/core/src/livingworld/infrastructure/llm/structured.py)。Domain/application 不依赖 HTTPX、jsonschema 或 referencing；只有 infrastructure 验证/IO。Validator 没有 world/content/knowledge 写入能力。

## 1. 官方依据与模式

2026-10-08复核[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)：Chat Completions的native response_format使用json_schema，包含name、strict=true和schema；仅支持其文档子集，root必须object且不能root anyOf。0.1.42仅在wire副本补齐required／closed object，原始schema仍本地权威；动态map等不支持的副本在网络前拒绝，其他provider-subset失败可返回normalized INVALID_REQUEST。不是通用schema编译器。

[DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/) 与 [Chat API](https://api-docs.deepseek.com/api/create-chat-completion/) 当前使用 response_format.type=json_object，提供 JSON syntax 保证，不代表已执行调用方 schema。提示中的 JSON 指令由调用方编写；adapter 不扫描关键字，不偷偷追加指令、示例或 schema。空输出与 length 需要独立处理。

| StructuredOutputMode | Wire | Schema enforcement |
| --- | --- | --- |
| NONE（默认） | 文本；结构化请求 unsupported | 无 |
| NATIVE_JSON_SCHEMA | `{type: json_schema, json_schema: {name, strict: true, schema}}` | 目标声明的 native 子集 + dreamtalk 本地 |
| JSON_OBJECT_LOCAL_VALIDATE | `{type: json_object}` | 仅 dreamtalk 本地 |

ChatCompletionsProfile 显式声明模式，gateway ModelCapabilities 同时暴露 mode 和兼容布尔；不按 hostname/provider/model-name 推断。两种 wire 模式限定显式 type=object；不声称支持 $ref-only root、混合 roots 或数组 transport，返回 UNSUPPORTED_CAPABILITY，不改写 schema。通用本地解析/验证可处理 object/array/string/number/boolean/null，并以请求 schema 为准。

## 2. Dialect、引用和 format

直接生产依赖 jsonschema（锁定 4.26.0）与 referencing（锁定 0.37.0）。jsonschema 负责成熟 schema/instance validation；referencing 的现代 Registry 负责安全引用控制，已经是 jsonschema 所需的依赖，显式声明避免直接 import 依赖偶然传递安装。仅新增必要的 attrs/jsonschema-specifications/rpds-py 传递依赖；已有版本保持不变。

明确使用 Draft202012Validator.check_schema / Draft202012Validator，dialect 为 JSON Schema Draft 2020-12。缺省 $schema 使用该 dialect；显式声明只接受其 canonical URI（允许末尾 #）；嵌套不同 dialect 同样拒绝 INVALID_REQUEST。不会用 validator_for 根据任意内容改换行为。参见 [jsonschema validator 文档](https://python-jsonschema.readthedocs.io/en/stable/validate/)。

Schema 正确性、dialect 和所有已声明引用在凭据/HTTP 前检查。仅接受 `#` 开头的当前文档引用，通过 referencing Resource 的 schema-aware subresources 遍历并校验引用存在；不把 examples/default/const 等普通 JSON 数据里的 `$ref` 当作 schema keyword。如果这些数据被本地引用选为 schema，则目标也必须通过 schema/ref 检查；已访问目标不重复遍历，允许合法的递归本地引用。Registry 显式禁止任何 retrieval；http/file/relative 外部引用全部拒绝，不访问网络、文件或环境。缺失本地目标同样拒绝；参见 [现代 Registry 文档](https://python-jsonschema.readthedocs.io/en/stable/referencing/)。

Format 明确是 annotation-only：format_checker=None，不执行 email/date-time 等 format 校验，不安装 format extras，不依赖机器可选组件。请求 schema 保持原样，无默认值注入、字段删除或类型转换。

## 3. 完成语义、严格解析与本地验证

处理顺序：

1. C-005B provider response/type/tool semantics；
2. recognized refusal/content_filter → 成功 REFUSAL LLMResponse，跳过 JSON/schema；
3. OUTPUT_LIMIT → STRUCTURED_OUTPUT_FAILED / OUTPUT_TRUNCATED，先于解析，即使内容是合法 JSON；
4. 空/whitespace → EMPTY_OUTPUT；
5. strict parse → JSON_PARSE_FAILED 或单一 JSON value；
6. instance validation → SCHEMA_VALIDATION_FAILED 或 ValidatedStructuredResult。

JSON parser 要求完整单值，允许前后 JSON whitespace；拒绝 malformed/trailing garbage、多值、NaN/Infinity/-Infinity、浮点溢出产生的非有限值，以及任意层级 duplicate keys。不会剥离 fences、提取括号片段、替换引号或移除 trailing commas。不修复、不重试，每次最多一次 provider HTTP 调用。

原生约束响应也必须本地验证。成功 LLMResponse 保留原始 TextContent、真实 reported model、factual usage 和 send round-trip latency，并附独立 immutable validated claim。验证不让输出成为 canonical content、WorldTruth 或 command/event/projection。

## 4. 失败诊断与计量摘要

单一顶层 STRUCTURED_OUTPUT_FAILED，detail.reason 区分 JSON_PARSE_FAILED、SCHEMA_VALIDATION_FAILED、OUTPUT_TRUNCATED、EMPTY_OUTPUT。保留第一个 schema error 的 instance/schema paths 与标准 validator keyword。路径最多 16 段、键名全部 `*`、仅保留有限数组索引，避免动态字段或 authored schema 名字泄露内容。原 ValidationError.message/instance/schema/context、原 HTTPX exceptions、headers/body 均不进入公开失败对象；LLMError.__context__/__cause__ 为空。

LLMFailure.attempt 是 optional LLMAttemptSummary，普通 failure repr 隐藏它。摘要本身只有 ModelRef（已含 provider identity）、normalized LLMUsage、FinishReason、latency_ms。Usage 防御性复制标准 input/output/total，保留已有 closed allowlist 的 nonnegative numeric/None cached/audio/reasoning/prediction/cache-hit/miss facts；未知 metadata 丢弃、已知 counter 的非法文本拒绝。因此显式遍历所有隐藏字段仍没有 prompt、output、structured value、SecretValue、Authorization、raw error 或 HTTP objects。当前不保留可选 provider request ID 或 postprocessing diagnostics，避免输出反射。

已完成后处理失败保留这些事实，未报告 usage 仍为 None，不做价格计算。Auth/connection/timeout 等未获得可靠完成事实的失败 attempt=None。摘要不是 future retry/repair storage；没有保留 raw response 或 raw output 的公共字段。成功 response 可含模型内容，不能作为普通日志。StructuredLogger 仍仅记录固定 category 和本地 InvocationId trace，不自动记录 schema/output/usage/异常文本。

## 5. 离线验证与范围

[测试](../../tests/core/test_structured_generation.py)、[OpenAI native fixture](../../tests/core/fixtures/llm/openai_structured.json)、[DeepSeek JSON object fixture](../../tests/core/fixtures/llm/deepseek_structured.json) 为人工受控小 schema，不包含业务模型，不冒充真实 API traces。验证 wire shape、不变消息、模式声明、schema 前置错误、local refs、禁止 remote IO、所有通用 JSON roots、严格解析、required/additional/nested paths、无 coercion/default、refusal/filter/length precedence、single-attempt 和 factual usage。显式递归序列化包括隐藏字段，证明 secret/prompt/output canaries 不出现在 summary/error/repr/logs。

沿用 [C-005A fake](../../tests/application/test_llm_contracts.py)、[C-005B 文本测试](../../tests/core/test_openai_compatible.py)、[架构约束](../../tests/core/test_architecture.py) 和完整 Stage 0–3 Python 回归。没有 UI/desktop 改动，无 GUI smoke。

本节的历史C-005C1验证未实测真实API兼容性；后续streaming／retry／routing／accounting／Responses与业务接线见[LLM基础设施](LLM_INFRASTRUCTURE.md)、[生产组装](LLM_PRODUCTION_COMPOSITION.md)及[当前状态](../PROJECT_STATUS.md)，不再把这些已实现部分登记为未开发。0.1.42原生wire副本和具体服务效果仍待用户验收。
