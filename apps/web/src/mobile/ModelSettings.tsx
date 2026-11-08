import { useEffect, useState, type FormEvent } from "react";
import { hostCall, feedback, type ModelSetup } from "./host";
export function ModelSettings({ onConfigured }: { onConfigured: () => Promise<void> }) {
  const [model, setModel] = useState<ModelSetup>({ provider_kind: "openai-compatible", model_id: "", base_url: "", max_billable_input_tokens: 0, max_output_tokens: 8192, streaming: true, timeout_ms: 120000 });
  const [secret, setSecret] = useState(""), [configured, setConfigured] = useState(false), [reading, setReading] = useState(true);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    hostCall<ModelSetup | null>("model_status").then(value => { if (active && value) { setModel(value); setConfigured(true); } })
      .catch(e => { if (active) setError(feedback(e)); }).finally(() => { if (active) setReading(false); });
    return () => { active = false; };
  }, []);
  const change = <K extends keyof ModelSetup>(key: K, value: ModelSetup[K]) => setModel(current => ({ ...current, [key]: value }));
  const save = async (event: FormEvent) => {
    event.preventDefault(); if (busy || reading) return;
    setBusy(true); setError(""); setNotice("");
    try { await hostCall("configure_model", { ...model, secret }); setSecret(""); await onConfigured(); setConfigured(true); setNotice("API 设置已保存。发送消息时才会调用模型。"); }
    catch (e) { setError(feedback(e)); } finally { setBusy(false); }
  };
  if (reading) return <p role="status">正在读取模型设置…</p>;
  return <form className="mobile-form" onSubmit={event => void save(event)}>
    <h2>聊天模型</h2><p className="mobile-muted">填写你使用的 API。输入容量请按服务商公布的型号规格填写。</p>
    <label>接口类型<select disabled={busy} value={model.provider_kind} onChange={e => change("provider_kind", e.target.value as ModelSetup["provider_kind"])}>
      <option value="openai-compatible">Chat Completions 兼容接口</option><option value="openai-responses">Responses 接口</option>
      <option value="anthropic-messages">Anthropic Messages</option><option value="gemini-interactions">Gemini Interactions</option></select></label>
    <label>模型名称<input required maxLength={128} disabled={busy} autoCapitalize="none" autoCorrect="off" value={model.model_id} onChange={e => change("model_id", e.target.value)} /></label>
    {model.provider_kind === "openai-compatible" && <label>API 地址<input required type="url" placeholder="https://你的服务地址/v1" autoCapitalize="none" disabled={busy} value={model.base_url ?? ""} onChange={e => change("base_url", e.target.value)} /></label>}
    <label>API 密钥<input required={!configured} type="password" autoComplete="off" disabled={busy} value={secret} placeholder={configured ? "留空保留已有密钥" : "输入 API 密钥"} onChange={e => setSecret(e.target.value)} /></label>
    <label>最大输入容量（Token）<input required type="number" inputMode="numeric" min={1} max={2147483647} disabled={busy} value={model.max_billable_input_tokens || ""} onChange={e => change("max_billable_input_tokens", Number(e.target.value))} /></label>
    <label>最大回复长度（Token）<input required type="number" inputMode="numeric" min={1} max={2147483647} disabled={busy} value={model.max_output_tokens} onChange={e => change("max_output_tokens", Number(e.target.value))} /></label>
    <label className="mobile-check"><input type="checkbox" disabled={busy} checked={model.streaming} onChange={e => change("streaming", e.target.checked)} />流式显示回复</label>
    {error && <p role="alert" className="mobile-error">{error}</p>}{notice && <p role="status">{notice}</p>}
    <button className="primary-button" disabled={busy}>{busy ? "正在保存…" : "保存 API 设置"}</button>
  </form>;
}
