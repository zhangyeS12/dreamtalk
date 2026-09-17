"""Narrow PNG/APNG metadata reader; no image/frame decompression or materialization."""

import re
import struct
from dataclasses import dataclass
from zlib import crc32

from livingworld.application.imports import ContentImportError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True)
class PngMetadata:
    container: str
    card_chunks: tuple[tuple[str, bytes], ...]
    embedded_assets: tuple[dict, ...]


def read_png(payload: bytes, *, max_chunks: int) -> PngMetadata:
    if not payload.startswith(PNG_SIGNATURE):
        raise ContentImportError("invalid_png_signature")
    offset = len(PNG_SIGNATURE)
    seen: set[bytes] = set()
    cards = []
    assets = []
    count = 0
    width = height = color = depth = 0
    idat_closed = False
    animation_frames = None
    frames = sequence = 0
    frame_has_data = False
    frame_uses_idat = False
    while offset < len(payload):
        count += 1
        if count > max_chunks:
            raise ContentImportError("character_card_chunk_limit")
        if len(payload) - offset < 12:
            raise ContentImportError("truncated_png_chunk")
        length, kind = struct.unpack_from(">I4s", payload, offset)
        end = offset + 12 + length
        if length > 0x7FFFFFFF or end > len(payload):
            raise ContentImportError("invalid_png_chunk_length")
        if re.fullmatch(rb"[A-Za-z]{4}", kind) is None or kind[2] & 32:
            raise ContentImportError("invalid_png_chunk_type")
        data = payload[offset + 8 : end - 4]
        checksum = struct.unpack_from(">I", payload, end - 4)[0]
        if crc32(kind + data) != checksum:
            raise ContentImportError("invalid_png_crc")
        if not seen and kind != b"IHDR":
            raise ContentImportError("invalid_png_header_order")
        if b"IDAT" in seen and kind != b"IDAT":
            idat_closed = True
        if kind == b"IHDR":
            if seen or length != 13:
                raise ContentImportError("invalid_png_header")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data
            )
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if (
                not 0 < width <= 0x7FFFFFFF
                or not 0 < height <= 0x7FFFFFFF
                or depth not in depths.get(color, ())
                or compression != 0
                or filtering != 0
                or interlace not in (0, 1)
            ):
                raise ContentImportError("invalid_png_header")
        elif kind == b"PLTE":
            if (
                kind in seen
                or b"IDAT" in seen
                or color in (0, 4)
                or not 0 < length <= 768
                or length % 3
                or (color == 3 and length // 3 > 2**depth)
            ):
                raise ContentImportError("invalid_png_palette")
        elif kind == b"IDAT":
            if idat_closed or (color == 3 and b"PLTE" not in seen):
                raise ContentImportError("invalid_png_image_order")
            if frames and frame_uses_idat:
                frame_has_data = True
        elif kind == b"IEND":
            if length or b"IDAT" not in seen or end != len(payload):
                raise ContentImportError("invalid_png_end")
            if animation_frames is not None and (frames != animation_frames or not frame_has_data):
                raise ContentImportError("invalid_apng_frame_count")
            return PngMetadata(
                "apng" if animation_frames is not None else "png", tuple(cards), tuple(assets)
            )
        elif kind == b"tEXt":
            keyword, separator, text = data.partition(b"\0")
            if (
                not separator
                or not 1 <= len(keyword) <= 79
                or any(not (32 <= byte <= 126 or 161 <= byte <= 255) for byte in keyword)
                or keyword.startswith(b" ")
                or keyword.endswith(b" ")
                or b"  " in keyword
            ):
                raise ContentImportError("invalid_png_text")
            name = keyword.decode("latin-1")
            if name in ("chara", "ccv3"):
                cards.append((name, text))
            elif name.startswith("chara-ext-asset_:"):
                # Offset/size only: raw envelope retains binary/base64 content exactly.
                assets.append({"keyword": name, "chunk_offset": offset, "text_length": len(text)})
        elif kind == b"acTL":
            if animation_frames is not None or b"IDAT" in seen or length != 8:
                raise ContentImportError("invalid_apng_control")
            animation_frames, _plays = struct.unpack(">II", data)
            if animation_frames == 0:
                raise ContentImportError("invalid_apng_frame_count")
        elif kind == b"fcTL":
            if animation_frames is None or length != 26 or (frames and not frame_has_data):
                raise ContentImportError("invalid_apng_frame_control")
            seq, w, h, x, y, _num, _den, dispose, blend = struct.unpack(">IIIIIHHBB", data)
            if seq != sequence or not w or not h or x + w > width or y + h > height:
                raise ContentImportError("invalid_apng_frame_control")
            if dispose not in (0, 1, 2) or blend not in (0, 1):
                raise ContentImportError("invalid_apng_frame_control")
            frame_uses_idat = b"IDAT" not in seen
            if frame_uses_idat and (frames or (w, h, x, y) != (width, height, 0, 0)):
                raise ContentImportError("invalid_apng_default_frame")
            frames += 1
            sequence += 1
            frame_has_data = False
        elif kind == b"fdAT":
            if animation_frames is None or not frames or frame_uses_idat or length < 4:
                raise ContentImportError("invalid_apng_frame_data")
            if struct.unpack_from(">I", data)[0] != sequence:
                raise ContentImportError("invalid_apng_sequence")
            sequence += 1
            frame_has_data = True
        elif not kind[0] & 32:
            raise ContentImportError("unsupported_png_critical_chunk")
        seen.add(kind)
        offset = end
    raise ContentImportError("missing_png_end")
