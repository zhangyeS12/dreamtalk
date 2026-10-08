# Windows 应用更新

0.1.46起提供更新入口与完整安装包；当前[v0.1.47](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.47)完整签名安装器及便携版、[update-preview频道](https://github.com/zhangyeS12/dreamtalk/releases/tag/update-preview)已公开。0.1.46可从启动提示或手动入口发现0.1.47，真实跨版更新仍由用户验收。

## 使用

启动异步检查GitHub预发布频道；新版本在前台书架准备好后提示修复和改进。稍后仅本次运行不再自动弹窗。“不再自动弹窗”保存在本机所有世界共用的偏好中，后续仍检查，书架“世界档案库”右侧出现高亮“新更新”。点击该入口或世界内“设置 → 关于与诊断 → 检查应用更新”可手动打开，取消勾选恢复提醒。

点击更新前保存角色卡、世界书、封面、模型、身份、地点等编辑与聊天草稿。点击后下载并校验签名，等待当前任务完成，正常关闭Core，保留恢复备份，启动完整安装器并前台重启。下载失败或等待超时不会替换当前版本；备份／安装派发失败会尝试重启旧Core，点击“重新连接”恢复界面。更新不新增模型调用，也不自动恢复旧失败任务。

安装位置使用Tauri当前用户固定目录（默认`%LOCALAPPDATA%\dreamtalk`，以后沿注册安装目录升级）。安装器提供桌面／开始菜单入口；只修复官方dreamtalk已启用的自启动，保留`--background`，原来关闭的仍关闭。成功启动后删除清单内旧程序与临时程序恢复副本，保留最近数据快照。不会删除用户世界、消息、卡、封面或凭据，不扫描其他便携目录或下载ZIP。

**旧版首次迁入：** 0.1.42～0.1.45需要先从托盘彻底退出，再手动运行完整新版安装器，使用新桌面入口。旧便携包没有可信文件清单，首次安装不会擅自删除其目录；确认新版体验后可清理旧包。0.1.46便携版附带清单，可在以后应用内升级时迁入安装目录并清理本次源包。

## 恢复与限制

更新准备只持续本次Core世代，五分钟租约超时恢复准入。关闭普通前台不等于终止正在安装的系统安装器。Windows NSIS不是原子事务，磁盘／权限／安全软件造成的安装失败可能需要手动重跑安装器。

原应用数据目录仍`app.livingworld.desktop`。更新恢复材料位于其`updates/recovery/<随机ID>/`，数据及配置与程序来自同一停机时点；`updates/handoff.json`记录本次版本／入口迁移。新版未能真实就绪时不清除恢复程序。恢复必须成套处理，先退出应用并保存当前数据副本，再由用户明确决定恢复；不要只把旧EXE覆盖回来打开新版数据库。该目录不提供自动世界分支或无条件数据库降级。

新版能运行而旧文件／快捷方式处理失败时，更新窗口显示未全部处理，保留handoff以便重启重试；不假称“无残留”。源包文件被修改、符号链接／目录联接、非清单文件不会被当成可安全删除对象。用户另存的ZIP不属于本次清理。

签名使用Tauri updater公钥校验；这是更新包完整性签名，**不是Windows发布者证书**，首次安装仍可能出现未知发布者／SmartScreen。仅支持Windows x64完整安装包，macOS／Linux未交付。

## 维护者构建与密钥

本机PowerShell7，已批准私钥存于`artifacts/signing/updater.key.dpapi`，Windows当前用户绑定。不得提交该目录或把私钥写进发布说明／日志。

```powershell
# 已初始化后构建；不启动产物、不运行测试、不发布
pwsh -File scripts/updater-signing.ps1 -Mode Build -OutputName deletions-0147

# 用户自行选择仓库外的备份位置，交互输入至少12字符密码
pwsh -File scripts/updater-signing.ps1 -Mode Export -RecoveryFile E:\Backup\dreamtalk-updater-recovery.json

# 换机后同一公钥源码中恢复，交互输入上述密码
pwsh -File scripts/updater-signing.ps1 -Mode Import -RecoveryFile E:\Backup\dreamtalk-updater-recovery.json
```

导出采用PBKDF2-SHA256／600000轮及AES-256-GCM；恢复时校验公钥一致。未执行导出／导入验收。不要重新生成公钥替换已经交付客户端的信任根；遗失私钥和恢复备份后旧客户端无法信任新签名，须重新手动安装。

构建产物在`artifacts/installers/<名称>/`：完整`dreamtalk_<version>_x64-setup.exe`、`.exe.sig`、`windows.json`、更新说明与SHA256SUMS。构建使用已有Core／Web／Desktop链路，所有检查为build-only。

## 发布流程

只有获得对应版本GitHub发布授权后执行。本次用户已明确授权，v0.1.47和固定频道已发布，见[记录](maintenance/2026-10-08-authored-deletion.md)。

1. 编译签名完整包，更新`docs/releases/v<version>.md`中的用户可读说明，检查产物清单和SHA256。
2. 创建版本Release（如`v0.1.47`，当前仍预发布），上传安装器、`.sig`、便携ZIP、SHA256SUMS及说明。
3. 版本资产上传成功后，将该版本`windows.json`上传／替换到固定`update-preview` Release，文件名必须`windows.json`。首次需创建此频道Release；它承载当前预发布清单。
4. 频道内容使用更高SemVer、对应完整安装器URL及签名。仅提交源码、仅发布便携包或只创建版本Release都不够。
5. 用户验收跨版本下载／校验／等待任务／安装／Core重启／系统入口／旧文件回收。工程端不把产物存在当作这条链已验收。

实现：[成熟方案调查](research/2026-10-08-desktop-updates.md)、[批准范围](proposals/2026-10-08-desktop-updates.md)、[本轮记录](maintenance/2026-10-08-desktop-updates.md)。
