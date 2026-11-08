import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { CoreClient, type CharacterEvolutionEntry, type WorldContentItem } from "@dreamtalk/api-client";
import { ContentDetails } from "./WorldContent";

afterEach(cleanup);

function entry(changes: Partial<CharacterEvolutionEntry> = {}): CharacterEvolutionEntry {
  return { entry_id: "version-1", field: "personality", scope: "global", text: "开始愿意照顾他人", state: "active", selected: true, locked: false, source: "model", created_at_utc: "2026-01-01T00:00:00Z", quote: "我会一直照顾你", confidence: 0.9, change_kind: "addition", ...changes };
}

function item(personality = ""): WorldContentItem {
  return { characters: [{ id: "character", name: "合成人物", description: "合成描述", personality, background: "", scenario: "", speech_guidance: "", creator_notes: "", tags: [], example_dialogue: [], authored_instructions: {} }], lorebooks: [], entries: [] } as unknown as WorldContentItem;
}

function client(initial: CharacterEvolutionEntry[]) {
  let entries = initial.map(value => ({ ...value }));
  return Object.assign(Object.create(CoreClient.prototype) as CoreClient, {
    characterEvolution: vi.fn().mockImplementation(async () => entries.map(value => ({ ...value }))),
    changeCharacterEvolution: vi.fn().mockImplementation(async (_world, _root, change) => {
      entries = entries.map(value => {
        if (change.operation === "restore" && value.scope === change.scope && value.field === change.field) {
          return { ...value, selected: value.entry_id === change.entry_id, state: value.entry_id === change.entry_id ? "active" : "inactive" };
        }
        if (value.entry_id !== change.entry_id) return value;
        if (change.operation === "deactivate") return { ...value, selected: false, state: "inactive" };
        return { ...value, locked: change.operation === "lock" };
      }) as CharacterEvolutionEntry[];
      return entries.find(value => value.entry_id === change.entry_id)!;
    }),
  });
}

function setup(entries: CharacterEvolutionEntry[], personality = "") {
  const api = client(entries);
  const rendered = render(<ContentDetails item={item(personality)} evolutionCard={{ client: api, worldId: "world", rootImportId: "root" }} />);
  return { api, ...rendered };
}

it("shows automatic additions even when the original field is empty", async () => {
  const { container } = setup([entry()]);
  await screen.findByRole("heading", { name: "性格" });
  expect(container.querySelector("summary .evolution-added")?.textContent).toBe(entry().text);
  expect(screen.getByText(/点击标记查看历史或回退/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "采用" })).toBeNull();
});

it.each(["model", "user"] as const)("uses the recorded replacement kind for %s versions", async source => {
  const { container } = setup([entry({ source, change_kind: "replacement" })], "原来排斥他人");
  await waitFor(() => expect(container.querySelector("summary .evolution-changed")).not.toBeNull());
  expect(container.querySelector("summary .evolution-added")).toBeNull();
});

it("marks additions to a nonempty field as additions", async () => {
  const { container } = setup([entry()], "保留的原有特点");
  await waitFor(() => expect(container.querySelector("summary .evolution-added")).not.toBeNull());
});

it("restores an earlier version and can return to the original card", async () => {
  const first = entry({ state: "inactive", selected: false });
  const second = entry({ entry_id: "version-2", text: "开始主动帮助身边的人", change_kind: "replacement", created_at_utc: "2026-01-02T00:00:00Z" });
  const { api, container } = setup([first, second], "原始性格");
  await waitFor(() => expect(container.querySelector("summary .evolution-changed")).not.toBeNull());
  fireEvent.click(container.querySelector(".inline-evolution summary")!);
  fireEvent.click(screen.getByRole("button", { name: "恢复此版本" }));
  await waitFor(() => expect(container.querySelector("summary .evolution-added")?.textContent).toBe(first.text));
  expect(api.changeCharacterEvolution).toHaveBeenCalledWith("world", "root", expect.objectContaining({ operation: "restore", entry_id: first.entry_id }));
  fireEvent.click(screen.getByRole("button", { name: "恢复原始内容" }));
  await waitFor(() => expect(container.querySelector("summary .evolution-deleted")).not.toBeNull());
  expect(screen.getByText("原始性格")).toBeTruthy();
});

it("blocks rollback until the current version is unlocked", async () => {
  const { api, container } = setup([entry({ entry_id: "older", selected: false, state: "inactive" }), entry({ locked: true })], "原始性格");
  await screen.findAllByText(/当前生效.*已锁定/);
  fireEvent.click(container.querySelector(".inline-evolution summary")!);
  expect(screen.getByRole("button", { name: "恢复原始内容" }).hasAttribute("disabled")).toBe(true);
  expect(screen.getByRole("button", { name: "恢复此版本" }).hasAttribute("disabled")).toBe(true);
  fireEvent.click(within(container.querySelector(".evolution-active") as HTMLElement).getByRole("button", { name: "解锁" }));
  await waitFor(() => expect(api.changeCharacterEvolution).toHaveBeenCalledWith("world", "root", expect.objectContaining({ operation: "unlock" })));
  await waitFor(() => expect(screen.getByRole("button", { name: "恢复原始内容" }).hasAttribute("disabled")).toBe(false));
});

it("keeps the effective version visible when rollback fails and does not resubmit", async () => {
  const { api, container } = setup([entry()], "原始性格");
  vi.mocked(api.changeCharacterEvolution).mockRejectedValue(new Error("synthetic failure"));
  await waitFor(() => expect(container.querySelector("summary .evolution-added")).not.toBeNull());
  fireEvent.click(container.querySelector(".inline-evolution summary")!);
  fireEvent.click(screen.getByRole("button", { name: "恢复原始内容" }));
  await screen.findByRole("alert");
  expect(container.querySelector("summary .evolution-added")?.textContent).toBe(entry().text);
  expect(api.changeCharacterEvolution).toHaveBeenCalledOnce();
});

it("does not show a late response from another character", async () => {
  const api = client([]);
  let finish: (value: CharacterEvolutionEntry[]) => void = () => undefined;
  vi.mocked(api.characterEvolution).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValueOnce([entry({ text: "第二人的变化" })]);
  const { rerender } = render(<ContentDetails item={item()} evolutionCard={{ client: api, worldId: "world", rootImportId: "first" }} />);
  rerender(<ContentDetails item={item()} evolutionCard={{ client: api, worldId: "world", rootImportId: "second" }} />);
  await screen.findAllByText("第二人的变化");
  await act(async () => finish([entry({ text: "第一人的迟到结果" })]));
  expect(screen.queryByText("第一人的迟到结果")).toBeNull();
});
