# 2026-10-07 体验反馈修复 · Desktop0.1.40

本文件保留该维护／构建阶段的历史现场；其中“未提交／发布”指当时状态。后续0.1.40源码同步与外部导入验收见[记录](2026-10-07-github-source-sync.md)。

正式仓库`D:\LivingWorld`，HEAD基线`4d280cc`，分支`codex/world-archive`。保留前轮未提交的0.1.38去重维护与0.1.39长历史改进；本轮源码／文档未提交、推送或公开发布，GitHub仍为v0.1.37。

## 反馈、原因与变化

1. **连续同角色主动联系**：用户确认三次之间均在原会话回复。在线选择真实合格活动、优先同一次共同休闲，随后按计划／候选ID稳定哈希排序；离线Director按获准性格／背景／活动意图选人。没有角色额外权重，也没有轮换保证；其他角色缺已打开私聊、有效休闲／地点／计划等会减少合格候选。没有读取真实Episode，不能断定该存档每次具体原因或概率；选人／间隔／门禁未变，共同联系仍等待用户。
2. **通讯录主区太小**：复用既有React、原生details、CSS与草稿接线，隐藏重复页标题，去掉重复世界说明／添加按钮，管理入口收拢；桌面左列220px、横向外边距16px，头像88×104px、减少资料留白，阵营不再嵌套65vh滚动。没有新依赖／渲染器／迁移；静态布局审查使用impeccable，实际缩放和窄窗口待验收。
3. **相同活动／邀约漏记**：用户给出的同文休息开始时间分别为第5天19:08、第6天02:52／16:11、第7天16:24，文案来自`CharacterRoutineStarted`亲历投影，并非聊天注解。查询按event ID聚合观察，不能把不同时间的真实活动按同文删除；界面将亲历独立于聊天获知。普通同次注解明确条件邀约属于邀请，保留收工／时间允许／太晚不等的条件。在线邀请与离线`invite_chat`在送达事务记录完整原话，不新增API，离线问候不记录；超过1000字则省略可选元数据。现有原句／来源指纹及元数据可选边界保持；旧聊天不自动补录，普通模型仍可能漏记。
4. **动态显示过多**：用户明确确认最多5条进行中，绿／灰腾位、红占位。复用现有储备表与Kernel，按候选可用时间先后，每个事务最多发布5条补齐空位；窗口满时不发布。候选未到期不提前、过期取消、发布时间用当前真实世界时间。未发布正文不出接口／角色上下文；旧已发布账本不撤销，UI按发布时间先展示最早5条未处理项，其他依次补入。已处理折叠为历史；改回红色可进入待展示队列。每批10条／8条处理后续批／总容量／费用／授权／暂停不变，补位本身不调用模型。

## 源码入口

- 通讯录：[ProductApp](../../apps/web/src/ProductApp.tsx)、[样式](../../apps/web/src/world-terminal.css)；既有`WorldContent.tsx`／`ContactSocial.tsx`接线保持。
- 条件邀约：[chat_event_annotations.py](../../services/core/src/livingworld/application/chat_event_annotations.py)；主动邀请：[在线持久化](../../services/core/src/livingworld/infrastructure/persistence/proactive_contact.py)、[离线持久化](../../services/core/src/livingworld/infrastructure/persistence/offline_contact.py)与`record_contact_invitation`。
- 动态：[Kernel](../../services/core/src/livingworld/application/world_story.py)、[储备／标记](../../services/core/src/livingworld/infrastructure/persistence/world_story.py)、[展示](../../apps/web/src/WorldEventJournal.tsx)、[设置文案](../../apps/web/src/WorldNewsSettings.tsx)。

## 检查与交付

ESLint／TypeScript、全仓Ruff检查、5个Python格式／AST、3个SELECT表达式SQLite源码编译（无数据库连接）、世界内349条CSS规则解析通过；文档868个本地目标0断链，Git差异无空白错误。Ruff初次发现导入顺序／行长及混合换行，已修复；Git提醒CRLF／LF规范化，不是差异检查失败。

构建命令：`.\.venv\Scripts\python.exe scripts/build-portable.py --build-only --output-name feedback-0140`，退出0，Core重新冻结、Desktop release编译完成；EXE FileVersion／ProductVersion均为0.1.40。使用构建脚本中已核对的build-only分支，不执行Core／Cargo smoke。不添加／运行自动测试、不启动应用、不读取或迁移真实存档、不调用模型、不修改系统自启动。

Desktop SHA256：`7f7f0beead89f0efae6b9554be91c5d743f1b2d2f82b36f123b33b7c5ce1967b`。Core SHA256：`186803500b01ece48c13e4b5b0ec751ac18678cc3cccb3177525e8a4b0795bc4`。日志`artifacts/feedback-0140-build.log`，最终ZIP哈希和字节核对另存`artifacts/feedback-0140-build.json`（ignored，不属于Git发布）。

构建告警：主JS718.19kB、Three587.98kB、关系网817.51kB超过500kB提示；Rust `STATIC_VCRUNTIME`配置弃用；PyInstaller未找到可选`tzdata`／`pysqlite2`／`MySQLdb`，jieba已有转义SyntaxWarning。没有把告警当成运行验收通过，也没有通过修改依赖／压低检查隐藏告警。

独立入口：`artifacts/portable/feedback-0140/dreamtalk/dreamtalk-desktop.exe`，ZIP在同级`dreamtalk.zip`。API1、迁移源码head0037保持；运行迁移和效果由用户验收。先从旧程序托盘退出再打开新版，单实例会复用仍在运行的旧程序。包内文档在构建后同步为本轮完整记录，不表示旧公开包已更新。

## 接下来／疑问与建议

用户验收：资料／阵营是否显著更宽高且草稿保留；条件邀请是否正确保留限制；亲历是否不再被误认聊天重复；默认候选就绪后只5条，绿灰处理2条补2条，红不腾位，历史／旧过量队列／暂停重启正确。原长历史改进继续按前轮范围验收。

如果希望角色联系更均衡，可以讨论在所有实际合格候选中优先最近较少联系者；这是尚未批准的选人政策建议，不是当前实现，也不放宽共同联系理由。当前没有阻挡本轮修复的必要问题。
