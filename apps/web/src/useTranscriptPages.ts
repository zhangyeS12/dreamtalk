import { useEffect, useRef, useState } from "react";
import { CoreClient, type ChatMessage } from "@dreamtalk/api-client";

interface TranscriptState {
  key: string;
  messages: ChatMessage[] | null;
  latestLoaded: boolean;
  beforePosition: number | null;
  loadingOlder: boolean;
  failed: boolean;
  followingLatest: boolean;
}

const initial = (key: string): TranscriptState => ({
  key, messages: null, latestLoaded: false, beforePosition: null, loadingOlder: false, failed: false, followingLatest: true,
});

const MAX_VISIBLE_MESSAGES = 200;

function mergeMessages(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const byId = new Map([...current, ...incoming].map(message => [message.message_id, message]));
  return [...byId.values()].sort((left, right) => left.position - right.position);
}

/** Bounded transcript reads; a new page is merged by durable message identity. */
export function useTranscriptPages(client: CoreClient, worldId: string, conversationId: string, refresh: number, poll = false) {
  const key = `${worldId}/${conversationId}`;
  const currentKey = useRef(key);
  currentKey.current = key;
  const latestGeneration = useRef(0);
  const [latestRequest, setLatestRequest] = useState(0);
  const [state, setState] = useState<TranscriptState>(() => initial(key));

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    let timer: number | undefined;
    let failures = 0;
    setState(current => current.key === key ? { ...current, failed: false } : initial(key));
    const readLatest = async () => {
      try {
        const page = await client.conversationMessagePage(worldId, conversationId, undefined, controller.signal);
        if (!active) return;
        failures = 0;
        setState(current => {
          if (current.key !== key) return current;
          if (!current.followingLatest) return { ...current, failed: false };
          const previous = current.messages;
          if (!current.latestLoaded || previous === null || previous.length === 0) {
            return { ...current, latestLoaded: true, messages: mergeMessages(previous ?? [], page.items).slice(-MAX_VISIBLE_MESSAGES), beforePosition: page.next_before_position, failed: false };
          }
          // A large concurrent append may leave a gap. Restart at the latest page.
          if (page.items.length > 0 && page.items[0].position > previous[previous.length - 1].position + 1) {
            return { ...current, messages: page.items, beforePosition: page.next_before_position, failed: false };
          }
          const merged = mergeMessages(previous, page.items);
          const messages = merged.slice(-MAX_VISIBLE_MESSAGES);
          return { ...current, messages, beforePosition: merged.length > MAX_VISIBLE_MESSAGES ? messages[0].position : current.beforePosition, failed: false };
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
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [client, worldId, conversationId, key, refresh, poll, latestRequest]);

  const loadOlder = async (beforePrepend: () => void) => {
    if (state.key !== key || state.messages === null || state.loadingOlder || state.beforePosition === null) return;
    const cursor = state.beforePosition;
    const generation = latestGeneration.current;
    setState(current => ({ ...current, loadingOlder: true, failed: false }));
    try {
      const page = await client.conversationMessagePage(worldId, conversationId, cursor);
      if (currentKey.current !== key || generation !== latestGeneration.current) return;
      if (page.items.length > 0) beforePrepend();
      setState(current => current.key === key && current.beforePosition === cursor
        ? { ...current, messages: mergeMessages(current.messages ?? [], page.items).slice(0, MAX_VISIBLE_MESSAGES), beforePosition: page.next_before_position, loadingOlder: false, followingLatest: false }
        : current);
    } catch {
      if (currentKey.current === key && generation === latestGeneration.current) setState(current => current.key === key ? { ...current, loadingOlder: false, failed: true } : current);
    }
  };

  const acceptMessage = (message: ChatMessage) => {
    if (message.conversation_id !== conversationId || currentKey.current !== key) return;
    setState(current => {
      if (current.key !== key || !current.followingLatest) return current;
      const merged = mergeMessages(current.messages ?? [], [message]);
      const messages = merged.slice(-MAX_VISIBLE_MESSAGES);
      return { ...current, messages, beforePosition: merged.length > MAX_VISIBLE_MESSAGES ? messages[0].position : current.beforePosition };
    });
  };

  const showLatest = () => {
    latestGeneration.current += 1;
    setState(initial(key));
    setLatestRequest(value => value + 1);
  };

  return {
    acceptMessage, showLatest,
    followingLatest: state.key !== key || state.followingLatest,
    messages: state.key === key ? state.messages : null,
    hasOlder: state.key === key && state.beforePosition !== null,
    loadingOlder: state.key === key && state.loadingOlder,
    failed: state.key === key && state.failed,
    loadOlder,
  };
}
