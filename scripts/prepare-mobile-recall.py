"""Stage hash-pinned product resources. Never runs inference or accesses app-data."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NUMPY = "numpy-2.3.2-1-cp313-cp313-android_24_arm64_v8a.whl"
NUMPY_SHA = "f7beb51f8d162c110ee8d4c9e275f490ce39dddba919643d949687bb4286bedd"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare():
    assets = ROOT / "plugins/android/src/main/assets/semantic-model"
    manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["sha256"].items():
        target = assets / name
        if not target.is_file() and name == "model_optimized.onnx":
            source = ROOT.parent / "LivingWorld/artifacts/semantic-model" / name
            if source.is_file() and sha(source) == expected:
                shutil.copyfile(source, target)
        if not target.is_file() or sha(target) != expected:
            raise RuntimeError("mobile_recall_resource_missing_or_invalid:" + name)
    wheel = ROOT / "build-tools/wheels" / NUMPY
    if not wheel.is_file() or sha(wheel) != NUMPY_SHA:
        raise RuntimeError("mobile_recall_numpy_missing_or_invalid")
    print("Fixed BGE assets and Android NumPy hashes verified; no inference.")


if __name__ == "__main__":
    prepare()
