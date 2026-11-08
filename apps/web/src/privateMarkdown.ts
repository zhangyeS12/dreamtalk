import type { Element, ElementContent, Root, RootContent } from "hast";
import { privacyPieces, type PrivacySpan } from "./chatPrivacy";

/** Keep secrets out of the Markdown source, DOM attributes and closed masks. */
export function maskedMarkdown(text: string, spans: PrivacySpan[]) {
  let prefix = "DREAMTALKPRIVATE";
  while (text.includes(prefix)) prefix += "X";
  const slots: { text: string; owner: string }[] = [];
  const source = privacyPieces(text, spans).map(part => {
    if (!part.owner) return part.text;
    // Preserve the author's paragraphs, including when a private range crosses them.
    return part.text.split(/(\r?\n)/u).map(piece => {
      if (!piece || /^\r?\n$/u.test(piece)) return piece;
      const index = slots.push({ text: piece, owner: part.owner! }) - 1;
      return `${prefix}${index}Z`;
    }).join("");
  }).join("");
  return { source, prefix, slots };
}

/** Resolve opaque slots after Markdown parsing, before quote highlighting. */
export function privateMarkdownSlots({ prefix, count }: { prefix: string; count: number }) {
  return (tree: Root) => {
    const expression = new RegExp(`${prefix}(\\d+)Z`, "gu");
    const split = (value: string): ElementContent[] => {
      const nodes: ElementContent[] = [];
      let cursor = 0;
      for (const match of value.matchAll(expression)) {
        const index = Number(match[1]);
        if (index >= count) continue;
        if (match.index > cursor) nodes.push({ type: "text", value: value.slice(cursor, match.index) });
        nodes.push({ type: "element", tagName: "span", properties: { "data-private-slot": index }, children: [] });
        cursor = match.index + match[0].length;
      }
      if (cursor < value.length) nodes.push({ type: "text", value: value.slice(cursor) });
      return nodes;
    };
    const hasSlot = (node: RootContent): boolean => node.type === "element" &&
      (node.properties["data-private-slot"] !== undefined || node.children.some(hasSlot));
    const visit = (parent: Root | Element) => {
      parent.children = parent.children.flatMap((node): RootContent[] => {
        if (node.type !== "element") {
          // Raw HTML remains inert text; never parse it into executable elements.
          return "value" in node && typeof node.value === "string" ? split(node.value) : [node];
        }
        visit(node);
        const propertySlots: ElementContent[] = [];
        for (const [key, value] of Object.entries(node.properties)) {
          const parts = split(Array.isArray(value) ? value.join(" ") : String(value ?? ""));
          const found = parts.filter(hasSlot);
          if (!found.length) continue;
          delete node.properties[key];
          propertySlots.push(...found);
          // A private URL/title is never turned into a navigable public URL.
          if (node.tagName === "a") node.tagName = "span";
        }
        if (node.tagName === "img" && propertySlots.length) {
          node.tagName = "span";
          node.children = [{ type: "text", value: "[图片链接已隐藏]" }];
          node.properties = {};
        }
        node.children.push(...propertySlots);
        // Avoid nesting a reveal control inside an active link.
        if (node.tagName === "a" && node.children.some(hasSlot)) {
          node.tagName = "span";
          node.properties = {};
        }
        return [node];
      });
    };
    visit(tree);
  };
}
