# dreamtalk

All engineering agents must read AGENTS.md before modifying the repository.

## 下载体验（Windows）

**[dreamtalk 0.1.47 发布准备](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.47)** · [Windows x64 安装包](https://github.com/zhangyeS12/dreamtalk/releases/download/v0.1.47/dreamtalk_0.1.47_x64-setup.exe) · [完整便携包](https://github.com/zhangyeS12/dreamtalk/releases/download/v0.1.47/dreamtalk-0.1.47-windows-x64.zip)

本次发布已获用户批准，构建和上传结果见[记录](docs/maintenance/2026-10-08-authored-deletion.md)。公开前仍可使用历史 v0.1.42。

1. 优先下载并运行完整安装器 `dreamtalk_0.1.47_x64-setup.exe`；便携版则完整解压 `dreamtalk-0.1.47-windows-x64.zip` 后运行 `dreamtalk/dreamtalk-desktop.exe`。GitHub 自动生成的 **Source code** 是源码，不是可运行程序。
2. 支持 Windows 10/11 x64，需要 [Microsoft WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)。无需安装 Python、Node 或 Rust；请保留同目录的 `core/`。
3. 创建世界，配置自己的模型服务和API Key（书架设置是默认，各世界可独立覆盖；0.1.47包含删除入口和签名更新），在通讯录创建或导入角色卡，然后打开聊天。模型使用可能产生服务商费用；后台功能默认关闭。

公开v0.1.42是未签名的 **预发布体验版**，没有自动更新。本地0.1.46已实现更新入口和签名安装打包，尚未公开新包／更新频道，仍无最新版整体验收结论。详见[应用更新](docs/WINDOWS_UPDATES.md)。更新前从旧版托盘退出程序并备份重要应用数据。详细操作、升级和反馈方式见 [Windows 便携版说明](docs/PORTABLE_WINDOWS.md)。

当前逐项完成度、待验收、明确限制与接续顺序见 [当前状态清单](docs/PROJECT_STATUS.md)；工作规则见 [AGENTS.md](AGENTS.md)，模块入口、0.1.46应用更新、0.1.45封面修复、0.1.44移动优化／0.1.43世界独立模型、0.1.42模型适配、0.1.41地点优化及公开产物状态见 [HANDOFF.md](HANDOFF.md)。以下架构介绍不替代当前进度清单。

## 项目定位

dreamtalk 是持久化、事件驱动的多角色 AI 世界，不是普通聊天机器人。Director 负责世界与宏观剧情调度，Character Agent 主要负责自己拥有的记忆、人格表达和与玩家对话；世界真实事实、角色知识和玩家知识相互分离。项目在 GitHub 公开开发，源码采用 [Apache-2.0 许可证](LICENSE)。旧工程名及仍需兼容的内部标识见 [项目命名与兼容性](docs/architecture/PROJECT_IDENTITY.md)。

## 开发状态

截至2026-10-08，当前Desktop工作区 **0.1.46**，已build-only交付完整签名安装器及便携包，新增更新入口，继承封面缓存修复、角色移动及默认／世界独立模型；[本轮记录](docs/maintenance/2026-10-08-desktop-updates.md)。本地源码及产物未提交／推送／发布，更新频道尚未上线，公开仍上方v0.1.42完整预发布。项目处于体验和验收阶段，卡／书当轮外部JSON导入已获用户验收，其他功能不据此推定通过；已完成、待验收和未实现见状态清单。前轮旧包清理及自启动切至0.1.43见[记录](docs/maintenance/2026-10-08-local-cleanup.md)，工程端本轮未运行安装器、改当前启动注册或删在用旧入口。

Q-001B 提供仅开发环境启用的 [开发者运行时检查器](docs/architecture/RUNTIME_INSPECTOR.md)，用于通过真实 API/application 路径观察时钟、位置、Scene、trigger、activation、WorldEvent、Observation 与 owner-scoped EpisodicMemory。它不是最终产品 UI，也没有加入 Activation consumer 或自动 Observation→Memory。

普通用户首页为[世界档案书架](docs/WORLD_ARCHIVE.md)，初始横排书脊不显示详情，悬停轻抽、点击抽出后才展示右侧信息；空白书提供创建／导入入口。书排支持直接鼠标拖动及双向循环，每圈至少12本并始终保留空白入口，正面和书脊默认显示世界名；[编辑封面](docs/WORLD_COVERS.md)支持独立标题与三面本地图片裁剪，保留左上角dreamtalk。选择档案并明确进入后显示“聊天 / 通讯录 / 设置 / 我”四标签，支持创建与切换世界、暂停/恢复及时间倍率设置、在每个世界绑定 Player；未绑定的新世界可通过 canonical 命令从“家”创建本地玩家并进入。支持通用与世界专属个人资料保存，以及置顶的玩家已知“世界事件”时间线。事件查询先按绑定 Player 的 Observation 授权，再读取安全展示信息；已知事件可由玩家选择带入已有会话的待编辑消息，不会自动发送。[设置手册](docs/SETTINGS_HANDBOOK.md)按应用与当前世界分类，通讯录支持角色卡新建、联网生成、导入、预览确认和独立更新；世界书的新建、联网生成、导入与编辑已移到书架管理；通讯录只显示当前世界已确认的角色资料。首次打开角色会建立世界隔离的持久私聊会话；聊天页可读取该 Player 有权查看的消息记录，安全展示角色扮演 Markdown，并支持回车发送及 Shift+回车换行。角色卡开场白可作为该角色回复的语气示例，但不会自动成为已发送的消息。当前世界可创建多角色群聊，群聊消息和角色回复使用独立的一次性回合认领与共享 Token 上限；@角色名 指定下一位发言者，其他情况由独立调度器按已确认人格和群聊记录选人。内部服务和受认证 API 可幂等保存玩家消息与待处理回合；模型执行层已有逐次调用的保守 Token 预留，角色回复已具备内部一次性领取、受控模型生成与幂等提交边界，并已接入正式运行时与页面私聊发送入口；仅当配置了单一可用模型或明确的聊天路由、可信 Token 上限及会话凭证时才能发送。详见 [产品界面与知情边界](docs/architecture/PRODUCT_SURFACE.md) 与 [聊天模型](docs/architecture/CHAT_MODEL.md)。开发者检查器通过 URL 查询参数 `?developer=1` 进入。

Stage 5 — World Kernel & Simulation Runtime 已完成并冻结。C-006D 的 clock reconciliation、C-006C sparse activation/coalescing 与 C-006B deterministic Action/Scene/event-time perception 继续作为 Stage 6 substrate。详见 [Stage 5 验收](docs/architecture/STAGE5_ACCEPTANCE.md)、[Clock Reconciliation](docs/architecture/CLOCK_RECONCILIATION.md)、[Sparse Activation](docs/architecture/SPARSE_ACTIVATION.md)、[Action Resolution](docs/architecture/ACTION_RESOLUTION.md) 和 [Scenes and Perception](docs/architecture/SCENES_AND_PERCEPTION.md)。

Stage 4 — LLM Infrastructure 已完成并冻结。C-005E5 将四种 provider adapter、ModelRegistry、purpose routing、retry、accounting/pricing、Budget Guard 和 session credentials 接入单一生产 composition root。桌面 API key 由 OS credential facilities 持久化；Python Core 只接收内存 session credential。非秘密配置的内层使用严格version 1 JSON，0.1.43支持默认／世界覆盖的version 2容器，旧v1作为默认兼容；桌面设置提供单模型首次配置入口，常见型号使用经核对的容量预设，未知型号在高级设置确认可信Token上界。启动和配置都不会发现模型、验证 key 或发起生成。全部验收保持离线，没有真实付费 API；可选 live smoke 必须显式 opt-in。详见 [生产组装](docs/architecture/LLM_PRODUCTION_COMPOSITION.md)、[Stage 4 验收](docs/architecture/STAGE4_ACCEPTANCE.md)、[OpenAI Responses adapter](docs/architecture/OPENAI_RESPONSES_ADAPTER.md)、[Gemini Interactions adapter](docs/architecture/GEMINI_INTERACTIONS_ADAPTER.md)、[Anthropic Messages adapter](docs/architecture/ANTHROPIC_MESSAGES_ADAPTER.md)、[LLM routing](docs/architecture/LLM_ROUTING.md)、[Budget Guard](docs/architecture/LLM_BUDGET_GUARD.md)、[LLM accounting](docs/architecture/LLM_ACCOUNTING.md)、[执行策略](docs/architecture/LLM_EXECUTION_POLICY.md)、[基础契约](docs/architecture/LLM_INFRASTRUCTURE.md)、[结构化生成](docs/architecture/STRUCTURED_GENERATION.md) 和 [真实文本流](docs/architecture/LLM_STREAMING.md)。

Stage 3 已完成 canonical authored-content、Character Card/Lorebook 离线导入、Draft/Preview/confirmed Commit、外部 JSON 导出和 `.lwcontent` 原生内容包。原生包支持显式 roots 的依赖闭包、shared references、完整来源、本地 SHA-256 资产、六种三方冲突与事务化 accepted baseline。详见 [Stage 3 验收](docs/architecture/STAGE_3_ACCEPTANCE.md)、[原生内容包](docs/architecture/NATIVE_CONTENT_PACKAGE.md)、[内容模型](docs/architecture/CONTENT_MODEL.md)、[导入](docs/architecture/IMPORT_MODEL.md)、[导出](docs/architecture/EXPORT_MODEL.md) 和 [持久化](docs/architecture/PERSISTENCE_MODEL.md)。

`.lwcontent` = authored content package；`.lworld` 保留给未来 runtime-world/state package。旧格式后缀为兼容标识，不随项目改名而变。content package != backup != running world；hash integrity != publisher authentication；filesystem blobs + SQLite 不被宣称为一个 ACID transaction。导入/导出不创建 Runtime World/Character，不断言 Truth 或授予 Belief/PlayerKnowledge。作者文本/regex/activation metadata 保持不可信数据，不执行。

当前角色聊天上下文已接入本角色授权记忆、玩家描述、当前世界确认的角色卡，以及逐条开放的公共世界背景。世界书条目默认隐藏；暗线不因导入自动进入角色上下文。群聊记录按固定成员授权，沉默成员同样可在之后读取该群已发送的消息；聊天文本不会自动成为 WorldTruth、KnowledgeAssertion 或 Observation。长期聊天记忆与历史原文召回、Director 受约束的日常批量规划、手动处理的世界动态池、角色卡／世界书联网 Builder 已完成相应切片，边界见 HANDOFF 与各使用说明；相遇、共同休闲、阵营相识与世界内UI首轮优化已完成相应切片；更完整的自主剧情/关系成长、自动知识传播、checkpoint/branch与runtime`.lworld`仍未实现，完整离线重建和最终产品验收尚未完成。cloud sync、marketplace不是已批准排期。Stage 5 catch-up 只 materialize 到期 work，不编造离线叙事或角色决定。外部 PNG/APNG writer、CHARX、任意图复制、签名与 orphan blob GC 仍 deferred。Stage 2 的资源级 CAS、幂等、ledger/rebuild 和知识隔离继续沿用，见 [Stage 2 验收](docs/architecture/STAGE_2_ACCEPTANCE.md)。provider tools和完整多模型管理UI尚未完成；四类adapter和同次事件／记忆路径已有实现；用户历史聊天／生成反馈不代表全部provider／模型／代理已验收。

C-002 运行时基础继续沿用：共享 React UI、Tauri v2 Windows 开发壳、Python Core 启停协议、系统 API、SQLite 迁移元数据、结构化日志和 CI。普通前台启动由[三维流星动画](docs/CELESTIAL_STARTUP.md)承接真实加载，至少展示1.5秒后进入就绪书架；正常等待不显示核心连接技术文字，失败保留可理解的重试。开发Inspector的技术状态独立；进入选定世界后显示普通用户四标签页面。

当前已有受约束的角色回复与独立群聊发言调度器；Director已接线日常/移动、有限相遇及共同休闲，角色相识/阵营、本地有界语义+词法RAG和0.1.37观星室界面均已实现。尚未形成完整自主剧情、关系成长或自动知识传播；有界召回不是无限历史覆盖，最新版运行与视觉仍需用户验收。生产 action registry 与 Director 已批准的内核日常命令保持各自边界；Scene lifecycle 是内部应用操作。生产 snapshot store 只读，正式世界变更通过 Kernel/UoW 管线执行；投影恢复另用内部 ProjectionRebuilder。P-01 的时间推进/离线/暂停部分已由 C-006D 解决；其余待确认问题见 [PRODUCT_SPEC.md](docs/product/PRODUCT_SPEC.md)。Stage 0 审查见 [ARCHITECTURE_REVIEW_001.md](docs/architecture/ARCHITECTURE_REVIEW_001.md)，运行时边界见 [RUNTIME_FOUNDATION.md](docs/architecture/RUNTIME_FOUNDATION.md)。

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

直接使用 bootstrap 启动 Core：`uv run dreamtalk-core --desktop --bootstrap-path <absolute-path> --parent-pid <pid>`。旧命令 `livingworld-core` 仍作为兼容别名保留。bootstrap 必须由调用方创建，详见 [运行时协议](docs/architecture/RUNTIME_FOUNDATION.md)。

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

# Windows：构建随附 Python Core 的本地便携目录/zip（不需要使用者安装开发依赖）
npm run build:portable

# Windows integration
npm run test:desktop
npm run build:desktop
npm run test:desktop-smoke

# Optional real provider smoke: disabled unless --enable-live-provider is added.
# External API usage may incur cost; this is never run by CI/pytest.
npm run test:llm-live -- --config <path> --data-dir <path> --provider <id> --model <id> --credential-env <ENV_NAME>
```

`build:core` 生成 `artifacts/core/*.whl`；`build:desktop` 生成未签名的 Windows debug executable，依赖当前 checkout 的 `.venv`。`build:portable` 先冻结 Python Core 并验证独立启动和迁移，再构建 release 桌面程序，生成 `artifacts/portable/dreamtalk/` 与 zip。构建产物本身不自动发布；本次0.1.42已按用户明确授权发布到GitHub Release，仍不是签名安装包；使用说明见 [Windows 便携版](docs/PORTABLE_WINDOWS.md)。

只生成便携产物、由验收者另行执行生命周期检查时，可使用 `npm run build:portable -- --build-only`；默认命令仍包含自检。

开发数据库与日志保存在 app data。桌面使用 Tauri 的 `app_data_dir`；独立 Core / browser 开发 launcher 暂时沿用历史兼容路径 `%LOCALAPPDATA%/LivingWorld/development`。安装和源码目录不保存运行数据库或 bootstrap credentials。

GitHub Actions 配置包含 Python lint/test/wheel、TypeScript lint/test/Web build、真实 browser smoke 和 Windows supervisor/WebView smoke。远程 CI 结果以实际运行记录为准。
