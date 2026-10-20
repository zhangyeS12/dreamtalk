import { afterEach, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { ChatMessageBody } from "./ChatMessageBody";
import { StreamingReplyBubble } from "./StreamingReplyBubble";

afterEach(cleanup);

it.each(['“你好。”', '"你好。"', '「你好。」', '『你好。』', '«你好。»', '＂你好。＂'])("highlights spoken quotes %s while keeping narration plain", quote => {
  const text = `她走近，*微微一笑*，${quote} 随后转身。`;
  const { container } = render(<ChatMessageBody text={text} character />);
  expect(container.querySelector(".character-dialogue")?.textContent).toBe(quote);
  expect(container.querySelector("em .character-dialogue")).toBeNull();
  expect(container.textContent).toBe(`她走近，微微一笑，${quote} 随后转身。`);
});

it("keeps quote state across strong/link text and nested quotes, never code or actions", () => {
  const { container } = render(<ChatMessageBody character text={'她说：“你好，**朋友**，[看这里](https://example.com)。「好」。” *“动作示例”* `“代码”`\n\n```\n“代码块”\n```'} />);
  expect([...container.querySelectorAll(".character-dialogue")].map(node => node.textContent).join("")).toBe('“你好，朋友，看这里。「好」。”');
  expect(container.querySelector("a")?.getAttribute("href")).toBe("https://example.com");
  expect(container.querySelectorAll("code .character-dialogue, em .character-dialogue")).toHaveLength(0);
});

it("leaves player messages and ambiguous unquoted narration unchanged", () => {
  const { container, rerender } = render(<ChatMessageBody text="“玩家说话”" />);
  expect(container.querySelector(".character-dialogue")).toBeNull();
  rerender(<ChatMessageBody text="她望着窗外，神情平静。" character />);
  expect(container.querySelector(".character-dialogue")).toBeNull();
});

it("uses identical safe rendering during streaming and after completion", () => {
  const text = '她抬头。“你好**朋友**';
  const { container, rerender } = render(<StreamingReplyBubble name="角色" text={text} />);
  const partial = container.querySelector(".message-content")?.innerHTML;
  rerender(<ChatMessageBody text={text} character />);
  expect(container.querySelector(".message-content")?.innerHTML).toBe(partial);
  rerender(<ChatMessageBody text={text + '。” 她挥手。\n\n<script>bad()</script>\n\n[本地](/shutdown) ![图](https://example.com/tracker)'} character />);
  expect(container.querySelector("script, img, a[href='/shutdown']")).toBeNull();
  expect([...container.querySelectorAll(".character-dialogue")].map(node => node.textContent).join("")).toBe("“你好朋友。”");
});

it("resets an unmatched quote at a paragraph boundary", () => {
  const { container } = render(<ChatMessageBody text={'“未完台词\n\n她低头。'} character />);
  expect(container.querySelectorAll(".character-dialogue")).toHaveLength(1);
  expect(container.querySelectorAll("p")[1].querySelector(".character-dialogue")).toBeNull();
});
