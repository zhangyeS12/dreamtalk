"""One player-initiated turn's conservative physical-attempt token ceiling."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from livingworld.application.llm import LLMUsage, ReasoningTokenRelation


class TurnTokenBudgetError(ValueError):
    """A new provider attempt cannot be authorized inside this turn."""


class TurnTokenBoundViolation(TurnTokenBudgetError):
    """Reported usage exceeded the trusted reservation; further attempts stop."""


@dataclass(frozen=True, slots=True)
class TokenReservation:
    attempt_id: UUID
    input_upper_bound: int
    max_output_tokens: int

    @property
    def total(self) -> int:
        return self.input_upper_bound + self.max_output_tokens


class ChatTurnTokenBudget:
    """Sequential attempts share one ceiling, including retries and route fallbacks.

    The caller must supply a trusted upper bound for the selected model's full
    request (including provider message framing). This object does not guess a
    token count from text. `reserve` must run before accounting START/dispatch.
    """

    def __init__(self, limit: int) -> None:
        if type(limit) is not int or limit < 1:
            raise TurnTokenBudgetError("turn_token_limit_invalid")
        self._limit = limit
        self._spent = 0
        self._active: TokenReservation | None = None
        self._closed = False
        self._seen: set[UUID] = set()

    @property
    def remaining(self) -> int:
        return self._limit - self._spent - (self._active.total if self._active else 0)

    @property
    def closed(self) -> bool:
        return self._closed

    def reserve(
        self,
        attempt_id: UUID,
        *,
        input_upper_bound: int | None,
        max_output_tokens: int,
    ) -> TokenReservation:
        if self._closed or self._active is not None:
            raise TurnTokenBudgetError("turn_token_budget_unavailable")
        if not isinstance(attempt_id, UUID) or attempt_id in self._seen:
            raise TurnTokenBudgetError("turn_attempt_identity_invalid")
        if input_upper_bound is None:
            raise TurnTokenBudgetError("turn_input_bound_unavailable")
        if (
            type(input_upper_bound) is not int
            or input_upper_bound < 0
            or type(max_output_tokens) is not int
            or max_output_tokens < 1
        ):
            raise TurnTokenBudgetError("turn_token_reservation_invalid")
        reservation = TokenReservation(attempt_id, input_upper_bound, max_output_tokens)
        if reservation.total > self.remaining:
            raise TurnTokenBudgetError("turn_token_limit_exhausted")
        self._active = reservation
        self._seen.add(attempt_id)
        return reservation

    def release_undispatched(self, attempt_id: UUID) -> None:
        """Only safe before any provider exposure, e.g. accounting START denial."""
        self._require_active(attempt_id)
        self._active = None

    def settle(self, attempt_id: UUID, usage: LLMUsage | None) -> int:
        """Charge factual input+output; incomplete facts consume and close the turn."""
        reservation = self._require_active(attempt_id)
        self._active = None
        if usage is None or usage.input_tokens is None or usage.output_tokens is None:
            self._spent += reservation.total
            self._closed = True
            return self.remaining
        parts = usage.input_tokens + usage.output_tokens
        if (
            usage.reasoning_output_tokens is not None
            and usage.reasoning_token_relation is not ReasoningTokenRelation.INCLUDED_IN_OUTPUT
        ):
            # UNKNOWN is charged conservatively until provider semantics are known.
            parts += usage.reasoning_output_tokens
        factual = max(parts, usage.total_tokens or 0)
        if factual > reservation.total:
            self._spent = self._limit
            self._closed = True
            raise TurnTokenBoundViolation("turn_token_bound_violated")
        self._spent += factual
        return self.remaining

    def _require_active(self, attempt_id: UUID) -> TokenReservation:
        if self._active is None or self._active.attempt_id != attempt_id:
            raise TurnTokenBudgetError("turn_attempt_not_active")
        return self._active
