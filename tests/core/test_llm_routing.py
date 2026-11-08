"""Offline routing invariants: identities, deadline, dispatch, spend and stream locks."""

import ast
import asyncio
import json
from contextlib import aclosing
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
from uuid import UUID

import pytest
from livingworld.application.llm import (
    DispatchState,
    FinishReason,
    LLMAttemptSummary,
    LLMContractError,
    LLMError,
    LLMErrorCode,
    LLMPurpose,
    LLMUsage,
    ModelCapabilities,
    ModelRef,
    ProviderId,
    StreamCompleted,
    StreamFailed,
    StreamOutcome,
    StreamStarted,
    StructuredFailureDetail,
    StructuredFailureReason,
    StructuredOutputMode,
    StructuredOutputRequest,
    TextDelta,
)
from livingworld.application.llm_accounting import (
    AccountingInfrastructureError,
    AttemptOutcome,
    AttemptStart,
    LedgerQuery,
    summarize,
)
from livingworld.application.llm_budget import (
    BudgetAdmissionError,
    BudgetAdmissionFact,
    BudgetAdmissionSummary,
    BudgetId,
    BudgetIntegrityError,
    BudgetReason,
    BudgetScope,
    ModelUsageLimits,
    ReservationStatus,
)
from livingworld.application.llm_execution import (
    ExecutionDeadlineError,
    JitterStrategy,
    RetryPolicy,
)
from livingworld.application.llm_pricing import (
    InMemoryPricingCatalog,
    Meter,
    Money,
    PricingVariant,
    RateLine,
)
from livingworld.application.llm_registry import (
    AdapterKind,
    ModelRegistry,
    RegisteredModel,
    RegisteredProvider,
)
from livingworld.application.llm_routing import (
    ConfiguredGateways,
    ExplicitModelSelection,
    FallbackReason,
    ProfileSelection,
    PurposePolicy,
    RoutedModelGateway,
    RouteIssue,
    RoutePolicy,
    RoutePolicyId,
    RouteRequirements,
    RoutingConfiguration,
    RoutingError,
    RoutingEvent,
    RoutingProfile,
    budget_fallback_reason,
)
from livingworld.infrastructure.llm.fake import FakeModelGateway
from test_llm_accounting import AT, database_run, schedule
from test_llm_budget import D, counts, policy, req
from test_llm_execution import ScriptedGateway, VirtualTime, failure, stream_success, success
from test_openai_compatible import CANARY, PROMPT, REASONING, RESPONSE

A = ModelRef(ProviderId("openai-main"), "opaque-A")
B = ModelRef(ProviderId("deepseek-main"), "opaque-B")
C = ModelRef(ProviderId("local-lmstudio"), "opaque-C")
PROFILE = ProfileSelection(RoutingProfile.BALANCED)
CAPS = ModelCapabilities(text_generation=True, streaming=True)


def registry(*, overrides=None):
    overrides = overrides or {}
    return ModelRegistry(
        tuple(RegisteredProvider(m.provider_id, AdapterKind.OPENAI_COMPATIBLE) for m in (A, B, C)),
        tuple(
            overrides.get(
                m,
                RegisteredModel(
                    model=m, enabled=True, capabilities=CAPS, limits=ModelUsageLimits(100, 100)
                ),
            )
            for m in (A, B, C)
        ),
    )


def route_policy(candidates=(A, B, C), reasons=()):
    return RoutePolicy(RoutePolicyId("configured-order"), candidates, frozenset(reasons))


def configuration(candidates=(A, B, C), reasons=()):
    return RoutingConfiguration(
        (PurposePolicy(RoutingProfile.BALANCED, route_policy(candidates, reasons)),)
    )


def routed(
    gateways,
    *,
    candidates=(A, B, C),
    reasons=(),
    time=None,
    retries=2,
    trace=None,
    records=None,
    registered=None,
    **options,
):
    time = time or VirtualTime()
    return RoutedModelGateway(
        registered or registry(),
        configuration(candidates, reasons),
        ConfiguredGateways(gateways),
        policy=RetryPolicy(
            max_attempts=retries,
            initial_backoff_seconds=0.5,
            max_backoff_seconds=8,
            max_elapsed_seconds=10,
            jitter=JitterStrategy.NONE,
        ),
        clock=time.clock,
        sleep=time.sleep,
        observer=trace.append if trace is not None else None,
        retry_observer=records.append if records is not None else None,
        **options,
    )


def test_registry_instance_identity_exact_lookup_and_immutability():
    r = registry()
    assert len({p.provider_id for p in r.providers}) == 3
    assert {p.adapter_kind for p in r.providers} == {AdapterKind.OPENAI_COMPATIBLE}
    assert r.lookup(A).model == A and r.provider(B.provider_id).provider_id == B.provider_id
    assert r.lookup(ModelRef(A.provider_id, "opaque-B")) is None
    assert r.lookup(ModelRef(ProviderId("openai-compatible"), A.model_id)) is None
    assert r.capabilities(A) == CAPS
    assert r.usage_bounder().bound(req(model=A)).input_tokens == 100
    assert r.pricing_envelopes() == ()
    with pytest.raises(FrozenInstanceError):
        r.models = ()
    with pytest.raises(LLMContractError):
        ModelRegistry(r.providers, r.models + (r.models[0],))


