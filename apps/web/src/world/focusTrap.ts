import type { KeyboardEvent } from "react";

const FOCUSABLE = "a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex='-1'])";

/** Keep Tab inside a modal: from the last control wrap to the first, and back. */
export function trapTab(event: KeyboardEvent<HTMLElement>) {
  if (event.key !== "Tab") return;
  const items = [...event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(item => item.getClientRects().length > 0);
  if (!items.length) { event.preventDefault(); return; }
  const first = items[0], last = items[items.length - 1], active = document.activeElement;
  if (event.shiftKey && (active === first || !event.currentTarget.contains(active))) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && active === last) { event.preventDefault(); first.focus(); }
}
