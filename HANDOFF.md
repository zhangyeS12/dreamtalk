# dreamtalk 工作交接

更新日期：2026-09-28。此文件记录当前开发现场与接续工作，不替代 [AGENTS.md](AGENTS.md)。先读 AGENTS，再读本文，最后核对实际 Git 状态和相关代码；不能把下面的基线哈希当作永远不变的当前 HEAD。

## 最新接续：2026-09-28 聊天状态反馈

- 用户已授权自行选择技术方案并继续开发；每个新功能实现前先调查成熟项目，记录具体复用决定。规则已写入 AGENTS.md。
- 正式工作目录为 `D:\LivingWorld`，本地分支 `codex/chat-feedback`；不再使用旧工作克隆。开始接续时仍须核对实际 Git 状态。
- API client 接通现有 FastAPI `detail` 的有界机器标签；私聊/群聊区分保存、等待回复和检查状态，提供中文的模型、预算、校验、生成、账本异常提示。
- “检查回复状态”读取当前会话最近玩家消息的已有 GET，重新打开会话后仍可操作；不重放模型。群聊生成等待期间串行读取有界消息页，每次读取结束后间隔两秒，让已经保存的发言陆续出现；连续两次读取失败后暂停，手动刷新可恢复；离开会话或请求结束后停止读取。
- 尚未接通 Token 流式输出，尚未持久记录群轮停止原因；`completed` 只表示本轮终结，不能推断是自然停止。未增加依赖、数据库迁移或测试；未运行运行时/提供商验收。
- 本轮验证：`npm run lint`（ESLint + TypeScript）和 `git diff --check` 通过；`uv run --frozen --group packaging python scripts/build-portable.py --build-only` 成功生成前端、Rust 发布版与冻结 Core。没有运行测试、便携包 smoke 或提供商调用；实际效果由用户带自己的 API 验收。
- 最新便携包：`D:\LivingWorld\artifacts\portable\dreamtalk.zip`，27,814,276 bytes，2026-09-28 06:55:33 UTC；SHA256 `59B1076CDBFF2D6AEEA0AAF020E464B1604E3BDF4094D16A08A34002F3C103E3`。解压后运行 `dreamtalk\dreamtalk-desktop.exe`。此产物信息覆盖下方历史产物哈希。
- PyInstaller 分析仍产生平台分支、可选依赖及属性符号等 missing-module 警告，未出现以 `livingworld` 命名的缺失模块项。原始记录：`artifacts/pyinstaller-build/dreamtalk-core/warn-dreamtalk-core.txt`。构建成功不能替代运行验收，不宣称运行无警告。
- 复用调查和边界见 [本轮决定](docs/research/2026-09-28-chat-feedback-reuse.md)。下方“本轮仅文档交接”及基线描述保留为上次交接的历史记录，以此最新接续和实际代码为准。

## 1. 当前目标与上下文

用户要求先把核心聊天体验、导入、世界隔离和设置的真实效果完善到可亲自验收，然后会带自己的 API、角色卡、世界书试用。项目还没有最终验收，不应宣布完工。当前优先级是可用的沉浸聊天，而不是继续堆架构或准备 GitHub 发布。

最近讨论集中在两点：

- 世界书如何真正参与聊天，同时排除默认隐藏的暗线；群聊中所有参与角色应能参考已经发出的消息。
- 不重复造轮子。已取消“必须独立实现”的限制，允许评估成熟项目/组件；现有适配器没有因此被删除，也没有引入 SillyTavern 运行依赖。

本轮是**文档交接任务**，只更新 AGENTS.md 并创建 HANDOFF.md，没有修改业务代码。完成后新对话应继续产品开发，不再向用户索取已明确的四标签布局、群聊 Token 规则或世界隔离要求。

## 2. 仓库与代码基线

本轮写入前已实际检查两处 Git 仓库，它们均为 `master`，工作树和暂存区干净，HEAD 一致：

```text
1e7843cd71f557a0db2b5a4ecfa01bb9ccaaf17d
feat: prioritize relevant public lore in chat context
```

这是本次交接的**业务代码基线**；本轮后续文档提交不改变业务实现。

