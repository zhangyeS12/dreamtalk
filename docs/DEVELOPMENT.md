# dreamtalk 开发入口

使用和下载见[项目主页](../README.md)。开发前读[工程规则](../AGENTS.md)、[交接](../HANDOFF.md)及[状态清单](PROJECT_STATUS.md)，再按[文档导航](README.md)选择相关模块。当前版本和发行进度不在本页重复维护。

## 环境与源码

使用 Node.js、Python／uv、Rust 和 Windows 桌面构建工具；精确依赖以根 package.json、pyproject.toml、Cargo.toml 和各锁文件为准。源码不含个人密钥、存档、模型环境／权重或发布私钥。

```powershell
npm ci
uv sync --frozen
npm run lint
npm run typecheck:core
npm run check:contracts
```

| 目录 | 职责 |
| --- | --- |
| apps/web | React／TypeScript 界面 |
| apps/desktop/src-tauri | Tauri 宿主、子进程监督、模型配置及更新 |
| packages/api-client | 版本化 Core HTTP／WebSocket 客户端 |
| services/core | FastAPI、应用编排、领域／Kernel、SQLite持久化与Alembic迁移 |
| scripts | 编译、打包、签名和静态核对 |

模块调用链见[交接第3节](../HANDOFF.md#3-各部分怎样实现从哪里接手)，边界见[系统概览](architecture/SYSTEM_OVERVIEW.md)。不从旧日志猜路径或用临时副本覆盖正式源码。

## 类型与业务契约

Python 类型门禁采用锁定的 Pyright 1.1.414（MIT），复用现有 Node 工具链，仅作为开发依赖，不进入 Core 或安装载荷。Ruff 不检查跨函数类型，因此不能替代它；配置依据[官方说明](https://github.com/microsoft/pyright/blob/main/docs/configuration.md)。当前 standard 门禁由根 pyrightconfig.json 定义，覆盖整个 HTTP 目录，以及命令、LLM 执行／记账、存档协调、主动联系持久化、输入预算、分页编辑、角色版本解析、后台背景与未读、生产组装及生成器，共68个文件；尚非全仓类型覆盖。HTTP 目录新增文件自动进入门禁，没有错误忽略基线。CI 的 web job 执行此门禁，Python 矩阵检查生成契约是否过期。

业务响应 DTO 按模块维护在 services/core/src/livingworld/adapters/http/wire_contracts，contracts.py 保留兼容导出；写请求直接读取 HTTP handler 实际使用的 Pydantic 模型，复用领域枚举与运行状态类型。`npm run generate:contracts` 只读取 Python AST，生成 packages/api-client/src/contracts.generated.ts 的类型和校验；不导入应用、不连接数据库。修改契约后重新生成，禁止手改生成文件。未知注解使生成失败，不静默退成 any。

当前客户端业务 JSON 接口已全部使用生成的响应校验，覆盖聊天／记忆、内容、活动／事件、媒体／配音及开发者视图；JSON 写请求用 satisfies 核对实际请求模型。服务端绑定同源响应模型，扩展字段保留，流式进度也使用生成校验。二进制／multipart 和 SSE 传输约束仍单独处理，Tauri 宿主控制协议继续独立；不能宣称三端所有契约已生成。Python 的 Field 范围及严格校验继续由服务端执行，浏览器守卫不是完整 JSON Schema 校验器。

## 编译与验证

验证权限统一遵守 [AGENTS第20节](../AGENTS.md#20-current-verification-responsibility)。用户负责最终验收；现有离线测试（pytest、vitest、静态检查）可在隔离临时目录直接运行，缺陷修复和新功能应补回归测试。真实模型／凭据探测、真实存档操作及用户机器上已安装应用的运行仍须当前具体授权。

必要本机交付用 `npm run build:desktop:local`，独立 Cargo 目标及版本／摘要回执在 artifacts/local-desktop；共享 target/debug 不作快捷方式目标。先核对当前是否须保留旧版供更新验收，不能覆盖其入口。`build:desktop` 供 CI／原生工程检查；源码 EXE 依赖开发环境，对外完整包须另含 Core 与资源。

获准原生检查使用 `npm run test:desktop`，临时数据库位于源码外，并隔离备份、APPDATA／LOCALAPPDATA、缓存及临时目录。旧版检查更新也须隔离存档，不能以“不进入世界”为由读取已迁移数据。没有对应授权时不执行。

日常不制作安装器、便携包或 ZIP。只有对应 GitHub 发行许可才沿既有 `--build-only` 打包；先核对脚本不隐含测试。编译／打包成功不代表安装、更新、聊天、模型或迁移已验收。

## 隐私、CI与发布

提交／推送及发布遵守本轮授权；不强推、不重写历史。公开文档不写个人目录／私聊原文；许可、私钥和发布政策见[工程规则](../AGENTS.md)。静态门禁的基本入口为：

```powershell
python scripts/check-doc-links.py
python scripts/check-release-privacy.py
python scripts/check-release-privacy.py --ref HEAD
python scripts/check-release-privacy.py --package artifacts/portable/本次构建名/dreamtalk
```

分别核对文档、本次可提交文件、实际发布提交和实际载荷；路径示例不能直接当作现有产物。已知特征扫描不能替代人工审查，也不会清除旧提交和附件。

既有 foundation.yml 负责 Python 矩阵、前端／浏览器及 Windows 桌面，由 CI Gate 汇总。推送 main、`v*` 标签和 PR 时自动运行，也可手动触发；推送本身仍须用户明确提出，不弱化断言取得通过结论。发布构建通过 scripts/check-release-ci.py 核对干净工作区、完整 SHA 及该 SHA 最新工作流成功；缺失、取消、运行中或失败均阻止构建，不借用其他提交的结果；只有用户明确批准时才可用 `--skip-ci`（或 `DREAMTALK_RELEASE_SKIP_CI=1`），输出会标明跳过。这个核对不会自行推送或重跑 CI。
