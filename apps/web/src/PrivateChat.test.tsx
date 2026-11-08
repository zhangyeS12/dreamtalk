import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { type CoreClient, type GroupChatConversation } from "@dreamtalk/api-client";
import { GroupChatDetails } from "./GroupChat";
import { PrivateMessageBody, PrivacyButton } from "./PrivateChat";
import { movePrivacy, privacyError } from "./chatPrivacy";
import { withChatReads } from "./testClient";

afterEach(cleanup);
const a = "11111111-1111-4111-8111-111111111111", b = "22222222-2222-4222-8222-222222222222";
const people = [{ character_id: a, name: "甲" }, { character_id: b, name: "乙" }];

it("only enables new privacy for a selection containing one valid, unique @member", () => {
  const onChange = vi.fn(), text = "@甲（轻声）秘密，公开内容";
  const base = { text, spans: [], people, disabled: false, onChange };
  const { rerender } = render(<PrivacyButton {...base} selection={[0, 0]} />);
  expect(screen.getByRole("button")).toHaveProperty("disabled", true);
  rerender(<PrivacyButton {...base} selection={[7, 9]} />);
  expect(screen.getByRole("button")).toHaveProperty("disabled", true);
  rerender(<PrivacyButton {...base} selection={[0, 8]} />);
  fireEvent.click(screen.getByRole("button"));
  expect(onChange).toHaveBeenCalledWith([{ start: 0, end: 8, character_id: a }]);
  rerender(<PrivacyButton {...base} people={[...people, { character_id: b, name: "甲" }]} selection={[0, 8]} />);
  expect(screen.getByRole("button")).toHaveProperty("disabled", true);
});

it("keeps replacement text private and blocks sending when its @target is removed", () => {
  const text = "@甲 秘密。公开", spans = [{ start: 0, end: 6, character_id: a }];
  const next = "@甲 新的秘密。公开";
  const moved = movePrivacy(text, next, spans);
  expect(next.slice(moved[0].start, moved[0].end)).toBe("@甲 新的秘密。");
  expect(privacyError(next, moved, people)).toBeNull();
  const invalid = next.replace("@甲", "@丙");
  expect(privacyError(invalid, movePrivacy(next, invalid, moved), people)).toMatch(/@群成员/);
  const emoji = "😀" + next;
  const shifted = movePrivacy(next, emoji, moved);
  expect(shifted[0].start).toBe(0); // boundary insertion is conservative, stays private
  expect(privacyError(emoji, shifted, people)).not.toBeNull(); // @ must still be a valid mention
});

it("masks role replies inline and supports reveal, collapse and keyboard focus", () => {
  const { rerender } = render(<PrivateMessageBody text="秘密。公开。" character spans={[{ start: 0, end: 3, character_id: a }]} nameOf={() => "甲"} />);
  expect(screen.queryByText("秘密。")).toBeNull();
  const mask = screen.getByRole("button", { name: "查看私密片段，仅你与 甲 可见" });
  expect(mask.closest("p")?.textContent).toBe("███公开。");
  fireEvent.keyDown(mask, { key: "Enter" });
  expect(screen.getByText("秘密。")).toBeTruthy();
  const collapse = screen.getByRole("button", { name: "收起私密片段，仅你与 甲 可见" });
  expect(document.activeElement).toBe(collapse);
  fireEvent.click(collapse);
  expect(screen.queryByText("秘密。")).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole("button", { name: /查看私密片段/ }));
  fireEvent.keyDown(document.activeElement!, { key: " " });
  expect(screen.getByText("秘密。")).toBeTruthy();
  expect(screen.getByText("公开。")).toBeTruthy();
  rerender(<PrivateMessageBody text="秘密。公开。" character={false} spans={[{ start: 0, end: 3, character_id: a }]} nameOf={() => "甲"} />);
  expect(screen.queryByText("秘密。")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /查看私密片段，仅 甲 可见/ }));
  expect(screen.getByText("秘密。")).toBeTruthy();
});

it("preserves public Markdown, paragraphs and multiple UTF-16 ranges without leaking hidden text", () => {
  const text = "**公开😀秘密甲继续**，秘密乙结尾。\n\n第二段。";
  const spans = ["秘密甲", "秘密乙"].map(secret => ({ start: text.indexOf(secret), end: text.indexOf(secret) + secret.length, character_id: a }));
  const { container } = render(<PrivateMessageBody text={text} spans={spans} character nameOf={() => "甲"} />);
  expect(container.innerHTML).not.toMatch(/秘密甲|秘密乙|DREAMTALKPRIVATE|replyPart/);
  expect(container.querySelectorAll("p")).toHaveLength(2);
  expect(container.querySelector("strong")?.textContent).toBe("公开😀███继续");
  expect(container.querySelector("p div, p p")).toBeNull();
  fireEvent.click(screen.getAllByRole("button")[0]);
  expect(container.textContent).toContain("秘密甲");
  expect(container.textContent).not.toContain("秘密乙");
  expect(container.querySelectorAll("p")).toHaveLength(2);
});

