import pathlib,json
root=pathlib.Path(r"D:\dreamtalk安卓版")
files=json.load(__import__("sys").stdin)
for name,content in files.items():
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content,encoding="utf-8")
cli=root/"services/core/src/livingworld/bootstrap/cli.py"
s=cli.read_text(encoding="utf-8")
s=s.replace("    developer_tools: bool = False,\n) -> None:","    developer_tools: bool = False,\n    native_host=None,\n) -> None:")
anchor="        llm_session = await start_production_llm_session(config.llm_config_path, database, logger)\n"
assert anchor in s
s=s.replace(anchor,anchor+"        if native_host is not None:\n            native_host.attach(llm_session, maintenance, shutdown)\n")
cli.write_text(s,encoding="utf-8")
gradle=root/"apps/mobile/src-tauri/gen/android/build.gradle.kts"
s=gradle.read_text();s=s.replace('classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.25")','classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.25")\n        classpath("com.chaquo.python:gradle:17.2.0")')
gradle.write_text(s)
props=root/"apps/mobile/src-tauri/gen/android/gradle.properties"
with props.open("a",encoding="utf-8") as f:f.write("\nandroid.overridePathCheck=true\n")
manifest=root/"apps/mobile/src-tauri/gen/android/app/src/main/AndroidManifest.xml"
s=manifest.read_text();s=s.replace('android:icon="@mipmap/ic_launcher"','android:allowBackup="false"\n        android:networkSecurityConfig="@xml/network_security_config"\n        android:icon="@mipmap/ic_launcher"')
s=s.replace('android:name=".MainActivity"','android:windowSoftInputMode="adjustResize"\n            android:name=".MainActivity"')
manifest.write_text(s)
print("Wrote native host and Python runtime adapters")
