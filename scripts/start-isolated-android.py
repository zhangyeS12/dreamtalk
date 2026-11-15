from pathlib import Path
import os,json,subprocess,time
ROOT=Path(__file__).resolve().parents[1]
cache=Path(json.loads((ROOT/'build-tools/temporary-build-location.json').read_text())['directory'])
assert json.loads((cache/'.dreamtalk-build-cache.json').read_text())['source']==str(ROOT)
sdk=Path(r'D:\dreamtalk/android-build-link/build-tools/android-sdk');home=cache/'emulator-home';avds=cache/'emulator-avd';home.mkdir(exist_ok=True);avds.mkdir(exist_ok=True)
name='DreamtalkCrashTest001';profile=avds/(name+'.avd');profile.mkdir(exist_ok=True)
(avds/(name+'.ini')).write_text('avd.ini.encoding=UTF-8\npath='+profile.as_posix()+'\ntarget=android-35\n')
config={'AvdId':name,'avd.ini.displayname':'dreamtalk isolated crash regression','abi.type':'x86_64','hw.cpu.arch':'x86_64','hw.cpu.ncore':'2','hw.ramSize':'4096','hw.lcd.width':'1080','hw.lcd.height':'2400','hw.lcd.density':'420','hw.gpu.enabled':'yes','hw.gpu.mode':'swiftshader','hw.keyboard':'yes','hw.audioInput':'no','hw.audioOutput':'no','disk.dataPartition.size':'4G','image.sysdir.1':(sdk/'system-images/android-35/google_apis/x86_64').as_posix()+'/','tag.id':'google_apis','tag.display':'Google APIs','target':'android-35','showDeviceFrame':'no','fastboot.forceColdBoot':'yes'}
(profile/'config.ini').write_text('\n'.join(k+'='+v for k,v in config.items())+'\n')
env=os.environ.copy();env.update({'ANDROID_HOME':str(sdk),'ANDROID_SDK_ROOT':str(sdk),'ANDROID_EMULATOR_HOME':str(home),'ANDROID_USER_HOME':str(home),'ANDROID_AVD_HOME':str(avds),'ANDROID_ADB_SERVER_PORT':'5039','ADB_VENDOR_KEYS':str(home/'adbkey'),'ANDROID_SDK_HOME':str(home)})
adb=sdk/'platform-tools/adb.exe'
subprocess.run([str(adb),'-P','5039','--one-device','emulator-5570','start-server'],env=env,check=True)
out=ROOT/'artifacts/android-startup-regression';out.mkdir(exist_ok=True)
log=(out/'emulator-console.log').open('wb')
command=[str(sdk/'emulator/emulator.exe'),'-avd',name,'-port','5570','-no-window','-no-audio','-no-boot-anim','-no-snapshot','-gpu','swiftshader','-feature','-Vulkan','-camera-back','none','-camera-front','none']
p=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
(out/'emulator-session.json').write_text(json.dumps({'pid':p.pid,'serial':'emulator-5570','adb_port':5039,'profile':str(profile),'sdk':str(sdk)},indent=2))
print('Started isolated headless emulator',p.pid,flush=True)
for i in range(90):
 if p.poll() is not None:raise RuntimeError('Emulator exited, see emulator-console.log')
 result=subprocess.run([str(adb),'-P','5039','-s','emulator-5570','shell','getprop','sys.boot_completed'],capture_output=True,text=True,timeout=8,env=env)
 if result.stdout.strip()=='1':
  print('Android emulator boot completed',flush=True)
  for prop in ['ro.build.version.release','ro.product.cpu.abilist','ro.dalvik.vm.native.bridge']:
   value=subprocess.check_output([str(adb),'-P','5039','-s','emulator-5570','shell','getprop',prop],env=env,text=True).strip();print(prop,value,flush=True)
  break
 if i%5==0:print('Waiting for isolated Android boot',i*3,'seconds',flush=True)
 time.sleep(3)
else:raise RuntimeError('Emulator boot deadline exceeded')
