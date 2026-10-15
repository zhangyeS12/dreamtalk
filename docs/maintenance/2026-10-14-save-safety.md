# 2026-10-14 存档保护与可靠更新

基线：公开v0.1.77，源码提交3075f03。用户先要求只讨论，讨论后明确批准实现。本轮源码Desktop0.1.78，API1、Alembic0051、配音revision8保持；没有发布、打包、安装或运行测试/模型/真实存档。

2026-10-15继续收尾：恢复事务增加持久中断标记；普通维护取消不解除升级启动保护，只有宿主完成核对后显式开放；恢复/清空错误分支保留重试入口与密钥清理引用。清空仅在替换工作库中暂时移除并原样恢复数据库触发器，不弱化正常运行的不可变事件规则。旧升级材料接纳跳过可重建缓存，避免启动缓存变化被误判为丢档。

## 实现入口

- [save_safety.py](../../services/core/src/livingworld/infrastructure/save_safety.py)：独立SQLite快照、七日/升级保留、资产/配置、完整性及稳定ID/内容核对、ZIP导入导出、恢复事务、无正文财务回执保留和旧任务隔离。
- [save_safety.rs](../../apps/desktop/src-tauri/src/save_safety.rs)：本机Core工具监督、维护屏障、实际文件身份交叉核对、原生文件选择器、30分钟自动备份、用户确认恢复及清空。
- [SaveBackups.tsx](../../apps/web/src/SaveBackups.tsx)：书架/设置与启动保护界面；沿现有视觉组件，不替换主布局。
- [updater.rs](../../apps/desktop/src-tauri/src/updater.rs)：签名完整包修复路径、独立升级快照、旧handoff接纳、业务开放前核对与持久完成标记、未完成升级回退入口。未知旧程序不清理；新版已开放使用后禁止自动数据回退。
- [CLI](../../services/core/src/livingworld/bootstrap/cli.py)/[HTTP](../../services/core/src/livingworld/adapters/http/app.py)：启动保护先于迁移及模型初始化，迁移前备份；受认证`/system/storage`只返回身份/计数/摘要，更新待核对期间持久阻止业务和后台准入。
- [安装模板](../../apps/desktop/src-tauri/installer-template.nsi)/[hooks](../../apps/desktop/src-tauri/installer-hooks.nsh)/[备份脚本](../../apps/desktop/src-tauri/installer-save-backup.ps1)：固定Tauri官方MIT模板，移除清除应用数据分支，在旧卸载器与新文件替换前备份；不执行安装器。
- [回退脚本](../../apps/desktop/src-tauri/rollback-update.ps1)：只处理经核对清单里的匹配旧程序与完整停机数据，保留当前文件，等待应用退出，不终止未知程序。

## 证据与限制

截至2026-10-15，已完成ESLint/TypeScript、Ruff、Rust`cargo check --locked`、6个Python源码AST、两份PowerShell脚本解析和Git差异检查；文档链接1094个本地目标无断链，发布隐私扫描909个当前文件无已知特征发现，不读取app-data或模型。最终直接EXE通过`build:desktop`（`--debug --no-bundle`）必要编译，位于既有`apps/desktop/src-tauri/target/debug/dreamtalk-desktop.exe`，文件版本0.1.78、30,784,512字节，未启动。最后的安装备份脚本容量保护改动已单独通过解析，不属于本次直接EXE的嵌入内容。

编译有既有Vite大于500kB的chunk提示及Tauri `STATIC_VCRUNTIME`弃用提示；没有通过关闭警告冒充无风险。此轮不因备份功能扩大重构前端渲染或打包方式。

Python检查进程提示无法定位`D:\python\python.exe`，随后实际检查完成、退出码0；未把该环境提示当作数据故障的根因。Git差异检查只有既有CRLF/LF转换提示，无空白错误。

尚未执行：自动化测试、浏览器/桌面smoke、临时/真实存档备份恢复测试、模型调用、NSIS打包/安装、跨版升级和回滚运行。用户负责这些验收；源码接线与编译通过不代表数据保护已在所有故障场景成立。

NSIS安装不是原子系统事务；锁文件、磁盘故障和安全软件仍可能阻止回退。未确认成功则保留材料并报告未完成。旧程序无可信清单时只保护数据/修复安装，不尝试自动恢复未知旧程序。云同步、世界分支、密码加密导出及全自动无交互安装不在本轮范围。

当前源码改动未提交/推送。源码、公开下载0.1.77、已编译的直接EXE和用户正在运行的版本应分别核对；不更改现有安装入口或自启动。先从托盘完全退出旧程序，再由用户启动直接EXE体验。卸载模板改动只有未来获准构建/发布的新安装包才交付，不能替换已经分发的旧卸载器。

批准方案：[存档保护](../proposals/2026-10-14-save-safety.md)；复用来源/许可：[调查](../research/2026-10-14-save-safety.md)；用户手册：[数据与备份](../DATA_BACKUPS.md)。
