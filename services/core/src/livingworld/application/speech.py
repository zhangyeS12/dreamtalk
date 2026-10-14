"""Read authorized committed replies, then synthesize without changing text or memory."""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from time import monotonic
from uuid import UUID, uuid4, uuid5

import httpx

from livingworld.application.llm_config import CredentialUnavailableError
from livingworld.application.speech_contracts import CACHE_SECONDS, SpeechError
from livingworld.application.speech_signal import pcm_signal_facts
from livingworld.domain.identifiers import CharacterId, ConversationId, MessageId, WorldId


def spoken_text(text, skip_actions):
    if skip_actions:
        # Remove bracketed stage directions and standalone italic action paragraphs.
        for _ in range(8):
            updated = re.sub(r"\([^()]*\)|（[^（）]*）", "", text)
            if updated == text:
                break
            text = updated
        text = re.sub(r"(?m)^\s*\*[^*\n]+\*\s*$", "", text)
    return text.strip()


class SpeechService:
    def __init__(self, store, messages, providers, inspect_audio, maintenance, *, logger=None):
        self.store, self.messages, self.providers = store, messages, providers
        self.inspect_audio = inspect_audio
        self.lock = asyncio.Lock()
        self.maintenance = maintenance
        self.logger = logger
        self.task = None
        self.live = None
        self.cleanup_task = None
        self.cache_changed = asyncio.Event()
        self.local_repair = None

    async def begin_local_repair(self):
        async with self.lock:
            if self.task is not None or self.maintenance.preparing:
                raise SpeechError("speech_local_repair_busy")
            if self.local_repair and self.local_repair[1] > monotonic():
                raise SpeechError("speech_local_repair_busy")
            identity = str(uuid4())
            self.local_repair = (identity, monotonic() + 120)
            return {"lease": identity}

    async def end_local_repair(self, identity):
        async with self.lock:
            if self.local_repair and self.local_repair[0] == identity:
                self.local_repair = None
            return {"released": True}

    @property
    def busy(self):
        return self.lock.locked() or self.task is not None

    async def aclose(self):
        if self.cleanup_task is not None:
            self.cleanup_task.cancel()
            await asyncio.gather(self.cleanup_task, return_exceptions=True)
            self.cleanup_task = None
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def start(self):
        await self.store.expire_cache()
        self.cleanup_task = asyncio.create_task(self._clean_cache())

    async def _clean_cache(self):
        try:
            while True:
                self.cache_changed.clear()
                delay = 60.0
                # Only each short sweep counts as active; never fence an update
                # for the lifetime of this background waiter.
                with self.maintenance.operation() as admitted:
                    if admitted:
                        delay = await self.store.expire_cache()
                try:
                    await asyncio.wait_for(self.cache_changed.wait(), timeout=delay)
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:
            # No private exception text. Reads still enforce expiry if this fails.
            logging.getLogger(__name__).error("speech_cache_cleanup_failed")

    async def status(self, world):
        settings, revision = await self.store.settings(world)
        return {"settings": settings.model_dump(mode="json"), "revision": revision}

    async def save_settings(self, world, settings, expected):
        if settings.enabled:
            if settings.provider != "local" and not settings.consent_remote:
                raise SpeechError("speech_remote_consent_required")
            if settings.provider == "compshare" and (
                not settings.consent_paid or settings.secret_ref is None
            ):
                raise SpeechError("speech_paid_consent_required")
        if self.busy and settings.enabled:
            raise SpeechError("speech_busy")
        await self.store.save_settings(world, settings, expected)
        return await self.status(world)

    async def authorized_message(self, world, conversation, message):
        scope = WorldId(world)
        page = await self.messages.message_source(
            ConversationId(scope, conversation), MessageId(scope, message)
        )
        found = next((item for item in page.messages if item.message_id.value == message), None)
        if found is None or not isinstance(found.sender_id, CharacterId):
            raise SpeechError("speech_character_message_required")
        if found.media and found.media.get("only_media"):
            raise SpeechError("speech_character_message_required")
        return found

    async def generate(self, world, conversation, message, request_id=None, *, regenerate=False):
        async with self.lock:
            if regenerate and request_id is None:
                raise SpeechError("speech_request_required")
            found = await self.authorized_message(world, conversation, message)
            settings, _ = await self.store.settings(world)
            if not settings.enabled:
                raise SpeechError("speech_disabled")
            if settings.provider != "local" and not settings.consent_remote:
                raise SpeechError("speech_remote_consent_required")
            if settings.provider == "compshare" and (
                not settings.consent_paid or settings.secret_ref is None
            ):
                raise SpeechError("speech_paid_consent_required")
            # UUID5 is the established chat identity contract; bind by its stable card root.
            player, root = await self.store.target(world, conversation, found.sender_id.value)
            if uuid5(root, "livingworld:chat-character:v1") != found.sender_id.value:
                raise SpeechError("voice_character_not_found")
            card_id = await self.store.binding(world, root)
            if card_id is None:
                raise SpeechError("speech_voice_unbound")
            card = await self.store.card(world, UUID(card_id))
            manifest = json.loads(card.manifest_json)
            text = spoken_text(found.text, settings.skip_actions)
            if not text or not any(c.isalpha() or c.isdecimal() for c in text):
                raise SpeechError("speech_no_dialogue")
            if len(text) > settings.max_characters:
                raise SpeechError("speech_text_too_long")
            fingerprint = hashlib.sha256(
                json.dumps(
                    [
                        str(player),
                        str(message),
                        card.digest,
                        manifest,
                        text,
                        settings.provider,
                        settings.local_url if settings.provider == "local" else "",
                        str(settings.secret_ref),
                    ],
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            if request_id is not None:
                prior = await self.store.request_job(world, request_id)
                if prior is not None:
                    if (prior.cache_key or prior.fingerprint) != fingerprint or (
                        (prior.review_state is not None) != regenerate
                    ):
                        raise SpeechError("speech_request_conflict")
                    return {**await self.job_status(world, prior.job_id), "reused": True}
            existing = await self.store.existing_job(world, fingerprint)
            if (
                not regenerate
                and existing is not None
                and (
                    request_id is None
                    or existing.state == "running"
                    or (existing.state == "ready" and existing.audio is not None)
                )
            ):
                return {**await self.job_status(world, existing.job_id), "reused": True}
            if self.task is not None:
                raise SpeechError("speech_busy")
            if (
                settings.provider == "local"
                and self.local_repair
                and self.local_repair[1] > monotonic()
            ):
                raise SpeechError("speech_local_repairing")
            job, fresh = await self.store.claim(
                world,
                player,
                conversation,
                message,
                fingerprint,
                None if settings.provider == "local" else settings.daily_calls,
                request_id,
                regenerate=regenerate,
            )
            if fresh:
                now = monotonic()
                self.live = {
                    "identity": job.job_id,
                    "phase": "connecting",
                    "started": now,
                    "changed": now,
                    "segment": None,
                    "segments": None,
                }
                self.task = self.maintenance.spawn(
                    self._run(world, job.job_id, settings, card, manifest, text)
                )
            return {**await self.job_status(world, job.job_id), "reused": not fresh}

    def progress(self, phase, segment=None, segments=None):
        if self.live is not None:
            if self.live["phase"] != phase or self.live["segment"] != segment:
                self.live["changed"] = monotonic()
            self.live.update(phase=phase, segment=segment, segments=segments)

    async def _run(self, world, identity, settings, card, manifest, text):
        try:
            async with asyncio.timeout(960):
                audio = await self.providers.synthesize(
                    settings,
                    card,
                    manifest,
                    text,
                    identity,
                    lambda remote: self.store.remote_id(world, identity, remote),
                    self.progress,
                )
                self.progress("validating_audio")
                await asyncio.to_thread(self.inspect_audio, audio, "output.wav", reference=False)
                self.progress("saving_audio")
                await self.store.finish(world, identity, "ready", audio=audio)
                self.cache_changed.set()
        except asyncio.CancelledError:
            await self.store.finish(world, identity, "unknown", error="speech_interrupted")
            raise
        except TimeoutError:
            await self.store.finish(world, identity, "unknown", error="speech_timeout")
        except CredentialUnavailableError:
            await self.store.finish(world, identity, "failed", error="speech_key_required")
        except httpx.HTTPError:
            await self.store.finish(world, identity, "unknown", error="speech_status_lost")
        except SpeechError as error:
            state = (
                "unknown"
                if str(error) in {"speech_outcome_unknown", "speech_status_lost"}
                else "failed"
            )
            await self.store.finish(world, identity, state, error=str(error))
        except (KeyError, ValueError, TypeError, IndexError):
            await self.store.finish(world, identity, "unknown", error="speech_provider_protocol")
        except Exception:
            await self.store.finish(world, identity, "unknown", error="speech_outcome_unknown")
        finally:
            self.task = self.live = None

    async def job_status(self, world, identity):
        row = await self.authorized_job(world, identity)
        return self.job_facts(row)

    async def authorized_job(self, world, identity):
        row = await self.store.job(world, identity)
        found = await self.authorized_message(world, row.conversation_id, row.message_id)
        player, _ = await self.store.target(world, row.conversation_id, found.sender_id.value)
        if player != row.player_id:
            raise SpeechError("speech_job_not_found")
        return row

    def job_facts(self, row):
        live = self.live if self.live and self.live["identity"] == row.job_id else None
        return {
            "job_id": str(row.job_id),
            "state": row.state,
            "error": row.error,
            "phase": live["phase"] if live else row.state,
            "elapsed_seconds": int(monotonic() - live["started"]) if live else 0,
            "phase_seconds": int(monotonic() - live["changed"]) if live else 0,
            "segment": live["segment"] if live else None,
            "segments": live["segments"] if live else None,
            "review_state": row.review_state,
            "preview_completed": row.previewed_at is not None,
            "cache_expires_at": (
                (
                    datetime.fromisoformat(row.audio_saved_at or row.created_at)
                    + timedelta(seconds=CACHE_SECONDS)
                ).isoformat()
                if row.state == "ready"
                else None
            ),
        }

    async def reviews(self, world, conversation, messages):
        rows = await self.store.reviews(world, conversation, set(messages))
        result = []
        for row in rows:
            found = await self.authorized_message(world, conversation, row.message_id)
            player, _ = await self.store.target(world, conversation, found.sender_id.value)
            if player != row.player_id:
                continue
            # The bounded listing contains metadata only, never audio or dialogue.
            result.append({"message_id": str(row.message_id), **self.job_facts(row)})
        return {"items": result}

    async def preview_completed(self, world, identity):
        async with self.lock:
            await self.authorized_job(world, identity)
            await self.store.preview_completed(world, identity)
            return await self.job_status(world, identity)

    async def decide(self, world, identity, replace):
        async with self.lock:
            await self.authorized_job(world, identity)
            await self.store.decide(world, identity, replace)
            self.cache_changed.set()
            return await self.job_status(world, identity)

    async def audio(self, world, identity, *, inspect_signal=False):
        row = await self.authorized_job(world, identity)
        if row.state != "ready" or row.audio is None:
            raise SpeechError(row.error or "speech_audio_not_ready")
        if inspect_signal and self.logger is not None:
            try:
                facts = await asyncio.to_thread(pcm_signal_facts, row.audio)
                if facts is not None:
                    self.logger.emit_speech_signal_facts(**facts)
                else:
                    self.logger.emit("speech", "audio_signal_unavailable", level="WARNING")
            except (OSError, ValueError):
                # Diagnostics must never turn an otherwise playable cache into a failure.
                logging.getLogger(__name__).warning("speech_signal_diagnostic_failed")
        return row.audio
