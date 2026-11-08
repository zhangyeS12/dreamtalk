from pathlib import Path
import json,struct,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
def needed(data):
 assert data[:6]==b'\x7fELF\x02\x01','Unsupported ELF'
 off=struct.unpack_from('<Q',data,40)[0];size,num=struct.unpack_from('<HH',data,58)
 sections=[struct.unpack_from('<IIQQQQIIQQ',data,off+i*size) for i in range(num)]
 result=[]
 for section in sections:
  if section[1]!=6:continue
  strings=sections[section[6]][4]
  for pos in range(section[4],section[4]+section[5],16):
   tag,value=struct.unpack_from('<QQ',data,pos)
   if tag==0:break
   if tag==1:
    start=strings+value;end=data.index(b'\x00',start);result.append(data[start:end].decode('ascii'))
 return result
def verify(apk):
 systems=json.loads((ROOT/'build-tools/android-sdk/ndk/27.2.12479018/meta/system_libs.json').read_text())
 allowed={name for name,minimum in systems.items() if int(minimum)<=24}
 with zipfile.ZipFile(apk) as z:
  libraries={Path(n).name:n for n in z.namelist() if n.startswith('lib/arm64-v8a/') and n.endswith('.so')}
  missing={name:[dep for dep in needed(z.read(path)) if dep not in libraries and dep not in allowed] for name,path in libraries.items()}
  missing={name:deps for name,deps in missing.items() if deps}
  assert not missing,'Startup libraries missing from APK native directory: '+json.dumps(missing)
 return {'packaged_startup_libraries':len(libraries),'unresolved_dependencies':[]}
if __name__=='__main__':print(json.dumps(verify(Path(sys.argv[1]))))
