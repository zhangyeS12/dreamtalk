# 2026-10-08 · Desktop 0.1.42 GitHub 发布

用户明确要求将当前版本发布到GitHub。本轮范围是0.1.42源码及Windows x64完整便携预发布，包含前序0.1.41地点优化和0.1.38～0.1.40维护；不扩大功能验收，不修改用户存档、自启动注册或既有CI定义。

## 发布基线与范围

- 正式仓库为`D:\LivingWorld`，本轮起始HEAD为`0e6f2ee306450f98f188cd112ce6bcc4dcf17641`。发布前fetch核对`origin/main`和`origin/codex/world-archive`均为该提交，远程仓库为公开。
- Desktop版本为0.1.42，API协议为1，迁移源码head为0038_location_policies；根npm/Web/Core独立版本保持0.1.0。本轮未执行真实存档迁移。
- 源码同步采用普通快进，不强推或改写历史；发布提交使用`[skip ci]`，保留既有测试与工作流，不宣称CI通过。
- 发布入口为[v0.1.42](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.42)，附件为`dreamtalk-0.1.42-windows-x64.zip`和`SHA256SUMS.txt`。具体上传、公开下载与提交标识在发布完成后补记；本提交只记录已获授权的准备状态。

## 程序与包的证据

沿用已完成的`--build-only`产物`artifacts/portable/providers-0142/dreamtalk`，不重建或运行程序。在独立`artifacts/release-0142/`发布目录复制完整包、更新帮助文档及源码链接、添加BUILD_INFO.json后重新压缩；原本地包和旧Release均保留。

| 文件 | 原构建与发布准备时一致的SHA-256 |
| --- | --- |
| Desktop EXE | `bb90b3f5634def247c93a623f2622d917d4be1d9202dffb66e684d2cead3bca5` |
| Core EXE | `f37ecf30f79100d9d731a6889c7ade9aa3e50e294d80ed04c1f92d8d9c6ed0c3` |

前轮lint、类型、格式及build-only证据见[模型适配记录](2026-10-08-provider-compatibility.md)，地点实现见[地点记录](2026-10-07-location-scopes.md)。发布阶段核对Git差异、文档链接、程序及源码哈希、包内文件名、上传附件与匿名下载；不启动应用，不运行自动测试、付费模型或真实迁移。构建体积、STATIC_VCRUNTIME弃用及PyInstaller可选hidden import告警保持，不据发布成功消除。

发布前只对本轮待提交文本与包内文件名做有界敏感信息核对；匹配的凭据样式来自原已提交的离线测试fixture，未新增真实密钥或个人数据库。不将这种模式核对称为完整安全审计。

## 交付与验收边界

公开下载、源码同步、编译成功与用户体验验收分开。地点交互、旧存档升级、四类模型/代理具体效果、长期记忆和前序界面仍按[状态清单](../PROJECT_STATUS.md)的具体范围等待用户；共同联系继续由用户先等待，不触发生成。程序尚未签名，没有自动更新；完整离线演化、完整World Builder、运行世界备份/分支等仍未实现。

包内文档是发布源码提交的快照，`SOURCE_REVISION.txt`和`BUILD_INFO.json`提供可追溯引用；发布后的仓库说明可能有后续记录提交，不将包内快照与最新仓库文档混为一项。
