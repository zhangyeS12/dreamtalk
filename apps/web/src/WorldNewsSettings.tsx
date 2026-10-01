import { useCallback, useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type WorldNewsStatus } from "@dreamtalk/api-client";

const errors: Record<string, string> = {
  news_background_required: "请先确认世界书，并把适用条目逐条设为公共背景；至少一条需要能在世界动态场景触发（例如始终激活）。",
  news_background_invalid: "公共背景格式异常，请检查世界书。",
  news_background_capacity: "公共背景超过资料容量，请精简公开范围。",
  news_background_changed: "本批采用的背景已隐藏或更新，待发布内容已停止；可显式生成新的一批。",
  news_plan_invalid: "模型没有返回有效的10条动态；不会自动重试，重新生成会产生新用量。",
  news_generation_failed: "本批生成未完成，可能已产生用量；请检查模型设置后显式重试。",
  news_interrupted: "上次任务中断或资料已变化，没有自动重发模型请求。",
  news_execution_failed: "事件处理停止，请刷新状态；重新生成是新的模型任务。",
  news_pending_capacity: "未处理事件接近100条上限，请先标记已经历或跳过，再生成。",
  news_model_unavailable: "请先配置可用模型，优先使用 DeepSeek。",
  news_settings_changed: "设置已变化，请刷新状态后重试。",
  news_pool_not_empty: "池内仍有待发布事件，暂不生成新批次。",
};

export function WorldNewsSettings({ client, worldId, visible, paused }: { client: CoreClient; worldId: string; visible: boolean; paused: boolean }) {
  const [status, setStatus] = useState<WorldNewsStatus | null>(null);
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  const busyRef = useRef(false);
  const serial = useRef(0);
  const alive = useRef(true);
  const refresh = useCallback(async () => {
    if (busyRef.current) return;
    const request = ++serial.current;
    try {
      const next = await client.worldNewsStatus(worldId);
      if (alive.current && request === serial.current) { setStatus(next); setLoadError(""); }
    } catch { if (alive.current && request === serial.current) setLoadError("未能读取状态，请检查核心连接后刷新。"); }
  }, [client, worldId]);
  useEffect(() => {
    alive.current = true;
    if (!visible) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { alive.current = false; ++serial.current; window.clearInterval(timer); };
  }, [visible, refresh]);

  async function configure(enabled: boolean, consent = false, replenish = false) {
    if (!status || busyRef.current) return;
    busyRef.current = true; ++serial.current; setBusy(true); setNotice("");
    try {
      const next = await client.configureWorldNews(worldId, status, enabled, consent, replenish);
      if (alive.current) { setStatus(next); setConsentOpen(false); setNotice(enabled ? "已排队；程序运行且世界恢复后处理。" : "已关闭后续发布与续批；已开始的请求仍可能产生用量。"); }
    } catch (error) {
      if (alive.current) setNotice(error instanceof CoreRequestError && error.code && errors[error.code] ? errors[error.code] : "未能保存，请刷新状态后重试；未自动重试模型请求。");
    } finally { busyRef.current = false; if (alive.current) setBusy(false); }
  }
  const state = status?.state;
  const label = paused && status?.enabled ? "世界已暂停，生成和发布等待恢复。" : state === "generating" ? "正在生成一批动态……" : state === "ready" ? "事件池已就绪，按世界时间逐条发布。" : state === "attention" ? "事件池需要处理。" : state === "idle" ? "等待规划下一批动态。" : "尚未开启。";
  return <section className="settings-section"><div className="section-heading"><h2>世界动态事件池</h2><p>根据已确认的公共世界书背景，每次生成10条动态；首条就绪后发布，其余在有效时段内随机逐条发布，通常间隔15～45分钟世界时间。</p></div>
    <div className="setting-row"><span><strong>{label}</strong><small>{status?.model ? `使用 ${status.model}` : "尚无可用模型"}</small></span><button type="button" className="secondary-button" disabled={busy} onClick={() => void refresh()}>刷新状态</button></div>
    {status && <p>待发布 {status.pending} 条；最近一批已处理 {status.batch_processed}／{status.batch_total} 条。达到8／10时自动补充下一批，旧的未经历动态仍保留。</p>}
    {status?.error && <p role="alert" className="product-error">{errors[status.error] || "事件池暂不可用，请刷新后检查设置。"}</p>}
    <p className="inline-hint">“已经历”和“跳过”由你手动标记，不额外调用模型判断。与聊天额度和角色自动活动分别运行。过期候选不补造历史；任务中断不自动重发。</p>
    <div className="journal-entry-actions"><button type="button" className="primary-button" disabled={busy || !status || !status.enabled && !status.model_available} onClick={() => { if (!status) return; if (!status.enabled && !status.consented) setConsentOpen(true); else void configure(!status.enabled); }}>{status?.enabled ? "关闭事件池" : "开启事件池"}</button>
      {status?.enabled && state !== "generating" && (state === "attention" || status.pending === 0) && <button type="button" className="secondary-button" disabled={busy} onClick={() => void configure(true, false, true)}>生成新一批（调用模型）</button>}
    </div>
    {consentOpen && <div className="consent-panel"><p>授权当前世界使用你配置的模型批量生成公共动态，后台调用会产生费用并遵循现有模型预算。发送逐条公开的世界书标题、正文及已有动态标题；私聊正文、隐藏条目和私人记忆不发送。</p><p>首次生成10条，达到整批80%已处理后自动续批；未处理超过容量时停止。仅程序运行期间生效。</p><button type="button" className="primary-button" disabled={busy} onClick={() => void configure(true, true)}>同意后台用量并开启</button><button type="button" className="text-action" disabled={busy} onClick={() => setConsentOpen(false)}>暂不开启</button></div>}
    {loadError && <p role="alert" className="product-error">{loadError}</p>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
