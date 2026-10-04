"""Consented shared proposals in the existing Director store; no second scheduler."""

from datetime import UTC, datetime

from sqlalchemy import func, select, update

from livingworld.application.director import DirectorError
from livingworld.application.errors import EntityNotFoundError
from livingworld.infrastructure.persistence.director_models import (
    DirectorSettingsRecord as Settings,
)
from livingworld.infrastructure.persistence.encounter_models import (
    EncounterSettingsRecord as Encounters,
)
from livingworld.infrastructure.persistence.models import WorldRecord
from livingworld.infrastructure.persistence.shared_activity_models import (
    SharedActivityRecord as Shared,
)
from livingworld.infrastructure.persistence.shared_activity_models import (
    SharedActivitySettingsRecord as Consent,
)


class SharedDirectorMixin:
    async def configure_shared_activities(self, world, player, enabled, consent, revision):
        from livingworld.infrastructure.persistence.director import _binding, _write

        async with self.sessions() as session:
            await _write(session)
            if await session.get(WorldRecord, world.value) is None:
                raise EntityNotFoundError("world_not_found")
            bound = await _binding(session, world)
            if player is None or player.value != bound:
                raise DirectorError("director_player_required")
            director = await session.get(Settings, world.value)
            encounters = await session.get(Encounters, world.value)
            if enabled and not (
                director
                and director.enabled
                and encounters
                and encounters.enabled
                and director.player_id == bound == encounters.player_id
            ):
                raise DirectorError("director_shared_requires_encounters")
            setting = await session.get(Consent, world.value)
            if (setting.revision if setting else 0) != revision:
                raise DirectorError("director_settings_changed")
            if enabled and (not setting or setting.player_id != bound) and not consent:
                raise DirectorError("director_shared_consent_required")
            if (
                not setting
                and not enabled
                or setting
                and setting.enabled == enabled
                and setting.player_id == bound
            ):
                return
            if not setting:
                setting = Consent(
                    world_id=world.value,
                    player_id=bound,
                    enabled=False,
                    revision=0,
                    consented_at=datetime.now(UTC),
                )
                session.add(setting)
            if enabled and setting.player_id != bound:
                setting.consented_at = datetime.now(UTC)
            if enabled:
                setting.player_id = bound
            setting.enabled, setting.revision = enabled, setting.revision + 1
            await session.execute(
                update(Shared)
                .where(Shared.world_id == world.value, Shared.state == "pending")
                .values(state="cancelled")
            )
            await session.commit()

    async def advance_shared_activities(self, world, now):
        from livingworld.infrastructure.persistence.director import _binding, _write

        async with self.sessions() as session:
            await _write(session)
            config = await session.get(Settings, world.value)
            consent = await session.get(Consent, world.value)
            encounters = await session.get(Encounters, world.value)
            if not (
                config
                and config.enabled
                and config.state == "ready"
                and consent
                and consent.enabled
                and encounters
                and encounters.enabled
                and consent.player_id
                == config.player_id
                == encounters.player_id
                == await _binding(session, world)
            ):
                return (), None
            await session.execute(
                update(Shared)
                .where(
                    Shared.world_id == world.value,
                    Shared.state == "pending",
                    Shared.start_deadline <= now,
                )
                .values(state="expired", reason="window_elapsed")
            )
            scope = (
                Shared.world_id == world.value,
                Shared.plan_id == config.plan_id,
                Shared.consent_revision == consent.revision,
                Shared.state == "pending",
            )
            due = tuple(
                (
                    await session.scalars(
                        select(Shared.candidate_id)
                        .where(*scope, Shared.due_at <= now, Shared.start_deadline > now)
                        .order_by(Shared.due_at, Shared.candidate_id)
                        .limit(2)
                    )
                ).all()
            )
            deadline = await session.scalar(
                select(func.min(Shared.due_at)).where(*scope, Shared.due_at > now)
            )
            await session.commit()
            return due, deadline
