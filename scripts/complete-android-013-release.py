"""Close out the Android release after public download and CI verification."""

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/github-android-personal-013"


def main():
    def load(name):
        return json.loads((OUT / name).read_text(encoding="utf-8"))

    release = load("published-release.json")
    download = load("anonymous-download-verification.json")
    isolation = load("isolation-verification.json")
    source = load("source-commit.json")
    tag = load("tag-ci-verification.json")
    receipt = json.loads(
        (ROOT / "artifacts/android-preview/build-receipt-0.1.3.json").read_text(encoding="utf-8")
    )
    assert not release["draft"] and release["prerelease"]
    assert len(release["assets"]) == 4 and download["all_published_assets_match"]
    assert all(isolation.values())
    assert tag["commit"] == source["commit"] and tag["conclusion"] == "failure" and not tag["rerun"]
    url = release["html_url"]
    apk = next(x["browser_download_url"] for x in release["assets"] if x["name"].endswith(".apk"))
    ci = receipt["source_ci"]["url"]
    text = f"""# Android 当前状态

日期：2026-11-08。当前交付 **0.1.3／1003**，包名 app.livingworld.desktop，ARM64，最低 Android 7.0，target SDK 36。

[个人测试发布页]({url}) · [直接下载 APK]({apk})。公开预发布、非 Latest，4 个附件已发布；全部附件匿名完整下载的长度和 SHA-256 与本地及远端一致。Windows main、v0.2.1 发布及附件、固定频道原始字节、Latest 和本地工作区均与发行前相同。

## 已交付范围

手机内运行 Python Core，世界、身份、聊天和记忆保存在私有目录。保持简版界面、11 类设置、校园示例预览确认、后台会话与通知、系统文档导入导出、音色与表情库、独立调度器和 Keystore 适配。没有本地聊天、配音或视觉部署入口。语义记忆仍为关键词回退，不宣称与 Windows 完全等效。

本版对齐 Windows 当前源码中的句内私密遮罩及刷新保持展开状态、有效分类与兜底来源、普通群聊 reply_parts 兼容、完整正文恢复、分阶段错误诊断、媒体／记忆辅助失败记录和接口／流式校验。迁移 head 为 0066_chat_privacy_fallback，旧原文、受众和未知来源保持。后台默认关闭，费用、暂停、Busy、等待回复、权限过滤及未知收费结果不重发规则保持。

契约与入口见[同步说明](ANDROID_WINDOWS_SYNC.md)、[设置与后台联系](ANDROID_SETTINGS_MIGRATION.md)和[实现说明](ANDROID_IMPLEMENTATION.md)。

## 发布与工程证据

| 检查 | 当前结果 | 记录 |
| --- | --- | --- |
| 源码与 CI | 独立安卓分支，精确提交 {source['commit']}；1089 文件隐私无发现；构建前 CI 已通过；标签重复检查的一项前端时序断言失败，按用户新指令不重跑 | [构建前 CI]({ci})、[标签 CI]({tag['url']})、../artifacts/github-android-personal-013/source-commit.json |
| 离线回归 | 837 项 Core／支持链旧 revision 升级／安卓宿主测试、216 项前端与客户端测试通过；合成存储，不调用真实供应商 | ../artifacts/windows-sync-20261108/core-checks.json、../artifacts/windows-sync-20261108/web-checks.json |
| 手机宽度组件 | 320／390／720 宽度共 9 项，遮罩、刷新、焦点、展开收起、无横向溢出通过；页面错误和外部请求均为 0 | ../artifacts/windows-sync-20261108/browser/result.json |
| 静态与编译 | TypeScript、Pyright、Ruff、契约一致性、前端、Rust ARM64、Kotlin 和 Gradle release APK 通过 | ../artifacts/android-013-build.log、../artifacts/windows-sync-20261108/static-checks.json |
| 签名与载荷 | 原身份和原证书；强制 v1／v2／v3、ZIP CRC、无重复条目和 16KB 对齐通过；3453 项、397 个 Python 模块源码／字节码、67 迁移源文件、{receipt['native_libraries_16kb_aligned']} 个 ELF、15 个 Logo 图像及 11 个启动库通过 | ../artifacts/android-preview/build-receipt-0.1.3.json、../artifacts/android-preview/apk-verification-0.1.3.json、../artifacts/github-android-personal-013/feature-payload-verification.json |
| 分发与隔离 | 四附件远端大小／摘要和匿名完整下载一致；Windows 状态与发行前相同 | ../artifacts/github-android-personal-013/anonymous-download-verification.json、../artifacts/github-android-personal-013/isolation-verification.json |

APK 为 {receipt['bytes']} 字节，SHA-256：{receipt['sha256']}。

保留既有 Starlette／AnyIO、前端大分块和 Gradle 弃用提示。Windows 符号链接限制按复制分支处理，没有修改系统开发者模式。Tauri 只对两个生成配置改写换行，核对无语义差异后恢复冻结字节。CI 初次漏装 Core 包元数据，补齐后完整通过，未弱化断言或跳过用例。

## 用户已通过与待验收

用户已反馈 0.1.1 在 vivo X80／OriginOS 6 可以打开，只计入该版本启动场景；此前闪退与 Logo 修复见[启动记录](ANDROID_STARTUP_REPAIR.md)。

0.1.2 安装器提示“安装包缺乏开发者证书，建议联系安装包的开发者”，显示 77.14 MB。其源包与 0.1.1 证书相同且 v1／v2／v3 有效，但未收到手机 APK 或底层错误码，根因未确认。本版保留原证书并重新构建和核对，**不能据此宣称 vivo 安装报错已修复**。先验证本版覆盖安装和打开，保留旧版与原数据。

本轮没有运行生产 APK、已安装应用、真实模型或真实存档。真机安装、升级与数据连续性、真实 API 聊天／配音／视觉、锁屏来信、通知点击、权限撤销、Doze／回收／开机恢复、耗电发热、输入和流式流畅度、系统文件提供者及跨平台存档互通，均待用户验收。没有 32 位／x86 包、商店发行或自动更新。

## 来源与交付记录

安卓源码已在独立分支提交并推送，发布标签对应实际安卓源码；没有推送 Windows main 或复用 Windows CI 冒充安卓检查。

[本轮记录](GITHUB_ANDROID_PERSONAL_RELEASE_013.md) · [手机指南](../artifacts/android-preview/体验指南-0.1.3.md) · [本地 APK](../artifacts/android-preview/dreamtalk-android-0.1.3-arm64.apk) · [完成回执](../artifacts/github-android-personal-013/completed.json)。历史证据保留在[上版记录](GITHUB_ANDROID_PERSONAL_RELEASE_012.md)。
"""
    (ROOT / "docs/PROJECT_STATUS.md").write_text(text, encoding="utf-8")
    (ROOT / "README.md").write_text(f"""# dreamtalk 安卓体验版

当前交付与验收边界见[状态清单](docs/PROJECT_STATUS.md)。

[下载 APK]({apk}) · [GitHub 发布页]({url})

下载后验证覆盖安装和启动，保留旧版与原数据。此前 vivo 证书提示的根因尚未确认，新包仍需手机实测。后台默认关闭，开启前确认 API 用量和通知许可。

- [手机验收指南](artifacts/android-preview/体验指南-0.1.3.md)
- [Windows 修改同步](docs/ANDROID_WINDOWS_SYNC.md)
- [设置与后台联系](docs/ANDROID_SETTINGS_MIGRATION.md)
- [实现与构建](docs/ANDROID_IMPLEMENTATION.md)
""", encoding="utf-8")
    path = ROOT / "docs/ANDROID_IMPLEMENTATION.md"
    text = path.read_text(encoding="utf-8").replace(
        "没有 Android 源码 Git 提交或主分支推送；安卓个人测试发布另见状态清单。",
        "安卓源码已通过独立分支和精确提交 CI 管理，没有推送 Windows 主分支；源码标签、发布及验收边界见状态清单。"
    )
    text += "\n本次构建前的精确提交 CI 已通过。用户随后要求未主动要求时不再走 CI，因此停止等待或重跑标签重复检查；没有修改共享工作流配置或构建门禁。当前结果与验收边界见状态清单。\n"
    path.write_text(text, encoding="utf-8")
    path = ROOT / "docs/ANDROID_WINDOWS_SYNC.md"
    text = path.read_text(encoding="utf-8").replace(
        "本轮没有生成新 APK、运行已安装应用、调用真实模型、读取真实存档、提交或修改 GitHub 发布内容。",
        "源码同步检查阶段没有生成 APK 或发布；之后的独立源码提交、CI 与发行结果见状态清单，仍未运行用户已安装应用、调用真实模型或读取真实存档。"
    )
    path.write_text(text, encoding="utf-8")
    (ROOT / "docs/GITHUB_ANDROID_PERSONAL_RELEASE_013.md").write_text(f"""# 安卓个人测试发行记录

当前版本、检查与用户验收统一见[状态清单](PROJECT_STATUS.md)。

用户本轮明确要求发布新版本。已发布个人预发布 [android-v0.1.3-personal.1]({url})，Release ID {release['id']}，非 Latest，4 个附件。独立分支 codex/android-personal-0.1.3，实际源码提交 {source['commit']}；没有改写 Windows 历史或推送 main。

[构建前精确提交 CI]({ci}) 已通过；[标签重复 CI]({tag['url']}) 的一项前端时序断言失败，按用户新指令不重跑。首轮 CI 缺少 Core 包元数据，补齐环境与失败输出后完整通过，未弱化断言或跳过用例。构建使用带标记的安卓缓存，交付产物仍在安卓目录。

APK 为 {receipt['bytes']} 字节，SHA-256 {receipt['sha256']}；原证书 SHA-256 {receipt['signing_certificate_sha256']}。v1／v2／v3、16KB 对齐、397 模块源码对应及载荷隐私通过；Tauri 只调整两个生成配置的换行，已核对无语义差异并恢复冻结字节。

[资产](../artifacts/github-android-personal-013/asset-manifest.json)、[源码](../artifacts/github-android-personal-013/source-commit.json)、[标签核对](../artifacts/github-android-personal-013/tag-ci-verification.json)、[载荷](../artifacts/github-android-personal-013/feature-payload-verification.json)、[匿名下载](../artifacts/github-android-personal-013/anonymous-download-verification.json)、[Windows 隔离](../artifacts/github-android-personal-013/isolation-verification.json)和[完成回执](../artifacts/github-android-personal-013/completed.json)保留逐项证据。

未运行生产 APK、已安装应用、真实模型或真实存档。vivo 证书提示根因未确认，新包安装及真实聊天／后台通知仍待手机验收。
""", encoding="utf-8")
    done = {
        "completed_at": datetime.now(timezone.utc).isoformat(), "release_id": release["id"],
        "release": url, "download": apk, "version": "0.1.3", "version_code": 1003,
        "source_commit": source["commit"], "source_ci": receipt["source_ci"], "tag_ci": tag,
        "assets": 4, "all_anonymous_downloads_verified": True, "windows_isolation": isolation,
        "signature_schemes": ["v1", "v2", "v3"], "sha256": receipt["sha256"],
        "ci_policy": load("ci-policy.json"),
        "apk_runtime_executed": False, "real_api_used": False, "real_user_data_used": False,
        "vivo_x80_originos6_acceptance": "pending"
    }
    (OUT / "completed.json").write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"version": "0.1.3", "release": url, "assets": 4, "windows_isolation": isolation}))


if __name__ == "__main__":
    main()
