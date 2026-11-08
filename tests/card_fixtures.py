"""Controlled hand-authored card data and one-pixel containers; no external assets."""

import base64
import json
import struct
from pathlib import Path
from zlib import compress, crc32

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PIXELS = compress(b"\0\0\0\0\xff")


def card_document(version=2):
    path = Path(__file__).parent / "fixtures" / "character_cards" / f"v{version}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def json_bytes(document):
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc32(kind + data))


def card_text(keyword, document):
    return chunk(b"tEXt", keyword.encode("ascii") + b"\0" + base64.b64encode(json_bytes(document)))


def png_bytes(*text_chunks, animated=False, excluded_default=False):
    header = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    chunks = [header, *text_chunks]
    if animated:
        chunks.append(chunk(b"acTL", struct.pack(">II", 2, 0)))
        if not excluded_default:
            chunks.append(chunk(b"fcTL", struct.pack(">IIIIIHHBB", 0, 1, 1, 0, 0, 1, 10, 0, 0)))
    chunks.append(chunk(b"IDAT", PIXELS))
    if animated:
        seq = 0 if excluded_default else 1
        chunks.append(chunk(b"fcTL", struct.pack(">IIIIIHHBB", seq, 1, 1, 0, 0, 1, 10, 0, 0)))
        chunks.append(chunk(b"fdAT", struct.pack(">I", seq + 1) + PIXELS))
        if excluded_default:
            chunks.append(chunk(b"fcTL", struct.pack(">IIIIIHHBB", 2, 1, 1, 0, 0, 1, 10, 0, 0)))
            chunks.append(chunk(b"fdAT", struct.pack(">I", 3) + PIXELS))
    chunks.append(chunk(b"IEND", b""))
    return PNG_SIGNATURE + b"".join(chunks)
