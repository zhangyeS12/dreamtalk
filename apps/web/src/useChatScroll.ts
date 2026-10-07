import { useEffect, useLayoutEffect, useRef } from "react";
import type { ChatMessage } from "@dreamtalk/api-client";

/** Follow new messages only while the reader remains near the bottom. */
export function useChatScroll(messages: ChatMessage[] | null, progressText?: string) {
  const thread = useRef<HTMLElement>(null);
  const followLatest = useRef(true);
  const prependAnchor = useRef<{ height: number; top: number; id?: string; offset?: number } | null>(null);

  const beforePrepend = () => {
    const scroller = thread.current?.parentElement;
    if (scroller) {
      const edge = scroller.getBoundingClientRect().top;
      const visible = [...(thread.current?.querySelectorAll<HTMLElement>("[data-message-id]") ?? [])]
        .find(item => item.getBoundingClientRect().bottom > edge);
      prependAnchor.current = {
        height: scroller.scrollHeight, top: scroller.scrollTop,
        id: visible?.dataset.messageId, offset: visible ? visible.getBoundingClientRect().top - edge : undefined,
      };
      followLatest.current = false;
    }
  };

  useEffect(() => {
    const scroller = thread.current?.parentElement;
    if (!scroller) return;
    const onScroll = () => {
      followLatest.current = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight <= 80;
    };
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", onScroll);
  }, []);

  useLayoutEffect(() => {
    const scroller = thread.current?.parentElement;
    if (messages === null) { followLatest.current = true; prependAnchor.current = null; return; }
    if (!scroller) return;
    if (prependAnchor.current) {
      const anchor = prependAnchor.current;
      const retained = [...(thread.current?.querySelectorAll<HTMLElement>("[data-message-id]") ?? [])]
        .find(item => item.dataset.messageId === anchor.id);
      if (retained && anchor.offset !== undefined) {
        scroller.scrollTop += retained.getBoundingClientRect().top - scroller.getBoundingClientRect().top - anchor.offset;
      } else scroller.scrollTop = anchor.top + scroller.scrollHeight - anchor.height;
      prependAnchor.current = null;
    } else if (followLatest.current) scroller.scrollTop = scroller.scrollHeight;
  }, [messages, progressText]);

  const followBottom = () => { prependAnchor.current = null; followLatest.current = true; };
  return { thread, beforePrepend, followBottom };
}
