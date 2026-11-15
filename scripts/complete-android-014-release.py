"""Record the hotfix only after release assets and Windows isolation verify."""

from pathlib import Path
from datetime import datetime, timezone
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/github-android-personal-014"


def main():
    def load(name):
        return json.loads((OUT/name).read_text(encoding="utf-8"))
    release=load("published-release.json")
    download=load("anonymous-download-verification.json")
    isolation=load("isolation-verification.json")
    source=load("source-commit.json")
    authorization=load("release-authorization.json")
    receipt=json.loads((ROOT/"artifacts/android-preview/build-receipt-0.1.4.json").read_text(encoding="utf-8"))
    assert not release["draft"] and release["prerelease"] and len(release["assets"])==4
    assert download["all_published_assets_match"] and all(isolation.values())
    assert authorization["user_authorized_skip_ci"] and not receipt["source_ci"]["run"]
    url=release["html_url"]
    apk=next(a["browser_download_url"] for a in release["assets"] if a["name"].endswith(".apk"))
    status=f"""# Android 当前状态

日期：2026-11-08。当前交付 **0.1.4／1004**，包名 app.livingworld.desktop，ARM64，最低 Android 7.0，target SDK 36。

[个人测试发布页]({url}) · [直接下载 APK]({apk})。公开预发布、非 Latest，4 个附件全部通过远端摘要和匿名完整下载核对。Windows main、v0.2.1 发布及附件、频道原始字节、Latest 和本地工作区均与发行前一致。

## 本版启动修复

0.1.3 已由用户确认能安装并进入 dreamtalk 启动页面，但 Core 启动失败，诊断为 core_running=false、startup 为空。隔离数据复现了同样的空诊断：可信应用父目录存在别名时，存储保护在线程创建前拒绝，旧诊断没有捕获异常。

0.1.4 已交付可信父目录处理和完整启动前诊断，托管根及内部目录的链接保护保持。复制诊断不依赖目录或安全存储初始化，返回固定阶段、错误码、异常类别和项目源码位置，不输出异常原文、路径、正文、配置或密钥。修复与现象一致，但尚未读取手机底层路径，不能把模拟复现当作 vivo 确诊或修复验收。

契约和复现见[启动修复](ANDROID_STARTUP_PREFLIGHT.md)。聊天、11 类设置、校园示例、后台联系、系统文档及 Keystore 适配保留，语义记忆仍为关键词回退；没有本地模型部署入口。

## 工程与发行证据

| 检查 | 当前证据 | 记录 |
| --- | --- | --- |
| 源码 | 独立安卓修复分支，标签对应实际提交 {source['commit']}；{len(source['files'])} 文件及实际提交隐私无发现 | ../artifacts/github-android-personal-014/source-commit.json |
| 修复离线回归 | 33 项移动宿主、6 项前端提示测试、TypeScript、Ruff、Kotlin 编译通过；合成存储、外部网络阻止 | ../artifacts/android-013-startup-investigation/repair-verification.json |
| 本轮构建 | Rust ARM64、Kotlin、Gradle、前端和类型检查通过；本轮明确 SkipCI，未主动运行或等待 CI，未修改共享工作流 | ../artifacts/android-014-build.log、../artifacts/github-android-personal-014/release-authorization.json |
| 实际包 | 原证书 v1／v2／v3、ZIP CRC、无重复条目、16KB 对齐、397 个 Python 模块源码／字节码对应及隐私检查通过；Logo 15 个 DPI 图像，67 个迁移源文件，{receipt['native_libraries_16kb_aligned']} 个 ELF，11 个启动原生库 | ../artifacts/android-preview/build-receipt-0.1.4.json、../artifacts/android-preview/apk-verification-0.1.4.json、../artifacts/github-android-personal-014/feature-payload-verification.json |
| 公开分发 | 四附件大小和 SHA-256 与本地一致，全部无认证完整下载核对；APK 为 {receipt['bytes']} 字节 | ../artifacts/github-android-personal-014/anonymous-download-verification.json |
| Windows 隔离 | main、发布及附件、频道、Latest、本地工作区均不变 | ../artifacts/github-android-personal-014/isolation-verification.json |

APK SHA-256：{receipt['sha256']}。

保留既有 Kotlin／Gradle 弃用及前端分块体积提示。本轮只对已测试修复递增版本并构建、签名和分发，不运行生产 APK、用户已安装应用、真实模型或真实存档。

## 用户验收

0.1.1 的 vivo X80／OriginOS 6 打开场景已通过；0.1.3 的安装和启动页面已通过，但 Core 启动失败。本版能否完整打开，需用户覆盖安装后确认。若仍失败，用“复制启动诊断”提供新记录；保留原数据，不要求用户处理端口、命令行或恢复文件。

真实 API 聊天／配音／视觉、升级数据连续性、后台通知、Doze／回收／开机恢复、耗电发热、输入流畅度、系统文件提供者和跨平台存档仍待验收。没有 32 位／x86 包、商店发行或自动更新。

[本轮发行记录](GITHUB_ANDROID_PERSONAL_RELEASE_014.md) · [手机指南](../artifacts/android-preview/体验指南-0.1.4.md) · [完成回执](../artifacts/github-android-personal-014/completed.json) · [上版记录](GITHUB_ANDROID_PERSONAL_RELEASE_013.md)。
"""
    (ROOT/"docs/PROJECT_STATUS.md").write_text(status,encoding="utf-8")
    (ROOT/"README.md").write_text(f"""# dreamtalk 安卓体验版

[下载启动修复 APK]({apk}) · [GitHub 发布页]({url})

当前版本和验收边界见[状态清单](docs/PROJECT_STATUS.md)。验证覆盖安装及完整启动，保留原数据。若仍启动失败，复制启动诊断给工程端。

- [手机指南](artifacts/android-preview/体验指南-0.1.4.md)
- [启动修复](docs/ANDROID_STARTUP_PREFLIGHT.md)
- [设置和后台联系](docs/ANDROID_SETTINGS_MIGRATION.md)
- [实现说明](docs/ANDROID_IMPLEMENTATION.md)
""",encoding="utf-8")
    p=ROOT/"docs/ANDROID_STARTUP_PREFLIGHT.md"
    s=p.read_text(encoding="utf-8").replace("已公开 0.1.3 不包含此修复，手机是否解决仍待修复包验收。","此修复已进入当前交付 APK，具体版本和分发证据见状态清单；手机是否解决仍待用户验收。")
    s=s.replace("本轮未运行 CI、生产 APK、已安装应用、真实模型或真实存档；未打包、提交、推送或修改发布附件。","源码修复阶段未运行 CI、生产 APK、已安装应用、真实模型或真实存档；后续用户已授权快速发布，交付结果以状态清单为准。")
    p.write_text(s,encoding="utf-8")
    p=ROOT/"docs/ANDROID_IMPLEMENTATION.md"
    s=p.read_text(encoding="utf-8")
    s+="\n用户未明确要求时，工程端不主动运行或等待 CI。单次发布使用显式 SkipCI 参数和匹配版本的授权回执，保留默认门禁、共享工作流和本地编译、验签、载荷及下载核对。当前执行结果见状态清单。\n"
    p.write_text(s,encoding="utf-8")
    (ROOT/"docs/GITHUB_ANDROID_PERSONAL_RELEASE_014.md").write_text(f"""# 安卓启动修复发行记录

当前版本与验收以[状态清单](PROJECT_STATUS.md)为准。

用户本轮明确要求“快速发布”，此前明确要求未主动要求时不走 CI。已发布个人预发布 [android-v0.1.4-personal.1]({url})，Release ID {release['id']}，非 Latest。实际源码提交 {source['commit']}，位于独立修复分支，没有推送 Windows main。

本轮通过单次显式 SkipCI 和版本匹配的用户授权回执跳过 CI，不修改共享工作流或默认门禁，不主动查询或等待服务器自动检查。修复代码此前的 33 项宿主及 6 项前端回归、类型、格式和 Kotlin 编译通过，本轮完成必要编译及包核对。

APK 为 {receipt['bytes']} 字节，SHA-256 {receipt['sha256']}；沿用原证书。v1／v2／v3、16KB 对齐、397 模块源码对应、Logo 和启动依赖通过。四个附件均完成远端与匿名完整下载核对，Windows 发布和频道不变。

[源码](../artifacts/github-android-personal-014/source-commit.json)、[授权](../artifacts/github-android-personal-014/release-authorization.json)、[资产](../artifacts/github-android-personal-014/asset-manifest.json)、[载荷](../artifacts/github-android-personal-014/feature-payload-verification.json)、[匿名下载](../artifacts/github-android-personal-014/anonymous-download-verification.json)、[隔离](../artifacts/github-android-personal-014/isolation-verification.json)及[完成回执](../artifacts/github-android-personal-014/completed.json)保留证据。

未运行真实 APK、模型或存档；vivo X80 完整启动和实际 API／后台体验仍待手机验收。
""",encoding="utf-8")
    done={"completed_at":datetime.now(timezone.utc).isoformat(),"version":"0.1.4","version_code":1004,"release_id":release["id"],"release":url,"download":apk,"source_commit":source["commit"],"source_branch":source["branch"],"assets":4,"all_anonymous_downloads_verified":True,"windows_isolation":isolation,"ci_run_by_agent":False,"ci_waited":False,"ci_skip_user_authorized":True,"signature_schemes":["v1","v2","v3"],"sha256":receipt["sha256"],"apk_runtime_executed":False,"real_api_used":False,"real_user_data_used":False,"vivo_acceptance":"pending"}
    (OUT/"completed.json").write_text(json.dumps(done,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"version":"0.1.4","url":url,"assets":4,"windows_isolation":isolation}))


if __name__=="__main__":
    main()
