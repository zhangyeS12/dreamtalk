# 本地旧版本与构建文件清理

日期：2026-10-08；源码基线`85f8035`，Desktop0.1.43未提交工作区。用户要求“把无效文件去掉，只保留最新版”，并另行批准将唯一dreamtalk登录启动项从locations-0141更新到正在使用的world-models-0143，保留`--background`。

## 已完成

- 本地便携目录只保留`artifacts/portable/world-models-0143`的完整0.1.43程序及ZIP，删除61套旧便携目录、旧根ZIP、重复Release副本及历史打包中间文件。GitHub公开Release未删除或改动。
- 清理桌面Rust target、Web dist／Tauri gen、uv缓存、旧打包缓存及旧工作副本依赖／构建产物。正式仓库的`.venv`、`node_modules`、本地检索模型、导入示例与必要请求上界工具保留；下次构建会重新生成缓存。
- D盘284个清理目标约36.448GiB，C盘727个清理目标约21.845GiB；合计58.293GiB为文件逻辑大小，不等同实际磁盘释放量。
- 旧工作副本可读源码与Git历史在删除前压缩、逐文件SHA-256核对并完成ZIP完整性核对：`artifacts/cleanup-preserved-source-20261008.zip`，13255个文件，约36.84MiB。这份保护归档不包含可运行旧包、旧依赖或用户存档。正式源码清理前后765个文件哈希一致；随后只更新本清理说明和当前文档入口。
- 最新桌面及Core EXE哈希保持；app-data、密钥、世界数据库、用户导入资料保持。旧工作目录中本地数据、数据库、外部联结及根Git元数据独立保护，不按垃圾处理。
- 自启动条目已实际读回为`D:\LivingWorld\artifacts\portable\world-models-0143\dreamtalk\dreamtalk-desktop.exe --background`；不修改其他启动项，不关闭应用或调用模型。

具体删除清单与保留项见`artifacts/cleanup-20261008-*.json`。Windows权限受限的62处历史测试目录已处理，最终逐路径核对无残留；其中管理员直接ACL方法有20处删除回执，额外可计量约0.806GiB，其余已在前序处理中消失，不补猜其大小。原生权限工具超时后改用直接ACL方式，限定原清单和旧工作根，拒绝联结遍历；最终核对本轮辅助进程均已退出。

随后移除9处指向已删除旧源码的失效联结（仅删联结）、22个空目录和17个源码字节码缓存。旧C盘工作目录只保留根`.git`、`.smoke-appdata`、`.product-work/.local-appdata`及`.c003b-probe/runtime.sqlite3`，这些数据／元数据没有读取内容或删除。正式仓库开发依赖保持。

清理前后C／D盘可用空间合计增加约56.7GiB；这是两次磁盘快照的近似差值，会受其他程序写入影响。最新版253个Core源码仍与工作区一致，两个程序哈希保持；最终仅同步帮助文档并重压0.1.43 ZIP，没有重建或启动程序。文档链接与最终ZIP校验、唯一便携目录和启动指向见`artifacts/cleanup-20261008-final.json`及`artifacts/world-models-0143-build.json`。

## 边界

本轮没有运行自动化测试、应用smoke、真实模型或迁移；只做文件／Git／版本／哈希核对。源码未提交／推送，当前公开下载仍v0.1.42。本地新入口保持[0.1.43交付记录](2026-10-08-world-model-config.md)所列位置。历史维护记录中“保留旧包”是当时事实，现由本轮用户决定替代。
