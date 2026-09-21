# Q-001B Developer Runtime Inspector

Status: developer tooling for direct runtime verification. It is not the Stage 11 product UI.

## Boundary

The inspector is available only when Core starts with `--developer-tools`. `npm run dev:web` and Windows debug Tauri builds set that flag; ordinary Core startup and release desktop builds do not register `/developer/*` routes. Every inspector request uses the existing in-memory bearer session.

React reads through `CoreClient` and the authenticated HTTP adapter. The UI never opens SQLite. A read-only SQLAlchemy projection supplies operational rows, while every control delegates to an existing application path:

- pause, resume and scale use `WorldClockService` through `WorldSimulationRuntime`;
- safe triggers use `SimulationScheduler` with an allowlisted `developer.inspector` v1 empty payload;
- player movement uses the compatibility `MovePlayer` command, which delegates to the canonical `ActionResolutionService` path;
- memory uses explicit `RecordEpisodicMemory` and the existing owner-authorization check;
- demo setup uses `CreateWorld`, `CreateLocation`, `CreatePlayer`, `CreateCharacter`, `PlaceCharacter` and `CreateScene`.

No Activation consumer or automatic Observation-to-Memory path is introduced. The inspector does not fabricate WorldEvents, Observations or EpisodicMemories.

## Developer API

All routes below require the session bearer:

| Method and path | Purpose |
| --- | --- |
| `GET /developer/worlds` | List selectable Worlds |
| `POST /developer/demo-world` | Idempotently create the neutral `world_demo` fixture through application commands |
| `GET /developer/worlds/{world_id}/snapshot` | Read runtime state; optional `owner_character_id` binds the private memory view |
| `POST /developer/worlds/{world_id}/clock/pause` | Pause the canonical WorldClock |
| `POST /developer/worlds/{world_id}/clock/resume` | Resume the canonical WorldClock |
| `POST /developer/worlds/{world_id}/clock/scale` | Change the canonical clock scale |
| `POST /developer/worlds/{world_id}/triggers` | Schedule one bounded, allowlisted safe trigger |
| `POST /developer/worlds/{world_id}/move-player` | Execute canonical `move_player` |
| `POST /developer/worlds/{world_id}/memories` | Explicitly record one owner-authorized EpisodicMemory |

Snapshots expose event metadata rather than event payloads. Memory reads are made through a reader already bound to the selected Character; selecting another owner creates a different bound reader.

## Neutral demo

The deterministic, retry-safe demo setup uses only `world_demo`, `player_a`, `character_a`, `character_b`, `location_a`, `location_b` and `scene_a`. `character_a` is an active participant in `scene_a`; the player remains free to move through the canonical action path. Moving `player_a` from `location_a` to `location_b` produces the real `PlayerMoved` WorldEvent and event Observations for principals present at the origin and destination. The operator can then select `character_a`'s authorized Observation and explicitly call `RecordEpisodicMemory`.

The safe scheduled trigger targets `character_a`. The tickless scheduler materializes it as a real pending `SimulationActivation`; there is deliberately no consumer in Q-001B.
