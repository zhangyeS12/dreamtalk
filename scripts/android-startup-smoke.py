from pathlib import Path
import subprocess,time,json,re,xml.etree.ElementTree as ET,hashlib
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/android-startup-regression';session=json.loads((OUT/'emulator-session.json').read_text());assert session['serial']=='emulator-5570' and session['adb_port']==5039
PREFIX=[str(Path(session['sdk'])/'platform-tools/adb.exe'),'-P','5039','-s','emulator-5570']
def run(*args,timeout=90):return subprocess.run(PREFIX+list(args),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
def tree():
 run('shell','uiautomator','dump','/sdcard/dreamtalk-smoke-ui.xml');text=run('shell','cat','/sdcard/dreamtalk-smoke-ui.xml').stdout
 (OUT/'latest-smoke-ui.xml').write_text(text,encoding='utf-8');return ET.fromstring(text)
def text_of(t):return ' '.join(n.get('text','') for n in t.iter('node'))
def tap(node):
 b=list(map(int,re.findall(r'\d+',node.get('bounds'))));assert len(b)==4;run('shell','input','tap',str((b[0]+b[2])//2),str((b[1]+b[3])//2))
def wait_for(text,seconds=60):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  assert run('shell','pidof','app.livingworld.desktop').stdout.strip(),'App process exited'
  t=tree()
  if text.startswith('AndroidRegression'):
   if any(text in n.get('text','') and '打开世界' in n.get('text','') for n in t.iter('node')):return t
  elif text in text_of(t):return t
  if '暂时未能打开' in text_of(t):
   button=next((n for n in t.iter('node') if n.get('text')=='复制启动诊断'),None)
   if button is not None:tap(button);time.sleep(.5)
   log=run('logcat','-d','-s','dreamtalk-startup:E','dreamtalk-diagnostics:I','*:S').stdout;(OUT/'smoke-startup-errors.txt').write_text(log,encoding='utf-8')
   raise AssertionError('Core startup failed; redacted diagnostics saved')
  time.sleep(1)
 raise AssertionError('UI deadline exceeded waiting for '+text)
def capture(name):
 with (OUT/name).open('wb') as image:subprocess.run(PREFIX+['exec-out','screencap','-p'],stdout=image,check=True)
if __name__=='__main__':
 assert run('shell','getprop','ro.kernel.qemu').stdout.strip()=='1','Real devices are not permitted by this test'
 run('shell','settings','put','secure','show_ime_with_hard_keyboard','1')
 apk=ROOT/'artifacts/android-preview/dreamtalk-android-0.1.1-arm64.apk';r=run('install','-r',str(apk));assert r.returncode==0,(r.stdout,r.stderr)
 run('shell','am','force-stop','app.livingworld.desktop');run('logcat','-b','crash','-c');run('shell','am','start','-W','-n','app.livingworld.desktop/.MainActivity')
 t=wait_for('我的世界',90);capture('fixed-world-list.png');print('PASS: real Android world list reached',flush=True)
 name='AndroidRegression'+str(int(time.time()))
 if not any(name in n.get('text','') and '打开世界' in n.get('text','') for n in t.iter('node')):
  field=next(n for n in t.iter('node') if n.get('class')=='android.widget.EditText');tap(field);run('shell','input','text',name)
  capture('fixed-keyboard.png')
  ime=run('shell','dumpsys','input_method').stdout
  if 'mInputShown=true' in ime:run('shell','input','keyevent','4')
  t=tree();tap(next(n for n in t.iter('node') if n.get('text')=='创建世界'))
  t=wait_for(name);print('PASS: test world created from Android UI',flush=True)
 tap(next(n for n in t.iter('node') if name in n.get('text','') and '打开世界' in n.get('text','')));t=wait_for('从家开始')
 tap(next(n for n in t.iter('node') if n.get('text')=='从家开始'));t=wait_for('会话');capture('fixed-workspace.png');print('PASS: player identity initialized from Android UI',flush=True)
 run('shell','input','keyevent','3');time.sleep(2);run('shell','am','start','-W','-n','app.livingworld.desktop/.MainActivity');wait_for('会话');print('PASS: background and resume',flush=True)
 for attempt in range(3):
  run('shell','am','force-stop','app.livingworld.desktop');run('shell','am','start','-W','-n','app.livingworld.desktop/.MainActivity');t=wait_for('我的世界');assert name in text_of(t),'World missing after restart'
  print('PASS: world persisted after force-stop and restart '+str(attempt+1),flush=True)
 capture('fixed-reopened.png')
 crash=run('logcat','-b','crash','-d').stdout;(OUT/'fixed-crash-buffer.txt').write_text(crash,encoding='utf-8');assert 'Process: app.livingworld.desktop' not in crash,'App crash recorded'
 record={'apk':apk.name,'sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'android_version':'15','host_abi':'x86_64','app_abi':'arm64-v8a','native_bridge':'libndk_translation.so','test_world_name':name,'in_place_update':True,'world_list':True,'world_creation':True,'player_initialization':True,'background_resume':True,'restart_persistence':True,'cold_restarts_checked':3,'app_crash_recorded':False,'real_api_used':False,'real_user_data_used':False,'vivo_x80_acceptance':'pending'}
 (OUT/'fixed-startup-smoke.json').write_text(json.dumps(record,indent=2),encoding='utf-8');print(json.dumps(record),flush=True)
