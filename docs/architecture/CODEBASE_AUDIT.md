# Q-001 Codebase Audit

> 2026-10-07接续：以下为原阶段审查记录。当前维护已收拢A007的回滚后回执恢复、A009的16组版本集合、A010的通用错误/凭据处理，并消除A014生产空回调的线程任务；其余业务分派、域结构校验、各类型编码器和全量回放仍保留。见[维护记录](../maintenance/2026-10-07-code-and-docs.md)，不把历史DEFER统一当作当前未处理，也不宣称全部清零。

Status: **Q-001A blocking decisions resolved; Inspector remains a separate task**

Audit baseline: `880032c522e9eca941b10ff2d04954e69f506519`
Scope: Stage 1–6 production Python, React/TypeScript, Rust desktop host, migrations, architecture tests and current architecture documents.

## 1. Decision

The repository has a strong set of typed domain boundaries, transactional persistence tests, permission-first knowledge/memory reads, deterministic scheduling, safe provider contracts and desktop bootstrap controls. The audit did not find evidence of SQLite access from the UI, provider code importing into the domain, or LLM code directly mutating canonical world state.

At the audited baseline, the Runtime Inspector could not be implemented safely. Three connected `FIX_NOW` findings made the requested real trace ambiguous:

1. a scheduled activation has no supported consumer that turns it into an `ActionProposal`;
2. a resulting Observation does not automatically form EpisodicMemory, by explicit C-007A design;
3. the repository currently has two ways to commit `PlayerMoved`, with different perception/activation side effects.

Building the requested `time → trigger → activation → action → WorldEvent → Observation → EpisodicMemory` flow without resolving these points would either fake a transition, add the deferred activation-consumption feature, or silently introduce automatic Observation→Memory behavior. All three conflict with Q-001 or frozen architecture.

### Q-001A disposition

Q-001A resolved the blockers without adding the Inspector or Stage C-007B behavior:

- **A-001 — resolved by architecture decision:** no Activation consumer and no automatic Observation→Memory were added. A later Inspector must expose explicit existing steps: a user-selected action goes through ActionResolution, and `RecordEpisodicMemory` is deliberately invoked with authorized Observation evidence.
- **A-002 — resolved in implementation:** legacy `MovePlayer` now adapts to `ActionResolutionService`; only the action pipeline can commit normal Player `PlayerMoved` state/event/perception/activation/receipt effects. Historical result-v1 receipts remain exact-retry compatible without re-executing the retired path.
- **A-003 — resolved in implementation:** after `CreateWorld` commits, an application lifecycle port registers it with `WorldSimulationRuntime`. Registration is serialized/idempotent; failure marks the runtime DEGRADED while preserving the committed World, event and receipt.
- **A-004 — resolved in documentation:** `SYSTEM_OVERVIEW.md` and `RUNTIME_FOUNDATION.md` now describe implemented Stage 5/6 and C-007A boundaries.
- **A-005 — resolved in implementation:** the discarded immutable `participant.leave()` loop was removed; `leave_all` remains the single persistence operation.

The `DEFER` and `ACCEPTABLE` findings below are unchanged and were not refactored by Q-001A.

## 2. Findings

### A-001 — No supported end-to-end runtime path from Activation to Memory

- **Severity:** `FIX_NOW` — substantial; blocks the Runtime Inspector acceptance path.
- **Exact locations:**
  - `services/core/src/livingworld/application/scheduler.py::SimulationSchedulerRuntime._run_world`
  - `services/core/src/livingworld/application/action_resolution.py::ActionResolutionService.execute`
  - `services/core/src/livingworld/application/memory.py::EpisodicMemoryService.execute`
  - `docs/architecture/SPARSE_ACTIVATION.md`, especially the statements that C-006C has no handler execution and activation consumption is deferred
  - `docs/architecture/EPISODIC_MEMORY.md`, especially the statement that Observation does not automatically form Memory
- **Problem:** the scheduler materializes durable `SimulationActivation` rows and wakes the per-world tickless task, but it never consumes an activation or dispatches an action. `ActionResolutionService` may preserve a `source_activation_id`, but does not claim, complete or otherwise consume that activation. `EpisodicMemoryService` is a separate explicit command and correctly refuses to make Observation→Memory automatic.
- **Impact:** the exact visual chain required by Q-001 does not exist today. A UI-only implementation cannot bridge the missing transitions without inventing orchestration semantics. A hidden “demo flow” endpoint would be new runtime behavior, not an inspector.
- **Required decision:** choose one reviewed path before implementation: (a) expose separate explicit developer operations for “resolve this activation as move_player” and “record memory from selected Observation”; (b) authorize a narrowly scoped developer demo orchestrator and define its partial-failure semantics; or (c) move activation consumption into a separately scoped production task. Q-001 currently lists neither activation resolution nor memory formation among allowed operations.

