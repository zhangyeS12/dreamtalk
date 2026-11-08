"""Single canonical PlayerPresence movement transition used by commands and actions."""

from livingworld.application.ports import UnitOfWork
from livingworld.domain.identifiers import LocationId
from livingworld.domain.participants import PlayerPresence
from livingworld.domain.values import Revision, WorldTime


def resolve_player_movement(
    before: PlayerPresence,
    destination_id: LocationId,
    expected_revision: Revision,
) -> PlayerPresence:
    return before.at_location(destination_id, expected_revision=expected_revision)


def player_moved_payload(before: PlayerPresence, after: PlayerPresence) -> dict[str, object]:
    return {
        "player_id": str(after.player_id.value),
        "from_location_id": str(before.location_id.value),
        "to_location_id": str(after.location_id.value),
        "activity": after.activity.value,
        "availability": after.availability.value,
        "revision": after.revision.value,
    }


async def apply_player_movement(
    uow: UnitOfWork,
    before: PlayerPresence,
    after: PlayerPresence,
    expected_revision: Revision,
    occurred_at: WorldTime,
) -> None:
    await uow.players.replace_presence(after, expected_revision)
    if before.location_id != after.location_id:
        await uow.scenes.leave_active_for_principal(after.player_id, occurred_at)
