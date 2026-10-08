# 0.1.46 Windows应用更新实现

日期2026-10-08，正式仓库D:\LivingWorld，分支codex/world-archive，起始HEAD85f8035；继承0.1.43～0.1.45未提交改动。用户批准实现并另明确批准DPAPI发布密钥保管及恢复导出工具。本轮不提交／推送／发布，不启动程序／安装器，不读取真实存档，不修改当前注册／快捷方式。

## 实现

- `DesktopUpdates.tsx`贯穿书架／世界，启动异步检查，真实就绪＋前台可见才提示；稍后本次、全局不再弹窗仍检查，高亮入口及关于页手动检查。原生dialog、焦点／Escape、纯文本更新说明；当前编辑与请求会阻止安装。
- Rust `updater.rs`精确封装官方updater2.13.1，仅项目GitHub HTTPS Release安装器；更高版本、签名验证、512MiB／10分钟下载边界、单次操作与100ms进度节流。官方插件负责检查／下载／签名，宿主管理缓存并派发标准NSIS，避免插件直接process::exit和未管理临时EXE。
- Core `UpdateMaintenance`与完整ASGI请求生命周期、Director／动态／在线与离线任务接线。关闭新准入、同步任务登记、三分钟等待，租约五分钟；已接纳任务完成，取消或租约到期唤醒原调度器，无新模型调用或重放。`stop_for_update`禁止强杀，仅确认Core正常退出后备份。
- 数据／配置／旧程序同一停机快照；新版真实Core及书架就绪才修复官方入口、清理已确认旧程序和本次安装缓存。旧包文件清单／摘要／根目录与符号链接核对；原位置覆盖时仅清除不再存在的新版本文件。最近数据恢复快照保留，失败显示未完成并保留恢复材料。
- 完整Desktop／Core／模型资产／文档／许可证NSIS，currentUser稳定安装目录；保留autostart启用状态及--background，桌面官方入口修复，更新后前台启动。旧42～45手动迁入；不扫描未知复制件。便携46提供可核对清单。
- 发布公钥入配置；私钥DPAPI保护在Git忽略artifacts/signing，生成输出抑制、临时明文删除；提供PowerShell7交互密码加密导出／换机导入。未执行导出／导入验收。

## 当前证据

- ESLint／TypeScript、相关Core与打包源码Ruff检查／格式、Rust `cargo fmt`／`cargo check --locked --lib`、PowerShell发布脚本AST解析通过。五处Desktop版本均0.1.46，便携EXE文件／产品版本均0.1.46。构建脚本使用`--build-only`，没有运行应用、安装器或测试。
- 完整Core／Web／Desktop与NSIS构建退出0；日志`artifacts/updates-0146-complete-build.log`，签名安装器`artifacts/installers/updates-0146/dreamtalk_0.1.46_x64-setup.exe`，110,660,585字节，SHA256 `8c7dec65fe4d7b4dd2253162b056e3d5d0b8154555ffa3323943d5eb4f9c37ff`。同目录包含`.exe.sig`、`windows.json`、更新说明及4项SHA256SUMS，摘要与清单签名字段核对一致。这是生成签名及静态产物核对，不是客户端真实升级验收。
- 完整便携目录`artifacts/portable/updates-0146/dreamtalk`，ZIP `artifacts/portable/updates-0146/dreamtalk.zip`，145,933,538字节，SHA256 `1b761aae656bf172cd6b1364fb75a61da6fabd9b81fe17b9e06b5a0e8777fa22`。1,224个程序清单文件逐项摘要一致，ZIP含1,225项；258个打包Core Python源文件与当前源码一致，无发布私钥／signing目录。Desktop SHA256 `6b9e201b6da843a30ce8980f2ced5839add5f686d50bf805f867794851280d1b`；Core SHA256 `9d7e2e53fb88aae05e95fe75942a819ce3a78e59c594be9be3cca48a774a3cae`。静态记录在`artifacts/updates-0146-evidence.json`。
- 构建时包内文档600个本地目标、0断链；最终源码文档956个本地目标、0断链；外部URL仅计数，未探测。Git差异格式通过。随包文档是构建时快照，本节最终产物证据及少量当前状态文字在构建后补录，不把包内记录冒称最终仓库快照。
- 现有构建警告保留：Vite三处chunk超过500kB、STATIC_VCRUNTIME弃用；PyInstaller可选tzdata／pysqlite2／MySQLdb hidden import缺失。Python启动还有定位提示但相关源码检查退出0；没有因此推定运行时表现。
- 本轮两次中间产物在确认绝对路径、无目录联接且未被运行后清理；保护发布密钥和前序0.1.43～45入口。实际HEAD仍85f8035，本轮及继承改动未提交／推送／发布。

## 发布与验收

最新公开仍v0.1.42，update-preview频道未创建／上传；本地公钥配置不等于线上更新可用。本轮未启动应用、未安装／升级、未执行数据库迁移／provider／自动化测试。用户需验收新版本提示／静音、草稿门禁、任务排空、跨版本安装、恢复、快捷方式／自启动／清理和密钥恢复。共同联系继续用户等待，其他验收不扩大。

[使用与发布说明](../WINDOWS_UPDATES.md)、[批准方案](../proposals/2026-10-08-desktop-updates.md)、[成熟实现调查](../research/2026-10-08-desktop-updates.md)。
