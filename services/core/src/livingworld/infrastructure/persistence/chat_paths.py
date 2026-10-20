"""Immutable transcript forks, CAS path selection and idempotent reviewed mutations."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, func, insert, literal, or_, select

from livingworld.application.chat_paths import ChatPathError, PathConfirm
from livingworld.application.errors import EntityNotFoundError, IdempotencyConflictError
from livingworld.infrastructure.persistence.authored_lifecycle import require_active_conversation
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatPathMessageRecord as Member,
)
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatPathOperationRecord as Operation,
)
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatPathRecord as Path,
)
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatPathStateRecord as State,
)
from livingworld.infrastructure.persistence.chat_path_models import (
    ChatPathTurnRecord as PathTurn,
)
from livingworld.infrastructure.persistence.chat_path_queries import (
    active_message_clause,
    stamp_message,
)
from livingworld.infrastructure.persistence.contact_gate import waiting_conversation
from livingworld.infrastructure.persistence.models import (
    ChatConversationRecord as Conversation,
)
from livingworld.infrastructure.persistence.models import (
    ChatMessageRecord as Message,
)
from livingworld.infrastructure.persistence.models import (
    ChatReplyExecutionRecord as Execution,
)
from livingworld.infrastructure.persistence.models import (
    ChatReplyRecoveryRecord as Recovery,
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


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _view(row):
    return {
        "path_id": str(row.path_id),
        "parent_id": str(row.parent_id) if row.parent_id else None,
        "name": row.name,
        "kind": row.kind,
        "created_at": row.created_at.isoformat(),
        "fork_message_id": str(row.fork_message_id) if row.fork_message_id else None,
    }


class SqlAlchemyChatPathStore:
    def __init__(self, sessions):
        self._sessions = sessions

    async def _owner(self, session, world, conversation, player):
        row = await session.get(Conversation, (world, conversation))
        binding = await session.get(Binding, world)
        if row is None or row.player_id != player or binding is None or binding.player_id != player:
            raise EntityNotFoundError("conversation_not_found")
        return row

    async def _snapshot(self, session, owner, before=None):
        state = await session.get(State, (owner.world_id, owner.conversation_id))
        if state is None:
            main = Path(
                world_id=owner.world_id,
                path_id=owner.conversation_id,
                conversation_id=owner.conversation_id,
                parent_id=None,
                fork_message_id=None,
                name="主线",
                kind="main",
                created_at=owner.created_at_utc,
            )
            return {
                "active": _view(main),
                "revision": 0,
                "paths": [_view(main)],
                "next_before": None,
            }
        query = select(Path).where(
            Path.world_id == owner.world_id, Path.conversation_id == owner.conversation_id
        )
        if before is not None:
            cursor = await session.get(Path, (owner.world_id, before))
            if cursor is None or cursor.conversation_id != owner.conversation_id:
                raise EntityNotFoundError("chat_path_not_found")
            query = query.where(
                or_(
                    Path.created_at < cursor.created_at,
                    and_(Path.created_at == cursor.created_at, Path.path_id < cursor.path_id),
                )
            )
        rows = (
            await session.scalars(
                query.order_by(Path.created_at.desc(), Path.path_id.desc()).limit(41)
            )
        ).all()
        active = await session.get(Path, (owner.world_id, state.active_path_id))
        return {
            "active": _view(active),
            "revision": state.revision,
            "paths": [_view(row) for row in rows[:40]],
            "next_before": str(rows[39].path_id) if len(rows) > 40 else None,
        }

    async def snapshot(self, world, conversation, player, before=None):
        async with self._sessions() as session:
            return await self._snapshot(
                session, await self._owner(session, world, conversation, player), before
            )

    async def _quiet(self, session, owner, action):
        await require_active_conversation(session, owner.world_id, owner.conversation_id)
        busy = await session.scalar(
            select(Turn.turn_id)
            .join(
                Dispatch, and_(Dispatch.world_id == Turn.world_id, Dispatch.turn_id == Turn.turn_id)
            )
            .outerjoin(
                Execution,
                and_(Execution.world_id == Turn.world_id, Execution.turn_id == Turn.turn_id),
            )
            .where(
                Turn.world_id == owner.world_id,
                Turn.conversation_id == owner.conversation_id,
                or_(
                    Execution.state.in_(("running", "unknown")),
                    and_(Execution.turn_id.is_(None), Dispatch.completed_at_utc.is_(None)),
                ),
            )
            .limit(1)
        )
        if busy is not None:
            raise ChatPathError("chat_path_reply_running")
        if (
            action not in {"checkpoint", "rename"}
            and await waiting_conversation(session, owner.world_id, owner.player_id)
            == owner.conversation_id
        ):
            raise ChatPathError("chat_path_waiting_contact")
        # Background delivery is also a transcript writer. Its in-flight results
        # must finish before a user changes the destination path.
        from livingworld.infrastructure.persistence.offline_contact_models import (
            OfflineContactEpisodeRecord,
        )
        from livingworld.infrastructure.persistence.proactive_models import ProactiveEpisodeRecord

        for model in (OfflineContactEpisodeRecord, ProactiveEpisodeRecord):
            if (
                await session.scalar(
                    select(model.episode_id)
                    .where(model.world_id == owner.world_id, model.state == "writing")
                    .limit(1)
                )
                is not None
            ):
                raise ChatPathError("chat_path_reply_running")

    async def _prepare(self, session, owner, draft):
        state = await session.get(State, (owner.world_id, owner.conversation_id))
        revision = state.revision if state else 0
        active = state.active_path_id if state else owner.conversation_id
        if revision != draft.revision:
            raise ChatPathError("chat_path_changed")
        await self._quiet(session, owner, draft.action)
        target = None
        if draft.message_id is not None:
            target = await session.scalar(
                select(Message).where(
                    Message.world_id == owner.world_id,
                    Message.conversation_id == owner.conversation_id,
                    Message.message_id == draft.message_id,
                    active_message_clause(Message),
                )
            )
            if target is None:
                raise EntityNotFoundError("chat_message_not_found")
        if draft.action in {"edit", "candidate", "branch", "checkpoint"} and target is None:
            raise ChatPathError("chat_path_message_required")
        path = None
        if draft.action in {"switch", "rename"}:
            if state is None and draft.path_id == owner.conversation_id:
                path = None
            else:
                path = (
                    await session.get(Path, (owner.world_id, draft.path_id))
                    if draft.path_id
                    else None
                )
                if path is None or path.conversation_id != owner.conversation_id:
                    raise EntityNotFoundError("chat_path_not_found")
        if draft.action == "edit" and (
            not draft.text.strip() or len(draft.text.encode()) > 128 * 1024
        ):
            raise ChatPathError("chat_path_text_invalid")
        if (
            draft.action == "edit"
            and target is not None
            and target.media_json
            and json.loads(target.media_json).get("only_media")
        ):
            raise ChatPathError("chat_path_media_only")
        if draft.action == "rename" and not draft.name.strip():
            raise ChatPathError("chat_path_name_required")
        if draft.action == "candidate":
            await self._candidate_question(session, owner, target)
        head = (
            await session.scalar(
                select(func.max(Message.position)).where(
                    Message.world_id == owner.world_id,
                    Message.conversation_id == owner.conversation_id,
                    active_message_clause(Message),
                )
            )
            or 0
        )
        reviewed = _digest(
            {
                "world": str(owner.world_id),
                "conversation": str(owner.conversation_id),
                "player": str(owner.player_id),
                "path": str(active),
                "head": head,
                "draft": draft.model_dump(mode="json"),
                "source": target.text if target else None,
            }
        )
        return state, active, target, path, reviewed

    async def preview(self, world, conversation, player, draft):
        async with self._sessions() as session:
            owner = await self._owner(session, world, conversation, player)
            _, _, target, _, reviewed = await self._prepare(session, owner, draft)
            return {
                "reviewed_hash": reviewed,
                "draft": draft.model_dump(mode="json"),
                "original_text": target.text if target else None,
                "calls_model": draft.action == "candidate",
                "creates_path": draft.action in {"branch", "checkpoint", "edit", "candidate"},
            }

    async def _ensure_main(self, session, owner):
        state = await session.get(State, (owner.world_id, owner.conversation_id))
        if state is not None:
            return state
        session.add(
            Path(
                world_id=owner.world_id,
                path_id=owner.conversation_id,
                conversation_id=owner.conversation_id,
                parent_id=None,
                fork_message_id=None,
                name="主线",
                kind="main",
                created_at=owner.created_at_utc,
            )
        )
        await session.flush()
        state = State(
            world_id=owner.world_id,
            conversation_id=owner.conversation_id,
            active_path_id=owner.conversation_id,
            revision=0,
        )
        session.add(state)
        await session.flush()
        await session.execute(
            insert(Member).from_select(
                ["world_id", "path_id", "message_id"],
                select(
                    Message.world_id,
                    literal(owner.conversation_id, type_=Member.path_id.type),
                    Message.message_id,
                ).where(
                    Message.world_id == owner.world_id,
                    Message.conversation_id == owner.conversation_id,
                ),
            )
        )
        return state

    async def _fork(self, session, owner, state, draft, target, cutoff):
        path = Path(
            world_id=owner.world_id,
            path_id=uuid4(),
            conversation_id=owner.conversation_id,
            parent_id=state.active_path_id,
            fork_message_id=target.message_id,
            name=draft.name.strip()
            or {
                "edit": "编辑后的路线",
                "candidate": "候选回复",
                "branch": "新分支",
                "checkpoint": "检查点",
            }[draft.action],
            kind=draft.action,
            created_at=datetime.now(UTC),
        )
        session.add(path)
        await session.flush()
        await session.execute(
            insert(Member).from_select(
                ["world_id", "path_id", "message_id"],
                select(
                    Member.world_id,
                    literal(path.path_id, type_=Member.path_id.type),
                    Member.message_id,
                )
                .join(
                    Message,
                    and_(
                        Message.world_id == Member.world_id, Message.message_id == Member.message_id
                    ),
                )
                .where(
                    Member.world_id == owner.world_id,
                    Member.path_id == state.active_path_id,
                    Message.position <= cutoff,
                ),
            )
        )
        if draft.action != "checkpoint":
            state.active_path_id = path.path_id
        return path

    async def _candidate_question(self, session, owner, target):
        recovery = await session.get(Recovery, (owner.world_id, target.turn_id))
        source_id = recovery.source_turn_id if recovery else target.turn_id
        question = await session.scalar(
            select(Message).where(
                Message.world_id == owner.world_id,
                Message.conversation_id == owner.conversation_id,
                Message.turn_id == source_id,
                Message.sender_player_id == owner.player_id,
                active_message_clause(Message),
            )
        )
        if question is None:
            raise ChatPathError("chat_path_question_required")
        source = await session.get(Turn, (owner.world_id, source_id))
        if source is None or source.kind != "player":
            raise ChatPathError("chat_path_question_required")
        return question

    async def _candidate(self, session, owner, state, draft, target, reviewed):
        question = await self._candidate_question(session, owner, target)
        source_id = question.turn_id
        path = await self._fork(session, owner, state, draft, target, question.position)
        ordinal = (
            await session.scalar(
                select(func.max(Recovery.ordinal)).where(
                    Recovery.world_id == owner.world_id, Recovery.source_turn_id == source_id
                )
            )
            or 0
        ) + 1
        turn = Turn(
            world_id=owner.world_id,
            turn_id=uuid4(),
            conversation_id=owner.conversation_id,
            request_id=uuid4(),
            fingerprint=reviewed,
            token_ceiling=draft.token_ceiling,
            kind="retry",
            status="pending",
            created_at_utc=datetime.now(UTC),
        )
        session.add(turn)
        await session.flush()
        session.add(
            Recovery(
                world_id=owner.world_id,
                turn_id=turn.turn_id,
                source_turn_id=source_id,
                ordinal=ordinal,
            )
        )
        session.add(PathTurn(world_id=owner.world_id, turn_id=turn.turn_id, path_id=path.path_id))
        return path, turn.turn_id

    async def _edit(self, session, owner, state, draft, target, reviewed):
        path = await self._fork(session, owner, state, draft, target, target.position - 1)
        turn_id = target.turn_id
        if target.sender_player_id is not None:
            turn_id = uuid4()
            session.add(
                Turn(
                    world_id=owner.world_id,
                    turn_id=turn_id,
                    conversation_id=owner.conversation_id,
                    request_id=uuid4(),
                    fingerprint=reviewed,
                    token_ceiling=draft.token_ceiling,
                    status="pending",
                    kind="player",
                    created_at_utc=datetime.now(UTC),
                )
            )
            await session.flush()
            session.add(PathTurn(world_id=owner.world_id, turn_id=turn_id, path_id=path.path_id))
        position = (
            await session.scalar(
                select(func.max(Message.position)).where(
                    Message.world_id == owner.world_id,
                    Message.conversation_id == owner.conversation_id,
                )
            )
            or 0
        ) + 1
        row = Message(
            world_id=owner.world_id,
            message_id=uuid4(),
            conversation_id=owner.conversation_id,
            turn_id=turn_id,
            position=position,
            sender_player_id=target.sender_player_id,
            sender_character_id=target.sender_character_id,
            text=draft.text,
            created_at_utc=datetime.now(UTC),
            story_sent_at_utc=target.story_sent_at_utc,
            media_json=target.media_json,
        )
        session.add(row)
        await session.flush()
        await stamp_message(session, row)
        return path, turn_id if target.sender_player_id else None

    async def commit(self, world, conversation, player, request: PathConfirm):
        fingerprint = _digest(request.model_dump(mode="json", exclude={"request_id"}))
        async with self._sessions() as session, session.begin():
            await session.connection(execution_options={"livingworld_write_intent": True})
            owner = await self._owner(session, world, conversation, player)
            previous = await session.get(Operation, request.request_id)
            if previous is not None:
                if (
                    previous.world_id != world
                    or previous.conversation_id != conversation
                    or previous.fingerprint != fingerprint
                ):
                    raise IdempotencyConflictError("chat_request_conflict")
                return json.loads(previous.result_json)
            draft = request.draft
            _, _, target, selected, reviewed = await self._prepare(session, owner, draft)
            if request.reviewed_hash != reviewed:
                raise ChatPathError("chat_path_preview_changed")
            state = await self._ensure_main(session, owner)
            turn_id = None
            if draft.action == "candidate":
                path, turn_id = await self._candidate(
                    session, owner, state, draft, target, reviewed
                )
            elif draft.action == "edit":
                path, turn_id = await self._edit(session, owner, state, draft, target, reviewed)
            elif draft.action in {"branch", "checkpoint"}:
                assert target is not None
                path = await self._fork(session, owner, state, draft, target, target.position)
            else:
                path = selected or await session.get(Path, (world, conversation))
                if draft.action == "switch":
                    state.active_path_id = path.path_id
                else:
                    path.name = draft.name.strip()
            state.revision += 1
            result = {
                "path_id": str(path.path_id),
                "revision": state.revision,
                "turn_id": str(turn_id) if turn_id else None,
            }
            session.add(
                Operation(
                    request_id=request.request_id,
                    world_id=world,
                    conversation_id=conversation,
                    fingerprint=fingerprint,
                    result_json=json.dumps(result),
                )
            )
            return result
