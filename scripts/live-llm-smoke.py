"""Explicit, bounded developer smoke for one real configured LLM model."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from livingworld.application.llm import (
    LLMMessage,
    LLMPurpose,
    LLMRequest,
    MessageRole,
    ModelRef,
    ProviderId,
    TextContent,
)
from livingworld.bootstrap.llm_runtime import InvocationFactory, build_production_llm_runtime
from livingworld.infrastructure.database import bootstrap_database
from livingworld.infrastructure.llm.credentials import SessionCredentialProvider
from livingworld.infrastructure.llm.production_config import load_configuration
from livingworld.infrastructure.logging import StructuredLogger

MAX_VISIBLE_OUTPUT_CHARS = 512


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Opt-in real-provider LLM smoke")
    result.add_argument("--enable-live-provider", action="store_true")
    result.add_argument("--config", type=Path, required=True)
    result.add_argument("--data-dir", type=Path, required=True)
    result.add_argument("--provider", required=True)
    result.add_argument("--model", required=True)
    result.add_argument("--credential-env", required=True)
    result.add_argument("--prompt", default="Reply with exactly: OK")
    result.add_argument("--max-output-tokens", type=int, default=16, choices=range(1, 65))
    return result


async def execute(args: argparse.Namespace) -> int:
    if not args.enable_live_provider:
        print("live_provider_smoke_disabled; pass --enable-live-provider to permit network usage")
        return 2
    print(
        "WARNING: this command sends one real provider request and may incur external API cost.",
        file=sys.stderr,
    )
    secret = os.environ.get(args.credential_env)
    if not secret:
        print("live_provider_credential_missing", file=sys.stderr)
        return 2
    configuration = load_configuration(args.config.resolve())
    model = ModelRef(ProviderId(args.provider), args.model)
    registered = configuration.registry.lookup(model)
    configured = configuration.models.get(model)
    if registered is None or not registered.enabled or configured is None:
        print("live_provider_model_not_configured", file=sys.stderr)
        return 2
    reference = configuration.providers[model.provider_id].config.secret_ref
    credentials = SessionCredentialProvider(configuration.secret_refs)
    credentials.upsert(reference, secret)
    secret = ""
    credentials.complete_sync(secure_store_available=True)
    database = await bootstrap_database(args.data_dir.resolve())
    runtime = None
    try:
        runtime = await build_production_llm_runtime(
            configuration, database, StructuredLogger(), credentials=credentials
        )
        request = LLMRequest(
            invocation_id=InvocationFactory().create(),
            model=model,
            purpose=LLMPurpose("developer-live-smoke"),
            messages=(LLMMessage(MessageRole.USER, (TextContent(args.prompt),)),),
            max_output_tokens=args.max_output_tokens,
        )
        response = await runtime.gateway.generate(request)
        print(response.text[:MAX_VISIBLE_OUTPUT_CHARS])
        print(f"finish_reason={response.finish_reason.value}")
        return 0
    except Exception as error:
        print(f"live_provider_smoke_failed:{type(error).__name__}", file=sys.stderr)
        return 1
    finally:
        if runtime is not None:
            await runtime.aclose()
        await database.close()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(execute(parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
