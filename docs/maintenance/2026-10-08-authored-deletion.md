# 2026-10-08 · Desktop 0.1.47 删除入口与发布

起始正式仓库 D:\LivingWorld，分支 codex/world-archive，HEAD 85f8035。用户明确要求检查并补齐删除按钮，完成后直接上传 GitHub，以验收更新流程。本轮包含此前尚未发布的 0.1.43～0.1.46 授权改动；更新版本提升为 0.1.47。

## 已实现

- 角色资料底部和“添加／编辑角色卡 → 当前世界已保存”均有删除按钮，提交前说明影响。最新角色卡停用，阵营和头像绑定移除；旧修订不复活。历史私聊及含该角色的固定群聊保留只读，重新导入是新身份。
- 活动目录、阵营图、地点图、日常计划及主动联系过滤已删除角色；地点和角色容量按仍参与的作者内容计数。正在生成的会话阻止删除，消息／回复 claim 与删除共用串行 writer 核验，避免删除与付费派发竞态。
- 已删除角色所在会话的未回复主动联系不再阻挡后续联系。这是显式删除所造成的会话关闭，不写假回复；其余会话的未回复门禁不变。删除不触发模型调用。
- 编辑地点提供“删除此地点”。有子地点、活跃角色初始／当前地点或玩家当前位置时拒绝并解释；“家”不可删除。移除目录仍保留 canonical 地点与历史事实，同名可重新创建成新地点。
- 阵营原有空阵营删除政策保持；按钮明确为“删除阵营”，旁边解释需先移除成员／子阵营。
- Alembic 0040 追加 world_content_imports／local_location_catalog 的 removed_at，0039 移动字段保留。没有运行真实迁移。

## 接线与检查

UI 为 WorldContent／ContactSocial／LocationWorkspace，API client 删除方法接到 world_content 与 world_locations DELETE；持久层 authored_lifecycle 统一停用身份核验。聊天保存、claim、恢复、Director、相遇／共同休闲与主动联系沿原权限和预算边界。成熟来源见[调查](../research/2026-10-08-authored-deletion.md)。

ESLint／TypeScript、Python Ruff／修改文件格式、Rust 格式、Git 差异空白检查已通过；源码文档958个本地目标／0断链。GitHub为公开仓库，远程两分支与基线一致；私钥与产物由Git忽略，发布内容的有界文件名／私钥样式核对无匹配（不称完整安全审计）。完整构建与公开上传结果如下。仅允许源码／格式／编译／打包核对，没有新增或运行自动化测试，没有启动应用／安装器、读取真实存档或调用模型。旧 0.1.43 系统入口不在工程端修改。

## 待用户验收

删除按钮、旧修订不复活、历史只读、非空阵营提示、占用地点保护，以及 0.1.46 → 0.1.47 的更新提示／静音／下载／安装／重启／系统入口／旧文件清理。无更新器的旧版本须一次手动安装，更新签名不是 Windows 发布者证书。共同联系仍按原决定等待用户。

首次build-only因本轮版本替换误改num-iter锁定版本而失败，未生成交付包；已按原锁文件恢复为0.1.46，num-integer核对确认仍为原0.1.47。随后构建退出0。失败与后续成功分别记录。

## 构建与公开发布结果

- 107个源码／文档文件发布提交dbb506a，锁文件修正后应用提交／v0.1.47标签为`580cdf5c4c2f23f99fca2520d7f36e8024dd2441`。main和codex/world-archive普通快进推送；使用`[skip ci]`保留既有测试／工作流，不宣称CI通过。
- `pwsh -File scripts/updater-signing.ps1 -Mode Build -OutputName deletions-0147`的第二次build-only退出0；日志为artifacts/deletions-0147-build-retry.log。未运行应用、Core、安装器、测试套件或模型。
- 包内260个Core Python源码逐文件与构建源码一致；便携清单1229个文件，ZIP1230项。包内文档602个本地目标／0断链；EXE产品／文件版本均0.1.47，签名文本与清单相同且公钥ID一致（非运行签名验收）。文件名匹配无个人数据库／凭据，不称完整安全审计。
- 保留Vite三个大于500kB分块、STATIC_VCRUNTIME弃用及PyInstaller可选tzdata／pysqlite2／MySQLdb告警；Python环境路径诊断不影响后续退出码，不隐去这些限制。
- [v0.1.47](https://github.com/zhangyeS12/dreamtalk/releases/tag/v0.1.47)为公开预发布，Release ID 406833526，发布时间2026-10-08T13:04:24Z；[固定频道](https://github.com/zhangyeS12/dreamtalk/releases/tag/update-preview)ID 406836982，windows.json声明0.1.47及对应完整安装器。先完成版本资产再公开频道。历史v0.1.42保持。
- GitHub所有附件uploaded，服务器大小／SHA-256与本地一致；不带凭据完整下载安装器和便携ZIP核对一致，固定频道清单与本地完全相同。核对时间2026-10-08T13:07:47.538559+00:00。证据在artifacts/release-0147的package-audit／upload-audit／public-audit.json（ignored）。

| 附件 | 字节 | SHA-256 |
| --- | --- | --- |
| dreamtalk_0.1.47_x64-setup.exe | 110669887 | `319b080d37a4d621331473c1cd37728846a97c1c400e1d013b1a3941cec91448` |
| dreamtalk_0.1.47_x64-setup.exe.sig | 420 | `72e07a77548b42b2aa01f07d442297b07480b59d1df4bc7bc50611b86b63105c` |
| dreamtalk-0.1.47-windows-x64.zip | 145955124 | `51cd3541f0e10850774c2a83c160527ecca9f37e426c9bb5786f63d25c2929ca` |
| windows.json | 1670 | `7292c2341a8d3389abba1e9fcf1fa4d044ff510331c150055ee49b43bb9b0b8a` |

包内帮助文档是构建时的发布准备快照，SOURCE_REVISION.txt固定580cdf5；构建后仓库发布记录有后续更新，不把包内快照称为最新仓库文档。没有重打包或移动已公开标签。工程端未修改真实存档、自启动、桌面快捷方式或现有安装；0.1.46→0.1.47升级与清理由用户明确点击更新后验收。
