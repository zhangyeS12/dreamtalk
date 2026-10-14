import { invoke, isTauri } from "@tauri-apps/api/core";
import { useEffect, useRef, useState } from "react";
import { CoreClient, type SpeechPricing, type SpeechSettings as Preferences, type SpeechStatus } from "@dreamtalk/api-client";
import { useDesktopUpdateBlock } from "./DesktopUpdates";
import { speechFailure, useSpeech } from "./SpeechPlayback";

function localFailure(error: unknown): string {
  const code = typeof error === "string" ? error : error instanceof Error ? error.message : "";
  const messages: Record<string, string> = {
    speech_local_legacy: "配音服务需要更新。点击下方“一键修复本地配音”即可处理。",
    speech_local_bridge_outdated: "配音服务需要更新。点击下方“一键修复本地配音”即可处理。",
    speech_model_folder_invalid: "请选择完成部署的 IndexTTS 2.5 目录，其中应包含 .venv、checkpoints 和 indextts。",
    speech_model_folder_missing: "请先选择本地模型目录。",
    speech_model_folder_busy: "当前服务由 dreamtalk 管理，请退出程序后再更换模型目录。",
    speech_local_token_missing: "此目录缺少本地访问密钥文件，请先完成本地服务部署。",
    speech_local_start_failed: "本地配音服务未能启动。可以点击“一键修复本地配音”重新检查并连接。",
    speech_local_start_timeout: "本地配音服务尚未就绪。可以点击“一键修复本地配音”重新检查，不会重新生成声音。",
    speech_local_probe_timeout: "本地连接检查未在 10 秒内完成，无法确认服务状态；请核对本地网络，没有重复启动服务。",
    speech_local_probe_failed: "无法完成本地服务状态检查，请核对本地网络与服务日志。",
    speech_local_key_required: "未能连接所选模型的配音服务。点击“一键修复本地配音”检查并重新连接。",
    speech_local_repair_busy: "还有配音正在生成，本次修复未关闭服务。请等生成结束后再点击修复。",
    speech_local_repair_unverified: "无法安全确认正在运行的服务是否属于此模型，已保留它。请核对所选模型目录；其他程序不会被关闭。",
    speech_local_repair_failed: "本地配音未能恢复。可以再次修复，或重新选择完成部署的模型目录。",
    speech_local_repair_changed: "服务状态刚刚发生变化，本次没有关闭它。请再次点击修复重新检查。",
    speech_local_repair_helper_missing: "当前程序缺少修复组件，请从完整的新版文件夹启动 dreamtalk。",
    update_busy: "程序正在更新或处理另一项服务操作，请稍后再修复。",
  };
  return messages[code] ?? speechFailure(error);
}

