"""Audit and stage the signed personal APK. Does not run the app or publish."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import importlib.util
import io
import json
import marshal
import re
import shutil
import subprocess
import zipfile

root = Path(__file__).resolve().parents[1]
delivery = root / "artifacts/android-preview"
out = root / "artifacts/github-android-personal-012"
stage = out / "upload"
stage.mkdir(exist_ok=True)
apk = delivery / "dreamtalk-android-0.1.2-arm64.apk"
report = json.loads((delivery / "apk-verification.json").read_text(encoding="utf-8"))
sha = hashlib.sha256(apk.read_bytes()).hexdigest()
assert report["apk"] == apk.name and report["sha256"] == sha and not report["privacy_findings"]
tools = root / "build-tools/android-sdk/build-tools/35.0.0"
badging = subprocess.check_output([str(tools / "aapt2.exe"), "dump", "badging", str(apk)]).decode("utf-8", "replace")
assert "name='app.livingworld.desktop'" in badging
assert "versionCode='1002'" in badging and "versionName='0.1.2'" in badging
assert "minSdkVersion:'24'" in badging and "targetSdkVersion:'36'" in badging
assert "native-code: 'arm64-v8a'" in badging
manifest = subprocess.check_output([str(tools / "aapt2.exe"), "dump", "xmltree", str(apk), "--file", "AndroidManifest.xml"]).decode("utf-8", "replace")
for value in ("POST_NOTIFICATIONS", "FOREGROUND_SERVICE_SPECIAL_USE", "DreamtalkBackgroundService", "DreamtalkBootReceiver", "PROPERTY_SPECIAL_USE_FGS_SUBTYPE"):
    assert value in manifest, value
(out / "apk-badging.txt").write_text(badging, encoding="utf-8")
(out / "apk-manifest.txt").write_text(manifest, encoding="utf-8")
signature = (root / "artifacts/apk-signature-check.log").read_text(encoding="utf-8-sig")
certificate = re.search(r"certificate SHA-256 digest: ([0-9a-f]+)", signature).group(1)
assert certificate == "61bf42386884a6c001e14af9b75e297a59e255c4061195ec6e23cbe68c02c598"
assert "Verified using v2 scheme (APK Signature Scheme v2): true" in signature
assert "Verified using v3 scheme (APK Signature Scheme v3): true" in signature
payload = {}
with zipfile.ZipFile(apk) as archive:
    native = archive.read("lib/arm64-v8a/libdreamtalk_mobile.so")
    assert b"Java_app_livingworld_mobile_NativeBounds_tokenUpperBound" in native
    dex = b"".join(archive.read(name) for name in archive.namelist() if name.endswith(".dex"))
    for name in (b"app/livingworld/mobile/CoreRuntime", b"app/livingworld/mobile/NativeBounds", b"app/livingworld/mobile/ExamplePlugin"):
        assert name in dex, name
    for name in archive.namelist():
        if name.endswith(".imy"):
            with zipfile.ZipFile(io.BytesIO(archive.read(name))) as nested:
                for entry in nested.namelist():
                    if entry.startswith("livingworld/") and entry.endswith(".pyc"):
                        payload[entry] = nested.read(entry)
required = ["bootstrap/mobile_host", "bootstrap/mobile_settings", "bootstrap/mobile_storage", "bootstrap/mobile_notifications", "infrastructure/mobile_media_search"]
for name in required:
    assert "livingworld/" + name + ".pyc" in payload, name
storage = marshal.loads(payload["livingworld/bootstrap/mobile_storage.pyc"][16:])
assert "0.1.2" in storage.co_consts
(out / "feature-payload-verification.json").write_text(json.dumps({"version": "0.1.2", "version_code": 1002, "certificate_sha256": certificate, "required_core_modules": required, "native_activity_independent_counter_symbol": True, "background_service_and_permissions": True, "runtime_executed": False}, ensure_ascii=False, indent=2), encoding="utf-8")

notes = """## 安卓个人测试 0.1.2：设置、示例世界与后台联系

