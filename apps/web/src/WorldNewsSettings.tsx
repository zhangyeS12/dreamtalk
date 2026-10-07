import { useCallback, useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type WorldNewsStatus } from "@dreamtalk/api-client";

import { BackgroundTaskFeedback, taskErrorGuidance, newsGuidance, type BackgroundNavigate } from "./BackgroundTaskFeedback";
import { PublicBackgroundReadiness } from "./PublicBackgroundReadiness";

const errors: Record<string, string> = {
  news_background_required: "尚无可用于生成动态的公共背景，本次未调用模型。请返回书架，在“管理 / 导入世界书”中确认世界书并逐条设为“公共背景”。若关键词未命中，可编辑一个适合公开的条目，将“提供条件”改为“常驻背景”，预览确认后重新设为公共背景，再生成。",
  news_background_invalid: "公共背景格式异常，请检查世界书。",
  news_background_capacity: "公共背景超过资料容量，请精简公开范围。",
  news_background_changed: "本批采用的背景已隐藏或更新，待发布内容已停止；可显式生成新的一批。",
  news_plan_invalid: "模型已返回内容，但动态的条数、字段或取值不符合要求，本批未保存。无需反复修改公共背景；可显式生成新一批，会产生新用量。",
  news_output_empty: "模型没有返回动态正文，本批未保存，可能已产生用量。不会自动重试。",
  news_output_limit: "动态输出被截断，本批未保存。可提高模型回复长度或使用更简短的背景，再显式生成新一批。",
  news_token_bound_unavailable: "尚不能确认本次生成的模型输入上界，未发出模型请求。请核对模型与路由设置。",
  news_context_limit: "资料超过模型可接受的上下文范围，请精简公共背景后显式重试。",
  news_model_timeout: "模型请求超时，本次结果未确认，可能已产生用量。不会自动重发；请检查网络后再决定是否生成新批次。",
  news_model_rate_limited: "模型服务暂时限流，本批未完成。请稍后显式重试，刷新不会重发请求。",
  news_model_quota: "模型服务额度不足，本批未完成。请核对服务余额或额度后显式重试。",
  news_model_refused: "模型没有接受本次动态生成任务，本批未保存。请调整公开背景或模型后显式重试。",
  news_generation_failed: "本批生成未完成，现有记录未能区分具体原因，可能已产生用量。请查看连接与诊断；不会自动重试。",
  news_interrupted: "上次任务中断或资料已变化，没有自动重发模型请求。",
  news_execution_failed: "事件处理停止，请刷新状态；重新生成是新的模型任务。",
  news_pending_capacity: "未处理事件接近100条上限，请先标记已经历或跳过，再生成。",
  news_model_unavailable: "请先配置可用模型，优先使用 DeepSeek。",
  news_settings_changed: "设置已变化，请刷新状态后重试。",
  news_pool_not_empty: "池内仍有待发布事件，暂不生成新批次。",
};

