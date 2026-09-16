# LivingWorld

## 项目定位

LivingWorld 是持久化、事件驱动的多角色 AI 世界，不是普通聊天机器人。Director 负责世界与宏观剧情调度，Character Agent 主要负责自己拥有的记忆、人格表达和与玩家对话；世界真实事实、角色知识和玩家知识相互分离。

## 开发状态

当前阶段：**Stage 1 — C-002 Final Engineering Foundation**。已建立共享 React UI、Tauri v2 Windows 开发壳、Python Core 启停协议、系统 API、SQLite 迁移元数据、结构化日志和 CI。页面仅显示 Core Connecting / Ready / Failed。

Director、Character Agent、世界模拟、World/Character 业务表和最终 UI 尚未实现。冻结规则和 P-01 至 P-19 不变，见 [PRODUCT_SPEC.md](docs/product/PRODUCT_SPEC.md)。Stage 0 审查见 [ARCHITECTURE_REVIEW_001.md](docs/architecture/ARCHITECTURE_REVIEW_001.md)，本阶段实现边界见 [RUNTIME_FOUNDATION.md](docs/architecture/RUNTIME_FOUNDATION.md)。

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
