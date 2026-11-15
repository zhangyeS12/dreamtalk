import mobileCss from "./mobile.css?raw";
import { expect, test } from "vitest";
import postcss, { type Node } from "postcss";

test("required graph geometry and sheet styles have a phone-width base rule", () => {
  const tree = postcss.parse(mobileCss);
  for (const selector of [".mobile-contacts .atlas-surface", ".mobile-contacts .atlas-surface canvas",
    ".mobile-contacts .atlas-search", ".mobile-app dialog.relation-pair-sheet"]) {
    let base = false;
    tree.walkRules(rule => {
      if (!rule.selector.split(",").map(s => s.trim()).includes(selector)) return;
      let parent: Node["parent"] = rule.parent;
      let constrained = false;
      while (parent) {
        if (parent instanceof postcss.AtRule && parent.name === "media" && /(?:min|max)-width/.test(parent.params)) constrained = true;
        parent = parent.parent;
      }
      if (!constrained) base = true;
    });
    expect(base, selector + " must apply below 560px").toBe(true);
  }
});
