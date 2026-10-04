# dreamtalk 工作交接

更新日期：**2026-10-04**。本文件只保留当前工作现场与接续入口；持续规则见 [AGENTS.md](AGENTS.md)，逐项进度见 [当前状态清单](docs/PROJECT_STATUS.md)，完整旧记录见 [历史归档](docs/history/README.md)。
先读规则与当前用户要求，再核对 Git/源码。旧文档写“未实现”不能覆盖已存在的代码；代码有问题也不能自动改变用户已批准契约。

## 1. 当前任务、范围与结论

当前任务为修复主动联系无法开启与快速启动跳过动画，Desktop0.1.35源码已完成，源码检查及build-only构建结果见第6节。设置请求缺JSON头且后端strict UUID拒绝正常JSON字符串；两处一起修复，只对该UUID字段使用标准解析，保留其他严格字段及身份/revision核对。页面保留失败原因、显示已保存，未读取状态不冒充已关闭；不读取或改写用户存档开关、不自动启用付费功能。前台从三维首帧至少展示1.5秒，核心/书架并行加载，真实就绪后约900ms进入原书架；隐藏启动不强制展示，静态回退保留。协议/迁移/生成规则/自启动注册不变。0.1.34提交未改Core或开关逻辑，源码没有人为核心连接等待。详见[启动说明](docs/CELESTIAL_STARTUP.md)与[主动联系设置修复](docs/proposals/2026-10-04-proactive-contact.md)。

此前0.1.33真三维关系网和宽表单已交付源码/便携包，用户这轮转向启动体验；不据此标成全量关系网验收。0.1.30红点修复已获用户“问题已解决”反馈；0.1.31主动/离线联动仍待体验，不阻挡当前明确需求。
- 当前世界通讯录可创建、重命名、迁移、删除空阵营；子阵营不限制层级，角色可多重归属。同一个阵营的直接成员在单写事务中建立持久相识；父子和多跳关系不扩大熟人范围，撤出阵营只改变归属、不抹去已建立的相识。
- 头像复用已有世界封面图片校验、资产存储及授权读取，绑定稳定角色卡根ID。关系网改用3d-force-graph1.80.1 / Three.js0.186.1：真正三维头像球、明暗/透视/遮挡、稀疏星点、静置和聚焦后缓慢漂浮、连线同步；直接点击约260ms聚焦、左键平移/右键旋转/滚轮缩放，右侧完整姓名/阵营路径/聊天跳转。底部定位与键盘操作、暂停漂浮/减少动态效果、按需加载、切页释放及后台暂停均接线。旧全局input90px由表单字段样式覆盖，React Flow关闭交互造成的点击阻断随二维库移除；左侧选人不退出星图。当前头像用于通讯录及关系网。
- 私聊/群聊仅提供发言者本人有界阵营与相识数据，最多8个阵营、每阵营16名同伴和24名相识，合计4KiB；容量不足可整体移除，“本次参考内容”显示保留/省略。相识不证明共同经历、秘密或亲密度。
- 同阵营已确认相识满足共同休闲此前碰面的前提；仍要求已有放置角色、许可、实际同地点/活动、冷却和Kernel核验。见闻继续按真实执行记录。Director只在原批次收到有界相识ID，不额外调用模型、不立即重规划；同目的双人联系和跨路径未回复门禁保持。
- 0036只新增四张authored表；不写旧数值关系、不补造事件。不扩充委托、任务、奖励、战斗或三人以上新行动。详情见[说明](docs/CHARACTER_FACTIONS.md)和[批准方案](docs/proposals/2026-10-04-character-factions.md)。

## 2. 仓库与版本现场

