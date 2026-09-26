import { useEffect, useState, type FormEvent } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { type CoreClient, type LLMRuntimeStatus } from "@dreamtalk/api-client";

type ProviderKind = "openai-responses" | "anthropic" | "gemini" | "openai-compatible";
type ChatModelSetup = {
  provider_kind: ProviderKind;
  model_id: string;
  base_url: string | null;
  max_billable_input_tokens: number;
  max_output_tokens: number;
};
type ModelUpdateOutcome = { old_credential_cleanup_incomplete: boolean };
const cleanupWarningKey = "dreamtalk-model-cleanup-warning";

const statusText: Record<LLMRuntimeStatus, string> = {
  ready: "模型和凭据已就绪。首次聊天时才会实际联系提供商。",
  partially_configured: "部分模型缺少凭据。请检查现有高级模型配置。",
  unconfigured: "尚未配置聊天模型。完成首次设置后才能向角色发送消息。",
  degraded: "模型配置或凭据状态异常。世界和已有聊天记录仍可使用。",
};

export function ModelSetup({ client, onConfigured = () => window.location.reload() }: {
  client: CoreClient;
  onConfigured?: () => void;
}) {
  const [status, setStatus] = useState<LLMRuntimeStatus | null>(null);
  const [managed, setManaged] = useState<ChatModelSetup | null>(null);
  const [managedUnsupported, setManagedUnsupported] = useState(false);
  const [providerKind, setProviderKind] = useState<ProviderKind>("openai-responses");
  const [modelId, setModelId] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [inputLimit, setInputLimit] = useState("");
  const [outputLimit, setOutputLimit] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(() => {
    try {
      const warning = window.sessionStorage.getItem(cleanupWarningKey);
      window.sessionStorage.removeItem(cleanupWarningKey);
      return warning ?? "";
    } catch { return ""; }
  });

  useEffect(() => {
    let active = true;
    void client.health().then(async health => {
      if (!active) return;
      setStatus(health.llm_status);
      if (!isTauri() || health.llm_status === "unconfigured") return;
      try {
        const existing = await invoke<ChatModelSetup | null>("managed_chat_model_setup");
        if (!active || !existing) return;
        setManaged(existing);
        setProviderKind(existing.provider_kind);
        setModelId(existing.model_id);
        setBaseUrl(existing.base_url ?? "");
        setInputLimit(String(existing.max_billable_input_tokens));
        setOutputLimit(String(existing.max_output_tokens));
      } catch { if (active) setManagedUnsupported(true); }
    }).catch(() => { if (active) setError("无法读取模型状态，请检查核心连接。"); });
    return () => { active = false; };
  }, [client]);

  const inputBound = Number(inputLimit);
  const outputBound = Number(outputLimit);
  const editing = status !== "unconfigured" && managed !== null;
  const secretRequired = !editing || status !== "ready" || providerKind !== managed?.provider_kind;
  const valid = modelId.length > 0 && modelId.length <= 128 && modelId.trim() === modelId && !/\s/.test(modelId)
    && secret.length <= 4096 && (!secretRequired || secret.length > 0)
    && Number.isSafeInteger(inputBound) && inputBound >= 1 && inputBound <= 1_000_000
    && Number.isSafeInteger(outputBound) && outputBound >= 1 && outputBound <= 100_000
    && (providerKind !== "openai-compatible" || /^https?:\/\//.test(baseUrl));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!valid || saving || !isTauri() || (status !== "unconfigured" && !editing)) return;
    setSaving(true);
    setError("");
    try {
      const outcome = await invoke<ModelUpdateOutcome | void>(editing ? "update_chat_model" : "configure_chat_model", {
        setup: {
          provider_kind: providerKind,
          model_id: modelId,
          base_url: providerKind === "openai-compatible" ? baseUrl : null,
          max_billable_input_tokens: inputBound,
          max_output_tokens: outputBound,
        },
        secret,
      });
      setSecret("");
      if (outcome?.old_credential_cleanup_incomplete) {
        try { window.sessionStorage.setItem(cleanupWarningKey, "模型已更新，但旧凭据未能从 Windows 安全凭据存储清理。请检查本机凭据存储。"); } catch { /* The update remains committed. */ }
      }
      onConfigured();
    } catch (failure) {
      if (failure === "secure_storage_unavailable") setError("Windows 安全凭据存储不可用，密钥未保存。");
      else if (failure === "model_edit_requires_managed_single_chat_configuration") setError("当前模型配置含有高级设置，不能从此页面覆盖。");
      else if (failure === "model_update_new_secret_required") setError("更换提供商或补齐缺失凭据时，请填写新 API 密钥。");
      else if (failure === "model_setup_recovery_failed") setError("模型更新和恢复均未完成。请重启应用后检查模型状态。");
      else setError("模型设置未完成。请核对模型名称、服务地址和可信 Token 上界，或重新启动程序后重试。");
    } finally { setSaving(false); }
  };

  return <section className="settings-section model-setup" aria-label="聊天模型">
    <div className="section-heading"><h2>聊天模型</h2><p>{status === null ? "正在读取模型状态…" : statusText[status]}</p></div>
    {error ? <p className="app-alert" role="alert">{error}</p> : null}
    {managedUnsupported && status !== "unconfigured" ? <p className="inline-hint">当前配置由高级方式管理；此处不会覆盖其中的路由、定价或其他设置。</p> : null}
    {isTauri() && (status === "unconfigured" || (editing && !managedUnsupported)) ? <form onSubmit={event => void save(event)}>
      <div className="model-setup-fields">
        <label className="field"><span>提供商</span><select value={providerKind} disabled={saving} onChange={event => setProviderKind(event.target.value as ProviderKind)}><option value="openai-responses">OpenAI</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option><option value="openai-compatible">兼容 Chat Completions 的服务</option></select></label>
        <label className="field"><span>模型名称</span><input value={modelId} disabled={saving} onChange={event => setModelId(event.target.value)} maxLength={128} placeholder="按提供商显示的完整名称填写" /></label>
        {providerKind === "openai-compatible" ? <label className="field"><span>服务地址</span><input type="url" value={baseUrl} disabled={saving} onChange={event => setBaseUrl(event.target.value)} placeholder="https://example.com/v1" /></label> : null}
        <label className="field"><span>{secretRequired ? "API 密钥" : "新 API 密钥（可留空）"}</span><input type="password" autoComplete="off" value={secret} disabled={saving} onChange={event => setSecret(event.target.value)} maxLength={4096} placeholder={secretRequired ? "仅保存在 Windows 安全凭据存储" : "留空则沿用现有密钥；不会显示现有密钥"} /></label>
      </div>
      <details className="model-advanced"><summary>高级设置：可信 Token 上界（必填）</summary><p className="inline-hint">请按所选模型的官方说明填写单次请求可能计费的输入上限和允许的输出上限。系统会在每次调用前保守预留；没有可信上界就不会启动模型请求。</p><div className="model-setup-fields"><label className="field"><span>单次输入 Token 上界</span><input type="number" min="1" max="1000000" step="1" value={inputLimit} disabled={saving} onChange={event => setInputLimit(event.target.value)} /></label><label className="field"><span>单次输出 Token 上界</span><input type="number" min="1" max="100000" step="1" value={outputLimit} disabled={saving} onChange={event => setOutputLimit(event.target.value)} /></label></div></details>
      <div className="group-actions"><button type="submit" className="primary-button" disabled={!valid || saving}>{saving ? "正在保存并重启核心…" : editing ? "更新模型设置" : "保存模型设置"}</button></div>
      <p className="inline-hint">保存后核心会重新启动，页面自动连接。不会测试密钥有效性，也不会在设置时产生模型费用。更新失败时会恢复原配置。</p>
    </form> : null}
    {status === "unconfigured" && !isTauri() ? <p className="inline-hint">当前浏览器开发入口不保存模型密钥。请在桌面应用完成首次设置。</p> : null}
  </section>;
}
