import { invoke, isTauri } from "@tauri-apps/api/core";
import { useEffect, useRef, useState } from "react";
import { CoreClient, type VoiceCard, type VoiceCardPage, type VoiceCardPreview } from "@dreamtalk/api-client";
import { useDesktopUpdateBlock } from "./DesktopUpdates";
import { speechFailure } from "./SpeechPlayback";

export function CharacterVoice({ client, worldId, root, name, visible = true, onDirtyChange }: { client: CoreClient; worldId: string; root: string; name: string; visible?: boolean; onDirtyChange?: (dirty: boolean) => void }) {
  const [page, setPage] = useState<VoiceCardPage | null>(null), [offset, setOffset] = useState(0);
  const [binding, setBinding] = useState<string | null>(null), [chosen, setChosen] = useState("");
  const [source, setSource] = useState<File | null>(null), [cardName, setCardName] = useState(name + "的音色");
  const [preview, setPreview] = useState<VoiceCardPreview | null>(null), [busy, setBusy] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [refresh, setRefresh] = useState(0);
  const [sample, setSample] = useState<string | null>(null);
  const sampleUrl = useRef<string | null>(null), sampleAudio = useRef<HTMLAudioElement>(null), lock = useRef(false), lifetime = useRef(new AbortController());
  const shown = useRef(visible); shown.current = visible;
  const dirty = !!source || chosen !== (binding ?? "");
  useDesktopUpdateBlock(busy ? "正在处理音色卡。" : dirty ? "角色音色尚未确认。" : null);
  useEffect(() => { onDirtyChange?.(dirty || busy); return () => onDirtyChange?.(false); }, [dirty, busy, onDirtyChange]);
  useEffect(() => {
    if (visible) return;
    sampleAudio.current?.pause();
    if (sampleUrl.current) URL.revokeObjectURL(sampleUrl.current);
    sampleUrl.current = null; setSample(null);
  }, [visible]);
  useEffect(() => {
    lifetime.current = new AbortController();
    return () => { lifetime.current.abort(); if (sampleUrl.current) URL.revokeObjectURL(sampleUrl.current); };
  }, []);
  useEffect(() => {
    let active = true;
    void Promise.all([client.voiceCards(worldId, offset), client.voiceBinding(worldId, root)]).then(([cards, bound]) => {
      if (active) { setPage(cards); setBinding(bound.card_id); setChosen(bound.card_id ?? ""); }
    }).catch(failure => { if (active) setError(speechFailure(failure)); });
    return () => { active = false; };
  }, [client, worldId, root, offset, refresh]);
  const run = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(); }
    catch (failure) { if (!lifetime.current.signal.aborted) setError(speechFailure(failure)); }
    finally { lock.current = false; if (!lifetime.current.signal.aborted) setBusy(false); }
  };
  const chooseFile = (file?: File) => {
    if (!file) return;
    setSource(null); setPreview(null);
    if (file.size > 10 * 1024 * 1024 + 32768 || !/\.(wav|mp3|voicecard)$/i.test(file.name)) {
      setError("请选择不超过 10 MB 的 WAV／MP3 或 .voicecard 音色卡。"); return;
    }
    const title = file.name.replace(/\.[^.]+$/, "").slice(0, 64) || name + "的音色";
    setSource(file); setCardName(title); setError("");
    void run(async () => { const value = await client.previewVoiceCard(worldId, file, title); if (!lifetime.current.signal.aborted) setPreview(value); });
  };
  const importCard = () => void run(async () => {
    if (!source || !preview) return;
    const card = await client.importVoiceCard(worldId, source, cardName);
    await client.bindVoice(worldId, root, card.card_id);
    if (lifetime.current.signal.aborted) return;
    setBinding(card.card_id); setChosen(card.card_id); setSource(null); setPreview(null);
    setRefresh(value => value + 1); setNotice("音色卡已导入，并绑定给“" + name + "”。");
  });
  const selected = page?.items.find(item => item.card_id === chosen);
  const listen = () => void run(async () => {
    if (!chosen) return;
    const blob = await client.voiceReference(worldId, chosen, lifetime.current.signal);
    if (lifetime.current.signal.aborted || !shown.current) return;
    if (sampleUrl.current) URL.revokeObjectURL(sampleUrl.current);
    sampleUrl.current = URL.createObjectURL(blob); setSample(sampleUrl.current);
  });
  const exportCard = () => void run(async () => {
    if (!chosen) return;
    const filename = Array.from(selected?.manifest.name ?? "角色音色").map(char => char.charCodeAt(0) < 32 || '<>:"/\\|?*'.includes(char) ? "_" : char).join("") + ".voicecard";
    if (isTauri()) {
      const destination = await invoke<string | null>("save_file_export", { request: { kind: "voice", world_id: worldId, item_id: chosen }, filename });
      if (!lifetime.current.signal.aborted) setNotice(destination ? "音色卡已导出。" : "已取消保存。");
    } else {
      const blob = await client.exportVoiceCard(worldId, chosen);
      if (lifetime.current.signal.aborted) return;
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice("音色卡已交给浏览器下载。");
    }
  });
  const erase = (card: VoiceCard) => {
    if (!window.confirm(`删除音色卡“${card.manifest.name}”？\n当前世界使用它的角色会解除绑定，文字聊天和记忆会保留。`)) return;
    void run(async () => {
      await client.removeVoiceCard(worldId, card.card_id);
      if (lifetime.current.signal.aborted) return;
      if (sampleUrl.current) URL.revokeObjectURL(sampleUrl.current);
      sampleUrl.current = null; setSample(null); setRefresh(value => value + 1);
    });
  };
  return <details className="dossier-voice-options"><summary>角色音色{binding ? " · 已绑定" : " · 尚未绑定"}</summary><section className="character-voice"><h3>{name}的声音</h3><p className="inline-hint">一位角色绑定一张音色卡；同一张卡可重复使用。角色改名、换头像或更新资料不会改变绑定。自动配音需在设置中开启。</p>
    <label className="field"><span>使用音色卡</span><select value={chosen} disabled={busy || !page} onChange={event => { setChosen(event.target.value); sampleAudio.current?.pause(); if (sampleUrl.current) URL.revokeObjectURL(sampleUrl.current); sampleUrl.current = null; setSample(null); }}><option value="">不配音</option>{binding && !page?.items.some(item => item.card_id === binding) && <option value={binding}>当前已绑定音色（位于其他页）</option>}{page?.items.map(card => <option key={card.card_id} value={card.card_id}>{card.manifest.name} · {card.manifest.language}</option>)}</select></label>
    <div className="profile-actions"><button type="button" disabled={busy || !page || chosen === (binding ?? "")} onClick={() => void run(async () => { await client.bindVoice(worldId, root, chosen || null); if (lifetime.current.signal.aborted) return; setBinding(chosen || null); setNotice(chosen ? "角色音色已保存。" : "已解除角色音色绑定。"); })}>保存角色音色</button><button className="text-action" type="button" disabled={busy || !chosen} onClick={listen}>试听参考人声</button><button className="text-action" type="button" disabled={busy || !chosen} onClick={exportCard}>导出音色卡</button>{selected && <button className="text-action destructive-action" type="button" disabled={busy} onClick={() => erase(selected)}>删除音色卡</button>}</div>
    {sample && <audio ref={sampleAudio} className="voice-sample" controls src={sample} preload="metadata" />}
    {selected && <p className="inline-hint">{selected.manifest.description || "IndexTTS 2.5"} · 参考音频 {(selected.duration_ms / 1000).toFixed(1)} 秒 · 语速 {selected.manifest.speed}{selected.manifest.author ? ` · 作者：${selected.manifest.author}` : ""}{selected.manifest.license ? ` · 使用说明：${selected.manifest.license}` : ""}</p>}
    {(offset > 0 || page?.next_offset !== null && page?.next_offset !== undefined) && <div className="profile-actions"><button disabled={busy || offset === 0 || dirty} onClick={() => setOffset(value => Math.max(0, value - 100))}>上一页音色</button><button disabled={busy || page?.next_offset == null || dirty} onClick={() => setOffset(page!.next_offset!)}>下一页音色</button></div>}
    <label className="field"><span>导入音色卡或参考人声（WAV／MP3，0.5～15 秒，最大 10 MB）</span><input type="file" accept=".voicecard,.wav,.mp3,audio/wav,audio/mpeg" disabled={busy} onChange={event => { chooseFile(event.target.files?.[0]); event.target.value = ""; }} /></label>
    {source && <><label className="field"><span>音色名称</span><input value={cardName} maxLength={64} disabled={busy || /\.voicecard$/i.test(source.name)} onChange={event => setCardName(event.target.value)} /></label>{preview && <p>预览：{preview.manifest.name} · {preview.manifest.language} · {(preview.duration_ms / 1000).toFixed(1)} 秒。确认后保存并绑定给{name}。</p>}<div className="profile-actions"><button type="button" className="primary-button" disabled={busy || !preview || !cardName.trim()} onClick={importCard}>确认导入并绑定</button><button type="button" disabled={busy} onClick={() => { setSource(null); setPreview(null); }}>取消</button></div></>}
    {error && <p className="app-alert" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </section></details>;
}
