import { useEffect, useId, useState, type FormEvent } from "react";
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
type SetupField = "model_id" | "base_url" | "secret" | "input_limit" | "output_limit";
const setupFields: SetupField[] = ["model_id", "base_url", "secret", "input_limit", "output_limit"];
const byteLength = (value: string) => new TextEncoder().encode(value).length;

function validServiceUrl(value: string): boolean {
  if (/\s/.test(value) || value.includes("\\") || value.includes("?") || value.includes("#") || !/^https?:\/\//i.test(value)) return false;
  try {
    const url = new URL(value);
    return Boolean(url.hostname) && !url.username && !url.password && !url.search && !url.hash
      && (url.protocol === "https:" || (url.protocol === "http:"
        && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)));
  } catch { return false; }
}

const statusText: Record<LLMRuntimeStatus, string> = {
  ready: "模型和凭据已就绪。首次聊天时才会实际联系提供商。",
  partially_configured: "部分模型缺少凭据。请检查现有高级模型配置。",
  unconfigured: "尚未配置聊天模型。完成首次设置后才能向角色发送消息。",
  degraded: "模型配置或凭据状态异常。世界和已有聊天记录仍可使用。",
};

export function ModelSetup({ client, turnTokenCeiling, onConfigured = () => window.location.reload() }: {
  client: CoreClient;
  turnTokenCeiling?: number;
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
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const formId = useId();

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
  const validationErrors: Partial<Record<SetupField, string>> = {};
  if (!modelId) validationErrors.model_id = "请填写提供商的 API 模型 ID。";
  else if (/\s/.test(modelId) || Array.from(modelId).some(character => {
    const code = character.codePointAt(0)!;
    return code <= 31 || (code >= 127 && code <= 159);
  })) validationErrors.model_id = "模型名称不能含空格或控制字符。请填写完整 API 模型 ID，而不是品牌名称。";
  else if (byteLength(modelId) > 128) validationErrors.model_id = "模型名称过长，请核对提供商的 API 模型 ID（最多 128 字节）。";
  if (providerKind === "openai-compatible" && !validServiceUrl(baseUrl)) {
    validationErrors.base_url = "请填写完整 HTTPS 服务地址；本机服务可用 HTTP。地址不能含空格、密钥、查询参数或片段。";
  }
  if (secretRequired && !secret.trim()) validationErrors.secret = "请填写 API 密钥。";
  else if (byteLength(secret) > 4096) validationErrors.secret = "API 密钥过长，请重新复制提供商给出的密钥。";
  if (!Number.isSafeInteger(inputBound) || inputBound < 1 || inputBound > 1_000_000) {
    validationErrors.input_limit = "请填写 1 至 1,000,000 之间的整数输入上限，并按模型官方说明核对。";
  }
  if (!Number.isSafeInteger(outputBound) || outputBound < 1 || outputBound > 100_000) {
    validationErrors.output_limit = "请填写 1 至 100,000 之间的整数输出上限，并按模型官方说明核对。";
  }
  const firstInvalidField = setupFields.find(field => validationErrors[field]);
  const fieldError = (field: SetupField) => submitAttempted ? validationErrors[field] : undefined;
  const fieldFeedback = (field: SetupField) => fieldError(field)
    ? <span id={`${formId}-${field}-error`} className="model-field-error">{fieldError(field)}</span> : null;

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving) return;
    setSubmitAttempted(true);
    setError("");
    if (firstInvalidField) {
      const input = event.currentTarget.elements.namedItem(firstInvalidField);
      if (input instanceof HTMLElement) input.focus();
      return;
    }
    if (!isTauri() || (status !== "unconfigured" && !editing)) {
      setError("当前无法保存模型设置，请重新打开桌面应用的设置页面。");
      return;
    }
    setSaving(true);
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
      else if (failure === "model_setup_requires_empty_configuration") setError("模型状态已变化，请重新打开设置页面后再编辑。已有配置未被覆盖。");
      else if (failure === "model_setup_recovery_failed") setError("模型更新和恢复均未完成。请重启应用后检查模型状态。");
      else setError("模型设置未完成。请核对模型名称、服务地址和可信 Token 上界，或重新启动程序后重试。");
    } finally { setSaving(false); }
  };

  return <section className="settings-section model-setup" aria-label="聊天模型">
    <div className="section-heading"><h2>聊天模型</h2><p>{status === null ? "正在读取模型状态…" : statusText[status]}</p></div>
    {error ? <p className="app-alert" role="alert">{error}</p> : null}
    {managedUnsupported && status !== "unconfigured" ? <p className="inline-hint">当前配置由高级方式管理；此处不会覆盖其中的路由、定价或其他设置。</p> : null}
    {turnTokenCeiling !== undefined && inputBound >= turnTokenCeiling && (editing || status === "unconfigured") ? <p className="compatibility-notice" role="status">当前每轮 {turnTokenCeiling.toLocaleString("zh-CN")} Token 额度无法容纳 {inputBound.toLocaleString("zh-CN")} Token 输入预留与回复。聊天额度至少需 {(inputBound + 1).toLocaleString("zh-CN")}；{Number.isSafeInteger(outputBound) && outputBound > 0 ? `建议设置为 ${(inputBound + outputBound).toLocaleString("zh-CN")}，预留一次完整回复。` : ""} 模型设置仍可保存。输入预留使用填写的可信上界，不代表实际发送量；请按官方说明填写，勿为通过检查虚填较低值。</p> : null}
    {isTauri() && (status === "unconfigured" || (editing && !managedUnsupported)) ? <form noValidate aria-busy={saving} onSubmit={event => void save(event)}>
      {submitAttempted && firstInvalidField ? <p className="app-alert" role="alert">尚未保存：{validationErrors[firstInvalidField]} 请修改标红的字段后再保存。</p> : null}
      <div className="model-setup-fields">
        <label className="field"><span>提供商</span><select value={providerKind} disabled={saving} onChange={event => setProviderKind(event.target.value as ProviderKind)}><option value="openai-responses">OpenAI</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option><option value="openai-compatible">兼容 Chat Completions 的服务</option></select></label>
        <div className="field">
          <label htmlFor={`${formId}-model_id`}>模型名称</label>
          <input id={`${formId}-model_id`} name="model_id" value={modelId} disabled={saving} onChange={event => setModelId(event.target.value)} maxLength={128} placeholder="提供商给出的 API 模型 ID" aria-invalid={Boolean(fieldError("model_id"))} aria-describedby={`${formId}-model-hint${fieldError("model_id") ? ` ${formId}-model_id-error` : ""}`} />
          <span id={`${formId}-model-hint`} className="model-field-hint">填写 API 模型 ID，不是品牌名称；名称不能含空格。</span>
          {fieldFeedback("model_id")}
        </div>
        {providerKind === "openai-compatible" ? <div className="field">
          <label htmlFor={`${formId}-base_url`}>服务地址</label>
          <input id={`${formId}-base_url`} name="base_url" type="url" value={baseUrl} disabled={saving} onChange={event => setBaseUrl(event.target.value)} placeholder="https://example.com/v1" aria-invalid={Boolean(fieldError("base_url"))} aria-describedby={fieldError("base_url") ? `${formId}-base_url-error` : undefined} />
          {fieldFeedback("base_url")}
        </div> : null}
        <div className="field">
          <label htmlFor={`${formId}-secret`}>{secretRequired ? "API 密钥" : "新 API 密钥（可留空）"}</label>
          <input id={`${formId}-secret`} name="secret" type="password" autoComplete="off" value={secret} disabled={saving} onChange={event => setSecret(event.target.value)} maxLength={4096} placeholder={secretRequired ? "仅保存在 Windows 安全凭据存储" : "留空则沿用现有密钥；不会显示现有密钥"} aria-invalid={Boolean(fieldError("secret"))} aria-describedby={fieldError("secret") ? `${formId}-secret-error` : undefined} />
          {fieldFeedback("secret")}
        </div>
      </div>
      <div className="model-limits">
        <h3>模型 Token 上限（必填）</h3>
        <p className="inline-hint">输入上限按模型官方说明填写；输出上限是本应用允许单次回复使用的上限，不得超过模型限制。系统会据此预留聊天额度，不会自动填入未经核实的数值。</p>
        <div className="model-setup-fields">
          <div className="field">
            <label htmlFor={`${formId}-input_limit`}>单次输入 Token 上界</label>
            <input id={`${formId}-input_limit`} name="input_limit" type="number" min="1" max="1000000" step="1" value={inputLimit} disabled={saving} onChange={event => setInputLimit(event.target.value)} aria-invalid={Boolean(fieldError("input_limit"))} aria-describedby={fieldError("input_limit") ? `${formId}-input_limit-error` : undefined} />
            {fieldFeedback("input_limit")}
          </div>
          <div className="field">
            <label htmlFor={`${formId}-output_limit`}>单次输出 Token 上界</label>
            <input id={`${formId}-output_limit`} name="output_limit" type="number" min="1" max="100000" step="1" value={outputLimit} disabled={saving} onChange={event => setOutputLimit(event.target.value)} aria-invalid={Boolean(fieldError("output_limit"))} aria-describedby={fieldError("output_limit") ? `${formId}-output_limit-error` : undefined} />
            {fieldFeedback("output_limit")}
          </div>
        </div>
      </div>
      <div className="group-actions"><button type="submit" className="primary-button" disabled={saving}>{saving ? "正在保存并重启核心…" : editing ? "更新模型设置" : "保存模型设置"}</button></div>
      <p className="inline-hint">保存后核心会重新启动，页面自动连接。不会测试密钥有效性，也不会在设置时产生模型费用。更新失败时会恢复原配置。</p>
    </form> : null}
    {status === "unconfigured" && !isTauri() ? <p className="inline-hint">当前浏览器开发入口不保存模型密钥。请在桌面应用完成首次设置。</p> : null}
  </section>;
}
