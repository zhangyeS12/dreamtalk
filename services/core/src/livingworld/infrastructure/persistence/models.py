"""SQLAlchemy persistence records. These classes are never domain entities."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from livingworld.domain.values import WorldTime
from livingworld.infrastructure.persistence.types import (
    DecimalTextStorage,
    JSONTextStorage,
    UTCTimestampStorage,
    UUIDStorage,
    WorldTimeStorage,
)


class Base(DeclarativeBase):
    pass


class WorldRecord(Base):
    __tablename__ = "worlds"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    clock: Mapped[WorldClockRecord] = relationship(
        back_populates="world", cascade="save-update, merge", lazy="selectin", uselist=False
    )


class WorldClockRecord(Base):
    __tablename__ = "world_clocks"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    logical_time: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    observed_wall_time_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    time_scale: Mapped[Decimal] = mapped_column(DecimalTextStorage(), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    world: Mapped[WorldRecord] = relationship(back_populates="clock")
    __table_args__ = (
        CheckConstraint("state IN ('running', 'paused')", name="ck_world_clocks_state"),
    )


class LocationRecord(Base):
    __tablename__ = "locations"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    location_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class LocationConnectionRecord(Base):
    __tablename__ = "location_connections"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    source_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    target_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "source_id"], ["locations.world_id", "locations.location_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "target_id"], ["locations.world_id", "locations.location_id"]
        ),
    )


class PlayerRecord(Base):
    __tablename__ = "players"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class LocalPlayerBindingRecord(Base):
    """One selected Player per World in this local OS user's data directory."""

    __tablename__ = "local_player_bindings"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
    )


class LocalUserProfileRecord(Base):
    __tablename__ = "local_user_profile"
    singleton: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("singleton = 1", name="ck_local_user_profile_singleton"),
        CheckConstraint("revision > 0", name="ck_local_user_profile_revision"),
    )


class LocalWorldProfileRecord(Base):
    __tablename__ = "local_world_profiles"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (CheckConstraint("revision > 0", name="ck_local_world_profile_revision"),)


class PlayerPresenceRecord(Base):
    __tablename__ = "player_presences"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    location_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    activity: Mapped[str] = mapped_column(String(16), nullable=False)
    availability: Mapped[str] = mapped_column(String(16), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        CheckConstraint("activity IN ('active', 'inactive')", name="ck_presence_activity"),
        CheckConstraint("availability IN ('busy', 'available')", name="ck_presence_availability"),
        Index(
            "ix_player_presence_active_location",
            "world_id",
            "location_id",
            "player_id",
            sqlite_where=text("activity = 'active'"),
        ),
    )


class CharacterRecord(Base):
    __tablename__ = "characters"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class CharacterStateRecord(Base):
    __tablename__ = "character_states"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    location_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        Index(
            "ix_character_state_location",
            "world_id",
            "location_id",
            "character_id",
        ),
    )


class SceneRecord(Base):
    __tablename__ = "scenes"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    scene_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    location_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    ended_at: Mapped[WorldTime | None] = mapped_column(WorldTimeStorage())
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "location_id"], ["locations.world_id", "locations.location_id"]
        ),
        CheckConstraint("status IN ('open', 'closed')", name="ck_scene_status"),
        CheckConstraint(
            "(status = 'open' AND ended_at IS NULL) OR "
            "(status = 'closed' AND ended_at IS NOT NULL AND ended_at >= started_at)",
            name="ck_scene_lifecycle",
        ),
        CheckConstraint("revision >= 0", name="ck_scene_revision"),
        Index("ix_scenes_world_status", "world_id", "status", "scene_id"),
    )


