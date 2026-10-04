import { useCallback, useEffect, useRef, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
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
    const acknowledged = (event: Event) => { if ((event as CustomEvent<string>).detail === worldId) void read(); };
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
  useEffect(() => {
    let active = true, running = false;
    const check = async () => {
      if (!active || running || document.visibilityState !== "visible" || !document.hasFocus()) return;
      let position = 0;
      for (const message of messages ?? []) {
        const element = document.querySelector<HTMLElement>(`[data-message-id="${message.message_id}"]`);
        const parent = element?.closest<HTMLElement>(".chat-thread");
        if (!element || !parent) continue;
        const r = element.getBoundingClientRect(), p = parent.getBoundingClientRect();
        if (r.height > 0 && r.bottom > Math.max(0, p.top) && r.top < Math.min(window.innerHeight, p.bottom)) position = Math.max(position, message.position);
      }
      if (position <= acknowledged.current || (attempts.current.get(position) ?? 0) >= 2) return;
      running = true;
      attempts.current.set(position, (attempts.current.get(position) ?? 0) + 1);
      try {
        if (isTauri() && !await invoke<boolean>("report_desktop_presence", { worldId, visible: true })) return;
        if (!active || !document.hasFocus()) return;
        await client.markConversationRead(worldId, conversationId, position);
        if (active) { acknowledged.current = position; window.dispatchEvent(new CustomEvent(READ_EVENT, { detail: worldId })); }
      } catch { /* Two bounded read acknowledgements; no model work or hidden-tab acknowledgement. */ }
      finally { running = false; }
    };
    const changed = () => { void check(); };
    const frame = window.requestAnimationFrame(changed);
    window.addEventListener("focus", changed); document.addEventListener("visibilitychange", changed);
    document.addEventListener("scroll", changed, true);
    return () => { active = false; window.cancelAnimationFrame(frame); window.removeEventListener("focus", changed);
      document.removeEventListener("visibilitychange", changed); document.removeEventListener("scroll", changed, true); };
  }, [client, worldId, conversationId, messages]);
}