| 项 | 本次实际核对 |
| --- | --- |
| 正式仓库 | `D:\LivingWorld`；当前用户工作目录 `C:\Users\zhang\Documents\ChatGPT\LivingWorld` 是受限环境可写工作目录，不据此推断正式仓库/构建产物已搬迁。 |
| 分支 | `codex/world-archive`。 |
| 本轮开始 HEAD | `42e675c`，0.1.34星梦启动提交；开始工作区干净。此前文档整理基线为1221c18，后续以实际git log为准。 |
| 此前功能提交 | `844259a`：离线恢复门禁状态提示；`ed5f844`：在线主动联系与未读红点；前序 `9939579` 授权活动终态召回去重、`ee17ed6` 共同休闲/来源回看。 |
| 桌面版本 | `0.1.35`（package/Tauri/Cargo；交付 EXE 元数据以本轮构建核对）。根 npm/Core package 的 `0.1.0` 是已有独立包版本，不误改成桌面版本。 |
| Core API | `services/core/src/livingworld/domain/api_contract.json`：`api_protocol = 1`、loopback `127.0.0.1`；随机 Core 端口，UI 不硬编码。 |
| Alembic head | `0036_character_factions`，前序 `0035_proactive_contact`。此次不运行升级或读取真实存档。 |
| Git remote | `origin = https://github.com/zhangyeS12/dreamtalk.git`；只读本地配置，不表示本地最新提交已推送。 |

启动下一任务先 `git status --short`、`git log --oneline -8`、`git diff --stat`、`git diff --cached --stat`。
不覆盖用户/其他任务改动，不强推/重写历史；临时副本如需同步使用核对状态后的 fast-forward 流程，ignored 产物不会随 Git 自动同步。

## 3. 当前能力与验收

完整条目见 [PROJECT_STATUS.md](docs/PROJECT_STATUS.md)。接续者必须知道：

- 世界书架/三面封面、通讯录角色编辑、设置手册、卡/书手动及研究生成均有实际流程。
- 私聊/群聊自动选人、@、流式、分页、预算与显式回复恢复已接线。
- 长期记忆与授权历史原句是有界本地混合 RAG；纠正/停用过滤、渐进持久向量缓存、来源面板和会话摘要已实现。
- Director 日常、活动结束/中断、本人近况与近 128 条授权经历召回已实现；0.1.28 优先同次活动的已获准终态，保留原始历史。
- 在线主动联系、同目的双人联系、统一未回复门禁、通用红点与原有单角色离线补消息、动态事件池、碰面节奏、共同休闲已有代码；不等于完整离线世界、关系或任务成果。
- 用户曾明确报告生成卡/书、单聊、群聊 @/无 @ 正常，认可书架效果；0.1.23 全页读取/连接卡顿已收到“已验收，没问题”。
- 0.1.24～28 新切片没有完整新验收结论；不能把历史反馈扩成最新版全功能通过。

## 4. 最容易误判的边界

### 4.1 记忆与当前状态

- 长期聊天条目最多 16 条/8KiB，相关授权原句最多 4 条/8KiB；权限/有效版本先于检索。
- 本地 BGE + jieba/FTS5/BM25 融合；每通道引用至多 8192，新编码每次至多 128，DiskCache 目标 256MiB。不是无限全历史检索。
- 语义等待最多 3 秒可回退关键词；原生库在控制管道/线程之前准备，不能退回冷线程并发首次导入。
- 本人快照最多 6 条/6KiB，相关亲历最多 12 条/8KiB；当前真实状态优先。终态只在已有授权窗口关联，不能按 start ID 查全局隐藏结束。
- 自动同次记忆提取与私有 EpisodicMemory 不同；后者仍要求真实 Observation。旧聊天、会话摘要、角色自述、计划与 WorldTruth 不混淆。

### 4.2 模型、额度与恢复

- 当前优先 DeepSeek，但保留 OpenAI-compatible/Responses、Anthropic、Gemini adapter；实现存在不保证任意代理/型号已验收。
- 输入+输出上限是整个生成尝试：选人、所有角色、retry/fallback 合计。可信 bounds 及账本不能因提示裁剪而绕过。
- 人工失败恢复是用户批准的新 attempt/独立额度例外；原消息/用量/claim 保留。running/unknown/部分群回复不重放，刷新不自动调用。
- 卡/书生成、Director、离线联系、动态批次独立于聊天每轮额度，仍受各任务/金额预算；不要再用提高聊天额度修复无公共背景或格式错误。
- 正常台词不需用户逐条预览；持久创作内容和会话摘要需预览确认。普通完整台词可成功但无新增元数据，不额外付费补提取。