class SceneParticipantRecord(Base):
    __tablename__ = "scene_participants"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    participant_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    scene_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    principal_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    principal_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    principal_character_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    principal_player_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    joined_at: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    left_at: Mapped[WorldTime | None] = mapped_column(WorldTimeStorage())
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "scene_id"], ["scenes.world_id", "scenes.scene_id"]),
        ForeignKeyConstraint(
            ["world_id", "principal_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "principal_player_id"], ["players.world_id", "players.player_id"]
        ),
        CheckConstraint(
            "(principal_kind = 'character' AND principal_character_id IS NOT NULL "
            "AND principal_character_id = principal_id AND principal_player_id IS NULL) OR "
            "(principal_kind = 'player' AND principal_player_id IS NOT NULL "
            "AND principal_player_id = principal_id AND principal_character_id IS NULL)",
            name="ck_scene_participant_principal",
        ),
        CheckConstraint(
            "left_at IS NULL OR left_at >= joined_at", name="ck_scene_participant_time"
        ),
        Index(
            "uq_scene_active_principal",
            "world_id",
            "principal_kind",
            "principal_id",
            unique=True,
            sqlite_where=text("left_at IS NULL"),
        ),
        Index(
            "ix_scene_active_participants",
            "world_id",
            "scene_id",
            "left_at",
            "principal_kind",
            "principal_id",
        ),
        Index(
            "ix_scene_participant_history",
            "world_id",
            "principal_kind",
            "principal_id",
            "joined_at",
        ),
    )


class RelationshipRecord(Base):
    __tablename__ = "relationships"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    source_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    target_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    source_character_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    source_player_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    target_character_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    target_player_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    affinity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    trust: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    familiarity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    __table_args__ = (
        CheckConstraint(
            "typeof(affinity) = 'integer' AND affinity BETWEEN -100 AND 100",
            name="ck_relationship_affinity",
        ),
        CheckConstraint(
            "typeof(trust) = 'integer' AND trust BETWEEN -100 AND 100", name="ck_relationship_trust"
        ),
        CheckConstraint(
            "typeof(familiarity) = 'integer' AND familiarity BETWEEN 0 AND 100",
            name="ck_relationship_familiarity",
        ),
        ForeignKeyConstraint(
            ["world_id", "source_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "source_player_id"], ["players.world_id", "players.player_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "target_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "target_player_id"], ["players.world_id", "players.player_id"]
        ),
        CheckConstraint(
            "(source_kind = 'character' AND source_character_id IS NOT NULL "
            "AND source_character_id = source_id "
            "AND source_player_id IS NULL) OR "
            "(source_kind = 'player' AND source_player_id IS NOT NULL "
            "AND source_player_id = source_id "
            "AND source_character_id IS NULL)",
            name="ck_relationship_source",
        ),
        CheckConstraint(
            "(target_kind = 'character' AND target_character_id IS NOT NULL "
            "AND target_character_id = target_id "
            "AND target_player_id IS NULL) OR "
            "(target_kind = 'player' AND target_player_id IS NOT NULL "
            "AND target_player_id = target_id "
            "AND target_character_id IS NULL)",
            name="ck_relationship_target",
        ),
    )


class WorldEventRecord(Base):
    __tablename__ = "world_events"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    event_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    payload: Mapped[object] = mapped_column(JSONTextStorage(), nullable=False)
    payload_version: Mapped[int] = mapped_column(Integer, nullable=False)
    causation_event_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    causation_request_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    correlation_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    idempotency_key: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    # Retained SQLite ADD COLUMN default is migration compatibility, not allocation.
    ledger_position: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "causation_event_id"], ["world_events.world_id", "world_events.event_id"]
        ),
        CheckConstraint(
            "causation_event_id IS NULL OR causation_request_id IS NULL",
            name="ck_world_event_one_causation",
        ),
        CheckConstraint("payload_version >= 1", name="ck_world_event_payload_version"),
        UniqueConstraint("world_id", "idempotency_key", name="uq_world_event_idempotency"),
        Index("ix_world_events_occurred", "world_id", "occurred_at", "event_id"),
        CheckConstraint(
            "typeof(ledger_position) = 'integer' AND ledger_position > 0",
            name="ck_world_event_ledger_position",
        ),
        Index("uq_world_event_ledger_position", "world_id", "ledger_position", unique=True),
    )


class WorldLedgerCursorRecord(Base):
    __tablename__ = "world_ledger_cursors"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    last_position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint(
            "typeof(last_position) = 'integer' AND last_position >= 0",
            name="ck_world_ledger_cursor_position",
        ),
    )


