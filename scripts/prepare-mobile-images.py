"""Verify the pinned existing-Pillow codec supplement and redistribution notices."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    assets = ROOT / "plugins/android/src/main/assets/third-party"
    manifest = json.loads((assets / "image-codecs.json").read_text(encoding="utf-8"))
    wheel = ROOT / "build-tools/wheels" / manifest["wheel"]
    if not wheel.is_file():
        raise RuntimeError("mobile_webp_wheel_missing: run scripts/build-android-webp.py")
    with zipfile.ZipFile(wheel) as bundle:
        assert (
            hashlib.sha256(bundle.read("PIL/_webp.so")).hexdigest() == manifest["binary_sha256"]
        ), "mobile_webp_extension_invalid"
        for name, notice in manifest["licenses"].items():
            assert hashlib.sha256((assets / name).read_bytes()).hexdigest() == notice["sha256"], (
                "mobile_image_license_invalid"
            )
    print("Pinned Pillow WebP extension and four image notices verified; no image data read.")


if __name__ == "__main__":
    prepare()
