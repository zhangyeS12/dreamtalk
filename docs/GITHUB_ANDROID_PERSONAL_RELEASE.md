# 安卓个人测试预发布记录

本文件保留首轮安卓个人测试发布记录；当前交付与后续记录见 [状态清单](PROJECT_STATUS.md)。

日期：2026-11-07。用户明确授权将既有 Android 体验包发布到 GitHub，仅用于个人下载测试，并要求不影响 Windows。

[发布页](https://github.com/zhangyeS12/dreamtalk/releases/tag/android-v0.1.0-personal.1)，Release ID 437223044。发布为 prerelease、非 Latest，没有讨论帖、主分支推送或 Windows 附件变更。仓库公开，此预发布也公开可见；个人测试是用途标记，不是私有访问控制。

本轮只上传既有 APK、校验文件、体验指南和构建回执，共 4 项；没有进行新的发行构建、安装器打包、真实模型调用或 CI 跳过。标签以原 main 基准定位，仅用作下载标识；独立 Android 源码尚未同步至 GitHub，自动 Source code 档案不是本 APK 的 Android 工程。发布说明和回执已写明这一边界，不把 Windows 基准提交的 CI 当作 Android CI。

发布前递归 APK 检查 3440 项、82 个原生库 LOAD 对齐和 66 个迁移源文件，隐私无发现；标签基准提交的现有源码隐私门禁检查 1226 个文件，无发现。4 个 GitHub 附件的大小与 SHA-256 全部匹配本地上传清单。

发布后以不带认证的独立直连下载取得 HTTP 200，74985885 字节，SHA-256 `a8921af4164bfe6d68d06f871a5764c373d267254e73b3be98aaddc49baf3de2`，与本地 APK 相同。真实手机运行及用户验收仍待完成。

发布前后逐项比较确认：Windows 0.2.1 发布内容与 6 个附件、update-preview 发布及 windows.json 原始字节、Latest 状态、main SHA、本地 Windows 工作区状态和 tracked diff 均保持原样。没有改动 Windows 文档或源码。

本轮证据集中在 `artifacts/github-android-personal-001`：windows-before.json、windows-after.json、draft-verified.json、published-release.json、asset-manifest.json、anonymous-download-verification.json、isolation-verification.json。后续验收从 vivo 的安装、启动、输入／滚动和真实 API 聊天开始。
