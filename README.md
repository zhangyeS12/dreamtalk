# LivingWorld

All engineering agents must read AGENTS.md before modifying the repository.

## 项目定位

LivingWorld 是持久化、事件驱动的多角色 AI 世界，不是普通聊天机器人。Director 负责世界与宏观剧情调度，Character Agent 主要负责自己拥有的记忆、人格表达和与玩家对话；世界真实事实、角色知识和玩家知识相互分离。

## 开发状态

当前阶段：**Stage 6 — Memory & Cognition，C-007A Episodic Memory Foundation 已完成**。系统支持 Character 从自身已授权 Observation 显式形成不可变、evidence-backed 的主观 EpisodicMemory，并提供 owner-bound SQL 读取、稳定分页、原子幂等写入和 Alembic 0014 persistence。Observation 不自动创建 Memory；Memory 不授予 Truth、Knowledge 或 Belief，也不进入 authored content package 或 projection replay。详见 [Episodic Memory](docs/architecture/EPISODIC_MEMORY.md) 与 [Memory Model](docs/architecture/MEMORY_MODEL.md)。

Q-001B 提供仅开发环境启用的 [开发者运行时检查器](docs/architecture/RUNTIME_INSPECTOR.md)，用于通过真实 API/application 路径观察时钟、位置、Scene、trigger、activation、WorldEvent、Observation 与 owner-scoped EpisodicMemory。它不是最终产品 UI，也没有加入 Activation consumer 或自动 Observation→Memory。

普通用户入口已建立“聊天 / 通讯录 / 设置 / 我”四标签基础，支持创建与切换世界、暂停/恢复及时间倍率设置、在每个世界绑定 Player；未绑定的新世界可通过 canonical 命令从“家”创建本地玩家并进入。支持通用与世界专属个人资料保存，以及置顶的玩家已知“世界事件”时间线。事件查询先按绑定 Player 的 Observation 授权，再读取安全展示信息。设置支持导入、预览确认和独立更新当前世界的角色卡与世界书；通讯录只显示当前世界已确认的角色资料。首次打开角色会建立世界隔离的持久私聊会话；聊天页可读取该 Player 有权查看的消息记录。当前世界可创建多角色群聊，群聊消息和角色回复使用独立的一次性回合认领与共享 Token 上限；@角色名 指定下一位发言者，其他情况由独立调度器按已确认人格和群聊记录选人。内部服务和受认证 API 可幂等保存玩家消息与待处理回合；模型执行层已有逐次调用的保守 Token 预留，角色回复已具备内部一次性领取、受控模型生成与幂等提交边界，并已接入正式运行时与页面私聊发送入口；仅当配置了单一可用模型或明确的聊天路由、可信 Token 上限及会话凭证时才能发送。详见 [产品界面与知情边界](docs/architecture/PRODUCT_SURFACE.md) 与 [聊天模型](docs/architecture/CHAT_MODEL.md)。开发者检查器通过 URL 查询参数 `?developer=1` 进入。

Stage 5 — World Kernel & Simulation Runtime 已完成并冻结。C-006D 的 clock reconciliation、C-006C sparse activation/coalescing 与 C-006B deterministic Action/Scene/event-time perception 继续作为 Stage 6 substrate。详见 [Stage 5 验收](docs/architecture/STAGE5_ACCEPTANCE.md)、[Clock Reconciliation](docs/architecture/CLOCK_RECONCILIATION.md)、[Sparse Activation](docs/architecture/SPARSE_ACTIVATION.md)、[Action Resolution](docs/architecture/ACTION_RESOLUTION.md) 和 [Scenes and Perception](docs/architecture/SCENES_AND_PERCEPTION.md)。

Stage 4 — LLM Infrastructure 已完成并冻结。C-005E5 将四种 provider adapter、ModelRegistry、purpose routing、retry、accounting/pricing、Budget Guard 和 session credentials 接入单一生产 composition root。桌面 API key 由 OS credential facilities 持久化；Python Core 只接收内存 session credential。非秘密配置使用严格 version 1 JSON，启动不会发现模型、验证 key 或发起生成。全部验收保持离线，没有真实付费 API；可选 live smoke 必须显式 opt-in。详见 [生产组装](docs/architecture/LLM_PRODUCTION_COMPOSITION.md)、[Stage 4 验收](docs/architecture/STAGE4_ACCEPTANCE.md)、[OpenAI Responses adapter](docs/architecture/OPENAI_RESPONSES_ADAPTER.md)、[Gemini Interactions adapter](docs/architecture/GEMINI_INTERACTIONS_ADAPTER.md)、[Anthropic Messages adapter](docs/architecture/ANTHROPIC_MESSAGES_ADAPTER.md)、[LLM routing](docs/architecture/LLM_ROUTING.md)、[Budget Guard](docs/architecture/LLM_BUDGET_GUARD.md)、[LLM accounting](docs/architecture/LLM_ACCOUNTING.md)、[执行策略](docs/architecture/LLM_EXECUTION_POLICY.md)、[基础契约](docs/architecture/LLM_INFRASTRUCTURE.md)、[结构化生成](docs/architecture/STRUCTURED_GENERATION.md) 和 [真实文本流](docs/architecture/LLM_STREAMING.md)。

