"""World-scoped creator directory; other runtime locations are never enumerated."""

from uuid import uuid5

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from livingworld.application.director import MAX_CHARACTERS, MAX_LOCATIONS
from livingworld.application.errors import CharacterActivitySetupError, EntityNotFoundError
from livingworld.application.world_locations import (
    LocalLocation,
    LocationCatalogError,
    location_name_key,
)
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId
from livingworld.infrastructure.persistence.models import (
    CharacterStateRecord,
    ChatConversationRecord,
    ChatParticipantRecord,
    LocalLocationCatalogRecord,
    LocalPlayerBindingRecord,
    LocationRecord,
    WorldRecord,
)


def _home_id(world_id: WorldId):
    return uuid5(world_id.value, "livingworld:local-home:v1")


def _owned_direct_characters(player_id: PlayerId):
    return (
        select(ChatParticipantRecord.character_id)
        .join(
            ChatConversationRecord,
            (ChatConversationRecord.world_id == ChatParticipantRecord.world_id)
            & (ChatConversationRecord.conversation_id == ChatParticipantRecord.conversation_id),
        )
        .join(
            LocalPlayerBindingRecord,
            (LocalPlayerBindingRecord.world_id == ChatConversationRecord.world_id)
            & (LocalPlayerBindingRecord.player_id == ChatConversationRecord.player_id),
        )
        .where(
            ChatConversationRecord.world_id == player_id.world_id.value,
            ChatConversationRecord.player_id == player_id.value,
            ChatConversationRecord.kind == "direct",
        )
    )


class SqlAlchemyCharacterActivityDirectory:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def initialized(
        self, player_id: PlayerId, characters: tuple[CharacterId, ...]
    ) -> dict[CharacterId, bool]:
        async with self._sessions() as session:
            selected = await session.scalar(
                select(LocalPlayerBindingRecord.player_id).where(
                    LocalPlayerBindingRecord.world_id == player_id.world_id.value
                )
            )
            if selected != player_id.value:
                raise CharacterActivitySetupError("activity_player_changed")
            if not characters:
                return {}
            # Permission-filter contact identities before projecting existence.
            permitted = _owned_direct_characters(player_id).subquery()
            rows = (
                await session.execute(
                    select(permitted.c.character_id, CharacterStateRecord.character_id.is_not(None))
                    .outerjoin(
                        CharacterStateRecord,
                        (CharacterStateRecord.world_id == player_id.world_id.value)
                        & (CharacterStateRecord.character_id == permitted.c.character_id),
                    )
                    .where(permitted.c.character_id.in_([item.value for item in characters]))
                )
            ).all()
            result = {
                CharacterId(player_id.world_id, identity): placed for identity, placed in rows
            }
            if set(result) != set(characters):
                raise CharacterActivitySetupError("activity_character_unavailable")
            return result


class SqlAlchemyLocalLocationDirectory:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def list_locations(self, world_id: WorldId) -> tuple[LocalLocation, ...]:
        async with self._sessions() as session:
            if (
                await session.scalar(
                    select(WorldRecord.world_id).where(WorldRecord.world_id == world_id.value)
                )
                is None
            ):
                raise EntityNotFoundError("World does not exist")
            # Authorize using creator catalog BEFORE projecting any location name.
            statement = (
                select(LocationRecord.location_id, LocationRecord.name)
                .join(
                    LocalLocationCatalogRecord,
                    (LocalLocationCatalogRecord.world_id == LocationRecord.world_id)
                    & (LocalLocationCatalogRecord.location_id == LocationRecord.location_id),
                )
                .where(LocalLocationCatalogRecord.world_id == world_id.value)
                .order_by(LocationRecord.name, LocationRecord.location_id)
                .limit(MAX_LOCATIONS + 1)
            )
            rows = (await session.execute(statement)).all()
            if len(rows) > MAX_LOCATIONS:
                raise LocationCatalogError("location_catalog_capacity")
            locations = [
                LocalLocation(LocationId(world_id, row.location_id), row.name) for row in rows
            ]
            home_name = await session.scalar(
                select(LocationRecord.name).where(
                    LocationRecord.world_id == world_id.value,
                    LocationRecord.location_id == _home_id(world_id),
                    LocationRecord.name == "家",
                )
            )
            if home_name is not None:
                locations.insert(
                    0, LocalLocation(LocationId(world_id, _home_id(world_id)), "家", True)
                )
            return tuple(locations)


