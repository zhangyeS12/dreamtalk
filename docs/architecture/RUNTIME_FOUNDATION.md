# C-002：Application Runtime Foundation

状态：C-002 Stage 1 运行时基础继续沿用，本文同步记录 C-003A 领域与 C-003B 持久化接线。Stage 0 的 [冻结规则与 P-01～P-19](../product/PRODUCT_SPEC.md) 保持不变。当前不实现 Director、Agent、世界模拟、业务 API 或最终 UI。

## 工程边界与依赖

```text
domain ← application ← infrastructure / adapters
                         ↑
                       bootstrap（composition root）
```

domain 包含无框架的系统契约、RequestId、领域快照及 C-006A typed scheduling values；application 协调 readiness、shutdown 与 tickless scheduler；infrastructure 提供 SQLAlchemy AsyncEngine / aiosqlite / Alembic 的 SQLite 基础及结构化日志；HTTP adapter 使用 FastAPI / Pydantic v2；bootstrap 负责 asyncio/Uvicorn/Database/scheduler 生命周期与组装。内层依赖方向由 AST 架构测试检查。

共享 React UI 位于 `apps/web`，Tauri 壳位于 `apps/desktop`；所有 UI Core 请求经过 `packages/api-client` 的 CoreClient。UI 不知道固定 Core 端口。C-003B 引入任务指定的 SQLAlchemy ORM / Alembic；没有引入消息队列、Agent 框架或云数据库。

## 集中系统契约

唯一协议编号来源为 [api_contract.json](../../services/core/src/livingworld/domain/api_contract.json)，其中 `api_protocol = 1`。Python 使用包资源读取，TypeScript 导入同一 JSON，Rust 在编译时包含同一 JSON。wheel 必须携带该契约；构建检查会验证内容。

| API | 鉴权 | 语义 |
| --- | --- | --- |
| `GET /system/live` | 无 | 进程 liveness，返回 `live`，不返回运行数据 |
| `GET /system/health` | Bearer | 返回 `ready`、`core_version`、`api_protocol`、`generation` 与安全的 `llm_status` |
| `POST /system/shutdown` | Bearer + UUID `X-Request-Id` | 接受幂等系统关闭请求；同一 generation 重复请求不重复触发关闭 |

没有业务 API、公开 OpenAPI/docs 页面或数据库路径泄漏。shutdown RequestId 是基础设施抽象，不定义未来世界事件的幂等、Outreach 去重或业务 mutation cache。

## Desktop bootstrap v1

调用方将以下字段写到不可预测的 app-data runtime 子目录，启动参数为 `--desktop --bootstrap-path <path> --parent-pid <pid>`：

| 字段 | 定义 |
| --- | --- |
| `bootstrap_secret` | 至少 32 字符的随机启动 secret；不通过命令行传递、不记录日志 |
| `instance_nonce` | 每次启动的新 nonce；绑定本次 ready discovery |
| `protocol_min` / `protocol_max` | 调用方支持的协议范围；不兼容则拒绝启动 |
| `data_dir` / `log_dir` | 绝对 app-data 路径；源码与包资源目录拒绝作为数据或日志目录 |
| `allowed_origins`（可选） | 浏览器/WebView 的精确 CORS origin 列表；默认没有跨 origin 访问 |
| `llm_config_path`（可选） | 绝对 app-data 非秘密配置路径；不包含 API key |

Core 验证并读取后删除 bootstrap 文件。Core 以 OS 分配端口只绑定 `127.0.0.1`。SQLite 初始化、迁移与服务器启动成功后，原子发布同目录的 `ready.json`：endpoint、core_version、api_protocol、generation、instance_nonce、pid、launcher_pid；文件不含 bearer、bootstrap secret、DB path、用户数据或世界名称。

`launcher_pid` 用于 Windows venv redirector 场景：实际解释器 PID 或其 launcher PID 必须匹配 Rust 启动的子进程。该校验同时结合随机 nonce、协议和 authenticated health，不单独信任磁盘 endpoint。

双方在内存中派生 session：`HMAC-SHA256(bootstrap_secret, session_derivation + ':' + nonce + ':' + generation)`。派生标签同样来自集中 JSON 契约。session 只保存在 Core、Rust supervisor 与可信 WebView 内存，不写入 ready.json、数据库、日志、浏览器 storage 或构建产物。关闭后丢弃 session，重新启动使用新的 generation 和 secret。

## Supervisor 与关闭

CoreSupervisor 定义 Starting、Ready、Degraded、Restarting、Failed、Stopping。Rust 直接启动 checkout `.venv` 的 Python，并等待 ready record，校验身份、loopback URL 和契约后进行鉴权 health。失败时清理所属子进程和短期文件。health 失败进入 Degraded；显式 restart 会结束旧进程并建立新 generation。当前未实现自动重启策略。

窗口关闭时 Tauri 暂缓退出，Rust 发送鉴权 shutdown，等待 Core lifespan 完成及进程退出；超时后仅终止自己启动的 Windows 进程树。Core 还监视 Windows supervisor parent PID，在父进程消失后结束。没有实现 macOS/Linux desktop 的特有进程机制。

