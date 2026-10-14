# dreamtalk 开发入口

面向用户的项目介绍、下载与使用方法见[项目主页](../README.md)。本页只供参与开发时参考。

开始修改前完整阅读 [AGENTS.md](../AGENTS.md)、[HANDOFF.md](../HANDOFF.md) 和[当前状态](PROJECT_STATUS.md)。当前采用 React / TypeScript / Vite 前端、Tauri 桌面宿主与 Python Core，存储使用 SQLite，数据库迁移由 Alembic 管理。兼容身份保持 app.livingworld.desktop。

## 当前本地工作与交接

当前公开发行源码为v0.1.76／fcd2a05，Desktop0.1.76、迁移head0050_sticker_library_freshness；main及开发分支已同步，完整Windows资产和原更新频道已发布，证据见[记录](maintenance/2026-10-14-major-release.md)。最终发布回执的文档提交不改变发行代码或v0.1.76标签。模型环境、配音／视觉权重、录音、存档、个人配置和私钥不随源码或安装包提供；日常不打包规则继续适用。

本机图片服务自动启动及两个本地模型不限次数的原实现见[记录](maintenance/2026-10-13-local-model-startup-and-limits.md)，本次按明确授权构建0.1.76公开安装／便携资产，旧0.1.70包保持。免费云端最新版与付费配音API未测试、待确认；独立表情与配音对照许可均已结束，不运行产品、模型或原存档迁移。可选配音环境仍独立，不向Core加入Torch或CUDA。

## 本地环境

公开体验入口为完整0.1.76安装包或artifacts/portable/major-0176/dreamtalk/dreamtalk-desktop.exe；源码开发入口仍为apps/desktop/src-tauri/target/debug/dreamtalk-desktop.exe。切换前从托盘退出旧程序；编译前核对运行位置，选择未占用的输出。本次发行编译在release目录，保留用户正在运行的debug程序，没有运行新产物。原界面布局保持，检查及发布范围见[记录](maintenance/2026-10-14-major-release.md)。

需要 Node.js、Python / uv、Rust，以及 Windows 桌面构建工具。版本和依赖以根目录 package.json、pyproject.toml、锁文件、桌面 Cargo.toml 和构建脚本为准。源码下载不含个人密钥、存档或发布签名私钥。

```powershell
npm ci
uv sync --frozen
npm run lint
```

具体开发与打包命令先查根 package.json 和 scripts/；不要把历史维护记录中的路径当作当前安装位置。完整安装包和便携包必须包含 Core 与资源，不可仅发布一个 EXE。

## 验证边界

当前用户负责运行测试与最终验收。未获得具体授权，不添加或运行自动化测试、浏览器 / 桌面 smoke、真实模型探测或用户存档迁移。保留已有测试和 CI，不弱化断言。允许源码、差异、格式、lint、类型、文档链接与必要编译核对。

自2026-10-13起，除用户明确授权的GitHub发布外，不在本机打包；便携包、安装器、ZIP和 --build-only 打包均适用，日常开发完成不自动打包。必要编译或获准发布打包前检查脚本是否包含测试；发布便携版与安装器仍使用明确的 --build-only。编译／打包通过不代表聊天、升级、模型兼容或数据迁移已通过用户验收，发布打包例外也不授权运行测试或模型。

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

## 发布隐私检查

本地数据库、配置、导出与签名密钥由 .gitignore 排除；已跟踪或强制加入的文件仍须检查。公开文档保留产品契约和必要证据，不写个人目录或私聊原文。打包工具已接入静态隐私门禁；便携目录和安装器解出的实际文件也要通过检查。

```powershell
python scripts/check-release-privacy.py
python scripts/check-release-privacy.py --ref HEAD
python scripts/check-release-privacy.py --package artifacts/portable/本次构建名/dreamtalk
```

第一个命令检查当前可提交文件，第二个检查真正准备发布的提交，第三个检查实际载荷目录。只报告文件名和问题类型，不输出密钥或正文；它检查已知路径、格式与密钥特征，不能替代人工核对任意格式的数据。历史提交和已发布附件不会因本地文档修改而被清除，本轮也没有重写 Git 历史或修改 GitHub。
