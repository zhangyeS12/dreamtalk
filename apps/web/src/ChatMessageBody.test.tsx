import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ChatMessageBody } from "./ChatMessageBody";

afterEach(cleanup);

it("renders roleplay Markdown without changing the saved message", () => {
  const text = "*她轻轻点头*\n\n**你好**\n\n- 第一件事\n- 第二件事";
  const { container } = render(<ChatMessageBody text={text} />);
  expect(container.querySelector("em")?.textContent).toBe("她轻轻点头");
  expect(container.querySelector("strong")?.textContent).toBe("你好");
  expect(container.querySelectorAll("li")).toHaveLength(2);
  expect(text).toContain("*她轻轻点头*");
});

it("treats untrusted HTML and URLs as inert content", () => {
  const { container } = render(<ChatMessageBody text={
    '<script>window.bad = true</script>\n\n<img src="https://example.com/tracker">\n\n![portrait](https://example.com/tracker)\n\n[bad](javascript:alert(1)) [local](/system/shutdown) [safe](https://example.com/page)'
  } />);
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText(/图片链接已隐藏/)).toBeTruthy();
  expect(screen.getByText("bad").closest("a")).toBeNull();
  expect(screen.getByText("local").closest("a")).toBeNull();
  expect(screen.getByRole("link", { name: "safe" }).getAttribute("rel")).toBe("noopener noreferrer");
  expect(screen.getByRole("link", { name: "safe" }).getAttribute("target")).toBe("_blank");
});