### 4.3 世界书与事件

- 默认隐藏；明确公共后仍要 enabled、匹配常驻/支持关键词/来源条件和容量。公共条目数量不等于当次可用数量。
- 日常按角色/地点、quiet 等现有规则参与；动态池按自己的场景筛选，不能把“可供日常”当成“动态已触发”。
- 未修改条目在界面编辑更新中可保留原公开范围；改正文/触发条件、新增条目或文件替换重新确认。不要再笼统写“所有更新都重置”。
- 聊天获知保留说话者/原句/获知时间和变更，不自动认证事实；动态批次 10 条逐条发布，8/10 已经历或跳过才续批，错过不倒填。
- 玩家和每个角色的授权观察分别读取；群成员、玩家原位置、角色卡设定不授予现场目击。

### 4.4 活动与后台

- 日常每批 6 小时 WorldTime，至少 2 条且原批 50% 日常失效才提前重规划；失败不自动付费重放。
- 每批普通问候+共同开始合计最多 2 次；新见面对象每角色 24 世界小时最多一个，连续同场不刷问候；共同休闲另有每角色 24 小时一次与同对 6 小时冷却。
- 共同休闲仅 15～30 世界分钟真实休息/自由活动，结束/中断不代表任务/关系成果。
- 完全退出/关机不执行；托盘继续运行不是离线。恢复消息的剧情时间与真实生成时间分开，不补造错过的日常/碰面。
- 更新包不自动更新自启动注册；必须用户在新版设置显式“保存并更新启动位置”。本轮没有核对运行进程或改系统设置。

## 5. 代码入口与迁移

| 领域 | 当前入口 |
| --- | --- |
| UI/连接 | `apps/web/src/App.tsx`、`StartupSplash.tsx`、`celestialVortex.ts`、`Brand.tsx`、`connection.ts`、`ProductApp.tsx`、`WorldArchivePage.tsx`、`SettingsHandbook.tsx`；`packages/api-client/src`。 |
| 卡/书与公共背景 | `application/content_builder.py`、`lore_activation.py`、`infrastructure/persistence/world_content.py`；WorldContent/ContentEditor。 |
| 聊天/预算/恢复 | `application/chat_context.py`、`group_chat_context.py`、`chat_reply.py`、`group_chat_reply.py`、`chat_capacity.py`；`infrastructure/persistence/chat_reply_recovery.py`。 |
| 记忆/RAG | `application/long_chat_memory.py`；`infrastructure/persistence/long_chat_memory.py`、`infrastructure/chat_retrieval.py`、`semantic_chat_retrieval.py`。 |
| 经历/当前活动 | `application/character_activity_context.py`、`routine_lifecycle.py`、`experience_lifecycle.py`；`infrastructure/persistence/observed_events.py`。 |
| 世界事件 | `application/chat_event_annotations.py`、`world_story.py`；`infrastructure/persistence/world_story.py` 与对应 HTTP。 |
| Director/社交/离线 | `application/director.py`、`character_encounters.py`、`shared_activities.py`、`offline_contact.py` 及对应 persistence。 |
| 桌面生命周期 | `apps/desktop/src-tauri/src/lib.rs`、`supervisor.rs`、`llm_config.rs`、`credentials.rs`；`bootstrap/cli.py`、`infrastructure/database.py`。 |

上表 Python 路径相对 `services/core/src/livingworld/`。API 模块在 `adapters/http/`；WorldTime 为逻辑 epoch 整数微秒、UTC 为现实时间，不能隐式互换或经过浮点微秒。

重要增量：0023 资料任务、0024 摘要、0025 日常、0026 地点目录、0027 离线、0028 两块事件、0029 长期聊天记忆、0030 封面、0031 人工恢复、0032 参考记录、0033 相遇、0034 共同休闲、0035 主动联系/阅读位置、0036 阵营/头像/持久相识。
历史迁移/事件版本/稳定 ID 保持；旧结构 shape 检查不放松。0032 的追加列顺序必须与 ORM 一致，不能重复引入已修复启动问题。
不要用旧包打开已升级存档；不要把代码核对称为真实存档升级验证。

