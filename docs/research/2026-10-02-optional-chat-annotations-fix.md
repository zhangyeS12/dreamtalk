# 2026-10-02：完整台词与可选聊天资料分开校验

## 实际证据

用户反馈0.1.8仍不回复。只读进程路径确认桌面和Core均来自artifacts/portable/empty-reply-fix/dreamtalk，排除本次正在运行旧包的猜测。安全日志core-06bd7033-465d-4711-b136-c77b01a2705f.jsonl在日本时间19:04:50记录：HTTP 200、finish_reason=stop、input_tokens=7870、output_tokens=33、max_output_tokens=173315、transport=prompt_json、reason=json_parse_failed，trace_id=52d6ea35-cb6b-45f7-bf3f-3d86f58035d6。

这次是非空正文在JSON校验中失败，不是18:38/18:48的empty_output。没有记录或读取本次正文，不能确定它是普通台词、代码块还是损坏JSON，也不能宣称提供商内部原因已经得到证实。没有用户DB、凭据或模型调用。用户先前提供的名称“deep seek”不是已核实的API ID；不修改真实配置或凭猜测提高额度。

0.1.8只省略官方DeepSeek原生response_format，仍以StructuredOutputRequest要求网关先验证JSON。应用层尚未拿到台词就已报错，所以提示词调整没有解决整个格式边界。

## 成熟实现与选择

- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)记载JSON模式的空正文边界；前一轮已核对，此轮不把它作为当前json_parse_failed的解释。
- [官方Chat Completions接口](https://api-docs.deepseek.com/api/create-chat-completion/)区分普通文本和response_format。
- [LiteLLM JSON mode](https://docs.litellm.ai/docs/completion/json_mode)介绍客户端格式提示及验证。采用现有客户端边界，不引入框架，也不复制第三方实现代码。

直接使用项目已有Python json、Pydantic及pydantic-core：解析器负责JSON语法、转义及有界流式部分解析。产品适配仅识别完整单层代码块和是否属于资料对象，不自写JSON修复器、不付费重试或二次提取。

## 实现

私聊和群聊的annotate_request仍提示同次reply/events/memories，但使用应用内部chat_reply_encoding标记，不再声明必需的provider structured_output。该标记不发往服务商；实际提示和普通文本payload继续进入原请求预留、路由、财务结算。精确官方DeepSeek Flash/V4 Pro原小任务thinking策略保留，其他服务和结构化任务策略保持。

完整普通台词在原调用身份、结束状态、用量边界及64KiB检查后可保存；事件和记忆为空，不补调用。完整JSON或完整单层json代码块仍只显示非空reply，并按原句、当前权限、来源和开关校验元数据。以对象／数组／代码块开始或含带引号reply/events/memories成员的损坏内容拒绝；不截取半截reply，不把元数据当台词。流式普通文本直到终态验证才发一份完整台词；合法JSON可继续渐进显示reply，最终校验不得与已显示前缀矛盾。暂存流式文字仍不等于成功落库。

不影响公共世界动态、选择器、内容生成的严格结构化协议。长期记忆已有条目和历史原文召回继续可用；模型只返回普通台词时该次不会新增事件或长期条目，这是明确的降级范围。NaN/Infinity和重复JSON成员不被接受。没有改表、迁移、Kernel活动生命周期、角色权限或捕获开关。

官方非流式聊天增加chat_annotation_response_facts，仍仅记录固定枚举及数字计数，不记录正文、推理、模型ID、密钥或自由文本。该日志只说明提供商响应，chat_completed也不代表应用最终已保存；诊断失败不改变费用结算或重发。

## 验证范围

只做源码和diff审阅、Ruff/格式、ESLint/TypeScript、AST／版本／文档静态核对、Core与桌面编译及完整新包字节核对。按[AGENTS第20节](../../AGENTS.md)没有测试、应用启动、GUI、真实API、凭据探测或用户数据库读写。用户实测决定本次33Token响应是否落在兼容范围；不能声称所有JSON损坏或空正文均已解决。
