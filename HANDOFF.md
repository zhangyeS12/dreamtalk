# dreamtalk 工作交接

更新日期：**2026-10-04**。本文件只保留当前工作现场与接续入口；持续规则见 [AGENTS.md](AGENTS.md)，逐项进度见 [当前状态清单](docs/PROJECT_STATUS.md)，完整旧记录见 [历史归档](docs/history/README.md)。
先读规则与当前用户要求，再核对 Git/源码。旧文档写“未实现”不能覆盖已存在的代码；代码有问题也不能自动改变用户已批准契约。

## 1. 当前任务、范围与结论

用户反馈 0.1.29 查看消息后，会话名和聊天导航红点均未清除；0.1.30 修复后，用户明确回复“问题已解决”。当前 0.1.31 针对主动联系与离线恢复的状态提示做窄修复。**仅将红点已读问题记为用户验收通过；在线联系的同目的双人邀请、未回复门禁和离线联动等其他场景仍待体验。**

- 在线设置每世界/当前玩家默认关闭、首次后台费用同意；最短间隔 15～1440 世界分钟，默认 360，首次启用只建立基线。仅从已执行的休息/自由活动中选择；双人从同一个已开始共同休闲中选择。同一个日常 plan 只领一次，不能把不同任务凑成共同邀约。现有 `character_dialogue` 模型路由单次生成该轮全部角色消息，失败/中断不自动重放。
- 在线/离线共用 SQLite 写事务门禁。占用中或已有未获原会话回复的 outreach turn，其他角色不会发新联系。用户实际保存的后续消息解除门禁；单纯打开会话/清红点/重启/开关不解除。
- 会话阅读位置单独持久化。角色新消息使相应私聊/群聊和聊天导航出现红点；可见且已加载的消息才标已读。0035 迁移给旧消息建立已读基线，保留原离线未读。
- 0.1.29 阅读确认曾依赖一次额外 Tauri/Core 桌面状态调用，失败被静默吞掉且仅尝试两次；未读快照请求与确认同时进行时还可能覆盖新状态。0.1.30 改为前台可见消息直接提交已读位置、失败有界重试和显式手动重试；确认后取消旧快照、重新读取。用户已确认原红点问题解决，不据此推定其他功能通过。
- 0.1.31 源码核对在线/离线共用未回复门禁后，修正离线恢复的可见跳过原因：未回复原主动联系优先于同一离线理由已处理；并发联系单独提示。只使用原设置记录的错误码字段，不加迁移、不触发模型、不重放已跳过的恢复。旧 `offline_no_contact` 记录可能包含未回复，界面保留兼容说明。
- 仍不扩充到委托/任务/奖励/战斗或三人以上新共同活动；购物/电影的示例只有在后续有真实获准活动时才能成为具体共同目的。当前项目状态以 [状态清单](docs/PROJECT_STATUS.md) 为准，详细边界见 [实施契约](docs/proposals/2026-10-04-proactive-contact.md)。

## 2. 仓库与版本现场

