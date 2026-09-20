# LivingWorld

All engineering agents must read AGENTS.md before modifying the repository.

## 项目定位

LivingWorld 是持久化、事件驱动的多角色 AI 世界，不是普通聊天机器人。Director 负责世界与宏观剧情调度，Character Agent 主要负责自己拥有的记忆、人格表达和与玩家对话；世界真实事实、角色知识和玩家知识相互分离。

## 开发状态

当前阶段：**Stage 5 进行中，C-006B deterministic action resolution、Scene 与 event-time perception 已建立**。Core 现在具备类型化 ActionProposal、proposer/actor authority、allowlisted deterministic resolver、MovePlayer 生产 proof action、persistent Scene participation history，以及与 WorldEvent/投影/回执原子提交的 Observation 感知快照。C-006A 的 durable tickless scheduler 继续提供时间与 Activation 基础；Activation 明确不是 ActionProposal 或 WorldEvent。尚未实现 Director、Character Agent、知识/记忆形成、对话、一般世界动作目录或离线 catch-up 政策。详见 [Action Resolution](docs/architecture/ACTION_RESOLUTION.md)、[Scenes and Perception](docs/architecture/SCENES_AND_PERCEPTION.md) 和 [Simulation Scheduler](docs/architecture/SIMULATION_SCHEDULER.md)。

Stage 4 — LLM Infrastructure 已完成并冻结。C-005E5 将四种 provider adapter、ModelRegistry、purpose routing、retry、accounting/pricing、Budget Guard 和 session credentials 接入单一生产 composition root。桌面 API key 由 OS credential facilities 持久化；Python Core 只接收内存 session credential。非秘密配置使用严格 version 1 JSON，启动不会发现模型、验证 key 或发起生成。全部验收保持离线，没有真实付费 API；可选 live smoke 必须显式 opt-in。详见 [生产组装](docs/architecture/LLM_PRODUCTION_COMPOSITION.md)、[Stage 4 验收](docs/architecture/STAGE4_ACCEPTANCE.md)、[OpenAI Responses adapter](docs/architecture/OPENAI_RESPONSES_ADAPTER.md)、[Gemini Interactions adapter](docs/architecture/GEMINI_INTERACTIONS_ADAPTER.md)、[Anthropic Messages adapter](docs/architecture/ANTHROPIC_MESSAGES_ADAPTER.md)、[LLM routing](docs/architecture/LLM_ROUTING.md)、[Budget Guard](docs/architecture/LLM_BUDGET_GUARD.md)、[LLM accounting](docs/architecture/LLM_ACCOUNTING.md)、[执行策略](docs/architecture/LLM_EXECUTION_POLICY.md)、[基础契约](docs/architecture/LLM_INFRASTRUCTURE.md)、[结构化生成](docs/architecture/STRUCTURED_GENERATION.md) 和 [真实文本流](docs/architecture/LLM_STREAMING.md)。

Stage 3 已完成 canonical authored-content、Character Card/Lorebook 离线导入、Draft/Preview/confirmed Commit、外部 JSON 导出和 `.lwcontent` 原生内容包。原生包支持显式 roots 的依赖闭包、shared references、完整来源、本地 SHA-256 资产、六种三方冲突与事务化 accepted baseline。详见 [Stage 3 验收](docs/architecture/STAGE_3_ACCEPTANCE.md)、[原生内容包](docs/architecture/NATIVE_CONTENT_PACKAGE.md)、[内容模型](docs/architecture/CONTENT_MODEL.md)、[导入](docs/architecture/IMPORT_MODEL.md)、[导出](docs/architecture/EXPORT_MODEL.md) 和 [持久化](docs/architecture/PERSISTENCE_MODEL.md)。

`.lwcontent` = authored content package；`.lworld` 保留给未来 runtime-world/state package。content package != backup != running world；hash integrity != publisher authentication；filesystem blobs + SQLite 不被宣称为一个 ACID transaction。导入/导出不创建 Runtime World/Character，不断言 Truth 或授予 Belief/PlayerKnowledge。作者文本/regex/activation metadata 保持不可信数据，不执行。

运行内容实例化、automatic Lore→Truth/Belief、prompt assembly、Memory/RAG、Director、Character Agent、AI Builder、checkpoint/branch、`.lworld`、cloud sync、marketplace 和 final UI 尚未实现。C-006A Activation 只是到期工作；C-006B Scene 只是互动上下文，Observation 只记录事件访问，二者都不执行认知或对话语义。外部 PNG/APNG writer、CHARX、任意图复制、签名与 orphan blob GC 仍 deferred。Stage 2 的资源级 CAS、幂等、ledger/rebuild 和知识隔离继续沿用，见 [Stage 2 验收](docs/architecture/STAGE_2_ACCEPTANCE.md)。provider tools、settings UI、conversation persistence 和真实付费 API 验证尚未实现。

C-002 运行时基础继续沿用：共享 React UI、Tauri v2 Windows 开发壳、Python Core 启停协议、系统 API、SQLite 迁移元数据、结构化日志和 CI。页面仅显示 Core Connecting / Ready / Failed。

Director、Character Agent、一般世界模拟、业务 HTTP API、自动知识传播、语义检索及最终 UI 尚未实现。当前生产 action registry 只有 `move_player` v1；Scene lifecycle 是内部应用操作。生产 snapshot store 只读，正式世界变更通过 Kernel/UoW 管线执行；投影恢复另用内部 ProjectionRebuilder。冻结产品规则保持不变；P-01 的 catch-up/推进政策及其余待确认问题仍保留，见 [PRODUCT_SPEC.md](docs/product/PRODUCT_SPEC.md)。Stage 0 审查见 [ARCHITECTURE_REVIEW_001.md](docs/architecture/ARCHITECTURE_REVIEW_001.md)，运行时边界见 [RUNTIME_FOUNDATION.md](docs/architecture/RUNTIME_FOUNDATION.md)。

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
