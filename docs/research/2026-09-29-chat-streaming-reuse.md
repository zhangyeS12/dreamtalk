# Incremental dialogue — 2026-09-29

## Mature sources and reuse

- [eventsource-parser](https://github.com/rexxars/eventsource-parser/tree/v4.1.1) **4.1.1**, MIT: reuse arbitrary-chunk SSE parsing and maxBufferSize. Inspected npm/upstream package, installed source and license; exact pin/lock, portable notice at docs/licenses/eventsource-parser-4.1.1.txt. Installation disabled lifecycle scripts. A single authenticated fetch POST avoids automatic EventSource reconnection and paid-call replay; the parser performs no transport retry.
- [Starlette StreamingResponse](https://starlette.dev/responses/#streamingresponse), installed **1.6.0**, BSD-3-Clause: reuse this existing dependency for delivery/disconnect detection. Inspected installed source and Uvicorn ASGI 2.3 declaration. Add explicit iterator close for both ASGI branches, a queue of eight frames, and shielded cancellation cleanup. No new Python runtime/protocol parser.
- [OpenAI streaming](https://developers.openai.com/api/docs/guides/streaming-responses) and [complete-input count](https://developers.openai.com/api/reference/typescript/resources/responses/subresources/input_tokens), reviewed current v1 contract: inspected actual adapter payload; streaming changes transport, while model/input/disabled-truncation are identical. Extend existing count projection to stateless streaming, retaining exact direct-endpoint, structured/continuation exclusions and conservative fallback. This equivalence is inferred from the inspected payload and contract; live behavior is unverified.
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) documents stream/include_usage. Existing official MIT deepseek-recipe **0.1.0** converter creates the same Conversation independently of stream/parsing options. Pass the actual streaming payload to the existing official framing helper. No tokenizer/template rewrite or estimated hard bound; no helper/provider invocation for verification.
- SillyTavern-style incremental chat informs behavior; no AGPL code is copied. Existing governed adapters, React and the MIT parser fit Apache-2.0.

## Contract and limits

Add POST direct/group turn reply/stream routes alongside existing JSON routes. Owner lookup precedes headers; claimed returns 409; completed returns only durable messages without model generation. SSE frames carry turn_id and fixed kind: preparing/selecting, replying(speaker_id), delta(speaker_id,text), message(ChatMessage), completed, or error(fixed status/code). Idle comment heartbeat every ten seconds. No secrets, prompts, provider error bodies, selector output or reasoning deltas are exposed.

Choose streaming only when capability planning succeeds before dispatch. Nonstream-only routes keep complete delivery. Once dispatched, a failed stream never switches to nonstream generation; existing governed retry/fallback rules and accounting retain authority. Group selection remains internal and nonstream. All selection/reply attempts share the same hard input/output ceiling. Trusted per-request bounds, claim, ledger and final validation are preserved.

Deltas are provisional, at most 65,536 UTF-8 bytes per reply. Governed terminal settlement, invocation/finish/text/bound checks precede the original commit. Group messages commit individually; failure clears current partial text and preserves prior commits. No WorldEvent, CharacterBelief, PlayerKnowledge or memory is created by streaming.

Client limits: parser buffer 512 KiB characters, wire 64 MiB, 600,000 events, one direct/32 group messages. Validate matching turn/conversation/allowed speaker, message shape and byte limits. EOF without completed interrupts; no automatic reconnect. Merge committed messages by ID with paged history, suppress duplicate live bubbles after refresh, and follow scrolling only near the bottom.

Explicit desktop “逐步显示回复” preference reuses save/restart/rollback. New setup selects it; old managed configuration stays unchanged until user saves. Matching capability/profile is declared for all existing adapters; Chat Completions declares include_usage too. Unknown proxies may require disabling this setting. Missing usage keeps conservative reservation/unknown accounting; Claude/Gemini retain model-wide trusted input bounds. No user config or credential was changed during development.

Stop and leaving the conversation abort fetch and governed execution. A view closed during message saving cannot start a late generation. Cancellation is not a guaranteed refund or completed turn. Interrupted claims remain unresolved without automatic replay; one status GET reconciles a commit racing with cancellation.

## Verification

Ruff lint/format, ESLint/TypeScript and source review passed. Core PyInstaller and Vite/Rust release compiled; package/log/hash evidence is in HANDOFF.md. Under AGENTS section 20, no automated tests were added/modified/run, no browser/desktop/provider smoke checks, no credentials, user DB/config writes or app launches. Existing tests/CI preserved. Builds do not prove runtime acceptance; streaming, cancellation, provider terminal usage and natural group STOP await user verification.

Existing ChatTranscript/GroupChat test mocks still expect the previous JSON-generation client methods. Source inspection confirms they need adaptation to streaming; they were not modified or run under the current user testing instruction. No passing suite is claimed.
