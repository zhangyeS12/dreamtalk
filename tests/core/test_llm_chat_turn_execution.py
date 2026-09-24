"""A chat ceiling gates each physical attempt before provider dispatch."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from livingworld.application.llm import (
    FinishReason,
    LLMAttemptSummary,
    LLMError,
    LLMErrorCode,
    LLMFailure,
    LLMUsage,
    StreamCompleted,
    StreamFailed,
    StreamStarted,
)
from livingworld.application.llm_accounting import AttemptOutcome
from livingworld.application.llm_budget import (
    BoundGuarantee,
    ModelLimitUsageBounder,
    ModelUsageLimits,
    UsageUpperBound,
)
from livingworld.application.llm_chat_turn_budget import ChatTurnTokenBudget, TurnTokenBudgetError
from livingworld.application.llm_execution import ExecutingModelGateway
from test_llm_budget import req
from test_llm_execution import ScriptedGateway, execute, failure, stream_success, success
from test_llm_routing import PROFILE, A, B, FallbackReason, registry, routed
from test_openai_compatible import request


def bounder(req, input_limit=20, output_limit=10):
    return ModelLimitUsageBounder({req.model: ModelUsageLimits(input_limit, output_limit)})


def test_untrusted_or_unaffordable_bound_blocks_before_any_provider_call():
    req = request(max_output_tokens=10)
    for bound, ceiling in ((None, 50), (bounder(req), 29)):
        provider = ScriptedGateway(success(req))
        guard = ChatTurnTokenBudget(ceiling)
        gateway = execute(provider, token_bounder=bound)
        with pytest.raises(TurnTokenBudgetError):
            asyncio.run(gateway.generate(req, turn_budget=guard))
        assert provider.requests == []
        assert guard.remaining == ceiling

    class EstimateOnly:
        def bound(self, _request):
            return UsageUpperBound(1, 1, BoundGuarantee.ESTIMATE_ONLY)

    provider = ScriptedGateway(success(req))
    with pytest.raises(TurnTokenBudgetError, match="turn_input_bound_unavailable"):
        asyncio.run(
            execute(provider, token_bounder=EstimateOnly()).generate(
                req, turn_budget=ChatTurnTokenBudget(50)
            )
        )
    assert provider.requests == []


def test_factual_usage_releases_only_unused_reservation_across_invocations():
    first = request(max_output_tokens=10)
    second = request(max_output_tokens=10)
    provider = ScriptedGateway(success(first), success(second))
    gateway = execute(provider, token_bounder=bounder(first))
    guard = ChatTurnTokenBudget(50)
    assert asyncio.run(gateway.generate(first, turn_budget=guard)).usage.total_tokens == 10
    assert guard.remaining == 40
    assert asyncio.run(gateway.generate(second, turn_budget=guard)).usage.total_tokens == 10
    assert len(provider.requests) == 2
    assert guard.remaining == 30


def test_missing_usage_consumes_reservation_and_stops_further_generation():
    req = request(max_output_tokens=10)
    provider = ScriptedGateway(replace(success(req), usage=None), success(req))
    gateway = execute(provider, token_bounder=bounder(req))
    guard = ChatTurnTokenBudget(50)
    assert asyncio.run(gateway.generate(req, turn_budget=guard)).usage is None
    assert guard.closed and guard.remaining == 20
    with pytest.raises(TurnTokenBudgetError):
        asyncio.run(gateway.generate(request(max_output_tokens=10), turn_budget=guard))
    assert len(provider.requests) == 1


def test_retryable_failure_without_factual_usage_cannot_start_second_attempt():
    req = request(max_output_tokens=10)
    provider = ScriptedGateway(failure(req), success(req))
    gateway = execute(provider, token_bounder=bounder(req))
    guard = ChatTurnTokenBudget(100)
    with pytest.raises(LLMError) as caught:
        asyncio.run(gateway.generate(req, turn_budget=guard))
    assert caught.value.failure.code is LLMErrorCode.RATE_LIMITED
    assert guard.closed
    assert len(provider.requests) == 1


def test_stream_completion_settles_latest_terminal_usage_without_double_counting():
    req = request(max_output_tokens=10, streaming=True)
    provider = ScriptedGateway(stream_success(req))
    gateway = execute(provider, token_bounder=bounder(req))
    guard = ChatTurnTokenBudget(50)

    async def collect():
        return [event async for event in gateway.stream(req, turn_budget=guard)]

    events = asyncio.run(collect())
    assert len([event for event in events if isinstance(event, StreamCompleted)]) == 1
    assert guard.remaining == 40
    assert len(provider.requests) == 1


def test_interrupted_stream_has_no_completion_and_closes_turn():
    req = request(max_output_tokens=10, streaming=True)
    provider = ScriptedGateway(
        [StreamStarted(req.invocation_id, req.model), StreamFailed(failure(req))]
    )
    guard = ChatTurnTokenBudget(50)

    async def collect():
        return [
            event
            async for event in execute(provider, token_bounder=bounder(req)).stream(
                req, turn_budget=guard
            )
        ]

    events = asyncio.run(collect())
    assert not any(isinstance(event, StreamCompleted) for event in events)
    assert guard.closed and len(provider.requests) == 1


def test_accounting_start_failure_releases_undispatched_token_reservation():
    req = request(max_output_tokens=10)
    provider = ScriptedGateway(success(req))

    class BrokenStart:
        async def start(self, _record):
            raise RuntimeError("private database detail")

    guard = ChatTurnTokenBudget(50)
    gateway = ExecutingModelGateway(
        provider,
        accounting=BrokenStart(),
        wall_clock=lambda: datetime.now(UTC),
        accounting_diagnostics=lambda _diagnostic: None,
        token_bounder=bounder(req),
    )
    with pytest.raises(Exception, match="accounting"):
        asyncio.run(gateway.generate(req, turn_budget=guard))
    assert provider.requests == []
    assert guard.remaining == 50 and not guard.closed


def test_reported_usage_above_trusted_bound_closes_turn_without_reclassifying_provider():
    req = request(max_output_tokens=10)
    over = replace(success(req), usage=LLMUsage(25, 10, 35))
    provider = ScriptedGateway(over)
    gateway = execute(provider, token_bounder=bounder(req))
    guard = ChatTurnTokenBudget(50)
    assert asyncio.run(gateway.generate(req, turn_budget=guard)) is over
    assert guard.closed and guard.remaining == 0
    assert guard.bound_violated
    assert len(provider.requests) == 1


def test_turn_bound_violation_does_not_falsely_leave_healthy_accounting_incomplete():
    req = request(max_output_tokens=10)
    over = replace(success(req), usage=LLMUsage(25, 10, 35))

    class RecordingLedger:
        def __init__(self):
            self.started = []
            self.finalized = []
            self.completed = []

        async def start(self, record):
            self.started.append(record)

        async def finalize(self, facts):
            self.finalized.append(facts)

        async def complete_invocation(self, invocation_id, outcome):
            self.completed.append((invocation_id, outcome))

    ledger = RecordingLedger()
    gateway = ExecutingModelGateway(
        ScriptedGateway(over),
        accounting=ledger,
        wall_clock=lambda: datetime.now(UTC),
        accounting_diagnostics=lambda _diagnostic: None,
        token_bounder=bounder(req),
    )
    guard = ChatTurnTokenBudget(50)
    assert asyncio.run(gateway.generate(req, turn_budget=guard)) is over
    assert guard.closed
    assert guard.bound_violated
    assert len(ledger.started) == len(ledger.finalized) == 1
    assert ledger.completed == [(req.invocation_id, AttemptOutcome.SUCCESS)]


def test_completed_failure_bound_violation_preserves_failure_and_finalizes_accounting():
    req = request(max_output_tokens=10)
    completed = LLMAttemptSummary(req.model, LLMUsage(25, 10, 35), FinishReason.STOP, 5)
    failure = LLMFailure(
        LLMErrorCode.STRUCTURED_OUTPUT_FAILED, req.invocation_id, attempt=completed
    )

    class RecordingLedger:
        def __init__(self):
            self.completed = []

        async def start(self, _record):
            pass

        async def finalize(self, _facts):
            pass

        async def complete_invocation(self, invocation_id, outcome):
            self.completed.append((invocation_id, outcome))

    ledger = RecordingLedger()
    gateway = ExecutingModelGateway(
        ScriptedGateway(failure),
        accounting=ledger,
        wall_clock=lambda: datetime.now(UTC),
        accounting_diagnostics=lambda _diagnostic: None,
        token_bounder=bounder(req),
    )
    guard = ChatTurnTokenBudget(50)
    with pytest.raises(LLMError) as caught:
        asyncio.run(gateway.generate(req, turn_budget=guard))
    assert caught.value.failure is failure
    assert guard.bound_violated
    assert ledger.completed == [(req.invocation_id, AttemptOutcome.FAILED)]


def test_routed_fallback_uses_selected_candidates_trusted_bound():
    request_a = req(model=A, max_output_tokens=10)
    response_b = success(replace(request_a, model=B))
    provider_b = ScriptedGateway(response_b)
    gateway = routed(
        {B: provider_b},
        candidates=(A, B),
        reasons=(FallbackReason.CANDIDATE_UNAVAILABLE,),
        retries=1,
    )
    guard = ChatTurnTokenBudget(150)
    assert (
        asyncio.run(gateway.generate(request_a, selection=PROFILE, turn_budget=guard)) is response_b
    )
    assert len(provider_b.requests) == 1 and provider_b.requests[0].model == B
    assert guard.remaining == 140


def test_routed_model_without_trusted_limit_is_blocked_before_provider():
    request_a = req(model=A, max_output_tokens=10)
    provider = ScriptedGateway(success(request_a))
    base = registry()
    missing = replace(
        base,
        models=(replace(base.models[0], limits=None), *base.models[1:]),
    )
    gateway = routed({A: provider}, candidates=(A,), registered=missing)
    with pytest.raises(TurnTokenBudgetError, match="turn_input_bound_unavailable"):
        asyncio.run(gateway.generate(request_a, turn_budget=ChatTurnTokenBudget(150)))
    assert provider.requests == []