| 位置 | 本轮实际用途 |
| --- | --- |
| `D:\LivingWorld` | 用户的正式交付仓库；本轮检查时没有配置 Git remote，未连接 GitHub。 |
| `C:\Users\zhang\.codex\visualizations\2026\09\15\01a0a4e1-d243-7fc2-86dc-5a29a37df3ce\livingworld-work` | 本次受限环境允许写入的工作克隆；`origin` 指向 `D:\LivingWorld`。不是云端仓库。 |

若新对话可直接写 D 盘，优先在那里工作。若权限仍限制 D 盘写入，沿用工作克隆，先核对两边状态/哈希，在工作克隆提交后通过明确路径的 `git pull --ff-only` 同步 D 盘；不要覆盖 D 盘的新修改、强推或重写历史。构建产物属于 ignored 文件，Git 同步不会自动复制它们。

开始接续时执行：

```powershell
Set-Location D:\LivingWorld
git status --short
git log --oneline -8
git diff --stat
git diff --cached --stat
```

检查是否有另一任务正在修改相同文件，不把用户/其他任务的修改混入自己的提交。不要根据本文件推测活动进程已经退出；本轮没有启动或关闭应用。

## 3. 已完成到什么程度

以下“已实现”依据本轮源码读取，**不等于本轮实际运行或用户验收通过**。

| 能力 | 实际实现与当前界限 |
| --- | --- |
| 运行底座 | React/TypeScript/Vite、Tauri v2 Windows 壳、Python/FastAPI Core、随机 loopback 端口、认证发现与启停、SQLite/Alembic、日志、既有 CI 均存在。 |
| 普通界面 | PC 宽度的中文聊天 / 通讯录 / 设置 / 我；创建切换世界、暂停恢复、倍率、可用/忙碌、个人资料、当前世界导入和已知事件入口已接入 API。 |
| 身份与内容 | 每世界绑定本地 Player；默认从“家”进入；角色卡/世界书预览确认与独立更新；当前世界通讯录；首次打开聊天才创建/复用运行时 Character。 |
| 私聊 | 持久 Conversation、Player Message、turn、一次性 dispatch claim、角色生成与受控持久回复；页面发送、读取和错误提示已接线。 |
| 群聊 | 选择两个或以上角色建群；固定成员、共享持久记录、独立选人器、`@` 首位指定、逐条角色回复、整轮共享 Token 上限、完成标记。不是永久自主角色聊天。 |
| 聊天阅读 | `react-markdown` 安全渲染、回车发送/Shift+回车换行及输入法保护、自动滚动/历史位置处理、最近消息分页和“加载更早消息”。 |
| 世界书背景 | 世界书条目默认隐藏；当前世界逐条设为公共后，可进入角色回复上下文。最近加入有限的关键词相关性排序，详见第 5 节。 |
| 群聊知情 | 群成员即使没发言，也能在之后的私聊/其他群聊上下文读取自身参与群的有界消息窗口。不是自动 Knowledge/Truth/Memory 写入。 |
| 角色记忆 | C-007A 的 owner-scoped、Observation 证据支持的 EpisodicMemory 已存在，私聊/群聊回复读取本角色的有界记忆；尚未实现长期整理、检索或自动聊天记忆形成。 |
| LLM 底座 | OpenAI-compatible Chat、OpenAI Responses、Anthropic Messages、Gemini Interactions 四种 adapter；非流式/流式基础契约、structured validation、retry、routing、usage/pricing、financial budget、session credentials 已有。 |
| 内容兼容 | Character Card V2/V3、PNG/JSON 读取，Lorebook 标准化，原始兼容数据保留，外部 JSON 导出和 `.lwcontent` authored-content package 已有。并非完整酒馆兼容。 |
| 世界运行底座 | 确定性命令、行动、Scene、事件、Observation、tickless scheduler、sparse activation、clock reconciliation/catch-up、账本/回放和 CAS 已有；正式行动 registry 目前只有 `move_player` v1。 |
| 开发者工具 | `?developer=1` 可选择 Inspector 页面；相关 Core 开发 API 仍需显式 developer mode。它不是普通界面或自动 Activation consumer。 |
| 本地交付 | 已有随附冻结 Python Core 的 Windows 便携目录与 ZIP；无需使用者安装开发语言。没有签名安装包、自动更新或 GitHub 发布。 |

