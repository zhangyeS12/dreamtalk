"""Choose grounded contacts without a planner call; claim and deliver under one writer."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select, update

from livingworld.application.errors import EntityNotFoundError
from livingworld.application.lore_activation import select_common_background
from livingworld.application.proactive_contact import ProactiveContactError
from livingworld.domain.identifiers import PlayerId, WorldId
from livingworld.infrastructure.persistence.contact_gate import (
    contact_blocked,
    waiting_conversation,
)
from livingworld.infrastructure.persistence.director_background import read_director_background
from livingworld.infrastructure.persistence.director_models import (
    DirectorCandidateRecord as Routine,
)
from livingworld.infrastructure.persistence.director_models import DirectorPlanRecord as Plan
from livingworld.infrastructure.persistence.director_models import (
    DirectorSettingsRecord as Director,
)
from livingworld.infrastructure.persistence.encounter_models import (
    EncounterSettingsRecord as EncounterSettings,
)
from livingworld.infrastructure.persistence.mapping import to_domain
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    CharacterStateRecord,
    LocationRecord,
)
from livingworld.infrastructure.persistence.models import ChatConversationRecord as Conversation
from livingworld.infrastructure.persistence.models import ChatMessageRecord as Message
from livingworld.infrastructure.persistence.models import ChatParticipantRecord as Participant
from livingworld.infrastructure.persistence.models import ChatTurnDispatchRecord as Dispatch
from livingworld.infrastructure.persistence.models import ChatTurnRecord as Turn
from livingworld.infrastructure.persistence.models import LocalPlayerBindingRecord as Binding
from livingworld.infrastructure.persistence.models import PlayerPresenceRecord as Presence
from livingworld.infrastructure.persistence.models import WorldClockRecord as Clock
from livingworld.infrastructure.persistence.offline_contact import _write
from livingworld.infrastructure.persistence.proactive_models import (
    ProactiveEpisodeRecord as Episode,
)
from livingworld.infrastructure.persistence.proactive_models import (
    ProactiveSettingsRecord as Settings,
)
from livingworld.infrastructure.persistence.shared_activity_models import (
    SharedActivityRecord as Shared,
)
from livingworld.infrastructure.persistence.shared_activity_models import (
    SharedActivitySettingsRecord as SharedSettings,
)
from livingworld.infrastructure.persistence.world_story import record_contact_invitation

MINUTE = 60_000_000


def _json(data):
    value = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if len(value.encode("utf-8")) > 65536:
        raise ProactiveContactError("proactive_input_capacity")
    return value


class SqlAlchemyProactiveContactStore:
    def __init__(self, sessions, director, offline):
        self.sessions, self.director, self.offline = sessions, director, offline

    async def _owner(self, session, world, player):
        binding = await session.get(Binding, world.value)
        clock = await session.get(Clock, world.value)
        if not binding or player is None or binding.player_id != player.value or not clock:
            raise EntityNotFoundError("player_not_found")
        return clock

    async def snapshot(self, world, player):
        async with self.sessions() as session:
            await self._owner(session, world, player)
            cfg = await session.get(Settings, (world.value, player.value))
            waiting = await waiting_conversation(session, world.value, player.value)
            state = cfg.state if cfg else "off"
            if cfg and cfg.enabled and state != "attention" and waiting:
                state = "waiting_reply"
            return {
                "player_id": str(player.value),
                "enabled": bool(cfg and cfg.enabled),
                "consented": bool(cfg),
                "revision": cfg.revision if cfg else 0,
                "interval_minutes": cfg.interval_minutes if cfg else 360,
                "state": state,
                "error": cfg.error if cfg else None,
                "waiting_conversation_id": str(waiting) if waiting else None,
            }

    async def configure(self, world, player, enabled, minutes, consent, revision):
        async with self.sessions() as session:
            await _write(session)
            clock = await self._owner(session, world, player)
            cfg = await session.get(Settings, (world.value, player.value))
            if (cfg.revision if cfg else 0) != revision:
                raise ProactiveContactError("proactive_settings_changed")
            if enabled and cfg is None and not consent:
                raise ProactiveContactError("proactive_consent_required")
            if cfg is None and not enabled:
                return
            if cfg and cfg.enabled == enabled and cfg.interval_minutes == minutes:
                return
            now = datetime.now(UTC)
            logical = to_domain(clock).effective_time(now).microseconds
            if cfg is None:
                cfg = Settings(
                    world_id=world.value,
                    player_id=player.value,
                    enabled=False,
                    revision=0,
                    interval_minutes=minutes,
                    next_at=logical,
                    state="off",
                    consented_at=now,
                )
                session.add(cfg)
            cfg.enabled, cfg.revision, cfg.interval_minutes = enabled, cfg.revision + 1, minutes
            cfg.next_at, cfg.state, cfg.error = (
                logical + minutes * MINUTE,
                "idle" if enabled else "off",
                None,
            )
            # No claim, reason or unanswered turn is reset by this operation.
            await session.commit()

    async def interrupt_abandoned(self):
        async with self.sessions() as session:
            await _write(session)
            await session.execute(
                update(Episode)
                .where(Episode.state == "writing")
                .values(state="interrupted", error="proactive_interrupted")
            )
            await session.execute(
                update(Settings)
                .where(Settings.state == "writing")
                .values(state="attention", error="proactive_interrupted")
            )
            await session.commit()

    async def _source(self, session, cfg, kind, identity):
        """Current approved activity and presence, not a future plan or same-place guess."""
        now = datetime.now(UTC)
        world = WorldId(cfg.world_id)
        binding = await session.get(Binding, cfg.world_id)
        presence = await session.get(Presence, (cfg.world_id, cfg.player_id))
        clock = await session.get(Clock, cfg.world_id)
        director = await session.get(Director, cfg.world_id)
        if not (
            binding
            and binding.player_id == cfg.player_id
            and presence
            and presence.availability == "available"
            and clock
            and clock.state == "running"
            and director
            and director.enabled
            and director.state == "ready"
            and director.player_id == cfg.player_id
        ):
            return None
        logical = to_domain(clock).effective_time(now).microseconds
        row = await session.get(Shared if kind == "shared" else Routine, (cfg.world_id, identity))
        if not row or row.state != "active" or row.plan_id != director.plan_id:
            return None
        plan = await session.get(Plan, (cfg.world_id, row.plan_id))
        if (
            not plan
            or plan.state != "ready"
            or plan.generation != director.revision
            or not plan.window_start <= logical < plan.window_end
        ):
            return None
        if kind == "shared":
            shared_cfg = await session.get(SharedSettings, cfg.world_id)
            encounter_cfg = await session.get(EncounterSettings, cfg.world_id)
            if not (
                shared_cfg
                and shared_cfg.enabled
                and shared_cfg.player_id == cfg.player_id
                and shared_cfg.revision == row.consent_revision
                and encounter_cfg
                and encounter_cfg.enabled
                and encounter_cfg.player_id == cfg.player_id
                and encounter_cfg.revision == row.encounter_revision
                and not row.continuity_lost
                and row.started_at <= logical < row.planned_end
            ):
                return None
            identities = (row.first_character_id, row.second_character_id)
            routines = [
                await session.get(Routine, (cfg.world_id, r))
                for r in (row.first_routine_id, row.second_routine_id)
            ]
            revisions = (row.first_revision, row.second_revision)
            activity = "rest" if row.activity == "shared_rest" else "leisure"
        else:
            identities, routines, revisions, activity = (
                (row.character_id,),
                [row],
                (row.expected_revision + 1,),
                row.activity,
            )
        if activity not in {"rest", "leisure"}:
            return None
        characters = []
        for character, routine, revision in zip(identities, routines, revisions, strict=True):
            physical = await session.get(CharacterStateRecord, (cfg.world_id, character))
            if not (
                routine
                and routine.state == "active"
                and routine.character_id == character
                and routine.plan_id == row.plan_id
                and routine.location_id == row.location_id
                and routine.activity == activity
                and routine.due_at <= logical < routine.end_at
                and physical
                and physical.location_id == row.location_id
                and physical.revision == revision == routine.expected_revision + 1
            ):
                return None
            contact = (
                await session.execute(
                    select(Conversation, Participant)
                    .join(
                        Participant,
                        (Participant.world_id == Conversation.world_id)
                        & (Participant.conversation_id == Conversation.conversation_id),
                    )
                    .where(
                        Conversation.world_id == cfg.world_id,
                        Conversation.player_id == cfg.player_id,
                        Conversation.kind == "direct",
                        Participant.character_id == character,
                    )
                    .limit(2)
                )
            ).all()
            if len(contact) != 1:
                return None
            convo, member = contact[0]
            persona = await self.director.approved_persona(session, world, character)
            if "accepted_import_id" not in persona:
                return None
            named = await session.get(CharacterRecord, (cfg.world_id, character))
            characters.append(
                {
                    "character_id": str(character),
                    "name": named.name,
                    "conversation_id": str(convo.conversation_id),
                    "root_import_id": str(member.root_import_id),
                    **persona,
                }
            )
        location = await session.get(LocationRecord, (cfg.world_id, row.location_id))
        if not location:
            return None
        background = select_common_background(
            await read_director_background(session, world),
            ("\n".join(c["name"] for c in characters), location.name),
            generation_kind="quiet",
            include_references=True,
        )
        return {
            "characters": characters,
            "location": location.name,
            "activity": activity,
            "purpose": "invite_rest" if activity == "rest" else "invite_leisure",
            "common_world_background": background,
            "plan_id": str(row.plan_id),
            "player_epoch": await self.offline._epoch(session, cfg.world_id, cfg.player_id),
        }

    async def claim_ready(self):
        async with self.sessions() as session:
            await _write(session)
            configs = (
                await session.scalars(
                    select(Settings)
                    .where(Settings.enabled.is_(True), Settings.state == "idle")
                    .order_by(Settings.world_id)
                    .limit(64)
                )
            ).all()
            for cfg in configs:
                clock = await session.get(Clock, cfg.world_id)
                if not clock or clock.state != "running":
                    continue
                logical = to_domain(clock).effective_time(datetime.now(UTC)).microseconds
                if logical < cfg.next_at or await contact_blocked(
                    session, cfg.world_id, cfg.player_id
                ):
                    continue
                director = await session.get(Director, cfg.world_id)
                if not director or director.plan_id == cfg.last_plan_id:
                    continue
                choices = [
                    ("shared", r)
                    for r in (
                        await session.scalars(
                            select(Shared.candidate_id)
                            .where(Shared.world_id == cfg.world_id, Shared.state == "active")
                            .order_by(Shared.started_at, Shared.candidate_id)
                            .limit(2)
                        )
                    ).all()
                ]
                choices += [
                    ("routine", r)
                    for r in (
                        await session.scalars(
                            select(Routine.candidate_id)
                            .where(
                                Routine.world_id == cfg.world_id,
                                Routine.state == "active",
                                Routine.activity.in_(["rest", "leisure"]),
                            )
                            .order_by(Routine.due_at, Routine.candidate_id)
                            .limit(64)
                        )
                    ).all()
                ]
                # Prefer shared activity, then deterministic per-plan ordering.
                # This avoids fixed ID order; it does not guarantee character rotation.
                choices.sort(
                    key=lambda pair: (
                        pair[0] != "shared",
                        hashlib.sha256(f"{director.plan_id}:{pair[1]}".encode()).digest(),
                    )
                )
                for kind, identity in choices:
                    used = await session.scalar(
                        select(Episode.episode_id)
                        .where(
                            Episode.world_id == cfg.world_id,
                            Episode.player_id == cfg.player_id,
                            Episode.source_kind == kind,
                            Episode.source_id == identity,
                        )
                        .limit(1)
                    )
                    if used:
                        continue
                    try:
                        data = await self._source(session, cfg, kind, identity)
                        if data is None:
                            continue
                        serialized = _json(data)
                    except Exception:
                        cfg.state, cfg.error = "attention", "proactive_input_unavailable"
                        break
                    episode = uuid4()
                    session.add(
                        Episode(
                            world_id=cfg.world_id,
                            episode_id=episode,
                            player_id=cfg.player_id,
                            generation=cfg.revision,
                            source_kind=kind,
                            source_id=identity,
                            plan_id=UUID(data["plan_id"]),
                            input_json=serialized,
                            state="writing",
                            created_at_utc=datetime.now(UTC),
                        )
                    )
                    cfg.next_at, cfg.last_plan_id, cfg.state, cfg.error = (
                        logical + cfg.interval_minutes * MINUTE,
                        UUID(data["plan_id"]),
                        "writing",
                        None,
                    )
                    await session.commit()
                    return {"episode_id": episode, "world_id": cfg.world_id, "input": data}
            await session.commit()
            return None

    async def deliver(self, claim, replies, bound):
        async with self.sessions() as session:
            await _write(session)
            episode = await session.get(Episode, (claim["world_id"], claim["episode_id"]))
            cfg = (
                await session.get(Settings, (episode.world_id, episode.player_id))
                if episode
                else None
            )
            valid = bool(
                episode
                and episode.state == "writing"
                and cfg
                and cfg.enabled
                and cfg.revision == episode.generation
            )
            if valid:
                valid = not await contact_blocked(
                    session, episode.world_id, episode.player_id, exclude_online=episode.episode_id
                )
            if valid:
                current = await self._source(session, cfg, episode.source_kind, episode.source_id)
                valid = current is not None and _json(current) == episode.input_json
            if not valid:
                raise ProactiveContactError("proactive_context_changed")
            data = json.loads(episode.input_json)
            characters = data["characters"]
            now = datetime.now(UTC)
            if len(characters) == 1:
                conversation = UUID(characters[0]["conversation_id"])
            else:
                expected = {UUID(c["character_id"]) for c in characters}
                groups = (
                    await session.scalars(
                        select(Conversation)
                        .where(
                            Conversation.world_id == episode.world_id,
                            Conversation.player_id == episode.player_id,
                            Conversation.kind == "group",
                        )
                        .order_by(Conversation.conversation_id)
                        .limit(513)
                    )
                ).all()
                if len(groups) > 512:
                    raise ProactiveContactError("proactive_input_capacity")
                conversation = None
                for group in groups:
                    members = set(
                        (
                            await session.scalars(
                                select(Participant.character_id).where(
                                    Participant.world_id == episode.world_id,
                                    Participant.conversation_id == group.conversation_id,
                                )
                            )
                        ).all()
                    )
                    if members == expected:
                        conversation = group.conversation_id
                        break
                if conversation is None:
                    conversation = uuid5(
                        episode.world_id,
                        "proactive-group:"
                        + str(episode.player_id)
                        + ":"
                        + ":".join(sorted(str(i) for i in expected)),
                    )
                    session.add(
                        Conversation(
                            world_id=episode.world_id,
                            conversation_id=conversation,
                            player_id=episode.player_id,
                            kind="group",
                            created_at_utc=now,
                        )
                    )
                    await session.flush()
                    for c in characters:
                        session.add(
                            Participant(
                                world_id=episode.world_id,
                                conversation_id=conversation,
                                character_id=UUID(c["character_id"]),
                                root_import_id=UUID(c["root_import_id"]),
                            )
                        )
            position = (
                await session.scalar(
                    select(func.max(Message.position)).where(
                        Message.world_id == episode.world_id,
                        Message.conversation_id == conversation,
                    )
                )
                or 0
            )
            turn_id = uuid5(episode.episode_id, "outreach-turn")
            session.add(
                Turn(
                    world_id=episode.world_id,
                    turn_id=turn_id,
                    conversation_id=conversation,
                    request_id=episode.episode_id,
                    fingerprint=hashlib.sha256(episode.input_json.encode()).hexdigest(),
                    token_ceiling=bound,
                    kind="outreach",
                    status="pending",
                    created_at_utc=now,
                )
            )
            await session.flush()
            session.add(
                Dispatch(
                    world_id=episode.world_id,
                    turn_id=turn_id,
                    claimed_at_utc=episode.created_at_utc,
                    completed_at_utc=now,
                )
            )
            for index, c in enumerate(characters, 1):
                message = Message(
                    world_id=episode.world_id,
                    message_id=uuid5(episode.episode_id, c["character_id"]),
                    conversation_id=conversation,
                    turn_id=turn_id,
                    position=position + index,
                    sender_character_id=UUID(c["character_id"]),
                    text=replies[c["character_id"]],
                    created_at_utc=now,
                )
                session.add(message)
                await session.flush()
                clock = await session.get(Clock, episode.world_id)
                await record_contact_invitation(
                    session,
                    message,
                    PlayerId(WorldId(episode.world_id), episode.player_id),
                    c["name"],
                    to_domain(clock).effective_time(now).microseconds,
                )
            episode.state, episode.conversation_id = "delivered", conversation
            cfg.state, cfg.error = "idle", None
            await session.commit()

    async def finish(self, claim, state, code):
        async with self.sessions() as session:
            await _write(session)
            ep = await session.get(Episode, (claim["world_id"], claim["episode_id"]))
            if ep and ep.state == "writing":
                ep.state, ep.error = state, code
                cfg = await session.get(Settings, (ep.world_id, ep.player_id))
                if cfg and cfg.revision == ep.generation:
                    cfg.state, cfg.error = (
                        ("attention" if state in {"failed", "interrupted"} else "idle"),
                        code,
                    )
            await session.commit()
