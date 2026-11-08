"""Per-attempt failure facts. Never serialize exception text, locals or dialogue."""

import asyncio
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from uuid import UUID, uuid4

STAGES = frozenset(
    {
        "request",
        "availability",
        "context",
        "journal",
        "media_context",
        "preflight",
        "claim",
        "context_report",
        "selection_context",
        "selection_generate",
        "selection_decode",
        "reply_generate",
        "reply_decode",
        "privacy",
        "media",
        "persist_reply",
        "persist_memories",
        "persist_commit",
        "character_updates",
        "deliver",
        "finish",
        "execution_finalize",
        "summary_generate",
    }
)
CODES = frozenset(
    {
        "unexpected_error",
        "request_rejected",
        "cancelled",
        "chat_reply_recovered",
        "chat_reply_segmented_compat",
        "chat_private_classification_fallback",
        "chat_annotation_discarded",
        "chat_auxiliary_failed",
        "chat_model_unavailable",
        "chat_route_deadline_exhausted",
        "chat_accounting_unavailable",
        "chat_generation_failed",
        "chat_admission_denied",
        "turn_token_limit_exceeded",
        "turn_input_bound_unavailable",
        "chat_token_limit_unverifiable",
        "chat_token_bound_violated",
        "chat_reply_invalid",
        "chat_reply_output_limit",
        "chat_reply_empty",
        "chat_reply_format_invalid",
        "group_selection_invalid",
        "group_selection_output_limit",
        "chat_send_changed",
        "chat_turn_already_claimed",
        "chat_contact_removed",
        "chat_turn_not_found",
        "conversation_not_found",
        "selected_player_required",
        "chat_request_conflict",
        "chat_recovery_not_latest",
        "chat_recovery_has_replies",
        "chat_recovery_running",
        "chat_recovery_unknown",
        "chat_recovery_unavailable",
        "chat_privacy_invalid",
        "chat_privacy_target_required",
        "chat_provider_authentication",
        "chat_provider_permission_denied",
        "chat_provider_not_found",
        "chat_provider_rate_limited",
        "chat_provider_quota_exhausted",
        "chat_provider_timeout",
        "chat_provider_context_limit",
        "chat_provider_unsupported",
        "chat_attempt_superseded",
        "chat_checkpoint_read_only",
        "chat_context_limit_exceeded",
        "chat_context_report_invalid",
        "chat_context_report_limit",
        "chat_feedback_invalid",
        "chat_feedback_message_not_found",
        "chat_generation_configuration_invalid",
        "chat_group_dissolved",
        "chat_group_reply_running",
        "chat_group_waiting_reply",
        "chat_history_query_invalid",
        "chat_history_unavailable",
        "chat_identity_conflict",
        "chat_memory_owner_invalid",
        "chat_message_invalid",
        "chat_message_not_found",
        "chat_message_source_unavailable",
        "chat_page_cursor_invalid",
        "chat_page_limit_invalid",
        "chat_path_changed",
        "chat_path_confirmation_required",
        "chat_path_media_only",
        "chat_path_message_required",
        "chat_path_name_required",
        "chat_path_not_found",
        "chat_path_preview_changed",
        "chat_path_privacy_invalid",
        "chat_path_question_required",
        "chat_path_reply_running",
        "chat_path_text_invalid",
        "chat_path_waiting_contact",
        "chat_privacy_group_required",
        "chat_recall_cursor_invalid",
        "chat_recall_result_invalid",
        "chat_recall_scope_invalid",
        "chat_recovery_changed",
        "chat_reply_conflict",
        "chat_reply_ordinal_gap",
        "chat_reply_ordinal_invalid",
        "chat_send_required",
        "chat_sender_invalid",
        "chat_state_invalid",
        "chat_token_ceiling_invalid",
        "chat_turn_claim_invalid",
        "chat_turn_order_invalid",
        "chat_turn_state_invalid",
        "chat_world_mismatch",
        "group_members_invalid",
        "group_mention_ambiguous",
        "group_participants_changed",
        "group_participants_invalid",
        "group_reply_loop_unreachable",
        "group_request_conflict",
        "group_speaker_invalid",
        "group_turn_completed",
        "group_turn_required",
        "turn_attempt_identity_invalid",
        "turn_attempt_not_active",
        "turn_token_bound_violated",
        "turn_token_budget_unavailable",
        "turn_token_limit_exhausted",
        "turn_token_limit_invalid",
        "turn_token_reservation_invalid",
        "memory_model_unavailable",
        "memory_capacity_reached",
        "memory_generation_failed",
        "memory_model_failed",
        "memory_output_invalid",
        "memory_token_bound_unavailable",
        "memory_interrupted",
        "media_caption_failed",
        "media_caption_unavailable",
    }
)
REASONS = frozenset(
    {
        "invalid_json",
        "duplicate_member",
        "non_finite",
        "invalid_envelope",
        "missing_reply",
        "invalid_reply_type",
        "empty_reply",
        "invalid_reply_text",
        "oversized_reply",
        "invalid_private_parts",
        "stream_mismatch",
        "auxiliary_discarded",
        "output_limit_recovered",
        "classification_missing_or_invalid",
        "invocation_mismatch",
        "terminal_missing",
        "first_selection_requires_speaker",
        "selection_shape_invalid",
        "selection_not_member",
        "selection_encoding_invalid",
        "selection_finish_invalid",
        "selection_oversized",
        "segmented_in_public_context",
        "events_invalid",
        "memories_invalid",
        "character_updates_invalid",
        "media_invalid",
        "private_auxiliary_ignored",
        "memory_source_not_visible",
        "json_parse_failed",
        "schema_validation_failed",
        "output_truncated",
        "empty_output",
    }
)
ERROR_TYPES = frozenset(
    {
        "UnexpectedError",
        "CancelledError",
        "GeneratorExit",
        "HTTPException",
        "RequestValidationError",
        "ChatReplyValidationError",
        "ChatReplyUnavailableError",
        "ChatReplyBudgetError",
        "ChatReplyGenerationError",
        "ChatReplyIntegrityError",
        "DialogueFormatError",
        "MediaError",
        "ConversationMemoryError",
        "BuilderError",
        "ChatTurnUnavailableError",
        "EntityNotFoundError",
        "IdempotencyConflictError",
        "RoutingError",
        "ContextCapacityError",
        "LLMError",
        "LLMContractError",
        "BudgetAdmissionError",
        "TurnTokenBudgetError",
        "BudgetIntegrityError",
        "AccountingInfrastructureError",
        "ExecutionDeadlineError",
        "IntegrityError",
        "OperationalError",
        "DatabaseError",
        "TimeoutError",
        "ConnectionError",
        "OSError",
        "ValueError",
        "TypeError",
        "KeyError",
        "AttributeError",
        "RuntimeError",
        "UnicodeEncodeError",
        "UnicodeDecodeError",
    }
)