**明确未完成：** 完整自主 Character Agent、Director 批量计划/Event Reservoir 的生产执行与主动剧情、Activation consumer、自动知识传播、长期记忆整理/语义检索、AI Research Builder、Checkpoint/Timeline Branch 产品能力、`.lworld` 运行世界包、cloud sync/marketplace、完整模型管理、普通聊天页的流式输出，以及完整酒馆世界书激活行为。不要因为 docs 说 Stage 2–5 已冻结，就推断这些产品功能也已完成。

## 4. 本轮与紧邻前序工作的文件变化

### 本轮只改两份文档

| 文件 | 修改 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 同步最新优先级、自主推进/局部跳过、用户负责测试、三段式汇报、成熟组件复用、PC 聊天规则及验收前不发布；删除旧的“一切不确定立即停”与强制逐任务停止/自动测试冲突规则。 |
| [HANDOFF.md](HANDOFF.md) | 当前现场、入口、限制、近期改动、构建证据、继续顺序与易误解处。 |

没有业务、数据库迁移、测试或构建脚本变更。本轮没有重建便携版。

### 前序已提交的最近切片

下面来自实际 `git show`，不是本轮未提交工作：

| 提交 | 文件与用途 |
| --- | --- |
| `1e7843c` | `application/chat_context.py`：公共 lore 相关性排序，私聊传入本轮玩家文本；`application/group_chat_context.py`：群聊角色回复复用该排序；`docs/architecture/CHAT_MODEL.md`：记录真实范围和限制。 |
| `309719c` | `apps/web/src/GroupChat.tsx`：点击唯一命名群成员插入 `@名字`，保留光标位置并检查输入长度；`apps/web/src/product.css`：简洁样式；`CHAT_MODEL.md`：记录交互。不改服务端选人语义。 |
| `1b57f6b` | `AGENTS.md` 及 `docs/architecture/ADR/0001_reuse_mature_projects.md`：允许评估成熟组件；ADR 索引及 `ARCHITECTURE_REVIEW_001.md`：保留历史、标注被替代的独立实现限制。 |
| `7009288` | `scripts/build-portable.py` 和 `README.md`：加入 `--build-only`，允许构建而不隐式运行 smoke。默认脚本仍含自检。 |
| `6bfbb06` | HTTP CORS 修正为允许 `PUT`，否则桌面公共世界书开关的预检请求会失败。不要退回只有 GET/POST 的配置。 |

更早的 `64b6413` 已建立公共 lore 与群消息可见性；`5980f92`、`d7ca0b8` 已建立有界上下文读取/消息分页。继续前用 Git 查看需要修改的具体文件，不重新实现这些切片。

## 5. 接续工作需要知道的实际实现

### 5.1 从前端到 Core

```text
apps/web/src/main.tsx → App.tsx
  → connection.ts / CoreClient
  → ProductApp.tsx
    → WorldContent.tsx / ProfileEditor.tsx / ModelSetup.tsx
    → ChatTranscript.tsx / GroupChat.tsx
  → adapters/http/{worlds,profiles,world_content,player_events,chat_conversations,chat_messages}.py
  → application services
  → infrastructure/persistence adapters
```

- 桌面连接通过 Tauri `core_connection` 返回 endpoint/token/generation，浏览器开发连接通过 `virtual:core-connection`；UI 不硬编码 Core 端口。
- `App.tsx` health 成功后调用 `report_ui_ready`。Tauri 主窗口初始隐藏，不能把 Core ready 与 UI ready 混为一谈。
- API 协议从 `domain/api_contract.json` 集中读取，目前 `api_protocol = 1`。Tauri 的 dev UI 端口 1420 不是 Core 端口。
- `ProductApp.tsx` 默认整轮额度为 50,000，可设置 1–1,000,000；沿用 `livingworld.chat.turnTokenCeiling` 和 `livingworld.lastWorldId` localStorage 键。
- 模型配置 UI 在 `ModelSetup.tsx`；Rust IPC/config/credential 操作在 `src-tauri/src/lib.rs`、`llm_config.rs`、`credentials.rs`、`supervisor.rs`，不存在独立 `model_setup.rs`。

### 5.2 消息、claim 与角色生成

```text
打开联系人 → ChatConversationService → 世界内稳定 Character/Conversation
保存玩家消息 → ChatMessageService → SqlAlchemyChatMessageStore → pending turn
请求回复 → DirectChatReplyService / GroupChatReplyService
  → 上下文与 route/token preflight
  → 持久一次性 claim
  → governed gateway.generate(..., turn_budget=同一对象)
  → 校验 → durable reply / group completion
```

