# dreamtalk — Codex Project Constitution

This file is a permanent instruction for all Codex work in this repository.

The public project name is dreamtalk. Existing `livingworld` code, storage and protocol identifiers remain compatibility boundaries; see [PROJECT_IDENTITY.md](docs/architecture/PROJECT_IDENTITY.md). This naming change does not alter any product or architecture rule below.

Last reconciled with the user's confirmed instructions: 2026-09-29. Later explicit user instructions take precedence over this file. Earlier numbered task restrictions describe those tasks, not a permanent prohibition on subsequently authorized product work.

Before starting ANY dreamtalk engineering task:

1. Read this file completely.
2. Read the current task specification completely and read `HANDOFF.md` when present.
3. Read the architecture/product documents relevant to the task.
4. Inspect the existing repository before modifying anything.
5. Do not begin implementation until the task boundary is understood.
6. Before starting a new feature, search for mature existing implementations. Compare reuse, integration and the existing code; choose the best product effect and maintenance cost. Record the investigated sources/version, licensing and the concrete reuse decision. Do not duplicate a solved capability merely to keep the implementation independent.

Apply the user's latest explicit decisions when they supersede older rules. Stop the affected work only when an essential product/architecture decision remains genuinely undefined; do not ask the user to reconfirm decisions already made.

---

# 1. What dreamtalk is

dreamtalk is NOT:

- a chatbot wrapper;
- a demo;
- an MVP that will later be rewritten;
- a collection of independent agents constantly talking to each other;
- a project whose purpose is to accumulate trendy frameworks.

dreamtalk is intended to become a production-grade, resume-level AI persistent-world product.

The final product should allow a user to enter a persistent virtual world populated by characters that appear to continue living even when the player is not actively talking to them.

The product must be usable by ordinary users who do not understand prompts, samplers, RAG, Agent frameworks, databases, or model APIs.

The internal architecture may be sophisticated.

The external experience must remain simple.

The project is built as a real finished product from the beginning.

We build the final architecture incrementally.

We do NOT intentionally create disposable architecture merely to obtain a quick demo.

---

# 2. Core product vision

The important illusion dreamtalk must create is:

"The world continues to exist when I am not looking at it."

Immersive roleplay chat is the core experience. World progression and player-known events support conversations and supply topics; they must not turn the ordinary interface into a simulation dashboard. Remote direct and group chat are allowed without moving participants.

A player may be talking to Alice while elsewhere:

- Belle is doing something;
- Billy meets Banyue in a cafe;
- two characters form a relationship;
- an event develops;
- another character learns something;
- the player knows none of this yet.

These hidden changes are NOT automatically exposed in the UI.

The player may learn about them later through natural channels:

- a character mentions what happened;
- the player encounters the characters together;
- a message arrives;
- a news item appears;
- the player witnesses an event.

The player must NOT receive omniscient system notifications for hidden world events.

---

# 3. Responsibility split

dreamtalk has three major intelligence layers.

## Director

The Director manages the world.

It is responsible for concepts such as:

- macro world simulation;
- character activities;
- character encounters;
- relationship opportunities;
- events;
- schedules;
- world pacing;
- story opportunities;
- proactive contact opportunities;
- planning future possibilities.

The Director DOES NOT directly write final character dialogue.

The Director DOES NOT directly mutate canonical world state.

The Director produces proposals/plans.

## Character Agent

A Character Agent is deliberately narrower.

Its primary responsibilities are:

- maintaining and using that character's own memories;
- using only information that character is allowed to know;
- expressing the character's personality;
- communicating naturally with the player;
- proposing world-impacting consequences when necessary.

A Character Agent is NOT responsible for continuously simulating its whole life.

It does NOT independently run a permanent autonomous planner for every mundane action.

The Director handles the miscellaneous world-simulation work.

## Deterministic World Kernel

The World Kernel is the authoritative executor.

LLMs may propose.

The Kernel decides what becomes real.

Only the Kernel may commit canonical WorldEvents and update authoritative projections.

Never allow an LLM response to directly write WorldTruth.

---

# 4. Hidden knowledge is a core feature

The following concepts MUST remain distinct:

WorldTruth
CharacterBelief
PlayerKnowledge

Example:

WorldTruth:
Billy met Banyue at a cafe.

Billy:
knows this.

Banyue:
knows this.

Belle:
may not know this.

Player:
may not know this.

A Character Agent must never gain knowledge merely because the fact exists in the database.

