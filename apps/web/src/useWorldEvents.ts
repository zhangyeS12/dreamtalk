import { useCallback, useEffect, useReducer } from "react";
import type { CoreClient, KnownWorldEvent } from "@dreamtalk/api-client";

type Scope = { worldId: string; playerId: string | null };
type Draft = Scope & { conversationId: string; text: string };
type State = { open: boolean; known: (Scope & { items: KnownWorldEvent[] }) | null;
  topic: (Scope & { event: KnownWorldEvent }) | null; draft: Draft | null };
type Action = { type: "identity" } | { type: "open"; open: boolean }
  | { type: "known"; scope: Scope; items: KnownWorldEvent[] }
  | { type: "topic"; scope: Scope; event: KnownWorldEvent | null }
  | { type: "draft-used" } | { type: "discuss"; draft: Draft };
function reduce(state: State, action: Action): State {
  switch (action.type) {
    case "identity": return { ...state, known: null, topic: null, draft: null };
    case "open": return { ...state, open: action.open };
    case "known": return { ...state, known: { ...action.scope, items: action.items } };
    case "topic": return { ...state, topic: action.event ? { ...action.scope, event: action.event } : null };
    case "draft-used": return { ...state, draft: null };
    case "discuss": return { ...state, open: false, topic: null, draft: action.draft };
  }
}
function matches(scope: Scope | null, worldId: string, playerId: string | null) {
  return scope?.worldId === worldId && scope.playerId === playerId;
}

export function useWorldEvents(client: CoreClient, worldId: string, playerId: string | null,
  onError: (message: string) => void, displayTime: (raw: string) => string) {
  const [state, dispatch] = useReducer(reduce, { open: false, known: null, topic: null, draft: null });
  useEffect(() => { dispatch({ type: "identity" }); }, [worldId, playerId]);
  useEffect(() => {
    if (!worldId || !playerId || !state.open) return;
    let active = true;
    let timer: number | undefined;
    const controller = new AbortController();
    const read = async () => {
      try {
        const items = await client.knownEvents(worldId, controller.signal);
        if (active) dispatch({ type: "known", scope: { worldId, playerId }, items });
      } catch { if (active) onError("无法读取已获知的事件。"); }
      finally { if (active) timer = window.setTimeout(() => void read(), 2_000); }
    };
    void read();
    return () => { active = false; controller.abort(); window.clearTimeout(timer); };
  }, [client, worldId, playerId, state.open, onError]);
  const setEventsOpen = useCallback((open: boolean) => dispatch({ type: "open", open }), []);
  const setTopicEvent = useCallback((event: KnownWorldEvent | null) => dispatch({ type: "topic", scope: { worldId, playerId }, event }), [worldId, playerId]);
  const clearSuggestion = useCallback(() => dispatch({ type: "draft-used" }), []);
  const discuss = useCallback((conversationId: string): boolean => {
    if (!playerId || !matches(state.topic, worldId, playerId) || !state.topic) return false;
    const event = state.topic.event;
    dispatch({ type: "discuss", draft: { worldId, playerId, conversationId,
      text: `我看到一条世界事件：「${event.description || event.title}」（${displayTime(event.occurred_at)}）。你知道这件事吗？` } });
    return true;
  }, [worldId, playerId, state.topic, displayTime]);
  const suggestedFor = (conversationId: string) => matches(state.draft, worldId, playerId) && state.draft?.conversationId === conversationId ? state.draft.text : null;
  return { eventsOpen: state.open, setEventsOpen,
    visibleEvents: matches(state.known, worldId, playerId) ? state.known!.items : [],
    topicEvent: matches(state.topic, worldId, playerId) ? state.topic!.event : null,
    setTopicEvent, clearSuggestion, discuss, suggestedFor };
}
