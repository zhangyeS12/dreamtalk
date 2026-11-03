import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CoreClient, type ChatContextReports } from "@dreamtalk/api-client";
import { ContextReferencePanel } from "./ContextReferencePanel";

afterEach(cleanup);

function setup(read: CoreClient["chatContextReports"]) {
  const close = vi.fn();
  const parentKey = vi.fn();
  function Harness() {
    const [open, setOpen] = useState(false);
    return <div onKeyDown={parentKey}>
      <button onClick={() => setOpen(true)}>本次参考内容</button>
      <button>其他操作</button>
      {open ? <ContextReferencePanel client={{ chatContextReports: read } as CoreClient} worldId="world" conversationId="conversation" turnId="turn" names={new Map()} onClose={() => { close(); setOpen(false); }} /> : null}
    </div>;
  }
  const view = render(<Harness />);
  const opener = screen.getByRole("button", { name: "本次参考内容" });
  opener.focus();
  fireEvent.click(opener);
  return { ...view, opener, close, parentKey };
}

it("can close while loading, aborts the read and returns focus to its opener", () => {
  const read = vi.fn<CoreClient["chatContextReports"]>(() => new Promise(() => {}));
  const { opener, close } = setup(read);
  const button = screen.getByRole("button", { name: "关闭本次参考内容" });
  expect(document.activeElement).toBe(button);
  expect(screen.getByRole("status").textContent).toContain("正在读取");
  const signal = read.mock.calls[0][3];
  fireEvent.click(button);
  expect(close).toHaveBeenCalledOnce();
  expect(screen.queryByRole("region", { name: "本次参考内容" })).toBeNull();
  expect(signal?.aborted).toBe(true);
  expect(document.activeElement).toBe(opener);
});

it("closes with Escape inside the panel without forwarding it to the chat", async () => {
  const { opener, close, parentKey } = setup(vi.fn().mockResolvedValue({ turn_id: "turn", reports: [] }));
  await screen.findByText(/此轮没有参考记录/);
  const button = screen.getByRole("button", { name: "关闭本次参考内容" });
  fireEvent.keyDown(button, { key: "ArrowDown" });
  expect(close).not.toHaveBeenCalled();
  parentKey.mockClear();
  fireEvent.keyDown(button, { key: "Escape" });
  expect(close).toHaveBeenCalledOnce();
  expect(parentKey).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(opener);
});

it("keeps the close action available after a failed read", async () => {
  const { close } = setup(vi.fn().mockRejectedValue(new Error("offline")));
  expect((await screen.findByRole("alert")).textContent).toContain("未能读取");
  fireEvent.click(screen.getByRole("button", { name: "关闭本次参考内容" }));
  expect(close).toHaveBeenCalledOnce();
});

it("does not steal focus back when the user has moved outside the panel", async () => {
  const report: ChatContextReports = { turn_id: "turn", reports: [] };
  const { unmount } = setup(vi.fn().mockResolvedValue(report));
  await screen.findByText(/此轮没有参考记录/);
  const outside = document.createElement("button");
  document.body.append(outside);
  outside.focus();
  unmount();
  expect(document.activeElement).toBe(outside);
  outside.remove();
});