- HTTP 前缀为 `/api/v1/worlds/{world_id}/conversations`，需 bearer；发送还需 `X-Request-Id`。
- 私聊保存：`POST /{conversation_id}/messages`；群聊保存：`POST /{conversation_id}/group-messages`。二者返回 202 pending，不等于模型已经发言。
- 生成分别使用 `POST /{conversation_id}/turns/{turn_id}/reply` 和 `/group-turns/{turn_id}/reply`；对应 GET 可读 pending/claimed/completed。已完成结果读取不再次付费生成。
- UI 使用 `GET /{conversation_id}/messages/page`，默认 50、最大 100，游标 `before_position`；旧的完整消息读接口仍保留，不能让普通页面退回每次读全部历史。
- claim **不可重新领取**。模型失败、HTTP timeout 或重启后的 claimed turn 不自动 replay。UI 可查询一次状态，不自动再次生成。部分群回复已经持久提交时保留它们。
- 私聊及角色群回复只接受匹配 invocation 的非空、有界文本，finish 为 STOP 或 REFUSAL；截断不是成功回复。群选择器只接受合法成员 ID，已有回复后可返回 STOP。
- 群回复当前另外有 32 条安全上限；选择请求输出上限为 64 Token。`@` 只绕过首次选人调用，不禁止本轮随后选择其他人。
- 当前回复服务用 **`generate()`**，不是 `stream()`。基础 SSE adapters 已有，不代表 UI 已逐字流式显示。接通流式时不能破坏一次性 claim、终端校验、账本和未知用量处理。

### 5.3 聊天上下文

直接入口为 `application/chat_context.py::DirectChatContextBuilder`；群入口为 `group_chat_context.py::GroupChatContextBuilder`，共享公共背景、记忆及历史窗口工具。

- 角色人格从当前世界 accepted import replacement lineage 解析；更新卡片不换 runtime Character 或丢失聊天。
- 本地通用/世界资料都提供给角色，system 明确世界专属描述优先。没有自动语义冲突合并器。
- `private_chat_memories` 当前最多 12 条、内容累计 8 KiB；按 Character owner 读取，不是 RAG。
- prompt transcript 按完整 turn 截取，最多 32 条消息/96 KiB，不裁掉当前 turn；持久层有有界读取，不为 prompt 加载全部历史。
- 本角色曾参与的群消息读取默认最多 32 条，再受 8 KiB 内容预算约束；另一个群回复时排除当前群以避免重复输入。群选人器不拿任何角色私有记忆。
- 角色卡 `first_mes` 仅作有界语气示例（8 KiB），不是自动发出的开场消息。
- 导入文本、背景、个人资料、消息都是 lower-trust data。世界书/角色卡中的作者指令不是新增 privileged system instruction。

### 5.4 公共世界书当前是“有界排序”，不是完整激活引擎

- `SqlAlchemyWorldContentStore.list_common_lore` 只查指定世界、当前 accepted 版本、明确公开的条目；disabled 条目不会用于聊天。
- `common_chat_lore(..., relevance_text=本轮玩家消息)` 取消息末 4096 个字符并 casefold，以 primary keywords 的字面子串命中排序。
- 命中条目优先；随后按 priority 降序、order 升序、稳定 ID 排序。最多 16 条，title/content 累计 12 KiB；超预算条目跳过。
- **未命中但已公开的条目仍可能填入剩余额度。** 这不是“未命中不激活”；不要在后续说明中把它说成完整 ST World Info 触发。
- 尚未执行 regex、secondary-key 条件、历史深度扫描、递归、概率、sticky/cooldown 等行为。导入保存这些元数据不等于聊天引擎消费了它们。
- 当前公共标记按 `(world_id, import_id, entry_id)` 保存。替换导入后读新版本，旧公共标记不会自动授予新版本权限；设置需要对当前版本显式开放。不要为了便利自动把隐藏条目公开。

### 5.5 Token、预算和模型配置

