import type { Element, Root, RootContent, Text } from "hast";

// Independent quote-based display rule. Never inject HTML or change stored text.
const pairs: Record<string, string> = { '"': '"', "“": "”", "「": "」", "『": "』", "«": "»", "＂": "＂" };
const blocks = new Set(["p", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th"]);
const inert = new Set(["code", "pre", "em", "img", "script", "style"]);

export function dialogueHighlight() {
  return (tree: Root) => {
    const inline = (parent: Root | Element, quotes: string[]) => {
      parent.children = parent.children.flatMap((node): RootContent[] => {
        if (node.type === "element") {
          if (!inert.has(node.tagName)) inline(node, quotes);
          return [node];
        }
        if (node.type !== "text") return [node];
        const segments: RootContent[] = [];
        let buffer = "", active = quotes.length > 0;
        const flush = () => {
          if (!buffer) return;
          const text: Text = { type: "text", value: buffer };
          segments.push(active ? { type: "element", tagName: "span", properties: { className: ["character-dialogue"] }, children: [text] } : text);
          buffer = "";
        };
        for (const character of node.value) {
          const closing = quotes.length > 0 && character === quotes[quotes.length - 1];
          if (!closing && pairs[character]) {
            if (!active) { flush(); active = true; }
            quotes.push(pairs[character]);
          }
          buffer += character;
          if (closing) {
            quotes.pop();
            if (!quotes.length) { flush(); active = false; }
          }
        }
        flush();
        return segments;
      });
    };
    const visit = (parent: Root | Element) => {
      for (const node of parent.children) {
        if (node.type !== "element" || inert.has(node.tagName)) continue;
        if (blocks.has(node.tagName)) inline(node, []);
        else visit(node);
      }
    };
    visit(tree);
  };
}