| 项 | 本次实际核对 |
| --- | --- |
| 正式仓库 | `D:\LivingWorld`；当前用户工作目录 `C:\Users\zhang\Documents\ChatGPT\LivingWorld` 是受限环境可写工作目录，不据此推断正式仓库/构建产物已搬迁。 |
| 分支 | `codex/world-archive`。 |
| 文档整理前 HEAD | `1221c18a019874b1bc5de2deeeed8043d75f666c`，范围纠正文档提交；开始工作区干净。后续以实际 `git log` 为准。 |
| 当前功能提交 | `ed5f844`：在线主动联系与未读红点；前序 `9939579` 授权活动终态召回去重、`ee17ed6` 共同休闲/来源回看。 |
| 桌面版本 | `0.1.31`（package/Tauri/Cargo；交付 EXE 元数据以本轮构建核对）。根 npm/Core package 的 `0.1.0` 是已有独立包版本，不误改成桌面版本。 |
| Core API | `services/core/src/livingworld/domain/api_contract.json`：`api_protocol = 1`、loopback `127.0.0.1`；随机 Core 端口，UI 不硬编码。 |
| Alembic head | `0035_proactive_contact`，前序 `0034_shared_activities`。此次不运行升级或读取真实存档。 |
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
| UI/连接 | `apps/web/src/App.tsx`、`connection.ts`、`ProductApp.tsx`、`WorldArchivePage.tsx`、`SettingsHandbook.tsx`；`packages/api-client/src`。 |
| 卡/书与公共背景 | `application/content_builder.py`、`lore_activation.py`、`infrastructure/persistence/world_content.py`；WorldContent/ContentEditor。 |
| 聊天/预算/恢复 | `application/chat_context.py`、`group_chat_context.py`、`chat_reply.py`、`group_chat_reply.py`、`chat_capacity.py`；`infrastructure/persistence/chat_reply_recovery.py`。 |
| 记忆/RAG | `application/long_chat_memory.py`；`infrastructure/persistence/long_chat_memory.py`、`infrastructure/chat_retrieval.py`、`semantic_chat_retrieval.py`。 |
| 经历/当前活动 | `application/character_activity_context.py`、`routine_lifecycle.py`、`experience_lifecycle.py`；`infrastructure/persistence/observed_events.py`。 |
| 世界事件 | `application/chat_event_annotations.py`、`world_story.py`；`infrastructure/persistence/world_story.py` 与对应 HTTP。 |
| Director/社交/离线 | `application/director.py`、`character_encounters.py`、`shared_activities.py`、`offline_contact.py` 及对应 persistence。 |
| 桌面生命周期 | `apps/desktop/src-tauri/src/lib.rs`、`supervisor.rs`、`llm_config.rs`、`credentials.rs`；`bootstrap/cli.py`、`infrastructure/database.py`。 |

上表 Python 路径相对 `services/core/src/livingworld/`。API 模块在 `adapters/http/`；WorldTime 为逻辑 epoch 整数微秒、UTC 为现实时间，不能隐式互换或经过浮点微秒。

重要增量：0023 资料任务、0024 摘要、0025 日常、0026 地点目录、0027 离线、0028 两块事件、0029 长期聊天记忆、0030 封面、0031 人工恢复、0032 参考记录、0033 相遇、0034 共同休闲、0035 主动联系/阅读位置。
历史迁移/事件版本/稳定 ID 保持；旧结构 shape 检查不放松。0032 的追加列顺序必须与 ORM 一致，不能重复引入已修复启动问题。
不要用旧包打开已升级存档；不要把代码核对称为真实存档升级验证。

## 6. 交付与证据

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

最新完整包（本轮核对 EXE 存在与 ProductVersion 0.1.28）：

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

此次已读红点修复后，应沿 [状态清单第六节](docs/PROJECT_STATUS.md#六真正的下一步与完成判据) 继续：

1. 红点不清已获用户反馈解决。0.1.31 补足离线恢复因未回复/并发联系跳过时的状态提示；下一步聚焦仍未获证实的主动联系闭环：实际共同休闲的两位角色是否只为同一件事邀请、未回复时是否阻止后续跨角色联系、回复后下一合法机会能否再次联系，以及离线恢复的提示与行为是否一致。不要为验证而代用户触发付费模型或读取真实存档。
2. 最新待用户验收是经历终态/身份隔离、共同休闲真实生命周期、来源前后文；参考 [0.1.28 说明](docs/EXPERIENCE_STATE_RECALL.md)、[0.1.27 说明](docs/SHARED_LEISURE.md)。不替用户执行测试。
3. 更大产品愿景与明确实现限制单独列，不自动排入下一轮；没有缺口证据不泛泛安排“优化记忆”。
4. 最终发行仍待用户验收和明确批准，不自行 push/Release；日常本地保存与公开发布分开。

本轮依据用户对红点修复的明确反馈，继续收敛主动联系与离线恢复；当前没有需要用户决定的新产品方案。0.1.30 的红点现象已获用户验收，0.1.31 离线跳过状态的运行效果尚未验收。
关键维护建议：后续直接更新当前状态行/现场，不再往根交接叠加多份“最新接续”；完整历史通过 Git/归档追溯。

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
