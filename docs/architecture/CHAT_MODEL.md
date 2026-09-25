# Roleplay Chat Model

Status: approved product and architecture decisions; implementation is incremental.

Related concepts: [Conversation and Message](DOMAIN_MODEL.md#21-conversation),
[system responsibilities](SYSTEM_OVERVIEW.md#角色扮演聊天边界), and
[confirmed product decisions](../product/PRODUCT_SPEC.md#已确认的产品补充决策).

## Purpose

Chat is the main player experience. A Conversation is a durable communication
history between the current world's bound Player and one or more runtime
Characters. Chat messages provide roleplay and topics; they are not WorldEvents,
WorldTruth, CharacterKnowledge, or PlayerKnowledge by themselves.

## Runtime character identity

An imported CharacterDefinition is a world-scoped contact, not a runtime
Character. The first time a player opens a conversation with that contact, Core
creates or reuses its runtime Character identity. Importing a card alone does
not create a runtime Character. A character may be contacted remotely; opening
or sending a chat message does not move the Player or Character.

The link from an accepted world-content lineage to a runtime Character is
world-scoped. Replacing a card in one world does not replace another world's
snapshot or identity. A confirmed update supplies the current authored persona
for later generation while preserving the existing runtime Character and
conversation history.

The current implementation can open and list durable direct-conversation
identities for the selected local Player. Opening a current accepted character
contact follows its replacement lineage back to the first accepted import, then
uses stable world-scoped IDs for one runtime Character and one direct
Conversation per Player/contact pair. The existing `CreateCharacter` command
owns the canonical `CharacterCreated` event; opening a Conversation does not
itself emit a WorldEvent, move either participant, or create an Observation.
Replacing an accepted card preserves that runtime identity. An unselected
Player, cross-world import, or stale import cannot open a conversation.

The schema has a separate participant relation so group conversations can share
the same durable identity boundary. An authenticated group-create endpoint now
accepts two or more distinct current Character Card imports from the selected
Player's world. It resolves replacement roots, reuses the same lazy runtime
Character creation path as direct chat, and atomically stores one group
Conversation and its participants. The request ID identifies a retried create;
it cannot be reused for a different participant set. A separate owner-scoped
group-list endpoint reads these records. The existing direct-list endpoint and
ordinary UI still show direct conversations only. Group message sends are
explicitly rejected until the independent speaker scheduler and shared-turn
budget are connected; this avoids storing a group turn that cannot be safely
completed. Creating a group does not move anyone, create an Observation, or
invent a WorldEvent beyond the existing canonical CharacterCreated events for
newly opened contacts.

The current direct-conversation API opens/lists identities only. An authenticated POST endpoint now persists a Player
message and its pending turn through the application service, returning the same
result for a repeated request ID. It returns `202 pending`; it does not dispatch
a model or promise a Character reply. The ordinary UI opens a contact and
shows the durable conversation in the Chat tab. Message sending is enabled only
when a suitable production chat model and session credential are available.

An authenticated transcript read endpoint now returns stored messages in their
Conversation order for the currently selected local Player only. Missing Player
selection and cross-world/foreign Conversations fail closed. This read path does
not create a Message, Observation, KnowledgeAssertion, or WorldEvent. The Chat tab reads
this endpoint when a Conversation is opened and renders the durable ordered
transcript. Switching worlds or Conversations discards a late response from the
previous selection. The Chat tab sends through the authenticated player-send
endpoint and asks for a direct reply only when one text-capable production model
or an explicit `character_dialogue` BALANCED route has trusted billable-token
bounds and a session credential. No model is chosen implicitly when several are
configured. Every candidate in that route must have a trusted bound; preflight
uses the largest candidate input bound before claiming the turn. The per-turn token ceiling is
saved locally in the UI and persisted with each player send; later setting changes
cannot alter an existing turn. An unavailable model disables sending.

The player-send POST endpoint requires bearer authorization and `X-Request-Id`. It rejects
an unselected Player, a foreign/world-mismatched Conversation, blank or oversized
text, invalid token ceiling, and a request ID reused for different semantics.
It creates no WorldEvent, Observation, or KnowledgeAssertion. A pending turn is
not retried or completed by process startup.

The authenticated direct-turn read returns `pending`, `claimed`, or `completed`
from the dispatch and reply records, always under selected-Player authorization.
The direct-reply POST reads the original PlayerSend and ceiling from persistence;
it accepts no client-supplied message or model output. It returns an already
committed reply without a new provider call. A claimed turn cannot be replayed,
including after an HTTP timeout or restart. The UI may query its state once but
does not resend the uncertain model request. Provider and validation failures
are presented with bounded error labels rather than prompt/output data.

## Direct and group conversations

- A direct conversation has one Player and one Character.
- A group conversation has one Player and the explicitly selected Characters.
- Group participants share one ordered transcript.
- One player message starts one bounded group turn. It does not start autonomous
  character-to-character chatter outside that turn.
- A group-turn scheduler chooses one speaker at a time from the conversation's
  accepted character personas and shared transcript. If the player explicitly
  addresses a participant with `@`, that participant speaks next. The scheduler
  is separate from the world Director; it does not plan the world, commit events,
  or write final character dialogue.
- The selected speaker's final dialogue comes from that character's agent,
  passes system validation, and is sent without per-message user preview.

## Shared token ceiling

The local chat setting is a hard maximum for one player-initiated turn. It counts
provider-reported input and output tokens for speaker selection and every
character response, including physical retries and route fallbacks. Before each
physical provider attempt, the system must reserve a conservative input-token
upper bound and the allowed output-token maximum against the same turn budget.
If the input bound is unavailable or cannot fit, no provider call starts. When
usage is reported, only the unused reservation is released. When usage is
missing or incomplete, the reservation remains consumed conservatively and no
further generation starts for that turn. No next speaker starts after the
remaining budget reaches zero.

The configured ceiling limits LLM token use; it does not estimate price. The
existing LLM usage ledger remains authoritative for factual usage and cost.

`ChatTurnTokenBudget` implements sequential reservation/settlement arithmetic.
The LLM execution/routing gateway now accepts the same turn budget across
invocations. Before each physical attempt it uses the selected candidate's
explicit trusted `ModelUsageLimits` to reserve the maximum billable input and
allowed output; a missing or estimate-only bound rejects before accounting
START or provider dispatch. Accounting START failure releases an undispatched
reservation. Terminal factual usage settles once, including for streams; an
interrupted/unknown attempt consumes its reservation and closes the turn.
Reported usage above the trusted bound closes the turn as an integrity failure
without rewriting the factual provider outcome. This is deliberately
conservative: a model whose full configured bound exceeds the remaining turn
budget cannot be called even for a short prompt. An internal direct-reply service
now creates one turn budget from the persisted ceiling and passes it through the
routed gateway. It checks the trusted input bound, reduces the requested output
cap to fit the turn, and checks route availability before claiming. It accepts only
a nonblank bounded reply with a complete stop or explicit refusal. Truncated,
wrong-invocation and over-bound responses cannot enter the transcript. This
service is composed into the production direct-chat HTTP/UI flow when one suitable
model or an explicit suitable BALANCED chat route is configured. Group scheduling
remains separate work.

## Information and content boundaries

- Prompt assembly uses the active world's accepted CharacterDefinition, the
  current Conversation transcript, and the local general/world-specific Player
  descriptions. The world-specific description has precedence when they conflict.
- Imported card fields, Lorebook text, profile text, and prior messages are
  untrusted content. They are data, never privileged system instructions.
- Only explicitly authorized Knowledge and Memory may be added to a Character
  context. Permission filtering happens before retrieval or prompt assembly.
- A message can contain a false claim. Receiving or reading it does not silently
  promote that claim into WorldTruth or PlayerKnowledge.
- Hidden WorldEvents are not supplied to the player or a Character merely
  because they exist. Any later event context must pass the relevant owner's
  knowledge boundary.

The internal direct-chat context builder resolves the current accepted card
from the Conversation's world-scoped replacement lineage, then reads only the
selected Player's transcript up to the current sent message and that Player's
general/current-world profile. It also requests recent EpisodicMemory through
a reader bound to that Conversation's Character identity. At most 12 recent
memories are considered and at most 8 KiB of their UTF-8 content enters the
prompt; a larger individual memory is skipped. The builder verifies each returned
memory's owner again before assembly. Memory content and card/profile fields are
serialized as lower-trust user data under a fixed system instruction. Card-authored
system prompts, creator notes, raw import metadata, WorldTruth, hidden events,
other worlds, and other Characters' private memories are not added. Knowledge
assertions are not yet retrieved. The current-world profile is explicitly given
precedence over the general description. This builder prepares input only; it
does not dispatch a model or authorize any new knowledge.

The persisted transcript remains complete. Prompt assembly always includes the
current Player send, then retains the most recent complete prior turns while
staying within 32 messages and 96 KiB of message text. Delayed replies may
interleave with later sends; selection groups records by durable turn identity
and restores message position order in the prompt. The first older turn that
cannot fit ends the history window. This bounded window is only a prompt view;
it does not delete or summarize stored messages or weaken the physical-attempt
Token preflight.

## Persistence boundary

Conversation and Message are durable interaction records. They are not entries in
the canonical WorldEvent ledger. A durable player-send receipt prevents an HTTP
retry from appending the same user message or repeating a completed turn. A turn
whose provider outcome is uncertain is not silently regenerated; unresolved
usage remains subject to the normal LLM accounting integrity rules.

`ChatTurnId` and `MessageId` identify committed records independently of
`RequestId`. The request identity plus a fingerprint of the resolved Player,
Conversation, text, and turn token ceiling protects the atomic player send.
Retrying the same request returns the original turn/message identities and
position; reusing it for different semantics fails. New requests append in
per-Conversation order. The initial durable status is `pending` and does not
itself trigger provider generation. The current schema stores player messages;
the sender columns hold an explicit Character identity for the validated reply
path. The internal direct-reply boundary can claim a pending turn once in
a durable `chat_turn_dispatches` row before provider work. A second or restarted
claimant cannot generate it again. A caller-provided, bounded nonblank reply
can be appended in transcript order; repeating the same completion returns
the committed message, while conflicting content fails. Claim and reply writes
are separate transactions. An interrupted claim remains unresolved without a
fabricated reply or automatic provider replay, because the provider outcome may
be unknown. The legacy `chat_turns.status = pending` field records the initial
player-send receipt; the claim and Character message establish later execution
state. The public API cannot write arbitrary Character text. The internal
direct-reply service generates and validates a reply through the governed LLM
gateway before committing it. This is direct-chat plumbing only; it does not
create an autonomous Character Agent or implement group speaker selection.
