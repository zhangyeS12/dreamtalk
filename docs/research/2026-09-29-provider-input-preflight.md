# Provider input preflight — 2026-09-29

## Scope and mature implementation decision

The user accepted unmentioned group replies and authorized continued product work. Keep the shared hard input/output turn quota, claims, ledger and knowledge filtering. Extend request-specific reservations to another provider without recreating tokenizers or message templates.

- OpenAI's [token-counting guide](https://developers.openai.com/api/docs/guides/token-counting) describes complete request counts including role/boundary formatting. Its [count schema](https://developers.openai.com/api/reference/python/resources/responses/subresources/input_tokens/methods/count) provides `POST /v1/responses/input_tokens`, disabled truncation and a typed response. Reviewed 2026-09-29, current v1 contract. Reuse that hosted capability through existing HTTPX and credential handling; no SDK dependency or local token-count formula.
- The official [openai-python resource](https://github.com/openai/openai-python/blob/main/src/openai/resources/responses/input_tokens.py) was inspected at blob `2748ce756c8e1c53ab8cfaf5c2b20429899ffa44`. It confirms the endpoint and supported input fields. The SDK is Apache-2.0; no SDK code is copied or distributed. The existing HTTPX license remains unchanged.
- [Claude token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) declares an estimate with possible differences at generation. It is useful for context management, but does not establish our hard upper-bound guarantee; no guessed margin or estimated value is promoted to HARD_UPPER_BOUND.
- [Gemini token guidance](https://ai.google.dev/gemini-api/docs/tokens) offers `models.count_tokens` and Interactions usage examples. This review does not establish equivalence of every current stateless Interactions wire field, including role/system framing, to the count request. Retain the trusted model-wide fallback pending a verified full-request mapping. This is an unresolved integration boundary, not a claim that Google lacks counting.
- Existing local DeepSeek official framing remains reusable and unchanged. Chat Completions proxies inherit no direct-service guarantee. Adding a general agent framework or approximate token-counter library does not solve the frozen hard-reservation requirement.

## Implementation and limits

The OpenAI adapter exposes a count projection from its actual `_payload`: model, full text input items and disabled truncation. Only the exact direct `https://api.openai.com/v1/responses` endpoint qualifies, including the default base. Structured schema, streaming and opaque continuation remain excluded. Model capacity still requires trusted configuration; no automatic values, route policies, keys or user quotas change.

One count operation uses the existing session credential, TLS transport and fixed official endpoint. Redirects and environment proxies stay disabled. A five-second total timeout, 4 MiB request limit and 4 KiB response limit apply. Duplicate JSON keys, wrong object tags, booleans, negative/overflow counts, HTTP failure or timeout retain the original full-model bound. No count-response diagnostics or input bodies are persisted or exposed. Counting sends the same already-authorized, permission-filtered input to the configured provider; it does not generate a reply. No invoice/zero-cost guarantee is asserted.

`prepare_usage_bound` is an optional async preparation seam. Existing sync `bound` and fake/other bounders retain their contract. Direct/group initial preparation occurs before the one-time claim. Each governed physical attempt/retry/fallback prepares before turn reservation and accounting START; the existing monotonic deadline is checked again afterwards. The monetary guard reads the same cached count synchronously inside its transaction, making no remote call there. Input is charged for every generated attempt as before.

Counts/failures have a 30-second bounded process-local cache of at most 64 input digests and numeric results; no prompt, credential, raw error or response is stored. Clipping the requested output reuses the unchanged input projection. A missing/expired count always restores the full trusted capacity. Each attempt obtains its own reservation; cached counts do not make retries or group speakers free. The documented service/tokenizer and alias remaining consistent between count and generation is an explicit continuity assumption. Actual usage above any reserved bound still stops with the existing integrity error.

The ordinary OpenAI settings hint now reflects request-based admission, with conservative fallback. Other provider estimates are not silently accepted, and the UI does not promise arbitrary proxy compatibility.

## Verification

Source review, Ruff lint/format and TypeScript/ESLint are performed. Core/desktop compilation and a new separate portable artifact are recorded in HANDOFF.md when completed. Under AGENTS.md section 20 no automated tests, smoke checks, provider/credential probes or user data writes are performed. User acceptance of this OpenAI path remains pending; prior DeepSeek acceptance does not establish it. Existing tests are preserved; maintenance of newly async preflight expectations requires later explicit testing authorization.
