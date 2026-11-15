from pathlib import Path
import sys,json
root=Path(r"D:\dreamtalk安卓版")
native=json.load(sys.stdin)
(root/"apps/mobile/src-tauri/src/token_bound.rs").write_text(native,encoding="utf-8")
cargo=root/"apps/mobile/src-tauri/Cargo.toml"
s=cargo.read_text();s += '\nserde = { version = "1", features = ["derive"] }\nserde_json = "1"\ndeepseek-recipe = "=0.1.0"\ndeepseek-recipe-encoding = "=0.1.0"\njni = "0.21"\n'
cargo.write_text(s)
p=root/"apps/mobile/src-tauri/src/lib.rs";s=p.read_text();p.write_text("mod token_bound;\n"+s)
p=root/"plugins/android/src/main/java/ExamplePlugin.kt";s=p.read_text();s=s.replace("    private val worker", "    external fun tokenUpperBound(payload: String): Long\n    private val worker");p.write_text(s)
p=root/"plugins/android/src/main/java/Example.kt";p.write_text("package app.livingworld.mobile\n")
for p in (root/"plugins/android/src").rglob("*.kt"):
 s=p.read_text();s=s.replace("com.plugin.mobile-coreapp.livingworld.mobile","app.livingworld.mobile");p.write_text(s)
p=root/"services/core/src/livingworld/infrastructure/llm/request_bounds.py"
s=p.read_text();s=s.replace("class ProviderRequestUsageBounder:", "_mobile_counter = None\n\n\ndef configure_mobile_counter(counter):\n    global _mobile_counter\n    _mobile_counter = counter\n\n\nclass ProviderRequestUsageBounder:")
s=s.replace("self._helper.is_file()","(self._helper.is_file() or _mobile_counter is not None)")
start=s.index("                result = subprocess.run(")
end=s.index("                if type(upper) is not int",start)
original=s[start:end]
s=s[:start]+'                if _mobile_counter is not None:\n                    upper = _mobile_counter(data.decode("utf-8"))\n                else:\n'+ "".join("    "+line+"\n" for line in original.splitlines())+s[end:]
p.write_text(s)
p=root/"services/core/src/livingworld/bootstrap/mobile_host.py"
s=p.read_text();s=s.replace('    _credentials.complete_sync(secure_store_available=True)','    _credentials.complete_sync(secure_store_available=True)\n    if hasattr(_host, "tokenUpperBound"):\n        from livingworld.infrastructure.llm.request_bounds import configure_mobile_counter\n        configure_mobile_counter(lambda payload: int(_host.tokenUpperBound(payload)))')
s=s.replace('            from livingworld.infrastructure.llm.production_config import parse_configuration\n            parse_configuration(production_document(updated))','            from livingworld.infrastructure.llm.production_config import load_configuration\n            check_path = _root / ("model-check-" + str(uuid4()) + ".json")\n            _root.mkdir(parents=True, exist_ok=True)\n            try:\n                check_path.write_text(json.dumps(production_document(updated)), encoding="utf-8")\n                load_configuration(check_path)\n            finally:\n                check_path.unlink(missing_ok=True)')
p.write_text(s)
p=root/"apps/web/src/mobile/MobileApp.tsx";s=p.read_text();s=s.replace('import { PlayerPersonaEditor } from "../PlayerPersonaEditor";\n',"");s=s.replace('<PlayerPersonaEditor client={client} worldId={world.world_id} onDirtyChange={setDirty} />',"");p.write_text(s)
source=Path(r"D:\LivingWorld\scripts\settings-save-transport.mjs")
target=root/"scripts/settings-save-transport.mjs"
target.write_bytes(source.read_bytes())
print("Adapted trustworthy native request bounds and fixed model validation")
