import { useEffect, useId, useState, type FormEvent } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { type CoreClient, type LLMRuntimeStatus } from "@dreamtalk/api-client";

import { findModelPreset, modelPresets, presetsReviewedAt, type ProviderKind } from "./modelPresets";
type ChatModelSetup = {
  provider_kind: ProviderKind;
  model_id: string;
  base_url: string | null;
  max_billable_input_tokens: number;
  max_output_tokens: number;
  streaming?: boolean;
  timeout_ms?: number;
  native_json?: boolean;
  inherited?: boolean;
};
type ModelUpdateOutcome = { old_credential_cleanup_incomplete: boolean };
const cleanupWarningKey = "dreamtalk-model-cleanup-warning";
type SetupField = "model_id" | "base_url" | "secret" | "input_limit" | "output_limit" | "timeout";
const setupFields: SetupField[] = ["model_id", "base_url", "secret", "input_limit", "output_limit", "timeout"];
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
  ready: "模型和凭据已就绪。聊天或联网生成时才会实际联系提供商。",
  partially_configured: "部分模型缺少凭据。请检查现有高级模型配置。",
  unconfigured: "尚未配置聊天模型。完成首次设置后才能向角色发送消息。",
  degraded: "模型配置或凭据状态异常。世界和已有聊天记录仍可使用。",
};

export type ModelSetupSummary = { status: LLMRuntimeStatus | null; model: string | null; replyTokens: number | null };

