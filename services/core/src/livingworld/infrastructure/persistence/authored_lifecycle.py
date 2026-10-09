"""Author removals retire participation without erasing canonical facts or history."""

from uuid import uuid5

from sqlalchemy import select

from livingworld.application.errors import ChatTurnUnavailableError
from livingworld.infrastructure.persistence.deletion_models import GroupDissolutionRecord
from livingworld.infrastructure.persistence.models import (
    ChatParticipantRecord,
    WorldContentImportRecord,
)


async def removed_character_roots(session, world):
    # Project identity metadata only; never load card text or other worlds.
    rows = (
        await session.execute(
            select(
                WorldContentImportRecord.import_id,
                WorldContentImportRecord.replaces_import_id,
                WorldContentImportRecord.removed_at,
            ).where(
                WorldContentImportRecord.world_id == world,
                WorldContentImportRecord.kind == "character",
            )
        )
    ).all()
    predecessors = {row.import_id: row.replaces_import_id for row in rows}
    removed = set()
    for row in rows:
        if row.removed_at is None:
            continue
        root, seen = row.import_id, set()
        while predecessors.get(root) is not None:
            if root in seen or predecessors[root] not in predecessors:
                raise ChatTurnUnavailableError("contact_lineage_invalid")
            seen.add(root)
            root = predecessors[root]
        removed.add(root)
    return removed


async def removed_character_ids(session, world):
    return {
        uuid5(root, "livingworld:chat-character:v1")
        for root in await removed_character_roots(session, world)
    }


async def require_active_conversation(session, world, conversation):
    if await session.get(GroupDissolutionRecord, (world, conversation)) is not None:
        raise ChatTurnUnavailableError("chat_group_dissolved")
    roots = set(
        await session.scalars(
            select(ChatParticipantRecord.root_import_id).where(
                ChatParticipantRecord.world_id == world,
                ChatParticipantRecord.conversation_id == conversation,
            )
        )
    )
    if roots & await removed_character_roots(session, world):
        raise ChatTurnUnavailableError("chat_contact_removed")
