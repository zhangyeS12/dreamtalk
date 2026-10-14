"""World/owner-scoped speech attempts, durable admission and expiring audio."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4, uuid5

from sqlalchemy import and_, delete, func, or_, select, update

from livingworld.application.speech_contracts import (
    CACHE_BYTES,
    CACHE_SECONDS,
    SpeechError,
    SpeechSettings,
)
from livingworld.infrastructure.persistence.factions import _characters
from livingworld.infrastructure.persistence.models import (
    ChatConversationRecord,
    ChatParticipantRecord,
    WorldRecord,
)
from livingworld.infrastructure.persistence.speech_models import (
    RemoteVoiceRecord,
    SpeechCallRecord,
    SpeechJobRecord,
    SpeechSettingsRecord,
    VoiceBindingRecord,
    VoiceCardRecord,
)


def card_summary(row):
    return {
        "card_id": str(row.card_id),
        "manifest": json.loads(row.manifest_json),
        "duration_ms": row.duration_ms,
        "digest": row.digest,
    }


def expired_audio(now):
    cutoff = (now - timedelta(seconds=CACHE_SECONDS)).isoformat()
    return and_(
        SpeechJobRecord.audio.is_not(None),
        or_(
            SpeechJobRecord.audio_saved_at <= cutoff,
            and_(SpeechJobRecord.audio_saved_at.is_(None), SpeechJobRecord.created_at <= cutoff),
        ),
    )


class SqlAlchemySpeechStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def require_world(self, world):
        async with self.sessions() as session:
            if await session.get(WorldRecord, world) is None:
                raise SpeechError("world_not_found")

    async def local_requested(self):
        async with self.sessions() as session:
            rows = (await session.scalars(select(SpeechSettingsRecord.settings_json))).all()
            return any(
                (settings := SpeechSettings.model_validate_json(value)).enabled
                and settings.provider == "local"
                and settings.local_url == "http://127.0.0.1:7861"
                for value in rows
            )

    async def existing_job(self, world, fingerprint):
        await self.expire_cache()
        async with self.sessions() as session:
            return await session.scalar(self.latest_job(world, fingerprint))

    @staticmethod
    def latest_job(world, fingerprint):
        return (
            select(SpeechJobRecord)
            .where(
                SpeechJobRecord.world_id == world,
                or_(
                    SpeechJobRecord.review_state.is_(None),
                    SpeechJobRecord.review_state == "accepted",
                ),
                or_(
                    SpeechJobRecord.cache_key == fingerprint,
                    and_(
                        SpeechJobRecord.cache_key.is_(None),
                        SpeechJobRecord.fingerprint == fingerprint,
                    ),
                ),
            )
            .order_by(SpeechJobRecord.created_at.desc(), SpeechJobRecord.job_id.desc())
            .limit(1)
        )

    @staticmethod
    def pending_review(world, conversation, message):
        return select(SpeechJobRecord).where(
            SpeechJobRecord.world_id == world,
            SpeechJobRecord.conversation_id == conversation,
            SpeechJobRecord.message_id == message,
            SpeechJobRecord.review_state == "pending",
        )

    async def request_job(self, world, request_id):
        identity = uuid5(world, "livingworld:speech:manual:" + str(request_id))
        return await self.job(world, identity, required=False)

    async def reviews(self, world, conversation, messages):
        await self.expire_cache()
        async with self.sessions() as session:
            return (
                await session.execute(
                    select(
                        SpeechJobRecord.job_id,
                        SpeechJobRecord.message_id,
                        SpeechJobRecord.player_id,
                        SpeechJobRecord.state,
                        SpeechJobRecord.error,
                        SpeechJobRecord.previewed_at,
                        SpeechJobRecord.base_job_id,
                        SpeechJobRecord.review_state,
                        SpeechJobRecord.audio_saved_at,
                        SpeechJobRecord.created_at,
                    ).where(
                        SpeechJobRecord.world_id == world,
                        SpeechJobRecord.conversation_id == conversation,
                        SpeechJobRecord.message_id.in_(messages),
                        SpeechJobRecord.review_state == "pending",
                    )
                )
            ).all()

    async def expire_cache(self):
        now = datetime.now(UTC)
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await session.execute(
                update(SpeechJobRecord)
                .where(expired_audio(now))
                .values(audio=None, state="expired", error="speech_cache_expired")
            )
            oldest = await session.scalar(
                select(
                    func.min(
                        func.coalesce(SpeechJobRecord.audio_saved_at, SpeechJobRecord.created_at)
                    )
                ).where(SpeechJobRecord.audio.is_not(None))
            )
        if oldest is None:
            return 60.0
        remaining = (datetime.fromisoformat(oldest) - now).total_seconds() + CACHE_SECONDS
        return max(0.1, min(60.0, remaining))

    async def settings(self, world):
        await self.require_world(world)
        async with self.sessions() as session:
            row = await session.get(SpeechSettingsRecord, world)
            return (
                (SpeechSettings.model_validate_json(row.settings_json), row.revision)
                if row
                else (SpeechSettings(), 0)
            )

    async def save_settings(self, world, settings, expected):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            if await session.get(WorldRecord, world) is None:
                raise SpeechError("world_not_found")
            row = await session.get(SpeechSettingsRecord, world)
            if (row.revision if row else 0) != expected:
                raise SpeechError("speech_edit_conflict")
            if row is None:
                row = SpeechSettingsRecord(world_id=world, revision=0, settings_json="{}")
                session.add(row)
            row.settings_json = settings.model_dump_json()
            row.revision += 1

    async def library(self, world, offset=0):
        await self.require_world(world)
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(
                        VoiceCardRecord.card_id,
                        VoiceCardRecord.manifest_json,
                        VoiceCardRecord.digest,
                        VoiceCardRecord.duration_ms,
                    )
                    .where(VoiceCardRecord.world_id == world)
                    .order_by(VoiceCardRecord.card_id)
                    .offset(offset)
                    .limit(101)
                )
            ).all()
            return {
                "items": [card_summary(row) for row in rows[:100]],
                "next_offset": offset + 100 if len(rows) > 100 else None,
            }

    async def import_card(self, world, manifest, audio, duration):
        await self.require_world(world)
        encoded = manifest.model_dump_json()
        digest = hashlib.sha256(audio).hexdigest()
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            # Repeated confirmation of the same file reuses the existing card.
            row = await session.scalar(
                select(VoiceCardRecord).where(
                    VoiceCardRecord.world_id == world,
                    VoiceCardRecord.digest == digest,
                    VoiceCardRecord.manifest_json == encoded,
                )
            )
            if row is None:
                row = VoiceCardRecord(
                    world_id=world,
                    card_id=uuid4(),
                    manifest_json=encoded,
                    digest=digest,
                    duration_ms=duration,
                    audio=audio,
                )
                session.add(row)
            return card_summary(row)

    async def card(self, world, card_id):
        async with self.sessions() as session:
            row = await session.get(VoiceCardRecord, (world, card_id))
            if row is None:
                raise SpeechError("voice_card_not_found")
            return row

    async def binding(self, world, root):
        async with self.sessions() as session:
            if root not in await _characters(session, world, [root]):
                raise SpeechError("voice_character_not_found")
            row = await session.get(VoiceBindingRecord, (world, root))
            return str(row.card_id) if row else None

    async def target(self, world, conversation, speaker):
        async with self.sessions() as session:
            owner = await session.get(ChatConversationRecord, (world, conversation))
            person = await session.get(ChatParticipantRecord, (world, conversation, speaker))
            if owner is None or person is None:
                raise SpeechError("voice_character_not_found")
            return owner.player_id, person.root_import_id

    async def bind(self, world, root, card):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            if root not in await _characters(session, world, [root]):
                raise SpeechError("voice_character_not_found")
            row = await session.get(VoiceBindingRecord, (world, root))
            if card is None:
                if row:
                    await session.delete(row)
            elif await session.get(VoiceCardRecord, (world, card)) is None:
                raise SpeechError("voice_card_not_found")
            elif row:
                row.card_id = card
            else:
                session.add(VoiceBindingRecord(world_id=world, root_import_id=root, card_id=card))

    async def remove_card(self, world, card):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await session.execute(
                delete(VoiceBindingRecord).where(
                    VoiceBindingRecord.world_id == world, VoiceBindingRecord.card_id == card
                )
            )
            await session.execute(
                delete(VoiceCardRecord).where(
                    VoiceCardRecord.world_id == world, VoiceCardRecord.card_id == card
                )
            )

    async def claim(
        self,
        world,
        player,
        conversation,
        message,
        fingerprint,
        daily_limit,
        request_id=None,
        *,
        regenerate=False,
    ):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            identity = uuid5(
                world,
                "livingworld:speech:manual:" + str(request_id)
                if request_id is not None
                else "livingworld:speech:v1:" + fingerprint,
            )
            # A repeated HTTP request never retries a completed/failed attempt.
            prior = await session.get(SpeechJobRecord, (world, identity))
            if prior is not None:
                if (prior.cache_key or prior.fingerprint) != fingerprint or (
                    (prior.review_state is not None) != regenerate
                ):
                    raise SpeechError("speech_request_conflict")
                return prior, False
            existing = await session.scalar(self.latest_job(world, fingerprint))
            if (
                not regenerate
                and existing is not None
                and (
                    request_id is None
                    or existing.state == "running"
                    or (existing.state == "ready" and existing.audio is not None)
                )
            ):
                return existing, False
            pending = await session.scalar(self.pending_review(world, conversation, message))
            if pending is not None:
                if pending.state in {"running", "ready"}:
                    raise SpeechError("speech_review_pending")
                pending.review_state = "discarded"
            day = datetime.now(UTC).date().isoformat()
            if daily_limit is not None:
                calls = await session.scalar(
                    select(func.count())
                    .select_from(SpeechCallRecord)
                    .where(SpeechCallRecord.day == day, SpeechCallRecord.is_local.is_not(True))
                )
                if calls >= daily_limit:
                    raise SpeechError("speech_daily_limit")
            attempt_fingerprint = (
                hashlib.sha256((fingerprint + ":manual:" + str(request_id)).encode()).hexdigest()
                if request_id is not None
                else fingerprint
            )
            row = SpeechJobRecord(
                world_id=world,
                job_id=identity,
                fingerprint=attempt_fingerprint,
                cache_key=fingerprint,
                player_id=player,
                conversation_id=conversation,
                message_id=message,
                state="running",
                created_at=datetime.now(UTC).isoformat(),
                review_state="pending" if regenerate else None,
                base_job_id=existing.job_id if regenerate and existing else None,
            )
            session.add(row)
            session.add(SpeechCallRecord(job_id=identity, day=day, is_local=daily_limit is None))
            return row, True

    async def job(self, world, identity, *, required=True):
        # Enforce the deadline on every read, even if a scheduled sweep is delayed.
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await session.execute(
                update(SpeechJobRecord)
                .where(
                    SpeechJobRecord.world_id == world,
                    SpeechJobRecord.job_id == identity,
                    expired_audio(datetime.now(UTC)),
                )
                .values(audio=None, state="expired", error="speech_cache_expired")
            )
        async with self.sessions() as session:
            row = await session.get(SpeechJobRecord, (world, identity))
            if row is None and required:
                raise SpeechError("speech_job_not_found")
            return row

    async def preview_completed(self, world, identity):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(SpeechJobRecord, (world, identity))
            if row.review_state != "pending" or row.state != "ready" or row.audio is None:
                raise SpeechError("speech_review_not_ready")
            saved = datetime.fromisoformat(row.audio_saved_at or row.created_at)
            if (datetime.now(UTC) - saved).total_seconds() >= CACHE_SECONDS:
                raise SpeechError("speech_cache_expired")
            if row.previewed_at is None:
                row.previewed_at = datetime.now(UTC).isoformat()

    async def decide(self, world, identity, replace):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(SpeechJobRecord, (world, identity))
            decision = "accepted" if replace else "discarded"
            if row.review_state == decision:
                return
            if row.review_state != "pending":
                raise SpeechError("speech_review_conflict")
            if row.state != "ready" or row.audio is None:
                raise SpeechError("speech_review_not_ready")
            saved = datetime.fromisoformat(row.audio_saved_at or row.created_at)
            if (datetime.now(UTC) - saved).total_seconds() >= CACHE_SECONDS:
                raise SpeechError("speech_cache_expired")
            if row.previewed_at is None:
                raise SpeechError("speech_preview_required")
            if replace:
                current = await session.scalar(self.latest_job(world, row.cache_key))
                if (current.job_id if current else None) != row.base_job_id:
                    raise SpeechError("speech_review_conflict")
                if current is not None:
                    current.audio, current.state, current.error = None, "replaced", None
                # Acceptance never extends the six-hour lifetime of this sound.
            else:
                row.audio, row.state, row.error = None, "discarded", None
            row.review_state = decision

    async def remote_id(self, world, identity, remote_id):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(SpeechJobRecord, (world, identity))
            row.remote_id = remote_id

    async def finish(self, world, identity, state, audio=None, error=None):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(SpeechJobRecord, (world, identity))
            row.state, row.audio, row.error = state, audio, error
            if state == "ready" and audio is not None:
                row.audio_saved_at = datetime.now(UTC).isoformat()
            await session.flush()
            # Clear derived sound only. Every later manual attempt keeps its own receipt.
            total = await session.scalar(
                select(func.coalesce(func.sum(func.length(SpeechJobRecord.audio)), 0))
            )
            if total > CACHE_BYTES:
                protected = select(SpeechJobRecord.base_job_id).where(
                    SpeechJobRecord.review_state == "pending",
                    SpeechJobRecord.base_job_id.is_not(None),
                    SpeechJobRecord.state.in_(["running", "ready"]),
                )
                pending_audio = select(SpeechJobRecord.job_id).where(
                    SpeechJobRecord.review_state == "pending",
                    SpeechJobRecord.state.in_(["running", "ready"]),
                )
                candidates = await session.execute(
                    select(
                        SpeechJobRecord.world_id,
                        SpeechJobRecord.job_id,
                        func.length(SpeechJobRecord.audio),
                    )
                    .where(
                        SpeechJobRecord.audio.is_not(None),
                        SpeechJobRecord.job_id != identity,
                        SpeechJobRecord.job_id.not_in(protected),
                        SpeechJobRecord.job_id.not_in(pending_audio),
                    )
                    .order_by(
                        func.coalesce(SpeechJobRecord.audio_saved_at, SpeechJobRecord.created_at)
                    )
                )
                for old_world, old_id, size in candidates:
                    if total <= CACHE_BYTES:
                        break
                    await session.execute(
                        update(SpeechJobRecord)
                        .where(
                            SpeechJobRecord.world_id == old_world,
                            SpeechJobRecord.job_id == old_id,
                        )
                        .values(audio=None, state="expired", error="speech_cache_expired")
                    )
                    total -= size
                if total > CACHE_BYTES:
                    row.audio, row.state, row.error = None, "failed", "speech_cache_full"

    async def recover(self):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await session.execute(
                update(SpeechJobRecord)
                .where(SpeechJobRecord.state == "running")
                .values(state="unknown", error="speech_interrupted")
            )

    async def remote_voice(self, world, key):
        async with self.sessions() as session:
            row = await session.get(RemoteVoiceRecord, (world, key))
            return row.voice_id if row else None

    async def save_remote_voice(self, world, key, identity):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            row = await session.get(RemoteVoiceRecord, (world, key))
            if row is None:
                session.add(RemoteVoiceRecord(world_id=world, cache_key=key, voice_id=identity))
            else:
                row.voice_id = identity
