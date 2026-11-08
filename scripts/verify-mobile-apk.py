from pathlib import Path
import base64,hashlib,importlib.util,io,json,struct,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('privacy_gate',ROOT/'scripts/check-release-privacy.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
apk=Path(sys.argv[1]).resolve()
assert apk.is_relative_to((ROOT/'artifacts').resolve()),'APK must be inside artifacts'
from importlib import import_module
dependency_reader=import_module("verify-android-native-deps")
problems=[];libraries=[];count=0;migrations=[];core_payload=set();python_extensions=[]
def scan(bundle,prefix=''):
 global count
 for member in bundle.infolist():
  if member.is_dir():continue
  name=prefix+member.filename;data=bundle.read(member);count+=1
  # The same reviewed public template has a different container path on Android.
  checked='core/_internal/livingworld/infrastructure/examples/campus.json' if member.filename=='livingworld/infrastructure/examples/campus.json' else name
  problems.extend(name+': '+finding for finding in gate.findings(checked,data,source=False))
  if member.filename.endswith('.imy'):
   with zipfile.ZipFile(io.BytesIO(data)) as nested:scan(nested,name+'!/')
  if member.filename.startswith('livingworld/'):core_payload.add(member.filename)
  if 'livingworld/infrastructure/persistence/migrations/versions/' in member.filename and member.filename.endswith('.py'):migrations.append(member.filename)
  if data[:4]==b'\x7fELF':
   assert data[4:6]==b'\x02\x01',name+': unsupported ELF format'
   off=struct.unpack_from('<Q',data,32)[0];size,num=struct.unpack_from('<HH',data,54)
   align=[struct.unpack_from('<Q',data,off+i*size+48)[0] for i in range(num) if struct.unpack_from('<I',data,off+i*size)[0]==1]
   if member.filename in ('pydantic_core/_pydantic_core.so','rpds.so'):
    dependencies=dependency_reader.needed(data)
    assert 'libpython3.13.so' in dependencies,name+': Android CPython extension must explicitly link its runtime'
    python_extensions.append({'path':name,'needed':dependencies})
   libraries.append({'path':name,'load_alignment':align})
   if not align or min(align)<16384:problems.append(name+': ELF alignment below 16KB')
with zipfile.ZipFile(apk) as z:scan(z)
from importlib import import_module
brand=import_module("verify-android-brand").verify(apk)
native_dependencies=import_module("verify-android-native-deps").verify(apk)
assert len(migrations)>=65,'Alembic source migrations absent'
assert any(x.endswith('bootstrap/mobile_host.pyc') or x.endswith('bootstrap/mobile_host.py') for x in core_payload),'Mobile host absent'
for p in (ROOT/'apps/web/dist').rglob('*.js'):
 if b'__DREAMTALK_MOBILE_TEST_HOST__' in p.read_bytes():problems.append('production test bridge present')
report={'apk':apk.name,'bytes':apk.stat().st_size,'sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'entries_inspected':count,'native_libraries':libraries,'alembic_source_migrations':len(migrations),'privacy_findings':problems,'brand':brand,'native_dependency_closure':native_dependencies,'python_extension_linkage':python_extensions,'evidence':'static APK payload, not Android runtime or user acceptance'}
(ROOT/'artifacts/android-preview/apk-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='native_libraries'},ensure_ascii=False))
if problems:raise SystemExit('APK static verification failed')