Permission filtering must happen BEFORE semantic retrieval or prompt assembly.

Do NOT implement secrecy as:

"give the model all information and tell it not to reveal secrets."

That is architecturally unacceptable.

Characters may also hold incorrect beliefs.

A CharacterBelief is not automatically WorldTruth.

---

# 5. Relationships

Relationships exist internally but are NOT exposed to normal players as numerical game statistics.

Do NOT design normal UI such as:

Affinity: 82
Trust: 76
Relationship +5

The real-world feeling is more important.

Players should infer relationships from:

- behavior;
- tone;
- willingness to help;
- willingness to share information;
- proactive contact;
- conflict;
- remembered experiences.

Developer/debug tools may inspect internal relationship state.

Relationships may be directional.

A → B does not have to equal B → A.

---

# 6. Player presence

The player can physically exist in only ONE location at a time.

This is a hard world invariant.

Remote communication such as messaging is allowed regardless of location.

Offline/inactive does not mean the player's physical location disappears.

The player must not automatically become a witness to events merely because an event occurs at the location where the player was last stored while inactive.

---

# 7. Offline world behavior

The world should feel as though time continues while the player is offline.

However, a closed desktop application does NOT need to literally run a background AI process all night.

The intended architecture is catch-up simulation:

last known world state
+
elapsed real time
+
existing world plan
+
deterministic simulation
+
limited Director replanning when required

= reconstructed world progression when the user returns.

This must preserve the user experience:

"I came back and things happened while I was away."

without wasting API calls continuously while the app is closed.

---

# 8. Proactive character contact

The player has a state similar to:

Busy
Available

When Busy:

ordinary proactive character contact should not occur.

The world itself may continue.

When Available:

the Director may decide that a character has a legitimate reason to contact the player.

A proactive reason may initiate ONE unsolicited contact.

If the player does not answer, the character must not repeatedly send:

"Are you there?"
"Hello?"
"Why aren't you replying?"

for the same reason.

A materially new event may create a new reason.

That is different.

Multiple characters may proactively contact the player together.

However, they MUST share the same purpose.

Example:

Nicole + Anby + Billy
→ asking whether the player will accept one commission.

Valid.

Alice:
asks to go shopping.

Belle:
asks about a Hollow emergency.

Billy:
asks about a movie.

All sent together merely because the player became Available.

Invalid.

Multi-character proactive contact is represented conceptually as one Outreach Episode with one shared purpose.

---

# 9. Director API cost rule

The Director MUST NOT use the LLM as a slot machine.

Forbidden design:

every 10 minutes
→ call LLM
→ "what happens now?"

every character movement
→ call LLM

every possible encounter
→ call LLM

Instead:

one Director planning call should solve many related planning questions for a Planning Window.

A Director Plan may contain:

- character activity blocks;
- encounter opportunities;
- relationship opportunities;
- event candidates;
- story hooks;
- proactive contact opportunities;
- contingencies.

Candidates enter an Event Reservoir.

Deterministic code later decides whether each candidate is:

activated;
deferred;
cancelled;
expired.

Normal selection should consume zero LLM tokens.

Replanning occurs only when:

- the planning window is nearly exhausted; or
- enough important assumptions have changed that a meaningful portion of the plan is invalid.

Do NOT trigger a new LLM call for every minor deviation.

---

# 10. AI World Builder and Character Builder

dreamtalk must eventually allow ordinary users to type things such as:

"Create the Zenless Zone Zero world."

or:

"Create Hoshimi Miyabi from Zenless Zone Zero."

The product should research relevant sources and construct usable world/character data automatically.

The architecture is:

Research
→ Evidence
→ Claims
→ Conflict Detection
→ Draft
→ Preview
→ User Confirmation
→ Commit

Never allow web research output to silently become canonical world truth.

Sources and provenance matter.

The system should eventually support updating a world when new source material appears.

---

# 11. SillyTavern relationship

SillyTavern is:

- a reference product;
- a source of useful UX lessons;
- a compatible ecosystem target.

The user no longer requires dreamtalk to implement every capability independently.
Prefer a mature existing component when it fits the product, reduces maintenance,
and preserves the Core's authority and privacy boundaries. SillyTavern may be
evaluated as a reusable component or integration, not only as inspiration.

We may independently implement compatibility with:

- Character Card V2;
- Character Card V3;
- PNG/JSON cards;
- Lorebooks.

