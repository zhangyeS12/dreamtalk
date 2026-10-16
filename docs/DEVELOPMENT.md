# dreamtalk 开发入口

面向用户的项目介绍、下载与使用方法见[项目主页](../README.md)。本页只供参与开发时参考。

开始修改前完整阅读 [AGENTS.md](../AGENTS.md)、[HANDOFF.md](../HANDOFF.md) 和[当前状态](PROJECT_STATUS.md)。当前采用 React / TypeScript / Vite 前端、Tauri 桌面宿主与 Python Core，存储使用 SQLite，数据库迁移由 Alembic 管理。兼容身份保持 app.livingworld.desktop。

## 当前本地工作与交接

当前源码Desktop0.1.80、迁移head0053_example_world_setup、配音revision8；公开0.1.80载荷仍固定c7bcf3b及0052。本轮补齐CI门禁与原创校园示例，已获源码推送及CI验证授权，不创建新发行，见[记录](maintenance/2026-10-16-ci-campus-example.md)。模型环境、配音／视觉权重、录音、存档、个人配置和私钥不随源码或安装包提供；日常不打包规则继续适用。

本机图片服务自动启动及两个本地模型不限次数的原实现见[记录](maintenance/2026-10-13-local-model-startup-and-limits.md)。免费云端最新版与付费配音API仍待确认。历史单次隔离检查和配音对照许可不复用；用户已明确批准当前CI的具体隔离检查，范围与结果见[本轮记录](maintenance/2026-10-16-ci-campus-example.md)。可选配音环境仍独立，不向Core加入Torch或CUDA。

## 本地环境

公开体验入口为GitHub的完整0.1.80安装包；本机直接入口和产物哈希以[交接](../HANDOFF.md#2-仓库运行和版本现场)为准。源码开发入口为apps/desktop/src-tauri/target/debug/dreamtalk-desktop.exe，本轮已仅编译更新此EXE。原书架与开屏呈现保持；工程构建不启动已安装程序，也不操作真实存档。

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

第一个命令检查当前可提交文件，第二个检查真正准备发布的提交，第三个检查实际载荷目录。只报告文件名和问题类型，不输出密钥或正文；它检查已知路径、格式与密钥特征，不能替代人工核对任意格式的数据。历史提交和已发布附件不会因本地文档修改而被清除。当前CI与校园示例工作仅批准源码推送与CI验证，不含发行或本机打包授权，不重写Git历史或改变旧版本附件。

## CI与发布构建

foundation.yml覆盖Python矩阵、前端／浏览器和Windows桌面，统一由CI Gate报告。源码推送与手动触发均需遵守本轮具体授权；不能通过skip-ci、跳过检查或弱化断言取得发布通过结论。

发布用的build-only便携构建及安装器构建会先调用scripts/check-release-ci.py，要求源文件已提交且工作区干净，并核对该完整SHA的最新工作流成功。没有运行、仍在运行、取消或失败均阻止构建，不使用其他提交的成功记录。每轮结果按Actions中的完整提交核对；本地通过不能替代远端结果。此检查只读，不自动推送、重跑或改仓库设置。