这是独立安卓个人测试预发布，供手机下载验证；不进入 Windows 更新通道，不设置为 Latest。

### 下载与覆盖安装

下载 **dreamtalk-android-0.1.2-arm64.apk**，约 SIZE MiB。包名、体验签名保持，可直接覆盖安装 0.1.1，无需先卸载。ARM64，Android 7.0 及以上；本轮以 vivo X80／OriginOS 6 为主要验收设备。

### 本次内容

- 补齐 11 类可迁移设置：模型与聊天、聊天视觉、表情与图片、角色配音、后台运行与通知、数据与备份、世界时间、角色活动、主动联系、世界动态、关于与诊断。
- 模型支持全局默认、世界独立配置、独立群聊调度器和恢复继承，沿用 Token 硬上限；派生配置使用独立密钥引用，密钥由 Android Keystore 保护。
- 提供校园示例的预览与确认创建，不自动开启生成。视觉保持简版；配音／图片分析只提供在线路线，没有本地模型部署入口。
- 增加可停止的安卓后台会话、系统通知和可选开机恢复。角色消息先提交到存档，再发送不包含聊天正文的来信提示；点击定位到对应世界和会话，保留忙碌、暂停、合法事由及等待回复限制。
- 增加五个存档位置、系统文件选择与导入导出、角色音色与表情库入口；当前数据库缺失时要求恢复确认，避免误建空存档。
- 保留既有 Logo、启动依赖修复、应用身份、手机数据位置以及未知付费结果不自动重发规则。

### 建议验收顺序

1. 覆盖安装，确认原世界、聊天与 API 配置仍在；也可从书架预览创建校园示例。
2. 打开角色私聊，再按需开启“角色活动”和“主动联系”，确认 API 用量；玩家保持可联系、世界保持运行。
3. 在“后台运行与通知”允许通知、确认费用并开启后台；核对后台状态通知。必要时通过应用内按钮检查 vivo 的后台耗电、自启动与通知设置。
4. 退到桌面或锁屏，在不重新打开应用时观察来信；收到后点击，核对原会话、消息与时间，观察是否重复。不要通过强行停止应用测试普通后台运行。
5. 联系间隔按世界分钟计算，默认 360。可在设置中调整；仍需真实活动理由，不保证开启即发消息。已有待回复联系、忙碌或暂停会阻止后续普通联系。

后台生成默认关闭，开启可能产生 API 费用和额外耗电；系统省电或厂商限制可能延迟执行。关机、强行停止及明确停止后台时不承诺继续运行。

### 工程证据与待验收

本轮为 build-only 发行，没有运行已安装应用、读取真实存档或调用真实 API。发布源码离线回归通过，前端相关回归与三个手机宽度的界面检查通过；本次 APK 已核对版本、原签名、16KB ELF 对齐、启动库依赖、Logo、后台服务权限、独立 JNI 计数入口及新增 Core 模块，递归载荷隐私检查无发现。详细计数与摘要见附件 android-build-receipt.json。

**0.1.1 的模拟器启动结果不作为 0.1.2 运行证据。** 本版锁屏联系、通知点击、系统回收与开机恢复、耗电和发热、Keystore 升级兼容、真实 API 效果及存档跨平台互通均待手机验收。语义召回仍使用关键词回退，不能宣称与 Windows 完全等效。

### 与 Windows 隔离及源码说明

本次仅建立 android-* 个人测试预发布并上传 APK、校验、指南和回执；不推送 main，不更改 Windows 发布附件或 update-preview/windows.json。安卓工程在独立工作区，尚未提交为 GitHub Android 源码；发布标签基于已核对的仓库基准，仅用作下载标识。自动 Source code 档案是 Windows 基准，不是此 APK 的 Android 工程。没有将 Windows CI 当作 Android CI，也没有使用 --skip-ci。公开仓库的个人测试预发布公开可见。

APK SHA-256：`SHA`