The current Apache-2.0 repository and SillyTavern's AGPL-3.0 code have different
licensing obligations. Do not paste or incorporate its implementation into this
repository without a concrete license and distribution decision. Reusing its
public formats, documented behavior, or a separately integrated runtime is a
different engineering choice; evaluate each against maintenance, licensing,
security, and the existing World Kernel/knowledge invariants. See
[ADR-0001](docs/architecture/ADR/0001_reuse_mature_projects.md).

---

# 12. Current architectural direction

The project currently follows:

React + TypeScript
        ↓
versioned HTTP/WebSocket API
        ↓
Python dreamtalk Core
        ↓
Application / Domain / Kernel
        ↓
Persistence

Desktop:

Tauri v2 Rust host
→ supervises Python Core
→ provides OS integration

Desktop storage baseline:

SQLite WAL + FTS5

Future server/cloud baseline:

PostgreSQL + pgvector

Optional later deployment/benchmark profile:

MySQL InnoDB + Qdrant
Optional Redis only when distributed execution actually requires it.

Do not introduce infrastructure because it looks impressive.

Every dependency must solve an actual problem.

---

# 13. Engineering philosophy

The user does NOT want:

"good enough."

The user wants:

"a strong final implementation."

However, "final quality" does NOT mean unnecessary complexity.

The desired standard is:

correct
maintainable
explainable
testable
product-grade

NOT:

maximum number of libraries;
maximum number of abstractions;
maximum number of microservices;
maximum number of files.

Prefer the simplest architecture that satisfies the final product requirements.

---

# 14. User's working style

The user has authorized autonomous progress toward a usable complete product and does not want to provide a separate prompt for every implementation step. Complete concrete product slices and continue other authorized, well-defined work; do not stop merely because one historical stage/task ended.

The user delegates routine technical and component choices to the engineer and judges the achieved product effect. Choose and proceed within the confirmed product/Kernel/knowledge/budget boundaries; do not repeatedly request component-selection approval. Investigate mature implementations before each new feature and include the reuse decision in the completion report.

An explicit current task boundary still applies. A request to only answer, only edit documentation, or stop after a particular task must be respected.

For local uncertainty or a difficult implementation branch: record confirmed facts, the unresolved point and useful evidence; skip that branch and continue independent work that is clear. Do not guess unresolved semantics or repeatedly attack a blocked path.

Stop the dependent work and report when a genuinely new product direction, public contract, persistence, security or financial decision requires the user's judgment, or a frozen architectural boundary would need to change. Ordinary implementation choices are the engineer's responsibility.

Do not implement speculative features or placeholder production behavior that violates frozen architecture. Prioritize usable chat, real settings and configuration effects over extra architecture for its own sake.

The user values:

- understanding why something exists;
- clear progress;
- verifiable completion criteria;
- avoiding unnecessary detours;
- high final quality;
- not wasting time repeatedly trying a broken path.

Every technology that enters the final resume should be explainable.

Therefore architecture should remain understandable, not artificially complicated.

---

# 15. CRITICAL: Anti-stuck / anti-loop policy

Codex MUST NOT repeatedly attack the same failing operation without new evidence.

This is a hard project rule.

## Same-action retry rule

If exactly the same action fails twice for substantially the same reason:

STOP repeating it.

Do one of:

- inspect logs/state;
- use a different method;
- reduce the problem;
- verify assumptions;
- report the blocker.

A third identical retry is only justified if NEW evidence indicates the previous failure condition has changed.

"Maybe it works this time" is not evidence.

## GUI failure rule

GUI automation is a last-mile tool, not a debugging strategy.

If:

- a window becomes unresponsive;
- a button does not respond;
- a GUI process hangs;
- an installer/UI step behaves unexpectedly;

do NOT repeatedly click it.

Prefer:

CLI
logs
process inspection
configuration files
direct API calls
build output

whenever equivalent verification is possible.

Do not spend large amounts of task time fighting a frozen graphical window.

## Blocker timebox

If one implementation/debugging branch produces no meaningful new information for approximately 10 minutes:

stop that branch and reassess.

Ask:

"What assumption am I currently making?"

"What evidence would distinguish the likely causes?"

"What cheaper diagnostic can I run?"

If the same local blocker still cannot be resolved after approximately 20 minutes of focused diagnosis, stop that branch, record:

- what is blocked;
- exact error;
- what was tried;
- evidence collected;
- likely causes;
- recommended next action.

