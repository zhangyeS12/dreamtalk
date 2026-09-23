from uuid import uuid4

import pytest
from livingworld.application.llm import LLMUsage, ReasoningTokenRelation
from livingworld.application.llm_chat_turn_budget import (
    ChatTurnTokenBudget,
    TurnTokenBoundViolation,
    TurnTokenBudgetError,
)


def test_one_ceiling_charges_all_physical_attempts_and_releases_only_factual_unused_tokens():
    turn = ChatTurnTokenBudget(50)
    first, retry, fallback = uuid4(), uuid4(), uuid4()
    turn.reserve(first, input_upper_bound=12, max_output_tokens=18)
    assert turn.remaining == 20
    with pytest.raises(TurnTokenBudgetError, match="unavailable"):
        turn.reserve(retry, input_upper_bound=1, max_output_tokens=1)
    assert turn.settle(first, LLMUsage(input_tokens=12, output_tokens=3)) == 35
    turn.reserve(retry, input_upper_bound=10, max_output_tokens=15)
    assert turn.settle(retry, LLMUsage(input_tokens=9, output_tokens=6)) == 20
    turn.reserve(fallback, input_upper_bound=10, max_output_tokens=10)
    assert turn.settle(fallback, LLMUsage(input_tokens=10, output_tokens=10)) == 0
    with pytest.raises(TurnTokenBudgetError, match="exhausted"):
        turn.reserve(uuid4(), input_upper_bound=0, max_output_tokens=1)


def test_no_trusted_input_bound_denies_before_attempt_and_undispatched_can_release():
    turn = ChatTurnTokenBudget(20)
    with pytest.raises(TurnTokenBudgetError, match="bound_unavailable"):
        turn.reserve(uuid4(), input_upper_bound=None, max_output_tokens=5)
    assert turn.remaining == 20
    denied = uuid4()
    turn.reserve(denied, input_upper_bound=8, max_output_tokens=10)
    turn.release_undispatched(denied)
    assert turn.remaining == 20
    with pytest.raises(TurnTokenBudgetError, match="identity_invalid"):
        turn.reserve(denied, input_upper_bound=8, max_output_tokens=10)


@pytest.mark.parametrize("usage", [None, LLMUsage(input_tokens=5), LLMUsage(output_tokens=2)])
def test_missing_or_incomplete_usage_consumes_reservation_and_stops_turn(usage):
    turn = ChatTurnTokenBudget(50)
    attempt = uuid4()
    turn.reserve(attempt, input_upper_bound=10, max_output_tokens=20)
    assert turn.settle(attempt, usage) == 20
    assert turn.closed
    with pytest.raises(TurnTokenBudgetError, match="unavailable"):
        turn.reserve(uuid4(), input_upper_bound=1, max_output_tokens=1)


def test_reported_usage_above_upper_bound_is_integrity_failure():
    turn = ChatTurnTokenBudget(50)
    attempt = uuid4()
    turn.reserve(attempt, input_upper_bound=10, max_output_tokens=5)
    with pytest.raises(TurnTokenBoundViolation, match="bound_violated"):
        turn.settle(attempt, LLMUsage(input_tokens=11, output_tokens=5))
    assert turn.remaining == 0
    assert turn.closed


def test_total_usage_fact_cannot_be_ignored_when_larger_than_input_plus_output():
    turn = ChatTurnTokenBudget(20)
    attempt = uuid4()
    turn.reserve(attempt, input_upper_bound=10, max_output_tokens=10)
    assert turn.settle(attempt, LLMUsage(input_tokens=5, output_tokens=5, total_tokens=17)) == 3


def test_additive_or_unknown_reasoning_tokens_are_charged_conservatively():
    turn = ChatTurnTokenBudget(30)
    first, second = uuid4(), uuid4()
    turn.reserve(first, input_upper_bound=10, max_output_tokens=10)
    assert (
        turn.settle(
            first,
            LLMUsage(
                input_tokens=5,
                output_tokens=4,
                reasoning_output_tokens=3,
                reasoning_token_relation=ReasoningTokenRelation.ADDITIVE_TO_OUTPUT,
            ),
        )
        == 18
    )
    turn.reserve(second, input_upper_bound=10, max_output_tokens=8)
    assert (
        turn.settle(
            second,
            LLMUsage(input_tokens=5, output_tokens=4, reasoning_output_tokens=3),
        )
        == 6
    )


@pytest.mark.parametrize("invalid", [0, -1, True, 1.5])
def test_invalid_turn_limit_rejected(invalid):
    with pytest.raises(TurnTokenBudgetError, match="limit_invalid"):
        ChatTurnTokenBudget(invalid)
