import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { CoreClient, CoreRequestError, type ChatMessage, type SpeechJob, type SpeechStatus } from "@dreamtalk/api-client";
import "./speech.css";

const errors: Record<string, string> = {
  speech_disabled: "配音已关闭。", speech_voice_unbound: "这位角色尚未绑定音色，请在通讯录的角色资料中设置。",
  speech_service_unavailable: "配音服务或密钥暂不可用，请核对服务设置。",
  speech_busy: "仍有配音正在生成，请等它结束后再操作。",
  speech_daily_limit: "已达到今天的配音次数上限。文字聊天仍可继续。",
  speech_text_too_long: "这条台词超过设置中的配音字数上限，已保留完整文字。",
  speech_no_dialogue: "这条消息没有需要朗读的台词。",
  speech_local_unavailable: "无法连接本地配音服务，请先启动服务，并核对设置中的地址。",
  speech_local_key_required: "本地配音访问密钥不正确，请复制当前服务的密钥并重新保存。",
  speech_key_required: "请先在配音设置中保存服务密钥。",
  speech_outcome_unknown: "服务未返回可核实的配音结果；无法确认完成，不会自动重新生成。",
  speech_interrupted: "配音任务因程序退出而中断，当前没有可播放的已保存结果；不会自动重新生成。",
  speech_status_lost: "配音服务连接中断，无法继续读取任务状态；没有重新提交生成请求。",
  speech_timeout: "配音超过 16 分钟的等待上限，已停止等待；不会自动重新生成。",
  speech_audio_download_failed: "声音已生成，但读取音频失败；没有重新生成。",
  speech_hf_free_account_required: "免费路线只接受已核实的免费 Hugging Face 个人账户，或不填密钥使用匿名额度。",
  speech_hf_api_changed: "官方演示接口已变化，当前适配停止调用，请使用其他路线。",
  speech_hf_quota_or_generation: "官方演示暂时无法生成，可能额度用尽或排队失败；没有切换到付费服务。",
  speech_balance_insufficient: "云服务可用积分不足。", speech_price_unavailable: "未能确认云服务计价，配音未开始。",
  speech_provider_rejected: "配音服务拒绝了请求，请核对额度、密钥和服务状态。",
  speech_provider_protocol: "配音服务返回了无法确认的结果，不会自动重试。",
  speech_generation_failed: "配音生成失败，文字回复已保留。",
  speech_audio_incomplete: "本地模型生成的声音没有完整结束，已停止保存和播放；文字回复完整保留，没有自动重新生成。",
  speech_sentence_capacity: "台词中的发音标记或单段内容超出模型实际容量，无法完整生成；文字回复已保留。",
  speech_local_bridge_outdated: "配音服务需要更新。请到“设置 → 角色配音”点击“一键修复本地配音”；本次没有提交生成任务。",
  speech_local_repairing: "本地配音正在修复，请稍后再播放；没有提交生成任务。",
  speech_cache_expired: "这条声音缓存已过期或被清理。再次点击“播放配音”会重新生成。",
  speech_request_conflict: "这次配音请求与原记录不一致，请重新选择消息。",
  speech_review_pending: "这条消息已有新配音等待处理，请在消息下方试听并选择是否替换。",
  speech_review_not_ready: "新配音尚未完成或已过期，原配音没有被替换。",
  speech_review_conflict: "配音记录已变化，请重新读取后再选择；原配音没有被覆盖。",
  speech_preview_required: "请先播放完新配音，再选择是否替换。",
  speech_cache_full: "配音缓存空间不足，新声音未保存，待确认配音的原声音已保留。",
  voice_audio_format: "请选择 WAV、MP3 或 .voicecard 音色卡。",
  voice_audio_invalid: "音频无法读取，请换一段清晰的 WAV 或 MP3。",
  voice_reference_duration: "参考音频需为 0.5～15 秒，建议使用 5～10 秒清晰人声。",
  voice_audio_size_limit: "参考音频最大 10 MB；生成声音也有容量限制。",
  voice_card_invalid: "音色卡格式不正确，需包含 manifest.json 和一份 WAV／MP3 参考音频。",
  speech_edit_conflict: "设置已变化，请重新读取后保存。",
  speech_remote_consent_required: "使用远程服务前，请确认发送台词与参考音频。",
  speech_paid_consent_required: "使用付费服务前，请保存密钥并确认配音费用。",
  speech_asset_host_untrusted: "服务返回了未获支持的音频存储地址，已停止传输。",
};
export function speechFailure(error: unknown): string {
  if (error instanceof CoreRequestError && error.code) return errors[error.code] ?? "配音操作未能完成，请核对设置。";
  return "配音操作未能确认，请核对服务设置；文字回复会保留。";
}
export function speechJobFailure(code: string | null, retryAction = "播放配音"): string {
  return (errors[code ?? ""] ?? "配音未完成，文字回复已保留。").replaceAll("播放配音", retryAction);
}
function speechRetryHint(code: string | null, action: string): string {
  return code === "speech_local_bridge_outdated" || code === "speech_local_repairing" ? "" : ` 点击“${action}”可发起一次新的尝试。`;
}

