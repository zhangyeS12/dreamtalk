import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type DirectorStatus } from "@dreamtalk/api-client";

const errors: Record<string, string> = {
  director_player_required: "请先选择你在当前世界的身份。",
  director_model_unavailable: "请先配置可用的聊天模型。",
  director_settings_changed: "设置已变化，请刷新状态后重试。",
  director_consent_required: "首次开启需要确认后台模型用量。",
  director_characters_required: "上一批规划因当时没有已设置初始地点的角色而停止。请先设置至少一名角色的初始地点，再点击“重新规划”；刷新状态不会发起新规划。",
  director_world_capacity: "当前资料超过规划容量（16位角色、32个地点、64 KiB资料），请精简后再规划。",
  director_background_capacity: "公共背景超过规划读取容量（512条启用条目，每条关键词和条件16 KiB），请精简公开范围或触发条件后再规划。",
  director_background_invalid: "公共背景资料格式异常，暂时不能规划，请检查或重新确认世界书。",
  director_background_changed: "本批采用的公共背景已隐藏或更新，计划未接纳，已开始的请求可能产生用量。不会自动重试；重新规划是新的模型任务。",
  director_plan_invalid: "模型未给出有效的活动计划。不会自动重试；重新规划会产生新的模型用量。",
  director_character_mapping_invalid: "当前角色资料关联不完整，暂时不能规划。",
  director_model_failed: "本批规划未完成。可能已产生模型用量；系统不会自动重试。",
  director_interrupted: "上次规划中断，系统没有重复调用模型。你可以显式开始新的规划。",
  director_execution_failed: "活动执行遇到问题，自动运行已停在待处理状态。",
  director_retry_unavailable: "当前无需重新规划，请刷新状态。",
};

export function WorldActivities({ client, worldId, visible, paused, hasInitializedCharacters = null }: {
  client: CoreClient; worldId: string; visible: boolean; paused: boolean; hasInitializedCharacters?: boolean | null;
}) {
  const [status, setStatus] = useState<DirectorStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const requestSerial = useRef(0);
  const busyRef = useRef(false);
  const [consentOpen, setConsentOpen] = useState(false);
  useEffect(() => {
    if (!visible) return;
    let alive = true;
    const read = async () => {
      if (busyRef.current) return;
      const serial = ++requestSerial.current;
      try {
        const next = await client.directorStatus(worldId);
        if (alive && serial === requestSerial.current) { setStatus(next); setLoadError(""); }
      } catch { if (alive && serial === requestSerial.current) setLoadError("未能读取自动活动状态，请检查核心连接。"); }
    };
    void read();
    const timer = window.setInterval(() => void read(), 5000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [client, worldId, visible]);

  async function configure(enabled: boolean, consent = false, retry = false) {
    if (!status || busy) return;
    busyRef.current = true;
    ++requestSerial.current;
    setBusy(true); setNotice("");
    try {
      setStatus(await client.configureDirector(worldId, status, enabled, consent, retry));
      setConsentOpen(false);
      setNotice(enabled ? (retry ? "新的规划已排队；暂停的世界恢复后才开始。" : "已开启，角色将根据计划活动。") : "已关闭后续规划和待执行活动。已经开始的模型请求仍可能产生用量。");
    } catch (error) {
      setNotice(error instanceof CoreRequestError && error.code && errors[error.code]
        ? errors[error.code] : "未能更新设置，请读取最新状态后重试。");
    } finally { busyRef.current = false; setBusy(false); }
  }

  const state = status?.state;
  const charactersNowReady = status?.error === "director_characters_required" && hasInitializedCharacters === true;
  const label = paused && status?.enabled ? "世界已暂停，活动与后续规划等待恢复。"
    : state === "ready" ? "活动计划已就绪；已经发生且获知的活动可在世界事件中查看。"
    : state === "planning" ? "正在规划下一批活动……"
    : state === "attention" ? charactersNowReady ? "角色初始地点已确认，上一批规划仍待重新开始。" : "上一批自动活动已停止，需要处理。"
    : state === "idle" ? "已开启，正在等待规划。" : "尚未开启。";
  return <section className="settings-section">
    <div className="section-heading"><h2>世界自动活动</h2><p>角色可以休息、工作或自由活动，并在已有地点之间移动。实际活动可以成为聊天话题。</p></div>
    <p role="status">{label}</p>
    <p className="inline-hint">每批覆盖6小时世界时间，采用当前模型{status?.model ? `「${status.model}」` : ""}，独立于聊天额度，后台规划会产生模型用量。应用关闭后不调用模型。</p>
    <p className="inline-hint">自动活动需要电脑保持开机且程序未退出，最小化或设置为关闭到托盘可继续运行。退出或关机后停止；重开会推进未暂停的世界时间，但目前不会完整补演错过的活动。离线主动消息可在“离线期间的消息”中单独开启。</p>
    <p className="inline-hint">日常规划也会参考你在“角色卡与世界书”中公开的背景：条目按来源条件和背景容量参与，关键词匹配角色名和当前地点名。修改在下一批规划时生效。</p>
    {status?.error && <p className={charactersNowReady ? "app-notice" : "error-banner"} role={charactersNowReady ? "status" : "alert"}>{charactersNowReady ? "至少一名角色已设置初始地点，无需重复设置。点击下方“重新规划”开始新的一批（会调用模型）；刷新只核对状态，不会自动重试。" : errors[status.error] ?? "自动活动暂时无法继续，请查看模型设置或重新读取状态。"}</p>}
    <div className="setting-row">
      <button type="button" disabled={!status || busy} onClick={() => {
        if (status?.enabled) void configure(false);
        else if (status?.consented) void configure(true);
        else setConsentOpen(true);
      }}>{busy ? "保存中……" : status?.enabled ? "关闭自动活动" : "开启自动活动"}</button>
      {status?.enabled && state === "attention" && <button type="button" className="primary-button" disabled={busy} onClick={() => {
        if (window.confirm("重新规划将发起一个新的模型任务，可能产生费用。是否继续？")) void configure(true, false, true);
      }}>重新规划（调用模型）</button>}
      <button type="button" disabled={busy} onClick={() => {
        const serial = ++requestSerial.current;
        void client.directorStatus(worldId).then(next => { if (serial === requestSerial.current) { setStatus(next); setLoadError(""); } }).catch(() => { if (serial === requestSerial.current) setLoadError("未能读取状态，请检查核心连接。"); });
      }}>刷新状态</button>
    </div>
    {consentOpen && <div className="editor-panel" role="group" aria-label="授权后台规划">
      <p>开启后授权此世界自动调用当前模型规划活动，无需逐批确认。规划遵循现有模型预算；你可以随时关闭。</p>
      <p className="inline-hint">将已有角色资料与本世界公开背景发送给当前模型服务，安排日常与移动；不发送隐藏条目、私聊或私人记忆，不移动你的玩家身份。</p>
      <button type="button" className="primary-button" disabled={busy} onClick={() => void configure(true, true)}>同意后台模型用量并开启</button>
      <button type="button" disabled={busy} onClick={() => setConsentOpen(false)}>暂不开启</button>
    </div>}
    {loadError && <p role="alert">{loadError}</p>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