export function WorldNewsSettings({ client, worldId, visible, paused, onNavigate }: { client: CoreClient; worldId: string; visible: boolean; paused: boolean; onNavigate?: BackgroundNavigate }) {
  const [status, setStatus] = useState<WorldNewsStatus | null>(null);
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const [operationError, setOperationError] = useState("");
  const [operationCode, setOperationCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [consentOpen, setConsentOpen] = useState(false);
  const busyRef = useRef(false);
  const serial = useRef(0);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; ++serial.current; }; }, []);
  const refresh = useCallback(async () => {
    if (busyRef.current) return null;
    const request = ++serial.current;
    try {
      const next = await client.worldNewsStatus(worldId);
      if (alive.current && request === serial.current) { setStatus(next); setLoadError(""); return true; }
      return null;
    } catch { if (alive.current && request === serial.current) { setLoadError("未能读取状态，请检查核心连接后刷新。"); return false; } return null; }
  }, [client, worldId]);
  useEffect(() => {
    if (!visible) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { ++serial.current; window.clearInterval(timer); };
  }, [visible, refresh]);

  async function configure(enabled: boolean, consent = false, replenish = false) {
    if (!status || busyRef.current) return;
    busyRef.current = true; ++serial.current; setBusy(true); setNotice(""); setOperationError(""); setOperationCode(null);
    try {
      const next = await client.configureWorldNews(worldId, status, enabled, consent, replenish);
      if (alive.current) { setStatus(next); setLoadError(""); setConsentOpen(false); setNotice(!enabled ? "已关闭后续发布与续批；已开始的请求仍可能产生用量。" : paused ? "已保存，世界暂停期间不会开始生成；恢复后处理。" : next.state === "idle" ? "背景条件已核对，等待后台开始生成。" : "设置已保存，请按当前事件池状态查看进度。"); }
    } catch (error) {
      if (alive.current) { setOperationCode(error instanceof CoreRequestError ? error.code : null); setOperationError(error instanceof CoreRequestError && error.code && errors[error.code] ? errors[error.code] : "未能保存，请刷新状态后重试；未自动重试模型请求。"); }
    } finally { busyRef.current = false; if (alive.current) setBusy(false); }
  }
  const state = status?.state;
  const guidance = newsGuidance(status, paused, loadError, status?.error ? errors[status.error] ?? "事件池暂不可用，请刷新后检查设置。" : "");
  return <section className="settings-section"><div className="section-heading"><h2>世界动态事件池</h2><p>根据已确认的公共世界书背景，每次生成10条动态。按可发布时间先后补入，最多5条进行中；标绿或标灰后补位，标红继续占位，其余保留在储备中。</p></div>
    <div className="setting-row"><span><strong>当前生成模型</strong><small>{status?.model ? `使用 ${status.model}` : status ? "尚未配置模型" : "正在核对模型…"}</small></span><button type="button" className="secondary-button" disabled={busy} onClick={() => { void refresh().then(ok => { if (ok === true && alive.current) { setOperationError(""); setNotice("已读取最新状态，未生成动态或重新提交设置。"); } }); }}>刷新状态</button></div>
    <BackgroundTaskFeedback name="世界动态" guidance={guidance} onNavigate={onNavigate} disabled={busy} />
    {status && <p>待发布 {status.pending} 条；最近一批已处理 {status.batch_processed}／{status.batch_total} 条。达到8／10时自动补充下一批，旧的未经历动态仍保留。</p>}
    <p className="inline-hint">“已经历”和“跳过”由你手动标记，不额外调用模型判断。与聊天额度和角色自动活动分别运行。过期候选不补造历史；任务中断不自动重发。</p>
    <div className="journal-entry-actions"><button type="button" className="primary-button" disabled={busy || !status || !status.enabled && !status.model_available} onClick={() => { if (!status) return; if (!status.enabled && !status.consented) setConsentOpen(true); else void configure(!status.enabled); }}>{status?.enabled ? "关闭事件池" : "开启事件池"}</button>
      {status?.enabled && state !== "generating" && (state === "attention" || status.pending === 0) && <button type="button" className="secondary-button" disabled={busy} onClick={() => void configure(true, false, true)}>生成新一批（调用模型）</button>}
    </div>
    {consentOpen && <div className="consent-panel"><p>授权当前世界使用你配置的模型批量生成公共动态，后台调用会产生费用并遵循现有模型预算。发送逐条公开的世界书标题、正文及已有动态标题；私聊正文、隐藏条目和私人记忆不发送。</p><p>首次生成10条，达到整批80%已处理后自动续批；未处理超过容量时停止。仅程序运行期间生效。</p><button type="button" className="primary-button" disabled={busy} onClick={() => void configure(true, true)}>同意后台用量并开启</button><button type="button" className="text-action" disabled={busy} onClick={() => setConsentOpen(false)}>暂不开启</button></div>}
    <PublicBackgroundReadiness client={client} worldId={worldId} visible={visible} disabled={busy} onManage={onNavigate ? () => onNavigate("lore") : undefined} />
    {operationError && <BackgroundTaskFeedback name="更新事件池" guidance={taskErrorGuidance(operationCode, operationError, "本次设置未能确认")} onNavigate={onNavigate} disabled={busy} />}
    {loadError && <p role="alert" className="product-error">{loadError}</p>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
