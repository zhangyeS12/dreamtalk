"""Fetch pinned public weights for packaging; never execute an embedding model."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REVISION = "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"
BASE = f"https://huggingface.co/Qdrant/bge-small-zh-v1.5/resolve/{REVISION}/"
WEIGHT_HASH = "1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38"
FILES = [
    "config.json",
    "model_optimized.onnx",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
]


def main():
    directory = ROOT / "artifacts/semantic-model"
    directory.mkdir(parents=True, exist_ok=True)
    previous = (
        json.loads((directory / "manifest.json").read_text())
        if (directory / "manifest.json").is_file()
        else {}
    )
    hashes = {}
    for name in FILES:
        path = directory / name
        expected = WEIGHT_HASH if name.endswith(".onnx") else previous.get("sha256", {}).get(name)
        if path.is_file() and expected:
            with path.open("rb") as handle:
                existing = hashlib.file_digest(handle, "sha256").hexdigest()
            if existing == expected:
                hashes[name] = expected
                continue
        print("Downloading", name, flush=True)
        temporary = path.with_suffix(path.suffix + ".part")
        with urlopen(BASE + name, timeout=90) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        with temporary.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if expected and digest != expected:
            raise ValueError("semantic_model_checksum_mismatch")
        temporary.replace(path)
        hashes[name] = digest
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "model": "BAAI/bge-small-zh-v1.5",
                "export": "Qdrant/bge-small-zh-v1.5",
                "revision": REVISION,
                "license": "MIT",
                "sha256": hashes,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Pinned model files ready; no model execution.", flush=True)


if __name__ == "__main__":
    main()