Then continue independent, well-defined work. Ask the user only if their decision or intervention is necessary. These timeboxes are limits, not permission to keep hammering a problem that should already have been set aside.

## Long-running command rule

A legitimately long build command is different from being stuck.

Long commands are allowed when:

- the process is producing observable progress;
- CPU/disk/network activity or logs indicate work;
- its expected duration is reasonable.

A silent/unresponsive process without evidence of progress must not be assumed healthy indefinitely.

## Failure escalation

When blocked, use this sequence:

1. inspect the existing failure evidence;
2. capture exact evidence;
3. inspect logs/state;
4. form a hypothesis;
5. check the hypothesis with the cheapest authorized inspection or build step;
6. try one alternative approach;
7. if still blocked, record and skip the branch; report any required user decision or intervention.

Never use:

retry
retry
retry
retry
retry

as a debugging method.

---

# 16. Tool discipline

Before using a GUI, ask whether CLI/API/file inspection can accomplish the same goal.

Prefer deterministic tools.

Examples:

Prefer:
git status/diff/log
rg and source/configuration inspection
logs
process status
filesystem inspection
build output

over:

opening applications repeatedly
clicking buttons repeatedly
waiting for UI animations
guessing whether a window "probably worked"

Do not write or run automated tests or smoke checks unless the user explicitly requests them again; see section 20. GUI inspection is not evidence that unperformed acceptance tests passed.

---

# 17. Scope discipline

Respect the current explicit task boundary. Historical task instructions to stop after C-003, C-004, etc. do not override the user's later authorization to continue the product autonomously.

When the active request is to continue the project, complete the next useful, sufficiently specified slice. Do not ask for another stage prompt merely to proceed.

If a future feature needs an interface now, create the smallest clean seam required.

Do NOT implement the future feature itself.

If you discover something that should be changed later:

record it under:

Future consideration

or:

Unresolved issue

Do not expand a narrowly scoped current task. Under ongoing product authorization, recorded future work may be taken up when its requirements are clear and it advances the agreed product.

---

# 18. No architecture invention without permission

If an architectural decision has already been frozen:

follow it.

If a new problem requires changing a frozen architectural decision:

STOP and report.

Do not silently decide:

"Redis would be easier so I added Redis."

"LangGraph simplifies this so I rewrote the runtime."

"Electron was easier so I replaced Tauri."

"MongoDB fits this object better so I added MongoDB."

These are architectural decisions and require review.

---

# 19. Dependencies

Before adding a dependency, answer:

1. What exact problem does it solve?
2. Can existing dependencies solve it adequately?
3. Is it required by the currently authorized product work?
4. What maintenance/runtime cost does it introduce?

If there is no strong answer:

do not add it.

---

# 20. Current verification responsibility

The user explicitly assigned testing and acceptance to themselves. Until they change this instruction:

- Do not add or run automated tests, test suites, browser/desktop smoke checks, or live-provider smoke calls.
- Preserve existing tests and CI; do not delete or weaken them to hide a failure.
- Source inspection, Git diff review, formatting/lint/type checks and necessary compilation/packaging remain allowed. Report them as such, not as runtime acceptance.
- Inspect build scripts for embedded tests. Use the existing `--build-only` portable-packaging option when producing an artifact without smoke checks.
- Do not make paid model calls or probe API credentials merely to validate configuration without explicit authorization.
- Clearly distinguish implemented code, successful compilation, historical test evidence and user-verified behavior. A build does not prove that chat, settings or lifecycle works.

Existing Kernel, knowledge-isolation, idempotency and budget invariants remain mandatory even while automated testing is delegated to the user.

---

# 21. Completion reports

At the end of a task report:

1. 本轮做了什么 — concrete changes, why they help, actual checks/build results, and commit/status when applicable.
2. 接下来要做什么 — the next useful work in priority order.
3. 疑问和建议 — unresolved decisions, risks or required user actions; say none when there are none.

Keep routine reports concise. An update is not a request to end ongoing authorized development or to ask for another prompt. Follow a current request for a different report format when one is given.

Do NOT hide:

- skipped tests;
- environment limitations;
- partially verified behavior;
- warnings;
- failures.

If something was not verified, explicitly state that it was not verified.

---

# 22. Stop conditions

STOP and ask/report instead of continuing when:

- the task contradicts frozen architecture;
- an essential new product, public-contract, persistence, security or financial choice is genuinely undefined;
- a narrowly scoped current task cannot be completed without materially different work;
- user data or Git history may be destroyed;
- a migration may irreversibly modify real user data;
- secrets/credentials would need unsafe handling;
- the user must intervene to unblock the remaining work.

Stop the affected branch; continue unrelated authorized work where safe. A local technical blocker or missing user acceptance is not permission to guess, falsely claim success, or spend two hours blindly retrying.

---

# Final rule

Optimize for:

correct progress per unit time

not:

visible activity.

Being busy is not the goal.

Moving dreamtalk toward the finished product is the goal.
---

# 23. Confirmed product experience and release boundary

The following later user decisions apply alongside the architecture above; details are in [PRODUCT.md](PRODUCT.md), [PRODUCT_SPEC.md](docs/product/PRODUCT_SPEC.md) and [CHAT_MODEL.md](docs/architecture/CHAT_MODEL.md):

- PC-first, simple Chinese interface with four bottom tabs in order: 聊天 / 通讯录 / 设置 / 我. Use the available desktop width and familiar WeChat-style navigation, not a phone-sized frame.
- Create/select a World before importing cards/books. Contacts and conversations are world-scoped; confirmed updates affect only the selected World. A runtime Character is created/reused on first opening chat, not by importing its card.
- Bind one local Player per World; a newly entered World starts the Player at 家. “可用 / 忙碌” describes unsolicited-contact availability, not network connectivity.
- Keep general self-description and world-specific identity separate; world-specific identity takes precedence. Put player-known world events at the top of the chat list as topics.
- Public world background may be shared with all characters. Lorebook entries remain hidden by default until explicitly exposed in that World; imported hidden plot material must not leak into prompts.
- Persisted group messages are visible to every fixed member, including silent members. Exposure is not WorldTruth, CharacterBelief or automatic EpisodicMemory.
- Use an independent group speaker scheduler based on accepted personas and shared dialogue. A unique `@` selects the next speaker; the world Director remains the batch planner.
- A player message starts one bounded turn. Input plus output for selection, every character, retry and fallback share the hard Token ceiling. Before every physical call, require a trustworthy conservative reservation; stop early rather than guess or exceed it.
- Validated runtime dialogue sends directly. Persistent authored/generated content still requires Draft → Preview → Commit.
- Prefer mature projects/components where they fit, subject to section 11; the user no longer requires independent implementation.
- The repository is intended for GitHub open source under Apache-2.0. Do not push or publish before the user completes final acceptance and explicitly approves it. Keep `D:\LivingWorld` and existing app-data/protocol identifiers until a separately approved migration.

This section and sections 14–22 replace the former blanket instruction to halt on every uncertainty and the former automatic-testing/stage-by-stage-stop workflow.

# 24. Approved Director runtime boundary (2026-09-29)

The user explicitly approved the recommended [Director proposal](docs/proposals/2026-09-29-director-runtime.md): per-world default off, first enable consents to background model usage, then compliant runtime batches are accepted automatically. Each window is six hours of WorldTime; replan at window end or when at least two candidates and at least half the original batch are invalid. Failed/interrupted/empty plans require an explicit new request, never an automatic provider replay.

This resolves the runtime WorldPlan part of P-16 separately from authored cards/books and reviewed conversation summaries. DIRECTOR may propose only existing placed Characters' typed routine activities/movement, through Kernel consent, candidate, revision, location and occupancy checks; it never moves Player or writes final dialogue, private knowledge or relationships. Closing prevents new work/late result activation; already admitted provider work may charge. PAUSED does not execute candidates or admit a new plan. Outreach purpose/episode policy remains a later concrete decision. This supersedes the older C-006B Director prohibition only for this approved routine action.


# 25. Approved manual reply recovery (2026-10-03)

The user explicitly approved an independent paid generation attempt after a failed
reply. It is limited to the latest player message with no persisted Character reply.
The player explicitly confirms the current token ceiling and model usage; each new
attempt has its own one-time claim and shares that attempt's ceiling across selection,
retries/fallbacks and all speakers. The original message is not duplicated; original
turns, usage and claims remain durable and are never reset. Running or unknown results
cannot be replayed. A pending attempt may be manually dispatched using its saved ceiling.
Only a recorded terminal validation failure or a known interrupted local execution may
permit a new attempt; old untracked claimed turns remain unknown. No startup, refresh or
background process automatically invokes the provider for reply recovery. This narrowly supersedes the
single-ceiling-per-original-message clause in section 23 for this explicit new attempt.