## 6. 交付与证据

### 0.1.35 主动联系保存和启动最低展示

源码修复及范围见第1节，版本同步package/Tauri/Cargo/npm锁文件。前端ESLint/tsc、目标Python Ruff lint/格式、文档链接（0断链）及Git差异检查通过；`--build-only --output-name startup-proactive-fix`完成。Desktop ProductVersion/FileVersion均为0.1.35，新包`artifacts/portable/startup-proactive-fix/dreamtalk`与同级`dreamtalk.zip`；旧包保留。Core HTTP适配源码与包内原文件核对；根规则/交接/产品及docs随包同步，静态清单位于`artifacts/startup-proactive-fix-source-audit.json`。未运行产品、自动测试、模型或真实存档；保存持久性、至少1.5秒画面和主动联系仍待用户体验。

Desktop SHA256 `aa81b23dcc2795efac06e72453b59a94abe1318a5922fdb097e382088674dd38`；Core SHA256 `2d7bc064f1af15e7525108e4465bb492ea89e308889e95b8c9e152f3a43baa94`。本轮仅Core HTTP请求字段适配改变，无持久化/迁移/生成规则修改。构建有非阻塞大chunk告警（主709.62kB、共享Three.js587.98kB、关系网817.51kB）及STATIC_VCRUNTIME弃用；不隐藏告警或声称帧率已验收。

### 0.1.34 星梦启动与新Logo

Three.js0.186.1真实空间流星、明暗球体/遮挡、星点和透视相机；900ms真实就绪后的穿越/透明交接。原Logo字节保留，TauriCLI2.11.4转换窗口/托盘/任务栏图标和favicon，页头复用Brand。书架数据及有界封面就绪接线、失败只读重试、减少动态效果/静态回退、隐藏启动与资源释放完成。没有改Core/协议/迁移或自启动注册。

前端ESLint/tsc、图标脚本Ruff格式/lint、本地文档链接及Git差异检查通过；`--build-only --output-name celestial-startup`已完成。后续启动读取取消修正已重新编译桌面并同步EXE，包内文档/ZIP重新生成核对。ProductVersion/FileVersion为0.1.34。新包`artifacts/portable/celestial-startup/dreamtalk`及同级`dreamtalk.zip`；原Core与0.1.33字节哈希相同，旧包保留。尚未启动产品、执行自动测试、真实存档或模型；图标与原Logo元数据及当前源码/产物清单见`artifacts/celestial-startup-source-audit.json`，不是运行验收。

保留非阻塞告警：主chunk707.79kB（gzip210.68kB）、共享Three.js587.98kB（gzip145.15kB）、关系网817.51kB（gzip233.11kB）、STATIC_VCRUNTIME弃用；启动场景单独6.64kB（gzip2.95kB），Three与关系网按需加载。图标CLI提示Windows某字体文件无法加载，源SVG仅嵌PNG，产物存在并具备所需透明/尺寸层；未隐藏告警，也没有声称GPU/帧率验收通过。Desktop SHA256 `a5533aa30f76743baf93409f4eb9a3723639e597d5915c559ac31a9034fe75cf`；Core SHA256 `fcb37748d6a6a9f3da5f81ad3d9df1b6488963099c799c8011030f3e2e7387b0`；原Logo SHA256 `15cc4b6eb20b831282cdf3134c4b037809d6ff6944330edaf6b248df0e76fd6e`。

### 0.1.33 三维人物关系网优化

用户反馈0.1.32名称框过窄、图内头像无法点击、球体像平面。源码定位：全局input宽90px且阵营字段没有覆盖；React Flow节点既不draggable/selectable且外层未设置onNodeClick，库将pointerEvents设为none。当前用产品字段样式加宽表单，替换成3d-force-graph1.80.1 / Three.js0.186.1真三维头像球、透视/明暗/遮挡、图内拾取与相机动画，静置/聚焦后缓慢漂浮、连线跟随，保留右侧姓名/阵营/聊天。按需加载、切页释放、后台暂停、减少动态效果和键盘定位均已接线。没有改Core、迁移、财务/角色相识契约。