体验证书 SHA-256：`CERT`
"""
notes = notes.replace("SIZE", str(round(apk.stat().st_size / 1048576, 1))).replace("SHA`", sha + "`").replace("CERT`", certificate + "`")
(out / "release-notes.md").write_text(notes, encoding="utf-8")
guide = notes.split("### 与 Windows 隔离及源码说明")[0]
(delivery / "体验指南-0.1.2.md").write_text(guide, encoding="utf-8")
regression = (root / "artifacts/release-012-offline-regression.log").read_text(encoding="utf-8-sig")
assert re.search(r"48 passed", regression), regression[-1000:]
source = json.loads((root / "artifacts/settings-source-check.json").read_text(encoding="utf-8"))
source_files = list(dict.fromkeys([entry["file"] for entry in source["source_files"]] + ["package.json", "package-lock.json", "apps/mobile/package.json", "apps/mobile/src-tauri/tauri.conf.json", "apps/mobile/src-tauri/Cargo.toml", "apps/mobile/src-tauri/Cargo.lock", "scripts/android-release-snapshot.py", "scripts/prepare-android-012-release.py"]))
spec = importlib.util.spec_from_file_location("privacy", root / "scripts/check-release-privacy.py")
gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
source_problems = []
source_digest = []
for name in source_files:
    data = (root / name).read_bytes()
    source_problems.extend(name + ":" + label for label in gate.findings(name, data, source=True))
    source_digest.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
assert not source_problems, source_problems
(out / "source-manifest.json").write_text(json.dumps(source_digest, ensure_ascii=False, indent=2), encoding="utf-8")
base = json.loads((out / "windows-before.json").read_text(encoding="utf-8"))
receipt = {"product": "dreamtalk Android personal test", "version": "0.1.2", "version_code": 1002, "package_id": "app.livingworld.desktop", "abi": "arm64-v8a", "min_sdk": 24, "target_sdk": 36, "apk": apk.name, "bytes": apk.stat().st_size, "sha256": sha, "signing_certificate_sha256": certificate, "signature_schemes": ["v2", "v3"], "created_at_jst": datetime.now(timezone(timedelta(hours=9))).isoformat(), "source_base_commit": base["main"], "android_source_committed": False, "android_ci": "not configured for this independent personal build; Windows CI is not Android evidence", "skip_ci_used": False, "distribution_only": True, "offline_regression": "48 passed", "frontend_regression": "35 passed", "browser_widths": [320, 390, 720], "privacy_findings": [], "privacy_entries_inspected": report["entries_inspected"], "source_files_inspected": len(source_files), "native_libraries_16kb_aligned": len(report["native_libraries"]), "startup_dependency_closure": report["native_dependency_closure"], "brand": report["brand"], "python_extension_linkage": report["python_extension_linkage"], "new_payload_modules": required, "apk_runtime_executed": False, "real_api_used": False, "real_user_data_used": False, "vivo_x80_originos6_acceptance": "pending"}
(delivery / "build-receipt-0.1.2.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
(delivery / (apk.name + ".sha256")).write_text(sha + "  " + apk.name + "\n", encoding="ascii")
shutil.copyfile(apk, stage / apk.name)
shutil.copyfile(delivery / (apk.name + ".sha256"), stage / (apk.name + ".sha256"))
shutil.copyfile(delivery / "build-receipt-0.1.2.json", stage / "android-build-receipt.json")
shutil.copyfile(delivery / "体验指南-0.1.2.md", stage / "android-preview-guide.md")
shutil.copyfile(delivery / "apk-verification.json", delivery / "apk-verification-0.1.2.json")
for file in [*stage.iterdir(), out / "release-notes.md"]:
    assert not gate.findings(file.name, file.read_bytes(), source=False), file.name
assets = [{"name": file.name, "bytes": file.stat().st_size, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()} for file in sorted(stage.iterdir())]
assert len(assets) == 4
(out / "asset-manifest.json").write_text(json.dumps(assets, indent=2), encoding="utf-8")
print(json.dumps({"apk": apk.name, "MiB": round(apk.stat().st_size / 1048576, 1), "sha256": sha, "certificate": certificate, "assets": len(assets), "source_privacy_findings": 0, "new_payload_modules": len(required)}, ensure_ascii=False))
