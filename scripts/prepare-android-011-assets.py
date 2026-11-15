from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil,re,importlib.util
ROOT=Path(__file__).resolve().parents[1];delivery=ROOT/'artifacts/android-preview';out=ROOT/'artifacts/github-android-personal-011';stage=out/'upload'
report=json.loads((delivery/'apk-verification.json').read_text(encoding='utf-8'));smoke=json.loads((ROOT/'artifacts/android-startup-regression/fixed-startup-smoke.json').read_text(encoding='utf-8'));apk=delivery/report['apk']
assert report['sha256']==smoke['sha256']==hashlib.sha256(apk.read_bytes()).hexdigest(),'Final APK and executed smoke do not match'
assert all(smoke[k] for k in ['world_list','world_creation','player_initialization','background_resume','restart_persistence']) and not smoke['app_crash_recorded']
receipt=json.loads((delivery/'build-receipt-0.1.1.json').read_text(encoding='utf-8'));receipt.update({'bytes':report['bytes'],'sha256':report['sha256'],'created_at_jst':datetime.now(timezone(timedelta(hours=9))).isoformat(),'privacy_entries_inspected':report['entries_inspected'],'native_libraries_16kb_aligned':len(report['native_libraries']),'startup_dependency_closure':report['native_dependency_closure'],'brand':report['brand'],'python_extension_linkage':report['python_extension_linkage'],'runtime_test':smoke})
(delivery/'build-receipt-0.1.1.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');(delivery/(apk.name+'.sha256')).write_text(report['sha256']+'  '+apk.name+'\n',encoding='ascii')
for name in [apk.name,apk.name+'.sha256']:shutil.copyfile(delivery/name,stage/name)
shutil.copyfile(delivery/'build-receipt-0.1.1.json',stage/'android-build-receipt.json');shutil.copyfile(delivery/'体验指南-0.1.1.md',stage/'android-preview-guide.md')
p=out/'release-notes.md';notes=p.read_text(encoding='utf-8');notes=re.sub(r'(APK SHA-256：`)[0-9a-f]{64}(`)',lambda m:m[1]+report['sha256']+m[2],notes)
if '系统栏' not in notes:notes=notes.replace('### 实际验证与限制','- 修正深色系统栏、安全区与软键盘布局；实际软键盘输入已纳入隔离运行检查。\n\n### 实际验证与限制')
p.write_text(notes,encoding='utf-8')
spec=importlib.util.spec_from_file_location('privacy',ROOT/'scripts/check-release-privacy.py');gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
for file in [*stage.iterdir(),p]:assert not gate.findings(file.name,file.read_bytes(),source=False),file.name
(out/'asset-manifest.json').write_text(json.dumps([{'name':x.name,'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in sorted(stage.iterdir())],indent=2),encoding='utf-8')
print(json.dumps({'apk':apk.name,'sha256':report['sha256'],'MiB':round(report['bytes']/1048576,1),'executed_same_apk':True,'assets':4,'privacy_findings':0},ensure_ascii=False))