function playbackFailure(code: string): string {
  const failures: Record<string, string> = {
    audio_playback_policy_blocked: "声音已保存，但当前版本的播放权限阻止了声音。请打开修正版后点击消息旁的“播放配音”重播。",
    audio_playback_blocked: "声音已保存，但自动播放被拦截。请保持窗口在前台，点击消息旁的“播放配音”重播。",
    audio_playback_decode_failed: "声音已保存，但播放器无法解码这份音频；没有重新生成。",
    audio_playback_timeout: "声音已保存，但播放器加载或缓冲超时。点击消息旁的“播放配音”重播，不会重复生成。",
  };
  return failures[code] ?? "声音已生成，但播放器未能开始或继续播放。点击消息旁的“播放配音”读取已保存声音，不会重复生成。";
}

const phases: Record<string, string> = {
  connecting: "正在连接配音服务", accepted: "本地服务已接收任务",
  loading_model: "正在加载本地模型，首次使用需要较长时间", preparing_text: "正在处理台词",
  synthesizing: "本地模型正在合成声音", saving_audio: "正在保存声音",
  downloading_audio: "声音已生成，正在读取音频", validating_audio: "正在核对音频",
  waiting_remote: "任务处理中，远程服务尚未返回完成结果",
};
function waitForStatus(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const aborted = () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", aborted); resolve(); }, 1000);
    if (signal.aborted) aborted(); else signal.addEventListener("abort", aborted, { once: true });
  });
}

function generationFeedback(job: SpeechJob): string {
  const segment = job.segment && job.segments ? ` · 第 ${job.segment}/${job.segments} 段` : "";
  const slow = job.phase_seconds >= 120 ? " · 此阶段耗时较长，服务仍可响应状态查询" : "";
  return `${phases[job.phase] ?? "正在查询配音任务状态"}${segment} · 已等待 ${job.elapsed_seconds} 秒${slow}`;
}
type Item = { conversation: string; message: string; requestId?: string; mode?: "regenerate" | "preview"; jobId?: string };
function previewEntries(current: Record<string, SpeechJob>, message: string, job: SpeechJob): Record<string, SpeechJob> {
  const next = { ...current };
  delete next[message];
  if (job.review_state === "pending") next[message] = job;
  return Object.fromEntries(Object.entries(next).slice(-256));
}
type SpeechContextValue = {
  status: SpeechStatus | null; feedback: string; playing: string | null; busy: boolean;
  playbackMode: Item["mode"]; previews: Record<string, SpeechJob>; reviewFeedback: Record<string, string>; deciding: string | null;
  refresh: () => Promise<void>; stop: () => void; play: (conversation: string, message: string) => void;
  regenerate: (conversation: string, message: string) => void;
  preview: (conversation: string, message: string, jobId: string) => void;
  loadPreviews: (conversation: string, messages: string[], signal?: AbortSignal) => Promise<void>;
  followPreview: (message: string, job: string, signal: AbortSignal) => Promise<void>;
  decide: (message: string, job: string, decision: "replace" | "keep") => Promise<void>;
  committed: (conversation: string, message: ChatMessage) => void;
};
const SpeechContext = createContext<SpeechContextValue | null>(null);
export function useSpeech() { return useContext(SpeechContext); }