it.each(["秘密。公开。", "**秘密。公开。**", "“秘密。公开。”"])("keeps a revealed mask and keyboard focus across parent refreshes: %s", text => {
  const start = text.indexOf("秘密。");
  const frame = (tick: number) => <section data-refresh={tick}>
    <PrivateMessageBody text={text} character spans={[{ start, end: start + 3, character_id: a }]} nameOf={() => "甲"} />
    <p>刷新次数：{tick}</p>
  </section>;
  const { rerender } = render(frame(0));
  fireEvent.click(screen.getByRole("button", { name: "查看私密片段，仅你与 甲 可见" }));
  const collapse = screen.getByRole("button", { name: "收起私密片段，仅你与 甲 可见" });
  for (let tick = 1; tick <= 20; tick++) {
    // Fresh span arrays and callbacks match ConversationParts on each poll.
    rerender(frame(tick));
    expect(screen.getByText("秘密。")).toBeTruthy();
    expect(screen.getByRole("button", { name: /收起私密片段/ })).toBe(collapse);
    expect(document.activeElement).toBe(collapse);
  }
  fireEvent.click(collapse);
  rerender(frame(21));
  expect(screen.queryByText("秘密。")).toBeNull();
  expect(screen.getByRole("button", { name: /查看私密片段/ }).getAttribute("aria-expanded")).toBe("false");
});

it.each(["[链接](SECRET)", "[SECRET](https://example.com)", "![SECRET](https://example.com/image)", "```SECRET\n代码\n```", "<b title=\"SECRET\">原文</b>"])("keeps private Markdown properties and code inert: %s", text => {
  const { container } = render(<PrivateMessageBody text={text} spans={[{ start: text.indexOf("SECRET"), end: text.indexOf("SECRET") + 6, character_id: a }]} character nameOf={() => "甲"} />);
  expect(container.innerHTML).not.toMatch(/SECRET|DREAMTALKPRIVATE/);
  expect(container.querySelector("a, img, script")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /查看私密片段/ }));
  expect(container.textContent).toContain("SECRET");
});

it("retains private paragraphs and distinguishes confirmed privacy, fallback and unknown history", () => {
  const text = "私密第一段。\n\n私密第二段。";
  const base = { text, spans: [{ start: 0, end: text.length, character_id: a }], character: true, nameOf: () => "甲" };
  const { container, rerender } = render(<PrivateMessageBody {...base} fallback={false} />);
  expect(container.querySelectorAll("p")).toHaveLength(2);
  expect(screen.queryByText(/暂按私密保护/)).toBeNull();
  rerender(<PrivateMessageBody {...base} fallback />);
  expect(screen.getByText(/公开／私密范围未能确认/)).toBeTruthy();
  rerender(<PrivateMessageBody {...base} fallback={null} />);
  expect(screen.queryByText(/暂按私密保护/)).toBeNull();
  fireEvent.click(screen.getAllByRole("button")[0]);
  expect(screen.getByText("私密第一段。")).toBeTruthy();
  rerender(<PrivateMessageBody {...base} spans={[{ ...base.spans[0], character_id: b }]} />);
  expect(screen.queryByText("私密第一段。")).toBeNull();
});

it("persists the selected private span and retries an uncertain save with identical text and audiences", async () => {
  const group: GroupChatConversation = { conversation_id: "group-a", player_id: "player-a", kind: "group", participants: people.map(person => ({ character_id: person.character_id, character_name: person.name, root_import_id: person.character_id })) };
  const sendGroupMessage = vi.fn().mockRejectedValue(new Error("uncertain"));
  const client = { sendGroupMessage, conversationMessagePage: vi.fn().mockResolvedValue({ items: [], next_before_position: null }), groupReplyAvailability: vi.fn().mockResolvedValue({ available: true }) } as unknown as CoreClient;
  render(<GroupChatDetails client={withChatReads(client)} worldId="world-a" playerId="player-a" group={group} tokenCeiling={50000} onBack={() => {}} />);
  const draft = await screen.findByRole("textbox", { name: "发送群聊消息" }) as HTMLTextAreaElement;
  await waitFor(() => expect(draft.disabled).toBe(false));
  const secret = "@甲（轻声）私密内容。", text = secret + "公开内容。";
  fireEvent.change(draft, { target: { value: text } });
  draft.focus(); draft.setSelectionRange(0, secret.length); fireEvent.select(draft);
  const glasses = screen.getByRole("button", { name: "将选中文字设为私密" });
  await waitFor(() => expect(glasses).toHaveProperty("disabled", false));
  fireEvent.click(glasses);
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(sendGroupMessage).toHaveBeenCalledOnce());
  expect(sendGroupMessage.mock.calls[0]?.[6]).toEqual([{ start: 0, end: secret.length, character_id: a }]);
  fireEvent.click(await screen.findByRole("button", { name: "重试保存" }));
  await waitFor(() => expect(sendGroupMessage).toHaveBeenCalledTimes(2));
  expect(sendGroupMessage.mock.calls[1]).toEqual(sendGroupMessage.mock.calls[0]);
});
