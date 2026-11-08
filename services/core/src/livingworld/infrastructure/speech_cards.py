"""Bounded ZIP parsing and read-only audio metadata, using TinyTag (MIT)."""

import io
import json
import math
import zipfile

from tinytag import TinyTag, TinyTagException

from livingworld.application.speech_contracts import MAX_REFERENCE_BYTES, SpeechError, VoiceManifest


def inspect_audio(data: bytes, filename: str, *, reference=True):
    if filename not in {"reference.wav", "reference.mp3", "output.wav"}:
        raise SpeechError("voice_audio_format")
    if not data or len(data) > (MAX_REFERENCE_BYTES if reference else 32 * 1024 * 1024):
        raise SpeechError("voice_audio_size_limit")
    wav = filename.endswith(".wav")
    if wav and not (data[:4] == b"RIFF" and data[8:12] == b"WAVE"):
        raise SpeechError("voice_audio_invalid")
    if not wav and not (
        data[:3] == b"ID3" or len(data) >= 2 and data[0] == 255 and data[1] & 224 == 224
    ):
        raise SpeechError("voice_audio_invalid")
    try:
        info = TinyTag.get(filename, file_obj=io.BytesIO(data), tags=False, image=False)
        duration = info.duration
        if not duration or not math.isfinite(duration) or not info.samplerate:
            raise SpeechError("voice_audio_invalid")
        if info.channels not in {1, 2} or not 8000 <= info.samplerate <= 192000:
            raise SpeechError("voice_audio_invalid")
        if reference and not 0.5 <= duration <= 15:
            raise SpeechError("voice_reference_duration")
        if not reference and duration > 1800:
            raise SpeechError("voice_audio_size_limit")
        return round(duration * 1000), "audio/wav" if wav else "audio/mpeg"
    except SpeechError:
        raise
    except (TinyTagException, OSError, ValueError, IndexError, EOFError) as error:
        raise SpeechError("voice_audio_invalid") from error


def read_card(data: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if (
                len(entries) != 2
                or len(set(names)) != 2
                or "manifest.json" not in names
                or not set(names) <= {"manifest.json", "reference.wav", "reference.mp3"}
                or any(entry.flag_bits & 1 or entry.is_dir() for entry in entries)
                or sum(entry.file_size for entry in entries) > MAX_REFERENCE_BYTES + 16384
                or archive.getinfo("manifest.json").file_size > 16384
            ):
                raise SpeechError("voice_card_invalid")
            manifest = VoiceManifest.model_validate_json(archive.read("manifest.json"))
            if manifest.reference not in names:
                raise SpeechError("voice_card_invalid")
            audio = archive.read(manifest.reference)
            duration, media = inspect_audio(audio, manifest.reference)
            return manifest, audio, duration, media
    except SpeechError:
        raise
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        KeyError,
        ValueError,
        OSError,
        RuntimeError,
        NotImplementedError,
    ) as error:
        raise SpeechError("voice_card_invalid") from error


def write_card(manifest, audio):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr(manifest["reference"], audio)
    return output.getvalue()
