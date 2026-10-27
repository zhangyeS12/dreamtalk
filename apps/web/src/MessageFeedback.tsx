import { useEffect, useState } from "react";
import type { ChatMessage, CoreClient } from "@dreamtalk/api-client";
import { ThumbsDown, ThumbsUp } from "lucide-react";

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
    <button type="button" className={vote === "up" ? "active" : ""} aria-label="喜欢这个回复" aria-pressed={vote === "up"} disabled={busy || disabled} onClick={() => void choose("up")} title="以后更多参考这种表达"><ThumbsUp aria-hidden="true" /></button>
    <button type="button" className={vote === "down" ? "active down" : "down"} aria-label="不喜欢这个回复" aria-pressed={vote === "down"} disabled={busy || disabled} onClick={() => void choose("down")} title="以后换一种表达"><ThumbsDown aria-hidden="true" /></button>
    {error && <span role="status">反馈未保存</span>}
  </div>;
}
