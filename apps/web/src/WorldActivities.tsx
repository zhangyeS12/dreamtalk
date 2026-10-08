import { useEffect, useRef, useState } from "react";
import { CoreClient, CoreRequestError, type DirectorStatus } from "@dreamtalk/api-client";

import { BackgroundTaskFeedback, taskErrorGuidance, activityGuidance, type BackgroundNavigate } from "./BackgroundTaskFeedback";
import { PublicBackgroundReadiness } from "./PublicBackgroundReadiness";

const errors: Record<string, string> = {
  director_encounters_require_activity: "请先开启世界自动活动，再允许角色相遇。",
  director_encounter_consent_required: "首次允许相遇，需要确认同批后台规划的模型用量。",
  director_player_required: "请先选择你在当前世界的身份。",
  director_model_unavailable: "请先配置可用的聊天模型。",
  director_settings_changed: "设置已变化，请刷新状态后重试。",
  director_consent_required: "首次开启需要确认后台模型用量。",
  director_characters_required: "上一批规划因当时没有已设置初始地点的角色而停止。请先设置至少一名角色的初始地点，再点击“重新规划”；刷新状态不会发起新规划。",
  director_world_capacity: "当前资料超过规划容量（16位角色、32个地点、64 KiB资料），请精简后再规划。",
  director_location_scope_unavailable: "角色没有可进入的活动地点。请在通讯录中核对初始地点与隐藏分支开放范围。",
  director_location_scope_changed: "本批地点或常驻规则已改变，计划未接纳。已开始的模型请求可能产生用量；不会自动重试，可核对后手动重新规划。",
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

export function WorldActivities({ client, worldId, visible, paused, hasInitializedCharacters = null, onNavigate }: {
  client: CoreClient; worldId: string; visible: boolean; paused: boolean; hasInitializedCharacters?: boolean | null; onNavigate?: BackgroundNavigate;
}) {
  const [status, setStatus] = useState<DirectorStatus | null>(null);
  const [locationReady, setLocationReady] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const [operationError, setOperationError] = useState("");
  const [operationCode, setOperationCode] = useState<string | null>(null);
  const requestSerial = useRef(0);
  const busyRef = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; ++requestSerial.current; }; }, []);
  const [consentOpen, setConsentOpen] = useState(false);
  const [encounterConsentOpen, setEncounterConsentOpen] = useState(false);
  const [sharedConsentOpen, setSharedConsentOpen] = useState(false);
  const currentWorld = useRef(worldId);
  currentWorld.current = worldId;
  useEffect(() => {
    setStatus(null); setNotice(""); setLoadError(""); setOperationError(""); setOperationCode(null);
    setConsentOpen(false); setEncounterConsentOpen(false); setSharedConsentOpen(false);
    ++requestSerial.current;
  }, [worldId]);
  useEffect(() => {
    if (!visible) return;
    let alive = true;
    const read = async () => {
      if (busyRef.current) return;
      const serial = ++requestSerial.current;
      try {
        const [next, people] = await Promise.all([client.directorStatus(worldId), client.listActivityCharacters(worldId)]);
        if (alive && serial === requestSerial.current) { setStatus(next); setLocationReady(people.items.some(person => person.initialized)); setLoadError(""); }
      } catch { if (alive && serial === requestSerial.current) setLoadError("未能读取自动活动状态，请检查核心连接。"); }
    };
    void read();
    const timer = window.setInterval(() => void read(), 5000);
    return () => { alive = false; ++requestSerial.current; window.clearInterval(timer); };
  }, [client, worldId, visible]);

  async function configure(enabled: boolean, consent = false, retry = false) {
    if (!status || busyRef.current) return;
    busyRef.current = true;
    ++requestSerial.current;
    setBusy(true); setNotice(""); setOperationError(""); setOperationCode(null);
    try {
      const next = await client.configureDirector(worldId, status, enabled, consent, retry);
      if (!mounted.current || currentWorld.current !== worldId) return;
      setStatus(next); setLoadError("");
      setConsentOpen(false);
      setNotice(enabled ? (retry ? "新的规划已排队；暂停的世界恢复后才开始。" : "开关已保存，请按上方状态查看规划进度；有了有效计划后才执行活动。") : "已关闭后续规划和待执行活动。已经开始的模型请求仍可能产生用量。");
    } catch (error) {
      if (!mounted.current || currentWorld.current !== worldId) return;
      setOperationCode(error instanceof CoreRequestError ? error.code : null);
      setOperationError(error instanceof CoreRequestError && error.code && errors[error.code]
        ? errors[error.code] : "未能更新设置，请读取最新状态后重试。");
    } finally { busyRef.current = false; if (mounted.current) setBusy(false); }
  }

  async function configureEncounters(enabled: boolean, consent = false) {
    if (!status || busyRef.current) return;
    busyRef.current = true; ++requestSerial.current;
    setBusy(true); setNotice(""); setOperationError(""); setOperationCode(null);
    try {
      const next = await client.configureDirectorEncounters(worldId, status, enabled, consent);
      if (!mounted.current || currentWorld.current !== worldId) return;
      setStatus(next); setLoadError(""); setEncounterConsentOpen(false);
      setNotice(enabled ? "已允许角色相遇，下一批日常规划生效；此次保存未额外调用模型。" : "已关闭后续相遇，取消尚未执行的候选；已发生的见闻保留。");
    } catch (error) {
      if (!mounted.current || currentWorld.current !== worldId) return;
      setOperationCode(error instanceof CoreRequestError ? error.code : null);
      setOperationError(error instanceof CoreRequestError && error.code && errors[error.code]
        ? errors[error.code] : "未能保存相遇设置，请刷新状态后重试。");
    } finally { busyRef.current = false; if (mounted.current) setBusy(false); }
  }

  async function configureShared(enabled: boolean, consent = false) {
    if (!status || busyRef.current) return;
    busyRef.current = true; ++requestSerial.current;
    setBusy(true); setNotice(""); setOperationError(""); setOperationCode(null);
    try {
      const next = await client.configureSharedActivities(worldId, status, enabled, consent);
      if (!mounted.current || currentWorld.current !== worldId) return;
      setStatus(next); setLoadError(""); setSharedConsentOpen(false);
      setNotice(enabled ? "已允许共同休闲，下一批日常规划生效；保存不会额外调用模型。" : "已关闭共同休闲，未开始的候选已取消；正在进行的活动会中断，世界暂停时恢复后记录。已有经历保留。");
    } catch (error) {
      if (!mounted.current || currentWorld.current !== worldId) return;
      const code = error instanceof CoreRequestError ? error.code : null;
      setOperationCode(code);
      setOperationError(code === "director_shared_requires_encounters" ? "请先开启世界自动活动和角色相遇。" : code === "director_shared_consent_required" ? "请确认同批后台模型用量后开启。" : code && errors[code] ? errors[code] : "未能确认共同休闲设置，请刷新状态后核对；没有自动重试。");
    } finally { busyRef.current = false; if (mounted.current) setBusy(false); }
  }

  const state = status?.state;
  const reason = status?.error ? errors[status.error] ?? "自动活动暂时无法继续，请刷新核对。" : "";
  const guidance = activityGuidance(status, paused, hasInitializedCharacters ?? locationReady, loadError, reason);
  return <section className="settings-section">
    <div className="section-heading"><h2>世界自动活动</h2><p>角色可以休息、工作或自由活动，并在已有地点之间移动。实际活动可以成为聊天话题。</p></div>
    <BackgroundTaskFeedback name="自动活动" guidance={guidance} onNavigate={onNavigate} disabled={busy} />
    <p className="inline-hint">每批覆盖6小时世界时间，采用当前模型{status?.model ? `「${status.model}」` : ""}，独立于聊天额度，后台规划会产生模型用量。应用关闭后不调用模型。</p>
    <p className="inline-hint">自动活动需要电脑保持开机且程序未退出，最小化或设置为关闭到托盘可继续运行。退出或关机后停止；重开会推进未暂停的世界时间，但目前不会完整补演错过的活动。离线主动消息可在“离线期间的消息”中单独开启。</p>
    <p className="inline-hint">日常规划也会参考你在书架世界管理中公开的背景：条目按来源条件和背景容量参与，关键词匹配角色名和当前地点名。修改在下一批规划时生效。</p>
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
        void client.directorStatus(worldId).then(next => { if (serial === requestSerial.current) { setStatus(next); setLoadError(""); setOperationError(""); setNotice("已读取最新状态，未发起模型调用或重新规划。"); } }).catch(() => { if (serial === requestSerial.current) setLoadError("未能读取状态，请检查核心连接。"); });
      }}>刷新状态</button>
    </div>
    {consentOpen && <div className="editor-panel" role="group" aria-label="授权后台规划">
      <p>开启后授权此世界自动调用当前模型规划活动，无需逐批确认。规划遵循现有模型预算；你可以随时关闭。</p>
      <p className="inline-hint">将已有角色资料与本世界公开背景发送给当前模型服务，安排日常与移动；不发送隐藏条目、私聊或私人记忆，不移动你的玩家身份。</p>
      <button type="button" className="primary-button" disabled={busy} onClick={() => void configure(true, true)}>同意后台模型用量并开启</button>
      <button type="button" disabled={busy} onClick={() => setConsentOpen(false)}>暂不开启</button>
    </div>}
    <div className="editor-panel" role="group" aria-label="角色相遇设置">
      <h3>角色相遇</h3>
      <p>{status?.encounters_enabled ? (status.enabled ? "已允许：双方实际碰面后会记住这段经历。" : "已允许，自动活动关闭期间不执行相遇。") : "尚未开启。允许角色在休息或自由活动时短暂碰面。"}</p>
      <p className="inline-hint">相遇随下一批6小时日常一起规划，不逐次调用 API；只在双方实际处于同一地点且时段有效时记录。不会移动你，不自动改变关系，也不补演错过的碰面。</p>
      <p className="inline-hint">普通相遇与共同休闲合计每批最多两次；每位角色每24小时世界时间最多新增一个见面对象。两人一直在同一地点时不重复记录问候，分开后再碰面才重新考虑；同一对仍有6小时冷却。</p>
      <p className="inline-hint">角色可在聊天中自然提及自己的见闻；短暂问候不会自动变成正式认识或熟悉。你未亲历或尚未从聊天获知的相遇，不会直接出现在世界事件中。</p>
      <button type="button" disabled={!status || busy || (!status.enabled && !status.encounters_enabled)} onClick={() => {
        if (status?.encounters_enabled) void configureEncounters(false);
        else if (status?.encounters_consented) void configureEncounters(true);
        else setEncounterConsentOpen(true);
      }}>{status?.encounters_enabled ? "关闭角色相遇" : "允许角色相遇"}</button>
      {!status?.enabled && <p className="inline-hint">先开启上方世界自动活动，再允许相遇。</p>}
      {encounterConsentOpen && <div role="group" aria-label="授权相遇规划">
        <p>开启后允许现有 Director 在日常批次中安排两名角色短暂碰面，使用已有角色资料、地点和公共背景；同批输出可能增加用量，遵循现有预算，不发送私聊或私人记忆。</p>
        <button type="button" className="primary-button" disabled={busy || !status?.enabled} onClick={() => void configureEncounters(true, true)}>同意同批后台用量并开启</button>
        <button type="button" disabled={busy} onClick={() => setEncounterConsentOpen(false)}>暂不开启</button>
      </div>}
    </div>
    <div className="editor-panel" role="group" aria-label="共同休闲设置">
      <h3>共同休闲</h3>
      <p>{status?.shared_activities_enabled ? status.enabled && status.encounters_enabled ? "已允许：已实际碰面或同属一个阵营的两名角色，可以一起休息或自由活动。" : "已允许，自动活动或角色相遇关闭期间不执行。" : "尚未开启。已实际碰面或同阵营的角色可以积累共同经历。"}</p>
      <p className="inline-hint">随下一批日常一起规划，两人在相同地点、相同休闲类型下共同活动15～30分钟世界时间。每位角色每24小时最多一次，同一对至少间隔6小时；与普通问候合计每批最多两次。</p>
      <p className="inline-hint">真实开始、正常结束或中断都会分别记录，角色聊天可自然提及自己的经历。不会自动改关系、移动你或编造谈话、购物和任务成果；退出后不补造已完成经历。</p>
      <button type="button" disabled={!status || busy || ((!status.enabled || !status.encounters_enabled) && !status.shared_activities_enabled)} onClick={() => {
        if (status?.shared_activities_enabled) void configureShared(false);
        else if (status?.shared_activities_consented) void configureShared(true);
        else setSharedConsentOpen(true);
      }}>{status?.shared_activities_enabled ? "关闭共同休闲" : "允许共同休闲"}</button>
      {(!status?.enabled || !status.encounters_enabled) && <p className="inline-hint">先开启世界自动活动和角色相遇；同阵营直接成员无需先完成实际碰面。</p>}
      {sharedConsentOpen && <div role="group" aria-label="授权共同休闲规划"><p>允许现有 Director 在同一日常批次安排共同休闲；只使用已有角色资料、地点和公共背景，同批输出可能增加用量。不会逐活动调用API，不发送私聊、私人记忆或新增的相遇历史。</p>
        <button type="button" className="primary-button" disabled={busy || !status?.enabled || !status.encounters_enabled} onClick={() => void configureShared(true, true)}>同意同批后台用量并开启</button>
        <button type="button" disabled={busy} onClick={() => setSharedConsentOpen(false)}>暂不开启</button>
      </div>}
    </div>
    <PublicBackgroundReadiness client={client} worldId={worldId} visible={visible} disabled={busy} onManage={onNavigate ? () => onNavigate("lore") : undefined} />
    {loadError && <p role="alert">{loadError}</p>}
    {operationError && <BackgroundTaskFeedback name="更新自动活动" guidance={taskErrorGuidance(operationCode, operationError, "本次设置未能确认")} onNavigate={onNavigate} disabled={busy} />}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