- `ChatTurnTokenBudget` 是本轮串行使用的内存预留对象；玩家 Message/turn 保存原始额度、claim 防止重启重新开始。同一群轮中的选人和回复共享一个对象，并传入底层物理 retry/fallback。
- 必须有 `HARD_UPPER_BOUND`。当前按配置的整个模型输入上界保守预留，不是按短 prompt 猜输入长度；额度小于可信输入上界时，即使一句话也可能不能发。
- usage 不完整时保守消耗预留并关闭本轮；超过上界时报告完整性问题，不把事实用量改小。
- `bootstrap/llm_runtime.py::_chat_reply_configuration` 只选唯一合格模型或显式 `character_dialogue` 的 BALANCED route；多模型无路由时不猜。每个候选都需可信 limits；可用性还依 route policy 检查 session credential。
- 桌面简化模型设置面向 managed single configuration，可创建/更新并通过 supervisor 重启 Core；不会在保存配置时测试 key 或生成回复。高级配置不能被简化表单默默覆盖。
- 四种 adapter 的“有实现”不保证任意代理地址/模型都兼容。浏览器没有桌面的 OS credential IPC，不能把桌面设置能力宣传成浏览器完全相同。
- 已有 financial Budget Guard/usage ledger 和聊天 Token 上限是两种不同约束。预算按 requested ModelRef 归属，reported model 可用于实际定价。不要改成 requested OR reported budget matching。
- 账本 START 失败不得调用模型；模型执行后 FINALIZE 失败不能重放模型、不能伪造零费用，持久 START 保持 INCOMPLETE。routing 已有 invocation 级共享 monotonic deadline，fallback 不重置。

### 5.6 Canonical state、记忆与迁移

- `WorldTime` 是逻辑 epoch 的整数微秒；真实时间用 UTC-aware datetime。两者不可隐式互换。前端显示用 BigInt/字符串，不经过浮点微秒。
- Alembic 是唯一迁移 authority，当前源码 head 为 `0022_world_common_lore`。legacy `schema_version`/`migration_history` 是兼容审计，不是另一套 runner；ambiguous legacy 状态 fail closed。
- `0017` 世界快照、`0018` conversations、`0019` messages、`0020` dispatch、`0021` group completion、`0022` common lore 已存在。不要重新创建同名机制或凭旧 Stage 文档猜 schema head。
- 普通移动唯一入口为 `ActionResolutionService`；兼容 `MovePlayer` 适配进去。初始化放置与玩家行动不是同一语义。
- CreateWorld commit 后经 lifecycle port 注册 WorldSimulationRuntime；运行时失败标 degraded，不把已提交世界谎称 rolled back。
- `RecordEpisodicMemory` 要求真实、同世界且该 Character 获准的 Observation 证据。普通聊天目前不生成这些证据，不自动写 EpisodicMemory。不能为实现“独立记忆”伪造 Observation 或自动把消息断言为事实。
- Player 的置顶事件 feed 先按绑定 Player 的 event Observation 授权；安全标题能力有限。无已知事件时为空，禁止用假剧情填补。

## 6. 已确认决策与理由：避免重新询问

长期约束见 AGENTS；这里记录接续实现时最易误判的决定：

| 决策 | 原因/实现影响 |
| --- | --- |
| 世界专属内容是确认快照 | 同卡/同书在多个世界使用不能串改；替换沿 lineage 保留身份与历史。 |
| 首次开聊才建 Character | 导入只是创作内容；通讯录先可见，不触发后台角色或付费活动。 |
| 群聊独立选人 | Director 的 batch-planner contract 不能被逐句选人调用改变；`@` 确定首位。 |
| 输入+输出整轮硬上限，可信保守预留 | 防止多角色、选人、retry/fallback 累计爆量；用户接受宁可提前停。 |
| 公共背景可共知，暗线默认禁止 | 导入不等于授予角色所有知识；关键词 relevance 排在权限过滤之后。 |
| 所有固定群成员看到消息 | 沉默成员不会因没回复就遗漏群消息；消息内容仍可能是假话。 |
| 台词直接发送，持久创作预览确认 | 避免聊天逐条确认，保留 authored content 的审查边界。 |
| 不再要求独立实现 | 优先效果和维护成本；[ADR-0001](docs/architecture/ADR/0001_reuse_mature_projects.md) 已替代旧 review 的该限制，未更改 Apache-2.0。 |

## 7. 不应重复的路径与历史问题

