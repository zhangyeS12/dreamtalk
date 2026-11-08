import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ChatMessage } from "@dreamtalk/api-client";
import { useChatScroll } from "./useChatScroll";

afterEach(cleanup);

function Thread({ messages }: { messages: ChatMessage[] | null }) {
  const { thread, beforePrepend } = useChatScroll(messages);
  return <div data-testid="scroll-area"><button onClick={beforePrepend}>load older</button><section ref={thread}>{messages?.length ?? 0}</section></div>;
}

const first: ChatMessage = {
  message_id: "m1", turn_id: "t1", conversation_id: "c1", position: 1,
  sender_kind: "player", sender_id: "p1", text: "你好", created_at_utc: "2026-09-27T00:00:00Z",
};

it("opens at the latest message but leaves a reader on older messages until they return", () => {
  const view = render(<Thread messages={null} />);
  const scroller = screen.getByTestId("scroll-area");
  Object.defineProperties(scroller, {
    scrollHeight: { configurable: true, value: 1000 },
    clientHeight: { configurable: true, value: 200 },
  });
  view.rerender(<Thread messages={[first]} />);
  expect(scroller.scrollTop).toBe(1000);

  scroller.scrollTop = 100;
  fireEvent.scroll(scroller);
  view.rerender(<Thread messages={[first, { ...first, message_id: "m2", position: 2 }]} />);
  expect(scroller.scrollTop).toBe(100);

  scroller.scrollTop = 750;
  fireEvent.scroll(scroller);
  view.rerender(<Thread messages={[first, { ...first, message_id: "m3", position: 3 }]} />);
  expect(scroller.scrollTop).toBe(1000);
});

it("keeps the current message in view when older messages are prepended", () => {
  const view = render(<Thread messages={[first]} />);
  const scroller = screen.getByTestId("scroll-area");
  let height = 1000;
  Object.defineProperties(scroller, {
    scrollHeight: { configurable: true, get: () => height },
    clientHeight: { configurable: true, value: 200 },
  });
  scroller.scrollTop = 100;
  fireEvent.scroll(scroller);
  fireEvent.click(screen.getByRole("button", { name: "load older" }));
  height = 1300;
  view.rerender(<Thread messages={[{ ...first, message_id: "older", position: 0 }, first]} />);
  expect(scroller.scrollTop).toBe(400);
});
