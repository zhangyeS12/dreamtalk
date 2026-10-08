import { useEffect, useRef, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type ChatReplyAvailability } from "@dreamtalk/api-client";
import {
  chatReplyFailureFeedback, chatReplyStateFeedback, chatSaveFailureFeedback,
  chatTokenReservationFeedback, type ChatRequestPhase,
} from "./chatFeedback";
import { useReplyStream } from "./useReplyStream";
import { useTranscriptPages } from "./useTranscriptPages";

interface Options {
  client: CoreClient;
  worldId: string;
  playerId: string;
  conversationId: string;
  kind: "direct" | "group";
  speakers: string[];
  tokenCeiling: number;
  suggestedDraft?: string | null;
  onSuggestionUsed?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  readOnly?: boolean;
}

/** Save retries reuse one request ID; uncertain model calls are only inspected. */
export function useChatReplyWorkflow({
  client, worldId, playerId, conversationId, kind, speakers, tokenCeiling,
  suggestedDraft, onSuggestionUsed, onDirtyChange, readOnly = false,
}: Options) {
  const [refresh, setRefresh] = useState(0);
  const [availability, setAvailability] = useState<ChatReplyAvailability | null>(null);
  const [availabilityReading, setAvailabilityReading] = useState(true);
  const [availabilityFailed, setAvailabilityFailed] = useState(false);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<{ text: string; ceiling: number; requestId: string } | null>(null);
  const [phase, setPhase] = useState<ChatRequestPhase>(null);
  const [recoveryBusy, setRecoveryBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [replyFailure, setReplyFailure] = useState<{ turnId: string; message: string } | null>(null);
  const actionLock = useRef(false);
  const stream = useReplyStream();
  const transcript = useTranscriptPages(client, worldId, conversationId, refresh, true);
  const available = !readOnly && availability?.available === true && !availabilityReading && !availabilityFailed;
  const budgetFeedback = chatTokenReservationFeedback(availability, tokenCeiling, kind);
  const sending = phase !== null || recoveryBusy;

  useEffect(() => { onDirtyChange?.(Boolean(draft.trim() || pending || sending)); }, [draft, pending, sending, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  useEffect(() => {
    if (suggestedDraft) { setDraft(suggestedDraft); onSuggestionUsed?.(); }
  }, [suggestedDraft, onSuggestionUsed]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setAvailabilityReading(true); setAvailabilityFailed(false);
    const request = kind === "direct"
      ? client.directReplyAvailability(worldId, controller.signal)
      : client.groupReplyAvailability(worldId, controller.signal);
    void request.then(result => { if (active) setAvailability(result); })
      .catch(() => { if (active) setAvailabilityFailed(true); })
      .finally(() => { if (active) setAvailabilityReading(false); });
    return () => { active = false; controller.abort(); };
  }, [client, worldId, kind, refresh]);

  const readTurn = (turnId: string) => kind === "direct"
    ? client.directTurn(worldId, conversationId, turnId)
    : client.groupTurn(worldId, conversationId, turnId);
  const latestPlayerMessage = transcript.followingLatest ? transcript.messages?.filter(message => message.sender_kind === "player" && message.sender_id === playerId).at(-1) : undefined;
  const visibleStreamDraft = transcript.followingLatest && stream.draft && (transcript.messages?.filter(message => message.turn_id === stream.draft?.turnId && message.sender_kind === "character").length ?? 0) <= stream.draft.index ? stream.draft : null;

  const checkReply = async () => {
    if (actionLock.current || sending || pending || !latestPlayerMessage) return;
    actionLock.current = true; setPhase("checking"); setFeedback("");
    try {
      const recovery = await client.replyRecovery(worldId, conversationId, latestPlayerMessage.turn_id);
      const turn = await readTurn(recovery.attempt_turn_id);
      if (!stream.isMounted()) return;
      setRefresh(value => value + 1);
      setFeedback(turn.state !== "completed" && replyFailure?.turnId === turn.turn_id
        ? replyFailure.message : chatReplyStateFeedback(turn.state, kind));
    } catch { if (stream.isMounted()) setFeedback(chatReplyStateFeedback(null, kind)); }
    finally { actionLock.current = false; if (stream.isMounted()) setPhase(null); }
  };

  const inspectFailedReply = async (turnId: string, failure: unknown, showStopped: boolean) => {
    if (!stream.isMounted()) return;
    setPhase("checking");
    // One status read; never retry or create a model attempt here.
    const turn = await readTurn(turnId).catch(() => null);
    if (!stream.isMounted()) return;
    setRefresh(value => value + 1);
    const message = turn?.state === "completed" ? chatReplyStateFeedback(turn.state, kind)
      : showStopped && stream.wasStopped()
        ? "已请求停止生成。已保存的发言会保留；可检查回复状态，系统不会自动重新调用模型。"
        : chatReplyFailureFeedback(failure, kind);
    setFeedback(message);
    if (turn?.state !== "completed") setReplyFailure({ turnId, message });
  };

  const generateSavedReply = async (turnId: string) => {
    if (actionLock.current || pending || !available) return;
    actionLock.current = true;
    setPhase("replying"); setFeedback(""); setReplyFailure(null);
    try {
      await stream.run(client, worldId, conversationId, turnId, kind, speakers, transcript.acceptMessage);
      if (stream.isMounted()) setRefresh(value => value + 1);
    } catch (failure) { await inspectFailedReply(turnId, failure, false); }
    finally { actionLock.current = false; if (stream.isMounted()) setPhase(null); }
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (actionLock.current || sending || !available || (!draft.trim() && !pending)) return;
    if (budgetFeedback && !pending) { setFeedback(budgetFeedback); return; }
    if (!transcript.followingLatest) transcript.showLatest();
    actionLock.current = true;
    const current = pending ?? { text: draft, ceiling: tokenCeiling, requestId: crypto.randomUUID() };
    setPending(current); setPhase("saving"); setFeedback("");
    try {
      const sent = kind === "direct"
        ? await client.sendPlayerMessage(worldId, conversationId, current.text, current.ceiling, current.requestId)
        : await client.sendGroupMessage(worldId, conversationId, current.text, current.ceiling, current.requestId);
      if (!stream.isMounted()) return;
      setPending(null); setDraft(""); setReplyFailure(null);
      setRefresh(value => value + 1); setPhase("replying");
      try {
        await stream.run(client, worldId, conversationId, sent.turn_id, kind, speakers, transcript.acceptMessage);
        if (stream.isMounted()) setRefresh(value => value + 1);
      } catch (failure) { await inspectFailedReply(sent.turn_id, failure, true); }
    } catch (failure) {
      if (!stream.isMounted()) return;
      if (failure instanceof CoreRequestError && failure.status >= 400 && failure.status < 500) {
        setPending(null); setFeedback(chatSaveFailureFeedback(failure));
      } else {
        setFeedback("消息保存结果尚未确认。可重试保存同一条消息，不会创建重复回合。");
      }
    } finally { actionLock.current = false; if (stream.isMounted()) setPhase(null); }
  };

  return {
    ...transcript, refresh, setRefresh, available, availabilityReading, availabilityFailed,
    budgetFeedback, draft, setDraft, pending, phase, sending, setRecoveryBusy, feedback,
    stream, visibleStreamDraft, latestPlayerMessage, checkReply, generateSavedReply, send,
  };
}
