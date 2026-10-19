"""One local recovery target, frozen past inputs, durable no-replay receipts."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update

from livingworld.application.director import DirectorError
from livingworld.application.errors import EntityNotFoundError
from livingworld.application.lore_activation import select_common_background
from livingworld.application.offline_contact import OfflineContactError
from livingworld.application.offline_contact_inputs import (
    MAX_CONTACT_SCAN,
    MAX_CONTACTS,
    MAX_INPUT_BYTES,
    PERSONA_READ_BYTES,
    PREPARATION_ERRORS,
    ContactInput,
    capture_cursor,
    encode_input,
    pack_snapshot,
)
from livingworld.domain.identifiers import PlayerId, WorldId
from livingworld.infrastructure.persistence.director_background import (
    background_is_current,
    read_director_background,
)
from livingworld.infrastructure.persistence.director_models import (
    DirectorCandidateRecord as Candidate,
)
from livingworld.infrastructure.persistence.mapping import to_domain
from livingworld.infrastructure.persistence.models import (
    CharacterRecord,
    WorldRecord,
)
from livingworld.infrastructure.persistence.models import (
    ChatConversationRecord as Conversation,
)
from livingworld.infrastructure.persistence.models import (
    ChatMessageRecord as Message,
)
from livingworld.infrastructure.persistence.models import (
    ChatParticipantRecord as Participant,
)
from livingworld.infrastructure.persistence.models import (
    ChatTurnDispatchRecord as Dispatch,
)
from livingworld.infrastructure.persistence.models import (
    ChatTurnRecord as Turn,
)
from livingworld.infrastructure.persistence.models import (
    LocalPlayerBindingRecord as Binding,
)
from livingworld.infrastructure.persistence.models import (
    PlayerPresenceRecord as Presence,
)
from livingworld.infrastructure.persistence.models import (
    WorldClockRecord as Clock,
)
from livingworld.infrastructure.persistence.models import (
    WorldContentImportRecord as Imported,
)
from livingworld.infrastructure.persistence.offline_contact_models import (
    LocalSessionVisibilityRecord as Visibility,
)
from livingworld.infrastructure.persistence.offline_contact_models import (
    OfflineContactEpisodeRecord as Episode,
)
from livingworld.infrastructure.persistence.offline_contact_models import (
    OfflineContactSettingsRecord as Settings,
)
from livingworld.infrastructure.persistence.world_story import record_contact_invitation


async def _write(session):
    await session.begin()
    await session.connection(execution_options={"livingworld_write_intent": True})


def _json(value):
    text = encode_input(value)
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise OfflineContactError("offline_snapshot_capacity")
    return text


class SqlAlchemyOfflineContactStore:
    def __init__(self, sessions, director):
        self.sessions, self.director = sessions, director

    async def _owner(self, session, world, player):
        if await session.get(WorldRecord, world.value) is None:
            raise EntityNotFoundError("world_not_found")
        binding = await session.get(Binding, world.value)
        if player is None or binding is None or binding.player_id != player.value:
            raise OfflineContactError("offline_player_required")

    async def snapshot(self, world, player):
        async with self.sessions() as session:
            await self._owner(session, world, player)
            cfg = await session.get(Settings, 1)
            owned = (
                cfg is not None and cfg.world_id == world.value and cfg.player_id == player.value
            )
            unread = (
                await session.scalars(
                    select(Episode)
                    .where(
                        Episode.world_id == world.value,
                        Episode.player_id == player.value,
                        Episode.state == "delivered",
                        Episode.read_at_utc.is_(None),
                    )
                    .order_by(Episode.created_at_utc.desc())
                    .limit(16)
                )
            ).all()
            return {
                "enabled": bool(owned and cfg.enabled),
                "consented": bool(owned),
                "revision": cfg.revision if cfg else 0,
                "hours": cfg.hours if owned else 6,
                "state": cfg.state if owned else "off",
                "error": cfg.error if owned else None,
                "input_preparation": (
                    json.loads(cfg.input_json).get("input_preparation")
                    if owned and cfg.input_json
                    else None
                ),
                "last_online_at": cfg.last_online_at.isoformat()
                if owned and cfg.last_online_at
                else None,
                "unread": [
                    {"message_id": str(ep.message_id), "conversation_id": str(ep.conversation_id)}
                    for ep in unread
                ],
            }

    async def configure(self, world, player, enabled, hours, consent, revision):
        async with self.sessions() as session:
            await _write(session)
            await self._owner(session, world, player)
            cfg = await session.get(Settings, 1)
            if (cfg.revision if cfg else 0) != revision:
                raise OfflineContactError("offline_settings_changed")
            owned = (
                cfg is not None and cfg.world_id == world.value and cfg.player_id == player.value
            )
            if enabled and not owned and not consent:
                raise OfflineContactError("offline_consent_required")
            if not enabled and not owned:
                return
            if owned and cfg.enabled == enabled and cfg.hours == hours:
                return
            now = datetime.now(UTC)
            if cfg is None:
                cfg = Settings(
                    singleton=1,
                    world_id=world.value,
                    player_id=player.value,
                    enabled=False,
                    revision=0,
                    hours=hours,
                    consented_at=now,
                    state="off",
                )
                session.add(cfg)
            if not owned:
                cfg.consented_at = now
                cfg.input_json = None
            cfg.world_id, cfg.player_id = world.value, player.value
            cfg.enabled, cfg.hours, cfg.revision = enabled, hours, cfg.revision + 1
            cfg.state, cfg.error, cfg.episode_id = ("idle" if enabled else "off"), None, None
            # Enabling/change establishes a new baseline; it cannot backfill old downtime.
            cfg.last_online_at = now
            cfg.input_json = await self._capture(session, cfg, now) if enabled else None
            await self._preparation_status(session, cfg)
            await session.commit()

    async def _epoch(self, session, world, player):
        value = await session.scalar(
            select(Message.message_id)
            .join(
                Conversation,
                (Conversation.world_id == Message.world_id)
                & (Conversation.conversation_id == Message.conversation_id),
            )
            .where(
                Message.world_id == world,
                Conversation.player_id == player,
                Message.sender_player_id == player,
            )
            .order_by(Message.created_at_utc.desc(), Message.message_id.desc())
            .limit(1)
        )
        return str(value) if value else "initial"

    async def _capture(self, session, cfg, now, *, advance=False):
        from livingworld.infrastructure.persistence.authored_lifecycle import removed_character_ids

        removed = await removed_character_ids(session, cfg.world_id)
        after = capture_cursor(cfg.input_json, advance=advance)
        binding = await session.get(Binding, cfg.world_id)
        presence = await session.get(Presence, (cfg.world_id, cfg.player_id))
        clock = await session.get(Clock, cfg.world_id)
        if not binding or binding.player_id != cfg.player_id:
            cfg.enabled, cfg.state = False, "off"
            cfg.revision += 1
            return None
        if (
            not presence
            or presence.availability != "available"
            or not clock
            or clock.state != "running"
        ):
            return _json(
                {
                    "eligible": False,
                    "input_selection": {
                        "after": str(after) if after else None,
                        "next_after": str(after) if after else None,
                    },
                }
            )
        world = WorldId(cfg.world_id)
        logical = clock.logical_time.microseconds
        elapsed = max(0, int((now - clock.observed_wall_time_utc).total_seconds() * 1000000))
        logical += int(elapsed * clock.time_scale)
        # Remote contact does not require a physical placement or a routine plan.
        # Bind the finite contact set to this Player before reading approved personas.
        query = (
            select(Conversation, Participant, CharacterRecord.name)
            .join(
                Participant,
                (Participant.world_id == Conversation.world_id)
                & (Participant.conversation_id == Conversation.conversation_id),
            )
            .join(
                CharacterRecord,
                (CharacterRecord.world_id == Participant.world_id)
                & (CharacterRecord.character_id == Participant.character_id),
            )
            .where(
                Conversation.world_id == cfg.world_id,
                Conversation.player_id == cfg.player_id,
                Conversation.kind == "direct",
                Participant.character_id.not_in(removed),
            )
            .order_by(Conversation.conversation_id)
        )
        # A keyset cursor advances once per recovery, never on every heartbeat.
        # Read one bounded local cohort, wrapping at the end of the directory.
        contacts = list(
            (
                await session.execute(
                    (query.where(Conversation.conversation_id > after) if after else query).limit(
                        MAX_CONTACT_SCAN + 1
                    )
                )
            ).all()
        )
        if after and len(contacts) <= MAX_CONTACT_SCAN:
            contacts.extend(
                (
                    await session.execute(
                        query.where(Conversation.conversation_id <= after).limit(
                            MAX_CONTACT_SCAN + 1 - len(contacts)
                        )
                    )
                ).all()
            )
        characters: list[ContactInput] = []
        seen = set()
        scanned, excluded = 0, 0
        next_after = after
        for convo, part, name in contacts[:MAX_CONTACT_SCAN]:
            scanned += 1
            next_after = convo.conversation_id
            if part.character_id in seen:
                continue
            seen.add(part.character_id)
            try:
                persona = await self.director.approved_persona(
                    session, world, part.character_id, text_limit=PERSONA_READ_BYTES
                )
                if not isinstance(persona, dict) or not isinstance(
                    persona.get("accepted_import_id"), str
                ):
                    raise OfflineContactError("offline_character_mapping_invalid")
                accepted = UUID(persona["accepted_import_id"])
                if not isinstance(persona.get("persona"), dict):
                    raise OfflineContactError("offline_character_mapping_invalid")
                public_persona = {
                    field: persona["persona"].get(field)
                    for field in ("personality", "description", "background")
                }
                if any(not isinstance(value, str) for value in public_persona.values()):
                    raise OfflineContactError("offline_character_mapping_invalid")
                name.encode("utf-8")
                for value in public_persona.values():
                    value.encode("utf-8")
                characters.append(
                    {
                        "character_id": str(part.character_id),
                        "name": name,
                        "conversation_id": str(convo.conversation_id),
                        "accepted_import_id": str(accepted),
                        "persona": public_persona,
                        "persona_truncated": persona.get("persona_truncated") is True,
                    }
                )
            except (DirectorError, OfflineContactError, ValueError, TypeError, KeyError):
                # Only this candidate is excluded. Database failures still abort
                # the capture and cannot authorize a model invocation.
                excluded += 1
                continue
            if len(characters) == MAX_CONTACTS:
                break
        background_omitted = False
        try:
            background = (
                select_common_background(
                    await read_director_background(
                        session, world, texts=("\n".join(c["name"] for c in characters),)
                    ),
                    ("\n".join(c["name"] for c in characters),),
                    generation_kind="quiet",
                    include_references=True,
                )
                if characters
                else []
            )
        except DirectorError:
            # An unavailable optional public context cannot stop a valid greeting.
            # Do not bypass exposure checks or substitute private lore.
            background, background_omitted = [], True
        snapshot = {
            "player_epoch": await self._epoch(session, cfg.world_id, cfg.player_id),
            "utc_offset_minutes": int(now.astimezone().utcoffset().total_seconds() // 60),
            "input_selection": {
                "after": str(after) if after else None,
                "next_after": str(next_after) if next_after else None,
            },
        }
        # This is a past plan/intent, not evidence that future activities occurred.
        candidates = (
            await session.scalars(
                select(Candidate)
                .where(
                    Candidate.world_id == cfg.world_id,
                    Candidate.character_id.in_([UUID(c["character_id"]) for c in characters]),
                    Candidate.state.in_(["pending", "active"]),
                    Candidate.end_at > logical,
                )
                .order_by(Candidate.due_at, Candidate.candidate_id)
                .limit(64)
            )
        ).all()
        intentions = [
            {
                "character_id": str(c.character_id),
                "activity": c.activity,
                "starts_after_minutes": max(0, (c.due_at - logical) // 60000000),
                "ends_after_minutes": max(0, (c.end_at - logical) // 60000000),
            }
            for c in candidates
        ]
        preparation = {
            "selected": len(characters),
            "excluded": excluded,
            "clipped": 0,
            "batched": len(contacts) > scanned,
            "background_omitted": background_omitted,
            "context_limited": False,
        }
        try:
            return pack_snapshot(snapshot, characters, background, intentions, preparation)
        except ValueError:
            raise OfflineContactError("offline_snapshot_capacity") from None

    async def _preparation_status(self, session, cfg):
        if not cfg.enabled or not cfg.input_json or cfg.state in {"waiting", "planning", "writing"}:
            return
        data = json.loads(cfg.input_json)
        preparation = data.get("input_preparation", {})
        prepared = data.get("eligible") or (
            preparation.get("selected") == 0 and preparation.get("excluded") == 0
        )
        if cfg.state == "attention" and cfg.error in PREPARATION_ERRORS and prepared:
            episode = await session.get(Episode, cfg.episode_id) if cfg.episode_id else None
            # Recover the actual task receipt if an old preparation error hid it.
            if (
                episode
                and episode.world_id == cfg.world_id
                and episode.player_id == cfg.player_id
                and episode.generation == cfg.revision
            ):
                state = {
                    "queued": "waiting",
                    "planning": "planning",
                    "writing": "writing",
                    "failed": "attention",
                    "interrupted": "attention",
                }.get(episode.state, episode.state)
                cfg.state, cfg.error = state, episode.error
            else:
                cfg.state, cfg.error = "idle", None
        if (
            not data.get("eligible")
            and preparation.get("excluded", 0)
            and (cfg.error is None or cfg.error in PREPARATION_ERRORS)
        ):
            cfg.state, cfg.error = "attention", "offline_candidates_unavailable"

    async def _unanswered(self, session, cfg, exclude=None):
        from livingworld.infrastructure.persistence.contact_gate import contact_blocked

        return await contact_blocked(session, cfg.world_id, cfg.player_id, exclude_offline=exclude)

    async def interrupt_abandoned(self):
        async with self.sessions() as session:
            await _write(session)
            await session.execute(
                update(Episode)
                .where(Episode.state.in_(["queued", "planning", "writing"]))
                .values(state="interrupted", error="offline_interrupted")
            )
            cfg = await session.get(Settings, 1)
            if cfg and cfg.state in {"waiting", "planning", "writing"}:
                cfg.state, cfg.error = "attention", "offline_interrupted"
            await session.commit()

    async def pulse(self, recover=True):
        async with self.sessions() as session:
            await _write(session)
            cfg = await session.get(Settings, 1)
            if not cfg or not cfg.enabled:
                return
            now = datetime.now(UTC)
            if cfg.last_online_at and now < cfg.last_online_at:
                cfg.error = "offline_clock_regression"
                await session.commit()
                return
            previous = cfg.last_online_at
            recovering = bool(recover and previous and now - previous >= timedelta(hours=cfg.hours))
            if recovering:
                frozen = json.loads(cfg.input_json) if cfg.input_json else {}
                binding = await session.get(Binding, cfg.world_id)
                epoch = frozen.get("player_epoch", "initial")
                reason = hashlib.sha256(
                    f"{cfg.world_id}:{cfg.player_id}:offline_check_in:{epoch}".encode()
                ).hexdigest()
                used = await session.scalar(
                    select(Episode.episode_id)
                    .where(
                        Episode.world_id == cfg.world_id,
                        Episode.player_id == cfg.player_id,
                        Episode.reason_key == reason,
                    )
                    .limit(1)
                )
                eligible = bool(
                    frozen.get("eligible") and binding and binding.player_id == cfg.player_id
                )
                blocked = await self._unanswered(session, cfg) if eligible else False
                if eligible and not used and not blocked:
                    ep = Episode(
                        episode_id=uuid4(),
                        world_id=cfg.world_id,
                        player_id=cfg.player_id,
                        generation=cfg.revision,
                        reason_key=reason,
                        offline_from=previous,
                        offline_to=now,
                        input_json=cfg.input_json,
                        state="queued",
                        created_at_utc=now,
                    )
                    session.add(ep)
                    cfg.episode_id, cfg.state, cfg.error = ep.episode_id, "waiting", None
                else:
                    if blocked:
                        from livingworld.infrastructure.persistence.contact_gate import (
                            waiting_conversation,
                        )

                        unanswered = await waiting_conversation(
                            session, cfg.world_id, cfg.player_id
                        )
                    else:
                        unanswered = None
                    if unanswered:
                        skip_reason = "offline_waiting_reply"
                    elif used:
                        skip_reason = "offline_reason_used"
                    elif blocked:
                        skip_reason = "offline_contact_in_progress"
                    else:
                        skip_reason = "offline_no_contact"
                    cfg.state, cfg.error = "skipped", skip_reason
            cfg.last_online_at = now
            try:
                cfg.input_json = await self._capture(session, cfg, now, advance=recovering)
                await self._preparation_status(session, cfg)
            except OfflineContactError as error:
                cfg.input_json = None
                if cfg.state not in {"waiting", "planning", "writing"} and (
                    cfg.error is None or cfg.error in PREPARATION_ERRORS
                ):
                    cfg.state, cfg.error = "attention", str(error)
            except Exception:
                cfg.input_json = None
                if cfg.state not in {"waiting", "planning", "writing"} and (
                    cfg.error is None or cfg.error in PREPARATION_ERRORS
                ):
                    cfg.state, cfg.error = "attention", "offline_input_unavailable"
            await session.commit()

    async def _valid(self, session, ep):
        cfg = await session.get(Settings, 1)
        binding = await session.get(Binding, ep.world_id)
        presence = await session.get(Presence, (ep.world_id, ep.player_id))
        clock = await session.get(Clock, ep.world_id)
        if not (
            cfg
            and cfg.enabled
            and cfg.revision == ep.generation
            and cfg.world_id == ep.world_id
            and cfg.player_id == ep.player_id
            and binding
            and binding.player_id == ep.player_id
            and presence
            and presence.availability == "available"
            and clock
            and clock.state == "running"
        ):
            return False
        data = json.loads(ep.input_json)
        if await self._epoch(session, ep.world_id, ep.player_id) != data.get("player_epoch"):
            return False
        if await self._unanswered(session, cfg, exclude=ep.episode_id):
            return False
        if not await background_is_current(session, WorldId(ep.world_id), ep.input_json):
            return False
        for c in data["characters"]:
            imported = UUID(c["accepted_import_id"])
            current = await session.get(Imported, imported)
            if current is None or current.world_id != ep.world_id or current.removed_at is not None:
                return False
            if await session.scalar(
                select(Imported.import_id)
                .where(Imported.world_id == ep.world_id, Imported.replaces_import_id == imported)
                .limit(1)
            ):
                return False
            contact = await session.get(Conversation, (ep.world_id, UUID(c["conversation_id"])))
            part = await session.get(
                Participant, (ep.world_id, UUID(c["conversation_id"]), UUID(c["character_id"]))
            )
            if (
                not contact
                or contact.player_id != ep.player_id
                or contact.kind != "direct"
                or not part
            ):
                return False
        return True

    async def claim_ready(self):
        async with self.sessions() as session:
            await _write(session)
            ep = await session.scalar(select(Episode).where(Episode.state == "queued").limit(1))
            if ep is None:
                return None
            if not await self._valid(session, ep):
                await self._terminal(session, ep, "skipped", "offline_context_changed")
                await session.commit()
                return None
            ep.state = "planning"
            cfg = await session.get(Settings, 1)
            cfg.state = "planning"
            result = {
                "episode_id": ep.episode_id,
                "world_id": ep.world_id,
                "input": json.loads(ep.input_json),
                "offline_from": ep.offline_from,
                "offline_to": ep.offline_to,
            }
            await session.commit()
            return result

    async def prepare_dialogue(self, identity, character, purpose, story_time):
        async with self.sessions() as session:
            await _write(session)
            ep = await session.get(Episode, identity)
            if not ep or ep.state != "planning" or not await self._valid(session, ep):
                raise OfflineContactError("offline_context_changed")
            if not ep.offline_from < story_time < ep.offline_to:
                raise OfflineContactError("offline_plan_invalid")
            chosen = next(
                (
                    c
                    for c in json.loads(ep.input_json)["characters"]
                    if c["character_id"] == character
                ),
                None,
            )
            if chosen is None:
                raise OfflineContactError("offline_plan_invalid")
            ep.character_id, ep.conversation_id = UUID(character), UUID(chosen["conversation_id"])
            ep.purpose, ep.story_sent_at_utc, ep.state = purpose, story_time, "writing"
            cfg = await session.get(Settings, 1)
            cfg.state = "writing"
            await session.commit()
            return chosen

    async def deliver(self, identity, text, token_ceiling):
        async with self.sessions() as session:
            await _write(session)
            ep = await session.get(Episode, identity)
            if not ep or ep.state != "writing" or not await self._valid(session, ep):
                raise OfflineContactError("offline_context_changed")
            now = datetime.now(UTC)
            if now < ep.offline_to:
                raise OfflineContactError("offline_clock_regression")
            position = (
                await session.scalar(
                    select(func.max(Message.position)).where(
                        Message.world_id == ep.world_id,
                        Message.conversation_id == ep.conversation_id,
                    )
                )
                or 0
            ) + 1
            turn_id, message_id = uuid4(), uuid4()
            # Explicit outreach turn; there is no fake player send or runnable reply claim.
            session.add(
                Turn(
                    world_id=ep.world_id,
                    turn_id=turn_id,
                    conversation_id=ep.conversation_id,
                    request_id=ep.episode_id,
                    fingerprint=ep.reason_key,
                    token_ceiling=token_ceiling,
                    kind="outreach",
                    status="pending",
                    created_at_utc=now,
                )
            )
            await session.flush()
            session.add(
                Dispatch(
                    world_id=ep.world_id,
                    turn_id=turn_id,
                    claimed_at_utc=ep.created_at_utc,
                    completed_at_utc=now,
                )
            )
            message = Message(
                world_id=ep.world_id,
                message_id=message_id,
                conversation_id=ep.conversation_id,
                turn_id=turn_id,
                position=position,
                sender_character_id=ep.character_id,
                text=text,
                created_at_utc=now,
                story_sent_at_utc=ep.story_sent_at_utc,
            )
            session.add(message)
            await session.flush()
            if ep.purpose == "invite_chat":
                chosen = next(
                    c
                    for c in json.loads(ep.input_json)["characters"]
                    if c["character_id"] == str(ep.character_id)
                )
                clock = await session.get(Clock, ep.world_id)
                await record_contact_invitation(
                    session,
                    message,
                    PlayerId(WorldId(ep.world_id), ep.player_id),
                    chosen["name"],
                    to_domain(clock).effective_time(now).microseconds if clock else None,
                )
            ep.message_id = message_id
            await self._terminal(session, ep, "delivered", None)
            await session.commit()

    async def _terminal(self, session, ep, state, code):
        ep.state, ep.error = state, code
        cfg = await session.get(Settings, 1)
        if cfg and cfg.revision == ep.generation and cfg.episode_id == ep.episode_id:
            cfg.state = "attention" if state in {"failed", "interrupted"} else state
            cfg.error = code

    async def finish(self, identity, state, code=None):
        async with self.sessions() as session:
            await _write(session)
            ep = await session.get(Episode, identity)
            if ep and ep.state in {"queued", "planning", "writing"}:
                await self._terminal(session, ep, state, code)
            await session.commit()

    async def mark_read(self, world, player, message_id):
        async with self.sessions() as session:
            await _write(session)
            await self._owner(session, world, player)
            ep = await session.scalar(
                select(Episode).where(
                    Episode.world_id == world.value,
                    Episode.player_id == player.value,
                    Episode.message_id == message_id,
                    Episode.state == "delivered",
                )
            )
            if ep is None:
                raise EntityNotFoundError("message_not_found")
            if ep.read_at_utc is None:
                ep.read_at_utc = datetime.now(UTC)
            await session.commit()

    async def reset_visibility(self):
        async with self.sessions() as session:
            await _write(session)
            row = await session.get(Visibility, 1)
            if row is None:
                session.add(
                    Visibility(
                        singleton=1, world_id=None, visible_until=datetime.now(UTC), sequence=0
                    )
                )
            else:
                row.world_id, row.visible_until, row.sequence = None, datetime.now(UTC), 0
            await session.commit()

    async def visibility(self, world_id, visible, sequence):
        async with self.sessions() as session:
            await _write(session)
            row = await session.get(Visibility, 1)
            if row is None or sequence <= row.sequence:
                return
            if visible:
                if world_id is None or await session.get(Binding, world_id) is None:
                    return
                row.world_id = world_id
                row.visible_until = datetime.now(UTC) + timedelta(seconds=30)
            else:
                row.world_id, row.visible_until = None, datetime.now(UTC)
            row.sequence = sequence
            await session.commit()
