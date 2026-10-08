# 其他模型服务的适配调查

调查日期：2026-10-08。用户要求核对并完善其他厂商适配，随后明确选择继续保留严格整轮 Token 硬上限。调查依据为当前官方文档和本仓库源码；没有真实模型调用，也没有凭据探测。

## 当前成熟接口与实际采用

| 来源 / 核对版本 | 核对结果 | 本轮采用与限制 |
| --- | --- | --- |
| [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)，当前 Responses API | strict schema 要求对象字段全部 required、additionalProperties=false；只支持 JSON Schema 的子集。 | Responses 和声明原生 Schema 的兼容服务使用独立 wire 副本：封闭对象、全部字段必填、移除 default/方言声明，字符串长度限制留在说明与原始本地校验。原始 schema 不改写；动态 map 和不支持的根对象在网络前拒绝。不是任意 schema 编译器或任意代理保证。 |
| [Claude Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)，当前 Messages API 的 output_config.format | 原生语法不接受部分数值、字符串长度及数组约束；官方 SDK 采用简化 wire schema 加完整本地校验。 | 按文档行为独立实现小范围转换，仅移除 wire 中不支持的约束并写入字段说明，本地仍用原始 schema 校验；不复制 SDK 源码，不引入 SDK。 |
| [Gemini Structured Output](https://ai.google.dev/gemini-api/docs/structured-output)、[Interactions API](https://ai.google.dev/api/interactions-api)，当前 v1beta/interactions | Interactions 使用 response_format；请求只接受一个前置系统指令。 | 保留既有 Interactions adapter 与 store=false；聊天同次附带事件/记忆时把既有系统块和附带协议合并成一个系统消息，不把聊天原文提升为系统指令。原生能力需具体模型确认。 |
| [Claude Token Counting](https://platform.claude.com/docs/en/build-with-claude/token-counting)，当前 count_tokens | 官方将结果明确描述为估计，不是已证明的严格计费上界。 | 不把估计值升级为 HARD_UPPER_BOUND；继续使用可信模型输入容量预留。 |
| [Gemini Tokens](https://ai.google.dev/gemini-api/docs/tokens)，当前 countTokens | 文档中的 generateContent 计数不能直接证明当前 Interactions 请求的完整输入计费上界。 | 不混用两种协议的计数，不凭经验补常数。保留容量预留并显示额度要求。 |

## 复用与许可

继续使用项目已有 HTTPX、jsonschema 与 Pydantic，分别承担一次 HTTP 请求、原始 schema 校验和业务模型校验；没有增加依赖、运行框架或付费计数请求。本轮参考公开协议与文档行为，未复制 OpenAI、Anthropic、Google 或 SillyTavern 的实现代码；官方文档是技术依据，不将网页或 SDK 的许可推定为仓库 Apache-2.0 的再分发许可。维护成本集中在四个现有 adapter、一个小型 wire 转换函数和既有模型配置入口。

## 不扩大保证

同次附带聊天事件/记忆不依赖原生 JSON Schema，四类文本生成路由都可尝试；合法完整普通台词允许没有新条目，不额外补提取。字段数量、来源原句、角色/玩家/世界权限及停用/纠正过滤保持。

严格额度仍涵盖选人、角色发言、内部 retry/fallback；未知或计数失败时回到可信模型容量。容量预留是准入依据，不是实际发送或固定扣费量。厂商能力、具体型号、第三方代理、超时与用量返回仍须用户体验验收；静态核对不替代真实兼容结论。