- 不能把 `cargo test` 留下的桌面 executable 当作正式 custom-protocol 产物。历史曾出现 Core/supervisor ready 但无 ui_ready；正确正式命令在第 10 节。本轮没有再次 smoke，也不声称历史原因已再次验证。
- 不反复启动窗口/点击/第三次无新证据重试同一失败。保留 artifact 路径、修改时间、安全 stdout/stderr 与实际等待条件后再判断。
- `uv` 默认 cache 访问曾在本受限会话被拒绝，最近打包改用已有 `.venv\Scripts\python.exe` 调用同一脚本。不要把 cache 权限问题误判为项目代码坏了或循环重装依赖。
- 默认 `build:portable` 含 standalone smoke 和 Rust supervisor test；“只打包”需 `--build-only`，不要绕过用户负责测试的决定。
- 不沿用 legacy MovePlayer 独立写 PlayerMoved，不添加自动 Activation→action 或 Observation→Memory 来拼演示链路。[CODEBASE_AUDIT.md](docs/architecture/CODEBASE_AUDIT.md) 的 Q-001A disposition 已记录原因和修复。
- 对未知/缺少模型 bounds、含糊的 `@`、未知 provider usage，不能用“看起来够用”放行。
- 不把原始 ST world-info regex、脚本、私有字段直接执行，不把 raw compatibility 数据当 privileged prompt，也不为“完全兼容”破坏 canonical invariant。
- 不直接粘贴需要不同许可义务的代码后仍宣称全部 Apache-2.0；目前实际复用的是公开行为/规范及适合的既有依赖，如 `react-markdown`，不是一个已嵌入的 ST runtime。

## 8. 尚未完成、风险与技术债

### 用户体验缺口

1. **长期独立记忆尚不完整。** 有 owner-scoped EpisodicMemory 和有界历史，但普通聊天未形成长期证据记忆；长对话后较早内容不会全部进入 prompt。别将持久 Message 与完整记忆系统混为一谈。
2. **世界书与酒馆能力仍有差距。** 当前公开背景排序不是完整条件激活/注入位置引擎；隐藏背景没有角色专属授权传播路径。不能宣称已实现 ST 的所有功能。
3. **Director 和主动事件尚未生产接通。** 现有世界时间、scheduler 和事件账本不能自己生成丰富剧情；event feed 当前只有有限安全标题。
4. **聊天仍是整段生成后出现。** 缺少普通界面流式输出；群聊可能有多次选人和生成耗时。
5. **保守 bounds 配置对普通用户仍有门槛。** managed model UI 要手填核实过的上界；不能为了降低门槛随意估值，丰富 Model Registry/安全候选预设仍需推进。
6. **未知结果/claimed turn 缺少完整恢复 UX。** 当前不重放可防重复付费，但用户可能看到已存玩家消息却没回复；完善明确状态说明，不能偷偷清除 claim。
7. **模型设置仅有简化管理。** 多 provider/route 高级管理、tools、真实代理兼容验收、云端/多用户身份不完整。

### 文档和维护风险

- `docs/architecture/PRODUCT_SURFACE.md` 个人资料部分仍有旧阶段“未实现 prompt assembly”句子；现在 `chat_context.py`/`group_chat_context.py` 已组装资料。后续可局部修正文档，别因此再写一套上下文。
- `CHAT_MODEL.md` 的少量早期段落仍写“API opens/lists only”，后文已描述 send/reply。以真实 endpoint、当前服务和后续段落为准。
- `CODEBASE_AUDIT.md` 保留旧 A-001～A-005 的 FIX_NOW 文字供审计历史，顶部 disposition 已解决；Q-001B Inspector 已在代码中，不应重新宣告阻塞。DEFER 中的大 command handler、广 UoW、schema compatibility matrix、provider pipelines、全 ledger replay、large ORM/supervisor 等债务仍不能说已全消除。
- 便携版未签名/无自动更新；本机历史 `livingworld_core` wheel 文件比最近业务代码旧，不能当最新 dreamtalk wheel 分发。
- 本轮未确认新的可复现业务 bug；“尚未运行验证”不是“已知无 bug”。旧 Python 应用错误弹窗的本机原因没有本轮证据，不应编造已修好或已复现的结论。

需要用户判断但**尚未在当前切片解决**的边界，应在有具体设计时汇总：新 chat-memory evidence/形成路径、隐藏设定如何授权到特定角色、World Plan/event narration 的详细产品语义。先推进其他确定工作，不重新询问第 6 节已确认项。