@pytest.mark.parametrize("kind", [AdapterKind.ANTHROPIC, AdapterKind.GEMINI])
def test_future_adapter_kind_needs_no_routing_or_accounting_contract_change(kind):
    r = replace(
        registry(), providers=(RegisteredProvider(A.provider_id, kind), *registry().providers[1:])
    )
    router = routed({A: FakeModelGateway()}, registered=r)
    assert asyncio.run(router.generate(req(model=A))).model_used == A


def test_profile_order_is_configuration_defined_and_exact_purpose_precedes_default():
    purpose = LLMPurpose("open-purpose-identity")
    cfg = RoutingConfiguration(
        tuple(
            PurposePolicy(profile, route_policy(order))
            for profile, order in (
                (RoutingProfile.FAST, (C, B, A)),
                (RoutingProfile.BALANCED, (B, A, C)),
                (RoutingProfile.BEST, (A, C, B)),
            )
        )
        + (PurposePolicy(RoutingProfile.BALANCED, route_policy((C, A)), purpose),)
    )
    router = RoutedModelGateway(registry(), cfg, ConfiguredGateways({}))
    request = req(model=A)
    for profile, order in (
        (RoutingProfile.FAST, (C, B, A)),
        (RoutingProfile.BALANCED, (B, A, C)),
        (RoutingProfile.BEST, (A, C, B)),
    ):
        plan = router.plan(request, selection=ProfileSelection(profile))
        assert plan == router.plan(request, selection=ProfileSelection(profile))
        assert plan.candidates == order
        with pytest.raises(FrozenInstanceError):
            plan.candidates = ()
    assert router.plan(replace(request, purpose=purpose), selection=PROFILE).candidates == (C, A)
    empty = RoutedModelGateway(registry(), RoutingConfiguration(), ConfiguredGateways({}))
    with pytest.raises(RoutingError, match="routing_policy_missing"):
        empty.plan(request, selection=PROFILE)


def test_controlled_three_provider_instances_use_same_family_and_real_fake_contract():
    async def run():
        for model in (A, B, C):
            router = routed(
                {
                    m: FakeModelGateway(chunks=(m.model_id,), usage=LLMUsage(7, 3, 10))
                    for m in (A, B, C)
                }
            )
            request = req(model=model)
            result = await router.generate(request)
            assert result.model_used == model and result.text == model.model_id
            async with aclosing(router.stream(replace(request, streaming=True))) as events:
                seen = [event async for event in events]
            assert sum(isinstance(e, StreamStarted) for e in seen) == 1
            assert sum(isinstance(e, StreamCompleted) for e in seen) == 1
            assert "".join(e.text for e in seen if isinstance(e, TextDelta)) == model.model_id

    asyncio.run(run())


@pytest.mark.parametrize(
    "issue",
    [RouteIssue.MODEL_DISABLED, RouteIssue.CAPABILITY_MISMATCH, RouteIssue.MODEL_UNREGISTERED],
)
def test_capability_and_status_filters_are_pre_execution(issue):
    entry = RegisteredModel(
        model=A,
        enabled=issue is not RouteIssue.MODEL_DISABLED,
        capabilities=ModelCapabilities() if issue is RouteIssue.CAPABILITY_MISMATCH else CAPS,
    )
    r = registry(overrides={A: entry})
    if issue is RouteIssue.MODEL_UNREGISTERED:
        r = replace(r, models=r.models[1:])
    request = req(model=A)
    a, b = ScriptedGateway(success(request)), ScriptedGateway(success(replace(request, model=B)))
    router = routed({A: a, B: b}, registered=r)
    plan = router.plan(request, selection=PROFILE)
    assert plan.candidates == (B, C) and plan.skipped[0].issue == issue
    assert asyncio.run(router.generate(request, selection=PROFILE)).model_used == B
    assert a.requests == []
    with pytest.raises(RoutingError) as rejected:
        asyncio.run(router.generate(request))
    assert rejected.value.issue == issue