export function SpeechSettings({ client, worldId, onDirtyChange }: { client: CoreClient; worldId: string; onDirtyChange?: (dirty: boolean) => void }) {
  const speech = useSpeech();
  const [saved, setSaved] = useState<SpeechStatus | null>(null), [draft, setDraft] = useState<Preferences | null>(null);
  const [secret, setSecret] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [notice, setNotice] = useState(""), [pricing, setPricing] = useState<SpeechPricing | null>(null);
  const [local, setLocal] = useState<{ model_root: string | null; state: string } | null>(null);
  const [repairing, setRepairing] = useState(false);
  const lock = useRef(false), pendingReference = useRef<string | null>(null);
  const dirty = !!saved && !!draft && (JSON.stringify(saved.settings) !== JSON.stringify(draft) || !!secret.trim() || !!pendingReference.current);
  useDesktopUpdateBlock(busy ? "正在处理配音设置或本地服务。" : dirty ? "配音设置尚未保存。" : null);
  useEffect(() => { onDirtyChange?.(dirty || busy); }, [dirty, busy, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  useEffect(() => {
    let current = true;
    void client.speechSettings(worldId).then(value => { if (current) { setSaved(value); setDraft(value.settings); } })
      .catch(error => { if (current) setError(speechFailure(error)); });
    return () => { current = false; };
  }, [client, worldId]);
  useEffect(() => {
    if (!isTauri()) return;
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    const readLocal = async () => {
      try { const value = await invoke<{ model_root: string | null; state: string }>("local_speech_status"); if (current && !lock.current) setLocal(value); }
      catch { if (current && !lock.current) setLocal(null); }
      if (current) timer = setTimeout(() => void readLocal(), 5000);
    };
    void readLocal();
    return () => { current = false; clearTimeout(timer); };
  }, []);
  const read = async () => {
    if (lock.current) return;
    if (dirty && !window.confirm("重新读取会放弃尚未保存的配音设置，继续吗？")) return;
    lock.current = true; setBusy(true); setError("");
    try { const value = await client.speechSettings(worldId); setSaved(value); setDraft(value.settings); setSecret(""); pendingReference.current = null; await speech?.refresh(); }
    catch (failure) { setError(speechFailure(failure)); }
    finally { lock.current = false; setBusy(false); }
  };
  const save = async () => {
    if (lock.current || !draft || !saved) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try {
      let reference = draft.secret_ref;
      if (draft.enabled && draft.provider === "local" && draft.local_url === "http://127.0.0.1:7861" && isTauri() && local?.model_root) {
        reference = pendingReference.current ?? draft.secret_ref ?? crypto.randomUUID(); pendingReference.current = reference;
        const value = await invoke<{ model_root: string | null; state: string }>("prepare_local_speech", { worldId, secretRef: reference });
        setLocal(value);
        if (value.state === "legacy") throw new Error("speech_local_legacy");
      } else if (secret.trim()) {
        if (!isTauri()) throw new Error("desktop_credentials_required");
        reference = pendingReference.current ?? crypto.randomUUID(); pendingReference.current = reference;
        await invoke("speech_credential_put", { worldId, secretRef: reference, secret: secret.trim() });
      } else if (pendingReference.current) reference = pendingReference.current;
      const value = await client.saveSpeechSettings(worldId, { ...draft, secret_ref: reference }, saved.revision);
      setSaved(value); setDraft(value.settings); setSecret(""); pendingReference.current = null; setPricing(null);
      if (!value.settings.enabled) speech?.stop();
      await speech?.refresh();
      setNotice(value.settings.enabled ? "配音已开启。给角色绑定音色后，新回复会自动播放。" : "配音已关闭。");
      if (isTauri() && saved.settings.secret_ref && saved.settings.secret_ref !== reference) {
        try { await invoke("forget_speech_credentials", { worldId, secretRef: saved.settings.secret_ref }); }
        catch { setNotice("配音设置已保存；旧密钥的清理未能确认，可在下次保存时继续核对。"); }
      }
    } catch (failure) { setError(failure instanceof Error && failure.message === "desktop_credentials_required" ? "服务密钥需要在桌面版中安全保存。" : localFailure(failure)); }
    finally { lock.current = false; setBusy(false); }
  };
  const price = async () => {
    if (lock.current || dirty) return;
    lock.current = true; setBusy(true); setError("");
    try { setPricing(await client.speechPricing(worldId)); }
    catch (failure) { setError(speechFailure(failure)); }
    finally { lock.current = false; setBusy(false); }
  };
  const configureLocal = async (choose: boolean) => {
    if (lock.current || !draft) return;
    lock.current = true; setBusy(true); setError("");
    try {
      if (choose) {
        const value = await invoke<{ model_root: string | null; state: string } | null>("choose_local_speech_folder");
        if (value) { setLocal(value); setNotice("本地模型目录已登记。开启配音并保存后，服务会随 dreamtalk 启动。"); }
      } else {
        const reference = pendingReference.current ?? draft.secret_ref ?? crypto.randomUUID(); pendingReference.current = reference;
        const value = await invoke<{ model_root: string | null; state: string }>("prepare_local_speech", { worldId, secretRef: reference });
        setLocal(value); setNotice(value.state === "legacy" ? "配音服务需要更新，请点击“一键修复本地配音”。" : "本地服务已就绪。模型在收到第一条配音任务时加载。");
      }
    } catch (failure) { setError(localFailure(failure)); }
    finally { lock.current = false; setBusy(false); }
  };
  const repairLocal = async () => {
    if (lock.current || !draft || !saved || !isTauri()) return;
    lock.current = true; setBusy(true); setRepairing(true); setError("");
    setNotice("正在检查并修复本地配音，请稍候…");
    try {
      if (!local?.model_root) {
        const selected = await invoke<{ model_root: string | null; state: string } | null>("choose_local_speech_folder");
        if (!selected) { setNotice("尚未选择模型目录，修复没有开始。"); return; }
        setLocal(selected);
      }
      const savedLocal = saved.settings.provider === "local" && saved.settings.local_url === "http://127.0.0.1:7861";
      const reference = savedLocal && saved.settings.secret_ref ? saved.settings.secret_ref : pendingReference.current ?? crypto.randomUUID();
      const value = await invoke<{ model_root: string | null; state: string }>("repair_local_speech", { worldId, secretRef: reference });
      setLocal(value);
      if (savedLocal) {
        if (saved.settings.secret_ref !== reference) {
          pendingReference.current = reference;
          const updated = await client.saveSpeechSettings(worldId, { ...saved.settings, secret_ref: reference }, saved.revision);
          setSaved(updated);
        }
        setDraft(current => current && current.provider === "local" && current.local_url === "http://127.0.0.1:7861" ? { ...current, secret_ref: reference } : current);
        setSecret(""); pendingReference.current = null;
        await speech?.refresh();
        setNotice("本地配音已恢复。可以返回聊天播放配音；此次修复没有重新生成声音。");
      } else {
        pendingReference.current = reference;
        setNotice("本地服务已恢复。保存当前配音设置后即可使用；此次修复没有重新生成声音。");
      }
    } catch (failure) { setNotice(""); setError(localFailure(failure)); }
    finally { lock.current = false; setBusy(false); setRepairing(false); }
  };
  if (!draft) return <section className="settings-section"><h2>角色配音</h2><p>{error || "正在读取配音设置…"}</p><button type="button" onClick={() => void read()}>重新读取</button></section>;
  const field = <K extends keyof Preferences>(key: K, value: Preferences[K]) => setDraft(old => old ? { ...old, [key]: value } : old);
  return <section className="settings-section speech-settings"><div className="section-heading"><h2>角色配音</h2><p>仅影响当前世界。角色文字回复保存后，使用他绑定的音色自动说话；群聊按发言顺序播放。</p></div>
    <label className="speech-check"><input type="checkbox" checked={draft.enabled} disabled={busy} onChange={event => { field("enabled", event.target.checked); if (!event.target.checked) speech?.stop(); }} /><span><strong>开启角色配音</strong><small>保存后生效。切换页面、回到书架或隐藏窗口会停止播放。</small></span></label>
    <label className="field"><span>配音方式</span><select disabled={busy} value={draft.provider} onChange={event => {
      setDraft(old => old ? { ...old, provider: event.target.value as Preferences["provider"], secret_ref: null, consent_remote: false, consent_paid: false } : old);
      setSecret(""); setPricing(null); pendingReference.current = null;
    }}><option value="local">本地 IndexTTS 2.5</option><option value="huggingface">官方 Hugging Face 演示 · 免费额度</option><option value="compshare">优云智算 IndexTTS 2.5 · 付费云服务</option></select></label>
    {draft.provider === "local" ? <><p className="inline-hint">登记本地模型目录并开启配音后，服务随 dreamtalk 后台启动，无需保留启动窗口。首次合成时加载模型并占用显存；退出程序会关闭由它启动的服务。</p>
      {isTauri() && draft.local_url === "http://127.0.0.1:7861" && <div className="speech-local-service"><p role="status">{repairing ? "正在修复本地配音…" : local?.state === "ready" ? "本地服务已就绪" : local?.state === "legacy" || local?.state === "outdated" ? "配音服务需要更新，可以一键修复" : "本地服务尚未就绪，可以一键检查并修复"}</p><div className="profile-actions"><button type="button" className="primary-button" disabled={busy} onClick={() => void repairLocal()}>{repairing ? "正在修复…" : "一键修复本地配音"}</button><button type="button" className="text-action" disabled={busy} onClick={() => void configureLocal(true)}>选择模型目录</button><button type="button" className="text-action" disabled={busy || !local?.model_root} onClick={() => void configureLocal(false)}>检查服务</button></div><p className="inline-hint">检查服务、更新旧版本并重新连接。生成中的配音会保留，修复不会重新生成声音。</p>{local?.model_root && <details><summary>查看模型目录</summary><p className="inline-hint">{local.model_root}</p></details>}</div>}
      <label className="field"><span>本地服务地址</span><input value={draft.local_url} disabled={busy} onChange={event => field("local_url", event.target.value)} placeholder="http://127.0.0.1:7861" maxLength={200} /></label></>
      : draft.provider === "huggingface" ? <p className="inline-hint">使用你指定的官方 IndexTTS 2.5 Demo。可不填密钥使用共享匿名额度；免费个人账户可填写自己的 HF Token。排队、休眠或额度用尽会停止配音；PRO／无法核实的账户不会进入免费路线。</p>
        : <><p className="inline-hint">需要自己的优云智算模型 API Key。每次任务前读取计价与余额；费用按平台结算。字数和每日次数限制独立于文字聊天额度。首次使用会在云账户保存可复用音色；删除本地音色卡不会删除云端副本，云端副本需到平台管理。</p><button type="button" disabled={busy || dirty || !saved?.settings.secret_ref} onClick={() => void price()}>查看当前计价与余额（不生成语音）</button>{pricing && <p role="status">每 {pricing.unit_characters} 个计费字符 {pricing.costs.text_to_speech} 积分 · 可用 {pricing.balance.available_points} 积分。计价可能变化，每次生成前重新核对。</p>}</>}
    <label className="field"><span>{draft.provider === "local" ? "本地访问密钥" : draft.provider === "huggingface" ? "HF Token（可选）" : "云服务 API Key"}</span><input type="password" autoComplete="off" value={secret} disabled={busy || !isTauri()} maxLength={4096} onChange={event => setSecret(event.target.value)} placeholder={draft.secret_ref ? "已保存；留空保留当前密钥" : "仅保存在本机安全凭据存储"} /></label>
    {draft.secret_ref && <button className="text-action" disabled={busy} type="button" onClick={() => { field("secret_ref", null); pendingReference.current = null; setSecret(""); }}>移除此路线密钥（保存后生效）</button>}
    <div className="speech-limits"><label className="field"><span>每条配音最多字数</span><input type="number" min={1} max={2000} step={1} disabled={busy} value={draft.max_characters} onChange={event => field("max_characters", Number(event.target.value))} /></label>{draft.provider !== "local" && <label className="field"><span>每日最多生成次数</span><input type="number" min={1} max={1000} step={1} disabled={busy} value={draft.daily_calls} onChange={event => field("daily_calls", Number(event.target.value))} /></label>}</div>
    <p className="inline-hint">声音从生成成功起缓存6小时，重播不续期，也不计生成次数。没有有效缓存或上次失败时，点击“播放配音”会重新生成；付费路线会按新任务计费。{draft.provider === "local" ? "本地配音不限生成次数。" : "云端次数按本机所有世界合计、UTC 日期计算，失败尝试也计一次；本地调用不占云端次数。"}超长回复保留完整文字并提示。</p>
    <label className="speech-check"><input type="checkbox" checked={draft.skip_actions} disabled={busy} onChange={event => field("skip_actions", event.target.checked)} /><span>跳过括号中的动作描写及独立一行的星号动作，只朗读台词。</span></label>
    {draft.provider !== "local" && <label className="speech-check"><input type="checkbox" checked={draft.consent_remote} disabled={busy} onChange={event => field("consent_remote", event.target.checked)} /><span>允许将待朗读台词和所绑定的参考音频发送给此服务；世界书和其他聊天内容不随配音发送。</span></label>}
    {draft.provider === "compshare" && <label className="speech-check"><input type="checkbox" checked={draft.consent_paid} disabled={busy} onChange={event => field("consent_paid", event.target.checked)} /><span>我同意新回复自动配音，以及手动点击在没有有效缓存时调用该付费服务。停止播放不撤销已提交任务的费用。</span></label>}
    {error && <p className="app-alert" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="profile-actions"><button className="primary-button" type="button" disabled={busy || !dirty} onClick={() => void save()}>{busy ? "正在处理…" : "保存配音设置"}</button><button className="text-action" type="button" disabled={busy} onClick={() => void read()}>重新读取</button></div>
  </section>;
}
