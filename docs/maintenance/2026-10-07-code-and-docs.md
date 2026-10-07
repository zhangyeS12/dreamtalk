# 2026-10-07 审查后的文档与代码维护

本文件保留该维护／构建阶段的历史现场；其中“未提交／发布”指当时状态。后续0.1.40源码同步与外部导入验收见[记录](2026-10-07-github-source-sync.md)。

基线：`4d280cc`，分支 `codex/world-archive`。用户授权更新文档和优化代码；共同联系尚未收到消息，由用户先等待并验收。此次维护不更改共同联系的触发、间隔、费用、活动和等待回复契约。

## 已收拢的问题

| 审查项 | 本次处理 |
| --- | --- |
| 架构文档旧状态 | 同步系统、运行时、领域、内容、持久化、路由、卡兼容与 Director 当前说明；保留明确标注的历史阶段记录。 |
| 迁移 head | 当前源码为0036，0018/0014等描述归回历史语境；不读取用户存档推定其实际 cursor。 |
| 产品决定表 | P-03/P-04/P-08/P-18登记已批准子集，未定义的多人/时间线/Reflection等范围保留。 |
| 缺失使用手册 | 补齐[主动联系](../PROACTIVE_CONTACT.md)，记录合法活动、共同目的、费用、未读和原会话回复门禁；明确当前等待用户验收。 |
| 文档检查遗漏 | `check-doc-links.py`包含所有根Markdown及docs，并提供`--root`检查独立文档打包目录；只检查本地目标，不认证外部URL或锚点。 |
| 后续包内断链 | `portable_docs.py`复制根交接/产品规则，保留包内本地链接，源码/测试引用转成构建时Git引用；记录`SOURCE_REVISION.txt`。Git引用不包含未提交改动，外部可访问性仍需发布时核对。 |
| 私聊/群聊发送重复 | [useChatReplyWorkflow.ts](../../apps/web/src/useChatReplyWorkflow.ts)共享模型可用状态、草稿、保存请求ID、发送锁、失败状态读取与人工生成入口；不知道结果的模型调用不重放。私聊/群聊API和角色列表保持分开。 |
| 上下文资料重复 | `ChatContextSources`共享原构造参数；角色/玩家字段投影复用，原私聊/群聊权限校验、召回、选人和活动插入位置保持。 |
| 适配器通用处理重复 | [adapter_support.py](../../services/core/src/livingworld/infrastructure/llm/adapter_support.py)共享错误转换及三类凭据读取；各供应商Token正则与协议解析保留，compatible特殊路径不合并。 |
| 回执恢复重复 | [idempotency.py](../../services/core/src/livingworld/application/idempotency.py)共享回滚后一次新事务读取；四类服务保持原异常集合、回执方法、指纹与事务内业务校验，不再次执行操作。 |
| 迁移版本集合重复 | 将16组手写后续版本集合改为一条已审核版本链的只读集合；静态展开后，所有迁移函数AST与基线相同，没有schema/迁移脚本变更。 |
| 旧样式/依赖/空回调 | 删除确认无引用的旧CSS；移除httpx2及其独有的httpcore2/httpx2-jsfetch/truststore锁项，其余锁定版本保持；生产初始化传None，已有调用者提供的初始化函数仍受支持。 |

## 检查与交付边界

ESLint/TypeScript、全仓Ruff源码检查、18个改动Python文件格式检查及前端编译通过；两份清理CSS解析通过（product 272条/world-archive 101条规则）。仓库文档841个本地目标/0断链；独立文档打包499个本地目标/0断链，653个外部URL只计数未联网核验。四类幂等操作/回执方法/异常集合及其他业务方法保持相同，两个上下文build在展开字段投影后AST相同，迁移函数在展开版本集合后AST相同。这些是源码结构核对，不是运行验收。

全仓Ruff格式检查发现未修改的 `persistence/proactive_contact.py` 有一条既有混合行尾告警；本轮保留该文件。前端编译仍有大于500kB的chunk体积告警。

最初离线锁解析缺少ddgs缓存，改用正常索引解析后完成；未安装新依赖或升级其他锁定版本。未运行自动测试、浏览器/桌面smoke、Core、数据库迁移、模型或真实存档诊断，也未改自启动。维护阶段先在ignored的独立目录核对文档打包；随后用户要求提供新入口，进入下述独立便携打包。

本轮未提交、推送或发布。公开`v0.1.37`与原Release ZIP仍是原快照，不能把本轮源码维护和文档检查写成其内容已更新。

## 新入口打包

用户要求“把新入口给我”。Desktop package/Tauri/Cargo及对应锁文件改为0.1.38，区别于公开0.1.37；根npm/Web/Core版本、API协议与迁移head保持。使用现有仓库Python执行 `scripts/build-portable.py --build-only --output-name maintenance-0138`，退出码0，完成新EXE、冻结Core与完整ZIP。新入口为 `artifacts/portable/maintenance-0138/dreamtalk/dreamtalk-desktop.exe`，文件/产品版本均为0.1.38。没有启动程序、读取真实存档、触发联系或修改开机启动注册。最终产物、构建告警及源码/包内文档检查证据见交接第6节；完整ZIP和哈希清单保存在ignored的artifacts目录。

## 保留的维护项

`CommandHandler._mutate`的大型命令分派、迁移域结构校验和回执各类型编码器仍有维护负担；这次只收拢确定的共用部分，没有把不同领域规则合并为通用流程。

事件回放仍一次读取整个世界账本，长期存档的实际内存影响未测量；后续可按容量证据讨论流式读取。旧公开发布包断链需在后续获授权的发布中替换，本地0.1.38不自动覆盖公开Release。本轮不宣称审查中的全部维护债已消除。
