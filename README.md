# LivingWorld

All engineering agents must read AGENTS.md before modifying the repository.

## 项目定位

LivingWorld 是持久化、事件驱动的多角色 AI 世界，不是普通聊天机器人。Director 负责世界与宏观剧情调度，Character Agent 主要负责自己拥有的记忆、人格表达和与玩家对话；世界真实事实、角色知识和玩家知识相互分离。

## 开发状态

当前阶段：**Stage 4 — C-005C1 Structured Generation & Local Schema Validation**。沿用 C-005A/B 的中立契约与非流式 Chat adapter，增加显式 NONE / NATIVE_JSON_SCHEMA / JSON_OBJECT_LOCAL_VALIDATE 模式、严格 JSON 解析和本地 Draft 2020-12 验证。只有本地验证通过才生成结构化结果；已完成调用的后处理失败保留不含模型内容的计量摘要，拒绝仍返回成功响应。OpenAI/DeepSeek 通过受控离线 fixtures 验证。真实 API 调用、production default wiring、streaming、retry/repair、费用、路由/预算和使用记录持久化尚未验证或实现。详见 [LLM 基础契约](docs/architecture/LLM_INFRASTRUCTURE.md)、[Chat adapter](docs/architecture/OPENAI_COMPATIBLE_ADAPTER.md) 和 [结构化生成边界](docs/architecture/STRUCTURED_GENERATION.md)。

Stage 3 已完成 canonical authored-content、Character Card/Lorebook 离线导入、Draft/Preview/confirmed Commit、外部 JSON 导出和 `.lwcontent` 原生内容包。原生包支持显式 roots 的依赖闭包、shared references、完整来源、本地 SHA-256 资产、六种三方冲突与事务化 accepted baseline。详见 [Stage 3 验收](docs/architecture/STAGE_3_ACCEPTANCE.md)、[原生内容包](docs/architecture/NATIVE_CONTENT_PACKAGE.md)、[内容模型](docs/architecture/CONTENT_MODEL.md)、[导入](docs/architecture/IMPORT_MODEL.md)、[导出](docs/architecture/EXPORT_MODEL.md) 和 [持久化](docs/architecture/PERSISTENCE_MODEL.md)。

`.lwcontent` = authored content package；`.lworld` 保留给未来 runtime-world/state package。content package != backup != running world；hash integrity != publisher authentication；filesystem blobs + SQLite 不被宣称为一个 ACID transaction。导入/导出不创建 Runtime World/Character，不断言 Truth 或授予 Belief/PlayerKnowledge。作者文本/regex/activation metadata 保持不可信数据，不执行。

运行内容实例化、automatic Lore→Truth/Belief、activation、prompt assembly、Memory/RAG、Director、Character Agent、AI Builder、checkpoint/branch、`.lworld`、cloud sync、marketplace 和 final UI 尚未实现。外部 PNG/APNG writer、CHARX、任意图复制、签名与 orphan blob GC 仍 deferred。Stage 2 的资源级 CAS、幂等、ledger/rebuild 和知识隔离继续沿用，见 [Stage 2 验收](docs/architecture/STAGE_2_ACCEPTANCE.md)。停止于 C-005C1，C-005C2 未开始。

C-002 运行时基础继续沿用：共享 React UI、Tauri v2 Windows 开发壳、Python Core 启停协议、系统 API、SQLite 迁移元数据、结构化日志和 CI。页面仅显示 Core Connecting / Ready / Failed。

Director、Character Agent、世界模拟、业务 HTTP API、自动知识传播、语义检索及最终 UI 尚未实现。生产 snapshot store 只读，正式世界变更通过命令管线执行；投影恢复另用内部 ProjectionRebuilder。冻结产品规则保持不变；P-01 的推进政策及其余待确认问题仍保留，见 [PRODUCT_SPEC.md](docs/product/PRODUCT_SPEC.md)。Stage 0 审查见 [ARCHITECTURE_REVIEW_001.md](docs/architecture/ARCHITECTURE_REVIEW_001.md)，运行时边界见 [RUNTIME_FOUNDATION.md](docs/architecture/RUNTIME_FOUNDATION.md)。

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
```

`build:core` 生成 `artifacts/core/*.whl`；`build:desktop` 生成未签名、未打包的 Windows debug executable。该桌面开发产物依赖当前 checkout 的 `.venv`，尚不是独立安装包。

开发数据库与日志保存在 app data。桌面使用 Tauri 的 `app_data_dir`；独立 Core / browser 开发 launcher 使用 `%LOCALAPPDATA%/LivingWorld/development`。安装和源码目录不保存运行数据库或 bootstrap credentials。

GitHub Actions 配置包含 Python lint/test/wheel、TypeScript lint/test/Web build、真实 browser smoke 和 Windows supervisor/WebView smoke。远程 CI 结果以实际运行记录为准。
