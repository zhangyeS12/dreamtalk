"""Bounded PCM level facts; no listening, recognition, trimming or model calls."""

import io
import math
import sys
import wave
from array import array


def pcm_signal_facts(audio: bytes):
    if not audio or len(audio) > 32 * 1024 * 1024:
        return None
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            rate, channels = source.getframerate(), source.getnchannels()
            declared_frames = source.getnframes()
            if (
                source.getsampwidth() != 2
                or source.getcomptype() != "NONE"
                or channels not in {1, 2}
                or not 8000 <= rate <= 192000
                or not 0 < declared_frames <= rate * 1800
            ):
                return None
            rms_levels, peak_levels, durations = [], [], []
            actual_frames = 0
            for _second in range(math.ceil(declared_frames / rate)):
                raw = source.readframes(rate)
                if not raw:
                    break
                if len(raw) % (2 * channels):
                    return None
                samples = array("h", raw)
                if sys.byteorder != "little":
                    samples.byteswap()
                frames = len(samples) // channels
                actual_frames += frames
                peak = max(abs(sample) for sample in samples)
                rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))

                def dbfs(value):
                    return (
                        round(max(-120.0, 20 * math.log10(value / 32768)), 2) if value else -120.0
                    )

                rms_levels.append(dbfs(rms))
                peak_levels.append(dbfs(peak))
                durations.append(frames / rate)
            if not actual_frames:
                return None
            trailing_quiet = 0.0
            for rms, peak, duration in zip(
                reversed(rms_levels), reversed(peak_levels), reversed(durations), strict=True
            ):
                if rms > -60 or peak > -50:
                    break
                trailing_quiet += duration
            return {
                "sample_rate": rate,
                "channels": channels,
                "duration_seconds": round(actual_frames / rate, 3),
                "declared_duration_seconds": round(declared_frames / rate, 3),
                "trailing_quiet_seconds": round(trailing_quiet, 3),
                "missing_frames": max(0, declared_frames - actual_frames),
                "per_second_rms_dbfs": rms_levels,
                "per_second_peak_dbfs": peak_levels,
            }
    except (wave.Error, EOFError, ValueError, OverflowError):
        return None
