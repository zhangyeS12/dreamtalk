import { useEffect, useRef, useState } from "react";
import { CoreClient, type ChatMessage } from "@dreamtalk/api-client";

interface TranscriptState {
  key: string;
  messages: ChatMessage[] | null;
  latestLoaded: boolean;
  beforePosition: number | null;
  loadingOlder: boolean;
  failed: boolean;
}

const initial = (key: string): TranscriptState => ({
  key, messages: null, latestLoaded: false, beforePosition: null, loadingOlder: false, failed: false,
});

function mergeMessages(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const byId = new Map([...current, ...incoming].map(message => [message.message_id, message]));
  return [...byId.values()].sort((left, right) => left.position - right.position);
}

/** Bounded transcript reads; a new page is merged by durable message identity. */
export function useTranscriptPages(client: CoreClient, worldId: string, conversationId: string, refresh: number, poll = false) {
  const key = `${worldId}/${conversationId}`;
  const currentKey = useRef(key);
  currentKey.current = key;
  const [state, setState] = useState<TranscriptState>(() => initial(key));

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    let failures = 0;
    setState(current => current.key === key ? { ...current, failed: false } : initial(key));
    const readLatest = async () => {
      try {
        const page = await client.conversationMessagePage(worldId, conversationId);
        if (!active) return;
        failures = 0;
        setState(current => {
          if (current.key !== key) return current;
          const previous = current.messages;
          if (!current.latestLoaded || previous === null || previous.length === 0) {
            return { ...current, latestLoaded: true, messages: mergeMessages(previous ?? [], page.items), beforePosition: page.next_before_position, failed: false };
          }
          // A large concurrent append may leave a gap. Restart at the latest page.
          if (page.items.length > 0 && page.items[0].position > previous[previous.length - 1].position + 1) {
            return { ...current, messages: page.items, beforePosition: page.next_before_position, failed: false };
          }
          return { ...current, messages: mergeMessages(previous, page.items), failed: false };
        });
      } catch {
        failures += 1;
        if (active) setState(current => current.key === key ? { ...current, failed: true } : current);
      } finally {
        // Serial reads prevent slow connections from piling up requests. Two
        // failures pause polling; an explicit refresh can start it again.
        if (active && poll && failures < 2) timer = window.setTimeout(() => { void readLatest(); }, 2000);
      }
    };
    void readLatest();
    return () => { active = false; window.clearTimeout(timer); };
  }, [client, worldId, conversationId, key, refresh, poll]);

  const loadOlder = async (beforePrepend: () => void) => {
    if (state.key !== key || state.messages === null || state.loadingOlder || state.beforePosition === null) return;
    const cursor = state.beforePosition;
    setState(current => ({ ...current, loadingOlder: true, failed: false }));
    try {
      const page = await client.conversationMessagePage(worldId, conversationId, cursor);
      if (currentKey.current !== key) return;
      if (page.items.length > 0) beforePrepend();
      setState(current => current.key === key && current.beforePosition === cursor
        ? { ...current, messages: mergeMessages(current.messages ?? [], page.items), beforePosition: page.next_before_position, loadingOlder: false }
        : current);
    } catch {
      setState(current => current.key === key ? { ...current, loadingOlder: false, failed: true } : current);
    }
  };

  const acceptMessage = (message: ChatMessage) => {
    if (message.conversation_id !== conversationId || currentKey.current !== key) return;
    setState(current => current.key === key
      ? { ...current, messages: mergeMessages(current.messages ?? [], [message]) }
      : current);
  };

  return {
    acceptMessage,
    messages: state.key === key ? state.messages : null,
    hasOlder: state.key === key && state.beforePosition !== null,
    loadingOlder: state.key === key && state.loadingOlder,
    failed: state.key === key && state.failed,
    loadOlder,
  };
}
