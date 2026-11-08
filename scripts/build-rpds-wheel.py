from wheel_record import write_record
from pathlib import Path
import hashlib,json,os,subprocess,sys,tarfile,tomllib,urllib.request,zipfile
ROOT=Path(r"D:\dreamtalk安卓版")
package,version="rpds-py","0.25.1"
meta=json.load(urllib.request.urlopen("https://pypi.org/pypi/"+package+"/"+version+"/json",timeout=60))
source=next(x for x in meta["urls"] if x["packagetype"]=="sdist")
archive=ROOT/"build-tools"/source["filename"]
if not archive.exists():
 with urllib.request.urlopen(source["url"],timeout=60) as r:data=r.read()
 if hashlib.sha256(data).hexdigest()!=source["digests"]["sha256"]:raise RuntimeError("Source digest mismatch")
 archive.write_bytes(data)
directory=ROOT/"build-tools"/source["filename"].removesuffix(".tar.gz")
if not directory.exists():
 with tarfile.open(archive) as t:t.extractall(ROOT/"build-tools",filter="data")
pyproject=tomllib.loads((directory/"pyproject.toml").read_text())
maturin=pyproject.get("tool",{}).get("maturin",{})
print("rpds source build configuration",maturin,flush=True)
cargo=tomllib.loads((directory/"Cargo.toml").read_text())
module=maturin.get("module-name",cargo.get("lib",{}).get("name","rpds"))
package_dir=directory/maturin.get("python-source",".")/module.split(".")[0]
ndk=ROOT/"build-tools/android-sdk/ndk/27.2.12479018/toolchains/llvm/prebuilt/windows-x86_64/bin"
env=os.environ.copy()
env.update({"CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER":str(ndk/"aarch64-linux-android24-clang.cmd"),"CC_aarch64_linux_android":str(ndk/"aarch64-linux-android24-clang.cmd"),"AR_aarch64_linux_android":str(ndk/"llvm-ar.exe"),"PYO3_CONFIG_FILE":str(ROOT/"build-tools/pyo3-android313.txt"),"PYTHON":sys.executable,"CARGO_TARGET_DIR":str(ROOT/"artifacts/rpds-target"),"PYTHONUTF8":"1","RUSTFLAGS":"-C link-arg=-Wl,-z,max-page-size=16384"})
from importlib import import_module
import_module("android-python-link").link_android_python(ROOT,env)
subprocess.run(["cargo","build","--release","--target","aarch64-linux-android","--features","pyo3/extension-module"],cwd=directory,env=env,check=True)
binary=next((ROOT/"artifacts/rpds-target/aarch64-linux-android/release").glob("*.so"))
wheel_dir=ROOT/"build-tools/wheels";wheel_dir.mkdir(exist_ok=True)
wheel=wheel_dir/("rpds_py-"+version+"-cp313-cp313-android_24_arm64_v8a.whl")
info="rpds_py-"+version+".dist-info"
with zipfile.ZipFile(wheel,"w",zipfile.ZIP_DEFLATED) as z:
 for p in package_dir.rglob("*"):
  if p.is_file():z.writestr(module.split(".")[0]+"/"+p.relative_to(package_dir).as_posix(),p.read_bytes())
 z.writestr(module.replace(".","/")+".so",binary.read_bytes())
 z.writestr(info+"/METADATA","Metadata-Version: 2.1\nName: rpds-py\nVersion: "+version+"\nRequires-Python: >=3.9\nLicense: MIT\n")
 z.writestr(info+"/WHEEL","Wheel-Version: 1.0\nGenerator: dreamtalk-android-build\nRoot-Is-Purelib: false\nTag: cp313-cp313-android_24_arm64_v8a\n")
 for p in directory.glob("LICENSE*"):z.writestr(info+"/"+p.name,p.read_bytes())
 write_record(z,info)
print("BUILT",wheel.name,hashlib.sha256(wheel.read_bytes()).hexdigest(),flush=True)
