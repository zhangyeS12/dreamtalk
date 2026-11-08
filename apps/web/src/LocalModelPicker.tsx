import { invoke, isTauri } from "@tauri-apps/api/core";
import { useEffect, useId, useRef, useState } from "react";

export interface LocalModelCatalog {
  models: { id: string; name: string }[];
  selected: string | null;
  complete: boolean;
}

export function LocalModelPicker({ kind, value, endpoint, onChange, onCatalog, disabled = false, refreshKey = 0 }: {
  kind: "vision" | "speech";
  value: string;
  endpoint?: string;
  onChange: (id: string) => void;
  onCatalog?: (catalog: LocalModelCatalog) => void;
  disabled?: boolean;
  refreshKey?: number;
}) {
  const id = useId();
  const requestKey = JSON.stringify([kind, endpoint, refreshKey]);
  const [loaded, setLoaded] = useState<{ key: string; catalog: LocalModelCatalog } | null>(null);
  const catalog = loaded?.key === requestKey ? loaded.catalog : null;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const latest = useRef({ value, onChange, onCatalog });
  latest.current = { value, onChange, onCatalog };
  useEffect(() => {
    let active = true;
    setLoaded(null); setError("");
    if (!isTauri()) { setLoading(false); setError("请在桌面版中选择本地模型。"); return; }
    setLoading(true);
    const request = kind === "vision"
      ? invoke<LocalModelCatalog>("local_image_models", { endpoint })
      : invoke<LocalModelCatalog>("local_speech_models");
    void request.then(result => {
      if (!active) return;
      setLoaded({ key: requestKey, catalog: result });
      latest.current.onCatalog?.(result);
    }).catch(() => {
      if (active) setError(kind === "vision"
        ? "暂时无法读取视觉模型，已保留原选择。可检查并启动图片服务后刷新。"
        : "暂时无法读取配音模型，已保留原选择。可选择已部署的模型目录后刷新。");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [kind, endpoint, refresh, refreshKey, requestKey]);
  useEffect(() => {
    // Only choose in the draft, never during a save or after an endpoint switch.
    if (!disabled && kind === "vision" && !value && catalog?.complete && catalog.models.length === 1) {
      latest.current.onChange(catalog.models[0].id);
    }
  }, [catalog, kind, value, disabled]);
  const selected = value || (kind === "speech" ? catalog?.selected ?? "" : "");
  const missing = selected && !catalog?.models.some(model => model.id === selected);
  const label = kind === "vision" ? "本地视觉模型" : "本地配音模型";
  return <div className="local-model-picker">
    <label className="field" htmlFor={id}><span id={`${id}-label`}>{label}</span>
      <select id={id} aria-labelledby={`${id}-label`} aria-describedby={`${id}-help`} value={selected}
        disabled={disabled || loading || !catalog?.models.length}
        onChange={event => onChange(event.target.value)}>
        <option value="">{loading ? "正在读取模型…" : catalog?.models.length ? "选择已部署模型" : "尚未发现可用模型"}</option>
        {missing && <option value={selected}>{kind === "vision" ? selected : "已保存的 IndexTTS 2.5 部署"}（暂未检测到）</option>}
        {catalog?.models.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}
      </select>
    </label>
    <button type="button" className="text-action" disabled={disabled || loading || !isTauri()} onClick={() => setRefresh(value => value + 1)}>{loading ? "正在读取…" : "刷新模型列表"}</button>
    <p id={`${id}-help`} className="inline-hint">{kind === "vision" ? "仅列出已安装并确认支持识图的本地模型。唯一可用模型会自动选中，保存设置后生效。" : "当前支持 IndexTTS 2.5；选择的部署为整机共用，开启配音并保存后使用。当前世界的配音开关和角色音色独立保存。"} 刷新不会加载模型、识图或生成配音。</p>
    {error && <p role="status" className="app-alert">{error}</p>}
    {catalog && !catalog.complete && <p role="status" className="inline-hint">部分模型信息尚未读取完整，已保留原选择，可稍后刷新。</p>}
  </div>;
}
