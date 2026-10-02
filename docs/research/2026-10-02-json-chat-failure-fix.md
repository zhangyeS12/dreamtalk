# 0.1.5 聊天结构化失败与公共动态背景诊断

2026-10-02，基线2e0f992，当前请求为解释并修复截图中的聊天失败和事件池未完成，不增加另一套生成框架。

## 确认的证据

当前运行的desktop／Core均来自world-event-journal完整包，非旧自启动目录。最新Core日志显示chat_structured_output_failed，说明进入完成响应的结构化校验，不足以判断API密钥无效。旧日志没有写入细分reason；现有AttemptFacts也不保留结构化错误子类，不能从单个总类推断输出一定截断／一定空回复／一定缺reply字段。

截图中世界动态是news_background_required对应提示，pending=0且最近一批0／0；背景选取未通过时claim在dispatch前返回，不存在一批已经生成但没展示的10条。公共可见授权与常驻／关键词／后台生成类型条件是独立条件，单纯已有世界书或点击生成并不满足全部条件。

默认诊断视图所见数据库为0014且没有新版表，与当前截图和日志不一致；自动审批拒绝了原存档读取，理由是此前授权只限临时副本。用户随后明确批准本次只读错误／用量／公共条目计数诊断，查询仍得到旧版本视图，因此停止该分支；未做第三次相同读取、写入、升级、修复、完整性检查或应用停止。不能把此差异说成用户存档损坏，也不能声称已取得本轮具体finish_reason／Token数。

## 成熟接口核对与修复

- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)当日官方文档：JSON模式只确保JSON形式，应用仍需明确目标示例及合理输出长度，也有空返回边界。保留既有json_object和本地严格验证，不从字段别名猜台词，不把截断正文当完整回复，不另调模型修复。
- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)及[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)当日官方文档：现代模型默认开启thinking，支持thinking.type=disabled；max_tokens限制生成输出。现有官方deepseek-recipe0.1.0请求schema已包含thinking，保守输入helper沿用实际payload，无新依赖／Token估算器。
- 同次事件提取输出规则原在角色台词规则之前。改为先角色规则，再明确最后的JSON传输规则，再原顺序会话；reply字段才是台词，历史纯台词不决定本次格式。两类小JSON任务chat_event_reply／world_news_batch仅在官方https DeepSeek端点及deepseek-flash／deepseek-v4-pro指定thinking disabled，代理／旧模型／其他任务不改，不提高用户额度或重试预算。此为减少风险的修复，未证实thinking就是这一次失败的唯一原因。
- 新增固定公开错误子类：空返回、输出长度耗尽、JSON／reply格式不合规。共享流式／非流式与私聊／群聊映射，日志仅增加allowlisted结构化reason，不记录原始回复、schema、密钥或错误正文。实际模型调用及失败用量继续结算，消息不自动重发。
- 公共背景取同一授权SQL／筛选函数，在configure进入新批排队前核对，再在claim和发布时继续核对。前置不合格立即返回安全错误，原设置／候选／计数事务不提交；没有模型调用，也没有把隐藏／未触发条目自动公开。界面明确“角色卡与世界书 → 提供条件 → 常驻背景 → 预览确认 → 公共背景”的可操作路径，排队反馈不再覆盖真实前置失败。用户仍可选择有效关键词触发而非常驻。

仅源码／静态／编译／包内核对；按AGENTS§20不运行测试、应用／GUI、真实API、凭据探测。只读诊断的限定授权不扩大为数据库升级或自动测试授权。运行效果由用户验收，后续失败可从新版安全日志区分原因。
