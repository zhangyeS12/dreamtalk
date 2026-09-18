"""Provider-neutral sequential attempt execution. No content or credential workspace."""

import asyncio
import math
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic

from livingworld.application.llm import (
    DispatchState,
    InvocationId,
    LLMContractError,
    LLMError,
    LLMErrorCode,
    LLMFailure,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ModelGateway,
    StreamCompleted,
    StreamFailed,
    StreamStarted,
)


class JitterStrategy(StrEnum):
    FULL = "full"
    NONE = "none"


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 8.0
    max_elapsed_seconds: float = 30.0
    jitter: JitterStrategy = JitterStrategy.FULL
    retry_rate_limits: bool = True
    retry_transient_http: bool = True
    retry_not_dispatched: bool = True
    retry_http_timeouts: bool = True

    def __post_init__(self):
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise LLMContractError("invalid_max_attempts")
        for name in ("initial_backoff_seconds", "max_backoff_seconds", "max_elapsed_seconds"):
            value = getattr(self, name)
            if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
                raise LLMContractError("invalid_retry_duration")
        if self.max_elapsed_seconds <= 0 or self.max_backoff_seconds < self.initial_backoff_seconds:
            raise LLMContractError("invalid_retry_bounds")
        if not isinstance(self.jitter, JitterStrategy):
            raise LLMContractError("invalid_jitter_strategy")
        for name in (
            "retry_rate_limits",
            "retry_transient_http",
            "retry_not_dispatched",
            "retry_http_timeouts",
        ):
            if type(getattr(self, name)) is not bool:
                raise LLMContractError("invalid_retry_category")


class RetryReason(StrEnum):
    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    TRANSIENT_HTTP_FAILURE = "transient_http_failure"
    NOT_DISPATCHED_TRANSPORT_FAILURE = "not_dispatched_transport_failure"
    AMBIGUOUS_DISPATCH_NOT_REPLAYED = "ambiguous_dispatch_not_replayed"
    ATTEMPT_LIMIT_REACHED = "attempt_limit_reached"
    ELAPSED_BUDGET_EXHAUSTED = "elapsed_budget_exhausted"
    RETRY_AFTER_EXCEEDS_BUDGET = "retry_after_exceeds_budget"
    PERMANENT_FAILURE = "permanent_failure"
    STARTED_STREAM_NOT_REPLAYABLE = "started_stream_not_replayable"


@dataclass(frozen=True, slots=True)
class RetryDecision:
    retry: bool
    delay_seconds: float
    reason: RetryReason


@dataclass(frozen=True, slots=True)
class RetryRecord:
    """Closed execution diagnostics; not usage accounting or an attempt response."""

    invocation_id: InvocationId
    attempt_ordinal: int
    decision: RetryDecision
    failure_code: LLMErrorCode | None = None
    dispatch_state: DispatchState | None = None
    http_status: int | None = None


class ExponentialBackoff:
    def __init__(self, random_unit: Callable[[], float] = random.random):
        self._random_unit = random_unit

    def delay(self, policy: RetryPolicy, attempt_ordinal: int, remaining: float) -> float:
        initial, maximum = policy.initial_backoff_seconds, policy.max_backoff_seconds
        exponent = attempt_ordinal - 1
        # Avoid overflow even with a very large (finite) configured attempt count.
        if initial == 0 or maximum == 0:
            ceiling = 0.0
        elif exponent >= math.ceil(math.log2(maximum) - math.log2(initial)):
            ceiling = maximum
        else:
            ceiling = min(maximum, math.ldexp(initial, exponent))
        ceiling = min(ceiling, remaining)
        if policy.jitter is JitterStrategy.NONE:
            return ceiling
        unit = self._random_unit()
        if type(unit) not in {int, float} or not math.isfinite(unit) or not 0 <= unit <= 1:
            raise LLMContractError("invalid_jitter_sample")
        return ceiling * unit


def decide_retry(
    failure: LLMFailure,
    *,
    attempt_ordinal: int,
    elapsed_seconds: float,
    policy: RetryPolicy,
    backoff: ExponentialBackoff,
    stream_started: bool = False,
) -> RetryDecision:
    def stop(reason):
        return RetryDecision(False, 0.0, reason)

    if stream_started:
        return stop(RetryReason.STARTED_STREAM_NOT_REPLAYABLE)
    if failure.attempt is not None or failure.code not in {
        LLMErrorCode.RATE_LIMITED,
        LLMErrorCode.TIMEOUT,
        LLMErrorCode.PROVIDER_UNAVAILABLE,
    }:
        return stop(RetryReason.PERMANENT_FAILURE)
    if failure.dispatch_state is DispatchState.DISPATCHED_OR_UNKNOWN:
        return stop(RetryReason.AMBIGUOUS_DISPATCH_NOT_REPLAYED)
    reason = None
    if failure.dispatch_state is DispatchState.HTTP_RESPONSE_RECEIVED:
        if (
            failure.code is LLMErrorCode.RATE_LIMITED
            and failure.http_status == 429
            and policy.retry_rate_limits
        ):
            reason = RetryReason.RATE_LIMITED
        elif (
            failure.code is LLMErrorCode.PROVIDER_UNAVAILABLE
            and failure.http_status in {500, 502, 503, 504}
            and policy.retry_transient_http
        ):
            reason = RetryReason.TRANSIENT_HTTP_FAILURE
        elif (
            failure.code is LLMErrorCode.TIMEOUT
            and failure.http_status == 408
            and policy.retry_http_timeouts
        ):
            reason = RetryReason.TRANSIENT_HTTP_FAILURE
    elif (
        failure.code in {LLMErrorCode.TIMEOUT, LLMErrorCode.PROVIDER_UNAVAILABLE}
        and policy.retry_not_dispatched
    ):
        reason = RetryReason.NOT_DISPATCHED_TRANSPORT_FAILURE
    if reason is None:
        return stop(RetryReason.PERMANENT_FAILURE)
    if attempt_ordinal >= policy.max_attempts:
        return stop(RetryReason.ATTEMPT_LIMIT_REACHED)
    remaining = policy.max_elapsed_seconds - elapsed_seconds
    if remaining <= 0:
        return stop(RetryReason.ELAPSED_BUDGET_EXHAUSTED)
    provider_delay = failure.retry_after_seconds or 0.0
    # A new attempt must start strictly before the deadline, including a zero wait.
    if provider_delay >= remaining:
        return stop(RetryReason.RETRY_AFTER_EXCEEDS_BUDGET)
    delay = max(provider_delay, backoff.delay(policy, attempt_ordinal, remaining))
    if delay >= remaining:
        return stop(RetryReason.ELAPSED_BUDGET_EXHAUSTED)
    return RetryDecision(True, delay, reason)