## 9. 验证与现存产物

### 本轮实际完成的核对

- Git status/log/diff/cached diff；D 盘与工作克隆业务基线一致且写入前 clean。
- 阅读主要 UI、API、chat/context/reply/budget、bootstrap、public lore persistence/migration、memory、Tauri 配置/入口和构建脚本。
- 核对现存 ZIP 的 SHA-256、exe 修改时间及开发依赖目录存在。
- 本轮仅文档编辑，不跑 Python/前端/Rust 测试、smoke、付费 API，不启动应用，不重新构建。文档写入后的 `git diff --check` 无问题；链接脚本检查 535 个本地目标，0 broken（111 个外部 URL 仅计数，未在线验证）。

前序对话曾报告最近的 Web build 与 `build-portable.py --build-only` 成功；本轮重新确认了产物存在，但未复跑构建、未取得本轮运行验收证据。不要引用旧测试数量作为当前代码全部通过的证明，也不要把“配置可保存”当作“API 真实调用成功”。

现存可供用户试用的文件（2026-09-28 核对）：

```text
D:\LivingWorld\artifacts\portable\dreamtalk.zip
D:\LivingWorld\artifacts\portable\dreamtalk\dreamtalk-desktop.exe
D:\LivingWorld\artifacts\portable\dreamtalk\core\dreamtalk-core.exe

ZIP SHA256:
4B186D95477E26F97DF8652AC5CC3400BC9FC6FB98F5A55ACCA434F7CF5638D8

desktop exe LastWriteTimeUtc: 2026-09-27 15:54:43Z
core exe LastWriteTimeUtc:    2026-09-27 15:54:17Z
```

该 ZIP 没有在本轮确认到一个内嵌源码 commit marker；不能仅由时间戳保证可执行文件与任意后续 HEAD 完全一致。两份文档的本轮更新不需要重打包。运行时需整个解压目录及 WebView2，不能只复制桌面 exe。

用户尚需自行验收：自己的 provider/key/model 的实际聊天，角色卡/世界书导入与公共开关效果，群聊选人和整轮上限，切换世界隔离，重启后数据，暂停/倍率/availability 和设置更新。没有授权因此自动发送付费验证调用。

## 10. 关键命令与调试入口

开发依赖见 README：Python 3.12+、uv、Node 24+、Rust/MSVC/WebView2。缺依赖才安装；本轮 D 盘 `.venv` 与 `node_modules` 存在。

在实际开发仓库根目录：

```powershell
# 启动选一个，不同时抢占 UI dev 端口
npm run dev:desktop
npm run dev:web
npm run dev:core

# 必要时构建；这些不是用户验收结果
npm run build:web
npm run build:desktop
npm run build:portable -- --build-only

# 若 uv cache 权限仍阻塞，且现有 venv 含 PyInstaller
.\.venv\Scripts\python.exe scripts\build-portable.py --build-only

# 文档/差异静态检查，不是业务测试
.\.venv\Scripts\python.exe scripts\check-doc-links.py
git diff --check
```

`build:desktop` 已在 package.json 中带 `--debug --no-bundle --features custom-protocol`；不要手拼替代命令。portable 脚本依次冻结 Core、正式 release 构建桌面、复制 `core/` 并 ZIP；`--build-only` 跳过生命周期检查。

认证/bootstrap/runtime 入口：`bootstrap/cli.py`、`bootstrap/reader.py`、`application/runtime.py`、`infrastructure/database.py`；Rust `supervisor.rs`；React `connection.ts`。排查 Core→Supervisor→UI 时区分 `core_ready`、`supervisor_ready`、`ui_ready` 和 shutdown，记录实际启动的 artifact，不泄露 bootstrap secret/bearer/API key。

应用数据保存到 Tauri app-data（identifier 仍为 `app.livingworld.desktop`）；独立 Core/browser 开发 launcher 使用历史 `%LOCALAPPDATA%/LivingWorld/development`。不要把数据库放到源码/安装/便携目录，不因改名自行迁移数据。

相关架构阅读顺序：