C-005E5 将 sidecar stdin 保留为 Rust→Python 的 bounded credential control channel。Rust 在 shutdown 前先关闭 stdin writer；Python 使用 unbuffered pipe reader并有限等待其退出，避免解释器结束时的 buffered-reader 竞态。该通道不向 WebView 暴露，也不承载业务 RPC。桌面凭据由 OS-native keyring 持久化，Core 仅保存 session copy；完整边界见 [LLM_PRODUCTION_COMPOSITION.md](LLM_PRODUCTION_COMPOSITION.md)。

Core 的 graceful drain 上限为 5 秒，窗口关闭的 supervisor 等待为 8 秒，留出 transport drain 和进程退出余量；超时 fallback 有单独的 Windows 集成测试。

C-006A composition root 还持有 `SimulationSchedulerRuntime`。每个显式 active World 最多一个可中断 asyncio task；shutdown 先 wake/join scheduler waits，再 dispose Database，不会把未到期 Trigger 标为 FIRED。schedule/cancel/未来 clock mutation 使用进程内 signal 唤醒，但 SQLite queue 仍是事实来源。详见 [SIMULATION_SCHEDULER.md](SIMULATION_SCHEDULER.md)。

`report_ui_ready` 是可信 WebView 对 compatible authenticated health 的反馈，不是业务 API。Windows debug smoke 模式在该反馈后关闭实际窗口，检查日志中的完整生命周期，并要求走 graceful 路径。

桌面 build 显式启用 `custom-protocol`，从内嵌 Web 资源加载 UI；desktop dev 使用独立 Vite server。CoreClient 将浏览器原生 fetch 绑定到 globalThis，避免 native browser/WebView 的调用上下文错误。

## Browser 开发连接

`dev:web` 的 Node launcher 启动同一 Core、校验 ready record，将派生 session 通过仅开发模式的 Vite virtual module 交给页面；Vite 只监听 loopback。正常 build 不嵌入 session，Tauri build 从 Rust IPC 获取连接。独立发布的 browser transport/session delivery 尚未实现；未配置的生产 Web 页面显示 Core Failed。

该开发通道不能暴露到 LAN 或互联网。服务器/云 transport 留待后续任务，不在本阶段加入。

## SQLite 与日志

数据库在 app data 的 `data/runtime.sqlite3`。C-003B 集中创建 AsyncEngine 与 session factory，每条连接启用 WAL、foreign_keys、recursive_triggers、busy_timeout，并在启动时探测 FTS5。bootstrap await 数据库初始化后启动 HTTP；关闭时释放 process-owned engine。领域 schema 与约束见 [PERSISTENCE_MODEL.md](PERSISTENCE_MODEL.md)，没有业务 API。

Alembic 是唯一迁移执行器，alembic_version 是权威 cursor：0001 精确表示旧 C-002 基础，0002 增加领域表。旧库必须先验证版本、历史 checksum 与 schema 形状，才 stamp 0001 并 upgrade；任何歧义失败关闭，不自动修复或重建。旧 schema_version=1 和 migration_history 原始行作为兼容/历史证据保留，不再表示当前 schema cursor，也不驱动迁移。迁移失败事务回滚，重复启动不重放、不重复审计。

普通日志只接受 timestamp、level、component、event 与可选已验证 UUID trace_id；不接受任意 payload 或异常原文。C-006A 增加专用 scheduler metadata allowlist：world id、kind、due/lag WorldTime、batch/activation count 和 state，接口不能接收 trigger payload。Core stdout 与 app-data `logs/core-<generation>.jsonl` 使用同一结构。HTTP access log 被禁用；secret/token/prompt/user conversation 默认不记录。日志轮转/保留策略尚未实现。

## 明确的扩展与测试点

- Python BootstrapFileAccess 与 Rust BootstrapFilePolicy 预留 owner/ACL 校验接口；当前仅做文件基本验证、create_new 和随机目录，未实现生产 ACL 加固。
- 当前开发 executable 依赖 checkout Python venv；独立 Python runtime 分发、安装包、签名和更新不在 C-002 内。
- SQLite migration 已由 C-003B 接管为 Alembic；后续新增 schema 必须由明确任务及新 revision 定义，不能恢复第二套 runner。
- CoreClient 的连接来源可被后续 server transport 替换；当前不提供云鉴权或多用户连接协议。
- 现阶段没有业务 trace、LLM 调用、真实费用统计或世界行为。

## 相关实现与证据

- [Python tests](../../tests/core/test_bootstrap.py)、[system tests](../../tests/core/test_system.py)、[SQLite tests](../../tests/core/test_database.py)、[依赖方向 tests](../../tests/core/test_architecture.py)
- [Windows supervisor tests](../../apps/desktop/src-tauri/tests/supervisor.rs)、[真实 WebView smoke](../../scripts/desktop-smoke.py)
- [真实 browser smoke](../../scripts/browser-smoke.py)：启动所属 Core/Vite，验证 Core Ready 与无 page error，然后要求 graceful shutdown。Playwright 仅在 browser-test 测试依赖组中使用。
- [GitHub Actions](../../.github/workflows/foundation.yml)

实现依据包括 [Tauri Windows prerequisites](https://v2.tauri.app/start/prerequisites/)、[Tauri Rust IPC](https://v2.tauri.app/develop/calling-rust/)、[Python asyncio](https://docs.python.org/3/library/asyncio.html)、[SQLite WAL](https://www.sqlite.org/wal.html)。这些来源不扩展产品定义。
