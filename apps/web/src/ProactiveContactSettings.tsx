import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type ProactiveContactStatus } from "@dreamtalk/api-client";

function failureMessage(failure: unknown): string {
  if (failure instanceof CoreRequestError && failure.code === "proactive_settings_changed") return "设置已变化，请刷新状态后再保存。";
  if (failure instanceof CoreRequestError && failure.code === "proactive_model_unavailable") return "当前模型尚不可用，请先检查模型设置。";
  return "未能确认主动联系设置，请刷新状态后重试。";
}
export function ProactiveContactSettings({ client, worldId, playerId }: { client: CoreClient; worldId: string; playerId: string }) {
  const [status, setStatus] = useState<ProactiveContactStatus | null>(null);
  const [minutes, setMinutes] = useState("360");
  const [consenting, setConsenting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const latest = useRef<ProactiveContactStatus | null>(null);
  const writing = useRef(false);
  const alive = useRef(false);
  const serial = useRef(0);
  useEffect(() => { alive.current = true; return () => { alive.current = false; serial.current += 1; }; }, []);
  useEffect(() => {
    let active = true, failures = 0;
    let timer: number | undefined;
    const controller = new AbortController();
    const read = async () => {
      const ticket = serial.current;
      try {
        if (!writing.current) {
          const value = await client.proactiveContactStatus(worldId, controller.signal);
          if (!active || ticket !== serial.current || writing.current) return;
          if (value.player_id !== playerId) throw new Error("player_changed");
          const first = latest.current === null;
          latest.current = value; setStatus(value);
          if (first) setMinutes(String(value.interval_minutes));
          failures = 0;
        }
      } catch { failures += 1; if (active) setError("无法读取主动联系状态，请点击刷新状态重试。"); }
      finally { if (active && failures < 2) timer = window.setTimeout(() => void read(), 10000); }
    };
    setError(""); void read();
    return () => { active = false; controller.abort(); window.clearTimeout(timer); };
  }, [client, worldId, playerId, refresh]);
  const save = async (enabled: boolean, consent = false) => {
    if (!latest.current || writing.current) return;
    const amount = Number(minutes);
    if (!Number.isInteger(amount) || amount < 15 || amount > 1440) { setError("请输入15～1440之间的整数世界分钟。"); return; }
    writing.current = true; setBusy(true); setError("");
    const ticket = ++serial.current;
    try {
      const value = await client.configureProactiveContact(worldId, latest.current, enabled, amount, consent);
      if (!alive.current || ticket !== serial.current) return;
      latest.current = value; setStatus(value); setMinutes(String(value.interval_minutes)); setConsenting(false);
    } catch (failure) { if (alive.current && ticket === serial.current) setError(failureMessage(failure)); }
    finally { writing.current = false; if (alive.current && ticket === serial.current) { setBusy(false); setRefresh(n => n + 1); } }
  };
  const label = status?.state === "waiting_reply" ? "等待你回复上一次主动联系，期间所有角色都不会再次主动联系。"
    : status?.state === "writing" ? "正在准备一次主动联系。"
    : status?.state === "attention" ? "本次任务已停止，不会自动重试模型调用。"
    : status?.enabled ? "已开启；达到间隔并有真实活动理由时才联系。" : "尚未开启在线主动联系。";
  return <section className="settings-section" aria-label="在线主动联系">
    <h3>角色主动联系</h3><p>角色休息或自由活动时，可以主动邀你加入。两名角色必须正在一起参加同一次共同休闲，才能在同一个群聊共同邀请。</p>
    <p role="status">{label}</p>
    <div className="inline-form"><label>最短联系间隔（世界分钟）<input type="number" min={15} max={1440} step={1} value={minutes} disabled={busy} onChange={event => setMinutes(event.target.value)} /></label>
      <button type="button" className="secondary-button" disabled={!status || busy || (!status.enabled && !status.model_available)} onClick={() => status?.enabled ? void save(false) : status?.consented ? void save(true) : setConsenting(true)}>{status?.enabled ? "关闭主动联系" : "开启主动联系"}</button>
      <button type="button" className="secondary-button" disabled={!status?.enabled || busy || Number(minutes) === status.interval_minutes} onClick={() => void save(true)}>保存间隔</button>
      <button type="button" className="text-action" disabled={busy} onClick={() => setRefresh(n => n + 1)}>刷新状态</button></div>
    <p className="inline-hint">默认360分钟，首次开启从此刻计时，每批日常最多一次。忙碌、暂停或没有有效活动时跳过。打开会话只清除红点；只有在收到联系的会话里发送回复才解除等待。在线与离线联系共用这个限制。</p>
    <p className="inline-hint">依赖已开启的世界自动活动；多人还需开启相遇和共同休闲。程序完全退出或电脑关机后停止。后台生成使用当前模型、遵守已有任务预算，可能产生费用。</p>
    {consenting && <div className="inline-notice"><p>同意此世界使用已确认角色资料、实际活动与公共背景生成主动消息。私聊正文、摘要、私人记忆和隐藏世界书不发送。双人消息一次生成，同一件事共同发出邀请。</p><button type="button" className="primary-button" disabled={busy} onClick={() => void save(true, true)}>同意后台模型用量并开启</button><button type="button" className="text-action" disabled={busy} onClick={() => setConsenting(false)}>暂不开启</button></div>}
    {status?.error && <p className="app-alert">{status.error === "proactive_context_changed" ? "活动、资料或玩家状态已变化，迟到邀请已取消。" : status.error === "proactive_input_unavailable" ? "角色活动或获准资料暂不可用，请检查后关闭再开启。" : "本次生成未完成或被中断，可能已有用量。检查后可关闭再开启；不会重放原任务。"}</p>}
    {error && <p className="app-alert" role="alert">{error}</p>}
  </section>;
}
