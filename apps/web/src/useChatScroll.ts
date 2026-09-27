import { useEffect, useLayoutEffect, useRef } from "react";
import type { ChatMessage } from "@dreamtalk/api-client";

/** Follow new messages only while the reader remains near the bottom. */
export function useChatScroll(messages: ChatMessage[] | null) {
  const thread = useRef<HTMLElement>(null);
  const followLatest = useRef(true);

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
    if (messages !== null && scroller && followLatest.current) scroller.scrollTop = scroller.scrollHeight;
  }, [messages]);

  return thread;
}