class SqlAlchemyLocalLocationCatalog:
    def __init__(self, session) -> None:
        self._session = session

    async def check_new(self, world_id: WorldId, name: str) -> None:
        key = location_name_key(name)
        duplicate = await self._session.scalar(
            select(LocalLocationCatalogRecord.location_id).where(
                LocalLocationCatalogRecord.world_id == world_id.value,
                LocalLocationCatalogRecord.name_key == key,
            )
        )
        if duplicate is not None:
            raise LocationCatalogError("location_name_exists")
        # The Kernel has already reserved SQLite's writer. Count + create + receipt
        # therefore share one transaction, including a slot for future onboarding.
        count = await self._session.scalar(
            select(func.count())
            .select_from(LocationRecord)
            .where(LocationRecord.world_id == world_id.value)
        )
        home = await self._session.scalar(
            select(LocationRecord.location_id).where(
                LocationRecord.world_id == world_id.value,
                LocationRecord.location_id == _home_id(world_id),
            )
        )
        capacity = MAX_LOCATIONS if home is not None else MAX_LOCATIONS - 1
        if count is None or count >= capacity:
            raise LocationCatalogError("location_catalog_capacity")

    async def add(self, location_id: LocationId, name: str) -> None:
        self._session.add(
            LocalLocationCatalogRecord(
                world_id=location_id.world_id.value,
                location_id=location_id.value,
                name_key=location_name_key(name),
            )
        )
        try:
            await self._session.flush()
        except IntegrityError:
            raise LocationCatalogError("location_creation_conflict") from None

    async def check_initial_activity(
        self, character_id: CharacterId, location_id: LocationId, player_id: PlayerId
    ) -> None:
        # The Kernel reserves the writer first: authorization, capacity, null-CAS,
        # event, state and command receipt all use this one transaction.
        selected = await self._session.scalar(
            select(LocalPlayerBindingRecord.player_id).where(
                LocalPlayerBindingRecord.world_id == player_id.world_id.value
            )
        )
        if selected != player_id.value:
            raise CharacterActivitySetupError("activity_player_changed")
        permitted = await self._session.scalar(
            _owned_direct_characters(player_id)
            .where(ChatParticipantRecord.character_id == character_id.value)
            .limit(1)
        )
        if permitted is None:
            raise CharacterActivitySetupError("activity_character_unavailable")
        catalogued = await self._session.scalar(
            select(LocalLocationCatalogRecord.location_id).where(
                LocalLocationCatalogRecord.world_id == location_id.world_id.value,
                LocalLocationCatalogRecord.location_id == location_id.value,
            )
        )
        home = (
            location_id.value == _home_id(location_id.world_id)
            and await self._session.scalar(
                select(LocationRecord.location_id).where(
                    LocationRecord.world_id == location_id.world_id.value,
                    LocationRecord.location_id == location_id.value,
                    LocationRecord.name == "家",
                )
            )
            is not None
        )
        if catalogued is None and not home:
            raise CharacterActivitySetupError("activity_location_unavailable")
        exists = await self._session.scalar(
            select(CharacterStateRecord.character_id).where(
                CharacterStateRecord.world_id == character_id.world_id.value,
                CharacterStateRecord.character_id == character_id.value,
            )
        )
        if exists is not None:
            raise CharacterActivitySetupError("activity_initial_already_set")
        count = await self._session.scalar(
            select(func.count())
            .select_from(CharacterStateRecord)
            .where(CharacterStateRecord.world_id == character_id.world_id.value)
        )
        if count is None or count >= MAX_CHARACTERS:
            raise CharacterActivitySetupError("activity_character_capacity")
