"""World-scoped creator directory; other runtime locations are never enumerated."""

from uuid import uuid5

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from livingworld.application.director import MAX_CHARACTERS, MAX_LOCATIONS
from livingworld.application.errors import CharacterActivitySetupError, EntityNotFoundError
from livingworld.application.world_locations import (
    LocalLocation,
    LocationCatalogError,
    location_name_key,
)
from livingworld.domain.identifiers import CharacterId, LocationId, PlayerId, WorldId
from livingworld.infrastructure.persistence.location_policy_models import (
    CharacterLocationPolicyRecord,
    LocationAccessRecord,
    LocationPolicyRecord,
)
from livingworld.infrastructure.persistence.location_rules import LocationRules
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
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

    async def locations(self, player_id, characters):
        async with self._sessions() as session:
            selected = await session.scalar(
                select(LocalPlayerBindingRecord.player_id).where(
                    LocalPlayerBindingRecord.world_id == player_id.world_id.value
                )
            )
            if selected != player_id.value:
                raise CharacterActivitySetupError("activity_player_changed")
            permitted = _owned_direct_characters(player_id).subquery()
            states = (
                await session.scalars(
                    select(CharacterStateRecord)
                    .join(permitted, CharacterStateRecord.character_id == permitted.c.character_id)
                    .where(
                        CharacterStateRecord.world_id == player_id.world_id.value,
                        CharacterStateRecord.character_id.in_([item.value for item in characters]),
                    )
                )
            ).all()
            rules = await LocationRules.load(session, player_id.world_id.value)
            result = {}
            for state in states:
                initial, locked, policy_revision = await rules.scope(
                    session, player_id.world_id.value, state.character_id
                )
                result[CharacterId(player_id.world_id, state.character_id)] = (
                    initial,
                    state.location_id,
                    locked,
                    state.revision,
                    policy_revision,
                )
            return result

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
                select(LocationRecord.location_id, LocationRecord.name, LocationRecord.revision)
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
            rules = await LocationRules.load(session, world_id.value)
            locations = [
                LocalLocation(
                    LocationId(world_id, row.location_id),
                    row.name,
                    parent_id=LocationId(world_id, rules.parents[row.location_id])
                    if rules.parents.get(row.location_id)
                    else None,
                    hidden=row.location_id in rules.hidden,
                    allowed_characters=tuple(
                        CharacterId(world_id, char)
                        for loc, char in sorted(rules.grants, key=lambda pair: str(pair[1]))
                        if loc == row.location_id
                    ),
                    revision=row.revision,
                )
                for row in rows
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

    async def _catalogued(self, identity):
        if identity.value == _home_id(identity.world_id):
            return (
                await self._session.get(LocationRecord, (identity.world_id.value, identity.value))
                is not None
            )
        return (
            await self._session.get(
                LocalLocationCatalogRecord, (identity.world_id.value, identity.value)
            )
            is not None
        )

    async def check_edit(self, identity, name):
        if identity.value == _home_id(identity.world_id) or not await self._catalogued(identity):
            raise LocationCatalogError("location_not_editable")
        duplicate = await self._session.scalar(
            select(LocalLocationCatalogRecord.location_id).where(
                LocalLocationCatalogRecord.world_id == identity.world_id.value,
                LocalLocationCatalogRecord.name_key == location_name_key(name),
                LocalLocationCatalogRecord.location_id != identity.value,
            )
        )
        if duplicate is not None:
            raise LocationCatalogError("location_name_exists")

    async def check_options(self, location_id, parent_id, hidden, allowed_characters):
        world = location_id.world_id.value
        rules = await LocationRules.load(self._session, world)
        if parent_id and (
            not await self._catalogued(parent_id)
            or location_id.value in rules.ancestors(parent_id.value)
        ):
            raise LocationCatalogError("location_parent_invalid")
        if (
            len(set(allowed_characters)) != len(allowed_characters)
            or len(allowed_characters) > MAX_CHARACTERS
        ):
            raise LocationCatalogError("location_access_invalid")
        for character in allowed_characters:
            if await self._session.get(CharacterRecord, (world, character.value)) is None:
                raise LocationCatalogError("location_access_invalid")
        changed = LocationRules(
            set(rules.locations) | {location_id.value},
            dict(rules.parents),
            set(rules.hidden),
            set(rules.grants),
            dict(rules.scopes),
        )
        changed.parents[location_id.value] = parent_id.value if parent_id else None
        changed.hidden.discard(location_id.value)
        if hidden:
            changed.hidden.add(location_id.value)
        changed.grants = {pair for pair in changed.grants if pair[0] != location_id.value} | {
            (location_id.value, char.value) for char in allowed_characters
        }
        states = (
            await self._session.scalars(
                select(CharacterStateRecord).where(CharacterStateRecord.world_id == world)
            )
        ).all()
        for state in states:
            initial, _, _ = await rules.scope(self._session, world, state.character_id)
            if (
                initial
                and rules.visible(state.character_id, initial)
                and not changed.visible(state.character_id, initial)
            ):
                raise LocationCatalogError("location_occupied_access")
            if rules.visible(state.character_id, state.location_id) and not changed.visible(
                state.character_id, state.location_id
            ):
                raise LocationCatalogError("location_occupied_access")
            if await rules.allowed(
                self._session, world, state.character_id, state.location_id
            ) and not await changed.allowed(
                self._session, world, state.character_id, state.location_id
            ):
                raise LocationCatalogError("location_scope_conflict")

    async def configure(self, location_id, name, parent_id, hidden, allowed_characters):
        world = location_id.world_id.value
        policy = await self._session.get(LocationPolicyRecord, (world, location_id.value))
        if policy is None:
            policy = LocationPolicyRecord(world_id=world, location_id=location_id.value)
            self._session.add(policy)
        policy.parent_id, policy.hidden = parent_id.value if parent_id else None, hidden
        catalog = await self._session.get(LocalLocationCatalogRecord, (world, location_id.value))
        if catalog:
            catalog.name_key = location_name_key(name)
        await self._session.execute(
            delete(LocationAccessRecord).where(
                LocationAccessRecord.world_id == world,
                LocationAccessRecord.location_id == location_id.value,
            )
        )
        for character in allowed_characters:
            self._session.add(
                LocationAccessRecord(
                    world_id=world, location_id=location_id.value, character_id=character.value
                )
            )

    async def check_character_config(self, character_id, location_id, player_id, policy_revision):
        selected = await self._session.scalar(
            select(LocalPlayerBindingRecord.player_id).where(
                LocalPlayerBindingRecord.world_id == player_id.world_id.value
            )
        )
        if selected != player_id.value:
            raise CharacterActivitySetupError("activity_player_changed")
        if (
            await self._session.scalar(
                _owned_direct_characters(player_id)
                .where(ChatParticipantRecord.character_id == character_id.value)
                .limit(1)
            )
            is None
        ):
            raise CharacterActivitySetupError("activity_character_unavailable")
        if not await self._catalogued(location_id):
            raise CharacterActivitySetupError("activity_location_unavailable")
        rules = await LocationRules.load(self._session, player_id.world_id.value)
        _, _, actual = await rules.scope(
            self._session, player_id.world_id.value, character_id.value
        )
        if policy_revision is None or actual != policy_revision:
            raise CharacterActivitySetupError("activity_location_policy_changed")
        if not rules.visible(character_id.value, location_id.value):
            raise CharacterActivitySetupError("activity_location_hidden")
        state = await self._session.get(
            CharacterStateRecord, (player_id.world_id.value, character_id.value)
        )
        if state is None:
            count = await self._session.scalar(
                select(func.count())
                .select_from(CharacterStateRecord)
                .where(CharacterStateRecord.world_id == player_id.world_id.value)
            )
            if count >= MAX_CHARACTERS:
                raise CharacterActivitySetupError("activity_character_capacity")

    async def configure_character(self, character_id, location_id, locked):
        world = character_id.world_id.value
        policy = await self._session.get(CharacterLocationPolicyRecord, (world, character_id.value))
        if policy is None:
            policy = CharacterLocationPolicyRecord(
                world_id=world, character_id=character_id.value, revision=1
            )
            self._session.add(policy)
        else:
            policy.revision += 1
        policy.initial_location_id, policy.locked = location_id.value, locked

    async def config_destination(self, character_id, root, locked, before):
        rules = await LocationRules.load(self._session, character_id.world_id.value)
        initial, _, _ = await rules.scope(
            self._session, character_id.world_id.value, character_id.value
        )
        if (
            before
            and not locked
            and initial == root.value
            and await rules.allowed(
                self._session,
                character_id.world_id.value,
                character_id.value,
                before.location_id.value,
            )
        ):
            return before.location_id
        return root

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
        rules = await LocationRules.load(self._session, player_id.world_id.value)
        if not rules.visible(character_id.value, location_id.value):
            raise CharacterActivitySetupError("activity_location_hidden")
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
