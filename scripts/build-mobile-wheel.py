from wheel_record import write_record
from pathlib import Path
import hashlib,json,zipfile
root=Path(__file__).resolve().parents[1]
source=root/"services/core/src/livingworld"
wheel_dir=root/"build-tools/wheels";wheel_dir.mkdir(exist_ok=True)
target=wheel_dir/"dreamtalk_core-0.1.0-py3-none-any.whl"
info="dreamtalk_core-0.1.0.dist-info"
with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as bundle:
 for path in sorted(source.rglob("*")):
  if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc",".pyo"):
   bundle.writestr("livingworld/"+path.relative_to(source).as_posix(),path.read_bytes())
 bundle.writestr(info+"/METADATA","Metadata-Version: 2.1\nName: dreamtalk-core\nVersion: 0.1.0\nLicense: Apache-2.0\nRequires-Python: >=3.12\n")
 bundle.writestr(info+"/WHEEL","Wheel-Version: 1.0\nGenerator: dreamtalk-mobile-build\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
 bundle.writestr(info+"/LICENSE",(root/"LICENSE").read_bytes())
 write_record(bundle,info)
print(target.name,hashlib.sha256(target.read_bytes()).hexdigest())
