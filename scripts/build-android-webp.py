"""Build the missing upstream Pillow WebP extension for the pinned Android runtime."""

import hashlib
import json
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from wheel_record import write_record

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "artifacts/android-webp-build"
SOURCES = [
    (
        "pillow-11.0.0",
        "https://files.pythonhosted.org/packages/source/p/pillow/pillow-11.0.0.tar.gz",
        "72bacbaf24ac003fea9bff9837d1eedb6088758d41e100c1552930151f677739",
    ),
    (
        "libwebp-1.6.0",
        "https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-1.6.0.tar.gz",
        "e4ab7009bf0629fd11982d4c2aa83964cf244cffba7347ecd39019a9e38c4564",
    ),
]
BUILD.mkdir(parents=True, exist_ok=True)
for name, url, digest in SOURCES:
    archive = ROOT / "build-tools" / (name + ".tar.gz")
    if not archive.exists():
        with urllib.request.urlopen(url, timeout=60) as response:
            archive.write_bytes(response.read())
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest, (
        "image_source_digest_mismatch"
    )
    if not (ROOT / "build-tools" / name).exists():
        with tarfile.open(archive) as bundle:
            bundle.extractall(ROOT / "build-tools", filter="data")

runtime_archives = list(
    (
        ROOT
        / "build-tools/gradle-user/caches/modules-2/files-2.1/com.chaquo.python/target/3.13.16-0"
    ).rglob("*arm64-v8a.zip")
)
assert len(runtime_archives) == 1, "pinned_android_python_headers_missing"
runtime = runtime_archives[0]
with zipfile.ZipFile(runtime) as bundle:
    for name in bundle.namelist():
        if name.startswith("include/") and not name.endswith("/"):
            target = BUILD / "runtime" / name
            assert target.resolve().is_relative_to((BUILD / "runtime").resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(name))
cache = Path(
    json.loads((ROOT / "build-tools/temporary-build-location.json").read_text())["directory"]
)
marker = json.loads((cache / ".dreamtalk-build-cache.json").read_text())
assert marker["temporary_build_only"] and Path(marker["source"]).resolve() == ROOT.resolve()
python_lib = ROOT / "plugins/android/build/python/jniLibs/release/arm64-v8a/libpython3.13.so"
assert python_lib.is_file()
project = BUILD / "project"
project.mkdir(exist_ok=True)
cmake_text = """cmake_minimum_required(VERSION 3.16)
project(dreamtalk_pillow_webp C)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_ANIM_UTILS OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_CWEBP OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_DWEBP OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_GIF2WEBP OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_IMG2WEBP OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_VWEBP OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_WEBPINFO OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_WEBPMUX OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_EXTRAS OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_FUZZTEST OFF CACHE BOOL "" FORCE)
set(WEBP_BUILD_LIBWEBPMUX ON CACHE BOOL "" FORCE)
add_subdirectory("@WEBP_SOURCE@" webp)
add_library(_webp SHARED "@PILLOW_SOURCE@/src/_webp.c")
target_include_directories(_webp PRIVATE
    "@PYTHON_INCLUDE@" "@PILLOW_SOURCE@/src" "@WEBP_SOURCE@/src")
target_compile_definitions(_webp PRIVATE HAVE_PROTOTYPES=1 STDC_HEADERS=1)
target_link_libraries(_webp PRIVATE libwebpmux webpdemux webp "@PYTHON_LIBRARY@" m dl)
target_link_options(_webp PRIVATE "-Wl,-z,max-page-size=16384" "-Wl,--no-undefined")
set_target_properties(_webp PROPERTIES PREFIX "" OUTPUT_NAME "_webp")
"""
for key, value in {
    "WEBP_SOURCE": ROOT / "build-tools/libwebp-1.6.0",
    "PILLOW_SOURCE": ROOT / "build-tools/pillow-11.0.0",
    "PYTHON_INCLUDE": BUILD / "runtime/include/python3.13",
    "PYTHON_LIBRARY": python_lib,
}.items():
    cmake_text = cmake_text.replace("@" + key + "@", value.as_posix())
(project / "CMakeLists.txt").write_text(cmake_text, encoding="utf-8")
vs_cmake = (
    "C:/Program Files/Microsoft Visual Studio/18/Community/Common7/IDE/"
    "CommonExtensions/Microsoft/CMake"
)
cmake = shutil.which("cmake") or vs_cmake + "/CMake/bin/cmake.exe"
ninja = shutil.which("ninja") or vs_cmake + "/Ninja/ninja.exe"
command = [
    cmake,
    "-S",
    str(project),
    "-B",
    str(BUILD / "native"),
    "-G",
    "Ninja",
    "-DCMAKE_MAKE_PROGRAM=" + ninja,
    "-DCMAKE_BUILD_TYPE=Release",
    "-DCMAKE_TOOLCHAIN_FILE=" + str(cache / "ndk/build/cmake/android.toolchain.cmake"),
    "-DANDROID_ABI=arm64-v8a",
    "-DANDROID_PLATFORM=android-24",
]
subprocess.run(command, check=True)
subprocess.run(
    [cmake, "--build", str(BUILD / "native"), "--target", "_webp", "--parallel", "4"], check=True
)
binary = BUILD / "native/_webp.so"
wheel = (
    ROOT / "build-tools/wheels/dreamtalk_pillow_webp-11.0.0.1-cp313-cp313-android_24_arm64_v8a.whl"
)
info = "dreamtalk_pillow_webp-11.0.0.1.dist-info"
with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as bundle:
    bundle.writestr("PIL/_webp.so", binary.read_bytes())
    bundle.writestr(
        info + "/METADATA",
        "Metadata-Version: 2.1\nName: dreamtalk-pillow-webp\nVersion: 11.0.0.1\n"
        "Requires-Dist: Pillow==11.0.0\nLicense: HPND AND BSD-3-Clause\n",
    )
    bundle.writestr(
        info + "/WHEEL",
        "Wheel-Version: 1.0\nGenerator: dreamtalk-android-build\nRoot-Is-Purelib: false\n"
        "Tag: cp313-cp313-android_24_arm64_v8a\n",
    )
    for name, source in [
        ("Pillow-LICENSE", ROOT / "build-tools/pillow-11.0.0/LICENSE"),
        ("libwebp-COPYING", ROOT / "build-tools/libwebp-1.6.0/COPYING"),
        ("libwebp-PATENTS", ROOT / "build-tools/libwebp-1.6.0/PATENTS"),
        ("libwebp-AUTHORS", ROOT / "build-tools/libwebp-1.6.0/AUTHORS"),
    ]:
        bundle.writestr(info + "/licenses/" + name, source.read_bytes())
    write_record(bundle, info)
report = {
    "wheel": wheel.name,
    "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    "binary_bytes": binary.stat().st_size,
    "pillow": "11.0.0",
    "libwebp": "1.6.0",
    "android_api": 24,
    "abi": "arm64-v8a",
    "python": "3.13.16-0",
    "python_headers_archive_sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
    "sources": [{"name": name, "url": url, "sha256": digest} for name, url, digest in SOURCES],
    "evidence": "cross-compiled extension, Android runtime validation is separate",
}
(BUILD / "receipt.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report), flush=True)
