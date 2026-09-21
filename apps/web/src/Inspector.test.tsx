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
    scenes: [{ scene_id: "scene-a", location_id: "location-a", status: "open", started_at: "1000000", participants: [{ kind: "character", principal_id: "character-a", name: "character_a", joined_at: "1000000" }] }],
    triggers: [{ trigger_id: "trigger-a", kind: "developer.inspector", status: "fired", priority: 0, due_at: "2000000" }],
    activations: [{ activation_id: "activation-a", target: "character:character-a", kind: "character_schedule_due", priority: 0, due_at: "2000000", fidelity: "active", cause_count: 1 }],
    events: [
      { event_id: "event-world", type: "WorldCreated", occurred_at: "1000000", ledger_position: 1 },
      { event_id: "event-a", type: "PlayerMoved", occurred_at: "2000000", ledger_position: 2 },
    ],
    observations: [{ observation_id: "observation-a", principal_kind: "character", principal_id: "character-a", principal_name: "character_a", event_id: "event-a", channel: "witnessed", observed_at: "2000000" }],
    memories: [{ memory_id: "memory-a", owner_character_id: "character-a", content: "测试记忆", experienced_from: "2000000", experienced_to: "2000000", formed_at: "2000000", salience: null, evidence: [{ observation_id: "observation-a", observed_at: "2000000" }] }],
  };
  const client = {
    listWorlds: vi.fn().mockResolvedValue([snapshot.world]),
    snapshot: vi.fn().mockResolvedValue(snapshot),
  } as unknown as CoreClient;
  render(<Inspector client={client} />);
  expect(await screen.findByText("开发者运行时检查器")).toBeTruthy();
  expect(await screen.findByText("模拟激活")).toBeTruthy();
  expect(await screen.findByText("演示世界")).toBeTruthy();
  expect((await screen.findAllByText("玩家甲")).length).toBeGreaterThan(0);
  expect((await screen.findAllByText("角色甲")).length).toBeGreaterThan(0);
  expect((await screen.findAllByText("地点甲")).length).toBeGreaterThan(0);
  expect((await screen.findAllByText("2.00 秒（2000000 微秒）")).length).toBeGreaterThan(0);
  expect(await screen.findByText("已触发")).toBeTruthy();
  expect(await screen.findByText("角色日程到期")).toBeTruthy();
  expect(await screen.findByText("世界已创建")).toBeTruthy();
  expect(await screen.findByText("玩家已移动")).toBeTruthy();
  expect(await screen.findByText("目击")).toBeTruthy();
  expect(document.body.textContent).not.toContain("Developer Runtime Inspector");
  expect(document.body.textContent).not.toContain("No records");
  expect(document.body.textContent).not.toContain("world_demo");
  expect(document.body.textContent).not.toContain("player_a");
  expect(document.body.textContent).not.toContain("character_a");
  expect(document.body.textContent).not.toContain("location_a");
});
