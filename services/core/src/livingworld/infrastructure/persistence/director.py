"""Durable consent, one-way planning claims and Kernel-bound routine candidates."""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy import LargeBinary, case, cast, func, select, true, update

from livingworld.application.director import MAX_CHARACTERS, MAX_LOCATIONS, WINDOW_US, DirectorError
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.lore_activation import select_common_background
from livingworld.domain.actions import ActionRejectionReason
from livingworld.infrastructure.persistence.director_background import (
    background_is_current,
    read_director_background,
)
from livingworld.infrastructure.persistence.director_models import (
    DirectorCandidateRecord as Candidate,
)
from livingworld.infrastructure.persistence.director_models import DirectorPlanRecord as Plan
from livingworld.infrastructure.persistence.director_models import (
    DirectorSettingsRecord as Settings,
)
from livingworld.infrastructure.persistence.encounter_models import (
    EncounterCandidateRecord as Encounter,
)
from livingworld.infrastructure.persistence.encounter_models import (
    EncounterSettingsRecord as EncounterSettings,
)
from livingworld.infrastructure.persistence.encounter_policy import pacing_rejection
from livingworld.infrastructure.persistence.factions import known_pairs
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    CharacterStateRecord,
    ChatParticipantRecord,
    LocalPlayerBindingRecord,
    LocationRecord,
    WorldClockRecord,
    WorldContentImportRecord,
    WorldRecord,
)
from livingworld.infrastructure.persistence.shared_activity_authority import SharedKernelMixin
from livingworld.infrastructure.persistence.shared_activity_models import (
    SharedActivityRecord as Shared,
)
from livingworld.infrastructure.persistence.shared_activity_models import (
    SharedActivitySettingsRecord as SharedSettings,
)
from livingworld.infrastructure.persistence.shared_activity_store import SharedDirectorMixin


async def _write(session):
    await session.begin()
    await session.connection(execution_options={"livingworld_write_intent": True})


async def _binding(session, world):
    binding = await session.get(LocalPlayerBindingRecord, world.value)
    return binding.player_id if binding else None


async def _pending_cancel(session, world, state="cancelled"):
    await session.execute(
        update(Shared)
        .where(Shared.world_id == world.value, Shared.state == "pending")
        .values(state=state)
    )
    await session.execute(
        update(Encounter)
        .where(Encounter.world_id == world.value, Encounter.state == "pending")
        .values(state=state)
    )
    await session.execute(
        update(Candidate)
        .where(Candidate.world_id == world.value, Candidate.state == "pending")
        .values(state=state)
    )