### A-002 — `PlayerMoved` has two canonical write paths with different side effects

- **Severity:** `FIX_NOW` — substantial; the Inspector cannot safely choose a canonical operation while both remain externally plausible.
- **Exact locations:**
  - `services/core/src/livingworld/application/command_handler.py::CommandHandler._mutate`, `case MovePlayer()`
  - `services/core/src/livingworld/application/action_resolution.py::ActionResolutionService._execute` and `._resolve_move`
  - shared transition helper `services/core/src/livingworld/application/player_movement.py`
- **Problem:** both paths use the same PlayerPresence transition and emit `PlayerMoved` v1. The legacy `MovePlayer` command appends the event and updates presence, but does not resolve an occurrence audience, create event-time Observations or materialize wake activations. The action-resolution path performs all of those Stage 5 side effects.
- **Impact:** identical event type/version does not imply identical canonical consequences. Calling the legacy command from the Inspector would fail the requested Observation trace; calling action resolution works, but leaves another production-capable path that bypasses the Stage 5 perception contract.
- **Required decision:** designate one canonical post-Stage-5 movement entry. Prefer routing external/runtime movement through `ActionResolutionService` and either retiring the legacy `MovePlayer` mutation or making it delegate to the same complete action pipeline. Do not independently duplicate audience logic in `CommandHandler`.

### A-003 — A world created after bootstrap is not enrolled in the running simulation runtime

- **Severity:** `FIX_NOW` — blocks the “create neutral demo world if none exists” operation from having defined runtime behavior.
- **Exact locations:**
  - `services/core/src/livingworld/bootstrap/cli.py::run` calls `WorldSimulationRuntime.start_all()` once before HTTP readiness
  - `services/core/src/livingworld/application/command_handler.py::CommandHandler._transaction` handles `CreateWorld`
  - `services/core/src/livingworld/application/simulation_runtime.py::WorldSimulationRuntime.start_world`
  - `services/core/src/livingworld/application/scheduler.py::SimulationSchedulerRuntime.activate_world`
- **Problem:** `CreateWorld` commits World/WorldClock/event/receipt, but does not notify `WorldSimulationRuntime`. Only worlds present during bootstrap receive reconciliation, a runtime state and a scheduler task.
- **Impact:** an Inspector-created demo world can exist durably while `WorldSimulationRuntime.state(world_id)` remains absent and no realtime scheduler loop is active. Calling `start_world` after the commit may solve the happy path, but the ownership and recovery behavior for “world committed, runtime enrollment failed” are not defined.
- **Required decision:** define a live-world onboarding application service that owns durable creation followed by runtime enrollment, including idempotent retry/degraded-state behavior. The HTTP adapter should call that service rather than assemble the sequence itself.

### A-004 — Current-status architecture documents contradict implemented Stage 5/6 state

- **Severity:** `FIX_NOW` — small, but misleading for the next implementation.
- **Exact locations:**
  - `docs/architecture/SYSTEM_OVERVIEW.md` status paragraph says world simulation is not implemented and only points to Stage 2/3 plus C-005A
  - `docs/architecture/RUNTIME_FOUNDATION.md` opening says the current system does not implement world simulation, even though the same document later describes C-006D composition
  - `README.md` correctly says Stage 5 is complete and C-007A is complete
- **Problem:** the overview documents present an obsolete current state while the implementation and README describe scheduler, action resolution, sparse activation, clock reconciliation and episodic memory.
- **Impact:** a maintainer choosing seams for the Inspector can follow the wrong architecture status and accidentally create parallel runtime abstractions.
- **Required action:** update the two status sections after the blocking decisions are made; preserve historical stage acceptance documents as historical snapshots.

### A-005 — Dead pure call in Scene close path

- **Severity:** `FIX_NOW` — trivial cleanup, no architecture decision required.
- **Exact location:** `services/core/src/livingworld/application/scenes.py::SceneService._execute`, `EndScene` branch.
- **Problem:** the loop calls `participant.leave(command.ended_at)` and discards the immutable return value; `leave_all` then performs the actual persistence update.
- **Impact:** readers may believe per-participant domain transitions are persisted when they are not. Today it is wasted work rather than a data bug because `leave_all` writes the intended state.
- **Required action:** remove the dead loop, or persist the returned transitions if domain-level per-participant validation is required. Do not keep both.

### A-006 — World command dispatch has become an oversized conditional transaction