class KnowledgeAssertionRecord(Base):
    __tablename__ = "knowledge_assertions"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    assertion_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    owner_character_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    owner_player_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    subject: Mapped[str] = mapped_column(String, nullable=False)
    predicate: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[object] = mapped_column(JSONTextStorage(), nullable=False)
    epistemic_status: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(DecimalTextStorage())
    valid_from: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    valid_to: Mapped[WorldTime | None] = mapped_column(WorldTimeStorage())
    provenance_event_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    source_assertion_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "owner_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "owner_player_id"], ["players.world_id", "players.player_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "provenance_event_id"],
            ["world_events.world_id", "world_events.event_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "source_assertion_id"],
            ["knowledge_assertions.world_id", "knowledge_assertions.assertion_id"],
        ),
        CheckConstraint(
            "(scope = 'truth' AND owner_character_id IS NULL AND owner_player_id IS NULL) OR "
            "(scope = 'character_belief' AND owner_character_id IS NOT NULL "
            "AND owner_player_id IS NULL) OR "
            "(scope = 'player_knowledge' AND owner_player_id IS NOT NULL "
            "AND owner_character_id IS NULL)",
            name="ck_knowledge_owner",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_knowledge_validity"),
        Index("ix_knowledge_character_owner", "world_id", "scope", "owner_character_id"),
        Index("ix_knowledge_player_owner", "world_id", "scope", "owner_player_id"),
    )


class ObservationRecord(Base):
    __tablename__ = "observations"
    __mapper_args__ = {"eager_defaults": False}
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    principal_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    principal_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_at: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    principal_character_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    principal_player_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    target_event_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    target_assertion_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    created_at: Mapped[datetime | None] = mapped_column(UTCTimestampStorage())
    observation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    basis: Mapped[str | None] = mapped_column(String(32), server_default=text("NULL"))
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "principal_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "principal_player_id"], ["players.world_id", "players.player_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "target_event_id"], ["world_events.world_id", "world_events.event_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "target_assertion_id"],
            ["knowledge_assertions.world_id", "knowledge_assertions.assertion_id"],
        ),
        CheckConstraint(
            "(principal_kind = 'character' AND principal_character_id IS NOT NULL "
            "AND principal_character_id = principal_id "
            "AND principal_player_id IS NULL) OR "
            "(principal_kind = 'player' AND principal_player_id IS NOT NULL "
            "AND principal_player_id = principal_id "
            "AND principal_character_id IS NULL)",
            name="ck_observation_principal",
        ),
        CheckConstraint(
            "(target_kind = 'event' AND target_event_id IS NOT NULL "
            "AND target_event_id = target_id "
            "AND target_assertion_id IS NULL) OR "
            "(target_kind = 'assertion' AND target_assertion_id IS NOT NULL "
            "AND target_assertion_id = target_id "
            "AND target_event_id IS NULL)",
            name="ck_observation_target",
        ),
        CheckConstraint(
            "channel IN ('witnessed', 'told', 'message', 'news', 'document', 'inferred')",
            name="ck_observation_channel",
        ),
        Index(
            "uq_observation_event_principal",
            "world_id",
            "target_event_id",
            "principal_kind",
            "principal_id",
            unique=True,
            sqlite_where=text("target_kind = 'event' AND basis = 'event_occurrence'"),
        ),
        Index(
            "ix_observation_principal_history",
            "world_id",
            "principal_kind",
            "principal_id",
            "target_kind",
            "observed_at",
        ),
    )


