import asyncio
from datetime import UTC, datetime
from uuid import UUID

from alembic import command
from livingworld.infrastructure.persistence import Database, models, speech_models
from livingworld.infrastructure.persistence import media_models as media
from livingworld.infrastructure.persistence.migration import (
    HEAD_REVISION,
    STICKER_DESCRIPTION_REVISION,
    _alembic_config,
)
from sqlalchemy import text


async def seed_legacy_content(connection):
    """Synthetic content and bytes, never the user's database or credentials."""
    world = UUID("a" * 32)
    player, character, imported, conversation, turn, message, asset, card, job = (
        UUID(int=value) for value in range(1, 10)
    )
    timestamp = datetime(2026, 10, 1, tzinfo=UTC)

    async def add(record, **values):
        await connection.execute(record.__table__.insert().values(world_id=world, **values))

    await add(models.PlayerRecord, player_id=player, name="Synthetic player", revision=1)
    await add(models.CharacterRecord, character_id=character, name="Synthetic friend", revision=1)
    await add(
        models.WorldContentImportRecord,
        import_id=imported,
        reviewed_hash="b" * 64,
        kind="character",
        snapshot_json='{"synthetic":true}',
        accepted_at=timestamp,
    )
    await add(
        models.ChatConversationRecord,
        conversation_id=conversation,
        player_id=player,
        kind="direct",
        direct_root_import_id=imported,
        created_at_utc=timestamp,
    )
    await add(
        models.ChatTurnRecord,
        turn_id=turn,
        conversation_id=conversation,
        request_id=UUID(int=10),
        fingerprint="c" * 64,
        token_ceiling=1000,
        status="pending",
        created_at_utc=timestamp,
    )
    await add(
        models.ChatMessageRecord,
        message_id=message,
        conversation_id=conversation,
        turn_id=turn,
        position=1,
        sender_character_id=character,
        text="Synthetic saved reply",
        created_at_utc=timestamp,
        media_json='{"synthetic":true}',
    )
    await add(
        media.MediaAssetRecord,
        asset_id=asset,
        digest="d" * 64,
        mime="image/png",
        data=b"synthetic-image-bytes",
        description="Original asset description",
        caption_state="ready",
    )
    await add(
        media.StickerEntryRecord,
        entry_id=UUID(int=11),
        library="public",
        library_key=f"public:{world}",
        asset_id=asset,
        active=True,
        added_at_utc=timestamp,
        description="Independent sticker description",
    )
    await add(
        media.MediaSettingsRecord,
        settings_json='{"secret_ref":"00000000-0000-0000-0000-000000000012"}',
    )
    await add(
        speech_models.VoiceCardRecord,
        card_id=card,
        manifest_json='{"synthetic":true}',
        digest="e" * 64,
        duration_ms=1000,
        audio=b"synthetic-reference-bytes",
    )
    await add(speech_models.VoiceBindingRecord, root_import_id=imported, card_id=card)
    await add(
        speech_models.SpeechJobRecord,
        job_id=job,
        fingerprint="f" * 64,
        player_id=player,
        conversation_id=conversation,
        message_id=message,
        state="ready",
        created_at=timestamp.isoformat(),
        audio=b"synthetic-generated-bytes",
        audio_saved_at=timestamp.isoformat(),
        cache_key="9" * 64,
    )


def test_0052_upgrade_only_adds_example_receipts_and_preserves_existing_rows(tmp_path):
    async def run():
        database = Database(tmp_path)
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(
                    lambda sync: command.upgrade(
                        _alembic_config(sync), STICKER_DESCRIPTION_REVISION
                    )
                )
                await connection.execute(
                    text("INSERT INTO worlds VALUES (:world, 'Synthetic legacy world', 9)"),
                    {"world": "a" * 32},
                )
                await seed_legacy_content(connection)
                tables = (
                    (
                        await connection.execute(
                            text(
                                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                before = {
                    name: (await connection.execute(text(f'SELECT * FROM "{name}"'))).all()
                    for name in tables
                    if name != "alembic_version"
                }
            await database.initialize()
            await database.initialize()
            async with database.engine.connect() as connection:
                assert (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one() == HEAD_REVISION
                assert (
                    await connection.execute(text("SELECT COUNT(*) FROM example_world_setups"))
                ).scalar_one() == 0
                for name, rows in before.items():
                    assert (await connection.execute(text(f'SELECT * FROM "{name}"'))).all() == rows
        finally:
            await database.close()

    asyncio.run(run())