`npm run lint`（ESLint/tsc）、文档链接（741本地目标无缺失）与`git diff --check`通过；`--build-only --output-name relationship-universe`完成，未启动产品、运行自动测试/模型/真实存档。Desktop ProductVersion/FileVersion为0.1.33。新包：`artifacts/portable/relationship-universe/dreamtalk`及同级`dreamtalk.zip`；旧包保留。41个运行/类型依赖许可已纳入文档和包，源文件/文档/ZIP核对记录保存于`artifacts/relationship-universe-source-audit.json`，不等同交互与视觉验收。

构建仍有非阻塞告警：主chunk688.54kB（gzip205.38kB），按需三维chunk1403.12kB（gzip376.58kB），STATIC_VCRUNTIME弃用。三维chunk只在打开关系网时加载；没有隐藏告警或据此声称运行性能通过。Desktop SHA256 `d557b3a3ef0ded6e4596a6e860d61200141687bddb1c2ffd35a4daed4bed4382`；Core SHA256 `fcb37748d6a6a9f3da5f81ad3d9df1b6488963099c799c8011030f3e2e7387b0`，Core与0.1.32相同。

### 0.1.32 阵营、头像与关系网

源代码、前端ESLint/tsc、目标Python Ruff格式/lint、14份AST及77个本地文档目标检查通过；`--build-only --output-name character-factions`完成。迁移列序、约束、旧版本识别按源码核对；未执行数据库诊断、自动测试或桌面/模型调用。新包：`artifacts/portable/character-factions/dreamtalk`、同级`dreamtalk.zip`；Desktop ProductVersion/FileVersion均为0.1.32，14份变更Core源码（含0036）与包内原始文件字节一致，依赖许可纳入docs及third-party-licenses。旧包保留，真实效果仍待用户验收。

构建保留非阻塞告警：前端主chunk867.43kB（gzip264.31kB），STATIC_VCRUNTIME弃用，以及PyInstaller可选平台/后端模块缺失提示；没有据此声称运行兼容通过。Desktop SHA256 `04b16e54b3d5612842d3829967c4927c0ccdf69e10055f30f24db6ab0e362304`；Core SHA256 `fcb37748d6a6a9f3da5f81ad3d9df1b6488963099c799c8011030f3e2e7387b0`。静态产物清单位于`artifacts/character-factions-source-audit.json`。

### 0.1.31 主动联系与离线恢复状态

源码确认在线/离线共用同一世界与玩家的持久门禁：已送达的主动联系必须在原会话收到玩家后续回复，阅读和清红点不释放。此前离线恢复被该门禁阻断时只保存 `offline_no_contact`，容易误认没有触发。现在保存 `offline_waiting_reply` 或 `offline_contact_in_progress` 并显示相应说明；若同一离线理由也已使用，未回复提示优先。旧笼统状态仍显示兼容说明；没有改变实际发送、重试、费用或迁移。

`npm run lint`、目标 Python Ruff check/format、`git diff --check`、文档链接检查通过；`--build-only --output-name outreach-linkage` 完成，Desktop `ProductVersion/FileVersion 0.1.31`，Core 与 0035 迁移均在新包/ZIP 内。交付路径：`artifacts/portable/outreach-linkage/dreamtalk` 和同级 `dreamtalk.zip`；ZIP 无重复条目，打包的状态文档与当前源码文档字节一致。未运行桌面、真实存档、模型或付费调用，实际离线恢复提示仍待用户体验。

### 0.1.30 已读红点修复

用户已确认 0.1.29 中查看消息后会话名与底部“聊天”红点都不消失。静态定位：阅读确认先请求桌面状态，任一次失败都可能阻止实际已读写入；失败曾静默吞掉且尝试次数有限；旧未读快照请求也可与成功确认竞态。现在仅在前台可见且焦点窗口对可见的已加载消息提交已读位置，写入失败最多尝试 3 次并显示手动重试，成功后取消旧未读请求并重新读取。没有改变未回复主动联系门禁或数据库迁移。