class CharacterMemoryRecord(Base):
    __tablename__ = "character_memories"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    memory_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    owner_character_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    kind_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_format: Mapped[str] = mapped_column(String(24), nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    experienced_from: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    experienced_to: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    formed_at: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    salience: Mapped[int | None] = mapped_column(Integer)
    provenance_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance_version: Mapped[int] = mapped_column(Integer, nullable=False)
    sources: Mapped[list[EpisodicMemoryObservationSourceRecord]] = relationship(
        back_populates="memory",
        order_by="EpisodicMemoryObservationSourceRecord.position",
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "owner_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        CheckConstraint("kind = 'episodic'", name="ck_character_memory_kind"),
        CheckConstraint(
            "typeof(kind_version) = 'integer' AND kind_version = 1",
            name="ck_character_memory_kind_version",
        ),
        CheckConstraint(
            "length(trim(content)) > 0 AND length(CAST(content AS BLOB)) <= 16384",
            name="ck_character_memory_content",
        ),
        CheckConstraint(
            "content_format = 'plain_text' AND content_version = 1",
            name="ck_character_memory_content_format",
        ),
        CheckConstraint(
            "experienced_to >= experienced_from AND formed_at >= experienced_to",
            name="ck_character_memory_chronology",
        ),
        CheckConstraint(
            "salience IS NULL OR (typeof(salience) = 'integer' AND salience BETWEEN 0 AND 100)",
            name="ck_character_memory_salience",
        ),
        CheckConstraint(
            "provenance_kind = 'observation_evidence' AND provenance_version = 1",
            name="ck_character_memory_provenance",
        ),
        Index(
            "ix_character_memories_world_owner",
            "world_id",
            "owner_character_id",
            "memory_id",
        ),
        Index(
            "ix_character_memories_owner_experienced",
            "world_id",
            "owner_character_id",
            "experienced_to",
            "formed_at",
            "memory_id",
        ),
        Index(
            "ix_character_memories_owner_formed",
            "world_id",
            "owner_character_id",
            "formed_at",
            "memory_id",
        ),
    )


class EpisodicMemoryObservationSourceRecord(Base):
    __tablename__ = "episodic_memory_observation_sources"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    memory_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    position: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    observation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    memory: Mapped[CharacterMemoryRecord] = relationship(back_populates="sources")
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "memory_id"],
            ["character_memories.world_id", "character_memories.memory_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "observation_id"],
            ["observations.world_id", "observations.observation_id"],
        ),
        UniqueConstraint(
            "world_id",
            "memory_id",
            "observation_id",
            name="uq_episodic_memory_observation_source",
        ),
        CheckConstraint(
            "typeof(position) = 'integer' AND position >= 0",
            name="ck_episodic_memory_source_position",
        ),
        Index(
            "ix_episodic_memory_source_observation",
            "world_id",
            "observation_id",
            "memory_id",
        ),
    )


class CommandReceiptRecord(Base):
    __tablename__ = "command_receipts"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    request_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    command_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCTimestampStorage())
    result_kind: Mapped[str | None] = mapped_column(String(24))
    result_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    result_event_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    result_assertion_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    result_payload: Mapped[str | None] = mapped_column(Text)
    command_fingerprint: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint(
            "(command_fingerprint IS NULL AND result_payload IS NULL) OR "
            "(command_fingerprint IS NOT NULL AND length(command_fingerprint) = 64 "
            "AND result_payload IS NOT NULL AND status IN ('committed', 'rejected') "
            "AND completed_at IS NOT NULL)",
            name="ck_command_receipt_command_result",
        ),
        Index(
            "uq_command_request_identity",
            "request_id",
            unique=True,
            sqlite_where=text("command_fingerprint IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["world_id", "result_event_id"], ["world_events.world_id", "world_events.event_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "result_assertion_id"],
            ["knowledge_assertions.world_id", "knowledge_assertions.assertion_id"],
        ),
        CheckConstraint(
            "(result_kind IS NULL AND result_id IS NULL AND result_event_id IS NULL "
            "AND result_assertion_id IS NULL) OR "
            "(result_kind IS NOT NULL AND result_kind = 'event' AND result_id IS NOT NULL "
            "AND result_event_id IS NOT NULL AND result_event_id = result_id "
            "AND result_assertion_id IS NULL) OR "
            "(result_kind IS NOT NULL AND result_kind = 'assertion' AND result_id IS NOT NULL "
            "AND result_assertion_id IS NOT NULL AND result_assertion_id = result_id "
            "AND result_event_id IS NULL)",
            name="ck_command_receipt_result",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="ck_command_receipt_completion",
        ),
    )


class SimulationQueueCursorRecord(Base):
    __tablename__ = "simulation_queue_cursors"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    last_position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("last_position >= 0", name="ck_simulation_queue_cursor_position"),
    )


