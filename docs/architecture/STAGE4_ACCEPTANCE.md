# Stage 4 Acceptance — LLM Infrastructure

状态：C-005A 至 C-005E5 的离线验收基线。所有 provider wire 测试使用 deterministic fake/MockTransport；没有付费请求。Stage 4 完成后冻结，Stage 5 未开始。

## 1. Provider matrix

`configured` 表示能力必须在 exact model adapter profile 中显式开启；不支持的能力在 credential/network 前返回 typed failure，不伪造结果。

| 能力 | OpenAI-compatible | Anthropic Messages | Gemini Interactions | OpenAI Responses |
| --- | --- | --- | --- | --- |
| plain text | verified | verified | verified | verified |
| incremental text stream | configured; `[DONE]` terminal | configured; `message_start` lock | configured; `interaction.created` lock | configured; `response.created` lock |
| structured non-stream | native schema or JSON/local validate by profile | native schema when configured | native schema when configured | native schema when configured |
| refusal/filter | success semantics | success terminal | success terminal | success terminal |
| factual usage | common normalized snapshot | cache/TTL/reasoning facts | additive thought facts | cached/reasoning included facts |
| pricing/budget | common governed pipeline | common governed pipeline | common governed pipeline | common governed pipeline |
| retry/fallback | outer policy only | outer policy only | outer policy only | outer policy only |
| credential | SecretRef session lookup | SecretRef session lookup | SecretRef session lookup | SecretRef session lookup |

Adapter evidence is in [OpenAI-compatible tests](../../tests/core/test_openai_compatible.py), [Anthropic tests](../../tests/core/test_anthropic_messages.py), [Gemini tests](../../tests/core/test_gemini_interactions.py), and [OpenAI Responses tests](../../tests/core/test_openai_responses.py). Structured/stream contracts are also covered by [structured generation](../../tests/core/test_structured_generation.py) and [streaming](../../tests/core/test_llm_streaming.py).

## 2. Cross-protocol lifecycle

The deterministic four-protocol route proves:

```text
OpenAI-compatible attempt 1 → safe fallback
Anthropic attempt 2         → safe fallback
Gemini attempt 3            → safe fallback
OpenAI Responses attempt 4  → success
```

The route retains one InvocationId, one monotonic deadline and invocation-global ordinals. Every actual candidate gets its own requested ModelRef, pricing preflight, complete budget admission/reservation, accounting START, provider execution and FINAL/settlement. Candidate retry counters may reset; the deadline and ordinal do not. Integrity failure, unknown dispatch or an exposed stream STARTED boundary terminates routing.

Streaming tests cover safe fallback only before the protocol-specific STARTED boundary. Once exposed, no provider is switched and no `TextDelta` from another adapter is mixed into the logical stream. Cancellation produces neither FAILED nor COMPLETED solely because the caller cancelled.

## 3. Continuation boundary

`ProviderContinuationArtifact` remains provider-neutral application metadata. Gemini thought-signature and OpenAI Responses encrypted-reasoning artifacts round-trip through their closed codecs and validate provider/digest bindings. Foreign artifacts fail before credential resolution/network. Artifact payloads never enter World, Knowledge, Content, accounting or budget persistence. Conversation persistence remains Stage 9 work.

## 4. Production composition checks

[production tests](../../tests/core/test_llm_production.py) prove:

- config v1 wires all four explicit adapter families and FAST/BALANCED/BEST profiles;
- deterministic config defects fail safely before execution;
- missing credentials produce zero provider calls and zero attempt rows;
- the only exposed production gateway includes routing, retry, accounting, pricing and budget;
- owned adapter clients close with the Core runtime;
- control framing is bounded and Rust/Python share one contract fixture;
- Core restart requires host reprovision and does not persist the Python session key;
- the real-provider harness remains disabled despite a credential environment variable unless its opt-in flag is present.

Windows Rust integration additionally starts Core, provisions from a fake native-store abstraction, observes `ready`, restarts, reprovisions, observes `ready` again, gracefully stops, and scans the generated app-data tree for the credential canary.

## 5. Privacy and secret canaries

Stage 4 tests plant independent canaries for API key, prompt, response, reasoning, thought signature, encrypted reasoning artifact, private world/Character values and the sidecar control payload. Assertions cover safe object repr/serialization, structured logs, retry/routing/budget diagnostics, SQLite operational rows, world/content tables, config, bootstrap/ready files and test app-data bytes.

Permitted content lifetime is limited to the intended request/response/stream object or transient protocol decoder. Persisted LLM tables contain only normalized accounting/budget facts. Logs accept only timestamp, level, component, event and optional validated trace ID. No raw provider body, SSE, headers, SQL exception, prompt, completion, reasoning or credential is retained.

## 6. Static architecture audit

| Audit target | Result |
| --- | --- |
| provider/model-name heuristics | none in production config/composition/router |
| adapter-local retry | none; each adapter performs one physical HTTP attempt |
| provider budget/accounting bypass | none; production exposes governed routed gateway only |
| secret logging/plaintext persistence | none found; OS native store + in-memory Core session |
| World/Knowledge/Content mutation | LLM layer has no ports for these writes |
| prompt/reasoning persistence | closed persistence codecs reject them |
| streaming full-answer buffer | `TextDelta` is content source; terminal holds metadata only |
| unsafe fallback | blocked after unknown dispatch, STARTED or integrity failure |
| attempt identity | one InvocationId and global physical ordinal across route |
| money representation | Decimal text/data; no float money |
| hard-coded production prices | none; catalog is versioned configuration data |

Dependency direction remains `domain ← application ← infrastructure/adapters ← bootstrap`. Application contracts do not import Tauri/keyring. Provider adapters do not write accounting/budget DB directly. Rust credential code has no World/Character concepts; Python credentials have no OS-keychain API.

## 7. Freeze boundary

Alembic head remains `0010_llm_budget_guard`; C-005E5 introduces no schema migration. Real network verification is optional and was not executed. Provider credential validity, provider availability and provider billing accuracy therefore remain unverified external facts. Settings UI, online catalog/model discovery, tools/media, conversation persistence, Director, Character Agent, Memory and world simulation remain out of scope.
