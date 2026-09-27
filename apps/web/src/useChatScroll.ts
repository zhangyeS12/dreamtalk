import { useEffect, useLayoutEffect, useRef } from "react";
import type { ChatMessage } from "@dreamtalk/api-client";

/** Follow new messages only while the reader remains near the bottom. */
export function useChatScroll(messages: ChatMessage[] | null) {
  const thread = useRef<HTMLElement>(null);
  const followLatest = useRef(true);
  const prependAnchor = useRef<{ height: number; top: number } | null>(null);

  const beforePrepend = () => {
    const scroller = thread.current?.parentElement;
    if (scroller) {
      prependAnchor.current = { height: scroller.scrollHeight, top: scroller.scrollTop };
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
    if (messages === null || !scroller) return;
    if (prependAnchor.current) {
      scroller.scrollTop = prependAnchor.current.top + scroller.scrollHeight - prependAnchor.current.height;
      prependAnchor.current = null;
    } else if (followLatest.current) scroller.scrollTop = scroller.scrollHeight;
  }, [messages]);

  return { thread, beforePrepend };
}
