# 2026-10-15 · 0.1.78升级启动阻断与0.1.79源码修复

本页记录第一阶段0.1.79直接EXE交付。后续快照副文件误报、简化及0.1.80发布授权见[接续记录](2026-10-15-save-snapshot-update.md)；以下未发布／未授权陈述仅对应当时阶段。

基线1a29877，公开发行v0.1.78固定e4b7164。用户升级后停在存档保护页，随后允许仅检查本次启动的错误标记、升级与备份元数据、程序路径／版本及Core日志阶段与固定错误码；未授权打开数据库或恢复／修改真实数据。该次只读诊断已完成，本轮不扩大为存档操作许可。用户询问下一步后，继续已确认故障的源码修复与必要编译。

## 已确认原因

实际启动日志记录 `migration / alembic_schema_shape_mismatch`，宿主随后登记 `save_update_start_failed`，没有完成升级验收。升级前备份元数据已存在且有完整标记；这些元数据不证明全部正文、素材或恢复运行已经核验。

0050迁移在表尾添加`added_at_utc`，0052随后在表尾添加`description`；`StickerEntryRecord`却把`description`声明在`added_at_utc`前。`migration.py`按完整有序列定义严格比较，因此合法迁移结果被拒绝。修复仅调整模型声明到相同追加顺序，保留类型、可空性、键、索引、约束和既有迁移文件，不通过放宽校验或手工改版本号掩盖错误。

源码中SQLite连接显式BEGIN，Alembic启用transactional_ddl，升级与最终形状核验位于同一engine事务；异常走回滚。此次没有打开实际数据库验证回滚结果，不能把源码事务设计说成真实存档已通过完整性验收。

## 源码修复与入口

- Desktop源码0.1.79、API1、0052、配音revision8。原标识、app-data位置、备份和原更新公钥保持，未增加依赖。
- 存档保护页区分升级未完成和需要恢复备份；存在可读当前库元数据、合法失败标记及可信本项目handoff时，提供“重新检查并启动”。不会在启动或轮询时自动点击、恢复或重试。
- 仅用户点击后，桌面宿主持有原操作锁、排空并停止已有Core；保留原数据、失败标记、旧程序／存档检查点。在同主次版本的相同或后续正式补丁中接续未完成升级；拒绝降级、跨发行线及还原中／待确认状态。
- 受控桌面bootstrap增加默认false的严格布尔字段`retry_update_verification`。该次启动只暂时越过旧升级失败标记，其他存档保护检查保持；Core仍持有启动维护屏障。失败标记不提前删除，即使过程退出仍有保护记录。
- 强制重新核对真实Core文件身份、稳定记录、内容、素材和配置，不复用旧“已核对”回执跳过。通过后才开放维护屏障并清除升级失败标记；失败停止Core并保留保护页。没有恢复／替换存档，不重发旧聊天、配音或后台模型任务。
- 入口：`SaveBackups.tsx` → `retry_save_start` → `save_safety.rs`／`updater.rs` → 受控bootstrap／`guard` → 现有完整连续性核对。字段顺序修复在`persistence/media_models.py`，严格校验仍在`persistence/migration.py`。

## 检查与交付边界

ESLint／TypeScript、4份修改Python的Ruff lint／格式、Rust格式及`cargo check --locked`通过。离线编译模型列定义显示`active`、`added_at_utc`、`description`顺序与0050／0052追加相同，没有连接数据库。`npm run build:desktop`（debug／no-bundle／custom-protocol）成功，直接EXE位于`apps/desktop/src-tauri/target/debug/dreamtalk-desktop.exe`，产品版本0.1.79、30,879,232字节，未启动；该目录没有旧打包Core，直接EXE按既有debug路径使用本仓库Core源码。

编译保留既有前端大于500kB分包提示及Tauri STATIC_VCRUNTIME弃用提示，没有消除或隐去。未新增或运行自动测试、浏览器／桌面smoke、应用、模型、临时或真实存档迁移，不运行恢复或修改系统入口。

收尾文档链接核对1117个本地目标、0失效，外链仅计数；发布隐私静态门禁916文件、0已知特征命中，不访问app-data或模型。Git差异格式通过，保留现有CRLF／LF转换提示。

本轮没有新的GitHub推送／发布或打包许可。仅允许必要`build:desktop`（debug／no-bundle／custom-protocol）交付既有形式的直接EXE；不生成安装器、便携包或ZIP，不覆盖已发布0.1.78资产／标签。当前工作区改动未提交、未推送，用户实际使用与升级仍待验收。

用户体验时先从托盘完全退出旧版，再启动修正版直接EXE；若保护页仍在，点击“重新检查并启动”。先核对书架与消息是否恢复可用，再决定是否需要从备份恢复；该按钮的完整流程尚未由工程端运行。