1. [CHAT_MODEL.md](docs/architecture/CHAT_MODEL.md) 与 [PRODUCT_SPEC.md](docs/product/PRODUCT_SPEC.md) 已确认补充。
2. [PRODUCT_SURFACE.md](docs/architecture/PRODUCT_SURFACE.md)、[PRODUCT.md](PRODUCT.md)、[LLM_PRODUCTION_COMPOSITION.md](docs/architecture/LLM_PRODUCTION_COMPOSITION.md)。
3. 按当前改动选择 [EPISODIC_MEMORY.md](docs/architecture/EPISODIC_MEMORY.md)、[LLM_ROUTING.md](docs/architecture/LLM_ROUTING.md)、[LLM_BUDGET_GUARD.md](docs/architecture/LLM_BUDGET_GUARD.md)、[LLM_ACCOUNTING.md](docs/architecture/LLM_ACCOUNTING.md)、[PERSISTENCE_MODEL.md](docs/architecture/PERSISTENCE_MODEL.md)。
4. 借鉴世界书时查 ADR-0001 中的官方 ST World Info 来源；要引用具体源码/依赖时重新核对项目版本与许可，而不是相信聊天记忆中的“它可以复制”。

## 11. 下一步优先顺序

以下是基于当前缺口的接续建议，不是额外冻结的架构方案：

1. **保持当前聊天链路可理解。** 先核对实际 UI/APIs 的保存、pending/claimed/completed、群部分回复和 Token 停止反馈；修复确定的真实功能缺口，避免再写一个发送/生成/记忆服务。用户测试反馈到来时优先处理复现问题，不替用户运行测试。
2. **继续世界书的实际参与能力。** 对照 ST 的已成型行为与已有 canonical/compatibility fields，列出可安全直接沿用/集成的局部能力；保持先授权再匹配。先明确排序与真正激活的差别，再增加已经明确的有界选择能力。未知 regex/递归/角色专属权限语义留记录，不猜。
3. **改善模型和群聊配置体验。** 在现有 ModelSetup/managed config/registry 上完善说明、route 可用性与预算反馈；避免再建立一套 model identity 或预算引擎。没有可靠 bounds 的候选仍不得放行。
4. **继续角色记忆与聊天的产品连接。** 先梳理已有 Observation-evidence、owner-scoped memory、message exposure 的边界和缺口；需要新增 chat-memory evidence/public contract 时给出具体方案供决定，不悄悄改变 C-007A 的证据要求。其间继续其他确定功能。
5. **接通更自然的消息呈现。** 普通聊天的流式显示可复用已有 stream adapter/contracts，但须先解决终端提交、claim、未知 usage 和取消状态的一致性；不能把半截模型输出假装 durable success。不是简单前端定时打字动画。
6. **之后再补世界话题生产。** Director 在 batch-plan/reservoir 边界内实现，借助已存在 scheduler/Kernel 提交合法事件；群选人器仍独立，hidden facts 不泄漏。不用假事件填聊天列表。
7. **为用户验收提供最新便携产物与实际步骤。** 有业务变更且可编译时用现有 build-only 流程更新；清楚列出未验证处，等待用户自行测试。完整验收通过并获批准后，才处理 GitHub push/release。

## 12. 最容易破坏的地方

- `livingworld` 模块、Tauri identifier、storage keys、协议 derivation 和格式后缀是兼容标识，不能搜索替换成 dreamtalk。
- 公开 lore、群消息可见和角色私有 Memory 是三类输入，不能做一个“全世界上下文”查询绕过授权。
- accepted 卡片、runtime Character、Conversation、WorldTruth 是不同生命周期；不能靠导入就创建所有后台角色/事件。
- Input+output 的 Token ceiling 是**整轮**，不是每人/每次调用；重新建 budget 或重置 fallback deadline 会破坏约束。
- Message 的普通幂等保存与模型的不可重领 claim 是不同保护；“重试保存”不能变成“再次请求模型”。
- `LLMResponse` 是非流式完整结果；`TextDelta` 是流式内容；`LLMStreamCompletion` 只含 terminal accounting metadata，不能把整段文本塞回 completion。
- 长期记忆未完成不代表可以读取别人的记忆补齐；历史消息已持久化也不代表每轮都读全量。
- 旧文档的阶段限制、FIX_NOW 描述、独立实现限制需结合后续确认与当前代码，不把已解除的历史条件重新当作阻塞。
- 没跑测试就写“未测试”，只有 build 就写“构建成功”；不要把可执行文件存在、health ready 或旧测试通过说成用户体验已验收。
