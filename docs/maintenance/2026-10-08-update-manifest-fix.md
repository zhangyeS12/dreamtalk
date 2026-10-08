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
