# 全角色空正文：聊天传输兼容修复

2026-10-02，基线0121a73 / 桌面0.1.7。用户反馈每位角色均无回复。本轮仅修复共用聊天输出链路，保留同次事件与长期记忆提取。

## 证据和结论边界

- 0.1.7的运行位置上轮已核对为long-memory完整目录。core-b4f9cdb9日志在日本时间18:38:11、18:48:03、18:48:15记录chat_structured_empty_output随后chat_structured_output_failed，用户于18:48后关闭程序。此固定码只在已获得HTTP完成响应、response.text为零字符或全空白时产生；无效JSON/字段、输出截断、鉴权/网络失败另有固定码。不能推断为空JSON对象、角色缺资料、存档坏或聊天额度不够。
- 本轮只投影非秘密llm.json的provider/model/能力/限制，但文件仍为177字节空配置，与成功credential同步和实际付费响应不一致，因此不把这一视图用作当前模型设置或服务异常证明，不再重复此分支。用户说明使用DeepSeek、回复上限100000、未开启流式，没有提供准确API模型ID；没有猜测ID或改写用户配置。
- 日志没有本次结束枚举、Token计数、thinking正文存在性或请求正文。确认的是空正文和共同结构化链路，不能证明服务内部为何产生空正文，也不能把官方的“偶发”解释当成全部根因。原解析按标准message.content取正文，无证据表明长期记忆解析吞掉了有效台词。

## 官方和成熟实现核对

- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)：服务端JSON输出会偶尔返回空内容，要求明确json及目标示例。普通角色SYSTEM仍有“只输出台词”，追加格式指令虽然解释覆盖但存在指令冲突；0.1.7记忆例子只是数组中的单条对象，寒暄没有完整reply/events/memories示例。这里只能认定其有风险，未经真实调用不能认定某句是唯一原因。
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：response_format可省略，max_tokens限制生成长度；不必依赖服务端JSON模式才能请求模型生成JSON。官方thinking文档仍将reasoning_content与最终content分开，不能把思考正文当角色台词。原已核对模型的thinking disabled边界保持。
- [LiteLLM structured output](https://docs.litellm.ai/docs/harness/structured_output)及[客户端校验](https://docs.litellm.ai/docs/completion/json_mode)：成熟实现区分传输格式能力和客户端结构化验证，存在“明确格式提示+本地校验”的路径。核对其文档方式，不复制实现、不引入LiteLLM依赖；直接复用项目已有jsonschema、Pydantic及pydantic-core部分JSON解析。

## 实施决策

仅官方https DeepSeek精确根端点及/v1、character_dialogue目的、chat_event_reply结构化请求、JSON_OBJECT_LOCAL_VALIDATE能力使用prompt JSON：实际请求省略response_format，保留StructuredOutputRequest及严格本地验证。非流式_payload和generate两处构造均遵循同一判断，流式复用同一_payload；预留helper仍读取实际发出的同一body，费用、完整回复、关闭/取消、既有路由和不自动重试保持。选择器、世界动态池、卡片/世界书、代理和其他供应商不改传输策略。不把这称为服务端JSON保证，也不接受任意纯文本、字段别名、截断JSON或思考链作为完整角色回复。

统一私聊/群聊角色规则：reply台词与传输格式不冲突。最终格式指令要求先完成非空reply；寒暄可以events/memories=[]。活动/事件/记忆三个示例皆为完整json对象，记忆更正、原句、独立开关规则不变。台词仍严格解码，元数据无效仍可忽略，不增加修复API调用。

非流式结构化失败新增固定枚举/计数日志：reason、finish_reason、input/output/reasoning_tokens、request max_output_tokens、HTTP status和prompt_json/native_json。不记录任何角色/玩家正文、模型返回ID、schema、密钥或推理文字；未知计数不冒充0，新诊断失败不更改调用结算。流式仍沿用原终止/文本校验反馈，本轮不声称扩展了其用量日志。

本轮没有证明问题已在服务端消失。避开已知空返回传输并减少指令冲突是有限兼容修复；prompt JSON仍可能格式不合规，按现有边界报错，不自动付费重试。用户需用完整0.1.8包验收实际回复/同次事件/记忆。没有读取数据库/聊天正文/密钥、运行测试或真实API。
