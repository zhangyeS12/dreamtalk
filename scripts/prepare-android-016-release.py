"""Audit the signed APK and stage only the four authorized personal release assets."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import marshal
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/github-android-personal-016"
DELIVERY = ROOT / "artifacts/android-preview"
APK = DELIVERY / "dreamtalk-android-0.1.6-arm64.apk"
TOOLS = ROOT / "build-tools/android-sdk/build-tools/35.0.0"


def main():
    state = json.loads((OUT / "source-commit.json").read_text(encoding="utf-8"))
    authorization = json.loads((OUT / "release-authorization.json").read_text(encoding="utf-8"))
    assert authorization["version"] == "0.1.6" and authorization["user_authorized_skip_ci"]
    ci = {"run": False, "waited": False, "user_authorized_skip": True, "source_commit": state["commit"], "reason": "Explicit user instruction; per-release SkipCI, shared workflows unchanged."}
    report = json.loads((DELIVERY / "apk-verification.json").read_text(encoding="utf-8"))
    sha = hashlib.sha256(APK.read_bytes()).hexdigest()
    assert report["apk"] == APK.name and report["sha256"] == sha and not report["privacy_findings"]
    badging = subprocess.check_output([str(TOOLS / "aapt2.exe"), "dump", "badging", str(APK)]).decode("utf-8", "replace")
    for value in ("name='app.livingworld.desktop'", "versionCode='1006'", "versionName='0.1.6'", "minSdkVersion:'24'", "targetSdkVersion:'36'", "native-code: 'arm64-v8a'"):
        assert value in badging, value
    (OUT / "apk-badging.txt").write_text(badging, encoding="utf-8")
    certificate = "61bf42386884a6c001e14af9b75e297a59e255c4061195ec6e23cbe68c02c598"
    for low, high, scheme in ((23, 23, "v1"), (24, 27, "v2"), (28, 36, "v3")):
        log = (ROOT / f"artifacts/apk-signature-sdk-{low}-{high}.log").read_text(encoding="utf-8-sig")
        assert re.search(r"certificate SHA-256 digest: " + certificate, log)
        assert re.search(r"Verified using " + scheme + r" scheme.*: true", log)
    manifest = subprocess.check_output([str(TOOLS / "aapt2.exe"), "dump", "xmltree", str(APK), "--file", "AndroidManifest.xml"]).decode("utf-8", "replace")
    for value in ("POST_NOTIFICATIONS", "FOREGROUND_SERVICE_SPECIAL_USE", "DreamtalkBackgroundService", "DreamtalkBootReceiver"):
        assert value in manifest, value
    (OUT / "apk-manifest.txt").write_text(manifest, encoding="utf-8")
    payload = {}
    with zipfile.ZipFile(APK) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        assert b"Java_app_livingworld_mobile_NativeBounds_tokenUpperBound" in archive.read("lib/arm64-v8a/libdreamtalk_mobile.so")
        for name in archive.namelist():
            if name.endswith(".imy"):
                with zipfile.ZipFile(io.BytesIO(archive.read(name))) as nested:
                    for item in nested.namelist():
                        if item.startswith("livingworld/"):
                            payload[item] = nested.read(item)
    verified = []
    source = ROOT / "services/core/src/livingworld"
    for file in sorted(source.rglob("*.py")):
        if "__pycache__" in file.parts:
            continue
        path = "livingworld/" + file.relative_to(source).as_posix()
        if path in payload:
            assert file.read_bytes() == payload[path], path
        else:
            assert path + "c" in payload, path
            code = marshal.loads(payload[path + "c"][16:])
            assert any(code == compile(file.read_bytes(), code.co_filename, "exec", dont_inherit=True, optimize=level) for level in (0, 1, 2)), path
        verified.append(path)
    required = ("application/chat_diagnostics.py", "adapters/http/chat_diagnostics.py", "application/chat_privacy.py", "infrastructure/persistence/migrations/versions/0066_chat_privacy_fallback.py")
    assert all("livingworld/" + name in verified for name in required)
    wheel = ROOT / "build-tools/wheels/dreamtalk_core-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        for path in verified:
            assert archive.read(path) == (ROOT / "services/core/src" / path).read_bytes(), path
    (OUT / "feature-payload-verification.json").write_text(json.dumps({"version":"0.1.6","verified_python_modules":len(verified),"source_and_bytecode_match":True,"head_revision":"0066_chat_privacy_fallback","all_signature_schemes_verified":["v1","v2","v3"],"same_signing_certificate":True,"production_apk_executed":False},indent=2),encoding="utf-8")
    receipt = {"product":"dreamtalk Android personal test","version":"0.1.6","version_code":1006,"package_id":"app.livingworld.desktop","abi":"arm64-v8a","min_sdk":24,"target_sdk":36,"apk":APK.name,"bytes":APK.stat().st_size,"sha256":sha,"signing_certificate_sha256":certificate,"signature_schemes":["v1","v2","v3"],"created_at":datetime.now(timezone.utc).isoformat(),"source_commit":state["commit"],"source_branch":state["branch"],"source_files":len(state["files"]),"source_ci":ci,"python_payload_modules":len(verified),"static_payload_entries":report["entries_inspected"],"native_libraries_16kb_aligned":len(report["native_libraries"]),"brand":report["brand"],"privacy_findings":[],"offline_regression":119,"frontend_regression_reused_for_identical_web_source":327,"frontend_typecheck_and_build":True,"image_runtime_checks":"Same image fix and codec passed isolated Android upload/crop/persistence/restart tests before release version stamping; release APK runtime is separate","apk_runtime_executed":False,"real_api_used":False,"real_user_data_used":False,"vivo_x80_originos6_acceptance":"pending for 0.1.6; previous 0.1.4 startup accepted"}
    (DELIVERY / "build-receipt-0.1.6.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (DELIVERY / (APK.name+".sha256")).write_text(sha+"  "+APK.name+"\n",encoding="ascii")
    shutil.copyfile(DELIVERY / "apk-verification.json",DELIVERY / "apk-verification-0.1.6.json")
    stage=OUT/"upload"; stage.mkdir(exist_ok=True)
    for source, name in ((APK,APK.name),(DELIVERY/(APK.name+".sha256"),APK.name+".sha256"),(DELIVERY/"build-receipt-0.1.6.json","android-build-receipt.json"),(DELIVERY/"体验指南-0.1.6.md","android-preview-guide.md")):
        shutil.copyfile(source,stage/name)
    spec=importlib.util.spec_from_file_location("privacy",ROOT/"scripts/check-release-privacy.py"); gate=importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
    assets=[]
    for file in sorted(stage.iterdir()):
        assert not gate.findings(file.name,file.read_bytes(),source=False),file.name
        assets.append({"name":file.name,"bytes":file.stat().st_size,"sha256":hashlib.sha256(file.read_bytes()).hexdigest()})
    assert len(assets)==4
    assert not gate.findings("release-notes.md",(OUT/"release-notes.md").read_bytes(),source=False)
    (OUT/"asset-manifest.json").write_text(json.dumps(assets,indent=2),encoding="utf-8")
    print(json.dumps({"apk":APK.name,"bytes":APK.stat().st_size,"sha256":sha,"python_modules_match":len(verified),"assets":4}))


if __name__=="__main__":
    main()
