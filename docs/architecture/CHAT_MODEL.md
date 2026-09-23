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

## Persistence boundary

Conversation and Message are durable interaction records. They are not entries in
the canonical WorldEvent ledger. A durable player-send receipt prevents an HTTP
retry from appending the same user message or repeating a completed turn. A turn
whose provider outcome is uncertain is not silently regenerated; unresolved
usage remains subject to the normal LLM accounting integrity rules.
