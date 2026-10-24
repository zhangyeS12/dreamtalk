"""Read only bounded CHARX card.json in memory; never extract files or fetch assets."""

import io
import posixpath
import re
import stat
import zipfile
import zlib

from livingworld.application.imports import ContentImportError


def read_charx(payload: bytes, *, max_json_bytes: int, max_entries: int) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            files = archive.infolist()
            if len(files) > max_entries:
                raise ContentImportError("character_card_archive_entry_limit")
            seen = set()
            expanded = 0
            for entry in files:
                name = entry.orig_filename
                path = posixpath.normpath(name)
                if (
                    not name
                    or "\0" in name
                    or "\\" in name
                    or posixpath.isabs(path)
                    or ".." in path.split("/")
                    or re.match(r"^[A-Za-z]:", name)
                    or name in seen
                    or entry.flag_bits & 1
                    or stat.S_ISLNK(entry.external_attr >> 16)
                ):
                    raise ContentImportError("unsafe_character_card_archive")
                seen.add(name)
                expanded += entry.file_size
                if expanded > 128 * 1024 * 1024:
                    raise ContentImportError("character_card_archive_size_limit")
            if "card.json" not in seen:
                raise ContentImportError("character_card_archive_missing_json")
            card = archive.getinfo("card.json")
            if card.file_size > max_json_bytes:
                raise ContentImportError("character_card_json_size_limit")
            with archive.open(card) as source:
                result = source.read(max_json_bytes + 1)
            if len(result) > max_json_bytes:
                raise ContentImportError("character_card_json_size_limit")
            return result
    except ContentImportError:
        raise
    except (
        OSError,
        ValueError,
        RuntimeError,
        NotImplementedError,
        zipfile.BadZipFile,
        EOFError,
        zlib.error,
    ):
        raise ContentImportError("invalid_character_card_archive") from None