`npm run lint`、`git diff --check`、文档链接检查通过；`--build-only --output-name unread-clear` 完成，Desktop `ProductVersion 0.1.30`，Core 与 0035 迁移均在新包/ZIP 内。新包为 `artifacts/portable/unread-clear/dreamtalk`、同级 `dreamtalk.zip`；0.1.29 旧包保留。构建轮次未代用户运行桌面、真实存档或模型。

2026-10-04 后续用户反馈“问题已解决”：0.1.30 原红点不清现象已由用户体验确认解决。此反馈不覆盖双人主动联系、等待回复门禁、离线联动或其他回归场景。

### 0.1.29 主动联系切片

源码已接线；Python lint/compileall、前端 ESLint/tsc、文档链接通过。`--build-only --output-name proactive-contact` 完成，核对 Desktop/Core EXE、ZIP、0035 迁移与打包文档存在；ProductVersion 0.1.29。运行验收仍由用户负责，本轮不调用付费模型或实际存档。新包路径：`artifacts/portable/proactive-contact/dreamtalk`，ZIP 为同级 `dreamtalk.zip`；旧 0.1.28 包保留。EXE SHA256：Desktop `a0fb8bf76dde344f6105935fc6bc66eb81a5f198b636c09194f7a21da3eb111d`、Core `c4b865514ffd9cfbf6d3b509f3876e98c735b646cc8f166f118847c4be0fe755`。

### 历史 0.1.28 包与证据

当时完整包（本轮核对 EXE 存在与 ProductVersion 0.1.28）：

```text
D:\LivingWorld\artifacts\portable\experience-state\dreamtalk\dreamtalk-desktop.exe
D:\LivingWorld\artifacts\portable\experience-state\dreamtalk\core\dreamtalk-core.exe
D:\LivingWorld\artifacts\portable\experience-state\dreamtalk.zip
```

保留完整目录/core/本地语义模型，无需本机重新解压已有目录。旧包保留但不是默认最新入口。
0.1.28 历史交接记录：build-only 的 PyInstaller/Core、Vite、Rust 完成；233 份冻结源码、包/ZIP 与模型/许可核对完成。
记录的 SHA256（历史包核对结果，本轮未重新全量 hash）：

| 文件 | SHA256 |
| --- | --- |
| Desktop | `acafc250d5ab563f2474502be1686b2de125c1591209784de30b211134dc49bc` |
| Core | `6631bf0794d880c77cb0a08fc6eb97890b6f2bccc8af5e6a4b80fcee88dc1082` |
| ZIP | `55fb9bcfe8e28831aaf0a57964317e3619d35f2b9af60fa37d7c2320c92bc3b6` |

构建/静态清单在 `artifacts/experience-state-build.log`、`experience-state-source-audit.json`、`experience-state-audit.json`；ignored，不当作 Git 已同步文件。
历史告警保留：前端主 chunk >500kB、STATIC_VCRUNTIME 弃用、PyInstaller 可选 tzdata/pysqlite2/MySQLdb 提示；没有据此宣称运行兼容已通过。
以上旧包仅属于 0.1.28 历史记录；0.1.29 与 0.1.30 的源码和便携包在第六节分别列明，实际完成以构建记录为准。

## 7. 可用命令与检查约束

在正式仓库先核对依赖再执行需要的命令，不因交接列出命令就运行产品：

```powershell
git status --short
git log --oneline -8
git diff --check
.\.venv\Scripts\python.exe scripts\check-doc-links.py
```

需要打包且属于后续实现时：`npm run build:portable -- --build-only`；若 uv cache 权限阻塞而现有 venv 有打包依赖，可用 `.\.venv\Scripts\python.exe scripts\build-portable.py --build-only`。
开发入口为 npm `dev:desktop` / `dev:web` / `dev:core`；本轮不启动。UI dev 1420 不是 Core 端口，多个 launcher 不要抢占同一 UI 端口。
默认打包脚本可能包含 smoke，不能漏掉 `--build-only`。不运行测试、GUI、provider、数据库诊断或凭据探测；以前的单次诊断许可不可当长期授权。
用户 app-data identifier 仍 `app.livingworld.desktop`；开发数据历史位置 `%LOCALAPPDATA%/LivingWorld/development`。不自行移动/删除存档或数据库 WAL。

