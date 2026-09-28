# Group speaker-selection fix — 2026-09-28

User verified character/lorebook API generation, direct chat and explicit group @ mentions. Automatic group speaking failed. The screenshot shows the existing generic validation failure, including after an @ reply.

## Existing defect and reuse

`GroupChatReplyService` allowed only 64 generated tokens for both first and subsequent selector calls. Reasoning models can spend this allowance before producing any final Character ID. Selection is bypassed for the first @ reply, which explains the different execution paths. The first and later selectors also duplicated UUID parsing; valid IDs wrapped as a JSON scalar, a one-field object or a Markdown code block were rejected. No raw model responses were inspected, so truncation/formatting is a source-supported diagnosis rather than a capture of the user's precise response.

Investigated official mature implementation: Microsoft AutoGen SelectorGroupChat docs (dev documentation, accessed 2026-09-28), https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/selector-group-chat.html, and upstream main selector implementation, https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_selector_group_chat.py. MIT. Reuse the existing separation of selection and agent response, clear candidate-only prompt and single-valid-participant validation; no AutoGen source is copied or additional agent runtime installed. Existing governed routing, durable claims, local stdlib JSON/UUID parser and group context already provide the needed implementation.

Official provider semantics supporting the diagnosis: https://api-docs.deepseek.com/guides/thinking_mode/ (default thinking/high), https://api-docs.deepseek.com/api/create-chat-completion/ (max_tokens includes generated reasoning; length means incomplete output). The fix itself is provider-independent, with no DeepSeek-only branch.

## Change

- Both selection paths use the same request factory with a cap up to 8,192, further limited by configured model/application output cap and preflight remaining turn allowance. This is a maximum, not fixed consumption. Every selector and speaker still shares one persisted hard input+output turn budget, including retries and fallback.
- Both paths use the same full-response decoder. Accept a bare UUID/STOP, quoted JSON scalar, exact one-field `character_id` JSON object, or a single complete text/json/plain code block wrapping them. Reject duplicate/extra keys, multiple/prose choices, nonstring values, unknown participants, partial output, refusal and over-1,024-byte decision text. First selection cannot STOP; subsequent selection may STOP after a durable reply. Normalization does not repair truncated JSON or invent a speaker.
- Strengthen the candidate-only prompt and first-reply requirement. Selector receives public accepted personas and shared transcript, not private memories. Character generation retains its own knowledge boundary.
- Fixed safe HTTP labels distinguish selector output-limit and invalid selection; UI explains which stage failed. Other validation failures keep the existing generic label. No raw error/model text is sent.
- No retries are added, no historical pending/claimed turn is replayed, no Director/WorldEvent behavior or persistence schema changes.

## Verification boundary

Ruff/format, ESLint/TypeScript, source diff review and release packaging only. AGENTS delegates tests/acceptance to the user: no automated tests or live-provider calls, and existing tests are preserved. A mode=ro ledger read failed to open the local database; an immutable read returned no recent character-dialogue facts in that disk view. It may be stale and is not evidence that the live calls were absent. No user credential reads or database writes were performed.

Next acceptance: new unaddressed group message selects at least one member and can finish naturally; @ replies remain functional and later scheduling can finish; known malformed/limited selector outcomes show accurate bounded feedback. Other provider request-bound work remains separate.
