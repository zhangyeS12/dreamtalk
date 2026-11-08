from pathlib import Path
import json,shutil

def link_android_python(root,env):
    cache=Path(json.loads((root/"build-tools/temporary-build-location.json").read_text())["directory"])
    marker=json.loads((cache/".dreamtalk-build-cache.json").read_text())
    assert Path(marker["source"]).resolve()==root.resolve() and marker["temporary_build_only"]
    directory=cache/"python313-link";directory.mkdir(exist_ok=True)
    source=root/"plugins/android/build/python/jniLibs/release/arm64-v8a/libpython3.13.so"
    target=directory/source.name;shutil.copyfile(source,target)
    # Android extension modules cannot depend on desktop-style global symbol lookup.
    # Link the exact Chaquopy Python runtime and reject unresolved extension symbols.
    flags=" -C link-arg=-Wl,--no-as-needed -C link-arg="+target.as_posix()+" -C link-arg=-Wl,--no-undefined"
    env["RUSTFLAGS"]=env.get("RUSTFLAGS","")+flags
