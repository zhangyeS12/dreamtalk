import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type ChatMessage } from "@dreamtalk/api-client";

/** Provisional text belongs to this mounted conversation and is never persisted. */
export function useReplyStream() {
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);
  const stopped = useRef(false);
  const [stopping, setStopping] = useState(false);
  const [draft, setDraft] = useState<{ turnId: string; index: number; speakerId: string; text: string } | null>(null);
  const [stage, setStage] = useState<"preparing" | "selecting" | "replying" | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; controller.current?.abort(); };
  }, []);

  const run = async (
    client: CoreClient, worldId: string, conversationId: string, turnId: string,
    kind: "direct" | "group", speakers: string[], acceptMessage: (message: ChatMessage) => void,
  ) => {
    if (!mounted.current) throw new DOMException("conversation_closed", "AbortError");
    const request = new AbortController();
    controller.current = request;
    stopped.current = false;
    setStopping(false); setDraft(null); setStage("preparing");
    let committed = 0;
    try {
      await client.streamChatReply(worldId, conversationId, turnId, kind, event => {
        if (!mounted.current || request.signal.aborted) return;
        if ((event.kind === "replying" || event.kind === "delta") && !speakers.includes(event.speaker_id)
          || event.kind === "message" && !speakers.includes(event.message.sender_id)) {
          throw new CoreRequestError(502, "chat_reply_invalid");
        }
        if (event.kind === "preparing" || event.kind === "selecting") setStage(event.kind);
        else if (event.kind === "replying") {
          setStage("replying"); setDraft({ turnId, index: committed, speakerId: event.speaker_id, text: "" });
        } else if (event.kind === "delta") {
          setDraft(current => current?.speakerId === event.speaker_id ? { ...current, text: current.text + event.text } : current);
        } else if (event.kind === "message") {
          committed += 1; acceptMessage(event.message); setDraft(null);
        }
      }, request.signal);
    } finally {
      if (controller.current === request) controller.current = null;
      if (mounted.current) { setDraft(null); setStage(null); setStopping(false); }
    }
  };

  return {
    run, draft, stage, stopping,
    isMounted: () => mounted.current,
    wasStopped: () => stopped.current,
    stop: () => { stopped.current = true; setStopping(true); controller.current?.abort(); },
  };
}
