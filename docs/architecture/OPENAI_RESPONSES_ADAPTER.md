# OpenAI Native Responses Adapter

Status: C-005E4 implemented and verified with offline contract fixtures. No production default
wiring or paid API call is part of this baseline.

## Protocol boundary

`AdapterKind.OPENAI_RESPONSES` is a separate protocol family from
`AdapterKind.OPENAI_COMPATIBLE`. `OpenAIResponsesGateway` sends one direct `httpx` request to
`POST /v1/responses`; it does not use the OpenAI SDK and does not translate through Chat
Completions. Existing OpenAI-compatible endpoints remain available for DeepSeek, local servers
and other compatible providers.

Provider and model selection are explicit registry data. Model names do not choose an adapter or
imply temperature, streaming, structured-output or reasoning-continuation support. The immutable
`OpenAIResponsesProfile` declares those capabilities plus optional default/maximum output limits.

## Stateless request contract

Every request explicitly carries:

```json
{
  "store": false,
  "background": false,
  "truncation": "disabled"
}
```

LivingWorld supplies the full ordered conversation. The adapter never sends
`previous_response_id`, `conversation`, tools, arbitrary metadata, `safety_identifier` or
`prompt_cache_key`. System, developer, user and assistant roles remain separate and ordered; text
is neither trimmed nor merged. Only text blocks are supported.

Credentials are resolved from `SecretRef` immediately before dispatch and sent only as a Bearer
header. Redirects, ambient proxy configuration and cookies are disabled; the Authorization header
is removed from the retained request object in `finally`. Logs contain fixed event names and the
local invocation trace only.

`max_output_tokens` maps directly and represents the complete generated-output envelope,
including reasoning tokens. Temperature is sent only when the explicit profile allows it. Stop
sequences, reasoning effort, verbosity and service-tier product controls are outside C-005E4.

## Output and structured generation

The adapter parses the Responses object itself. It processes output items in provider order and
exposes only `message.content.output_text`, without inserting separators. Reasoning text and
summaries are ignored. Unexpected tool or non-text output produces `UNSUPPORTED_CAPABILITY` and
is never executed.

Explicit refusal is a successful `LLMResponse` with `FinishReason.REFUSAL`; it is not retried,
used for fallback or parsed as JSON. Machine-readable incomplete reason `max_output_tokens` maps
to `OUTPUT_LIMIT`; documented filter/policy reasons map to refusal/filter terminal semantics.

Native structured requests use `text.format.type=json_schema`, `strict=true`, a deterministic safe
wire name and the original unchanged schema. Successful ordinary text is then parsed strictly and
validated locally with Draft 2020-12. Refusal/filter/truncation/provider failure precede parsing.
Structured streaming remains a local unsupported capability and performs no credential or network
operation.

## Opaque reasoning continuation

When the configured profile enables stateless reasoning continuation, requests explicitly include
`reasoning.encrypted_content`. A completed response may return a
`ProviderContinuationArtifact` scoped to:

```text
AdapterKind.OPENAI_RESPONSES + ProviderId + schema version
```

The opaque payload contains only the ordered provider item layout, encrypted reasoning state and
per-visible-block byte lengths/hashes. It does not duplicate visible assistant text. The artifact
is bound to the visible assistant content by a whole-content SHA-256 digest and block hashes.
Changing either the artifact or attached assistant text produces `CONTINUATION_STATE_INVALID`
before credentials or HTTP. Foreign adapter/provider artifacts are ignored.

On the next turn, the adapter reconstructs prior reasoning and assistant output items in their
original order from LivingWorld-managed history. It never uses the diagnostic Response ID as
conversation state. The artifact remains short-lived request context: it is excluded from repr and
the accounting persistence codec, and it is not Character memory, Knowledge, authored Content or
a WorldEvent.

## Streaming state machine

`response.created` is the sole STARTED boundary. After it, the existing execution policy locks the
route. Only `response.output_text.delta` emits `TextDelta`. Refusal deltas, reasoning text/summary,
annotations and opaque state never become visible text.

The adapter incrementally hashes visible deltas and does not retain a duplicate full answer.
`response.completed` with `status=completed` produces exactly one `StreamCompleted` after the
terminal output layout matches the streamed hashes. Terminal usage is the latest factual snapshot,
not an additive delta. Refusal has a successful REFUSAL outcome; max-output incomplete has an
OUTPUT_LIMIT completion. `response.failed`, malformed known events, unexpected tools, transport
failure and EOF before a semantic terminal produce `StreamFailed` with no completion. Well-formed
unknown future events are skipped. `asyncio.CancelledError` propagates without a synthetic terminal.

## Usage, pricing and diagnostics

Normalized usage maps input, cached input, output, reasoning-output and total tokens. When input
and cached counts are both factual and consistent, uncached input is their difference. Missing facts
remain `None`.

OpenAI reasoning tokens use `ReasoningTokenRelation.INCLUDED_IN_OUTPUT`; pricing must never add
reasoning tokens to output tokens again. `GENERATED_OUTPUT` pricing and hard-budget preflight use one
combined `max_output_tokens` bound. Prices still come only from the injected `PricingCatalog`.

Safe `x-request-id` and Response ID are separate optional diagnostics. `InvocationId` remains the
LivingWorld identity and Response ID is never a conversation key. Errors use HTTP status plus
documented machine type/code for authentication, permission, invalid/context requests, rate limit,
quota/billing, timeout and server availability. The adapter performs no retry.

## Evidence and limits

Offline tests are in
[test_openai_responses.py](../../tests/core/test_openai_responses.py). They cover exact stateless
payloads, role order, continuation round-trip/tamper/foreign artifacts, reasoning privacy,
structured validation, refusal, named SSE lifecycle, failure terminals, usage, pricing/budget and
a deterministic four-protocol route. Existing OpenAI-compatible, Anthropic and Gemini adapter tests
remain regression coverage.

The wire contract was checked against the official OpenAI
[Responses create reference](https://developers.openai.com/api/reference/resources/responses/methods/create),
[Responses migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses),
[streaming guide](https://developers.openai.com/api/docs/guides/streaming-responses) and
[Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
No SDK, dependency, migration, tool execution, provider conversation, production price, model
discovery or real paid API verification was added.