export function SpeechProvider({ client, worldId, children }: { client: CoreClient; worldId: string; children: ReactNode }) {
  const [status, setStatus] = useState<SpeechStatus | null>(null);
  const [feedback, setFeedback] = useState("");
  const [playing, setPlaying] = useState<string | null>(null), [busy, setBusy] = useState(false);
  const [playbackMode, setPlaybackMode] = useState<Item["mode"]>();
  const [previews, setPreviews] = useState<Record<string, SpeechJob>>({});
  const [reviewFeedback, setReviewFeedback] = useState<Record<string, string>>({});
  const [deciding, setDeciding] = useState<string | null>(null);
  const reviewVersion = useRef(0), decisionPending = useRef(false);
  const settings = useRef<SpeechStatus | null>(null), queue = useRef<Item[]>([]);
  const worker = useRef(false), epoch = useRef(0), mounted = useRef(false);
  const seen = useRef(new Set<string>());
  const audio = useRef<HTMLAudioElement | null>(null), url = useRef<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const release = useCallback(() => {
    audio.current?.pause();
    if (audio.current) { audio.current.src = ""; audio.current.load(); }
    audio.current = null;
    if (url.current) URL.revokeObjectURL(url.current);
    url.current = null;
  }, []);
  const stop = useCallback(() => {
    epoch.current++; queue.current = []; controller.current?.abort(); release();
    if (mounted.current) { setPlaying(null); setPlaybackMode(undefined); setBusy(false); setFeedback(""); }
  }, [release]);
  const refresh = useCallback(async () => {
    const next = await client.speechSettings(worldId);
    if (!mounted.current) return;
    settings.current = next; setStatus(next);
    if (!next.settings.enabled) stop();
  }, [client, worldId, stop]);
  useEffect(() => {
    mounted.current = true;
    void refresh().catch(() => { if (mounted.current) setFeedback("未能读取配音设置，自动配音暂未开启。"); });
    const hidden = () => { if (document.hidden) stop(); };
    const blur = () => stop();
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("blur", blur);
    return () => { mounted.current = false; stop(); document.removeEventListener("visibilitychange", hidden); window.removeEventListener("blur", blur); };
  }, [refresh, stop]);

  const rememberPreview = useCallback((message: string, job: SpeechJob) => {
    reviewVersion.current++;
    if (mounted.current) setPreviews(current => previewEntries(current, message, job));
  }, []);
  const loadPreviews = useCallback(async (conversation: string, messages: string[], signal?: AbortSignal) => {
    const version = reviewVersion.current;
    for (let offset = 0; offset < messages.length; offset += 128) {
      let page;
      try { page = await client.speechPreviews(worldId, conversation, messages.slice(offset, offset + 128), signal); }
      catch (failure) {
        if (!signal?.aborted && mounted.current) setFeedback("未能读取待确认配音，请刷新会话记录后重试；没有提交新生成任务。");
        throw failure;
      }
      if (!mounted.current || signal?.aborted || version !== reviewVersion.current) return;
      setPreviews(current => {
        const next = { ...current };
        for (const job of page.items) { delete next[job.message_id]; next[job.message_id] = job; }
        return Object.fromEntries(Object.entries(next).slice(-256));
      });
    }
  }, [client, worldId]);
  const followPreview = useCallback(async (message: string, jobId: string, signal: AbortSignal) => {
    try {
      let job: SpeechJob;
      do {
        await waitForStatus(signal);
        job = await client.speechJob(worldId, jobId, signal);
        if (signal.aborted || !mounted.current) return;
        setPreviews(current => current[message]?.job_id === jobId ? previewEntries(current, message, job) : current);
      } while (job.state === "running" && !signal.aborted);
    } catch {
      if (!signal.aborted && mounted.current) setReviewFeedback(current => ({ ...current, [message]: "未能继续读取新配音状态。重新打开会话可继续查询，不会重新生成。" }));
    }
  }, [client, worldId]);
  const decide = useCallback(async (message: string, jobId: string, decision: "replace" | "keep") => {
    if (decisionPending.current) return;
    decisionPending.current = true; setDeciding(message);
    try {
      await client.decideSpeechPreview(worldId, jobId, decision);
      reviewVersion.current++;
      if (mounted.current) {
        setPreviews(current => { const next = { ...current }; if (next[message]?.job_id === jobId) delete next[message]; return next; });
        setReviewFeedback(current => ({ ...current, [message]: "" }));
        setFeedback(decision === "replace" ? "已替换为新配音，下次点击‘播放配音’会读取新声音。" : "未替换原配音。新试听声音已清除。");
      }
    } catch (failure) {
      if (mounted.current) setReviewFeedback(current => ({ ...current, [message]: speechFailure(failure) }));
    } finally { decisionPending.current = false; if (mounted.current) setDeciding(null); }
  }, [client, worldId]);

  const drain = useCallback(async function runQueue() {
    if (worker.current) return;
    worker.current = true;
    const generation = epoch.current;
    try {
      while (queue.current.length && generation === epoch.current && mounted.current && !document.hidden) {
        const item = queue.current.shift()!;
        controller.current = new AbortController();
        setBusy(true); setPlaying(item.message); setPlaybackMode(item.mode); setFeedback(item.mode === "preview" ? "正在读取新配音…" : item.mode === "regenerate" ? "正在重新配音，原声音保留…" : "正在为这条回复配音…");
        try {
          let job = item.mode === "preview" ? await client.speechJob(worldId, item.jobId!, controller.current.signal)
            : item.mode === "regenerate" ? await client.regenerateSpeech(worldId, item.conversation, item.message, item.requestId!, controller.current.signal)
              : await client.generateSpeech(worldId, item.conversation, item.message, controller.current.signal, item.requestId);
          if (item.mode) { rememberPreview(item.message, job); setReviewFeedback(current => ({ ...current, [item.message]: "" })); }
          const deadline = Date.now() + 970_000;
          while (job.state === "running" && generation === epoch.current) {
            setFeedback(generationFeedback(job));
            if (Date.now() >= deadline) throw new Error("speech_poll_timeout");
            await waitForStatus(controller.current.signal);
            job = await client.speechJob(worldId, job.job_id, controller.current.signal);
            if (item.mode) rememberPreview(item.message, job);
          }
          if (generation !== epoch.current) break;
          if (job.state !== "ready") {
            const action = item.mode ? "重新配音" : "播放配音";
            setFeedback(`${speechJobFailure(job.error, action)}${item.mode ? " 原配音未替换。" : ""}${job.state === "failed" || job.state === "unknown" ? speechRetryHint(job.error, action) : ""}`);
            continue;
          }
          if (item.mode === "regenerate") { setFeedback("新配音已生成，请在消息下方试听，再选择是否替换。"); continue; }
          setFeedback(job.reused ? "正在读取已缓存的声音…" : "声音已生成，正在准备播放…");
          const blob = await client.speechAudio(worldId, job.job_id, controller.current.signal, Boolean(item.requestId));
          if (generation !== epoch.current) break;
          release(); url.current = URL.createObjectURL(blob);
          const sound = new Audio(url.current); audio.current = sound;
          await new Promise<void>((resolve, reject) => {
            const signal = controller.current!.signal;
            let settled = false;
            const startup = setTimeout(() => done(new Error("audio_playback_timeout")), 20_000);
            let stalled: ReturnType<typeof setTimeout> | undefined;
            let lastTime = 0, lastAdvance = Date.now();
            const watchdog = setInterval(() => { if (sound.currentTime > lastTime) { lastTime = sound.currentTime; lastAdvance = Date.now(); } else if (Date.now() - lastAdvance > 30_000) done(new Error("audio_playback_timeout")); }, 1000);
            const done = (failure?: Error) => { if (settled) return; settled = true; clearTimeout(startup); clearTimeout(stalled); clearInterval(watchdog); signal.removeEventListener("abort", aborted); document.removeEventListener("securitypolicyviolation", policyBlocked); sound.onended = null; sound.onerror = null; sound.onplaying = null; sound.onwaiting = null; sound.ontimeupdate = null; if (failure) reject(failure); else resolve(); };
            const aborted = () => done();
            const policyBlocked = (event: SecurityPolicyViolationEvent) => {
              if (event.effectiveDirective === "media-src" && (event.blockedURI === sound.src || event.blockedURI === "blob")) done(new Error("audio_playback_policy_blocked"));
            };
            sound.onended = () => done(); sound.onerror = () => done(new Error(sound.error?.code === 3 || sound.error?.code === 4 ? "audio_playback_decode_failed" : "audio_playback_failed"));
            const showPlaybackTime = () => { if (!settled && !sound.paused && generation === epoch.current && mounted.current) setFeedback(`正在播放 · ${Math.floor(sound.currentTime)}秒${Number.isFinite(sound.duration) ? ` / ${Math.ceil(sound.duration)}秒` : ""}`); };
            sound.ontimeupdate = showPlaybackTime;
            sound.onplaying = () => { clearTimeout(startup); clearTimeout(stalled); showPlaybackTime(); };
            sound.onwaiting = () => { clearTimeout(stalled); stalled = setTimeout(() => done(new Error("audio_playback_timeout")), 20_000); };
            signal.addEventListener("abort", aborted, { once: true });
            document.addEventListener("securitypolicyviolation", policyBlocked);
            void sound.play().catch((failure: unknown) => done(new Error(failure instanceof DOMException && failure.name === "NotSupportedError" ? "audio_playback_decode_failed" : "audio_playback_blocked")));
          });
          if (item.mode === "preview" && generation === epoch.current && sound.ended) {
            const completed = await client.speechPreviewCompleted(worldId, job.job_id);
            if (generation === epoch.current && mounted.current) {
              rememberPreview(item.message, completed);
              setFeedback("试听已结束，请在消息下方选择是否替换原配音。");
            }
          }
          if (!item.mode && generation === epoch.current) setFeedback("");
        } catch (failure) {
          if (generation === epoch.current && mounted.current) {
            let detail = failure instanceof Error && failure.message.startsWith("audio_playback_") ? playbackFailure(failure.message) : failure instanceof Error && failure.message === "speech_poll_timeout" ? errors.speech_timeout : speechFailure(failure);
            if (item.mode === "preview") {
              detail = detail.replaceAll("播放配音", "试听新配音").replaceAll("消息旁", "消息下方");
              setReviewFeedback(current => ({ ...current, [item.message]: detail }));
            }
            setFeedback(detail);
          }
          if (item.mode === "regenerate" && generation === epoch.current) void loadPreviews(item.conversation, [item.message]).catch(() => {});
        } finally { release(); }
      }
    } finally {
      worker.current = false;
      if (mounted.current && generation === epoch.current) { setBusy(false); setPlaying(null); setPlaybackMode(undefined); }
      if (mounted.current && queue.current.length && !document.hidden) void runQueue();
    }
  }, [client, worldId, release, rememberPreview, loadPreviews]);
  const play = useCallback((conversation: string, message: string) => {
    if (!settings.current?.settings.enabled) { setFeedback("请先在设置中的“角色配音”开启配音。"); return; }
    if (worker.current || queue.current.length) { setFeedback("已有声音在播放或生成，可先停止，再选择这条消息。"); return; }
    queue.current.push({ conversation, message, requestId: crypto.randomUUID() }); void drain();
  }, [drain]);
  const regenerate = useCallback((conversation: string, message: string) => {
    if (worker.current || queue.current.length || decisionPending.current) { setFeedback("已有声音正在播放、生成或保存选择，请等它结束后再重新配音。"); return; }
    queue.current.push({ conversation, message, requestId: crypto.randomUUID(), mode: "regenerate" }); void drain();
  }, [drain]);
  const preview = useCallback((conversation: string, message: string, jobId: string) => {
    if (worker.current || queue.current.length) { setFeedback("已有声音在播放或生成，请先停止，再试听新配音。"); return; }
    queue.current.push({ conversation, message, jobId, mode: "preview" }); void drain();
  }, [drain]);
  const committed = useCallback((conversation: string, message: ChatMessage) => {
    if (!settings.current?.settings.enabled || message.sender_kind !== "character" || message.media?.only_media || document.hidden || !mounted.current) return;
    if (seen.current.has(message.message_id)) return;
    seen.current.add(message.message_id);
    if (seen.current.size > 128) seen.current.delete(seen.current.values().next().value!);
    if (queue.current.length >= 8) { setFeedback("待播放回复较多，余下消息可手动播放。"); return; }
    if (playing === message.message_id || queue.current.some(item => item.message === message.message_id)) return;
    queue.current.push({ conversation, message: message.message_id }); void drain();
  }, [drain, playing]);
  return <SpeechContext.Provider value={{ status, feedback, playing, busy, playbackMode, previews, reviewFeedback, deciding, refresh, stop, play, regenerate, preview, loadPreviews, followPreview, decide, committed }}>{children}</SpeechContext.Provider>;
}