class ScheduledSimulationTriggerRecord(Base):
    __tablename__ = "simulation_scheduled_triggers"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    trigger_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    due_at: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    enqueue_position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[object] = mapped_column(JSONTextStorage(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    fired_at_utc: Mapped[datetime | None] = mapped_column(UTCTimestampStorage())
    cancelled_at_utc: Mapped[datetime | None] = mapped_column(UTCTimestampStorage())
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    causation_request_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    correlation_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    activation_target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    activation_target_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    activation_target_character_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    activation_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    activation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    activation_coalescing_key: Mapped[str | None] = mapped_column(String(128))
    activation_attention: Mapped[str] = mapped_column(String(16), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "world_id", "enqueue_position", name="uq_simulation_trigger_enqueue_position"
        ),
        Index(
            "ix_simulation_trigger_due",
            "world_id",
            "status",
            "due_at",
            "priority",
            "enqueue_position",
        ),
        CheckConstraint("typeof(due_at) = 'integer'", name="ck_simulation_trigger_due_at_type"),
        CheckConstraint("priority IN (-1,0,1)", name="ck_simulation_trigger_priority"),
        CheckConstraint("enqueue_position > 0", name="ck_simulation_trigger_enqueue_position"),
        CheckConstraint(
            "payload_version >= 1 AND payload_version <= 65535",
            name="ck_simulation_trigger_payload_version",
        ),
        CheckConstraint(
            "length(kind) >= 1 AND length(kind) <= 128", name="ck_simulation_trigger_kind"
        ),
        CheckConstraint(
            "(status = 'pending' AND fired_at_utc IS NULL AND cancelled_at_utc IS NULL) OR "
            "(status = 'fired' AND fired_at_utc IS NOT NULL AND cancelled_at_utc IS NULL) OR "
            "(status = 'cancelled' AND fired_at_utc IS NULL AND cancelled_at_utc IS NOT NULL)",
            name="ck_simulation_trigger_status",
        ),
        ForeignKeyConstraint(
            ["world_id", "activation_target_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        CheckConstraint(
            "(activation_target_kind = 'world' AND activation_target_id = world_id "
            "AND activation_target_character_id IS NULL) OR "
            "(activation_target_kind = 'character' "
            "AND activation_target_character_id = activation_target_id)",
            name="ck_simulation_trigger_activation_target",
        ),
        CheckConstraint(
            "activation_version >= 1 AND activation_version <= 65535",
            name="ck_simulation_trigger_activation_version",
        ),
        CheckConstraint(
            "activation_attention IN ('none','active') "
            "AND NOT (activation_target_kind = 'world' AND activation_attention = 'active')",
            name="ck_simulation_trigger_activation_attention",
        ),
    )


class SimulationActivationRecord(Base):
    __tablename__ = "simulation_activations"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    activation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    source_trigger_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    kind: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_version: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[WorldTime] = mapped_column(WorldTimeStorage(), nullable=False)
    payload: Mapped[object] = mapped_column(JSONTextStorage(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    materialized_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    target_character_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    activation_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    activation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    enqueue_position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    coalescing_key: Mapped[str | None] = mapped_column(String(128))
    attention: Mapped[str] = mapped_column(String(16), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "source_trigger_id"],
            ["simulation_scheduled_triggers.world_id", "simulation_scheduled_triggers.trigger_id"],
        ),
        UniqueConstraint("world_id", "source_trigger_id", name="uq_simulation_activation_source"),
        UniqueConstraint(
            "world_id", "enqueue_position", name="uq_simulation_activation_enqueue_position"
        ),
        ForeignKeyConstraint(
            ["world_id", "target_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        CheckConstraint(
            "(target_kind = 'world' AND target_id = world_id "
            "AND target_character_id IS NULL) OR "
            "(target_kind = 'character' AND target_character_id = target_id)",
            name="ck_simulation_activation_target",
        ),
        CheckConstraint(
            "activation_version >= 1 AND activation_version <= 65535",
            name="ck_simulation_activation_version",
        ),
        CheckConstraint("priority IN (-1,0,1)", name="ck_simulation_activation_priority"),
        CheckConstraint("enqueue_position > 0", name="ck_simulation_activation_enqueue_position"),
        CheckConstraint(
            "attention IN ('none','active') "
            "AND NOT (target_kind = 'world' AND attention = 'active')",
            name="ck_simulation_activation_attention",
        ),
        CheckConstraint("typeof(due_at) = 'integer'", name="ck_simulation_activation_due_at_type"),
        CheckConstraint(
            "payload_version >= 1 AND payload_version <= 65535",
            name="ck_simulation_activation_payload_version",
        ),
        CheckConstraint(
            "length(kind) >= 1 AND length(kind) <= 128", name="ck_simulation_activation_kind"
        ),
        CheckConstraint("status = 'pending'", name="ck_simulation_activation_status"),
        Index(
            "ix_simulation_activation_due",
            "world_id",
            "status",
            "due_at",
            "priority",
            "enqueue_position",
        ),
        Index("ix_simulation_activation_target", "world_id", "target_kind", "target_id"),
        Index(
            "uq_simulation_activation_pending_coalescing",
            "world_id",
            "target_kind",
            "target_id",
            "activation_kind",
            "activation_version",
            "coalescing_key",
            unique=True,
            sqlite_where=text("status = 'pending' AND coalescing_key IS NOT NULL"),
        ),
    )


class SimulationActivationCauseRecord(Base):
    __tablename__ = "simulation_activation_causes"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    activation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    cause_identity: Mapped[str] = mapped_column(String(160), primary_key=True)
    position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cause_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_trigger_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    source_event_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    source_scene_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    scene_activity: Mapped[str | None] = mapped_column(String(32))
    source_request_id: Mapped[UUID | None] = mapped_column(UUIDStorage())
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    attached_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "activation_id"],
            ["simulation_activations.world_id", "simulation_activations.activation_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "source_trigger_id"],
            ["simulation_scheduled_triggers.world_id", "simulation_scheduled_triggers.trigger_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "source_event_id"],
            ["world_events.world_id", "world_events.event_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "source_scene_id"], ["scenes.world_id", "scenes.scene_id"]
        ),
        UniqueConstraint(
            "world_id", "activation_id", "position", name="uq_simulation_activation_cause_position"
        ),
        CheckConstraint("position > 0", name="ck_simulation_activation_cause_position"),
        CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_simulation_activation_cause_fingerprint",
        ),
        CheckConstraint(
            "(cause_kind = 'scheduled_trigger' AND source_trigger_id IS NOT NULL "
            "AND source_event_id IS NULL AND source_scene_id IS NULL "
            "AND scene_activity IS NULL AND source_request_id IS NULL) OR "
            "(cause_kind = 'world_event' AND source_trigger_id IS NULL "
            "AND source_event_id IS NOT NULL AND source_scene_id IS NULL "
            "AND scene_activity IS NULL AND source_request_id IS NULL) OR "
            "(cause_kind = 'scene_activity' AND source_trigger_id IS NULL "
            "AND source_event_id IS NULL AND source_scene_id IS NOT NULL "
            "AND scene_activity IS NOT NULL AND source_request_id IS NOT NULL) OR "
            "(cause_kind = 'explicit_system' AND source_trigger_id IS NULL "
            "AND source_event_id IS NULL AND source_scene_id IS NULL "
            "AND scene_activity IS NULL AND source_request_id IS NOT NULL)",
            name="ck_simulation_activation_cause_shape",
        ),
        Index(
            "ix_simulation_activation_cause_order",
            "world_id",
            "activation_id",
            "position",
            "cause_identity",
        ),
        Index(
            "ix_simulation_activation_cause_identity",
            "world_id",
            "cause_identity",
        ),
    )


class SimulationScheduleReceiptRecord(Base):
    __tablename__ = "simulation_schedule_receipts"
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), primary_key=True
    )
    request_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "trigger_id"],
            ["simulation_scheduled_triggers.world_id", "simulation_scheduled_triggers.trigger_id"],
        ),
        Index("uq_simulation_schedule_request", "request_id", unique=True),
        CheckConstraint(
            "length(fingerprint) = 64", name="ck_simulation_schedule_receipt_fingerprint"
        ),
    )


