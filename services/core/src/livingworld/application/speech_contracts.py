"""Declarative voice cards and world-specific speech preferences; no executable payloads."""

from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_REFERENCE_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 32 * 1024 * 1024
CACHE_BYTES = 256 * 1024 * 1024
CACHE_SECONDS = 6 * 60 * 60


class SpeechError(ValueError):
    pass


class VoiceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    format: Literal["dreamtalk.voicecard"] = "dreamtalk.voicecard"
    version: Literal[1] = 1
    engine: Literal["indextts-2.5"] = "indextts-2.5"
    name: str = Field(min_length=1, max_length=64)
    language: Literal["ZH", "EN", "JA", "ES", "AR"] = "ZH"
    reference: Literal["reference.wav", "reference.mp3"] = "reference.wav"
    reference_text: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=1000)
    author: str = Field(default="", max_length=120)
    license: str = Field(default="", max_length=1000)
    speed: float = Field(default=1, ge=0.5, le=2)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("voice_name_required")
        return value.strip()


class SpeechSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    enabled: bool = Field(default=False, strict=True)
    provider: Literal["local", "huggingface", "compshare"] = "local"
    local_url: str = "http://127.0.0.1:7861"
    secret_ref: UUID | None = None
    max_characters: int = Field(default=1600, strict=True, ge=1, le=2000)
    daily_calls: int = Field(default=20, strict=True, ge=1, le=1000)
    skip_actions: bool = Field(default=True, strict=True)
    consent_remote: bool = Field(default=False, strict=True)
    consent_paid: bool = Field(default=False, strict=True)

    @field_validator("local_url")
    @classmethod
    def loopback_endpoint(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or not parsed.port
            or "\\" in value
            or any(c.isspace() for c in value)
        ):
            raise ValueError("speech_local_endpoint_invalid")
        return value.rstrip("/")