class SqlAlchemyDirectorStore(SharedDirectorMixin):
    def __init__(self, sessions, clocks):
        self.sessions, self._clocks = sessions, clocks

    async def clocks(self):
        return await self._clocks.list()

    async def snapshot(self, world, player):
        async with self.sessions() as session:
            if await session.get(WorldRecord, world.value) is None:
                raise EntityNotFoundError("world_not_found")
            config = await session.get(Settings, world.value)
            bound = await _binding(session, world)
            if player is None or bound != player.value:
                raise DirectorError("director_player_required")
            owned = config is not None and config.player_id == bound
            encounters = await session.get(EncounterSettings, world.value)
            encounter_owned = encounters is not None and encounters.player_id == bound
            shared = await session.get(SharedSettings, world.value)
            shared_owned = shared is not None and shared.player_id == bound
            return {
                "enabled": bool(owned and config.enabled),
                "revision": config.revision if config else 0,
                "state": config.state if owned else "off",
                "error": config.error if owned else None,
                "consented": bool(owned),
                "encounters_enabled": bool(encounter_owned and encounters.enabled),
                "encounter_revision": encounters.revision if encounters else 0,
                "encounters_consented": bool(encounter_owned),
                "shared_activities_enabled": bool(shared_owned and shared.enabled),
                "shared_activity_revision": shared.revision if shared else 0,
                "shared_activities_consented": bool(shared_owned),
            }

    async def configure(self, world, player, enabled, consent, revision, retry):
        async with self.sessions() as session:
            await _write(session)
            if await session.get(WorldRecord, world.value) is None:
                raise EntityNotFoundError("world_not_found")
            bound = await _binding(session, world)
            if player is None or player.value != bound:
                raise DirectorError("director_player_required")
            config = await session.get(Settings, world.value)
            if (config.revision if config else 0) != revision:
                raise DirectorError("director_settings_changed")
            if enabled and (config is None or config.player_id != bound) and not consent:
                raise DirectorError("director_consent_required")
            if retry and (not config or config.state != "attention" or not config.enabled):
                raise DirectorError("director_retry_unavailable")
            if (
                config is not None
                and config.enabled == enabled
                and config.player_id == bound
                and not retry
            ):
                return
            if config is None and not enabled:
                return
            if config is None:
                config = Settings(
                    world_id=world.value,
                    player_id=bound,
                    revision=0,
                    consented_at=datetime.now(UTC),
                    enabled=False,
                    state="off",
                )
                session.add(config)
            elif enabled and config.player_id != bound:
                config.consented_at = datetime.now(UTC)
            await _pending_cancel(session, world)
            if enabled:
                config.player_id = bound
            config.enabled = enabled
            config.revision += 1
            config.state = "idle" if enabled else "off"
            config.plan_id, config.error = None, None
            await session.commit()

    async def interrupt_abandoned(self):
        async with self.sessions() as session:
            await _write(session)
            await session.execute(
                update(Plan)
                .where(Plan.state == "planning")
                .values(state="interrupted", error="director_interrupted")
            )
            await session.execute(
                update(Settings)
                .where(Settings.state == "planning")
                .values(state="attention", error="director_interrupted")
            )
            await session.execute(
                update(Shared).where(Shared.state == "active").values(continuity_lost=True)
            )
            await session.commit()

    async def runtime_failed(self, world):
        async with self.sessions() as session:
            await _write(session)
            config = await session.get(Settings, world.value)
            if config and config.enabled:
                config.state, config.error = "attention", "director_execution_failed"
            await session.commit()

    async def advance(self, world, now):
        async with self.sessions() as session:
            await _write(session)
            config = await session.get(Settings, world.value)
            if config is None or not config.enabled:
                return "off", (), None
            if config.player_id != await _binding(session, world):
                config.enabled, config.state = False, "off"
                config.revision += 1
                await _pending_cancel(session, world)
                await session.commit()
                return "off", (), None
            await session.execute(
                update(Candidate)
                .where(
                    Candidate.world_id == world.value,
                    Candidate.state == "pending",
                    Candidate.end_at <= now,
                )
                .values(state="expired")
            )
            if config.state in ("attention", "planning"):
                await session.commit()
                return config.state, (), None
            if config.state == "idle":
                await session.commit()
                return "plan", (), None
            plan = await session.get(Plan, (world.value, config.plan_id))
            if plan is None or plan.state != "ready":
                config.state, config.error = "attention", "director_plan_invalid"
                await session.commit()
                return "attention", (), None
            invalid = await session.scalar(
                select(func.count())
                .select_from(Candidate)
                .where(
                    Candidate.world_id == world.value,
                    Candidate.plan_id == plan.plan_id,
                    Candidate.state == "invalid",
                )
            )
            replan = now >= plan.window_end or invalid >= 2 and invalid * 2 >= plan.candidate_count
            if replan:
                await session.commit()
                return "plan", (), None
            rows = (
                await session.scalars(
                    select(Candidate)
                    .where(
                        Candidate.world_id == world.value,
                        Candidate.plan_id == plan.plan_id,
                        Candidate.state == "pending",
                        Candidate.due_at <= now,
                        Candidate.end_at > now,
                    )
                    .order_by(Candidate.due_at, Candidate.candidate_id)
                    .limit(64)
                )
            ).all()
            due = tuple(
                {
                    key: getattr(row, key)
                    for key in (
                        "candidate_id",
                        "character_id",
                        "location_id",
                        "activity",
                        "expected_revision",
                    )
                }
                for row in rows
            )
            next_due = await session.scalar(
                select(func.min(Candidate.due_at)).where(
                    Candidate.world_id == world.value,
                    Candidate.plan_id == plan.plan_id,
                    Candidate.state == "pending",
                    Candidate.due_at > now,
                )
            )
            active_end = await session.scalar(
                select(func.min(Candidate.end_at)).where(
                    Candidate.world_id == world.value, Candidate.state == "active"
                )
            )
            next_time = min(
                value for value in (plan.window_end, next_due, active_end) if value is not None
            )
            await session.commit()
            return "ready", due, next_time

    async def claim(self, world, now, request_id):
        async with self.sessions() as session:
            await _write(session)
            config = await session.get(Settings, world.value)
            if (
                not config
                or not config.enabled
                or config.player_id != await _binding(session, world)
                or config.state in ("planning", "attention")
            ):
                return None
            clock = await session.get(WorldClockRecord, world.value)
            if clock is None or clock.state == "paused":
                return None
            try:
                snapshot = await self.planning_input(session, world, now)
            except DirectorError as error:
                config.state, config.error = "attention", str(error)
                await session.commit()
                return None
            config.state, config.error = "planning", None
            generation = config.revision
            config.plan_id = request_id
            # Old pending candidates remain inert while planning; accepting the new
            # batch and cancelling them share one transaction.
            session.add(
                Plan(
                    world_id=world.value,
                    plan_id=request_id,
                    generation=generation,
                    window_start=now,
                    window_end=now + WINDOW_US,
                    candidate_count=0,
                    input_json=json.dumps(snapshot, ensure_ascii=False),
                    state="planning",
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()
            return request_id, generation, snapshot

    async def planning_input(self, session, world, now):
        rows = (
            await session.execute(
                select(CharacterStateRecord, CharacterRecord.name)
                .join(
                    CharacterRecord,
                    (CharacterRecord.world_id == CharacterStateRecord.world_id)
                    & (CharacterRecord.character_id == CharacterStateRecord.character_id),
                )
                .where(CharacterStateRecord.world_id == world.value)
                .order_by(CharacterStateRecord.character_id)
                .limit(MAX_CHARACTERS + 1)
            )
        ).all()
        locations = (
            await session.scalars(
                select(LocationRecord)
                .where(LocationRecord.world_id == world.value)
                .order_by(LocationRecord.location_id)
                .limit(MAX_LOCATIONS + 1)
            )
        ).all()
        if not rows:
            raise DirectorError("director_characters_required")
        if len(rows) > MAX_CHARACTERS or len(locations) > MAX_LOCATIONS:
            raise DirectorError("director_world_capacity")
        characters = []
        for state, name in rows:
            active_end = await session.scalar(
                select(func.max(Candidate.end_at)).where(
                    Candidate.world_id == world.value,
                    Candidate.character_id == state.character_id,
                    Candidate.state == "active",
                )
            )
            character = {
                "character_id": str(state.character_id),
                "name": name,
                "location_id": str(state.location_id),
                "revision": state.revision,
                "available_from": max(now, active_end or now),
                "available_from_minute": max(
                    0, ((active_end or now) - now + 59_999_999) // 60_000_000
                ),
            }
            character.update(await self.approved_persona(session, world, state.character_id))
            characters.append(character)
        snapshot = {
            "window_start": now,
            "window_end": now + WINDOW_US,
            "characters": characters,
            "locations": [
                {"location_id": str(loc.location_id), "name": loc.name} for loc in locations
            ],
        }
        location_names = {str(loc.location_id): loc.name for loc in locations}
        # One synthetic planning context, not private chat or an omniscient history.
        # Include every character's name and own current place, not all destinations.
        planning_text = "\n".join(
            character["name"] + " " + location_names.get(character["location_id"], "")
            for character in characters
        )
        encounter_settings = await session.get(EncounterSettings, world.value)
        snapshot["encounters_enabled"] = bool(
            encounter_settings
            and encounter_settings.enabled
            and encounter_settings.player_id == await _binding(session, world)
        )
        snapshot["encounter_revision"] = encounter_settings.revision if encounter_settings else 0
        shared = await session.get(SharedSettings, world.value)
        snapshot["shared_activities_enabled"] = bool(
            shared
            and shared.enabled
            and snapshot["encounters_enabled"]
            and shared.player_id == await _binding(session, world)
        )
        snapshot["shared_activity_revision"] = shared.revision if shared else 0
        snapshot["known_faction_pairs"] = (
            await known_pairs(
                session,
                world.value,
                {UUID(character["character_id"]) for character in characters},
            )
            if snapshot["shared_activities_enabled"]
            else []
        )
        snapshot["common_world_background"] = select_common_background(
            await read_director_background(session, world),
            (planning_text,),
            generation_kind="quiet",
            include_references=True,
        )
        if len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) > 64 * 1024:
            raise DirectorError("director_world_capacity")
        return snapshot

    async def approved_persona(self, session, world, character_id):
        """Reuse the approved field projection for both placed routines and remote contacts."""
        roots = (
            await session.scalars(
                select(ChatParticipantRecord.root_import_id)
                .where(
                    ChatParticipantRecord.world_id == world.value,
                    ChatParticipantRecord.character_id == character_id,
                )
                .distinct()
                .limit(2)
            )
        ).all()
        if len(roots) > 1:
            raise DirectorError("director_character_mapping_invalid")
        if roots:
            imported = WorldContentImportRecord
            current = roots[0]
            for _ in range(128):
                kind = await session.scalar(
                    select(imported.kind).where(
                        imported.world_id == world.value, imported.import_id == current
                    )
                )
                if kind != "character":
                    raise DirectorError("director_character_mapping_invalid")
                replacement = await session.scalar(
                    select(imported.import_id).where(
                        imported.world_id == world.value, imported.replaces_import_id == current
                    )
                )
                if replacement is None:
                    break
                current = replacement
            else:
                raise DirectorError("director_world_capacity")
            # The accepted snapshot is an array of serialized canonical envelopes.
            # SQL extracts only the character's approved basic persona fields;
            # embedded lore, notes, extensions and instructions are never loaded.
            safe_snapshot = case(
                (func.json_valid(imported.snapshot_json), imported.snapshot_json), else_="[]"
            )
            parts = func.json_each(safe_snapshot).table_valued("key", "value")
            safe_part = case((func.json_valid(parts.c.value), parts.c.value), else_="{}")
            fields = ("description", "personality", "background")
            values = [func.json_extract(safe_part, f"$.data.{field}") for field in fields]
            projection = [
                case((func.length(cast(value, LargeBinary)) <= 65536, value), else_=None)
                for value in values
            ]
            cards = (
                await session.execute(
                    select(*projection)
                    .select_from(imported)
                    .join(parts, true())
                    .where(
                        imported.world_id == world.value,
                        imported.import_id == current,
                        func.json_extract(safe_part, "$.kind") == "character_definition",
                    )
                    .limit(2)
                )
            ).all()
            if len(cards) != 1:
                raise DirectorError("director_character_mapping_invalid")
            if any(not isinstance(value, str) for value in cards[0]):
                raise DirectorError("director_world_capacity")
            return {
                "persona": dict(zip(fields, cards[0], strict=True)),
                "accepted_import_id": str(current),
            }
        return {}

    async def can_dispatch(self, world, request_id, generation):
        async with self.sessions() as session:
            config = await session.get(Settings, world.value)
            if not (
                config
                and config.enabled
                and config.state == "planning"
                and config.revision == generation
                and config.plan_id == request_id
                and config.player_id == await _binding(session, world)
            ):
                return False
            plan = await session.get(Plan, (world.value, request_id))
            if not plan or plan.state != "planning":
                return False
            if not await background_is_current(session, world, plan.input_json):
                raise DirectorError("director_background_changed")
            return True

    async def finish(self, world, request_id, generation, candidates, encounters=(), shared=()):
        async with self.sessions() as session:
            await _write(session)
            config = await session.get(Settings, world.value)
            plan = await session.get(Plan, (world.value, request_id))
            if not plan or plan.state != "planning":
                return
            if (
                not config
                or not config.enabled
                or config.revision != generation
                or config.plan_id != request_id
                or config.player_id != await _binding(session, world)
            ):
                plan.state = "superseded"
                await session.commit()
                return
            if not await background_is_current(session, world, plan.input_json):
                plan.state, plan.error = "failed", "director_background_changed"
                config.state, config.error = "attention", plan.error
                await session.commit()
                return
            await _pending_cancel(session, world)
            for index, value in enumerate(candidates):
                session.add(
                    Candidate(
                        world_id=world.value,
                        candidate_id=uuid5(request_id, f"routine:{index}"),
                        plan_id=request_id,
                        state="pending",
                        **value,
                    )
                )
            await session.flush()
            consent = await session.get(EncounterSettings, world.value)
            planned_input = json.loads(plan.input_json)
            if (
                consent
                and consent.enabled
                and consent.player_id == config.player_id
                and consent.revision == planned_input.get("encounter_revision")
                and planned_input.get("encounters_enabled")
            ):
                for index, value in enumerate(encounters):
                    values = dict(value)
                    first = values.pop("first_routine_index")
                    second = values.pop("second_routine_index")
                    session.add(
                        Encounter(
                            world_id=world.value,
                            candidate_id=uuid5(request_id, f"encounter:{index}"),
                            plan_id=request_id,
                            consent_revision=consent.revision,
                            state="pending",
                            first_routine_id=uuid5(request_id, f"routine:{first}"),
                            second_routine_id=uuid5(request_id, f"routine:{second}"),
                            **values,
                        )
                    )
            joint_consent = await session.get(SharedSettings, world.value)
            if (
                joint_consent
                and joint_consent.enabled
                and joint_consent.player_id == config.player_id
                and joint_consent.revision == planned_input.get("shared_activity_revision")
                and planned_input.get("shared_activities_enabled")
                and consent
                and consent.enabled
                and consent.player_id == config.player_id
                and consent.revision == planned_input.get("encounter_revision")
            ):
                for index, value in enumerate(shared):
                    values = dict(value)
                    first, second = (
                        values.pop("first_routine_index"),
                        values.pop("second_routine_index"),
                    )
                    session.add(
                        Shared(
                            world_id=world.value,
                            candidate_id=uuid5(request_id, f"shared:{index}"),
                            plan_id=request_id,
                            consent_revision=joint_consent.revision,
                            encounter_revision=consent.revision,
                            state="pending",
                            continuity_lost=False,
                            first_routine_id=uuid5(request_id, f"routine:{first}"),
                            second_routine_id=uuid5(request_id, f"routine:{second}"),
                            **values,
                        )
                    )
            plan.candidate_count, plan.state = len(candidates), "ready"
            config.state, config.error = "ready", None
            await session.commit()

    async def fail(self, world, request_id, generation, code):
        async with self.sessions() as session:
            await _write(session)
            plan = await session.get(Plan, (world.value, request_id))
            if plan and plan.state == "planning":
                plan.state = "interrupted" if code == "director_interrupted" else "failed"
                plan.error = code
            config = await session.get(Settings, world.value)
            if (
                config
                and config.enabled
                and config.revision == generation
                and config.plan_id == request_id
            ):
                config.state, config.error = "attention", code
            await session.commit()

    async def configure_encounters(self, world, player, enabled, consent, revision):
        async with self.sessions() as session:
            await _write(session)
            if await session.get(WorldRecord, world.value) is None:
                raise EntityNotFoundError("world_not_found")
            bound = await _binding(session, world)
            if player is None or player.value != bound:
                raise DirectorError("director_player_required")
            director = await session.get(Settings, world.value)
            if enabled and (not director or not director.enabled or director.player_id != bound):
                raise DirectorError("director_encounters_require_activity")
            setting = await session.get(EncounterSettings, world.value)
            if (setting.revision if setting else 0) != revision:
                raise DirectorError("director_settings_changed")
            if enabled and (not setting or setting.player_id != bound) and not consent:
                raise DirectorError("director_encounter_consent_required")
            if not setting and not enabled:
                return
            if setting and setting.enabled == enabled and setting.player_id == bound:
                return
            if not setting:
                setting = EncounterSettings(
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
            setting.enabled = enabled
            setting.revision += 1
            await session.execute(
                update(Encounter)
                .where(Encounter.world_id == world.value, Encounter.state == "pending")
                .values(state="cancelled")
            )
            await session.execute(
                update(Shared)
                .where(Shared.world_id == world.value, Shared.state == "pending")
                .values(state="cancelled")
            )
            # Separate consent revision never invalidates admitted daily activities.
            await session.commit()

    async def advance_encounters(self, world, now):
        async with self.sessions() as session:
            await _write(session)
            config = await session.get(Settings, world.value)
            consent = await session.get(EncounterSettings, world.value)
            if not (
                config
                and config.enabled
                and config.state == "ready"
                and consent
                and consent.enabled
                and consent.player_id == config.player_id
                and config.player_id == await _binding(session, world)
            ):
                return (), None
            await session.execute(
                update(Encounter)
                .where(
                    Encounter.world_id == world.value,
                    Encounter.state == "pending",
                    Encounter.end_at <= now,
                )
                .values(state="expired")
            )
            scope = (
                Encounter.world_id == world.value,
                Encounter.plan_id == config.plan_id,
                Encounter.consent_revision == consent.revision,
                Encounter.state == "pending",
            )
            due = tuple(
                (
                    await session.scalars(
                        select(Encounter.candidate_id)
                        .where(*scope, Encounter.due_at <= now, Encounter.end_at > now)
                        .order_by(Encounter.due_at, Encounter.candidate_id)
                        .limit(8)
                    )
                ).all()
            )
            deadline = await session.scalar(
                select(func.min(Encounter.due_at)).where(*scope, Encounter.due_at > now)
            )
            await session.commit()
            return due, deadline


class DirectorKernelRepository(SharedKernelMixin):
    """Only used inside the Kernel's physical writer transaction."""

    def __init__(self, session):
        self.session = session

    async def candidate(self, proposal, occurred_at):
        world, payload = proposal.world_id, proposal.payload
        row = await self.session.get(Candidate, (world.value, payload.candidate_id))
        config = await self.session.get(Settings, world.value)
        if (
            not row
            or not config
            or not config.enabled
            or config.state != "ready"
            or config.plan_id != row.plan_id
            or config.player_id != await _binding(self.session, world)
            or row.character_id != proposal.actor_id.value
            or row.location_id != payload.destination_id.value
            or row.activity != payload.activity.value
            or row.expected_revision != payload.expected_presence_revision.value
        ):
            return None
        plan = await self.session.get(Plan, (world.value, row.plan_id))
        if (
            not plan
            or plan.state != "ready"
            or plan.generation != config.revision
            or row.state != "pending"
            or not row.due_at <= occurred_at.microseconds < row.end_at
            or occurred_at.microseconds >= plan.window_end
        ):
            return None
        return row

    async def occupied(self, character, now):
        return (
            await self.session.scalar(
                select(Candidate.candidate_id)
                .where(
                    Candidate.world_id == character.world_id.value,
                    Candidate.character_id == character.value,
                    Candidate.state == "active",
                    Candidate.end_at > now.microseconds,
                )
                .limit(1)
            )
            is not None
        )

    def invalidate(self, row, reason=ActionRejectionReason.PRECONDITION_FAILED):
        row.state, row.reason = "invalid", reason.value

    def start(self, row):
        row.state = "active"

    async def active(self, world, character=None):
        query = select(Candidate).where(
            Candidate.world_id == world.value, Candidate.state == "active"
        )
        if character is not None:
            query = query.where(Candidate.character_id == character.value)
        return tuple(
            (
                await self.session.scalars(
                    query.order_by(Candidate.end_at, Candidate.candidate_id).limit(64)
                )
            ).all()
        )

    def finish(self, row, interrupted):
        row.state = "cancelled" if interrupted else "finished"
        row.reason = "presence_changed" if interrupted else "interval_elapsed"

    async def encounter_candidate(self, world, candidate_id, now):
        row = await self.session.get(Encounter, (world.value, candidate_id))
        if not row or row.state != "pending":
            return None, None
        config = await self.session.get(Settings, world.value)
        consent = await self.session.get(EncounterSettings, world.value)
        plan = await self.session.get(Plan, (world.value, row.plan_id))
        if not (
            config
            and config.enabled
            and config.state == "ready"
            and consent
            and consent.enabled
            and consent.revision == row.consent_revision
            and consent.player_id == config.player_id
            and config.player_id == await _binding(self.session, world)
            and config.plan_id == row.plan_id
            and plan
            and plan.state == "ready"
            and plan.generation == config.revision
        ):
            row.state, row.reason = "cancelled", "consent_or_plan_changed"
            return row, None
        if not row.due_at <= now.microseconds < min(row.end_at, plan.window_end):
            row.state, row.reason = "expired", "window_elapsed"
            return row, None
        routines = [
            await self.session.get(Candidate, (world.value, identity))
            for identity in (row.first_routine_id, row.second_routine_id)
        ]
        if any(
            routine is None
            or routine.state != "active"
            or routine.activity not in {"rest", "leisure"}
            or routine.location_id != row.location_id
            or routine.plan_id != row.plan_id
            or routine.character_id != owner
            or not routine.due_at <= now.microseconds < routine.end_at
            for routine, owner in zip(
                routines, (row.first_character_id, row.second_character_id), strict=True
            )
        ):
            row.state, row.reason = "invalid", "activity_changed"
            return row, None
        rejected = await pacing_rejection(self.session, row, now.microseconds)
        if rejected is not None:
            row.state, row.reason = "invalid", rejected
            return row, None
        return row, tuple(routines)
