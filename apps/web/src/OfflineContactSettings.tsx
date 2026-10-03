import { useEffect, useRef, useState } from "react";
import { CoreRequestError, type OfflineContactStatus, type PlayerAvailability } from "@dreamtalk/api-client";
import { offlineContactErrorMessage } from "./useOfflineContact";
import { BackgroundTaskFeedback, offlineGuidance, type BackgroundNavigate } from "./BackgroundTaskFeedback";

export function OfflineContactSettings({ status, busy, refreshing, error, onRefresh, onSave, paused = false, availability = null, onNavigate }: {
  paused?: boolean; availability?: PlayerAvailability | null; onNavigate?: BackgroundNavigate;
  status: OfflineContactStatus | null; busy: boolean; refreshing: boolean; error: string;
  onRefresh: () => Promise<boolean | null>;
  onSave: (enabled: boolean, hours: number, consent: boolean) => Promise<boolean>;
}) {
  const [hours, setHours] = useState("6");
  const lock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [consentOpen, setConsentOpen] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => { if (status) setHours(String(status.hours)); }, [status?.hours]);
  const valid = Number.isInteger(Number(hours)) && Number(hours) >= 1 && Number(hours) <= 168;
  async function save(enabled: boolean, consent = false) {
    if (!status || lock.current || refreshing || (enabled && !valid)) return;
    lock.current = true; setNotice("");
    try {
      if (await onSave(enabled, valid ? Number(hours) : status.hours, consent) && mounted.current) {
        setConsentOpen(false);
        setNotice(enabled ? "已开启，先记录在线基线；下次离线恢复时再判断是否联系。" : "已关闭后续离线联系。已发出的模型请求仍可能产生费用。");
      }
    } finally { lock.current = false; }
  }
  async function refresh() {
    if (lock.current) return;
    lock.current = true; setNotice("");
    try { if (await onRefresh() === true && mounted.current) setNotice("已读取最新状态；刷新不会调用模型，也不会重新提交设置。"); }
    finally { lock.current = false; }
  }
  const guidance = offlineGuidance(status, paused, availability, error, status?.error ? offlineContactErrorMessage(new CoreRequestError(409, status.error)) : "");
  return <section className="settings-section">
    <div className="section-heading"><h2>离线期间的消息</h2><p>回来时，可能收到角色在离线期间留下的一条问候或邀请。</p></div>
    <BackgroundTaskFeedback name="离线联系" guidance={guidance} onNavigate={onNavigate} disabled={busy || refreshing} />
    <p className="inline-hint">仅在一个指定世界开启；此处开启会替换此前的目标世界。首次启用不会立刻生成。电脑开机或手动重开都适用，后台自启动是可选的。</p>
    <div className="setting-row"><label className="field"><span>离线多久后考虑联系（真实小时）</span><input type="number" min="1" max="168" step="1" value={hours} disabled={busy || refreshing} onChange={e => setHours(e.target.value)} /></label>
      <button type="button" disabled={!status || busy || refreshing || !valid || !status.model_available && !status.enabled} onClick={() => {
        if (status?.enabled) void save(false);
        else if (status?.consented) void save(true);
        else setConsentOpen(true);
      }}>{busy ? "保存中……" : status?.enabled ? "关闭离线联系" : "开启离线联系"}</button>
      {status?.enabled && <button type="button" disabled={busy || refreshing || !valid || Number(hours) === status.hours} onClick={() => void save(true)}>保存时长</button>}
      <button type="button" disabled={busy || refreshing} onClick={() => void refresh()}>{refreshing ? "读取中……" : "刷新状态"}</button>
    </div>
    {!valid && <p role="alert">请输入1至168之间的整数小时。</p>}
    <p className="inline-hint">一次恢复最多一条，Busy或世界暂停时跳过；同一理由不会重复，未回复上条主动消息时不会继续催促。时长与聊天额度、自动活动的世界时间分别设置。</p>
    {status?.last_online_at && <p className="inline-hint">最近在线基线：{new Date(status.last_online_at).toLocaleString("zh-CN")}。运行期间持续更新，不是下一条消息的预约时间。</p>}
    {error && <p className="error-banner" role="alert">{error}</p>}
    {consentOpen && <div className="editor-panel" role="group" aria-label="授权离线联系">
      <p>授权此世界恢复后使用当前模型选择角色并生成消息，后台调用会产生费用，遵循已有模型预算。</p>
      <p className="inline-hint">发送已确认角色资料、公共世界书背景和已有活动计划；私聊正文、隐藏条目和私人记忆不参与。消息显示离线区间内的剧情时间，“时间详情”保留真实生成时间。</p>
      <button type="button" className="primary-button" disabled={busy || refreshing} onClick={() => void save(true, true)}>同意后台模型用量并开启</button>
      <button type="button" disabled={busy || refreshing} onClick={() => setConsentOpen(false)}>暂不开启</button>
    </div>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
