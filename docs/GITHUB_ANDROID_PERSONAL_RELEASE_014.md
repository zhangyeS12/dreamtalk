# 安卓启动修复发行记录

当前版本与验收以[状态清单](PROJECT_STATUS.md)为准。

用户本轮明确要求“快速发布”，此前明确要求未主动要求时不走 CI。已发布个人预发布 [android-v0.1.4-personal.1](https://github.com/zhangyeS12/dreamtalk/releases/tag/android-v0.1.4-personal.1)，Release ID 438123078，非 Latest。实际源码提交 a0778010af9098fca0ad4cc0760980c30ac0edf7，位于独立修复分支，没有推送 Windows main。

本轮通过单次显式 SkipCI 和版本匹配的用户授权回执跳过 CI，不修改共享工作流或默认门禁，不主动查询或等待服务器自动检查。修复代码此前的 33 项宿主及 6 项前端回归、类型、格式和 Kotlin 编译通过，本轮完成必要编译及包核对。

APK 为 77165273 字节，SHA-256 16a160be1eb108f675994133f1947c9e202b88af7351af9f42469f299dbc84da；沿用原证书。v1／v2／v3、16KB 对齐、397 模块源码对应、Logo 和启动依赖通过。四个附件均完成远端与匿名完整下载核对，Windows 发布和频道不变。

[源码](../artifacts/github-android-personal-014/source-commit.json)、[授权](../artifacts/github-android-personal-014/release-authorization.json)、[资产](../artifacts/github-android-personal-014/asset-manifest.json)、[载荷](../artifacts/github-android-personal-014/feature-payload-verification.json)、[匿名下载](../artifacts/github-android-personal-014/anonymous-download-verification.json)、[隔离](../artifacts/github-android-personal-014/isolation-verification.json)及[完成回执](../artifacts/github-android-personal-014/completed.json)保留证据。

未运行真实 APK、模型或存档；vivo X80 完整启动和实际 API／后台体验仍待手机验收。
