# 聊天获知与公共世界动态复用调查

2026-10-01，基线7c21c8e；用户批准两块世界事件、同次回复附事件候选、手动进度及80%续批，并要求DeepSeek优先。此轮不是换模型或探测真实凭据的授权。

- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)和[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)：当日官方文档；JSON object模式已有成熟接口，需明确json提示并防截断/空输出。工具往返示例需要第二次调用，不采用为每条回复另派分类任务。优先接入DeepSeek兼容Chat Completions，不擅自替换用户已配置模型或调用测试。
- [Pydantic JSON parsing](https://docs.pydantic.dev/latest/concepts/json/)及[pydantic-core API](https://docs.pydantic.dev/latest/api/pydantic_core/)：复用已安装Pydantic/pydantic-core（MIT）的部分JSON解析和严格数据验证，不自己实现流式转义/JSON解码器，不增加新框架。
- 已核对OpenAI、Claude和Gemini官方结构化输出文档。成熟机制约束格式，不能证明自然语言事实；元数据失败不另付费修复。当前切片先做好DeepSeek JSON object与流式台词提取，其他提供商原聊天保留，后续分项适配。
- 公共事件复用现有SQLite/SQLAlchemy、Alembic、世界scheduler、有效WorldTime、已公开世界书标量投影、受控网关与硬预算、canonical EventAppender。事件池及手动进度为本产品扩展，不另装调度器/RAG/Agent引擎。

实现边界：聊天记录是有原句出处的角色自述/计划/传闻/邀请/变更，不授予世界真相或伪造亲历；获知时间与角色所述时间分开。公共池是已授权的运行时世界公告计划，逐条经Kernel接纳发布，未发布候选隐藏；不由台词或绿色标记移动玩家、发放物品、改变关系。日常Director的6小时/50%与公共事件池80%分别治理。

实现复用核对：现有DeepSeek官方recipe／encoding 0.1.0的Chat Completion schema包含response_format，转换及v4 system编码已处理JSON object格式；本地已有Rust request-bound helper因此沿用实际JSON请求payload的保守输入边界，未加一套Token计算或依赖。运行时仅对官方DeepSeek原NONE能力配置增强为JSON_OBJECT_LOCAL_VALIDATE，持久用户模型配置不改。pydantic-core部分JSON解析不向UI发送events字段，完整台词／元数据再单独校验。

聊天背景只取本人本会话最近报告及已发布公告，最多6条／4条，再按完整条目收缩至8KiB；不截断原句否定词、不读另一角色私聊。世界动态公用原director_plan模型路由及硬财务策略，运行状态和消费阈值独立；没有第二调度器或逐条判定调用。

本次uv.lock锁定版本：Pydantic2.13.5、pydantic-core2.46.5、SQLAlchemy2.0.54、Alembic1.20.0、jsonschema4.26.0；均沿用现有锁文件和许可随附，不升级依赖。
