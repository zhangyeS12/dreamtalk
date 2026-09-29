import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type OfflineContactStatus } from "@dreamtalk/api-client";
const errors: Record<string, string> = {
  offline_model_unavailable: "当前模型不可用，请检查模型设置。",
  offline_player_required: "请先选择此世界中的玩家身份。",
  offline_settings_changed: "设置已发生变化，请读取最新状态后重试。",
  offline_input_unavailable: "角色资料暂不可用。请先打开角色私聊，或检查资料容量。",
  offline_input_capacity: "角色资料超过当前容量，请减少参与角色或精简资料。",
  offline_interrupted: "上次任务被中断，系统不会自动重试这次恢复。",
  offline_generation_failed: "本次生成未完成，可能已产生费用，系统不会自动重试。",
  offline_plan_invalid: "本次联系计划未通过校验，已停止。",
  offline_dialogue_invalid: "本次角色消息未通过校验，已停止。",
  offline_context_changed: "身份、资料、玩家状态或新消息已变化，本次联系已取消。",
  offline_clock_regression: "系统时间向后调整，等待时间恢复后再判断离线时长。",
};
export function OfflineContactSettings({ client, worldId, status, onUpdated }: {
  client: CoreClient; worldId: string; status: OfflineContactStatus | null; onUpdated: (status: OfflineContactStatus) => void;
}) {
  const [hours, setHours] = useState("6");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [consentOpen, setConsentOpen] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => { if (status) setHours(String(status.hours)); }, [status?.hours]);
  const valid = Number.isInteger(Number(hours)) && Number(hours) >= 1 && Number(hours) <= 168;
  async function save(enabled: boolean, consent = false) {
    if (!status || lock.current || (enabled && !valid)) return;
    lock.current = true; setBusy(true); setNotice("");
    try {
      const next = await client.configureOfflineContact(worldId, status, enabled, valid ? Number(hours) : status.hours, consent);
      if (!mounted.current) return;
      onUpdated(next);
      setConsentOpen(false); setNotice(enabled ? "已开启，先记录在线基线；下次离线恢复时再判断是否联系。" : "已关闭后续离线联系。已发出的模型请求仍可能产生费用。");
    } catch (error) { setNotice(error instanceof CoreRequestError && error.code ? errors[error.code] ?? "未能保存，请刷新状态后重试。" : "未能连接核心，请稍后重试。"); }
    finally { lock.current = false; setBusy(false); }
  }
  const labels: Record<OfflineContactStatus["state"], string> = {
    off: "尚未开启。", idle: "已开启，等待下一次离线恢复。", waiting: "本次恢复已记录，正在等待模型就绪。",
    planning: "正在选择合适的联系角色和时段……", writing: "角色正在写消息……",
    delivered: "本次离线消息已送达。", skipped: "本次恢复没有发起联系。", attention: "本次任务已停止，需要查看原因。",
  };
  return <section className="settings-section">
    <div className="section-heading"><h2>离线期间的消息</h2><p>回来时，可能收到角色在离线期间留下的一条问候或邀请。</p></div>
    <p role="status">{status ? labels[status.state] : "正在读取设置……"}</p>
    <p className="inline-hint">仅在一个指定世界开启；此处开启会替换此前的目标世界。首次启用不会立刻生成。电脑开机或手动重开都适用，后台自启动是可选的。</p>
    <div className="setting-row"><label className="field"><span>离线多久后考虑联系（真实小时）</span><input type="number" min="1" max="168" step="1" value={hours} disabled={busy} onChange={e => setHours(e.target.value)} /></label>
      <button type="button" disabled={!status || busy || !valid || !status.model_available && !status.enabled} onClick={() => {
        if (status?.enabled) void save(false);
        else if (status?.consented) void save(true);
        else setConsentOpen(true);
      }}>{status?.enabled ? "关闭离线联系" : "开启离线联系"}</button>
      {status?.enabled && <button type="button" disabled={busy || !valid || Number(hours) === status.hours} onClick={() => void save(true)}>保存时长</button>}
    </div>
    {!valid && <p role="alert">请输入1至168之间的整数小时。</p>}
    <p className="inline-hint">一次恢复最多一条，Busy或世界暂停时跳过；同一理由不会重复，未回复上条主动消息时不会继续催促。时长与聊天额度、自动活动的世界时间分别设置。</p>
    {status?.error && errors[status.error] && <p className="error-banner" role="alert">{errors[status.error]}</p>}
    {consentOpen && <div className="editor-panel" role="group" aria-label="授权离线联系">
      <p>授权此世界恢复后使用当前模型选择角色并生成消息，后台调用会产生费用，遵循已有模型预算。</p>
      <p className="inline-hint">发送已确认角色资料、公共世界书背景和已有活动计划；私聊正文、隐藏条目和私人记忆不参与。消息显示离线区间内的剧情时间，“时间详情”保留真实生成时间。</p>
      <button type="button" className="primary-button" disabled={busy} onClick={() => void save(true, true)}>同意后台模型用量并开启</button>
      <button type="button" disabled={busy} onClick={() => setConsentOpen(false)}>暂不开启</button>
    </div>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