for _record in (
    WorldRecord,
    WorldClockRecord,
    LocationRecord,
    LocationConnectionRecord,
    PlayerRecord,
    PlayerPresenceRecord,
    CharacterRecord,
    CharacterStateRecord,
    RelationshipRecord,
    KnowledgeAssertionRecord,
    CommandReceiptRecord,
    ScheduledSimulationTriggerRecord,
):
    _record.__table__.append_constraint(
        CheckConstraint("revision >= 0", name=f"ck_{_record.__tablename__}_revision")
    )

WorldClockRecord.__table__.append_constraint(
    CheckConstraint("typeof(logical_time) = 'integer'", name="ck_world_clock_logical_time_type")
)
WorldEventRecord.__table__.append_constraint(
    CheckConstraint("typeof(occurred_at) = 'integer'", name="ck_world_event_occurred_type")
)
KnowledgeAssertionRecord.__table__.append_constraint(
    CheckConstraint(
        "typeof(valid_from) = 'integer' AND (valid_to IS NULL OR typeof(valid_to) = 'integer')",
        name="ck_knowledge_world_time_type",
    )
)
ObservationRecord.__table__.append_constraint(
    CheckConstraint("typeof(observed_at) = 'integer'", name="ck_observation_world_time_type")
)


class WorldContentImportRecord(Base):
    __tablename__ = "world_content_imports"
    import_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    replaces_import_id: Mapped[UUID | None] = mapped_column(
        UUIDStorage(), ForeignKey("world_content_imports.import_id"), nullable=True
    )
    world_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("worlds.world_id"), nullable=False
    )
    reviewed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        CheckConstraint("kind IN ('character', 'lorebook')", name="ck_world_content_import_kind"),
        CheckConstraint("length(reviewed_hash) = 64", name="ck_world_content_import_hash"),
        Index("ix_world_content_import_world", "world_id"),
        Index("uq_world_content_replaces", "replaces_import_id", unique=True),
    )


