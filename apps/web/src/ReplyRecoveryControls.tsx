import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type ReplyRecoveryView } from "@dreamtalk/api-client";

const reasons: Record<string, string> = {
  chat_recovery_unknown: "原调用的结果尚未确认，当前只能检查状态。旧版本未记录结束状态的失败回合也不能直接重放。",
  chat_recovery_running: "原调用仍在处理，请稍后检查状态。",
  chat_recovery_not_latest: "后面已有新消息，请针对最新消息继续聊天。",
  chat_recovery_has_replies: "已有角色发言会保留，本版不替换回复或补续部分群聊。",
  chat_recovery_changed: "回复状态已变化，请读取最新状态后再操作。",
};

export function ReplyRecoveryControls({ client, worldId, conversationId, sourceTurnId, refresh, tokenCeiling, blocked, onGenerate, onBusyChange }: {
  client: CoreClient; worldId: string; conversationId: string; sourceTurnId?: string;
  refresh: number; tokenCeiling: number; blocked: boolean;
  onGenerate: (turnId: string) => Promise<void>; onBusyChange: (busy: boolean) => void;
}) {
  const lifetime = useRef<AbortController | null>(null);
  const lock = useRef(false);
  const readSerial = useRef(0);
  const [view, setView] = useState<ReplyRecoveryView | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [confirmation, setConfirmation] = useState<{ expected: string; ceiling: number } | null>(null);
  const [pending, setPending] = useState<{ expected: string; ceiling: number; requestId: string } | null>(null);
  useEffect(() => { onBusyChange(busy); }, [busy, onBusyChange]);
  useEffect(() => () => onBusyChange(false), [onBusyChange]);
  useEffect(() => {
    const request = new AbortController(); lifetime.current = request;
    setView(null); setNotice(""); setConfirmation(null); setPending(null); setBusy(false); lock.current = false;
    const serial = ++readSerial.current;
    if (!sourceTurnId) return () => request.abort();
    void client.replyRecovery(worldId, conversationId, sourceTurnId, request.signal)
      .then(value => { if (!request.signal.aborted && serial === readSerial.current && !lock.current) setView(value); })
      .catch(() => { if (!request.signal.aborted && serial === readSerial.current && !lock.current) setNotice("未能读取恢复状态，可以稍后刷新。刷新不会调用模型。"); });
    return () => request.abort();
  }, [client, worldId, conversationId, sourceTurnId]);
  // Transcript refreshes only read status. They never create or execute an attempt.
  useEffect(() => {
    const request = lifetime.current;
    if (!sourceTurnId || !request || request.signal.aborted || lock.current) return;
    let active = true;
    const serial = ++readSerial.current;
    void client.replyRecovery(worldId, conversationId, sourceTurnId, request.signal)
      .then(value => { if (active && !request.signal.aborted && serial === readSerial.current && !lock.current) setView(value); })
      .catch(() => { /* Keep the last confirmed state; explicit refresh remains available. */ });
    return () => { active = false; };
  }, [client, worldId, conversationId, sourceTurnId, refresh]);

  async function run(action: (request: AbortController) => Promise<void>) {
    const request = lifetime.current;
    if (!sourceTurnId || !request || request.signal.aborted || lock.current || blocked) return;
    lock.current = true; ++readSerial.current; setBusy(true); setNotice("");
    try { await action(request); }
    catch (failure) {
      if (!request.signal.aborted) {
        const code = failure instanceof CoreRequestError ? failure.code ?? "" : "";
        setNotice(reasons[code] ?? "操作结果未能确认。请刷新状态；系统不会自动重新调用模型。");
      }
    } finally {
      if (!request.signal.aborted) { lock.current = false; setBusy(false); }
    }
  }
  const read = () => void run(async request => {
    const current = await client.replyRecovery(worldId, conversationId, sourceTurnId!, request.signal);
    if (!request.signal.aborted) { setView(current); setNotice("已读取最新状态，没有调用模型。"); }
  });
  const generate = () => void run(async request => {
    const current = await client.replyRecovery(worldId, conversationId, sourceTurnId!, request.signal);
    if (request.signal.aborted) return;
    setView(current);
    if (!current.can_generate) { setNotice(reasons[current.reason ?? ""] ?? "当前回合不能开始生成，请检查状态。"); return; }
    await onGenerate(current.attempt_turn_id);
    if (request.signal.aborted) return;
    setView(await client.replyRecovery(worldId, conversationId, sourceTurnId!, request.signal));
  });
  const confirm = () => void run(async request => {
    const attempt = pending ?? (confirmation ? { ...confirmation, requestId: crypto.randomUUID() } : null);
    if (!attempt) return;
    setPending(attempt);
    let receipt;
    try {
      receipt = await client.createReplyRecovery(worldId, conversationId, sourceTurnId!, attempt.expected, attempt.ceiling, attempt.requestId, request.signal);
    } catch (failure) {
      if (failure instanceof CoreRequestError && failure.status >= 400 && failure.status < 500 && !request.signal.aborted) {
        setPending(null); setConfirmation(null);
      }
      throw failure;
    }
    if (request.signal.aborted) return;
    // A lost preparation response can be retried with the same request ID. Read
    // after its receipt; never turn an uncertain generation into a replay.
    setPending(null); setConfirmation(null);
    const current = await client.replyRecovery(worldId, conversationId, sourceTurnId!, request.signal);
    if (request.signal.aborted) return;
    setView(current);
    if (current.attempt_turn_id !== receipt.turn_id || !current.can_generate) {
      setNotice(reasons[current.reason ?? ""] ?? "此次尝试已有状态，请检查回复记录。"); return;
    }
    await onGenerate(receipt.turn_id);
    if (request.signal.aborted) return;
    setView(await client.replyRecovery(worldId, conversationId, sourceTurnId!, request.signal));
  });

  if (!sourceTurnId || view?.state === "completed" || view?.state === "has_replies") return null;
  return <section className="reply-recovery" aria-label="回复恢复">
    {notice && <p role="status">{notice}</p>}
    {view?.reason && <p className="inline-hint">{reasons[view.reason] ?? "当前无法恢复此回合。"}</p>}
    {view?.can_generate && <p className="inline-hint">这条消息已保存但尚未开始生成。手动生成沿用已保存的 {view.token_ceiling.toLocaleString("zh-CN")} Token 上限，点击会产生模型用量。</p>}
    <div className="controls">
      {view?.can_generate && <button type="button" disabled={blocked || busy || !!pending} onClick={generate}>生成已保存消息的回复（调用模型）</button>}
      {view?.can_create && !confirmation && !pending && <button type="button" disabled={blocked || busy} onClick={() => setConfirmation({ expected: view.attempt_turn_id, ceiling: tokenCeiling })}>重新生成…</button>}
      <button type="button" disabled={blocked || busy} onClick={read}>刷新恢复状态</button>
    </div>
    {confirmation || pending ? <div role="alertdialog" aria-labelledby="reply-recovery-title">
      <p id="reply-recovery-title">为同一条消息开始一个新的付费尝试？</p>
      <p>原消息不会重复，原调用用量保留。本次输入与输出共用 {(pending ?? confirmation)!.ceiling.toLocaleString("zh-CN")} Token 上限，采用当前模型和费用预算。系统不会自动重试。</p>
      {pending && <p>准备结果尚未确认。再次确认沿用同一个请求，不会创建多个尝试；生成前会核对最新状态。</p>}
      <button type="button" className="primary-button" disabled={blocked || busy} onClick={confirm}>{busy ? "处理中…" : pending ? "重试确认同一请求" : "确认并生成（产生模型用量）"}</button>
      <button type="button" disabled={busy} onClick={() => { setConfirmation(null); setPending(null); }}>取消</button>
    </div> : null}
  </section>;
}