# 26. Approved character encounters (2026-10-03)

The user explicitly approved [the first encounter slice](docs/proposals/2026-10-03-character-encounters.md).
This narrowly extends section 24: a per-world default-off opt-in permits the existing
six-hour Director batch to propose optional brief greetings between two placed
Characters. The initial ceiling of eight is superseded by the later user-approved pacing below. Kernel admits only actual co-presence during both planned, active rest/leisure
intervals, with unchanged presence revisions, current consent/binding/plan and an unpaused
world. The execution window is at most five minutes; the same pair meets at most once in
six continuous hours of WorldTime. No missed/offline encounter is backfilled.

Kernel atomically records CharactersMet v1, event-time observations, candidate outcome and
idempotent receipt. Only participants and authorized physically present observers know it;
remote group membership grants no physical observation. Chat can recall a brief meeting,
never infer unrecorded private dialogue, task results or relationship changes. Players are
not moved. Disabling cancels pending encounters while preserving facts. New encounters use
the next normal batch, do not invoke a per-encounter API and do not change the existing
routine invalidation/replanning threshold or budget. No automated/runtime/provider testing
authorization is implied; section 20 still applies.

## Later approved encounter pacing (2026-10-04)

The user accepted slower encounters and continuous co-presence deduplication. Each
accepted plan may propose and execute at most two ordinary brief greetings (zero is
valid). Kernel admission also limits each Character to one first recorded counterpart
in a rolling 24 hours of WorldTime; both participants must qualify. Previously greeted
pairs do not spend the new-counterpart allowance, but still obey the per-plan ceiling,
six-hour pair cooldown and continuous co-presence rule. One ordinary greeting is recorded
per uninterrupted same-location stay; an actual canonical departure by either participant
is needed before considering another. Same-location routine/revision changes, restart and
disable/re-enable do not reset the policy. Preserve old facts, stable UUIDs, consent and
CharactersMet v1 replay. Rejected encounters neither invoke a replacement provider call
nor contribute to routine invalidation/replanning. A brief greeting does not imply name
exchange, formal introduction, shared task results or relationship progression. Existing
independently authorized familiarity is preserved; formal new actions remain outside this
slice. Reuse investigation and exact policy are in
[encounter pacing research](docs/research/2026-10-04-encounter-pacing-reuse.md).
Section 20's testing restrictions remain unchanged.

## Later approved shared leisure lifecycle (2026-10-04)

The user explicitly approved [the shared leisure proposal](docs/proposals/2026-10-04-shared-activities.md).
This narrowly extends sections 24/26: an independent per-world default-off opt-in permits
two previously actually greeted Characters to share 15–30 WorldTime minutes of overlapping
same-kind rest/leisure routines at one existing location in the same Director batch. Ordinary
greetings and shared starts together consume at most two social opportunities per plan;
each Character may start one shared activity per rolling 24 hours, with a six-hour pair cooldown.
Kernel atomically records SharedActivityStarted/Ended/Interrupted v1 with observations and
receipts. Normal completion requires actual continuous presence/activity and elapsed duration;
departure, routine change, withdrawal, plan replacement or unconfirmed offline continuity
interrupts it. Missed completion is not backfilled. No per-activity API, Player movement,
dialogue/task/asset results or relationship changes are authorized. Planning uses the existing
approved input, not new encounter-history or private-memory export. Observation and chat
isolation and limits remain unchanged. Section 20 testing responsibility still applies.


# 27. Confirmed scope correction (2026-10-04)

The user explicitly rejected the unsolicited "shared commissions" direction and said
"不要乱加东西". Only advance already confirmed product requirements and their fixes,
reliability and usability improvements. A general "continue the project" instruction
does not authorize inventing new product goals or treating the engineer's suggestions
as the user's requirements. Discuss a genuinely new product direction before implementation.

Shared commissions, patrol missions, quest/reward/combat systems are not approved and
must not be the default next step. References to these as future recommendations in
older handoff/research documents are withdrawn recommendations, not authorization.
Preserve the explicitly approved routine/encounter/shared-leisure boundaries and existing
chat, memory, world-event and offline-contact requirements. Ordinary technical choices
and well-defined improvements within those requirements remain delegated; do not ask
the user to reconfirm settled decisions. Section 20 testing responsibility is unchanged.
