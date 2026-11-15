import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { CoreClient, ChatConversation, GroupChatConversation } from "@dreamtalk/api-client";
import { MobileConversationDirectory, type MobileConversation } from "./ConversationDirectory";
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const direct = (id: string, name: string, pinned = false): ChatConversation => ({ conversation_id: id, character_id: id, root_import_id: "root-" + id, player_id: "player", character_name: name, kind: "direct", pinned });
function fixture(items: MobileConversation[] = [direct("a","角色甲"),direct("b","角色乙",true)]) {
  const pin = vi.fn(async (_world: string, id: string, pinned: boolean) => ({ conversation_id: id, pinned }));
  const avatars = vi.fn(async () => []);
  const props = { client: { avatarDigests: avatars, setConversationPinned: pin } as unknown as CoreClient, worldId:"world",
    conversations: items, unread: {}, onOpen: vi.fn(), onNewGroup: vi.fn(), onContacts: vi.fn(), onPinned: vi.fn() };
  return { props, pin, avatars };
}
test("directory prioritizes persisted pins then unread while preserving source order", () => {
  const f=fixture([direct("a","角色甲"),direct("b","角色乙",true),direct("c","角色丙")]);
  render(<MobileConversationDirectory {...f.props} unread={{c:2}}/>);
  const rows=screen.getAllByRole("listitem");
  expect(rows.map(row=>row.querySelector("strong")?.textContent)).toEqual(["角色乙","角色丙","角色甲"]);
  fireEvent.click(within(rows[1]).getByRole("button",{name:/角色丙.*私聊/}));
  expect(f.props.onOpen).toHaveBeenCalledWith(f.props.conversations[2]);
  expect(f.pin).not.toHaveBeenCalled();
});
test("name search and kind filter select real members without reading message bodies", () => {
  const group: GroupChatConversation={conversation_id:"g",player_id:"player",kind:"group",participants:[{character_id:"a",root_import_id:"root-a",character_name:"角色甲"}]};
  const f=fixture([direct("a","角色甲"),group]);render(<MobileConversationDirectory {...f.props}/>);
  fireEvent.click(screen.getByRole("button",{name:"群聊"}));
  fireEvent.change(screen.getByRole("searchbox"),{target:{value:"角色甲"}});
  expect(screen.getAllByRole("listitem")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button",{name:/角色甲.*群聊/}));
  expect(f.props.onOpen).toHaveBeenCalledWith(group);
});
test("pinning uses the existing world and stable conversation API; no optimistic success", async () => {
  const f=fixture();render(<MobileConversationDirectory {...f.props}/>);
  expect(f.props.onPinned).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"置顶角色甲"}));
  await waitFor(()=>expect(f.props.onPinned).toHaveBeenCalledWith("a",true));
  expect(f.pin).toHaveBeenCalledWith("world","a",true);
});
test("failed pinning keeps state and reports uncertainty without raw provider data", async () => {
  const f=fixture();f.pin.mockRejectedValueOnce(new Error("synthetic-private-detail"));
  render(<MobileConversationDirectory {...f.props}/>);
  fireEvent.click(screen.getByRole("button",{name:"置顶角色甲"}));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent","置顶状态尚未确认，请重新读取会话后再试。");
  expect(f.props.onPinned).not.toHaveBeenCalled();expect(screen.queryByText("synthetic-private-detail")).toBeNull();
});
test("directory bounds visible rows and only requests their avatar bindings", async () => {
  const f=fixture(Array.from({length:65},(_,i)=>direct(String(i),"角色"+i)));
  render(<MobileConversationDirectory {...f.props}/>);
  expect(screen.getAllByRole("listitem")).toHaveLength(30);
  await waitFor(()=>expect(f.avatars).toHaveBeenCalled());
  expect((f.avatars.mock.calls[0] as unknown as [string,string[]])[1]).toHaveLength(30);
  fireEvent.click(screen.getByRole("button",{name:"下一页"}));
  expect(screen.getAllByRole("listitem")).toHaveLength(30);
  fireEvent.click(screen.getByRole("button",{name:"下一页"}));
  expect(screen.getAllByRole("listitem")).toHaveLength(5);
});
test("empty search has a working reset and does not create conversations", () => {
  const f=fixture();render(<MobileConversationDirectory {...f.props}/>);
  fireEvent.change(screen.getByRole("searchbox"),{target:{value:"不存在"}});
  expect(screen.getByRole("heading",{name:"没有匹配的会话"})).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"查看全部会话"}));
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  expect(f.props.onOpen).not.toHaveBeenCalled();
});
