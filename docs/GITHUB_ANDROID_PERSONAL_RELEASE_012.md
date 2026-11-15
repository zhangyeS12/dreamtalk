# 安卓个人测试发布记录

本轮用户明确要求发布新版本供手机验证，并在中断后要求继续。当前版本、下载及验收状态统一见 [状态清单](PROJECT_STATUS.md)。

发布标识 android-v0.1.2-personal.1，Release ID 437491556，prerelease、非 Latest。独立安卓目录构建并沿用原证书；四项附件为 APK、SHA-256、指南与回执。草稿逐项核对远端大小及摘要后发布，再以不带认证的请求完整下载 APK，HTTP 200，77144793 字节，摘要 `3fe6046c05478b934188506564c5a402233045e60c440a7630770e7a30bccd9a`，与本地签名包一致。

Windows 发布内容和六项附件、update-preview 与 windows.json 原始字节、Latest、main 和本地 Git 状态／差异摘要，发布前后全部一致。未改动 Windows 源码和文档，没有 Android 源码提交、main 推送或 Windows 通道写入。

本轮构建脚本不含隐式应用运行；没有运行 APK、用户安装程序、真实 API 或真实存档。已签名载荷与离线检查不能替代 vivo X80／OriginOS 6 验收。源码仍在独立工作区，GitHub 标签自动源码档案是仓库基准，不能当作此 APK 的 Android 工程或 Android CI。

恢复了上次因自动审批额度不足而未执行的打包命令；本次审批通过后正常构建。网络读取偶发 EOF，仅切换只读核对的 HTTP 实现；上传完整保留，没有覆盖或重复发布。最终独立公开 API／curl 校验完成全部隔离核对。

本轮证据位于 artifacts/github-android-personal-012：windows-before.json、windows-after.json、isolation-verification.json、asset-manifest.json、source-manifest.json、feature-payload-verification.json、draft-verified.json、published-release.json、anonymous-download-verification.json、completed.json。实际构建与载荷回执见状态清单链接。