REPLY_SHAPES = frozenset(
    {
        "reply_text",
        "reply_parts",
        "legacy_parts",
        "history_parts",
        "text_body",
        "missing_body",
        "non_object",
        "invalid_json",
        "prose",
    }
)


@dataclass
class ChatTrace:
    logger: object
    kind: str
    operation: str
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    turn_id: str | None = None
    invocation_id: str | None = None
    stage: str = "request"
    ordinal: int | None = None
    finish_reason: str | None = None
    endpoint: str | None = None
    private_context: bool | None = None
    reply_shape: str | None = None
    reported: bool = False


_TRACE: ContextVar[ChatTrace | None] = ContextVar("chat_diagnostics", default=None)


def _chain(error):
    seen = set()
    for _ in range(8):
        if error is None or id(error) in seen:
            break
        seen.add(id(error))
        yield error
        error = error.__cause__ or error.__context__


def _failure_facts(error):
    from livingworld.application.chat_event_annotations import DialogueFormatError
    from livingworld.application.llm import LLMError, LLMFailure

    facts: dict[str, object] = {"code": "unexpected_error", "error_type": "UnexpectedError"}
    name = type(error).__name__
    if name in ERROR_TYPES:
        facts["error_type"] = name
    if isinstance(error, (asyncio.CancelledError, GeneratorExit)):
        facts["code"] = "cancelled"
    # Only our fixed codes are eligible; arbitrary exception/detail text is discarded.
    elif (
        type(error).__module__ == "builtins" or type(error).__module__.startswith("livingworld.")
    ) and str(error) in CODES:
        facts["code"] = str(error)
    elif name == "HTTPException":
        detail = getattr(error, "detail", None)
        facts["code"] = (
            detail if isinstance(detail, str) and detail in CODES else "request_rejected"
        )
        status = getattr(error, "status_code", None)
        if type(status) is int and 100 <= status <= 599:
            facts["http_status"] = status
    elif name == "RequestValidationError":
        facts["code"] = "request_rejected"
        facts["http_status"] = 422
    frames = []
    for cause in _chain(error):
        if isinstance(cause, DialogueFormatError) and cause.reason in REASONS:
            facts["reason"] = cause.reason
        reason = getattr(cause, "diagnostic_reason", None)
        if reason in REASONS:
            facts["reason"] = reason
        failure = (
            cause.failure
            if isinstance(cause, LLMError)
            else getattr(cause, "diagnostic_failure", None)
        )
        if isinstance(failure, LLMFailure):
            facts["provider_code"] = failure.code.value
            facts["dispatch_state"] = failure.dispatch_state.value
            status = failure.http_status
            if status is not None:
                facts["http_status"] = status
            if failure.attempt is not None:
                facts["finish_reason"] = failure.attempt.finish_reason.value
            if failure.structured_detail is not None:
                facts["reason"] = failure.structured_detail.reason.value
        original = getattr(cause, "orig", cause)
        if isinstance(original, BaseException) and type(original).__module__ == "sqlite3":
            db_code = getattr(original, "sqlite_errorcode", None)
            if type(db_code) is int and 0 <= db_code <= 65535:
                facts["database_code"] = db_code
        tb = cause.__traceback__
        while tb is not None:
            module = tb.tb_frame.f_globals.get("__name__", "")
            function = tb.tb_frame.f_code.co_name.strip("<>")
            if (
                isinstance(module, str)
                and re.fullmatch(r"livingworld(?:\.[a-zA-Z_]\w*)+", module)
                and re.fullmatch(r"[a-zA-Z_]\w{0,95}", function)
            ):
                frames.append({"module": module, "function": function, "line": tb.tb_lineno})
            tb = tb.tb_next
    facts["frames"] = frames[-12:]
    return facts


