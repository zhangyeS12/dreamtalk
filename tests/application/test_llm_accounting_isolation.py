"""Populated canonical knowledge stays outside operational accounting and estimates."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from livingworld.application.commands import AcquireKnowledge, AssertWorldTruth, FormCharacterBelief
from livingworld.application.llm import (
    InvocationId,
    LLMMessage,
    LLMPurpose,
    LLMRequest,
    MessageRole,
    ModelRef,
    ProviderId,
    TextContent,
)
from livingworld.application.llm_accounting import LedgerQuery
from livingworld.application.llm_execution import ExecutingModelGateway
from livingworld.domain.identifiers import KnowledgeAssertionId
from livingworld.domain.knowledge import ObservationChannel
from livingworld.domain.values import WorldTime
from livingworld.infrastructure.llm.fake import FakeModelGateway
from sqlalchemy import text


def test_accounting_cannot_mutate_or_store_existing_private_knowledge(environment):
    truth = "LW_EXISTING_TRUTH_ACCOUNTING_CANARY"
    belief = "LW_EXISTING_BELIEF_ACCOUNTING_CANARY"
    player = "LW_EXISTING_PLAYER_KNOWLEDGE_ACCOUNTING_CANARY"
    prompt = "LW_PROMPT_ACCOUNTING_ISOLATION_CANARY"

    async def run():
        env = environment
        try:
            await env.initialize()
            await env.handler.execute(
                env.command(
                    AssertWorldTruth,
                    assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                    subject="door",
                    predicate="state",
                    value=truth,
                    valid_from=WorldTime(123),
                )
            )
            for subject, value in (("belief", belief), ("player", player)):
                identity = KnowledgeAssertionId(env.world, uuid4())
                await env.handler.execute(
                    env.command(
                        FormCharacterBelief,
                        assertion_id=identity,
                        character_id=env.alice,
                        subject=subject,
                        predicate="state",
                        value=value,
                        epistemic_status="belief",
                        valid_from=WorldTime(123),
                    )
                )
                if subject == "player":
                    await env.handler.execute(
                        env.command(
                            AcquireKnowledge,
                            assertion_id=KnowledgeAssertionId(env.world, uuid4()),
                            receiver_id=env.player,
                            source_assertion_id=identity,
                            channel=ObservationChannel.TOLD,
                        )
                    )

            async def protected_snapshot():
                async with env.database.engine.connect() as connection:
                    names = (
                        (
                            await connection.execute(
                                text(
                                    "SELECT name FROM sqlite_master WHERE type='table' "
                                    "AND name NOT LIKE 'sqlite_%' AND name != 'llm_attempts'"
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    return {
                        name: sorted(
                            map(
                                repr,
                                (await connection.execute(text(f'SELECT * FROM "{name}"'))).all(),
                            )
                        )
                        for name in names
                    }

            before = await protected_snapshot()
            assert all(canary in repr(before) for canary in (truth, belief, player))
            req = LLMRequest(
                invocation_id=InvocationId(uuid4()),
                model=ModelRef(ProviderId("fake-accounting"), "controlled"),
                purpose=LLMPurpose("isolation-proof"),
                max_output_tokens=100,
                messages=(
                    LLMMessage(
                        MessageRole.USER, (TextContent(" ".join((prompt, truth, belief, player))),)
                    ),
                ),
                metadata={"private_knowledge": (truth, belief, player)},
            )
            ledger = env.database.llm_usage_ledger()
            diagnostics = []
            gateway = ExecutingModelGateway(
                FakeModelGateway(),
                accounting=ledger,
                wall_clock=lambda: datetime(2026, 9, 18, tzinfo=UTC),
                accounting_diagnostics=diagnostics.append,
            )
            await gateway.generate(req)
            assert not diagnostics
            assert await protected_snapshot() == before
            assert len(await ledger.query(LedgerQuery())) == 1
            async with env.database.engine.connect() as connection:
                raw = repr((await connection.execute(text("SELECT * FROM llm_attempts"))).all())
            assert all(canary not in raw for canary in (truth, belief, player, prompt))
        finally:
            await env.database.close()

    asyncio.run(run())
