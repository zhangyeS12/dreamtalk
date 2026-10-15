"""Scope checks happen before retrieval; message attachment writes share the chat transaction."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import jieba
from sqlalchemy import String, and_, case, cast, delete, func, or_, select, update
from sqlalchemy.orm import load_only

from livingworld.application.chat_media import MediaError, MediaSettings, PreparedMedia, prompt_text
from livingworld.infrastructure.persistence.character_card_bindings import (
    CharacterCardBindingRecord,
)
from livingworld.infrastructure.persistence.factions import _characters
from livingworld.infrastructure.persistence.media_models import (
    MediaAssetRecord,
    MediaAttemptRecord,
    MediaCaptionCallRecord,
    MediaSettingsRecord,
    StickerEntryRecord,
)
from livingworld.infrastructure.persistence.models import (
    ChatMessageRecord,
    ChatParticipantRecord,
    WorldRecord,
)


def source_message(source):
    return source.message if hasattr(source, "message") else source.player_message


def library_key(world, library, root=None):
    if library == "personal":
        return "personal"
    if library not in {"public", "character"} or (library == "character") != (root is not None):
        raise MediaError("media_library_invalid")
    return f"{world}:{library}:{root or ''}"


def sticker_scope(world, root):
    return and_(
        StickerEntryRecord.active.is_(True),
        StickerEntryRecord.library_key.in_(
            [library_key(world, "public"), library_key(world, "character", root)]
        ),
    )


def entry_description(entry, asset):
    return entry.description if entry.description is not None else asset.description


def asset_view(asset, description=None):
    return {
        "asset_id": str(asset.asset_id),
        "description": asset.description if description is None else description,
        "mime": asset.mime,
        "source_url": asset.source_url,
        "caption_state": asset.caption_state,
    }


async def root_for_character(session, world, character):
    row = await session.get(CharacterCardBindingRecord, (world, character))
    return row.root_import_id if row is not None else None


async def collect_sticker(session, world, root, asset, description):
    key = library_key(world, "character", root)
    existing = await session.scalar(
        select(StickerEntryRecord).where(
            StickerEntryRecord.library_key == key, StickerEntryRecord.asset_id == asset
        )
    )
    if existing is None:
        session.add(
            StickerEntryRecord(
                entry_id=uuid4(),
                world_id=world,
                library="character",
                library_key=key,
                root_import_id=root,
                asset_id=asset,
                active=True,
                description=description,
                added_at_utc=datetime.now(UTC),
            )
        )
    # A user explicitly removed an entry: automatic collection does not revive it.


async def media_allowed(
    session,
    world,
    conversation,
    source_position,
    frequency,
    *,
    kind="image",
    unlimited_stickers=False,
):
    # Every media kind shares the original-round limit, including recovery.
    sent = await session.scalar(
        select(MediaAttemptRecord.turn_id)
        .where(
            MediaAttemptRecord.world_id == world,
            MediaAttemptRecord.conversation_id == conversation,
            MediaAttemptRecord.source_position == source_position,
            MediaAttemptRecord.sent.is_(True),
        )
        .limit(1)
    )
    if sent is not None:
        return False
    if kind == "sticker" and unlimited_stickers:
        return True
    history = select(func.max(MediaAttemptRecord.source_position)).where(
        MediaAttemptRecord.world_id == world,
        MediaAttemptRecord.conversation_id == conversation,
        MediaAttemptRecord.sent.is_(True),
    )
    if unlimited_stickers:
        # Unknown old receipts conservatively count as images; no body backfill.
        history = history.where(
            or_(MediaAttemptRecord.sent_kind == "image", MediaAttemptRecord.sent_kind.is_(None))
        )
    latest = await session.scalar(history)
    if latest is None:
        return True
    rounds = await session.scalar(
        select(func.count())
        .select_from(ChatMessageRecord)
        .where(
            ChatMessageRecord.world_id == world,
            ChatMessageRecord.conversation_id == conversation,
            ChatMessageRecord.sender_player_id.is_not(None),
            ChatMessageRecord.position > latest,
            ChatMessageRecord.position <= source_position,
        )
    )
    return rounds >= frequency


async def attach_player_media(session, row, entry_id):
    entry = await session.get(StickerEntryRecord, entry_id)
    if entry is None or not entry.active or entry.library != "personal":
        raise MediaError("media_sticker_unavailable")
    asset = await session.get(MediaAssetRecord, entry.asset_id)
    row.media_json = json.dumps(
        {
            **asset_view(asset, entry_description(entry, asset)),
            "kind": "sticker",
            "entry_id": str(entry.entry_id),
            "only_media": not row.text.strip(),
        },
        ensure_ascii=False,
    )
    participants = await session.scalars(
        select(ChatParticipantRecord.character_id).where(
            ChatParticipantRecord.world_id == row.world_id,
            ChatParticipantRecord.conversation_id == row.conversation_id,
        )
    )
    for character in participants:
        root = await root_for_character(session, row.world_id, character)
        if root is not None:
            await collect_sticker(
                session, row.world_id, root, asset.asset_id, entry_description(entry, asset)
            )


async def attach_character_media(session, row, source, prepared):
    if prepared is None:
        return
    settings_row = await session.get(MediaSettingsRecord, row.world_id)
    settings = (
        MediaSettings.model_validate_json(settings_row.settings_json)
        if settings_row
        else MediaSettings()
    )
    original = source_message(source)
    if not settings.enabled or not await media_allowed(
        session,
        row.world_id,
        row.conversation_id,
        original.position,
        settings.frequency,
        kind=prepared.kind,
        unlimited_stickers=settings.unlimited_stickers,
    ):
        return
    root = await root_for_character(session, row.world_id, row.sender_character_id)
    if root is None:
        return
    asset = await session.get(MediaAssetRecord, prepared.asset_id)
    pending_download = asset is None and prepared.data is not None and prepared.entry_id is None
    if not pending_download and (asset is None or asset.world_id not in {None, row.world_id}):
        return
    if prepared.entry_id is not None:
        entry = await session.get(StickerEntryRecord, prepared.entry_id)
        if (
            entry is None
            or not entry.active
            or entry.library_key
            not in {
                library_key(row.world_id, "public"),
                library_key(row.world_id, "character", root),
            }
        ):
            return
    elif not pending_download and asset.world_id != row.world_id:
        return
    attempt = await session.get(MediaAttemptRecord, (row.world_id, source.turn_id.value))
    if attempt is None:
        attempt = MediaAttemptRecord(
            world_id=row.world_id,
            turn_id=source.turn_id.value,
            conversation_id=row.conversation_id,
            source_position=original.position,
            searched=False,
            sent=False,
        )
        session.add(attempt)
    if attempt.sent:
        return
    if pending_download:
        # No durable bytes exist until all attachment admission checks pass.
        asset = MediaAssetRecord(
            asset_id=prepared.asset_id,
            world_id=row.world_id,
            digest=hashlib.sha256(prepared.data).hexdigest(),
            data=prepared.data,
            mime=prepared.mime,
            description=prepared.description,
            source_url=prepared.source_url,
            caption_state=prepared.caption_state,
        )
        session.add(asset)
    attempt.sent = True
    attempt.sent_kind = prepared.kind
    row.media_json = json.dumps(
        {
            **asset_view(asset, prepared.description),
            "kind": prepared.kind,
            "only_media": prepared.only_media,
            "fallback_hash": hashlib.sha256(row.text.encode()).hexdigest(),
        },
        ensure_ascii=False,
    )
    if prepared.only_media:
        row.text = "[表情]" if prepared.kind == "sticker" else "[图片]"
    if prepared.kind == "sticker":
        await collect_sticker(session, row.world_id, root, asset.asset_id, prepared.description)


class SqlAlchemyChatMediaStore:
    def __init__(self, sessions):
        self.sessions = sessions

    async def recover(self, *, clean_orphans=True):
        # Keep call receipts; never replay a caption whose provider result is unknown.
        async with self.sessions() as session, session.begin():
            await session.execute(
                update(MediaAssetRecord)
                .where(MediaAssetRecord.caption_state == "running")
                .values(caption_state="failed")
            )
            await session.execute(
                update(MediaCaptionCallRecord)
                .where(MediaCaptionCallRecord.state == "running")
                .values(state="unknown")
            )
            # Legacy downloads were saved before their message. Startup has no
            # active generations; retain every library entry, including removals,
            # and every historical attachment. Only orphan web assets qualify.
            if not clean_orphans:
                return  # Upgrade continuity must be checked before optional GC.
            attachment_id = case(
                (
                    func.json_valid(ChatMessageRecord.media_json),
                    func.json_extract(ChatMessageRecord.media_json, "$.asset_id"),
                ),
                else_=None,
            )
            # NOT IN lets SQLite build the reference set once, rather than scan
            # all message attachments again for every candidate asset.
            referenced = select(func.lower(func.replace(attachment_id, "-", ""))).where(
                attachment_id.is_not(None)
            )
            in_library = select(StickerEntryRecord.asset_id)
            abandoned = (
                select(MediaAssetRecord.asset_id)
                .where(
                    MediaAssetRecord.source_url.is_not(None),
                    MediaAssetRecord.asset_id.not_in(in_library),
                    cast(MediaAssetRecord.asset_id, String).not_in(referenced),
                    ~select(ChatMessageRecord.message_id)
                    .where(
                        ChatMessageRecord.media_json.is_not(None),
                        func.json_valid(ChatMessageRecord.media_json) == 0,
                    )
                    .exists(),
                )
                .limit(32)
            )
            await session.execute(
                delete(MediaAssetRecord)
                .where(MediaAssetRecord.asset_id.in_(abandoned))
                .execution_options(synchronize_session=False)
            )

    async def scope(self, session, world, library, root=None):
        if await session.get(WorldRecord, world) is None:
            raise MediaError("world_not_found")
        if library == "character" and root not in await _characters(session, world):
            raise MediaError("media_character_unavailable")
        return library_key(world, library, root)

    async def settings(self, world):
        async with self.sessions() as session:
            await self.scope(session, world, "public")
            row = await session.get(MediaSettingsRecord, world)
            return MediaSettings.model_validate_json(row.settings_json) if row else MediaSettings()

    async def local_requested(self):
        async with self.sessions() as session:
            rows = (await session.scalars(select(MediaSettingsRecord.settings_json))).all()
            return any(
                (settings := MediaSettings.model_validate_json(value)).caption_route == "ollama"
                and settings.caption_model.strip()
                and settings.caption_endpoint.rstrip("/")
                in {"http://127.0.0.1:11434", "http://localhost:11434"}
                for value in rows
            )

    async def save_settings(self, world, settings):
        async with self.sessions() as session, session.begin():
            await self.scope(session, world, "public")
            row = await session.get(MediaSettingsRecord, world)
            if row is None:
                row = MediaSettingsRecord(world_id=world, settings_json=settings.model_dump_json())
                session.add(row)
            else:
                row.settings_json = settings.model_dump_json()
        return settings

    async def entries(self, world, library, root=None, offset=0, query=""):
        async with self.sessions() as session:
            key = await self.scope(session, world, library, root)
            stmt = (
                select(StickerEntryRecord, MediaAssetRecord)
                .join(MediaAssetRecord)
                .options(
                    load_only(
                        MediaAssetRecord.asset_id,
                        MediaAssetRecord.description,
                        MediaAssetRecord.mime,
                        MediaAssetRecord.source_url,
                        MediaAssetRecord.caption_state,
                        raiseload=True,
                    )
                )
                .where(StickerEntryRecord.library_key == key, StickerEntryRecord.active.is_(True))
            )
            if query.strip():
                stmt = stmt.where(
                    func.coalesce(
                        StickerEntryRecord.description, MediaAssetRecord.description
                    ).contains(query.strip(), autoescape=True)
                )
            rows = (
                await session.execute(
                    stmt.order_by(StickerEntryRecord.entry_id).offset(offset).limit(101)
                )
            ).all()
            return {
                "items": [
                    {
                        **asset_view(asset, entry_description(entry, asset)),
                        "entry_id": str(entry.entry_id),
                        "library": library,
                    }
                    for entry, asset in rows[:100]
                ],
                "has_more": len(rows) > 100,
            }

    async def import_sticker(self, world, library, root, data, mime, description):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            key = await self.scope(session, world, library, root)
            asset_world = None if library == "personal" else world
            digest = hashlib.sha256(data).hexdigest()
            asset = await session.scalar(
                select(MediaAssetRecord)
                .join(StickerEntryRecord)
                .where(StickerEntryRecord.library_key == key, MediaAssetRecord.digest == digest)
            )
            if asset is None:
                asset = MediaAssetRecord(
                    asset_id=uuid4(),
                    world_id=asset_world,
                    digest=digest,
                    mime=mime,
                    data=data,
                    description=description,
                    source_url=None,
                    caption_state="new",
                )
                session.add(asset)
                await session.flush()
            entry = await session.scalar(
                select(StickerEntryRecord).where(
                    StickerEntryRecord.library_key == key,
                    StickerEntryRecord.asset_id == asset.asset_id,
                )
            )
            if entry is None:
                entry = StickerEntryRecord(
                    entry_id=uuid4(),
                    world_id=asset_world,
                    library=library,
                    library_key=key,
                    root_import_id=root if library == "character" else None,
                    asset_id=asset.asset_id,
                    active=True,
                    added_at_utc=datetime.now(UTC),
                    description=description,
                )
                session.add(entry)
            else:
                entry.active = True
                entry.added_at_utc = datetime.now(UTC)
            return {
                **asset_view(asset, entry_description(entry, asset)),
                "entry_id": str(entry.entry_id),
                "library": library,
            }

    async def edit_entry(self, world, entry_id, description=None, remove=False):
        async with self.sessions() as session, session.begin():
            entry = await session.get(StickerEntryRecord, entry_id)
            if entry is None or entry.world_id not in {None, world}:
                raise MediaError("media_sticker_unavailable")
            await self.scope(session, world, entry.library, entry.root_import_id)
            if remove:
                entry.active = False
            if description is not None:
                entry.description = description

    async def caption_entry_description(self, world, asset_id, entry_id):
        async with self.sessions() as session:
            entry = await session.get(StickerEntryRecord, entry_id)
            if (
                entry is None
                or not entry.active
                or entry.world_id not in {None, world}
                or entry.asset_id != asset_id
            ):
                raise MediaError("media_sticker_unavailable")
            await self.scope(session, world, entry.library, entry.root_import_id)
            return entry.description

    async def apply_entry_caption(self, world, asset_id, entry_id, expected, caption):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self.scope(session, world, "public")
            await session.execute(
                update(StickerEntryRecord)
                .where(
                    StickerEntryRecord.entry_id == entry_id,
                    StickerEntryRecord.asset_id == asset_id,
                    StickerEntryRecord.world_id.is_(None) | (StickerEntryRecord.world_id == world),
                    StickerEntryRecord.active.is_(True),
                    StickerEntryRecord.description.is_(None)
                    if expected is None
                    else StickerEntryRecord.description == expected,
                )
                .values(description=caption[:200])
            )

    async def asset(self, world, asset_id):
        async with self.sessions() as session:
            await self.scope(session, world, "public")
            row = await session.get(MediaAssetRecord, asset_id)
            if row is None or row.world_id not in {None, world}:
                raise MediaError("media_asset_unavailable")
            return row.data, row.mime

    async def description(self, asset_id):
        async with self.sessions() as session:
            row = await session.get(MediaAssetRecord, asset_id)
            if row is None:
                raise MediaError("media_asset_unavailable")
            return row.description

    async def candidates(self, session, world, root, query):
        # Filter authorization in SQL before ranking, including the global personal library.
        terms = tuple(
            dict.fromkeys(t.strip().casefold() for t in jieba.cut(query) if len(t.strip()) >= 2)
        )[:12]
        if not terms:
            return []
        statement = (
            select(StickerEntryRecord, MediaAssetRecord)
            .join(MediaAssetRecord)
            .options(
                load_only(
                    MediaAssetRecord.asset_id,
                    MediaAssetRecord.description,
                    MediaAssetRecord.source_url,
                )
            )
            .where(
                sticker_scope(world, root),
                or_(
                    *(
                        func.coalesce(
                            StickerEntryRecord.description, MediaAssetRecord.description
                        ).contains(term, autoescape=True)
                        for term in terms
                    )
                ),
            )
        )
        rows = (await session.execute(statement.limit(200))).all()
        ranked = sorted(
            rows,
            key=lambda pair: (
                sum(term in entry_description(*pair).casefold() for term in terms),
                pair[0].library == "character",
            ),
            reverse=True,
        )
        return ranked[:5]

    async def library_catalog(self, session, world, root, query):
        """Current library knowledge is independent of permission to send this round."""
        if root is None:
            return [], 0
        scope = sticker_scope(world, root)
        count = await session.scalar(
            select(func.count(func.distinct(StickerEntryRecord.asset_id))).where(scope)
        )
        if count == 0:
            return [], 0
        recent = (
            await session.execute(
                select(StickerEntryRecord, MediaAssetRecord)
                .join(MediaAssetRecord)
                .options(
                    load_only(
                        MediaAssetRecord.asset_id,
                        MediaAssetRecord.description,
                        MediaAssetRecord.source_url,
                    )
                )
                .where(scope)
                .order_by(
                    StickerEntryRecord.added_at_utc.desc().nulls_last(),
                    StickerEntryRecord.entry_id.desc(),
                )
                .limit(10)
            )
        ).all()
        rows, seen = [], set()

        def add(candidates, limit):
            for entry, asset in candidates:
                if len(rows) >= limit:
                    break
                if asset.asset_id not in seen:
                    seen.add(asset.asset_id)
                    rows.append((entry, asset))

        if count <= 5:
            add(recent, 5)
        else:
            # Keep the newest additions visible even for a generic library
            # question; fill the rest with relevant matches, then recent items.
            add(recent, 2)
            add(await self.candidates(session, world, root, query), 5)
            add(recent, 5)
        return rows, count

    async def prompt_context(self, source, speaker):
        original = source_message(source)
        world = original.conversation_id.world_id.value
        settings = await self.settings(world)
        async with self.sessions() as session:
            root = await root_for_character(session, world, speaker.value)
            image_allowed = (
                settings.enabled
                and root is not None
                and await media_allowed(
                    session,
                    world,
                    original.conversation_id.value,
                    original.position,
                    settings.frequency,
                )
            )
            sticker_allowed = image_allowed or (
                settings.enabled
                and root is not None
                and settings.unlimited_stickers
                and await media_allowed(
                    session,
                    world,
                    original.conversation_id.value,
                    original.position,
                    settings.frequency,
                    kind="sticker",
                    unlimited_stickers=True,
                )
            )
            if settings.enabled:
                rows, count = await self.library_catalog(
                    session, world, root, prompt_text(original)
                )
            else:
                rows, count = [], None
            library_available = settings.enabled and root is not None
            allowed = sticker_allowed or image_allowed
            latest_added = max(
                (e.added_at_utc for e, _ in rows if e.added_at_utc is not None), default=None
            )
            return {
                "media_allowed": allowed,
                "sticker_allowed": sticker_allowed,
                "image_allowed": image_allowed,
                "library_has_stickers": bool(count),
                "library_available": library_available,
                "library_sticker_count": count if library_available else None,
                "library_complete": library_available and len(rows) == count,
                "library_latest_added_at_utc": latest_added.isoformat() if latest_added else None,
                "online_images_allowed": allowed and settings.online_enabled,
                "media_candidates": [
                    {
                        "entry_id": str(e.entry_id),
                        "library": e.library,
                        "description": entry_description(e, a)[:200],
                        "added_at_utc": e.added_at_utc.isoformat() if e.added_at_utc else None,
                        "newest_known_addition": latest_added is not None
                        and e.added_at_utc == latest_added,
                    }
                    for e, a in rows
                ],
            }

    async def select_for_reply(self, source, speaker, intent):
        if intent.kind != "sticker":
            return None
        original = source_message(source)
        world = original.conversation_id.world_id.value
        settings = await self.settings(world)
        async with self.sessions() as session:
            root = await root_for_character(session, world, speaker.value)
            if (
                root is None
                or not settings.enabled
                or not await media_allowed(
                    session,
                    world,
                    original.conversation_id.value,
                    original.position,
                    settings.frequency,
                    kind="sticker",
                    unlimited_stickers=settings.unlimited_stickers,
                )
            ):
                return None
            if intent.entry_id is not None:
                entry = await session.get(StickerEntryRecord, intent.entry_id)
                if (
                    entry is not None
                    and entry.active
                    and entry.library_key
                    in {library_key(world, "public"), library_key(world, "character", root)}
                ):
                    asset = await session.get(MediaAssetRecord, entry.asset_id)
                    return PreparedMedia(
                        asset.asset_id,
                        "sticker",
                        entry_description(entry, asset),
                        asset.source_url,
                        entry.entry_id,
                        intent.only_media,
                    )
            rows = await self.candidates(
                session, world, root, intent.intent + " " + intent.keywords
            )
            if rows:
                entry, asset = rows[0]
                return PreparedMedia(
                    asset.asset_id,
                    "sticker",
                    entry_description(entry, asset),
                    asset.source_url,
                    entry.entry_id,
                    intent.only_media,
                )
            return None

    async def claim_search(self, source, speaker, *, kind="image"):
        original = source_message(source)
        world = original.conversation_id.world_id.value
        settings = await self.settings(world)
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            if (
                not settings.enabled
                or not settings.online_enabled
                or not await media_allowed(
                    session,
                    world,
                    original.conversation_id.value,
                    original.position,
                    settings.frequency,
                    kind=kind,
                    unlimited_stickers=settings.unlimited_stickers,
                )
            ):
                return False
            if await root_for_character(session, world, speaker.value) is None:
                return False
            searched = await session.scalar(
                select(MediaAttemptRecord.turn_id)
                .where(
                    MediaAttemptRecord.world_id == world,
                    MediaAttemptRecord.conversation_id == original.conversation_id.value,
                    MediaAttemptRecord.source_position == original.position,
                    MediaAttemptRecord.searched.is_(True),
                )
                .limit(1)
            )
            if searched is not None:
                return False
            row = await session.get(MediaAttemptRecord, (world, source.turn_id.value))
            if row is not None and (row.searched or row.sent):
                return False
            if row is None:
                row = MediaAttemptRecord(
                    world_id=world,
                    turn_id=source.turn_id.value,
                    conversation_id=original.conversation_id.value,
                    source_position=original.position,
                    searched=True,
                    sent=False,
                )
                session.add(row)
            else:
                row.searched = True
            return True

    async def claim_prepared_caption(self, source, prepared, settings):
        world = source_message(source).conversation_id.world_id.value
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self.scope(session, world, "public")
            await self._claim_caption_call(session, world, prepared.asset_id, settings)

    async def claim_caption(self, world, asset_id, settings, *, retry=False):
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            await self.scope(session, world, "public")
            asset = await session.get(MediaAssetRecord, asset_id)
            if asset is None or asset.world_id not in {None, world}:
                raise MediaError("media_asset_unavailable")
            if asset.caption_state == "running":
                raise MediaError("media_caption_in_progress")
            if asset.caption_state == "done":
                return None
            if asset.caption_state == "failed" and not retry:
                raise MediaError("media_caption_failed")
            await self._claim_caption_call(session, world, asset_id, settings)
            asset.caption_state = "running"
            return asset.data, asset.mime

    async def _claim_caption_call(self, session, world, asset_id, settings):
        if not settings.caption_model.strip():
            raise MediaError("media_caption_not_configured")
        if settings.caption_route == "compatible" and not settings.remote_caption_consent:
            raise MediaError("media_caption_consent_required")
        day = datetime.now(UTC).date().isoformat()
        is_local = settings.caption_route == "ollama"
        if not is_local:
            count = await session.scalar(
                select(func.count())
                .select_from(MediaCaptionCallRecord)
                .where(
                    MediaCaptionCallRecord.utc_day == day,
                    MediaCaptionCallRecord.is_local.is_not(True),
                )
            )
            if count >= settings.daily_caption_limit:
                raise MediaError("media_caption_daily_limit")
        session.add(
            MediaCaptionCallRecord(
                call_id=uuid4(),
                world_scope=world,
                asset_id=asset_id,
                utc_day=day,
                state="running",
                usage_json=None,
                is_local=is_local,
            )
        )

    async def finish_caption(self, world, asset_id, caption, usage):
        await self._caption_result(world, asset_id, caption, usage, "done")

    async def fail_caption(self, world, asset_id):
        await self._caption_result(world, asset_id, None, None, "failed")

    async def _caption_result(self, world, asset_id, caption, usage, state):
        async with self.sessions() as session, session.begin():
            asset = await session.get(MediaAssetRecord, asset_id)
            if asset is not None and asset.caption_state == "running":
                asset.caption_state = state
                if caption:
                    asset.description = caption[:200]
            calls = await session.scalars(
                select(MediaCaptionCallRecord).where(
                    MediaCaptionCallRecord.world_scope == world,
                    MediaCaptionCallRecord.asset_id == asset_id,
                    MediaCaptionCallRecord.state == "running",
                )
            )
            for call in calls:
                call.state, call.usage_json = state, json.dumps(usage) if usage else None

    async def usage(self, world):
        async with self.sessions() as session:
            await self.scope(session, world, "public")
            day = datetime.now(UTC).date().isoformat()
            count = await session.scalar(
                select(func.count())
                .select_from(MediaCaptionCallRecord)
                .where(
                    MediaCaptionCallRecord.utc_day == day,
                    MediaCaptionCallRecord.is_local.is_not(True),
                )
            )
            return {"utc_day": day, "caption_calls": count}
