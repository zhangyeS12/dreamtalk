# dreamtalk — Codex Project Constitution

This file is a permanent instruction for all Codex work in this repository.

The public project name is dreamtalk. Existing `livingworld` code, storage and protocol identifiers remain compatibility boundaries; see [PROJECT_IDENTITY.md](docs/architecture/PROJECT_IDENTITY.md). This naming change does not alter any product or architecture rule below.

Before starting ANY dreamtalk engineering task:

1. Read this file completely.
2. Read the current task specification completely.
3. Read the architecture/product documents relevant to the task.
4. Inspect the existing repository before modifying anything.
5. Do not begin implementation until the task boundary is understood.

If a task instruction conflicts with this file, STOP and report the conflict instead of guessing.

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

The user prefers a clear complete roadmap.

Work is performed stage by stage.

A stage must be completed and validated before proceeding.

Do not secretly begin later stages because:

"it was easy to add while I was here."

Do not expand task scope.

Do not implement speculative features.

Do not create placeholder production behavior that violates frozen architecture.

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
test commands
direct API calls

whenever equivalent verification is possible.

Do not spend large amounts of task time fighting a frozen graphical window.

## Blocker timebox

If one implementation/debugging branch produces no meaningful new information for approximately 10 minutes:

stop that branch and reassess.

Ask:

"What assumption am I currently making?"

"What evidence would distinguish the likely causes?"

"What cheaper diagnostic can I run?"

If the same blocker still cannot be resolved after approximately 20 minutes of focused diagnosis:

STOP.

Report:

- what is blocked;
- exact error;
- what was tried;
- evidence collected;
- likely causes;
- recommended next action.

Do not burn another hour silently.

## Long-running command rule

A legitimately long build/test command is different from being stuck.

Long commands are allowed when:

- the process is producing observable progress;
- CPU/disk/network activity or logs indicate work;
- its expected duration is reasonable.

A silent/unresponsive process without evidence of progress must not be assumed healthy indefinitely.

## Failure escalation

When blocked, use this sequence:

1. reproduce once;
2. capture exact evidence;
3. inspect logs/state;
4. form a hypothesis;
5. test the hypothesis with the cheapest targeted test;
6. try one alternative approach;
7. if still blocked, report.

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
pytest
cargo test
npm test
curl/TestClient
logs
process status
filesystem inspection

over:

opening applications repeatedly
clicking buttons repeatedly
waiting for UI animations
guessing whether a window "probably worked"

GUI smoke testing is useful only for validating an actual user-visible integration after underlying components are already verified.

---

# 17. Scope discipline

Every engineering task has an explicit boundary.

If assigned C-003:

complete C-003.

Do not begin C-004.

If a future feature needs an interface now, create the smallest clean seam required.

Do NOT implement the future feature itself.

If you discover something that should be changed later:

record it under:

Future consideration

or:

Unresolved issue

Do not expand the current task unless the task cannot be correctly completed without doing so.

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
3. Is it required by the current task?
4. What maintenance/runtime cost does it introduce?

If there is no strong answer:

do not add it.

---

# 20. Testing philosophy

Tests are not a checkbox.

The important question is:

"What invariant does this prove?"

Especially important invariants include:

- LLM cannot directly mutate WorldTruth;
- one player cannot occupy two physical locations;
- duplicate commands do not duplicate events;
- projections can be reconstructed;
- Character A cannot read Character B's private knowledge;
- Player cannot see hidden world facts;
- one proactive reason cannot spam multiple messages;
- crash/retry cannot duplicate world changes.

Prefer meaningful invariant/integration tests over large numbers of trivial tests.

Do not report success only as:

"300 tests passed."

Explain what important behavior was proven.

---

# 21. Completion reports

At the end of a task report:

- what changed;
- why;
- tests performed;
- important invariants proven;
- commit hash;
- git status;
- unresolved issues;
- any shortcuts or compromises.

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
- a required architectural choice is genuinely undefined;
- accomplishing the task would require expanding scope substantially;
- the same technical blocker persists after disciplined diagnosis;
- user data or Git history may be destroyed;
- a migration may irreversibly modify real user data;
- secrets/credentials would need unsafe handling;
- successful implementation cannot be distinguished from a broken implementation with available evidence.

Stopping with a precise engineering report is preferable to spending two hours blindly retrying.

---

# Final rule

Optimize for:

correct progress per unit time

not:

visible activity.

Being busy is not the goal.

Moving dreamtalk toward the finished product is the goal.
---

# 用户补充：遇到不确定或难以解决的问题必须停止并汇报

在 dreamtalk 工作中遇到不确定问题或难以解决的问题时，必须立即停止相关工作并向用户汇报，不能自行猜测、擅自决定或持续死磕。

汇报应明确说明：

- 当前阻塞或不确定的事项；
- 已确认的事实与仍不确定的部分；
- 已尝试的方法、具体错误及已收集的证据；
- 建议的下一步及需要用户决定的内容。

等待用户明确下一步后，再继续相关工作。

本补充是用户对第 15 节和第 22 节的进一步要求：遇到上述情况后，不得以重试次数或 10/20 分钟时间窗口为由继续自行死磕。
