"""Prepare the independent Android source commit; never push or copy local data."""
from pathlib import Path
import hashlib,importlib.util,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts/github-android-personal-016";SNAP=ROOT/"artifacts/android-source-016";OLD=ROOT/"artifacts/android-source-015"
PARENT="163f9445b73459cebb9a6dbda2895e8b29bc87de";BRANCH="codex/android-hotfix-0.1.6"
def git(*args,cwd=SNAP):
 return subprocess.check_output(["git",*args],cwd=cwd,stderr=subprocess.PIPE)
def main():
 existed=SNAP.exists()
 assert SNAP.resolve().is_relative_to((ROOT/"artifacts").resolve()) and not SNAP.is_symlink()
 names={x["path"] for x in json.loads((OUT/"source-inventory.json").read_text())["files"]}
 names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/"scripts").glob("*.py"))
 gate_spec=importlib.util.spec_from_file_location("privacy",ROOT/"scripts/check-release-privacy.py");gate=importlib.util.module_from_spec(gate_spec);gate_spec.loader.exec_module(gate)
 entries=[];problems=[]
 for name in sorted(names):
  p=ROOT/name;assert p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(ROOT)
  data=p.read_bytes();problems.extend({"path":name,"codes":issue} for issue in gate.findings(name,data,source=True))
  entries.append({"path":name,"source":name,"sha256":hashlib.sha256(data).hexdigest()})
 assert not problems,problems
 if existed:
  assert not (OUT/"source-commit.json").exists()
  assert git("rev-parse","HEAD").decode().strip()==PARENT
  assert git("branch","--show-current").decode().strip()==BRANCH
 else:
  SNAP.mkdir()
  git("init","-b",BRANCH)
  git("config","core.autocrlf","false")
  for key in ["user.name","user.email"]:
   value=git("config","--get",key,cwd=OLD).decode().strip();assert value;git("config",key,value)
  git("fetch","--no-tags",str(OLD),PARENT)
  git("update-ref","refs/heads/"+BRANCH,PARENT)
 for item in entries:
  target=SNAP/item["path"];assert target.resolve().is_relative_to(SNAP.resolve());target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/item["path"],target)
 git("add","--all")
 tracked=set(git("ls-files","-z").decode().split("\0"))-{""}
 missing={x["path"] for x in entries}-tracked
 # These reviewed generated source inputs were also recorded in earlier Android
 # releases. Force only these paths, after the full-file privacy scan above.
 generated_root="apps/mobile/src-tauri/gen/android/"
 allowed={generated_root+name for name in ["app/proguard-tauri.pro","app/tauri.build.gradle.kts","app/tauri.properties","tauri.settings.gradle"]}
 generated_java=generated_root+"app/src/main/java/app/livingworld/desktop/generated/"
 allowed.update(generated_java+name for name in ["Ipc.kt","Logger.kt","PermissionHelper.kt","Rust.kt","RustWebChromeClient.kt","RustWebView.kt","RustWebViewClient.kt","TauriActivity.kt","WryActivity.kt","proguard-wry.pro"])
 assert missing<=allowed,sorted(missing-allowed)
 if missing:git("add","--force","--",*sorted(missing))
 tracked=set(git("ls-files","-z").decode().split("\0"))-{""}
 assert tracked=={x["path"] for x in entries},sorted({x["path"] for x in entries}-tracked)
 if "apps/mobile/src-tauri/gen/android/gradlew" in tracked:git("update-index","--chmod=+x","apps/mobile/src-tauri/gen/android/gradlew")
 gate.ROOT=SNAP
 current=[]
 for name,data in gate.source_files(None):current.extend({"path":name,"codes":x} for x in gate.findings(name,data,source=True))
 assert not current,current
 (OUT/"source-current-privacy.json").write_text(json.dumps({"files":len(entries),"findings":current},indent=2)+"\n")
 git("commit","-m","Release Android 0.1.6 personal preview [skip ci]")
 commit=git("rev-parse","HEAD").decode().strip()
 assert git("rev-parse","HEAD^").decode().strip()==PARENT
 assert not git("status","--porcelain","-uall")
 committed=[]
 for name,data in gate.source_files(commit):committed.extend({"path":name,"codes":x} for x in gate.findings(name,data,source=True))
 assert not committed,committed
 for item in entries:
  assert hashlib.sha256((ROOT/item["source"]).read_bytes()).hexdigest()==item["sha256"]
  assert hashlib.sha256((SNAP/item["path"]).read_bytes()).hexdigest()==item["sha256"]
 (OUT/"source-commit-privacy.json").write_text(json.dumps({"files":len(entries),"commit":commit,"findings":committed},indent=2)+"\n")
 git("remote","add","origin","https://github.com/zhangyeS12/dreamtalk.git")
 record={"version":"0.1.6","version_code":1006,"commit":commit,"parent":PARENT,"branch":BRANCH,"source_directory":SNAP.relative_to(ROOT).as_posix(),"files":entries,"ci_strategy":{"branch_matches_workflow":False,"commit_skip_ci":True,"shared_workflow_changed":False,"reference":"https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs"}}
 (OUT/"source-commit.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"commit":commit,"branch":BRANCH,"files":len(entries),"privacy_findings":0}))
if __name__=="__main__":main()