export function SpeechControls({ conversation, message }: { conversation: string; message: string }) {
  const speech = useSpeech();
  if (!speech) return null;
  const pending = speech.previews[message];
  if (!speech.status?.settings.enabled && !pending) return null;
  return <>{speech.status?.settings.enabled && <span className="speech-message-actions"><button type="button" className="text-action" onClick={() => speech.playing === message ? speech.stop() : speech.play(conversation, message)}>{speech.playing === message ? "停止配音" : "播放配音"}</button><button type="button" className="text-action" disabled={speech.busy || speech.deciding !== null || pending?.state === "ready" || pending?.state === "running"} title={speech.status.settings.provider === "local" ? "重新调用本地模型，试听后选择是否替换；本地不限生成次数" : "重新调用当前云端配音服务，试听后选择是否替换；计入云端配音次数和所选路线费用"} onClick={() => speech.regenerate(conversation, message)}>重新配音</button></span>}<SpeechPreview conversation={conversation} message={message} /></>;
}
function SpeechPreview({ conversation, message }: { conversation: string; message: string }) {
  const speech = useSpeech(), job = speech?.previews[message];
  const following = job?.state === "running" && !(speech?.busy && speech.playing === message);
  const follow = speech?.followPreview;
  const jobId = job?.job_id;
  const expires = job?.cache_expires_at;
  useEffect(() => {
    if (!following || !jobId || !follow) return;
    const controller = new AbortController();
    void follow(message, jobId, controller.signal);
    return () => controller.abort();
  }, [following, jobId, message, follow]);
  useEffect(() => {
    if (!expires || !jobId || !follow || job?.state !== "ready") return;
    const controller = new AbortController();
    const delay = Math.max(0, Date.parse(expires) - Date.now() + 250);
    if (!Number.isFinite(delay)) return;
    const timer = setTimeout(() => { void follow(message, jobId, controller.signal); }, delay);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [expires, jobId, job?.state, follow, message]);
  if (!speech || !job || job.review_state !== "pending") return null;
  const playing = speech.playing === message && speech.playbackMode === "preview";
  const deciding = speech.deciding === message;
  return <section className="speech-preview" aria-label="重新配音试听与选择">
    <span className="speech-preview-title">新配音{job.state === "ready" ? " · 待确认" : ""}</span>
    {job.state === "running" ? <p role="status">{generationFeedback(job)}</p>
      : job.state !== "ready" ? <p role="status">{speechJobFailure(job.error, "重新配音")} 原配音未替换。{speechRetryHint(job.error, "重新配音")}</p>
        : <><p role="status">{playing ? speech.feedback : job.preview_completed ? "试听已结束，请选择是否替换原配音。" : "请先试听新配音，播放完后选择是否替换。"}</p>
          <button type="button" className="text-action" disabled={deciding || (speech.busy && !playing)} onClick={() => playing ? speech.stop() : speech.preview(conversation, message, job.job_id)}>{playing ? "停止试听" : job.preview_completed ? "再次试听新配音" : "试听新配音"}</button>
          {job.preview_completed && <div className="speech-preview-decision" role="group" aria-label="是否替换原配音"><button type="button" className="primary-button" disabled={speech.deciding !== null || speech.busy} onClick={() => void speech.decide(message, job.job_id, "replace")}>{deciding ? "正在保存选择…" : "替换之前的配音"}</button><button type="button" className="text-action" disabled={speech.deciding !== null || speech.busy} onClick={() => void speech.decide(message, job.job_id, "keep")}>保留之前的配音</button></div>}
        </>}
    {speech.reviewFeedback[message] && <p role="alert">{speech.reviewFeedback[message]}</p>}
  </section>;
}

export function useSpeechPreviews(conversation: string, messages: ChatMessage[] | null) {
  const load = useSpeech()?.loadPreviews;
  useEffect(() => {
    if (!load || !messages) return;
    const controller = new AbortController();
    const ids = messages.filter(message => message.sender_kind === "character").map(message => message.message_id);
    void load(conversation, ids, controller.signal).catch(() => {});
    return () => controller.abort();
  }, [conversation, messages, load]);
}
export function SpeechFeedback() {
  const speech = useSpeech();
  useEffect(() => () => speech?.stop(), [speech?.stop]);
  if (!speech?.feedback && !speech?.busy) return null;
  return <div className="speech-feedback" role="status"><span>{speech.feedback}</span>{speech.busy && <button className="text-action" type="button" onClick={speech.stop}>停止配音</button>}</div>;
}
