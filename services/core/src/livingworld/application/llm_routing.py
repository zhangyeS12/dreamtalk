"""Deterministic operational routing above attempt execution; no provider IO/schema."""

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import aclosing
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from livingworld.application.llm import (
    InvocationId,
    LLMContractError,
    LLMError,
    LLMFailure,
    LLMPurpose,
    LLMRequest,
    LLMResponse,
    LLMStreamEvent,
    ModelGateway,
    ModelRef,
    StreamCompleted,
    StreamFailed,
    StreamStarted,
    StructuredOutputMode,
)
from livingworld.application.llm_accounting import AttemptOutcome
from livingworld.application.llm_budget import BudgetAdmissionError, BudgetReason
from livingworld.application.llm_execution import (
    ExecutingModelGateway,
    ExecutionDeadlineError,
    RetryPolicy,
    RetryReason,
    RetryRecord,
    _InvocationExecution,
    retry_failure_reason,
)
from livingworld.application.llm_registry import ModelRegistry


class RoutingProfile(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    BEST = "best"


class FallbackReason(StrEnum):
    RATE_LIMITED = "rate_limited"
    TRANSIENT_HTTP_FAILURE = "transient_http_failure"
    NOT_DISPATCHED = "not_dispatched_transport_failure"
    CANDIDATE_UNAVAILABLE = "candidate_unavailable"
    BUDGET_EXCEEDED = "budget_exceeded"
    BUDGET_UNVERIFIABLE = "budget_unverifiable"
    BUDGET_CURRENCY_UNSUPPORTED = "budget_currency_unsupported"


class RouteIssue(StrEnum):
    POLICY_MISSING = "routing_policy_missing"
    MODEL_UNREGISTERED = "model_unregistered"
    MODEL_DISABLED = "model_disabled"
    CAPABILITY_MISMATCH = "capability_mismatch"
    CANDIDATE_UNAVAILABLE = "candidate_unavailable"
    STRUCTURED_STREAM_UNSUPPORTED = "structured_stream_unsupported"
    NO_ELIGIBLE_CANDIDATE = "no_eligible_candidate"


class RoutingError(RuntimeError):
    """Local operational error, never an HTTP/provider failure."""

    def __init__(self, issue: RouteIssue):
        if not isinstance(issue, RouteIssue):
            raise LLMContractError("invalid_route_issue")
        self.issue = issue
        super().__init__(issue.value)


@dataclass(frozen=True, slots=True)
class RoutePolicyId:
    value: str

    def __post_init__(self):
        if type(self.value) is not str or not self.value.strip():
            raise LLMContractError("invalid_route_policy_id")


@dataclass(frozen=True, slots=True)
class RoutePolicy:
    policy_id: RoutePolicyId
    candidates: tuple[ModelRef, ...]
    allowed_fallback: frozenset[FallbackReason] = frozenset()

    def __post_init__(self):
        if (
            not isinstance(self.policy_id, RoutePolicyId)
            or type(self.candidates) is not tuple
            or not self.candidates
            or any(not isinstance(m, ModelRef) for m in self.candidates)
        ):
            raise LLMContractError("invalid_route_policy")
        if len(set(self.candidates)) != len(self.candidates):
            raise LLMContractError("duplicate_route_candidate")
        if type(self.allowed_fallback) is not frozenset or any(
            not isinstance(r, FallbackReason) for r in self.allowed_fallback
        ):
            raise LLMContractError("invalid_fallback_policy")


@dataclass(frozen=True, slots=True)
class PurposePolicy:
    profile: RoutingProfile
    policy: RoutePolicy
    purpose: LLMPurpose | None = None  # None is an explicitly configured default.

    def __post_init__(self):
        if (
            not isinstance(self.profile, RoutingProfile)
            or not isinstance(self.policy, RoutePolicy)
            or self.purpose is not None
            and not isinstance(self.purpose, LLMPurpose)
        ):
            raise LLMContractError("invalid_purpose_policy")


@dataclass(frozen=True, slots=True)
class RoutingConfiguration:
    policies: tuple[PurposePolicy, ...] = ()

    def __post_init__(self):
        if type(self.policies) is not tuple or any(
            not isinstance(p, PurposePolicy) for p in self.policies
        ):
            raise LLMContractError("invalid_routing_configuration")
        if len({(p.profile, p.purpose) for p in self.policies}) != len(self.policies):
            raise LLMContractError("duplicate_purpose_policy")

    def policy(self, purpose, profile):
        exact = next(
            (p.policy for p in self.policies if p.purpose == purpose and p.profile == profile), None
        )
        return (
            exact
            if exact is not None
            else next(
                (p.policy for p in self.policies if p.purpose is None and p.profile == profile),
                None,
            )
        )


@dataclass(frozen=True, slots=True)
class ProfileSelection:
    profile: RoutingProfile

    def __post_init__(self):
        if not isinstance(self.profile, RoutingProfile):
            raise LLMContractError("invalid_routing_profile")


@dataclass(frozen=True, slots=True)
class ExplicitModelSelection:
    model: ModelRef
    fallback_policy: RoutePolicy | None = None

    def __post_init__(self):
        if not isinstance(self.model, ModelRef):
            raise LLMContractError("invalid_model_ref")
        if self.fallback_policy is not None and (
            not isinstance(self.fallback_policy, RoutePolicy)
            or self.fallback_policy.candidates[0] != self.model
        ):
            raise LLMContractError("explicit_selection_must_be_primary")


type ModelSelection = ProfileSelection | ExplicitModelSelection


@dataclass(frozen=True, slots=True)
class RouteRequirements:
    streaming: bool = False
    structured_modes: frozenset[StructuredOutputMode] = frozenset()

    def __post_init__(self):
        if (
            type(self.streaming) is not bool
            or type(self.structured_modes) is not frozenset
            or any(
                not isinstance(m, StructuredOutputMode) or m is StructuredOutputMode.NONE
                for m in self.structured_modes
            )
        ):
            raise LLMContractError("invalid_route_requirements")

    @classmethod
    def for_request(cls, request):
        return cls(
            request.streaming,
            frozenset(
                {
                    StructuredOutputMode.NATIVE_JSON_SCHEMA,
                    StructuredOutputMode.JSON_OBJECT_LOCAL_VALIDATE,
                }
            )
            if request.structured_output is not None
            else frozenset(),
        )


@dataclass(frozen=True, slots=True)
class CandidateSkip:
    candidate: ModelRef
    issue: RouteIssue


@dataclass(frozen=True, slots=True)
class RoutePlan:
    invocation_id: InvocationId
    purpose: LLMPurpose
    selection: ModelSelection
    policy_id: RoutePolicyId | None
    candidates: tuple[ModelRef, ...]
    requirements: RouteRequirements
    allowed_fallback: frozenset[FallbackReason]
    skipped: tuple[CandidateSkip, ...] = ()


def resolve_route(
    registry: ModelRegistry,
    configuration: RoutingConfiguration,
    request: LLMRequest,
    *,
    selection: ModelSelection | None = None,
    requirements: RouteRequirements | None = None,
) -> RoutePlan:
    if (
        not isinstance(registry, ModelRegistry)
        or not isinstance(configuration, RoutingConfiguration)
        or not isinstance(request, LLMRequest)
    ):
        raise LLMContractError("invalid_route_resolution")
    selection = selection if selection is not None else ExplicitModelSelection(request.model)
    requirements = (
        requirements if requirements is not None else RouteRequirements.for_request(request)
    )
    if (
        not isinstance(requirements, RouteRequirements)
        or requirements.streaming != request.streaming
        or bool(requirements.structured_modes) != (request.structured_output is not None)
    ):
        raise LLMContractError("requirements_must_match_request")
    if request.streaming and request.structured_output is not None:
        raise RoutingError(RouteIssue.STRUCTURED_STREAM_UNSUPPORTED)
    if isinstance(selection, ProfileSelection):
        policy = configuration.policy(request.purpose, selection.profile)
        if policy is None:
            raise RoutingError(RouteIssue.POLICY_MISSING)
    elif isinstance(selection, ExplicitModelSelection):
        if selection.model != request.model:
            raise LLMContractError("explicit_selection_must_match_request")
        policy = selection.fallback_policy
    else:
        raise LLMContractError("invalid_model_selection")
    candidates = policy.candidates if policy is not None else (selection.model,)
    eligible, skipped = [], []
    for model in candidates:
        entry = registry.lookup(model)
        issue = (
            RouteIssue.MODEL_UNREGISTERED
            if entry is None
            else RouteIssue.MODEL_DISABLED
            if not entry.enabled
            else None
        )
        if issue is None:
            caps = entry.capabilities
            if (
                not caps.text_generation
                or requirements.streaming
                and not caps.streaming
                or requirements.structured_modes
                and (
                    not caps.structured_output
                    or caps.structured_output_mode not in requirements.structured_modes
                )
            ):
                issue = RouteIssue.CAPABILITY_MISMATCH
        if issue is not None:
            skipped.append(CandidateSkip(model, issue))
        else:
            eligible.append(model)
    if not eligible:
        raise RoutingError(
            skipped[0].issue if len(candidates) == 1 else RouteIssue.NO_ELIGIBLE_CANDIDATE
        )
    return RoutePlan(
        request.invocation_id,
        request.purpose,
        selection,
        policy.policy_id if policy else None,
        tuple(eligible),
        requirements,
        policy.allowed_fallback if policy else frozenset(),
        tuple(skipped),
    )


class GatewayResolver(Protocol):
    def gateway(self, model: ModelRef) -> ModelGateway | None: ...


class ConfiguredGateways:
    """Borrow configured clients separately from registry data; lifecycle stays outside."""

    def __init__(self, gateways: Mapping[ModelRef, ModelGateway]):
        copied = dict(gateways)
        if any(
            not isinstance(m, ModelRef)
            or not callable(getattr(g, "generate", None))
            or not callable(getattr(g, "stream", None))
            for m, g in copied.items()
        ):
            raise LLMContractError("invalid_configured_gateways")
        self._gateways = MappingProxyType(copied)

    def gateway(self, model):
        return self._gateways.get(model)


class RoutingEvent(StrEnum):
    PLANNED = "planned"
    SKIPPED = "skipped"
    SELECTED = "selected"
    FALLBACK = "fallback"
    DEADLINE_EXHAUSTED = "deadline_exhausted"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class RoutingRecord:
    invocation_id: InvocationId
    purpose: LLMPurpose
    profile: RoutingProfile | None
    policy_id: RoutePolicyId | None
    candidates: tuple[ModelRef, ...]
    event: RoutingEvent
    candidate: ModelRef | None
    reason: FallbackReason | RouteIssue | None
    hop_count: int

    def __post_init__(self):
        if (
            not isinstance(self.invocation_id, InvocationId)
            or not isinstance(self.purpose, LLMPurpose)
            or not isinstance(self.event, RoutingEvent)
        ):
            raise LLMContractError("invalid_routing_record")
        if (
            self.profile is not None
            and not isinstance(self.profile, RoutingProfile)
            or self.policy_id is not None
            and not isinstance(self.policy_id, RoutePolicyId)
        ):
            raise LLMContractError("invalid_routing_record")
        if (
            type(self.candidates) is not tuple
            or any(not isinstance(m, ModelRef) for m in self.candidates)
            or self.candidate is not None
            and not isinstance(self.candidate, ModelRef)
        ):
            raise LLMContractError("invalid_routing_record")
        if (
            self.reason is not None
            and not isinstance(self.reason, (FallbackReason, RouteIssue))
            or type(self.hop_count) is not int
            or self.hop_count < 0
        ):
            raise LLMContractError("invalid_routing_record")


def provider_fallback_reason(failure: LLMFailure, policy: RetryPolicy) -> FallbackReason | None:
    return {
        RetryReason.RATE_LIMITED: FallbackReason.RATE_LIMITED,
        RetryReason.TRANSIENT_HTTP_FAILURE: FallbackReason.TRANSIENT_HTTP_FAILURE,
        RetryReason.NOT_DISPATCHED_TRANSPORT_FAILURE: FallbackReason.NOT_DISPATCHED,
    }.get(retry_failure_reason(failure, policy))


def budget_fallback_reason(error: BudgetAdmissionError) -> FallbackReason | None:
    recoverable = {
        BudgetReason.EXCEEDED: FallbackReason.BUDGET_EXCEEDED,
        BudgetReason.UNVERIFIABLE: FallbackReason.BUDGET_UNVERIFIABLE,
        BudgetReason.CURRENCY_UNSUPPORTED: FallbackReason.BUDGET_CURRENCY_UNSUPPORTED,
    }
    summary = error.summary
    if (
        summary is None
        or not summary.integrity_healthy
        or any(f.reason is not None and f.reason not in recoverable for f in summary.facts)
    ):
        return None
    return recoverable.get(error.reason)


class RoutedModelGateway:
    """Route one invocation through borrowed single-attempt clients, sequentially.

    Profile selection is explicit per call; ordinary ModelGateway calls retain
    exact request.model selection. No private request data is stored in trace/context.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        configuration: RoutingConfiguration,
        gateways: GatewayResolver,
        *,
        observer: Callable[[RoutingRecord], None] | None = None,
        retry_observer: Callable[[RetryRecord], None] | None = None,
        **execution_options,
    ):
        if (
            not isinstance(registry, ModelRegistry)
            or not isinstance(configuration, RoutingConfiguration)
            or not callable(getattr(gateways, "gateway", None))
        ):
            raise LLMContractError("invalid_routed_gateway")
        self._registry, self._configuration, self._gateways, self._observer = (
            registry,
            configuration,
            gateways,
            observer,
        )
        self._options = dict(execution_options)
        self._options["observer"] = retry_observer
        # Validate execution composition once, without dispatching or owning a client.
        self._control = ExecutingModelGateway(self, **self._options)
        self._policy = self._control._policy
        self._clock = self._control._clock

    def plan(self, request, *, selection=None, requirements=None):
        return resolve_route(
            self._registry,
            self._configuration,
            request,
            selection=selection,
            requirements=requirements,
        )

    def _report(self, plan, event, candidate=None, reason=None, hops=0):
        if self._observer is None:
            return
        record = RoutingRecord(
            plan.invocation_id,
            plan.purpose,
            plan.selection.profile if isinstance(plan.selection, ProfileSelection) else None,
            plan.policy_id,
            plan.candidates,
            event,
            candidate,
            reason,
            hops,
        )
        try:
            self._observer(record)
        except Exception:
            pass  # Diagnostics cannot trigger provider switching or alter outcomes.

    def _prepare(self, request, selection, requirements):
        execution = _InvocationExecution(
            request.invocation_id,
            self._clock() + self._policy.max_elapsed_seconds,
            defer_terminal=True,
        )
        plan = self.plan(request, selection=selection, requirements=requirements)
        self._report(plan, RoutingEvent.PLANNED)
        for skip in plan.skipped:
            self._report(plan, RoutingEvent.SKIPPED, skip.candidate, skip.issue)
        return plan, execution

    def _can_fallback(self, plan, execution, reason, index, *, started=False):
        return (
            not started
            and execution.integrity_healthy
            and self._clock() < execution.deadline
            and index + 1 < len(plan.candidates)
            and reason is not None
            and reason in plan.allowed_fallback
        )

    def _target(self, plan, execution, index, hops):
        if self._clock() >= execution.deadline:
            self._report(plan, RoutingEvent.DEADLINE_EXHAUSTED, hops=hops)
            raise ExecutionDeadlineError()
        candidate = plan.candidates[index]
        try:
            gateway = self._gateways.gateway(candidate)
        except Exception:
            gateway = None  # Local configuration failure; never expose arbitrary details.
        if gateway is None:
            self._report(
                plan, RoutingEvent.SKIPPED, candidate, RouteIssue.CANDIDATE_UNAVAILABLE, hops
            )
            return None
        # Resolver is local but may consume time; gate the actual attempt again.
        if self._clock() >= execution.deadline:
            raise ExecutionDeadlineError()
        self._report(plan, RoutingEvent.SELECTED, candidate, hops=hops)
        return ExecutingModelGateway(gateway, **self._options)

    async def _terminate(self, plan, execution, outcome, candidate=None, hops=0):
        await self._control._finish_invocation(execution, outcome)
        self._report(plan, RoutingEvent.TERMINAL, candidate, hops=hops)

    async def generate(
        self,
        request: LLMRequest,
        *,
        selection: ModelSelection | None = None,
        requirements: RouteRequirements | None = None,
    ) -> LLMResponse:
        if request.streaming:
            raise LLMContractError("generate_requires_nonstreaming_request")
        plan, execution = self._prepare(request, selection, requirements)
        hops = 0
        try:
            for index, candidate in enumerate(plan.candidates):
                target = self._target(plan, execution, index, hops)
                if target is None:
                    if self._can_fallback(
                        plan, execution, FallbackReason.CANDIDATE_UNAVAILABLE, index
                    ):
                        self._report(
                            plan,
                            RoutingEvent.FALLBACK,
                            candidate,
                            FallbackReason.CANDIDATE_UNAVAILABLE,
                            hops + 1,
                        )
                        hops += 1
                        continue
                    raise RoutingError(RouteIssue.CANDIDATE_UNAVAILABLE)
                before = execution.ordinal
                try:
                    result = await target.generate(
                        replace(request, model=candidate), _execution=execution
                    )
                except LLMError as error:
                    reason = provider_fallback_reason(error.failure, self._policy)
                    if not self._can_fallback(plan, execution, reason, index):
                        await self._terminate(
                            plan, execution, AttemptOutcome.FAILED, candidate, hops
                        )
                        raise
                except BudgetAdmissionError as error:
                    reason = (
                        budget_fallback_reason(error)
                        if isinstance(plan.selection, ProfileSelection)
                        and execution.ordinal == before
                        else None
                    )
                    if not self._can_fallback(plan, execution, reason, index):
                        raise
                else:
                    await self._terminate(plan, execution, AttemptOutcome.SUCCESS, candidate, hops)
                    return result
                self._report(plan, RoutingEvent.FALLBACK, candidate, reason, hops + 1)
                hops += 1
        except LLMError:
            raise  # Logical FAILED was observed above; never double-terminate.
        except BaseException as error:
            await self._terminate(
                plan,
                execution,
                AttemptOutcome.CANCELLED
                if isinstance(error, asyncio.CancelledError)
                else AttemptOutcome.LOCAL_ERROR,
                hops=hops,
            )
            raise
        raise AssertionError("route_loop_unreachable")

    async def stream(
        self,
        request: LLMRequest,
        *,
        selection: ModelSelection | None = None,
        requirements: RouteRequirements | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        if not request.streaming:
            raise LLMContractError("stream_requires_streaming_request")
        plan, execution = self._prepare(request, selection, requirements)
        hops, started, terminal = 0, False, False
        try:
            for index, candidate in enumerate(plan.candidates):
                target = self._target(plan, execution, index, hops)
                if target is None:
                    if self._can_fallback(
                        plan,
                        execution,
                        FallbackReason.CANDIDATE_UNAVAILABLE,
                        index,
                        started=started,
                    ):
                        self._report(
                            plan,
                            RoutingEvent.FALLBACK,
                            candidate,
                            FallbackReason.CANDIDATE_UNAVAILABLE,
                            hops + 1,
                        )
                        hops += 1
                        continue
                    raise RoutingError(RouteIssue.CANDIDATE_UNAVAILABLE)
                before = execution.ordinal
                failure = None
                try:
                    async with aclosing(
                        target.stream(replace(request, model=candidate), _execution=execution)
                    ) as events:
                        async for event in events:
                            if isinstance(event, StreamFailed):
                                failure = event.failure
                                break
                            if isinstance(event, StreamStarted):
                                if started:
                                    raise LLMContractError("duplicate_stream_started")
                                started = True
                            if isinstance(event, StreamCompleted):
                                terminal = True
                                await self._terminate(
                                    plan, execution, AttemptOutcome.SUCCESS, candidate, hops
                                )
                                yield event
                                return
                            yield event
                except BudgetAdmissionError as error:
                    reason = (
                        budget_fallback_reason(error)
                        if isinstance(plan.selection, ProfileSelection)
                        and execution.ordinal == before
                        else None
                    )
                    if not self._can_fallback(plan, execution, reason, index, started=started):
                        raise
                else:
                    if failure is None:
                        raise LLMContractError("stream_missing_terminal")
                    reason = provider_fallback_reason(failure, self._policy)
                    if not self._can_fallback(plan, execution, reason, index, started=started):
                        terminal = True
                        await self._terminate(
                            plan, execution, AttemptOutcome.FAILED, candidate, hops
                        )
                        yield StreamFailed(failure)
                        return
                self._report(plan, RoutingEvent.FALLBACK, candidate, reason, hops + 1)
                hops += 1
        except BaseException as error:
            if not terminal:
                terminal = True
                await self._terminate(
                    plan,
                    execution,
                    AttemptOutcome.CANCELLED
                    if isinstance(error, asyncio.CancelledError)
                    else AttemptOutcome.LOCAL_ERROR,
                    hops=hops,
                )
            raise
        raise AssertionError("route_loop_unreachable")
