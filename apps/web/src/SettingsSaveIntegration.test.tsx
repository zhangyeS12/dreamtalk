import { afterAll, afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { startSettingsBridge, syntheticCardFile } from "../../../scripts/settings-save-transport.mjs";
import { CoreClient } from "@dreamtalk/api-client";
import { WorldStyleEditor } from "./WorldStyleEditor";
import { PlayerPersonaEditor } from "./PlayerPersonaEditor";

vi.mock("./DesktopUpdates", () => ({ useDesktopUpdateBlock: vi.fn() }));

let bridge: Awaited<ReturnType<typeof startSettingsBridge>>;
let world: string, client: CoreClient;
let requests: Request[];

beforeAll(async () => {
  bridge = await startSettingsBridge();
  world = bridge.world; requests = bridge.requests;
  client = new CoreClient({ endpoint: "http://127.0.0.1", token: "synthetic-session", generation: "synthetic" }, bridge.fetcher);
}, 30000);
afterEach(cleanup);
afterAll(async () => { await bridge?.close(); });

it("previews, confirms and reloads world style through the real client and HTTP parser", async () => {
  render(<WorldStyleEditor client={client} worldId={world} onDirtyChange={() => {}} />);
  const input = await screen.findByLabelText("当前世界的写作约定");
  fireEvent.change(input, { target: { value: "合成悬疑风格，动作与台词自然衔接。" } });
  fireEvent.click(screen.getByRole("button", { name: "预览修改" }));
  await screen.findByRole("heading", { name: "确认后的世界风格" });
  expect((await client.worldStyle(world)).revision).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: "确认并保存" }));
  await screen.findByText(/已保存。从下一次角色发言起/);
  expect(await client.worldStyle(world)).toEqual({ instructions: "合成悬疑风格，动作与台词自然衔接。", revision: 1 });
  const writes = requests.filter(request => request.method === "POST" && new URL(request.url).pathname.includes("/style/"));
  expect(writes).toHaveLength(2);
  expect(writes.map(request => request.headers.get("content-type"))).toEqual(["application/json", "application/json"]);
});

it("saves a sourced player identity with an empty story start through the same HTTP parser", async () => {
  render(<PlayerPersonaEditor client={client} worldId={world} onDirtyChange={() => {}} />);
  await screen.findByLabelText("设定人物名称");
  const file = syntheticCardFile({ spec: "chara_card_v2", spec_version: "2.0", data: { name: "合成玩家", description: "玩家专用的合成卡", personality: "温和", scenario: "合成世界", extensions: {} } });
  fireEvent.change(screen.getByLabelText("导入我的角色卡"), { target: { files: [file] } });
  await screen.findByText(/已读取玩家角色卡/);
  fireEvent.change(screen.getByLabelText("设定人物名称"), { target: { value: "合成玩家" } });
  fireEvent.change(screen.getByLabelText("公开身份介绍"), { target: { value: "合成世界的店主，仅用于隔离检查。" } });
  fireEvent.click(screen.getByRole("button", { name: "预览身份修改" }));
  await screen.findByRole("region", { name: "身份修改预览" });
  expect((await client.playerPersona(world)).revision).toBe(0);
  fireEvent.click(screen.getByRole("button", { name: "确认采用身份" }));
  await screen.findByText("设定身份已采用。");
  const saved = await client.playerPersona(world);
  expect(saved.revision).toBe(1);
  expect(saved.draft.identity_name).toBe("合成玩家");
  expect(saved.draft.public_identity).toBe("合成世界的店主，仅用于隔离检查。");
  expect(saved.source_state).toBe("current");
  expect(saved.draft.source?.scope).toBe("player");
  const writes = requests.filter(request => request.method === "POST" && new URL(request.url).pathname.includes("/persona/"));
  expect(writes).toHaveLength(3);
  expect(writes.map(request => request.headers.get("content-type"))).toEqual(["application/octet-stream", "application/json", "application/json"]);
});
