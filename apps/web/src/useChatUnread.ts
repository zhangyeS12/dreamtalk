import { useCallback, useEffect, useRef, useState } from "react";
import { CoreClient, type ChatMessage, type ChatUnreadStatus } from "@dreamtalk/api-client";

const READ_EVENT = "dreamtalk:chat-read";

export function useChatUnread(client: CoreClient, worldId: string, playerId: string | null) {
  const [result, setResult] = useState<{ scope: string; value: ChatUnreadStatus } | null>(null);
  const [error, setError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const scope = `${worldId}:${playerId ?? ""}`;
  useEffect(() => {
    let active = true, running = false, failures = 0;
    let timer: number | undefined;
    const controller = new AbortController();
    setError(false);
    if (!worldId || !playerId) return;
    const read = async () => {
      if (!active || running) return;
      running = true;
      window.clearTimeout(timer);
      try {
        const value = await client.chatUnread(worldId, controller.signal);
        if (value.player_id !== playerId) throw new Error("player_changed");
        if (active) { setResult({ scope, value }); setError(false); failures = 0; }
      } catch { failures += 1; if (active) setError(true); }
      finally { running = false; if (active && failures < 2) timer = window.setTimeout(() => void read(), 5000); }
    };
    // A read acknowledgement can arrive while the previous GET is in flight.
    // Restarting the effect discards that older result and requests a fresh snapshot.
    const acknowledged = (event: Event) => { if ((event as CustomEvent<string>).detail === worldId) setRefresh(n => n + 1); };
    window.addEventListener(READ_EVENT, acknowledged);
    void read();
    return () => { active = false; controller.abort(); window.clearTimeout(timer); window.removeEventListener(READ_EVENT, acknowledged); };
  }, [client, worldId, playerId, scope, refresh]);
  const value = result?.scope === scope ? result.value : null;
  return { value, error, refresh: useCallback(() => setRefresh(n => n + 1), []),
    hasUnread: Boolean(value?.items.some(item => item.unread > 0)),
    unread: (conversationId: string) => (value?.items.find(item => item.conversation_id === conversationId)?.unread ?? 0) > 0 };
}

/** Only acknowledge a loaded message visibly intersecting the current transcript. */
export function useConversationRead(client: CoreClient, worldId: string, conversationId: string, messages: ChatMessage[] | null) {
  const acknowledged = useRef(0);
  const attempts = useRef(new Map<number, number>());
  const loadedMessages = useRef(messages);
  loadedMessages.current = messages;
  const firstMessageId = messages?.[0]?.message_id ?? "";
  const lastMessageId = messages?.[messages.length - 1]?.message_id ?? "";
  const messageCount = messages?.length ?? 0;
  const [error, setError] = useState(false);
  const [retryRevision, setRetryRevision] = useState(0);
  useEffect(() => { acknowledged.current = 0; attempts.current.clear(); setError(false); }, [worldId, conversationId]);
  useEffect(() => {
    let active = true, running = false;
    let retryTimer: number | undefined;
    const check = async () => {
      if (!active || running || document.visibilityState !== "visible" || !document.hasFocus()) return;
      let position = 0;
      for (const message of loadedMessages.current ?? []) {
        const element = document.querySelector<HTMLElement>(`[data-message-id="${message.message_id}"]`);
        const scroller = element?.closest<HTMLElement>(".conversation-detail");
        if (!element || !scroller) continue;
        const r = element.getBoundingClientRect(), viewport = scroller.getBoundingClientRect();
        if (r.height > 0 && r.bottom > Math.max(0, viewport.top) && r.top < Math.min(window.innerHeight, viewport.bottom)) position = Math.max(position, message.position);
      }
      if (position <= acknowledged.current || (attempts.current.get(position) ?? 0) >= 3) return;
      running = true;
      attempts.current.set(position, (attempts.current.get(position) ?? 0) + 1);
      try {
        if (!active || document.visibilityState !== "visible" || !document.hasFocus()) return;
        await client.markConversationRead(worldId, conversationId, position);
        if (active) { acknowledged.current = position; setError(false); window.dispatchEvent(new CustomEvent(READ_EVENT, { detail: worldId })); }
      } catch {
        if (active) {
          if ((attempts.current.get(position) ?? 0) < 3) retryTimer = window.setTimeout(() => void check(), 1500);
          else setError(true);
        }
      }
      finally { running = false; }
    };
    const changed = () => { void check(); };
    const frame = window.requestAnimationFrame(changed);
    window.addEventListener("focus", changed); document.addEventListener("visibilitychange", changed);
    window.addEventListener("resize", changed); document.addEventListener("scroll", changed, true);
    return () => { active = false; window.cancelAnimationFrame(frame); window.clearTimeout(retryTimer); window.removeEventListener("focus", changed);
      document.removeEventListener("visibilitychange", changed); window.removeEventListener("resize", changed); document.removeEventListener("scroll", changed, true); };
  }, [client, worldId, conversationId, firstMessageId, lastMessageId, messageCount, retryRevision]);
  return { error, retry: () => { attempts.current.clear(); setError(false); setRetryRevision(n => n + 1); } };
}