def test_stream_and_typed_structured_modes_filter_without_guessing_model_name():
    r = registry(
        overrides={
            A: RegisteredModel(
                model=A,
                enabled=True,
                capabilities=ModelCapabilities(text_generation=True, structured_output=True),
            ),
            B: RegisteredModel(
                model=B,
                enabled=True,
                capabilities=ModelCapabilities(
                    text_generation=True,
                    streaming=True,
                    structured_output=True,
                    structured_output_mode=StructuredOutputMode.JSON_OBJECT_LOCAL_VALIDATE,
                ),
            ),
            C: RegisteredModel(
                model=C,
                enabled=True,
                capabilities=ModelCapabilities(
                    text_generation=True,
                    streaming=True,
                    structured_output=True,
                    structured_output_mode=StructuredOutputMode.NATIVE_JSON_SCHEMA,
                ),
            ),
        }
    )
    router = routed({}, registered=r)
    request = req(model=A)
    assert router.plan(replace(request, streaming=True), selection=PROFILE).candidates == (B, C)
    structured = replace(
        request, structured_output=StructuredOutputRequest("safe", {"type": "object"})
    )
    assert router.plan(structured, selection=PROFILE).candidates == (B, C)
    native = RouteRequirements(
        structured_modes=frozenset({StructuredOutputMode.NATIVE_JSON_SCHEMA})
    )
    assert router.plan(structured, selection=PROFILE, requirements=native).candidates == (C,)
    with pytest.raises(RoutingError, match="structured_stream_unsupported"):
        router.plan(replace(structured, streaming=True), selection=PROFILE)
    with pytest.raises(LLMContractError, match="requirements_must_match_request"):
        router.plan(request, selection=PROFILE, requirements=native)
    # Implementation uses explicit typed declarations, not string/model-name heuristics.
    path = Path(__file__).resolve().parents[2] / "services/core/src/livingworld/application"
    for name in ("llm_registry.py", "llm_routing.py"):
        tree = ast.parse((path / name).read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and any(
                isinstance(op, (ast.In, ast.NotIn)) for op in node.ops
            ):
                assert not any(
                    isinstance(part, ast.Constant) and part.value in {"gpt", "claude", "deepseek"}
                    for part in ast.walk(node)
                )


def test_exact_selection_does_not_follow_profile_but_explicit_chain_can_fallback():
    request = req(model=A)
    a = ScriptedGateway(failure(request), failure(request), failure(request), failure(request))
    b = ScriptedGateway(success(replace(request, model=B)))
    router = routed({A: a, B: b}, reasons=(FallbackReason.RATE_LIMITED,))
    with pytest.raises(LLMError):
        asyncio.run(router.generate(request))
    assert len(a.requests) == 2 and b.requests == []
    selected = ExplicitModelSelection(A, route_policy((A, B), (FallbackReason.RATE_LIMITED,)))
    assert asyncio.run(router.generate(request, selection=selected)).model_used == B
    with pytest.raises(LLMContractError, match="explicit_selection_must_be_primary"):
        ExplicitModelSelection(A, route_policy((B, A)))


def test_missing_gateway_is_local_configuration_and_skip_requires_explicit_policy():
    request = req(model=A)
    b = ScriptedGateway(success(replace(request, model=B)))
    router = routed({B: b})
    for selection in (None, PROFILE):
        with pytest.raises(RoutingError, match="candidate_unavailable"):
            asyncio.run(router.generate(request, selection=selection))
    assert b.requests == []
    trace = []
    allowed = routed({B: b}, reasons=(FallbackReason.CANDIDATE_UNAVAILABLE,), trace=trace)
    assert asyncio.run(allowed.generate(request, selection=PROFILE)).model_used == B
    assert any(t.event is RoutingEvent.SKIPPED and t.candidate == A for t in trace)


def test_gateway_resolution_failure_is_safe_local_unavailability():
    request = req(model=A)

    class BrokenResolver:
        def gateway(self, model):
            if model == A:
                raise RuntimeError(CANARY)
            return FakeModelGateway()

    exact = RoutedModelGateway(registry(), configuration(), BrokenResolver())
    with pytest.raises(RoutingError) as error:
        asyncio.run(exact.generate(request))
    assert error.value.issue is RouteIssue.CANDIDATE_UNAVAILABLE
    assert CANARY not in repr(error.value) and error.value.__context__ is None

    allowed = RoutedModelGateway(
        registry(),
        configuration(reasons=(FallbackReason.CANDIDATE_UNAVAILABLE,)),
        BrokenResolver(),
    )
    assert asyncio.run(allowed.generate(request, selection=PROFILE)).model_used == B


@pytest.mark.parametrize(
    "code,status,dispatch,reason",
    [
        (
            LLMErrorCode.RATE_LIMITED,
            429,
            DispatchState.HTTP_RESPONSE_RECEIVED,
            FallbackReason.RATE_LIMITED,
        ),
        (
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            503,
            DispatchState.HTTP_RESPONSE_RECEIVED,
            FallbackReason.TRANSIENT_HTTP_FAILURE,
        ),
        (
            LLMErrorCode.TIMEOUT,
            408,
            DispatchState.HTTP_RESPONSE_RECEIVED,
            FallbackReason.TRANSIENT_HTTP_FAILURE,
        ),
        (LLMErrorCode.TIMEOUT, None, DispatchState.NOT_DISPATCHED, FallbackReason.NOT_DISPATCHED),
    ],
)
def test_fallback_after_candidate_retries_preserves_semantic_payload_and_identity(
    code, status, dispatch, reason
):
    request = req(model=A, stop_sequences=("private-stop",), metadata={"meaning": "private-meta"})
    f = failure(request, code, status, dispatch_state=dispatch)
    a, b = ScriptedGateway(f, f), ScriptedGateway(success(replace(request, model=B)))
    router = routed({A: a, B: b}, reasons=(reason,))
    result = asyncio.run(router.generate(request, selection=PROFILE))
    assert result.model_used == B and result.invocation_id == request.invocation_id
    assert len(a.requests) == 2 and len(b.requests) == 1
    for actual in a.requests + b.requests:
        assert replace(actual, model=A) == request
        assert (
            actual.messages is request.messages
            and actual.structured_output is request.structured_output
        )


@pytest.mark.parametrize(
    "kind",
    ["unknown", "auth", "invalid", "malformed", "501", "parse", "schema", "empty", "truncated"],
)
def test_unsafe_or_completed_generation_failures_never_change_provider(kind):
    request = req(model=A)
    if kind == "unknown":
        f = failure(
            request, LLMErrorCode.TIMEOUT, None, dispatch_state=DispatchState.DISPATCHED_OR_UNKNOWN
        )
    elif kind in {"parse", "schema", "empty", "truncated"}:
        reason = {
            "parse": StructuredFailureReason.JSON_PARSE_FAILED,
            "schema": StructuredFailureReason.SCHEMA_VALIDATION_FAILED,
            "empty": StructuredFailureReason.EMPTY_OUTPUT,
            "truncated": StructuredFailureReason.OUTPUT_TRUNCATED,
        }[kind]
        f = failure(
            request,
            LLMErrorCode.STRUCTURED_OUTPUT_FAILED,
            None,
            attempt=LLMAttemptSummary(
                A,
                LLMUsage(7, 3, 10),
                FinishReason.OUTPUT_LIMIT if kind == "truncated" else FinishReason.STOP,
                10,
            ),
            structured_detail=StructuredFailureDetail(reason),
        )
    else:
        f = failure(
            request,
            {
                "auth": LLMErrorCode.AUTHENTICATION,
                "invalid": LLMErrorCode.INVALID_REQUEST,
                "malformed": LLMErrorCode.MALFORMED_RESPONSE,
                "501": LLMErrorCode.PROVIDER_UNAVAILABLE,
            }[kind],
            501 if kind == "501" else None,
        )
    a, b = ScriptedGateway(f), ScriptedGateway(success(replace(request, model=B)))
    router = routed({A: a, B: b}, reasons=tuple(FallbackReason))
    with pytest.raises(LLMError) as error:
        asyncio.run(router.generate(request, selection=PROFILE))
    assert error.value.failure is f and len(a.requests) == 1 and b.requests == []


@pytest.mark.parametrize("finish", [FinishReason.STOP, FinishReason.REFUSAL])
def test_success_and_refusal_are_terminal_original_objects(finish):
    request = req(model=A)
    response = success(request, finish)
    a, b = ScriptedGateway(response), ScriptedGateway(success(replace(request, model=B)))
    assert (
        asyncio.run(
            routed({A: a, B: b}, reasons=tuple(FallbackReason)).generate(request, selection=PROFILE)
        )
        is response
    )
    assert b.requests == []


def test_global_attempt_ordinal_and_accounting_one_logical_terminal(tmp_path):
    async def run(db):
        request = req(model=A)
        a, b = (
            ScriptedGateway(failure(request), failure(request)),
            ScriptedGateway(success(replace(request, model=B))),
        )
        ledger = db.llm_usage_ledger()
        records = []
        time = VirtualTime()
        # Retry observer belongs to execution; routing observer is separate.
        router = RoutedModelGateway(
            registry(),
            configuration(reasons=(FallbackReason.RATE_LIMITED,)),
            ConfiguredGateways({A: a, B: b}),
            policy=RetryPolicy(max_attempts=2, jitter=JitterStrategy.NONE),
            clock=time.clock,
            sleep=time.sleep,
            retry_observer=records.append,
            accounting=ledger,
            wall_clock=lambda: AT,
            accounting_diagnostics=lambda d: None,
        )
        result = await router.generate(request, selection=PROFILE)
        rows = await ledger.query(LedgerQuery(invocation_id=request.invocation_id))
        assert [r.start.attempt_ordinal for r in rows] == [1, 2, 3]
        assert [r.start.requested_model for r in rows] == [A, A, B]
        assert {r.start.invocation_id for r in rows} == {request.invocation_id}
        assert [r.invocation_outcome for r in rows] == [None, None, AttemptOutcome.SUCCESS]
        assert [r.attempt_ordinal for r in records] == [1, 2, 3]
        assert (
            summarize(rows).attempt_count == 3
            and summarize(rows).final_outcome is AttemptOutcome.SUCCESS
        )
        assert result.model_used == B

    asyncio.run(database_run(tmp_path, run))


class TimedGateway(ScriptedGateway):
    def __init__(self, time, durations, *actions):
        super().__init__(*actions)
        self.time, self.durations = time, list(durations)

    async def generate(self, request):
        self.time.value += self.durations.pop(0)
        return await super().generate(request)


def test_fallback_does_not_reset_deadline_or_cancel_already_dispatched_success():
    request, time = req(model=A), VirtualTime()
    a = TimedGateway(time, (4, 4), failure(request), failure(request))
    b = TimedGateway(time, (1, 1), failure(request), success(replace(request, model=B)))
    router = routed(
        {A: a, B: b},
        candidates=(A, B),
        time=time,
        reasons=(FallbackReason.RATE_LIMITED,),
    )
    with pytest.raises(LLMError):
        asyncio.run(router.generate(request, selection=PROFILE))
    assert len(a.requests) == 2 and len(b.requests) == 1 and time.value == 19.5
    assert time.waits == [0.5]  # B has its own retry count, but no route time remains.
    time = VirtualTime()
    response = success(request)
    a = TimedGateway(time, (100,), response)
    assert asyncio.run(routed({A: a}, time=time).generate(request, selection=PROFILE)) is response


def test_deadline_expiry_during_failure_prevents_next_candidate():
    request, time = req(model=A), VirtualTime()
    a = TimedGateway(time, (10,), failure(request))
    b = ScriptedGateway(success(replace(request, model=B)))
    with pytest.raises(LLMError):
        asyncio.run(
            routed({A: a, B: b}, time=time, reasons=(FallbackReason.RATE_LIMITED,)).generate(
                request, selection=PROFILE
            )
        )
    assert b.requests == []


def test_long_retry_after_stops_only_current_candidate():
    request, time = req(model=A), VirtualTime()
    a = ScriptedGateway(failure(request, retry_after_seconds=100))
    b = ScriptedGateway(success(replace(request, model=B)))
    assert (
        asyncio.run(
            routed({A: a, B: b}, time=time, reasons=(FallbackReason.RATE_LIMITED,)).generate(
                request, selection=PROFILE
            )
        ).model_used
        == B
    )
    assert len(a.requests) == 1 and len(b.requests) == 1 and time.waits == []


def test_expiry_while_resolving_gateway_never_starts_attempt():
    request, time = req(model=A), VirtualTime()
    a = ScriptedGateway(success(request))

    class Resolver:
        def gateway(self, model):
            time.value += 10
            return a

    router = RoutedModelGateway(
        registry(),
        configuration(),
        Resolver(),
        clock=time.clock,
        policy=RetryPolicy(max_elapsed_seconds=10),
    )
    with pytest.raises(ExecutionDeadlineError):
        asyncio.run(router.generate(request, selection=PROFILE))
    assert a.requests == []


def test_stream_can_fallback_only_before_started_without_duplicate_visible_lifecycle():
    async def run():
        request = req(model=A, streaming=True)
        a = ScriptedGateway([StreamFailed(failure(request))], [StreamFailed(failure(request))])
        b = ScriptedGateway(stream_success(replace(request, model=B)))
        async with aclosing(
            routed({A: a, B: b}, reasons=(FallbackReason.RATE_LIMITED,)).stream(
                request, selection=PROFILE
            )
        ) as events:
            seen = [e async for e in events]
        assert sum(isinstance(e, StreamStarted) for e in seen) == 1
        assert sum(isinstance(e, StreamCompleted) for e in seen) == 1
        assert not any(isinstance(e, StreamFailed) for e in seen)
        assert "".join(e.text for e in seen if isinstance(e, TextDelta)) == RESPONSE
        assert a.closed == [1, 2] and b.closed == [1]

    asyncio.run(run())


@pytest.mark.parametrize("partial", [False, True])
def test_stream_started_permanently_locks_route(partial):
    async def run():
        request = req(model=A, streaming=True)
        a = ScriptedGateway(
            [
                StreamStarted(request.invocation_id, A),
                *([TextDelta(request.invocation_id, RESPONSE)] if partial else []),
                StreamFailed(failure(request)),
            ]
        )
        b = ScriptedGateway(stream_success(replace(request, model=B)))
        async with aclosing(
            routed({A: a, B: b}, reasons=tuple(FallbackReason)).stream(request, selection=PROFILE)
        ) as events:
            seen = [e async for e in events]
        assert isinstance(seen[-1], StreamFailed)
        assert not any(isinstance(e, StreamCompleted) for e in seen)
        assert len(a.requests) == 1 and b.requests == [] and a.closed == [1]

    asyncio.run(run())


@pytest.mark.parametrize("outcome", [StreamOutcome.REFUSAL, StreamOutcome.CONTENT_FILTERED])
def test_stream_refusal_and_filter_are_success_terminal(outcome):
    async def run():
        request = req(model=A, streaming=True)
        a = ScriptedGateway(stream_success(request, finish=FinishReason.REFUSAL, result=outcome))
        b = ScriptedGateway(stream_success(replace(request, model=B)))
        async with aclosing(
            routed({A: a, B: b}, reasons=tuple(FallbackReason)).stream(request, selection=PROFILE)
        ) as events:
            seen = [e async for e in events]
        assert seen[-1].completion.outcome is outcome and b.requests == []
        assert not any(isinstance(e, TextDelta) for e in seen)

    asyncio.run(run())


@pytest.mark.parametrize("streaming", [False, True])
def test_cancellation_no_fallback_and_closes_iterator(streaming):
    async def run():
        request = req(model=A, streaming=streaming)
        entered = asyncio.Event()

        class BlockingGateway:
            closed = False

            async def generate(self, request):
                entered.set()
                await asyncio.Event().wait()

            async def stream(self, request):
                try:
                    entered.set()
                    await asyncio.Event().wait()
                    yield
                finally:
                    self.closed = True

        a, b = BlockingGateway(), ScriptedGateway(success(replace(request, model=B)))
        router = routed({A: a, B: b}, reasons=tuple(FallbackReason))

        async def consume():
            if streaming:
                async with aclosing(router.stream(request, selection=PROFILE)) as events:
                    return [e async for e in events]
            return await router.generate(request, selection=PROFILE)

        task = asyncio.create_task(consume())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert b.requests == []
        assert a.closed is streaming

    asyncio.run(run())


def test_safe_route_diagnostics_have_no_private_payload_fields():
    request = req(model=A, metadata={"private": CANARY}, stop_sequences=(REASONING,))
    trace = []
    a, b = (
        ScriptedGateway(failure(request), failure(request)),
        ScriptedGateway(success(replace(request, model=B))),
    )
    result = asyncio.run(
        routed({A: a, B: b}, reasons=(FallbackReason.RATE_LIMITED,), trace=trace).generate(
            request, selection=PROFILE
        )
    )
    wire = json.dumps([asdict(t) for t in trace], default=str) + repr(trace)
    for canary in (PROMPT, RESPONSE, REASONING, CANARY):
        assert canary not in wire
    assert any(t.event is RoutingEvent.FALLBACK and t.hop_count == 1 for t in trace)
    assert trace[-1].event is RoutingEvent.TERMINAL and trace[-1].candidate == result.model_used


class FailingAccounting:
    def __init__(self, failure_at):
        self.failure_at = failure_at
        self.started, self.finished = [], []

    async def start(self, record):
        if self.failure_at == "start":
            raise RuntimeError(CANARY)
        self.started.append(record)

    async def finalize(self, facts):
        if self.failure_at == "finalize":
            raise RuntimeError(PROMPT)
        if self.failure_at == "bound":
            raise BudgetIntegrityError("budget_bound_violation")
        self.finished.append(facts)

    async def complete_invocation(self, invocation_id, outcome):
        if self.failure_at == "terminal":
            raise RuntimeError(RESPONSE)


@pytest.mark.parametrize("stage", ["start", "finalize", "bound"])
def test_accounting_or_budget_integrity_never_fallback(stage):
    request = req(model=A)
    a, b = ScriptedGateway(failure(request)), ScriptedGateway(success(replace(request, model=B)))
    diagnostics = []
    router = routed(
        {A: a, B: b},
        reasons=tuple(FallbackReason),
        accounting=FailingAccounting(stage),
        wall_clock=lambda: AT,
        accounting_diagnostics=diagnostics.append,
    )
    with pytest.raises(AccountingInfrastructureError if stage == "start" else LLMError):
        asyncio.run(router.generate(request, selection=PROFILE))
    assert len(a.requests) == (0 if stage == "start" else 1) and b.requests == []
    assert CANARY not in repr(diagnostics) and PROMPT not in repr(diagnostics)


def test_accounting_degraded_success_still_returns_original_result():
    request = req(model=A)
    response = success(request)
    a, b = ScriptedGateway(response), ScriptedGateway(success(replace(request, model=B)))
    router = routed(
        {A: a, B: b},
        reasons=tuple(FallbackReason),
        accounting=FailingAccounting("finalize"),
        wall_clock=lambda: AT,
        accounting_diagnostics=lambda d: None,
    )
    assert asyncio.run(router.generate(request, selection=PROFILE)) is response and b.requests == []


def prices():
    return InMemoryPricingCatalog(
        tuple(
            schedule(
                model,
                variants=(
                    PricingVariant(
                        variant_id="controlled", rates=(RateLine(Meter.OUTPUT, D(rate), 1),)
                    ),
                ),
            )
            for model, rate in ((A, "0.08"), (B, "0.02"), (C, "0.01"))
        )
    )


@pytest.mark.parametrize("scope", ["global", "purpose", "model"])
def test_budget_denied_candidate_can_fallback_with_full_fresh_atomic_admission(tmp_path, scope):
    async def run(db):
        request = req(model=A, max_output_tokens=1)
        p = policy(
            limit=Money("USD", D("0.04")),
            **(
                {"purpose": request.purpose}
                if scope == "purpose"
                else {"model": A}
                if scope == "model"
                else {}
            ),
        )
        guard = db.llm_budget_guard(
            bounder=registry().usage_bounder(), catalog=prices(), diagnostics=lambda d: None
        )
        await guard.put_policy(p, None)
        a, b = (
            ScriptedGateway(success(request)),
            ScriptedGateway(success(replace(request, model=B))),
        )
        # Match output usage to the trusted cap to avoid an unrelated bound violation.
        b.attempts[0] = replace(b.attempts[0], usage=LLMUsage(7, 1, 8))
        reasons = (FallbackReason.BUDGET_EXCEEDED,)
        trace = []
        result = await routed(
            {A: a, B: b},
            reasons=reasons,
            trace=trace,
            budget_guard=guard,
            wall_clock=lambda: AT,
            accounting_diagnostics=lambda d: None,
        ).generate(request, selection=PROFILE)
        assert result.model_used == B and a.requests == [] and len(b.requests) == 1
        rows = await guard.query(LedgerQuery(invocation_id=request.invocation_id))
        assert (
            len(rows) == 1
            and rows[0].start.attempt_ordinal == 1
            and rows[0].start.requested_model == B
        )
        assert rows[0].invocation_outcome is AttemptOutcome.SUCCESS
        reservations = await guard.reservations(p.budget_id)
        if scope == "model":
            assert reservations == ()
        else:
            assert len(reservations) == 1 and reservations[0].reserved == Money("USD", D("0.02"))
            assert reservations[0].status is ReservationStatus.SETTLED
        assert (await guard.view(p.budget_id)).known_estimated_spend.amount == (
            D("0") if scope == "model" else D("0.02")
        )

    asyncio.run(database_run(tmp_path, run))


def test_exact_model_budget_denial_does_not_change_even_with_explicit_chain(tmp_path):
    async def run(db):
        request = req(model=A, max_output_tokens=1)
        guard = db.llm_budget_guard(
            bounder=registry().usage_bounder(), catalog=prices(), diagnostics=lambda d: None
        )
        await guard.put_policy(policy(limit=Money("USD", D("0.04"))), None)
        a, b = (
            ScriptedGateway(success(request)),
            ScriptedGateway(success(replace(request, model=B))),
        )
        router = routed(
            {A: a, B: b},
            reasons=tuple(FallbackReason),
            budget_guard=guard,
            wall_clock=lambda: AT,
            accounting_diagnostics=lambda d: None,
        )
        for selection in (
            None,
            ExplicitModelSelection(A, route_policy((A, B), tuple(FallbackReason))),
        ):
            with pytest.raises(BudgetAdmissionError) as error:
                await router.generate(request, selection=selection)
            assert error.value.summary.integrity_healthy
        assert a.requests == b.requests == [] and await counts(db) == (0, 0)

    asyncio.run(database_run(tmp_path, run))


def test_all_matching_hard_policies_evaluated_integrity_overrides_affordability(tmp_path):
    async def run(db):
        request = req(model=A, max_output_tokens=1)
        small = policy(budget_id=BudgetId(UUID(int=1)), limit=Money("USD", D("0.01")))
        broken = policy(
            budget_id=BudgetId(UUID(int=2)), limit=Money("USD", D("1")), purpose=request.purpose
        )
        healthy = policy(budget_id=BudgetId(UUID(int=3)), limit=Money("USD", D("1")), model=A)
        guard = db.llm_budget_guard(
            bounder=registry().usage_bounder(), catalog=prices(), diagnostics=lambda d: None
        )
        for p in (small, broken, healthy):
            await guard.put_policy(p, None)
        original = guard._view_in_session
        evaluated = []

        async def controlled(session, p):
            evaluated.append(p.budget_id)
            view = await original(session, p)
            return (
                replace(view, integrity_degraded=True, remaining=None)
                if p.budget_id == broken.budget_id
                else view
            )

        guard._view_in_session = controlled
        a, b = (
            ScriptedGateway(success(request)),
            ScriptedGateway(success(replace(request, model=B))),
        )
        with pytest.raises(BudgetAdmissionError) as error:
            await routed(
                {A: a, B: b},
                reasons=tuple(FallbackReason),
                budget_guard=guard,
                wall_clock=lambda: AT,
                accounting_diagnostics=lambda d: None,
            ).generate(request, selection=PROFILE)
        assert evaluated == [small.budget_id, broken.budget_id, healthy.budget_id]
        assert error.value.reason is BudgetReason.INTEGRITY_DEGRADED
        facts = error.value.summary.facts
        assert [f.reason for f in facts] == [
            BudgetReason.EXCEEDED,
            BudgetReason.INTEGRITY_DEGRADED,
            None,
        ]
        assert not error.value.summary.integrity_healthy
        assert a.requests == b.requests == [] and await counts(db) == (0, 0)
        wire = json.dumps(asdict(error.value.summary), default=str) + repr(error.value)
        assert all(c not in wire for c in (CANARY, PROMPT, RESPONSE, REASONING))

    asyncio.run(database_run(tmp_path, run))


def test_successful_budget_admission_returns_complete_committed_safe_facts(tmp_path):
    async def run(db):
        request = req(model=A, max_output_tokens=1)
        p = policy(limit=Money("USD", D("1")))
        guard = db.llm_budget_guard(
            bounder=registry().usage_bounder(),
            catalog=prices(),
            diagnostics=lambda diagnostic: None,
        )
        await guard.put_policy(p, None)
        result = await guard.admit(
            AttemptStart(request.invocation_id, 1, request.purpose, A, AT), request
        )
        assert result.admitted and result.reservations_committed
        assert len(result.facts) == 1
        fact = result.facts[0]
        assert fact.budget_id == p.budget_id and fact.reason is None
        assert fact.requested_upper_bound == Money("USD", D("0.08"))
        assert result.integrity_healthy
        wire = json.dumps(asdict(result), default=str) + repr(result)
        assert all(c not in wire for c in (CANARY, PROMPT, RESPONSE, REASONING))

    asyncio.run(database_run(tmp_path, run))


@pytest.mark.parametrize("reason", [BudgetReason.STATE_UNCERTAIN, BudgetReason.INTEGRITY_DEGRADED])
def test_terminal_budget_denial_never_fallback_with_any_policy(reason):
    async def run():
        request = req(model=A)
        p = policy()
        fact = BudgetAdmissionFact(
            budget_id=p.budget_id,
            scope=BudgetScope(),
            reason=reason,
            limit=p.limit,
            known_spend=Money("USD", D("0")),
            held=Money("USD", D("0")),
            remaining=None,
            requested_upper_bound=None,
            integrity_degraded=reason is BudgetReason.INTEGRITY_DEGRADED,
            unbounded_exposure=reason is BudgetReason.STATE_UNCERTAIN,
        )

        class Denial(FailingAccounting):
            async def admit(self, start, request):
                raise BudgetAdmissionError(
                    reason, p.budget_id, summary=BudgetAdmissionSummary((fact,))
                )

        a, b = (
            ScriptedGateway(success(request)),
            ScriptedGateway(success(replace(request, model=B))),
        )
        with pytest.raises(BudgetAdmissionError):
            await routed(
                {A: a, B: b},
                reasons=tuple(FallbackReason),
                budget_guard=Denial("unused"),
                wall_clock=lambda: AT,
                accounting_diagnostics=lambda d: None,
            ).generate(request, selection=PROFILE)
        assert a.requests == b.requests == []

    asyncio.run(run())


def test_legacy_denial_without_complete_safe_facts_fails_closed():
    assert (
        budget_fallback_reason(BudgetAdmissionError(BudgetReason.EXCEEDED, policy().budget_id))
        is None
    )


def test_budget_queries_each_physical_attempt_by_actual_requested_candidate(tmp_path):
    async def run(db):
        request = req(model=A, max_output_tokens=1)
        guard = db.llm_budget_guard(
            bounder=registry().usage_bounder(), catalog=prices(), diagnostics=lambda d: None
        )
        pa, pb = (
            policy(model=A, limit=Money("USD", D("1"))),
            policy(model=B, limit=Money("USD", D("1"))),
        )
        for p in (pa, pb):
            await guard.put_policy(p, None)
        a = ScriptedGateway(
            failure(
                request, LLMErrorCode.TIMEOUT, None, dispatch_state=DispatchState.NOT_DISPATCHED
            ),
            failure(
                request, LLMErrorCode.TIMEOUT, None, dispatch_state=DispatchState.NOT_DISPATCHED
            ),
        )
        b = ScriptedGateway(replace(success(replace(request, model=B)), usage=LLMUsage(7, 1, 8)))
        await routed(
            {A: a, B: b},
            reasons=(FallbackReason.NOT_DISPATCHED,),
            budget_guard=guard,
            wall_clock=lambda: AT,
            accounting_diagnostics=lambda d: None,
        ).generate(request, selection=PROFILE)
        rows = await guard.query(LedgerQuery(invocation_id=request.invocation_id))
        assert [r.start.attempt_ordinal for r in rows] == [1, 2, 3]
        assert (await guard.view(pa.budget_id)).known_estimated_spend.amount == D("0")
        assert (await guard.view(pb.budget_id)).known_estimated_spend.amount == D("0.02")
        assert [r.status for r in await guard.reservations(pa.budget_id)] == [
            ReservationStatus.RELEASED
        ] * 2
        assert len(await guard.reservations(pb.budget_id)) == 1

    asyncio.run(database_run(tmp_path, run))
