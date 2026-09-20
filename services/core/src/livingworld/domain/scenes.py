"""Persistent interaction contexts; physical Presence remains authoritative."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from livingworld.domain.errors import DomainInvariantError
from livingworld.domain.identifiers import (
    LocationId,
    PrincipalId,
    SceneId,
    SceneParticipantId,
    WorldId,
)
from livingworld.domain.values import Revision, WorldTime, require_type, same_world, utc_timestamp


class SceneStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class Scene:
    scene_id: SceneId
    world_id: WorldId
    location_id: LocationId
    status: SceneStatus
    started_at: WorldTime
    ended_at: WorldTime | None
    revision: Revision
    created_at_utc: datetime

    def __post_init__(self) -> None:
        require_type(self.scene_id, SceneId, "scene_id")
        require_type(self.location_id, LocationId, "location_id")
        same_world(self.world_id, self.scene_id, self.location_id)
        require_type(self.status, SceneStatus, "status")
        require_type(self.started_at, WorldTime, "started_at")
        require_type(self.revision, Revision, "revision")
        object.__setattr__(
            self, "created_at_utc", utc_timestamp(self.created_at_utc, "created_at_utc")
        )
        if self.ended_at is not None:
            require_type(self.ended_at, WorldTime, "ended_at")
            if self.ended_at < self.started_at:
                raise DomainInvariantError("Scene ended_at must not precede started_at")
        if (self.status is SceneStatus.OPEN) != (self.ended_at is None):
            raise DomainInvariantError(
                "Open Scene must have no ended_at; closed Scene must have ended_at"
            )

    def advance(self, expected_revision: Revision) -> "Scene":
        if self.status is SceneStatus.CLOSED:
            raise DomainInvariantError("Closed Scene cannot change")
        return replace(self, revision=self.revision.advance(expected_revision))

    def close(self, ended_at: WorldTime, expected_revision: Revision) -> "Scene":
        require_type(ended_at, WorldTime, "ended_at")
        advanced = self.advance(expected_revision)
        return replace(advanced, status=SceneStatus.CLOSED, ended_at=ended_at)


@dataclass(frozen=True, slots=True)
class SceneParticipant:
    participant_id: SceneParticipantId
    world_id: WorldId
    scene_id: SceneId
    principal_id: PrincipalId
    joined_at: WorldTime
    left_at: WorldTime | None = None

    def __post_init__(self) -> None:
        require_type(self.participant_id, SceneParticipantId, "participant_id")
        require_type(self.scene_id, SceneId, "scene_id")
        same_world(self.world_id, self.participant_id, self.scene_id, self.principal_id)
        require_type(self.joined_at, WorldTime, "joined_at")
        if self.left_at is not None:
            require_type(self.left_at, WorldTime, "left_at")
            if self.left_at < self.joined_at:
                raise DomainInvariantError("SceneParticipant left_at must not precede joined_at")

    @property
    def active(self) -> bool:
        return self.left_at is None

    def leave(self, left_at: WorldTime) -> "SceneParticipant":
        if not self.active:
            raise DomainInvariantError("SceneParticipant has already left")
        return replace(self, left_at=left_at)