export function ModelSetup({ client, worldId, turnTokenCeiling, onConfigured = () => window.location.reload(), onDirtyChange, onSummaryChange }: {
  client: CoreClient;
  worldId?: string;
  turnTokenCeiling?: number;
  onConfigured?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  onSummaryChange?: (summary: ModelSetupSummary) => void;
}) {
  const [status, setStatus] = useState<LLMRuntimeStatus | null>(null);
  const [managed, setManaged] = useState<ChatModelSetup | null>(null);
  const [managedUnsupported, setManagedUnsupported] = useState(false);
  const [advancedDefault, setAdvancedDefault] = useState(false);
  const [inherited, setInherited] = useState(Boolean(worldId));
  const scopedWarningKey = worldId ? `${cleanupWarningKey}:${worldId}` : cleanupWarningKey;
  useEffect(() => { onSummaryChange?.({ status, model: managed?.model_id ?? null, replyTokens: managed?.max_output_tokens ?? null }); }, [status, managed, onSummaryChange]);
  const [providerKind, setProviderKind] = useState<ProviderKind>("openai-responses");
  const [modelId, setModelId] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [inputLimit, setInputLimit] = useState("");
  const [outputLimit, setOutputLimit] = useState("8192");
  const [replyLength, setReplyLength] = useState("8192");
  const [manualLimits, setManualLimits] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [streaming, setStreaming] = useState(true);
  const [timeoutSeconds, setTimeoutSeconds] = useState("30");
  const [nativeJson, setNativeJson] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  useEffect(() => { onDirtyChange?.(dirty || saving); }, [dirty, saving, onDirtyChange]);
  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const formId = useId();

  const [error, setError] = useState(() => {
    try {
      const warning = window.sessionStorage.getItem(scopedWarningKey);
      window.sessionStorage.removeItem(scopedWarningKey);
      return warning ?? "";
    } catch { return ""; }
  });

  useEffect(() => {
    let active = true;
    void client.health(undefined, worldId).then(async health => {
      if (!active) return;
      setStatus(health.llm_status);
      if (!isTauri()) return;
      try {
        const existing = await invoke<ChatModelSetup | null>("managed_chat_model_setup", { worldId: worldId ?? null });
        if (!active || !existing) return;
        setManaged(existing);
        setInherited(existing.inherited ?? Boolean(worldId));
        setStreaming(existing.streaming ?? false);
        setTimeoutSeconds(String((existing.timeout_ms ?? 30_000) / 1000));
        setNativeJson(existing.native_json ?? false);
        setProviderKind(existing.provider_kind);
        setModelId(existing.model_id);
        setBaseUrl(existing.base_url ?? "");
        setInputLimit(String(existing.max_billable_input_tokens));
        setOutputLimit(String(existing.max_output_tokens));
        setReplyLength([2048, 8192, 16384].includes(existing.max_output_tokens) ? String(existing.max_output_tokens) : "custom");
        const preset = findModelPreset(existing.provider_kind, existing.model_id, existing.base_url ?? "");
        const manual = !preset || preset.input_tokens !== existing.max_billable_input_tokens;
        setManualLimits(manual);
        setAdvancedOpen(manual || ![2048, 8192, 16384].includes(existing.max_output_tokens)
          || Boolean(existing.native_json) || (existing.timeout_ms ?? 30_000) !== 30_000);
      } catch (failure) {
        if (active) {
          if (worldId && failure === "model_world_inherits_advanced_default") setAdvancedDefault(true);
          else {
            if (worldId && failure === "model_world_has_advanced_configuration") setInherited(false);
            setManagedUnsupported(true);
          }
        }
      }
    }).catch(() => { if (active) setError("无法读取模型状态，请检查核心连接。"); });
    return () => { active = false; };
  }, [client, worldId]);

  const preset = findModelPreset(providerKind, modelId, baseUrl);
  const inputBound = preset && !manualLimits ? preset.input_tokens : Number(inputLimit);
  const requestBoundAvailable = providerKind === "openai-responses" || Boolean(preset?.bound_encoding);
  const outputBound = Number(replyLength === "custom" ? outputLimit : replyLength);
  const outputMaximum = preset?.output_tokens ?? 1_000_000;
  const resetCapacity = () => { setManualLimits(false); setInputLimit(""); setNativeJson(false); };
  const rawTimeoutMs = Number(timeoutSeconds) * 1000;
  const timeoutMs = Math.round(rawTimeoutMs);
  const editing = managed !== null;
  const endpointChanged = providerKind === "openai-compatible"
    && baseUrl.replace(/\/+$/, "") !== (managed?.base_url ?? "").replace(/\/+$/, "");
  const secretRequired = !editing || status !== "ready" || providerKind !== managed?.provider_kind || endpointChanged;
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
  if (!Number.isSafeInteger(inputBound) || inputBound < 1 || inputBound > 10_000_000) {
    validationErrors.input_limit = "请在高级设置填写模型的输入容量（1 至 10,000,000 的整数），或选择已匹配的模型。";
  }
  if (!Number.isSafeInteger(outputBound) || outputBound < 1 || outputBound > outputMaximum) {
    validationErrors.output_limit = `回复长度必须是 1 至 ${outputMaximum.toLocaleString("zh-CN")} 之间的整数。`;
  }
  if (!Number.isSafeInteger(timeoutMs) || Math.abs(rawTimeoutMs - timeoutMs) > 0.000001
    || timeoutMs < 1000 || timeoutMs > 600_000) {
    validationErrors.timeout = "请求超时必须为 1 至 600 秒，最多保留三位小数。";
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
      const form = event.currentTarget;
      if (["input_limit", "output_limit", "timeout"].includes(firstInvalidField)) {
        setAdvancedOpen(true);
        if (firstInvalidField === "output_limit") setReplyLength("custom");
      }
      requestAnimationFrame(() => {
        const input = form.elements.namedItem(firstInvalidField);
        if (input instanceof HTMLElement) input.focus();
      });
      return;
    }
    if (!isTauri() || (status !== "unconfigured" && !editing && !advancedDefault)) {
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
          timeout_ms: timeoutMs,
          native_json: nativeJson,
        },
        secret,
        streaming,
        worldId: worldId ?? null,
      });
      setSecret("");
      if (outcome?.old_credential_cleanup_incomplete) {
        try { window.sessionStorage.setItem(scopedWarningKey, "模型已更新，但旧凭据未能从 Windows 安全凭据存储清理。请检查本机凭据存储。"); } catch { /* The update remains committed. */ }
      }
      setDirty(false);
      onConfigured();
    } catch (failure) {
      if (failure === "secure_storage_unavailable") setError("Windows 安全凭据存储不可用，密钥未保存。");
      else if (failure === "model_edit_requires_managed_single_chat_configuration") setError("当前模型配置含有高级设置，不能从此页面覆盖。");
      else if (failure === "model_update_new_secret_required") setError("更换提供商、服务地址或补齐缺失凭据时，请填写新 API 密钥。");
      else if (failure === "model_setup_requires_empty_configuration") setError("模型状态已变化，请重新打开设置页面后再编辑。已有配置未被覆盖。");
      else if (failure === "model_setup_recovery_failed") setError("模型更新和恢复均未完成。请重启应用后检查模型状态。");
      else setError("模型设置未完成。请核对模型名称、服务地址和回复长度，或重新启动程序后重试。");
    } finally { setSaving(false); }
  };

  const restoreDefault = async () => {
    if (!worldId || !isTauri() || saving || inherited) return;
    setSaving(true);
    setError("");
    try {
      const outcome = await invoke<ModelUpdateOutcome>("use_default_chat_model", { worldId });
      if (outcome.old_credential_cleanup_incomplete) {
        try { window.sessionStorage.setItem(scopedWarningKey, "已恢复默认模型，但旧凭据清理未完成。请检查本机凭据存储。"); } catch { /* The configuration is already saved. */ }
      }
      setSecret("");
      setDirty(false);
      onConfigured();
    } catch (failure) {
      setError(failure === "model_setup_recovery_failed"
        ? "恢复默认模型和恢复原配置均未完成。请重启应用后检查模型状态。"
        : "未能恢复默认模型，请检查核心连接后重试；本次失败会尝试恢复原配置。");
    }
    finally { setSaving(false); }
  };

  return <section className="settings-section model-setup" aria-label="聊天模型">
    <div className="section-heading"><h2>{worldId ? "当前世界模型" : "默认模型配置"}</h2><p>{status === null ? "正在读取模型状态…" : statusText[status]}</p></div>
    <p className="inline-hint">{worldId
      ? inherited ? "当前使用书架默认配置。保存后成为这个世界的独立配置，不会修改书架默认配置或其他世界。" : "当前世界使用独立配置。API、模型、密钥、容量、超时和流式设置只用于这个世界。"
      : "这里保存书架默认配置，供尚未单独设置的世界使用。已保存独立配置的世界不受这里的修改影响。"}</p>
    {worldId && !inherited && isTauri() ? <div className="group-actions"><button type="button" className="secondary-button" disabled={saving} onClick={() => void restoreDefault()}>恢复使用书架默认配置</button></div> : null}
    {error ? <p className="app-alert" role="alert">{error}</p> : null}
    {managedUnsupported && status !== "unconfigured" ? <p className="inline-hint">当前配置由高级方式管理；此处不会覆盖其中的路由、定价或其他设置。</p> : null}
    {advancedDefault ? <p className="inline-hint">书架默认配置由高级方式管理。下方可以为当前世界另建独立模型配置，原默认配置会保留。</p> : null}
    {turnTokenCeiling !== undefined && !requestBoundAvailable && Number.isSafeInteger(inputBound) && inputBound > 0 && inputBound + outputBound > turnTokenCeiling && (editing || advancedDefault || status === "unconfigured") ? <p className="compatibility-notice" role="status">此服务的一次调用需要预留 {inputBound.toLocaleString("zh-CN")} Token 输入。当前每轮额度为 {turnTokenCeiling.toLocaleString("zh-CN")}；至少 {(inputBound + 1).toLocaleString("zh-CN")} 才能留出输出空间，{Number.isSafeInteger(outputBound) && outputBound > 0 ? `预留一次完整回复需 ${(inputBound + outputBound).toLocaleString("zh-CN")}。` : ""} 群聊选人、多角色发言及重试仍共用整轮额度，需要更多余量。模型设置仍可保存。容量预留不代表实际发送量；请按官方说明填写，勿为通过检查虚填较低值。</p> : null}
    {isTauri() && status !== null && status !== "degraded" && !managedUnsupported && (status === "unconfigured" || editing || advancedDefault) ? <form noValidate aria-busy={saving} onChangeCapture={() => setDirty(true)} onSubmit={event => void save(event)}>
      {submitAttempted && firstInvalidField ? <p className="app-alert" role="alert">尚未保存：{validationErrors[firstInvalidField]} 请修改标红的字段后再保存。</p> : null}
      <div className="model-setup-fields">
        <label className="field"><span>提供商</span><select value={providerKind} disabled={saving} onChange={event => { setProviderKind(event.target.value as ProviderKind); resetCapacity(); }}><option value="openai-responses">OpenAI</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option><option value="openai-compatible">兼容 Chat Completions 的服务</option></select></label>
        <div className="field">
          <label htmlFor={`${formId}-model_id`}>模型名称</label>
          <input id={`${formId}-model_id`} name="model_id" value={modelId} disabled={saving} onChange={event => { setModelId(event.target.value); resetCapacity(); }} list={`${formId}-models`} maxLength={128} placeholder="提供商给出的 API 模型 ID" aria-invalid={Boolean(fieldError("model_id"))} aria-describedby={`${formId}-model-hint${fieldError("model_id") ? ` ${formId}-model_id-error` : ""}`} />
          <span id={`${formId}-model-hint`} className="model-field-hint">填写 API 模型 ID，不是品牌名称；名称不能含空格。</span>
          {fieldFeedback("model_id")}
          <datalist id={`${formId}-models`}>{modelPresets.filter(item => item.provider_kind === providerKind).map(item => <option key={item.model_id} value={item.model_id} />)}</datalist>
        </div>
        {providerKind === "openai-compatible" ? <div className="field">
          <label htmlFor={`${formId}-base_url`}>服务地址</label>
          <input id={`${formId}-base_url`} name="base_url" type="url" value={baseUrl} disabled={saving} onChange={event => { setBaseUrl(event.target.value); resetCapacity(); }} placeholder="https://example.com/v1" aria-invalid={Boolean(fieldError("base_url"))} aria-describedby={fieldError("base_url") ? `${formId}-base_url-error` : undefined} />
          {fieldFeedback("base_url")}
          <span className="model-field-hint">Kimi、GLM 等提供兼容接口的服务可在这里接入。填写控制台给出的基础地址（不含 /chat/completions）、准确模型 ID 和对应 API 密钥；未匹配的型号还需在高级设置核对输入容量。</span>
        </div> : null}
        <div className="field">
          <label htmlFor={`${formId}-secret`}>{secretRequired ? "API 密钥" : "新 API 密钥（可留空）"}</label>
          <input id={`${formId}-secret`} name="secret" type="password" autoComplete="off" value={secret} disabled={saving} onChange={event => setSecret(event.target.value)} maxLength={4096} placeholder={secretRequired ? "仅保存在 Windows 安全凭据存储" : "留空则沿用现有密钥；不会显示现有密钥"} aria-invalid={Boolean(fieldError("secret"))} aria-describedby={fieldError("secret") ? `${formId}-secret-error` : undefined} />
          {fieldFeedback("secret")}
        </div>
      </div>
      <div className="model-limits">
        <label className="streaming-setting"><input type="checkbox" checked={streaming} disabled={saving} onChange={event => setStreaming(event.target.checked)} />逐步显示回复</label>
        <p className="inline-hint">启用后，角色回答会逐步显示，可以停止生成。兼容服务需支持流式输出及用量返回；若服务不支持，可关闭后保存。失败不会自动重新调用模型。</p>
        <h3>回复长度</h3>
        <label className="field"><span>单次回复上限</span><select name="reply_length" value={replyLength} disabled={saving} onChange={event => { setReplyLength(event.target.value); if (event.target.value === "custom") setAdvancedOpen(true); }}>
          <option value="2048">简短 · 2,048 Token</option><option value="8192">标准 · 8,192 Token</option><option value="16384">较长 · 16,384 Token</option><option value="custom">自定义</option>
        </select></label>
        <p className="inline-hint">这是回复可用的最多 Token，不是每次固定用量。推理模型的思考也会占用此额度；聊天仍受每轮总额度约束。</p>
        {preset ? <p className="inline-hint">已匹配模型容量：上下文 {preset.context_tokens.toLocaleString("zh-CN")} Token，模型输出最多 {preset.output_tokens.toLocaleString("zh-CN")} Token。资料核对日期：{presetsReviewedAt}。{requestBoundAvailable ? "聊天按当前对话预留输入额度；无法核对时采用模型容量保守预留。" : "此服务暂按模型输入容量保守预留聊天额度。"}</p> : <p className="compatibility-notice">尚未匹配此服务与模型，请在高级设置按提供商文档填写输入容量。模型 ID 相同的第三方服务也需要单独核对。</p>}
        <details open={advancedOpen} onToggle={event => setAdvancedOpen(event.currentTarget.open)}>
          <summary>高级设置：容量、超时与结构化输出</summary>
          {preset ? <label className="field"><span>输入容量来源</span><select disabled={saving} value={manualLimits ? "manual" : "auto"} onChange={event => { setManualLimits(event.target.value === "manual"); if (!inputLimit) setInputLimit(String(preset.input_tokens)); }}><option value="auto">自动匹配</option><option value="manual">手动指定（保留自定义值）</option></select></label> : null}
          <div className="model-setup-fields">
            <div className="field">
              <label htmlFor={`${formId}-input_limit`}>模型输入容量</label>
              <input id={`${formId}-input_limit`} name="input_limit" type="number" min="1" max="10000000" step="1" value={preset && !manualLimits ? preset.input_tokens : inputLimit} disabled={saving || Boolean(preset && !manualLimits)} onChange={event => setInputLimit(event.target.value)} aria-invalid={Boolean(fieldError("input_limit"))} aria-describedby={fieldError("input_limit") ? `${formId}-input_limit-error` : undefined} />
              {fieldFeedback("input_limit")}
            </div>
            {replyLength === "custom" ? <div className="field">
              <label htmlFor={`${formId}-output_limit`}>自定义回复上限</label>
              <input id={`${formId}-output_limit`} name="output_limit" type="number" min="1" max={outputMaximum} step="1" value={outputLimit} disabled={saving} onChange={event => setOutputLimit(event.target.value)} aria-invalid={Boolean(fieldError("output_limit"))} aria-describedby={fieldError("output_limit") ? `${formId}-output_limit-error` : undefined} />
              {fieldFeedback("output_limit")}
            </div> : null}
            <div className="field">
              <label htmlFor={`${formId}-timeout`}>请求超时（秒）</label>
              <input id={`${formId}-timeout`} name="timeout" type="number" min="1" max="600" step="0.001" value={timeoutSeconds} disabled={saving} onChange={event => setTimeoutSeconds(event.target.value)} aria-invalid={Boolean(fieldError("timeout"))} aria-describedby={`${formId}-timeout-hint${fieldError("timeout") ? ` ${formId}-timeout-error` : ""}`} />
              <span id={`${formId}-timeout-hint`} className="model-field-hint">默认 30 秒。模型思考较慢时可适当增加；超时后不会自动重发。</span>
              {fieldFeedback("timeout")}
            </div>
          </div>
          <label className="streaming-setting"><input type="checkbox" checked={nativeJson} disabled={saving} onChange={event => setNativeJson(event.target.checked)} />该模型支持原生 JSON Schema（按厂商文档确认）</label>
          <p className="inline-hint">开启后，主动联系和世界动态使用原生结构化输出，结果仍须通过本地校验。第三方代理与具体模型需分别确认；不支持时可关闭，沿用提示约束与本地校验。普通聊天可在同次回复中附带记忆和事件，不需要开启此项，也不额外调用模型。</p>
          <p className="inline-hint">手动输入容量必须按提供商文档核对。没有可靠请求上界的服务仍按此容量预留；请勿为了通过额度检查填写更小的数值。</p>
        </details>
      </div>
      <div className="group-actions"><button type="submit" className="primary-button" disabled={saving}>{saving ? "正在保存并重启核心…" : worldId ? "保存当前世界模型" : editing ? "更新默认模型配置" : "保存默认模型配置"}</button></div>
      <p className="inline-hint">保存后核心会重新启动，页面自动连接。不会测试密钥有效性，也不会在设置时产生模型费用。更新失败时会恢复原配置。</p>
    </form> : null}
    {status === "unconfigured" && !isTauri() ? <p className="inline-hint">当前浏览器开发入口不保存模型密钥。请在桌面应用完成首次设置。</p> : null}
  </section>;
}
