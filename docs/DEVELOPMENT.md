# dreamtalk 开发入口

面向用户的项目介绍、下载与使用方法见[项目主页](../README.md)。本页只供参与开发时参考。

开始修改前完整阅读 [AGENTS.md](../AGENTS.md)、[HANDOFF.md](../HANDOFF.md) 和[当前状态](PROJECT_STATUS.md)。当前采用 React / TypeScript / Vite 前端、Tauri 桌面宿主与 Python Core，存储使用 SQLite，数据库迁移由 Alembic 管理。兼容身份保持 app.livingworld.desktop。

## 本地环境

需要 Node.js、Python / uv、Rust，以及 Windows 桌面构建工具。版本和依赖以 package.json、锁文件、services/core/pyproject.toml、Cargo.toml 和构建脚本为准。源码下载不含个人密钥、存档或发布签名私钥。

```powershell
npm ci
uv sync --project services/core
npm run lint
```

具体开发与打包命令先查根 package.json 和 scripts/；不要把历史维护记录中的路径当作当前安装位置。完整安装包和便携包必须包含 Core 与资源，不可仅发布一个 EXE。

## 验证边界

当前用户负责运行测试与最终验收。未获得具体授权，不添加或运行自动化测试、浏览器 / 桌面 smoke、真实模型探测或用户存档迁移。保留已有测试和 CI，不弱化断言。允许源码、差异、格式、lint、类型、文档链接与必要编译打包核对。

构建前检查脚本；便携版使用明确的 --build-only，安装器同样要求 --build-only。构建通过不代表聊天、升级、模型兼容或数据迁移已通过用户验收。

## 实现导航

| 目录 | 内容 |
| --- | --- |
| apps/web | 页面、聊天与管理界面 |
| apps/desktop | 桌面监督、系统集成、模型配置和应用更新 |
| packages/api-client | 前端访问本地 Core 的接口 |
| services/core | 应用编排、领域规则、持久化与迁移 |
| scripts | 打包、签名、许可和静态核对工具 |
| docs | 使用说明、架构、批准方案与历史维护证据 |

具体 UI → API → 应用 → 存储入口见[交接第 3 节](../HANDOFF.md#3-各部分怎样实现从哪里接手)，架构见[架构概览](architecture/SYSTEM_OVERVIEW.md)。提交和公开发布需要用户授权，不提交密钥、真实存档或构建缓存。
