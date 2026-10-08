# 2026-10-08 · Desktop 0.1.48 安装包清单修复

正式仓库 D:\LivingWorld，起始 HEAD 9230a0b，分支 codex/world-archive。用户反馈 0.1.46 → 0.1.47 出现“程序文件与交付清单不符”，只读定位后明确要求“修改”；本轮是此前已授权删除及更新发布的故障修复，准备交付 0.1.48 完整签名安装包、便携包及固定频道。

## 确认的原因

运行入口 D:\dreamtalk\dreamtalk-desktop.exe，版本0.1.46。交付清单1225项中只有主程序不匹配，其余1224项一致。只在内存中将NSIS安装类型标记还原后，主程序摘要与原清单完全一致；没有改写程序。

随后用官方7-Zip26.04直接读取两个原NSIS包，不执行安装器，确认安装器自带的主程序和清单本身就不一致：

| 版本 | 原清单主程序SHA256 | 实际安装主程序SHA256 |
| --- | --- | --- |
| 0.1.46 | `82a91b5ccbcdf140f0cb3a2411f4c3f3828b3fe67f25f403064cb0fd7dcc1da1` | `8048749083df361e86fab4f2958f95b407e832d810c2725180a7b6444be8c33c` |
| 0.1.47 | `b0bf02dfee0c55d160a0ddea08033e049109cf6da542ee65a4aaf51eb57a0ae4` | `9491f3dfb0ea6f616ca833ecff3b16cc4bccf38ddecd48bdd73881d97b2b6364` |

[tauri-cli2.11.4打包源码](https://github.com/tauri-apps/tauri/blob/tauri-cli-v2.11.4/crates/tauri-bundler/src/bundle.rs#L119)，MIT／Apache-2.0：生成NSIS前替换UNK为NSS标记，完成后恢复构建输出。旧脚本前后核对恢复后的文件，因而误以为主程序未变。便携目录和ZIP清单没有这项差异。原上传摘要／匿名下载一致的证据仍成立，但不能证明安装器内文件与清单一致；前序记录的检查范围据此明确。

## 修复范围

- [安装构建](../../scripts/build-installer.py)按已锁定Tauri行为计算实际NSIS主程序摘要。构建强制使用7-Zip只解压，不运行应用／安装器，逐项核对内含清单、主程序、Core及全部资源；不匹配立即停止，不形成可发布交付。结果写入ARCHIVE_VERIFICATION.json。
- [一次性修复工具](../../scripts/repair-update-manifest.ps1)仅支持上述两版的原安装清单：钉住完整清单SHA256及原／实际主程序SHA256，再核对每个程序文件。拒绝其他版本、内容变化、缺失文件、源码仓库、符号链接／目录联接或路径越界。默认只读；-Apply才原子替换清单。原清单备份也纳入新清单，由既有更新清理规则处理；再次运行只核对，不重复改写。
- 更新器运行时严格逐文件SHA256校验保持；不忽略主程序，不按版本泛化放行。原签名信任根、Core／数据库、模型费用和业务逻辑保持。本机修复只针对D:\dreamtalk的清单及清单备份，不运行安装器、不改主程序／存档／自启动／快捷方式。
- 构建阶段复用[官方7-Zip26.04](https://www.7-zip.org/download.html)（[许可](https://www.7-zip.org/license.txt)：LGPL／BSD及unRAR约束）作独立归档读取工具，仅存Git忽略诊断目录，不并入产品或增加运行时依赖。当前脚本需要ArchiveReader显式路径或PATH中的7z；未来Tauri变动须继续通过实际安装器静态核对。

## 检查与交付现场

修复工具PowerShell源码解析通过，已对D:\dreamtalk进行只读文件核对，1225项符合已知原包。PythonRuff／格式与AST、Git差异、文档链接及build-only结果在完成后补录。本轮不添加或运行自动测试，不运行应用／安装器／付费模型，不执行真实存档迁移。跨版本下载、排空、备份、安装、入口与清理仍由用户验收。


## build-only结果（发布前）

- 应用提交／v0.1.48标签`0f6a9d7836411ab0317383d834f122fb51b6ba80`，已正常快进推送main和codex/world-archive，保留既有CI／测试定义，提交用[skip ci]。
- `pwsh -NoProfile -File scripts/updater-signing.ps1 -Mode Build -OutputName updater-fix-0148 -ArchiveReader <官方7-Zip路径>`退出0。日志artifacts/updater-fix-0148-build.log，安装器及归档核对在artifacts/installers/updater-fix-0148；便携在artifacts/portable/updater-fix-0148。
- NSIS内含清单1232项全部匹配，包括实际主程序；结果ARCHIVE_VERIFICATION.json。便携清单1231项和ZIP1232项逐文件匹配，260个Core源码与本轮源码一致。EXE FileVersion／ProductVersion均0.1.48。签名文本／公钥ID格式核对符合，不代替实际更新插件验收。
- PythonRuff／格式、AST、两个PowerShell源码解析、依赖锁文件仅Desktop版本变更核对通过。仓库966个本地文档目标、随包609个目标均0断链；Git差异无格式错误。
- 既有非阻塞构建告警仍有大Web chunk、STATIC_VCRUNTIME弃用、PyInstaller可选hidden import缺少tzdata／pysqlite2／MySQLdb；未因此增加依赖，不宣称运行兼容验收。
- 未运行应用／安装器／自动测试／真实存档迁移或模型。包内文档是应用提交的发布准备快照，后续发布和本机修复证据另行记录，不重写历史包或移动版本标签。

| 文件 | 字节数 | SHA256 |
| --- | --- | --- |
| dreamtalk_0.1.48_x64-setup.exe | 110681156 | `d444f565a0a82c73e19e78776c97cf48190234a68f2477374560bd48e2b674ab` |
| dreamtalk-0.1.48-windows-x64.zip | 145959822 | `d7bc2eaab3b7c08185594ba813e2991c3f61bc65481e76c079306b793fae9fc7` |
| repair-update-manifest.ps1 | 6344 | `d3f69cf8b9cd3b94fe79482821f754061d992862d4f28eb9fd4a6b6f8a10b31b` |


## 本机旧清单修复现场

固定频道公开读取已确认0.1.48后才执行D:\dreamtalk清单修复。第一次-Apply因PowerShell把File.Replace的空备份路径绑定为空字符串而失败：旧清单未替换、原清单备份已创建、临时文件按finally清除，程序和存档未改。随后改为向File.Replace传入已核实的显式备份路径，原子保存原清单并替换清单；再次执行成功。

修复后版本仍0.1.46，含原清单备份共1226项逐文件SHA256一致，主程序仍为原安装器SHA256 `8048749083df361e86fab4f2958f95b407e832d810c2725180a7b6444be8c33c`。仅本轮两个清单文件变化，没有安装／启动／迁移／修改系统入口。证据artifacts/release-0148/local-repair.json。实际应用更新仍须关闭旧弹窗重新检查，目标确认为0.1.48，由用户点击及验收。

修复工具的PowerShell兼容修正属于独立辅助附件：后续源码提交和Release附件／SHA256SUMS将同步，不重打已核对的完整安装器／ZIP、不移动v0.1.48应用标签。先前匿名大文件下载证据仍对应同一安装器和ZIP；修正后的工具附件另行匿名核对。