Stage 3 已完成 canonical authored-content、Character Card/Lorebook 离线导入、Draft/Preview/confirmed Commit、外部 JSON 导出和 `.lwcontent` 原生内容包。原生包支持显式 roots 的依赖闭包、shared references、完整来源、本地 SHA-256 资产、六种三方冲突与事务化 accepted baseline。详见 [Stage 3 验收](docs/architecture/STAGE_3_ACCEPTANCE.md)、[原生内容包](docs/architecture/NATIVE_CONTENT_PACKAGE.md)、[内容模型](docs/architecture/CONTENT_MODEL.md)、[导入](docs/architecture/IMPORT_MODEL.md)、[导出](docs/architecture/EXPORT_MODEL.md) 和 [持久化](docs/architecture/PERSISTENCE_MODEL.md)。

`.lwcontent` = authored content package；`.lworld` 保留给未来 runtime-world/state package。content package != backup != running world；hash integrity != publisher authentication；filesystem blobs + SQLite 不被宣称为一个 ACID transaction。导入/导出不创建 Runtime World/Character，不断言 Truth 或授予 Belief/PlayerKnowledge。作者文本/regex/activation metadata 保持不可信数据，不执行。

运行内容实例化、automatic Lore→Truth/Belief、基于角色知识与记忆的完整 prompt assembly、Reflection、memory consolidation/forgetting/semantic retrieval/RAG、Director、Character Agent、AI Builder、activation consumption、checkpoint/branch、`.lworld`、cloud sync、marketplace 和 final UI 尚未实现。Stage 5 catch-up 只 materialize 到期 work，不编造离线叙事或角色决定；fidelity 只表示 operational context，不是剧情重要性、WorldTruth 或 LLM 策略。Scene 只是互动上下文，Observation 只记录历史访问；形成 EpisodicMemory 必须走 C-007A 的显式 owner-authorized command。外部 PNG/APNG writer、CHARX、任意图复制、签名与 orphan blob GC 仍 deferred。Stage 2 的资源级 CAS、幂等、ledger/rebuild 和知识隔离继续沿用，见 [Stage 2 验收](docs/architecture/STAGE_2_ACCEPTANCE.md)。provider tools、LLM settings UI 和真实付费 API 验证尚未实现。

C-002 运行时基础继续沿用：共享 React UI、Tauri v2 Windows 开发壳、Python Core 启停协议、系统 API、SQLite 迁移元数据、结构化日志和 CI。连接阶段显示“正在连接核心 / 核心已就绪 / 核心连接失败”；就绪后默认进入普通用户四标签页面。

Director、Character Agent、认知消费、自动知识传播、语义检索及最终 UI 尚未实现。当前生产 action registry 只有 `move_player` v1；Scene lifecycle 是内部应用操作。生产 snapshot store 只读，正式世界变更通过 Kernel/UoW 管线执行；投影恢复另用内部 ProjectionRebuilder。P-01 的时间推进/离线/暂停部分已由 C-006D 解决；其余待确认问题见 [PRODUCT_SPEC.md](docs/product/PRODUCT_SPEC.md)。Stage 0 审查见 [ARCHITECTURE_REVIEW_001.md](docs/architecture/ARCHITECTURE_REVIEW_001.md)，运行时边界见 [RUNTIME_FOUNDATION.md](docs/architecture/RUNTIME_FOUNDATION.md)。

## 开发环境与运行

在仓库根目录执行。需要 Python 3.12+、uv、Node 24、Rust 1.88+（本机使用 stable 1.95）；Windows Tauri 还需要 MSVC C++ Build Tools 和 WebView2。

```powershell
uv sync --frozen
npm ci

# Windows desktop：Rust 启动 Core，复用 React UI
npm run dev:desktop

# Browser：开发 launcher 启动 Core + loopback Vite，按 Ctrl+C 关闭
npm run dev:web

# Core alone：开发 launcher 生成 bootstrap；输出 endpoint，不输出 bearer
npm run dev:core
```

直接使用 bootstrap 启动 Core：`uv run livingworld-core --desktop --bootstrap-path <absolute-path> --parent-pid <pid>`。bootstrap 必须由调用方创建，详见 [运行时协议](docs/architecture/RUNTIME_FOUNDATION.md)。

## 检查与开发产物

```powershell
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest
npm run lint
npm test
npm run build:web
# Real browser lifecycle (Windows uses installed Edge; Linux needs playwright install chromium)
npm run test:web-smoke
npm run build:core
uv run python scripts/check-wheel.py
uv run python scripts/check-doc-links.py

# Windows integration
npm run test:desktop
npm run build:desktop
npm run test:desktop-smoke

# Optional real provider smoke: disabled unless --enable-live-provider is added.
# External API usage may incur cost; this is never run by CI/pytest.
npm run test:llm-live -- --config <path> --data-dir <path> --provider <id> --model <id> --credential-env <ENV_NAME>
```

`build:core` 生成 `artifacts/core/*.whl`；`build:desktop` 生成未签名、未打包的 Windows debug executable。该桌面开发产物依赖当前 checkout 的 `.venv`，尚不是独立安装包。

开发数据库与日志保存在 app data。桌面使用 Tauri 的 `app_data_dir`；独立 Core / browser 开发 launcher 使用 `%LOCALAPPDATA%/LivingWorld/development`。安装和源码目录不保存运行数据库或 bootstrap credentials。

GitHub Actions 配置包含 Python lint/test/wheel、TypeScript lint/test/Web build、真实 browser smoke 和 Windows supervisor/WebView smoke。远程 CI 结果以实际运行记录为准。