## 8. 下一步、限制与疑问

先验收0.1.35主动联系同意开启、刷新与重开保持状态，以及快速启动至少1.5秒三维展示/相机推进。按[启动说明](docs/CELESTIAL_STARTUP.md)核对隐藏后台、静态回退和失败重试；自动联系真正送达仍需合法活动/许可/间隔/回复门禁。三维关系网按[验收说明](docs/CHARACTER_FACTIONS.md)继续体验，不扩充玩法。

1. 启动/保存修复0.1.35和三维关系网0.1.33已有源码；0.1.35源码检查及便携build-only已完成，运行与画面待用户体验。没有必需新产品决定。
2. 主动联系仍有待验收：同一真实共同休闲的两名角色是否同目的邀请、未回复是否阻断跨角色后续联系、回复后是否在下一合法机会恢复。已有相识不代表一定会主动联系；活动、许可、冷却和门禁仍有效。
3. 以前经历终态/身份隔离、共同休闲生命周期和来源回看仍待体验，缺少验收不表示没实现。0.1.30红点清除已获用户确认。
4. 最终发行等待用户验收和明确批准；本轮只本地提交，不push/Release、不修改自启动或现有存档。

维护建议：直接更新当前状态和现场，完整历史通过Git/归档追溯。版本升级后由用户显式保存后台设置更新自启动路径；不要让旧便携版打开已升级存档。

## 9. 前次文档整理解决的冲突（历史记录）

| 旧说法/现场 | 当前事实与处理 |
| --- | --- |
| AGENTS 核对日期 2026-09-29 | 纳入截至 2026-10-04 已批准的恢复、相遇节奏、共同休闲、记忆/事件/离线及范围纠正；不新增授权。 |
| 多个“最新接续”与底部旧 master/1e7843c/no remote | 当前单一现场为 codex/world-archive/1221c18 整理基线，已配置 GitHub origin；原文移归档。 |
| 长期记忆/语义检索/持久索引/流式/Director 尚未实现 | 当前代码均有具体实现；真实效果和完整愿景另列，不再重复作为新功能。 |
| migration head 0022 | 当前 0035_proactive_contact；保留历史链，不实际执行升级。 |
| 默认使用 9 月便携包或泛称 artifacts/portable/dreamtalk | 先前使用 experience-state 的完整 0.1.28 包；0.1.29 另建便携包后以实际交付路径为准；不擅自替换运行进程/启动注册。 |
| 所有世界书更新都重置范围 | 当前界面编辑可保留完整未改条目范围；新/改条目与文件替换重新确认。 |
| 共同委托是下一步 | 用户已否定，撤回，不构成需求或授权。 |

旧根文件以原始字节保存为 [AGENTS 归档](docs/history/2026-10-04/AGENTS.before-consolidation.txt)、[HANDOFF 归档](docs/history/2026-10-04/HANDOFF.before-consolidation.txt)。归档是历史证据，不覆盖当前规则或排期。

## 10. 前次文档整理记录（历史记录）

- AGENTS 从 899 行收敛为 267 行，保留原编号关键边界、用户测试责任和已批准契约；交接从混合历史改为单一当前现场。
- 新增当前状态清单、完整原字节归档及 SHA256 索引；README 补当前入口。归档 Git 属性只保证 CRLF 原字节保存，不修改产品代码或测试规则。
- 实际静态核对：716 个本地 Markdown 目标无缺失（包括根 AGENTS/HANDOFF）；26 个明确源码路径存在；两份归档 SHA256 匹配且内容与整理基线一致。319 个外部 URL 仅计数，本轮没有联网探测。
- 前次仅整理文档，没有修改当时的应用行为/版本/迁移/用户存档；0.1.29 的新增功能、迁移与新包以本文件第一、六节和当前状态清单为准。
- 本轮仅作本地文档提交，具体哈希见 git log；不 push 或发布。
