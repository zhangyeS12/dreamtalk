"""Read-only SQLAlchemy projection for the developer runtime inspector."""

from __future__ import annotations

from sqlalchemy import func, select

from livingworld.domain.identifiers import PlayerId, WorldId
from livingworld.domain.values import Revision
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    CharacterStateRecord,
    LocationRecord,
    ObservationRecord,
    PlayerPresenceRecord,
    PlayerRecord,
    SceneParticipantRecord,
    SceneRecord,
    ScheduledSimulationTriggerRecord,
    SimulationActivationCauseRecord,
    SimulationActivationRecord,
    WorldEventRecord,
    WorldRecord,
)


class SqlAlchemyDeveloperInspectorStore:
    def __init__(self, sessions) -> None:
        self._sessions = sessions

    async def list_worlds(self) -> list[dict[str, object]]:
        async with self._sessions() as session:
            records = (await session.scalars(select(WorldRecord).order_by(WorldRecord.name))).all()
            return [{"world_id": str(item.world_id), "name": item.name} for item in records]

    async def player_presence_revision(self, player_id: PlayerId) -> Revision | None:
        async with self._sessions() as session:
            value = await session.scalar(
                select(PlayerPresenceRecord.revision).where(
                    PlayerPresenceRecord.world_id == player_id.world_id.value,
                    PlayerPresenceRecord.player_id == player_id.value,
                )
            )
            return Revision(value) if value is not None else None

    async def snapshot(self, world_id: WorldId) -> dict[str, object]:
        async with self._sessions() as session:
            world = await session.scalar(
                select(WorldRecord).where(WorldRecord.world_id == world_id.value)
            )
            if world is None:
                raise ValueError("world_not_found")
            locations = (
                await session.scalars(
                    select(LocationRecord)
                    .where(LocationRecord.world_id == world_id.value)
                    .order_by(LocationRecord.name)
                )
            ).all()
            players = (
                await session.execute(
                    select(PlayerRecord, PlayerPresenceRecord)
                    .join(
                        PlayerPresenceRecord,
                        (PlayerPresenceRecord.world_id == PlayerRecord.world_id)
                        & (PlayerPresenceRecord.player_id == PlayerRecord.player_id),
                    )
                    .where(PlayerRecord.world_id == world_id.value)
                    .order_by(PlayerRecord.name)
                )
            ).all()
            characters = (
                await session.execute(
                    select(CharacterRecord, CharacterStateRecord)
                    .outerjoin(
                        CharacterStateRecord,
                        (CharacterStateRecord.world_id == CharacterRecord.world_id)
                        & (CharacterStateRecord.character_id == CharacterRecord.character_id),
                    )
                    .where(CharacterRecord.world_id == world_id.value)
                    .order_by(CharacterRecord.name)
                )
            ).all()
            scenes = (
                await session.scalars(
                    select(SceneRecord)
                    .where(SceneRecord.world_id == world_id.value, SceneRecord.status == "open")
                    .order_by(SceneRecord.started_at, SceneRecord.scene_id)
                )
            ).all()
            participants = (
                await session.scalars(
                    select(SceneParticipantRecord)
                    .where(
                        SceneParticipantRecord.world_id == world_id.value,
                        SceneParticipantRecord.left_at.is_(None),
                    )
                    .order_by(SceneParticipantRecord.joined_at)
                )
            ).all()
            triggers = (
                await session.scalars(
                    select(ScheduledSimulationTriggerRecord)
                    .where(ScheduledSimulationTriggerRecord.world_id == world_id.value)
                    .order_by(
                        ScheduledSimulationTriggerRecord.due_at.desc(),
                        ScheduledSimulationTriggerRecord.enqueue_position.desc(),
                    )
                    .limit(50)
                )
            ).all()
            activations = (
                await session.scalars(
                    select(SimulationActivationRecord)
                    .where(SimulationActivationRecord.world_id == world_id.value)
                    .order_by(
                        SimulationActivationRecord.due_at.desc(),
                        SimulationActivationRecord.enqueue_position.desc(),
                    )
                    .limit(50)
                )
            ).all()
            cause_counts = dict(
                (
                    await session.execute(
                        select(
                            SimulationActivationCauseRecord.activation_id,
                            func.count().label("cause_count"),
                        )
                        .where(SimulationActivationCauseRecord.world_id == world_id.value)
                        .group_by(SimulationActivationCauseRecord.activation_id)
                    )
                ).all()
            )
            events = (
                await session.scalars(
                    select(WorldEventRecord)
                    .where(WorldEventRecord.world_id == world_id.value)
                    .order_by(WorldEventRecord.ledger_position.desc())
                    .limit(50)
                )
            ).all()
            observations = (
                await session.scalars(
                    select(ObservationRecord)
                    .where(
                        ObservationRecord.world_id == world_id.value,
                        ObservationRecord.target_kind == "event",
                    )
                    .order_by(ObservationRecord.observed_at.desc())
                    .limit(100)
                )
            ).all()
            names = {
                **{item.player_id: item.name for item, _ in players},
                **{item.character_id: item.name for item, _ in characters},
            }
            scene_participants: dict[object, list[dict[str, object]]] = {}
            for item in participants:
                scene_participants.setdefault(item.scene_id, []).append(
                    {
                        "kind": item.principal_kind,
                        "principal_id": str(item.principal_id),
                        "name": names.get(item.principal_id, "unknown"),
                        "joined_at": str(item.joined_at.microseconds),
                    }
                )
            return {
                "world": {"world_id": str(world.world_id), "name": world.name},
                "locations": [
                    {"location_id": str(item.location_id), "name": item.name} for item in locations
                ],
                "players": [
                    {
                        "player_id": str(item.player_id),
                        "name": item.name,
                        "location_id": str(presence.location_id),
                        "activity": presence.activity,
                        "availability": presence.availability,
                        "revision": presence.revision,
                    }
                    for item, presence in players
                ],
                "characters": [
                    {
                        "character_id": str(item.character_id),
                        "name": item.name,
                        "location_id": str(state.location_id) if state is not None else None,
                    }
                    for item, state in characters
                ],
                "scenes": [
                    {
                        "scene_id": str(item.scene_id),
                        "location_id": str(item.location_id),
                        "status": item.status,
                        "started_at": str(item.started_at.microseconds),
                        "participants": scene_participants.get(item.scene_id, []),
                    }
                    for item in scenes
                ],
                "triggers": [
                    {
                        "trigger_id": str(item.trigger_id),
                        "kind": item.kind,
                        "status": item.status,
                        "priority": item.priority,
                        "due_at": str(item.due_at.microseconds),
                    }
                    for item in triggers
                ],
                "activations": [
                    {
                        "activation_id": str(item.activation_id),
                        "target": f"{item.target_kind}:{item.target_id}",
                        "kind": item.activation_kind,
                        "priority": item.priority,
                        "due_at": str(item.due_at.microseconds),
                        "fidelity": None,
                        "cause_count": cause_counts.get(item.activation_id, 0),
                    }
                    for item in activations
                ],
                "events": [
                    {
                        "event_id": str(item.event_id),
                        "type": item.event_type,
                        "occurred_at": str(item.occurred_at.microseconds),
                        "ledger_position": item.ledger_position,
                    }
                    for item in events
                ],
                "observations": [
                    {
                        "observation_id": str(item.observation_id),
                        "principal_kind": item.principal_kind,
                        "principal_id": str(item.principal_id),
                        "principal_name": names.get(item.principal_id, "unknown"),
                        "event_id": str(item.target_event_id),
                        "channel": item.channel,
                        "observed_at": str(item.observed_at.microseconds),
                    }
                    for item in observations
                ],
            }
