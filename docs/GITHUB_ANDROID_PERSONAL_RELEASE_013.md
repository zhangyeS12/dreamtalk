# 安卓个人测试发行记录

当前版本、检查与用户验收统一见[状态清单](PROJECT_STATUS.md)。

用户本轮明确要求发布新版本。已发布个人预发布 [android-v0.1.3-personal.1](https://github.com/zhangyeS12/dreamtalk/releases/tag/android-v0.1.3-personal.1)，Release ID 438104002，非 Latest，4 个附件。独立分支 codex/android-personal-0.1.3，实际源码提交 0b10cd983cb5a123e2d9146171cfe728c0ab8f57；没有改写 Windows 历史或推送 main。

[构建前精确提交 CI](https://github.com/zhangyeS12/dreamtalk/actions/runs/42459426953) 已通过；[标签重复 CI](https://github.com/zhangyeS12/dreamtalk/actions/runs/42460201063) 的一项前端时序断言失败，按用户新指令不重跑。首轮 CI 缺少 Core 包元数据，补齐环境与失败输出后完整通过，未弱化断言或跳过用例。构建使用带标记的安卓缓存，交付产物仍在安卓目录。

APK 为 77161177 字节，SHA-256 5f5fe28b6cb87f1154b049c9c2af4a20855c3f4846cc773c63892e2ca1c6c91c；原证书 SHA-256 61bf42386884a6c001e14af9b75e297a59e255c4061195ec6e23cbe68c02c598。v1／v2／v3、16KB 对齐、397 模块源码对应及载荷隐私通过；Tauri 只调整两个生成配置的换行，已核对无语义差异并恢复冻结字节。

[资产](../artifacts/github-android-personal-013/asset-manifest.json)、[源码](../artifacts/github-android-personal-013/source-commit.json)、[标签核对](../artifacts/github-android-personal-013/tag-ci-verification.json)、[载荷](../artifacts/github-android-personal-013/feature-payload-verification.json)、[匿名下载](../artifacts/github-android-personal-013/anonymous-download-verification.json)、[Windows 隔离](../artifacts/github-android-personal-013/isolation-verification.json)和[完成回执](../artifacts/github-android-personal-013/completed.json)保留逐项证据。

未运行生产 APK、已安装应用、真实模型或真实存档。vivo 证书提示根因未确认，新包安装及真实聊天／后台通知仍待手机验收。