class ExecutingModelGateway:
    """Borrows a single-attempt gateway; caller owns its closing lifecycle.

    The retry window includes the first attempt and all waits. It prevents new
    attempts at/after its deadline; it does not cancel an in-flight generation.
    No request replacement, background task, cumulative usage or content buffer.
    """

    def __init__(
        self,
        gateway: ModelGateway,
        *,
        policy: RetryPolicy | None = None,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_unit: Callable[[], float] = random.random,
        observer: Callable[[RetryRecord], None] | None = None,
    ):
        self._gateway = gateway
        self._policy = policy if policy is not None else RetryPolicy()
        if not isinstance(self._policy, RetryPolicy):
            raise LLMContractError("invalid_retry_policy")
        self._clock, self._sleep = clock, sleep
        self._backoff = ExponentialBackoff(random_unit)
        self._observer = observer

    def _record(self, request, ordinal, decision, failure=None):
        if self._observer is not None:
            self._observer(
                RetryRecord(
                    request.invocation_id,
                    ordinal,
                    decision,
                    failure.code if failure else None,
                    failure.dispatch_state if failure else None,
                    failure.http_status if failure else None,
                )
            )

    def _decision(self, request, ordinal, started_at, failure, *, stream_started=False):
        decision = decide_retry(
            failure,
            attempt_ordinal=ordinal,
            elapsed_seconds=self._clock() - started_at,
            policy=self._policy,
            backoff=self._backoff,
            stream_started=stream_started,
        )
        self._record(request, ordinal, decision, failure)
        return decision

    async def _wait(self, request, ordinal, started_at, decision, failure):
        await self._sleep(decision.delay_seconds)
        # A scheduler may oversleep; never dispatch using a stale pre-sleep decision.
        if self._clock() - started_at >= self._policy.max_elapsed_seconds:
            self._record(
                request,
                ordinal,
                RetryDecision(
                    False,
                    0.0,
                    RetryReason.ELAPSED_BUDGET_EXHAUSTED,
                ),
                failure,
            )
            return False
        return True

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started_at = self._clock()
        for ordinal in range(1, self._policy.max_attempts + 1):
            failure = None
            try:
                result = await self._gateway.generate(request)
            except LLMError as error:
                failure = error.failure
            if failure is None:
                self._record(request, ordinal, RetryDecision(False, 0.0, RetryReason.SUCCESS))
                return result
            decision = self._decision(request, ordinal, started_at, failure)
            if not decision.retry or not await self._wait(
                request,
                ordinal,
                started_at,
                decision,
                failure,
            ):
                # Outside the exception handler: do not retain the attempt's traceback/context.
                raise LLMError(failure)
        raise AssertionError("retry_loop_unreachable")

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        started_at = self._clock()
        stream_started = False
        for ordinal in range(1, self._policy.max_attempts + 1):
            failure = None
            try:
                async with aclosing(self._gateway.stream(request)) as events:
                    async for event in events:
                        if isinstance(event, StreamFailed):
                            failure = event.failure
                            break
                        if isinstance(event, StreamStarted):
                            if stream_started:
                                raise LLMContractError("duplicate_stream_started")
                            stream_started = True
                        elif not stream_started:
                            raise LLMContractError("stream_event_before_started")
                        if isinstance(event, StreamCompleted):
                            self._record(
                                request,
                                ordinal,
                                RetryDecision(
                                    False,
                                    0.0,
                                    RetryReason.SUCCESS,
                                ),
                            )
                            yield event
                            return
                        yield event
            except LLMError as error:
                failure = error.failure
            if failure is None:
                raise LLMContractError("stream_missing_terminal")
            decision = self._decision(
                request,
                ordinal,
                started_at,
                failure,
                stream_started=stream_started,
            )
            if not decision.retry or not await self._wait(
                request,
                ordinal,
                started_at,
                decision,
                failure,
            ):
                yield StreamFailed(failure)
                return
        raise AssertionError("retry_loop_unreachable")