def _emit(trace, **facts):
    try:
        emit = getattr(trace.logger, "emit_chat_diagnostic", None)
        if emit is not None:
            emit(
                kind=trace.kind,
                operation=trace.operation,
                trace_id=trace.trace_id,
                turn_id=trace.turn_id,
                invocation_id=trace.invocation_id,
                stage=trace.stage,
                ordinal=trace.ordinal,
                finish_reason=trace.finish_reason,
                endpoint=trace.endpoint,
                private_context=trace.private_context,
                reply_shape=trace.reply_shape,
                **facts,
            )
    except Exception:
        pass  # Diagnostics cannot change persistence, settlement or authorize paid replay.


def chat_failure(error):
    trace = _TRACE.get()
    if trace is None or trace.reported:
        return
    try:
        facts = _failure_facts(error)
        finish = facts.pop("finish_reason", None)
        if isinstance(finish, str):
            trace.finish_reason = finish
        _emit(trace, outcome="cancelled" if facts["code"] == "cancelled" else "failed", **facts)
    except Exception:
        pass
    trace.reported = True


def chat_warning(code, *, reason=None, error=None, stage=None):
    trace = _TRACE.get()
    if trace is None:
        return
    prior = trace.stage
    try:
        facts = _failure_facts(error) if error is not None else {}
        facts.pop("finish_reason", None)
        facts["code"] = code if code in CODES else "chat_auxiliary_failed"
        if reason is not None and reason in REASONS:
            facts["reason"] = reason
        if stage is not None:
            trace.stage = stage
        _emit(trace, outcome="warning", **facts)
    except Exception:
        pass
    finally:
        trace.stage = prior


def chat_phase(stage, *, request=None, ordinal=None):
    if (trace := _TRACE.get()) is None:
        return
    trace.stage = stage
    if request is not None:
        trace.invocation_id = str(request.invocation_id.value)
        trace.finish_reason = None
        trace.private_context = bool(request.metadata.get("chat_privacy"))
        trace.reply_shape = None
    if ordinal is not None:
        trace.ordinal = ordinal


def chat_reply_shape(shape):
    if (trace := _TRACE.get()) is not None:
        trace.reply_shape = shape


def chat_result(finish):
    if (trace := _TRACE.get()) is not None:
        trace.finish_reason = finish.value


@contextmanager
def chat_diagnostic_scope(logger, *, kind="http", operation="request", turn_id=None, endpoint=None):
    trace = _TRACE.get()
    token = None
    if trace is None:
        trace = ChatTrace(logger, kind, operation)
        token = _TRACE.set(trace)
    else:
        trace.kind, trace.operation = kind, operation
        if trace.logger is None and logger is not None:
            trace.logger = logger
    if endpoint is not None:
        trace.endpoint = endpoint
    if turn_id is not None:
        trace.turn_id = str(UUID(str(getattr(turn_id, "value", turn_id))))
    try:
        yield trace
    except BaseException as error:
        chat_failure(error)
        raise
    finally:
        if token is not None:
            _TRACE.reset(token)


def diagnosed_reply(kind):
    def decorate(reply):
        @wraps(reply)
        async def diagnosed(self, sent, **kwargs):
            with chat_diagnostic_scope(
                getattr(self, "_logger", None),
                kind=kind,
                operation="reply",
                turn_id=getattr(sent, "turn_id", None),
            ):
                return await reply(self, sent, **kwargs)

        return diagnosed

    return decorate
