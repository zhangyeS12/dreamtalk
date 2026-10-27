import { useEffect, useState } from "react";
import type { ChatMessage, CoreClient } from "@dreamtalk/api-client";

function Thumb({ down = false }: { down?: boolean }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    <path d={down ? "M7 10v10M7 10H4.5A1.5 1.5 0 0 1 3 8.5v-6A1.5 1.5 0 0 1 4.5 1H9l4 9v10H8.5A1.5 1.5 0 0 1 7 18.5V10Zm6 0h5.2a2 2 0 0 1 1.95 2.45l-1.35 6A2 2 0 0 1 16.85 20H13" : "M7 14V4M7 14H4.5A1.5 1.5 0 0 1 3 12.5v-6A1.5 1.5 0 0 1 4.5 5H9l4-4v10H8.5A1.5 1.5 0 0 1 7 14Zm6-4h5.2a2 2 0 0 0 1.95-2.45l-1.35-6A2 2 0 0 0 16.85 0H13"} />
  </svg>;
}

export function MessageFeedback({ client, worldId, conversationId, message, disabled = false }: {
  client: CoreClient;
  worldId: string;
  conversationId: string;
  message: ChatMessage;
  disabled?: boolean;
}) {
  const [vote, setVote] = useState<"up" | "down" | null>(message.feedback ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => { setVote(message.feedback ?? null); }, [message.feedback, message.message_id]);
  const choose = async (next: "up" | "down") => {
    if (busy || disabled) return;
    const value = vote === next ? null : next;
    setBusy(true); setError(false);
    try {
      const saved = await client.setMessageFeedback(worldId, conversationId, message.message_id, value);
      setVote(saved.feedback ?? null);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };
  return <div className="message-feedback" aria-label="回复反馈">
    <button type="button" className={vote === "up" ? "active" : ""} aria-label="喜欢这个回复" aria-pressed={vote === "up"} disabled={busy || disabled} onClick={() => void choose("up")} title="以后更多参考这种表达"><Thumb /></button>
    <button type="button" className={vote === "down" ? "active" : ""} aria-label="不喜欢这个回复" aria-pressed={vote === "down"} disabled={busy || disabled} onClick={() => void choose("down")} title="以后换一种表达"><Thumb down /></button>
    {error && <span role="status">反馈未保存</span>}
  </div>;
}