- **Severity:** `DEFER` — address before adding another large family of world commands.
- **Exact location:** `services/core/src/livingworld/application/command_handler.py::CommandHandler` (about 494 lines), especially `._mutate` (about 354 lines).
- **Problem:** validation, lookup, transition construction, event payload creation, projection closure creation and result selection for all Stage 2 commands live in one match statement. Local closures make the transaction atomic, but make review and isolated evolution difficult.
- **Risk:** each new command increases the chance of missing a side effect such as perception, activation, Scene cleanup or new runtime barriers. A-002 is evidence of this divergence.
- **Recommendation:** retain one transaction owner but dispatch to small command-specific handlers that return a typed mutation plan. Do not create one service/repository stack per command.

### A-007 — Idempotent command scaffolding and receipt codecs are duplicated by result family

- **Severity:** `DEFER`.
- **Exact locations:**
  - `CommandHandler.execute/_transaction`
  - `ActionResolutionService.execute/_execute`
  - `SceneService.execute/_execute`
  - `EpisodicMemoryService.execute/_transaction`
  - `application/ports.py::CommandReceiptRepository`
  - `infrastructure/persistence/unit_of_work.py::CommandReceiptRepository`
- **Problem:** each service repeats fingerprint → existing receipt → transaction → commit → fresh-transaction duplicate recovery. The repository then exposes `existing`, `existing_action`, `existing_scene`, `existing_memory` plus matching add methods and hard-coded result versions 1–4.
- **Risk:** exception handling already differs among services, and every new result type adds methods to two interfaces plus persistence dispatch. This is a closed type switch disguised as multiple repository methods.
- **Recommendation:** after the movement-path decision, introduce one typed receipt codec/registry and one small transaction/idempotency executor. Keep domain-specific mutation inside each handler and preserve safe per-result serialization.

### A-008 — The general UnitOfWork is a broad capability bundle

- **Severity:** `DEFER`.
- **Exact locations:** `services/core/src/livingworld/application/ports.py::UnitOfWork` and `infrastructure/persistence/unit_of_work.py::SqlAlchemyUnitOfWork`.
- **Problem:** every command service receiving `UnitOfWork` gets worlds, locations, players, characters, relationships, scenes, knowledge, observations, memories, activations, events, event references and receipts, even if it needs only a subset.
- **Risk:** this weakens the repository’s otherwise strong capability-oriented security story. For example, Memory formation currently behaves correctly but technically receives canonical event and knowledge mutation capabilities.
- **Recommendation:** use focused UoW protocols for security-sensitive services while allowing a shared SQLAlchemy implementation underneath. Avoid multiplying physical transaction managers.

### A-009 — Migration compatibility validation encodes the full historical schema matrix in current code

- **Severity:** `DEFER`.
- **Exact locations:** `services/core/src/livingworld/infrastructure/persistence/migration.py::_validate_managed_state` and `._validate_domain_shape` (about 332 lines).
- **Problem:** the validator derives every supported historical shape from current ORM metadata plus a growing set of revision-specific exclusions and replacement checks.
- **Risk:** each new migration must update revision sets, table sets, column exclusions, constraints and index exceptions. A valid old database can be rejected if one historical delta is missed. The fail-closed behavior is correct, but the maintenance mechanism scales poorly.
- **Recommendation:** keep fail-closed validation, but move reviewed historical expectations into revision-local immutable manifests or validate only the takeover boundary plus current head. Do not infer a revision from shape.

### A-010 — Provider adapters contain oversized protocol pipelines

- **Severity:** `DEFER`.
- **Exact locations:**
  - `infrastructure/llm/openai_responses.py::OpenAIResponsesGateway` (about 573 lines; `stream` about 262)
  - `infrastructure/llm/gemini_interactions.py::GeminiInteractionsGateway` (about 584 lines; `stream` about 256)
  - `infrastructure/llm/anthropic_messages.py::AnthropicMessagesGateway` (about 507 lines; `stream` about 218)
  - `infrastructure/llm/openai_compatible.py::OpenAICompatibleChatGateway` (about 376 lines)
- **Problem:** request mapping, transport lifecycle, SSE parsing, provider continuation state, usage normalization, refusal/filter handling, structured-output integration and safe error conversion are concentrated in single classes.
- **Risk:** provider-specific code is justified, but the long streaming methods make terminal-event and cancellation invariants hard to compare. Fixes can land in one adapter and miss the others.
- **Recommendation:** extract only lifecycle pieces that are truly provider-neutral, especially terminal accounting/cancellation scaffolding. Keep wire parsing and provider semantics separate; do not force a false common provider schema.

### A-011 — Replay loads a complete world ledger into memory

- **Severity:** `DEFER`.
- **Exact locations:**
  - `application/ports.py::CanonicalEventReader.read`
  - `infrastructure/persistence/replay.py::_read`
  - `application/replay.py::ProjectionRebuilder`
- **Problem:** the contract returns `tuple[CanonicalEvent, ...]`, and the SQL adapter materializes every event before folding.
- **Risk:** rebuild memory usage grows with the lifetime event count, which conflicts with a long-lived persistent world. It is safe for current tests but not a scalable final recovery path.
- **Recommendation:** replace the tuple contract with bounded ordered pages or an async iterator while preserving one-world ordering and rebuild transaction semantics.

