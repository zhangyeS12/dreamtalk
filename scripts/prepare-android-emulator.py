from pathlib import Path
import xml.etree.ElementTree as ET,urllib.request,zipfile,hashlib,concurrent.futures,json
ROOT=Path(__file__).resolve().parents[1]
def local(tag):return tag.split('}')[-1]
def txt(e,n):return next((x.text for x in e.iter() if local(x.tag)==n),None)
def choose(file,wanted):
 found={}
 for pkg in ET.parse(file).getroot():
  if local(pkg.tag)!='remotePackage' or pkg.get('path') not in wanted:continue
  channel=next((x.get('ref') for x in pkg if local(x.tag)=='channelRef'),'channel-0')
  if channel!='channel-0':continue
  for arc in pkg.iter():
   if local(arc.tag)!='archive' or txt(arc,'host-os') not in [None,'windows']:continue
   complete=next((x for x in arc if local(x.tag)=='complete'),None)
   if complete is None:continue
   url=txt(complete,'url');base='https://dl.google.com/android/repository/'
   if pkg.get('path').startswith('system-images'):base+='sys-img/google_apis/'
   found[pkg.get('path')]={'package':pkg.get('path'),'url':base+url,'sha1':txt(complete,'checksum'),'size':int(txt(complete,'size'))};break
 assert set(found)==set(wanted),(wanted,found)
 return list(found.values())
def install(p):
 target=ROOT/'build-tools/android-sdk'/p['package'].replace(';','/')
 if (target/'.dreamtalk-installed').exists():print('Already installed',p['package'],flush=True);return
 path=ROOT/'build-tools'/p['url'].rsplit('/',1)[-1]
 if not path.is_file() or hashlib.file_digest(path.open('rb'),'sha1').hexdigest()!=p['sha1']:
  part=path.with_suffix('.part');digest=hashlib.sha1();count=0;reported=-1
  with urllib.request.urlopen(p['url'],timeout=60) as response,part.open('wb') as out:
   while chunk:=response.read(1024*1024):
    out.write(chunk);digest.update(chunk);count+=len(chunk);percent=count*10//p['size']
    if percent!=reported:print(p['package'],count//1048576,'MiB',flush=True);reported=percent
  assert digest.hexdigest()==p['sha1'],'Download hash mismatch'
  part.replace(path)
 stage=ROOT/'build-tools'/('extract-'+p['package'].replace(';','-'));stage.mkdir(exist_ok=True)
 with zipfile.ZipFile(path) as bundle:
  for name in bundle.namelist():assert (stage/name).resolve().is_relative_to(stage.resolve()),name
  bundle.extractall(stage)
 dirs=list(stage.iterdir());content=dirs[0] if len(dirs)==1 and dirs[0].is_dir() else stage
 assert not target.exists(),'Existing SDK target must be inspected'
 target.parent.mkdir(parents=True,exist_ok=True);content.rename(target);(target/'.dreamtalk-installed').write_text(p['url'],encoding='utf-8')
 print('Installed',p['package'],flush=True)
if __name__=='__main__':
 import sys
 wanted=['system-images;android-35;google_apis;x86_64'] if '--image' in sys.argv else ['emulator','platform-tools']
 file=ROOT/'build-tools'/('system-image-repository.xml' if '--image' in sys.argv else 'emulator-repository.xml')
 selected=choose(file,wanted)
 (ROOT/'build-tools'/('emulator-image-selection.json' if '--image' in sys.argv else 'emulator-tool-selection.json')).write_text(json.dumps(selected,indent=2),encoding='utf-8')
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(install,selected))
