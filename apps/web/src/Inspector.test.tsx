import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { CoreClient, type InspectorSnapshot } from "@livingworld/api-client";
import { Inspector } from "./Inspector";

afterEach(cleanup);

it("renders real inspector state and owner-scoped evidence controls", async () => {
  const snapshot: InspectorSnapshot = {
    world: { world_id: "world", name: "world_demo" },
    clock: { world_time: "2000000", state: "running", scale: "1", revision: 1 },
    runtime_state: "ready",
    locations: [{ location_id: "location-a", name: "location_a" }],
    players: [{ player_id: "player-a", name: "player_a", location_id: "location-a", activity: "active", availability: "available", revision: 0 }],
    characters: [{ character_id: "character-a", name: "character_a", location_id: "location-a" }],
    scenes: [], triggers: [], activations: [], events: [],
    observations: [{ observation_id: "observation-a", principal_kind: "character", principal_id: "character-a", principal_name: "character_a", event_id: "event-a", channel: "witnessed", observed_at: "2000000" }],
    memories: [],
  };
  const client = {
    listWorlds: vi.fn().mockResolvedValue([snapshot.world]),
    snapshot: vi.fn().mockResolvedValue(snapshot),
  } as unknown as CoreClient;
  render(<Inspector client={client} />);
  expect(await screen.findByText("Developer Runtime Inspector")).toBeTruthy();
  expect(await screen.findByText("SimulationActivations")).toBeTruthy();
  expect((await screen.findAllByText("character_a")).length).toBeGreaterThan(0);
  expect((await screen.findAllByText("2.00s (2000000µs)")).length).toBeGreaterThan(0);
});
