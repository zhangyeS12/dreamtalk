import { useEffect, useState, type FormEvent } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { type CoreClient, type LLMRuntimeStatus } from "@livingworld/api-client";

type ProviderKind = "openai-responses" | "anthropic" | "gemini" | "openai-compatible";

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
  const [providerKind, setProviderKind] = useState<ProviderKind>("openai-responses");
  const [modelId, setModelId] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [inputLimit, setInputLimit] = useState("");
  const [outputLimit, setOutputLimit] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void client.health().then(health => {
      if (active) setStatus(health.llm_status);
    }).catch(() => { if (active) setError("无法读取模型状态，请检查核心连接。"); });
    return () => { active = false; };
  }, [client]);

  const inputBound = Number(inputLimit);
  const outputBound = Number(outputLimit);
  const valid = modelId.length > 0 && modelId.length <= 128 && modelId.trim() === modelId && !/\s/.test(modelId)
    && secret.length > 0 && secret.length <= 4096
    && Number.isSafeInteger(inputBound) && inputBound >= 1 && inputBound <= 1_000_000
    && Number.isSafeInteger(outputBound) && outputBound >= 1 && outputBound <= 100_000
    && (providerKind !== "openai-compatible" || /^https?:\/\//.test(baseUrl));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!valid || saving || status !== "unconfigured" || !isTauri()) return;
    setSaving(true);
    setError("");
    try {
      await invoke("configure_chat_model", {
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
      onConfigured();
    } catch (failure) {
      if (failure === "secure_storage_unavailable") setError("Windows 安全凭据存储不可用，密钥未保存。");
      else if (failure === "model_setup_requires_empty_configuration") setError("已有模型配置，请先检查现有配置。本入口只用于首次设置。");
      else setError("模型设置未完成。请核对模型名称、服务地址和可信 Token 上界，或重新启动程序后重试。");
    } finally { setSaving(false); }
  };

  return <section className="settings-section model-setup" aria-label="聊天模型">
    <div className="section-heading"><h2>聊天模型</h2><p>{status === null ? "正在读取模型状态…" : statusText[status]}</p></div>
    {error ? <p className="app-alert" role="alert">{error}</p> : null}
    {status === "unconfigured" && isTauri() ? <form onSubmit={event => void save(event)}>
      <div className="model-setup-fields">
        <label className="field"><span>提供商</span><select value={providerKind} disabled={saving} onChange={event => setProviderKind(event.target.value as ProviderKind)}><option value="openai-responses">OpenAI</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option><option value="openai-compatible">兼容 Chat Completions 的服务</option></select></label>
        <label className="field"><span>模型名称</span><input value={modelId} disabled={saving} onChange={event => setModelId(event.target.value)} maxLength={128} placeholder="按提供商显示的完整名称填写" /></label>
        {providerKind === "openai-compatible" ? <label className="field"><span>服务地址</span><input type="url" value={baseUrl} disabled={saving} onChange={event => setBaseUrl(event.target.value)} placeholder="https://example.com/v1" /></label> : null}
        <label className="field"><span>API 密钥</span><input type="password" autoComplete="off" value={secret} disabled={saving} onChange={event => setSecret(event.target.value)} maxLength={4096} placeholder="仅保存在 Windows 安全凭据存储" /></label>
      </div>
      <details className="model-advanced"><summary>高级设置：可信 Token 上界（必填）</summary><p className="inline-hint">请按所选模型的官方说明填写单次请求可能计费的输入上限和允许的输出上限。系统会在每次调用前保守预留；没有可信上界就不会启动模型请求。</p><div className="model-setup-fields"><label className="field"><span>单次输入 Token 上界</span><input type="number" min="1" max="1000000" step="1" value={inputLimit} disabled={saving} onChange={event => setInputLimit(event.target.value)} /></label><label className="field"><span>单次输出 Token 上界</span><input type="number" min="1" max="100000" step="1" value={outputLimit} disabled={saving} onChange={event => setOutputLimit(event.target.value)} /></label></div></details>
      <div className="group-actions"><button type="submit" className="primary-button" disabled={!valid || saving}>{saving ? "正在保存并重启核心…" : "保存模型设置"}</button></div>
      <p className="inline-hint">保存后核心会重新启动，页面自动连接。不会测试密钥有效性，也不会在设置时产生模型费用。</p>
    </form> : null}
    {status === "unconfigured" && !isTauri() ? <p className="inline-hint">当前浏览器开发入口不保存模型密钥。请在桌面应用完成首次设置。</p> : null}
  </section>;
}
