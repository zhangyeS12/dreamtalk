"""media wire DTOs; TypeScript declarations and guards are generated from this source."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

from pydantic import ConfigDict, with_config

from livingworld.adapters.http.wire_contracts.numbers import WireNumber

type StickerLibrary = Literal["personal", "public", "character"]


@with_config(ConfigDict(extra="allow"))
class StickerEntry(TypedDict):
    entry_id: str
    asset_id: str
    library: StickerLibrary
    description: str
    mime: str
    source_url: str | None
    caption_state: str


@with_config(ConfigDict(extra="allow"))
class ChatMediaAttachment(TypedDict):
    asset_id: str
    kind: Literal["sticker", "image"]
    description: str
    source_url: str | None
    only_media: bool


@with_config(ConfigDict(extra="allow"))
class ChatMediaSettings(TypedDict):
    enabled: bool
    frequency: WireNumber
    unlimited_stickers: bool
    online_enabled: bool
    auto_caption: bool
    caption_route: Literal["ollama", "compatible"]
    caption_endpoint: str
    caption_model: str
    secret_ref: str | None
    remote_caption_consent: bool
    daily_caption_limit: WireNumber
    caption_output_tokens: WireNumber


@with_config(ConfigDict(extra="allow"))
class VoiceManifest(TypedDict):
    format: Literal["dreamtalk.voicecard"]
    version: Literal[1]
    engine: Literal["indextts-2.5"]
    name: str
    language: Literal["ZH", "EN", "JA", "ES", "AR"]
    reference: Literal["reference.wav", "reference.mp3"]
    reference_text: str
    description: str
    author: str
    license: str
    speed: WireNumber


@with_config(ConfigDict(extra="allow"))
class VoiceCardPreview(TypedDict):
    manifest: VoiceManifest
    duration_ms: WireNumber


@with_config(ConfigDict(extra="allow"))
class VoiceCard(TypedDict):
    manifest: VoiceManifest
    duration_ms: WireNumber
    card_id: str
    digest: str


@with_config(ConfigDict(extra="allow"))
class VoiceCardPage(TypedDict):
    items: list[VoiceCard]
    next_offset: WireNumber | None


@with_config(ConfigDict(extra="allow"))
class SpeechSettings(TypedDict):
    enabled: bool
    provider: Literal["local", "huggingface", "compshare"]
    local_url: str
    secret_ref: str | None
    max_characters: WireNumber
    daily_calls: WireNumber
    skip_actions: bool
    consent_remote: bool
    consent_paid: bool


@with_config(ConfigDict(extra="allow"))
class SpeechStatus(TypedDict):
    settings: SpeechSettings
    revision: WireNumber


@with_config(ConfigDict(extra="allow"))
class SpeechJob(TypedDict):
    job_id: str
    state: Literal["running", "ready", "failed", "unknown", "expired", "replaced", "discarded"]
    error: str | None
    phase: str
    elapsed_seconds: WireNumber
    phase_seconds: WireNumber
    segment: WireNumber | None
    segments: WireNumber | None
    reused: NotRequired[bool]
    review_state: NotRequired[
        Literal["pending"] | Literal["accepted"] | Literal["discarded"] | None
    ]
    preview_completed: NotRequired[bool]
    cache_expires_at: NotRequired[str | None]


@with_config(ConfigDict(extra="allow"))
class SpeechPreviewJob(TypedDict):
    job_id: str
    state: Literal["running", "ready", "failed", "unknown", "expired", "replaced", "discarded"]
    error: str | None
    phase: str
    elapsed_seconds: WireNumber
    phase_seconds: WireNumber
    segment: WireNumber | None
    segments: WireNumber | None
    reused: NotRequired[bool]
    review_state: NotRequired[
        Literal["pending"] | Literal["accepted"] | Literal["discarded"] | None
    ]
    preview_completed: NotRequired[bool]
    cache_expires_at: NotRequired[str | None]
    message_id: str


@with_config(ConfigDict(extra="allow"))
class SpeechPricingCosts(TypedDict):
    text_to_speech: WireNumber


@with_config(ConfigDict(extra="allow"))
class SpeechPricingBalance(TypedDict):
    available_points: WireNumber


@with_config(ConfigDict(extra="allow"))
class SpeechPricing(TypedDict):
    enabled: bool
    pricing_version: WireNumber
    unit_characters: WireNumber
    costs: SpeechPricingCosts
    balance: SpeechPricingBalance