class ChatConversationRecord(Base):
    """A local Player's durable communication space, independent of WorldEvents."""

    __tablename__ = "chat_conversations"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    player_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    direct_root_import_id: Mapped[UUID | None] = mapped_column(
        UUIDStorage(), ForeignKey("world_content_imports.import_id"), nullable=True
    )
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["world_id", "player_id"], ["players.world_id", "players.player_id"]),
        CheckConstraint(
            "(kind = 'direct' AND direct_root_import_id IS NOT NULL) OR "
            "(kind = 'group' AND direct_root_import_id IS NULL)",
            name="ck_chat_conversation_kind",
        ),
        Index("ix_chat_conversation_player", "world_id", "player_id", "created_at_utc"),
        Index(
            "uq_chat_direct_player_contact",
            "world_id",
            "player_id",
            "direct_root_import_id",
            unique=True,
            sqlite_where=text("kind = 'direct'"),
        ),
    )


class ChatParticipantRecord(Base):
    __tablename__ = "chat_participants"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    root_import_id: Mapped[UUID] = mapped_column(
        UUIDStorage(), ForeignKey("world_content_imports.import_id"), nullable=False
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        UniqueConstraint(
            "world_id", "conversation_id", "root_import_id", name="uq_chat_participant_contact"
        ),
    )


class ChatTurnRecord(Base):
    """The player-send receipt and a non-dispatched turn are one durable record."""

    __tablename__ = "chat_turns"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    turn_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    request_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    token_ceiling: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        Index("uq_chat_turn_request", "request_id", unique=True),
        CheckConstraint("length(fingerprint) = 64", name="ck_chat_turn_fingerprint"),
        CheckConstraint("token_ceiling > 0", name="ck_chat_turn_token_ceiling"),
        CheckConstraint("status = 'pending'", name="ck_chat_turn_status"),
    )


class ChatMessageRecord(Base):
    """Ordered transcript record; it does not confer knowledge or world truth."""

    __tablename__ = "chat_messages"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    message_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    turn_id: Mapped[UUID] = mapped_column(UUIDStorage(), nullable=False)
    position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_player_id: Mapped[UUID | None] = mapped_column(UUIDStorage(), nullable=True)
    sender_character_id: Mapped[UUID | None] = mapped_column(UUIDStorage(), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(UTCTimestampStorage(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "conversation_id"],
            ["chat_conversations.world_id", "chat_conversations.conversation_id"],
        ),
        ForeignKeyConstraint(
            ["world_id", "turn_id"], ["chat_turns.world_id", "chat_turns.turn_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "sender_player_id"], ["players.world_id", "players.player_id"]
        ),
        ForeignKeyConstraint(
            ["world_id", "sender_character_id"],
            ["characters.world_id", "characters.character_id"],
        ),
        UniqueConstraint(
            "world_id", "conversation_id", "position", name="uq_chat_message_position"
        ),
        Index(
            "uq_chat_turn_player_message",
            "world_id",
            "turn_id",
            unique=True,
            sqlite_where=sql_text("sender_player_id IS NOT NULL"),
        ),
        CheckConstraint("position > 0", name="ck_chat_message_position"),
        CheckConstraint("length(trim(text)) > 0", name="ck_chat_message_text"),
        CheckConstraint(
            "(sender_player_id IS NOT NULL AND sender_character_id IS NULL) OR "
            "(sender_player_id IS NULL AND sender_character_id IS NOT NULL)",
            name="ck_chat_message_sender",
        ),
    )
