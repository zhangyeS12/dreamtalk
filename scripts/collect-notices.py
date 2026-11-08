from pathlib import Path
import json,subprocess,email
root=Path(__file__).resolve().parents[1]
parts=['dreamtalk Android preview 0.1.0\nCopyright notices and third-party licenses\n\n'+(root/'LICENSE').read_text()]
if (root/'NOTICE').is_file():parts.append((root/'NOTICE').read_text())
lock=json.loads((root/'package-lock.json').read_text())
for name,item in sorted(lock['packages'].items()):
 if not name.startswith('node_modules/') or item.get('dev'):continue
 path=root/name
 parts.append('\nNPM: '+name.removeprefix('node_modules/')+' '+item.get('version','')+'\nLicense: '+str(item.get('license','see license text')))
 for f in sorted(path.iterdir()) if path.is_dir() else []:
  if f.is_file() and f.name.lower().split('.')[0] in ('license','licence','copying','notice'):parts.append(f.read_text(encoding='utf-8',errors='replace'))
meta=json.loads(subprocess.check_output(['cargo','metadata','--offline','--format-version','1','--filter-platform','aarch64-linux-android'],cwd=root/'apps/mobile/src-tauri'))
selected={x['id'] for x in meta['resolve']['nodes']}
for pkg in sorted(meta['packages'],key=lambda x:x['name']):
 if pkg['id'] not in selected:continue
 parts.append('\nRUST: '+pkg['name']+' '+pkg['version']+'\nLicense: '+str(pkg.get('license','see license text')))
 for f in sorted(Path(pkg['manifest_path']).parent.iterdir()):
  if f.is_file() and f.name.lower().split('.')[0].split('-')[0] in ('license','licence','copying','notice'):parts.append(f.read_text(encoding='utf-8',errors='replace'))
for group in ['common','arm64-v8a']:
 for path in sorted((root/'plugins/android/build/python/pip/release'/group).glob('*.dist-info')):
  metadata=email.message_from_bytes((path/'METADATA').read_bytes()) if (path/'METADATA').is_file() else {}
  parts.append('\nPYTHON: '+str(metadata.get('Name',path.name))+' '+str(metadata.get('Version',''))+'\nLicense: '+str(metadata.get('License-Expression',metadata.get('License','see license text'))))
  for f in sorted(path.rglob('*')):
   if f.is_file() and (f.name.lower().startswith(('license','licence','copying','notice','ftl.')) or 'licenses' in f.parts):parts.append(f.read_text(encoding='utf-8',errors='replace'))
parts.append('\nCPython 3.13\n'+(Path(__import__('sys').base_prefix)/'LICENSE.txt').read_text())
parts.append('\nChaquopy 17.2.0: MIT. https://github.com/chaquo/chaquopy/blob/master/LICENSE.txt\nAndroidX: Apache-2.0. https://source.android.com/license\nFreeType 2.9.1 rebuilt from official source with 16KB ELF alignment; FreeType License, see FTL.TXT above.\n')
output='\n'.join(parts)
out=root/'apps/web/public/third-party-notices.txt';out.parent.mkdir(exist_ok=True);out.write_text(output,encoding='utf-8')
(root/'docs/third-party-notices.txt').write_text(output,encoding='utf-8')
print('Notices bytes',out.stat().st_size,'rust packages',len(selected))
