from wheel_record import write_record
from pathlib import Path
import hashlib,json,os,subprocess,sys,tarfile,urllib.request,zipfile
ROOT=Path(r"D:\dreamtalk安卓版")
def fetch(url,path,sha=None):
 if path.exists() and (not sha or hashlib.sha256(path.read_bytes()).hexdigest()==sha): return
 with urllib.request.urlopen(url,timeout=60) as r: data=r.read()
 if sha and hashlib.sha256(data).hexdigest()!=sha: raise RuntimeError("Source digest mismatch")
 path.write_bytes(data)
version="2.27.2"
meta=json.load(urllib.request.urlopen("https://pypi.org/pypi/pydantic_core/"+version+"/json",timeout=60))
source=next(x for x in meta["urls"] if x["packagetype"]=="sdist")
archive=ROOT/"build-tools"/source["filename"]
fetch(source["url"],archive,source["digests"]["sha256"])
directory=ROOT/"build-tools"/("pydantic_core-"+version)
if not directory.exists():
 with tarfile.open(archive) as t:t.extractall(ROOT/"build-tools",filter="data")
ndk=ROOT/"build-tools/android-sdk/ndk/27.2.12479018/toolchains/llvm/prebuilt/windows-x86_64/bin"
config=ROOT/"build-tools/pyo3-android313.txt"
config.write_text("implementation=CPython\nversion=3.13\nshared=true\nabi3=false\nlib_name=python3.13\npointer_width=64\nsuppress_build_script_link_lines=true\n",encoding="utf-8")
env=os.environ.copy()
env.update({"CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER":str(ndk/"aarch64-linux-android24-clang.cmd"),"CC_aarch64_linux_android":str(ndk/"aarch64-linux-android24-clang.cmd"),"AR_aarch64_linux_android":str(ndk/"llvm-ar.exe"),"PYO3_CROSS":"1","PYO3_CROSS_PYTHON_VERSION":"3.13","PYO3_CONFIG_FILE":str(config),"PYTHON":sys.executable,"CARGO_TARGET_DIR":str(ROOT/"artifacts/pydantic-target"),"PYTHONUTF8":"1","RUSTFLAGS":"-C link-arg=-Wl,-z,max-page-size=16384"})
from importlib import import_module
import_module("android-python-link").link_android_python(ROOT,env)
command=["cargo","build","--release","--target","aarch64-linux-android","--features","extension-module"]
print("Cross-building pydantic-core",version,flush=True)
subprocess.run(command,cwd=directory,env=env,check=True)
binary=ROOT/"artifacts/pydantic-target/aarch64-linux-android/release/lib_pydantic_core.so"
if not binary.exists():
 candidates=list((ROOT/"artifacts/pydantic-target/aarch64-linux-android/release").glob("*.so"))
 if len(candidates)!=1: raise RuntimeError("Native extension output missing")
 binary=candidates[0]
wheel_dir=ROOT/"build-tools/wheels";wheel_dir.mkdir(exist_ok=True)
wheel=wheel_dir/("pydantic_core-"+version+"-cp313-cp313-android_24_arm64_v8a.whl")
info="pydantic_core-"+version+".dist-info"
with zipfile.ZipFile(wheel,"w",zipfile.ZIP_DEFLATED) as z:
 for p in (directory/"python/pydantic_core").rglob("*"):
  if p.is_file():z.writestr("pydantic_core/"+p.relative_to(directory/"python/pydantic_core").as_posix(),p.read_bytes())
 z.writestr("pydantic_core/_pydantic_core.so",binary.read_bytes())
 z.writestr(info+"/METADATA","Metadata-Version: 2.1\nName: pydantic_core\nVersion: "+version+"\nRequires-Python: >=3.8\nLicense: MIT\n")
 z.writestr(info+"/WHEEL","Wheel-Version: 1.0\nGenerator: dreamtalk-android-build\nRoot-Is-Purelib: false\nTag: cp313-cp313-android_24_arm64_v8a\n")
 z.writestr(info+"/LICENSE",(directory/"LICENSE").read_bytes())
 write_record(z,info)
print("BUILT",wheel.name,hashlib.sha256(wheel.read_bytes()).hexdigest(),flush=True)
