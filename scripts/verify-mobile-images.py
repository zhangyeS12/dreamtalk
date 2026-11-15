"""Check the actual nested APK codec bytes, runtime link and image notices."""

import hashlib
import importlib
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(apk):
    manifest = json.loads(
        (ROOT / "plugins/android/src/main/assets/third-party/image-codecs.json").read_text(
            encoding="utf-8"
        )
    )
    candidates = []
    with zipfile.ZipFile(apk) as bundle:
        for name in bundle.namelist():
            if not name.endswith(".imy"):
                continue
            with zipfile.ZipFile(io.BytesIO(bundle.read(name))) as nested:
                if "PIL/_webp.so" in nested.namelist():
                    candidates.append(nested.read("PIL/_webp.so"))
        assert len(candidates) == 1, "APK Pillow WebP codec missing or ambiguous"
        binary = candidates[0]
        assert hashlib.sha256(binary).hexdigest() == manifest["binary_sha256"], (
            "APK WebP codec digest mismatch"
        )
        needed = importlib.import_module("verify-android-native-deps").needed(binary)
        assert "libpython3.13.so" in needed, "WebP extension Python runtime link absent"
        assert not any("webp" in name for name in needed), "WebP must be statically linked"
        assert json.loads(bundle.read("assets/third-party/image-codecs.json")) == manifest, (
            "APK image manifest mismatch"
        )
        for name, notice in manifest["licenses"].items():
            assert (
                hashlib.sha256(bundle.read("assets/third-party/" + name)).hexdigest()
                == notice["sha256"]
            ), "APK image notice mismatch"
    return {
        "pillow": manifest["pillow"],
        "libwebp": manifest["libwebp"],
        "webp_extension_sha256": manifest["binary_sha256"],
        "needed": needed,
        "notices_verified": len(manifest["licenses"]),
        "evidence": "static payload, Android decode/render tested separately",
    }
