"""Finite planning cohorts over an unbounded authored character population."""

import json
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    Text,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from livingworld.application.director import WINDOW_US, DirectorError
from livingworld.infrastructure.persistence.location_policy_models import CharacterMobilityRecord
from livingworld.infrastructure.persistence.models import Base, CharacterStateRecord, UUIDStorage


class DirectorRotationRecord(Base):
    __tablename__ = "director_rotation"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    batch_size: Mapped[int] = mapped_column(Integer(), nullable=False, default=8)
    settings_revision: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    cycle: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0)
    window_end: Mapped[int] = mapped_column(BigInteger(), nullable=False, default=0)
    accepted: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    cohort_json: Mapped[str] = mapped_column(Text(), nullable=False, default="[]")
    __table_args__ = (
        ForeignKeyConstraint(["world_id"], ["worlds.world_id"]),
        CheckConstraint("cycle >= 0 AND window_end >= 0", name="ck_director_rotation_bounds"),
        CheckConstraint(
            "batch_size BETWEEN 1 AND 16 AND settings_revision >= 0",
            name="ck_director_rotation_settings",
        ),
        CheckConstraint(
            "json_valid(cohort_json) AND length(cohort_json) <= 1024",
            name="ck_director_rotation_cohort",
        ),
    )


class DirectorRotationMemberRecord(Base):
    __tablename__ = "director_rotation_members"
    world_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    character_id: Mapped[UUID] = mapped_column(UUIDStorage(), primary_key=True)
    last_cycle: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["world_id", "character_id"], ["characters.world_id", "characters.character_id"]
        ),
        CheckConstraint("last_cycle >= 0", name="ck_director_rotation_member_cycle"),
    )


async def select_cohort(session, world, now, size, removed):
    rotation = await session.get(DirectorRotationRecord, world)
    if rotation is None:
        rotation = DirectorRotationRecord(
            world_id=world,
            batch_size=size,
            settings_revision=0,
            cycle=0,
            window_end=0,
            accepted=True,
            cohort_json="[]",
        )
        session.add(rotation)
    eligible = select(CharacterStateRecord.character_id).where(
        CharacterStateRecord.world_id == world,
        CharacterStateRecord.character_id.not_in(removed),
    )
    if rotation.cohort_json != "[]" and (not rotation.accepted or now < rotation.window_end):
        previous = [UUID(value) for value in json.loads(rotation.cohort_json)]
        if not rotation.accepted:
            # An explicit retry may lower its size without drawing new people.
            # Unaccepted members have not consumed their turn in the cycle.
            previous = previous[:size]
            rotation.cohort_json = json.dumps([str(value) for value in previous])
        chosen = list(
            await session.scalars(eligible.where(CharacterStateRecord.character_id.in_(previous)))
        )
        if not chosen:
            raise DirectorError("director_characters_required")
        # Switching settings, restarting, retries and early replans cannot reroll.
        rotation.window_end = now + WINDOW_US
        rotation.accepted = False
        return chosen
    member = DirectorRotationMemberRecord
    waiting = eligible.outerjoin(
        member,
        (member.world_id == world) & (member.character_id == CharacterStateRecord.character_id),
    ).where(or_(member.last_cycle.is_(None), member.last_cycle < rotation.cycle))
    if await session.scalar(waiting.limit(1)) is None:
        rotation.cycle += 1
        waiting = eligible.outerjoin(
            member,
            (member.world_id == world) & (member.character_id == CharacterStateRecord.character_id),
        ).where(or_(member.last_cycle.is_(None), member.last_cycle < rotation.cycle))
    # An interrupted foreign trip gets a bounded return opportunity. Always leave
    # at least one ordinary slot so repeated returns cannot starve the population.
    priority = (
        list(
            await session.scalars(
                eligible.join(
                    CharacterMobilityRecord,
                    (CharacterMobilityRecord.world_id == world)
                    & (CharacterMobilityRecord.character_id == CharacterStateRecord.character_id),
                )
                .where(CharacterMobilityRecord.far_since.is_not(None))
                .order_by(CharacterMobilityRecord.far_since, CharacterStateRecord.character_id)
                .limit(min(2, size - 1))
            )
        )
        if size > 1
        else []
    )
    ordinary = list(
        await session.scalars(
            waiting.where(CharacterStateRecord.character_id.not_in(priority))
            .order_by(func.random())
            .limit(size - len(priority))
        )
    )
    chosen = priority + ordinary
    if not chosen:
        raise DirectorError("director_characters_required")
    rotation.cohort_json = json.dumps([str(value) for value in chosen])
    rotation.window_end, rotation.accepted = now + WINDOW_US, False
    return chosen


async def accept_cohort(session, world, identities):
    rotation = await session.get(DirectorRotationRecord, world)
    if rotation is None:
        return  # Previously accepted plans retain their contract.
    for identity in identities:
        record = await session.get(DirectorRotationMemberRecord, (world, identity))
        if record is None:
            session.add(
                DirectorRotationMemberRecord(
                    world_id=world, character_id=identity, last_cycle=rotation.cycle
                )
            )
        else:
            record.last_cycle = rotation.cycle
    rotation.accepted = True