### A-012 — Some architecture/performance tests assert implementation text and private methods

- **Severity:** `ACCEPTABLE` for the current frozen stages; reduce coupling when touching the affected area.
- **Exact locations:**
  - `tests/core/test_architecture.py` parses source AST and blacklists call/import names
  - `tests/application/test_episodic_memory.py::test_exact_concurrent_retry_and_evidence_failure_are_atomic` monkeypatches `SqlAlchemyMemoryMutationRepository._insert_sources`
  - the same test module captures SQL strings and asserts index names/query-plan text
- **Problem:** these tests can fail after behavior-preserving renames or query rewrites, while AST name blacklists cannot prove semantic absence of a capability.
- **Why acceptable now:** they enforce important boundaries and crash/query-plan properties that are otherwise difficult to observe. The coupling is explicit and localized.
- **Recommendation:** retain the invariant tests, but prefer injected failure points and public repository contract probes over private monkeypatches when those modules next change.

### A-013 — Central persistence files are large but still cohesive

- **Severity:** `ACCEPTABLE`.
- **Exact locations:** `infrastructure/persistence/models.py` (about 949 lines) and `unit_of_work.py` (about 798 lines).
- **Assessment:** size alone is not a defect. `models.py` is a single declarative schema surface and `unit_of_work.py` keeps one SQL transaction boundary. Splitting by arbitrary line count could make FK and atomicity review harder.
- **Watch point:** split by stable bounded contexts only when A-008/A-009 are addressed; avoid one repository package per table.

### A-014 — `create_app` retains an effectively dead initialization callback

- **Severity:** `ACCEPTABLE`.
- **Exact locations:** `adapters/http/app.py::create_app` and `bootstrap/cli.py::run`.
- **Problem:** the FastAPI lifespan calls a synchronous `initialize` callback, while production completes database, simulation and LLM initialization before creating the app and passes `lambda: None`.
- **Risk:** the name suggests readiness-critical initialization occurs inside lifespan when it does not.
- **Recommendation:** remove the callback in a future foundation cleanup, or rename/document it if tests still need a hook. It does not justify a new service layer.

### A-015 — Desktop supervisor is a large composition/lifecycle unit

- **Severity:** `DEFER`.
- **Exact location:** `apps/desktop/src-tauri/src/supervisor.rs::CoreSupervisor`.
- **Problem:** bootstrap file creation, Python discovery, child stdout filtering, readiness validation, HMAC session derivation, credential provisioning, health checks, restart and forced termination are implemented in one `impl`.
- **Risk:** Windows process ownership and secret handling are sensitive; future Inspector IPC commands will increase the class surface if added there directly.
- **Recommendation:** keep `CoreSupervisor` as lifecycle owner but place new developer API traffic in the shared `CoreClient`/HTTP boundary. Do not add Inspector state querying or world operations to Rust.

## 3. Duplicate invariants assessed as intentional

The audit does **not** classify the following as harmful duplication:

- world-scoped typed-ID checks in domain constructors, application commands and composite database foreign keys;
- memory content/source bounds in command, aggregate and database constraints;
- relationship metric ranges in value objects and SQL CHECK constraints;
- bearer/session validation in Rust discovery, TypeScript client and Python HTTP authorization;
- migration cursor checks plus schema-shape checks.

These are independent trust boundaries. They should remain synchronized through named constants/tests where possible, but removing one layer would weaken validation.

## 4. Runtime Inspector boundary after resolution

Once A-001 through A-003 have an accepted design, the Inspector should remain thin:

```text
React developer view
→ shared CoreClient
→ authenticated /developer/runtime endpoints
→ inspector application query/command facade
→ existing readers/services
→ SQLAlchemy adapters
```

The frontend should receive typed read models, never ORM rows or SQLite access. Rust should only continue to supervise Core and deliver the authenticated connection. The Inspector should remain disabled or unavailable outside explicit developer mode.

## 5. Verification performed for this audit

- Confirmed repository HEAD and clean baseline before writing this report.
- Enumerated all production Python, React/TypeScript and Rust source files.
- Measured module/class/function sizes with Python AST and line scans.
- Inspected application ports, command/action/scene/memory services, scheduler/runtime composition, persistence UoW/migration/replay, HTTP/CoreClient boundaries, provider adapters and desktop supervisor.
- Cross-checked current README and architecture status documents against production composition.
- No production implementation or schema was modified.

Full build/test/smoke execution was intentionally not started because the task requires stopping after a substantial `FIX_NOW` audit result. The last committed baseline already had its C-007A verification; Q-001 has not reached its implementation acceptance phase.
