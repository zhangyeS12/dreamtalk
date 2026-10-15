# 存档保护与更新实现调查

调查日期：2026-10-14。继续既有Tauri、Python Core、SQLite与Alembic，不新增运行框架或依赖。

| 来源 | 版本/许可 | 本轮复用与理由 |
| --- | --- | --- |
| [SQLite backup API](https://www.sqlite.org/backup.html)、[WAL说明](https://www.sqlite.org/wal.html) | 随既有Python运行时；SQLite公有领域 | 逻辑备份包含已提交WAL，避免复制一个仍在写入的主库漏掉数据；仅在既有维护屏障或停机后成套复制素材。 |
| [Tauri updater](https://v2.tauri.app/plugin/updater/) | 项目固定tauri-plugin-updater 2.13.1，MIT/Apache-2.0 | 继续HTTPS下载、签名验证及NSIS passive模式；旧清单用于可信清理，不作为新签名包下载的绝对前提。 |
| [Tauri CLI 2.11.4 NSIS模板](https://github.com/tauri-apps/tauri/blob/tauri-cli-v2.11.4/crates/tauri-bundler/src/bundle/windows/nsis/installer.nsi) | 本轮选择MIT授权，见[许可全文](../licenses/tauri-installer-MIT.txt) | 固定官方模板，仅移除清除应用数据的UI/删除分支，并在旧卸载器及程序替换前执行受控备份。单用安装hooks不能移除官方生成的删除选项，因此采用受支持的模板定制。 |
| Python sqlite3/zipfile/shutil、现有Tauri文件选择器 | 标准库及既有tauri-plugin-dialog 2.8.1 | 不新增压缩/数据库依赖；使用本机选择器，JS不能传入任意恢复路径；备份文件限制路径、大小、文件数、链接和完整性。 |

没有复制其他聊天产品的源码。Windows卷快照只是历史故障恢复的备用来源，不作为应用的日常备份保障。备份与恢复在产品自己的真实进程上下文执行，并通过Core返回的实际数据库文件身份交叉核对，避免把工具环境的映射副本误作正在使用的库。
