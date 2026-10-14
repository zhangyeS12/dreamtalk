# 0.1.73角色表情回复格式修复

日期：2026-10-13。用户反馈角色尝试发表情会让整条回复失败、文字也没有；界面明确提示“模型返回的格式不符合聊天要求，完整回复未保存”。源码0.1.73、API1、迁移head0049_local_model_limits、配音revision7；未提交／发布，不打包。

## 定位与证据边界

本轮只读核对运行程序为0.1.72，并读取最新两份Core日志的固定时间、事件、结束标记和数值用量字段。近期模型请求有HTTP200／finish_reason=stop；结合用户提供的格式失败提示，可确认失败在回复格式校验层，不能据此将每条模型调用都视为已保存的聊天回复。

源码存在两处媒体提示问题：原来虽要求非空备用reply，但示例只展示media对象，没有完整回复外层；授权候选另追加为最后一条USER消息，覆盖了真实玩家问题的末尾位置，易使模型只回答附件数据。没有读取被拒绝的模型正文，原日志也未记录JSON形状，因此不能断言这次一定缺reply、空reply或是哪一个JSON字段错误。

没有读取真实聊天、图片、角色卡、凭据或数据库，没有重新生成／恢复回复或触发搜索与模型测试。

## 修正

- 媒体候选改为原有USER资料对象内的`chat_media_context`，不另加最后一条玩家消息；原消息顺序与实际玩家问题保留。它仍是非特权数据，角色／世界／库权限在读取前过滤，说明和候选不进入SYSTEM内容。ContextPacker渲染同一JSON时保留此字段，继续按实际完整请求做原预算准入。
- 提示改为完整reply／events／memories／media示例，明确只发图使用`media.only_media=true`，非空reply作为附件不可用时的自然备用台词；成功发送图片时沿原only_media展示规则处理，不放宽完整JSON与非空台词校验。
- 私聊／群聊均接入格式失败固定分类：JSON无效、外层类型错误、缺reply、reply类型错误、空reply、过长reply、流式不一致。仍向UI返回原`chat_reply_format_invalid`，仅日志增加`chat_media.reply_format_*`固定事件；不记录原句、JSON值、媒体描述或用户身份。日志文件I/O失败不替换原校验错误。
- 不拼凑坏JSON、不将无效结构当普通台词保存、不额外调用模型补台词，不自动重试或恢复；表情库隔离、每原轮一次搜索、频率、群聊共享限制、整轮Token预算和持久回执保持。
- 沿用现有JSON／Pydantic解析、ContextPacker及StructuredLogger，不新增依赖、迁移、供应商或架构。

## 核对与体验入口

四份Python Ruff／格式／AST核对通过。没有添加或运行自动化测试、产品／UI／模型smoke或真实存档迁移。必要编译沿既有`npm run build:desktop`（调试、`--no-bundle`），使用独立`CARGO_TARGET_DIR=apps/desktop/src-tauri/target/sticker-reply-0173`，不覆盖运行中的0.1.72，也不结束应用或服务。

编译53.82秒、退出0；EXE产品版本0.1.73、30,412,800字节、Windows GUI Subsystem=2，SHA256 `9b92dba16f2f7a20fc790c9067ad81735e3923b5b526bde1619b508c70c24cab`。原前端构建资源哈希与0.1.72一致；仍有既有大chunk及STATIC_VCRUNTIME弃用告警。文档1097个本地目标、0断链，相关Git差异空白核对通过；Python既有真实路径定位警告未影响检查退出状态。

直接入口为`apps/desktop/src-tauri/target/sticker-reply-0173/debug/dreamtalk-desktop.exe`，依赖当前仓库及`.venv`。用户从托盘退出旧版后打开0.1.73，自行确认发文字＋表情、只发表情、群聊、频率拒绝／素材不可用时的自然文字回退；工程端不发起这些验证。若格式仍失败，先读取新增固定类别再定位，不以提示修改或编译成功推定实际模型已验收。
