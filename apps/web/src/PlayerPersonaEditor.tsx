import { useEffect, useId, useRef, useState } from "react";
import {
  CoreClient, CoreRequestError, type InitialRecognition, type PlayerPersonaDraft,
  type PlayerPersonaPreview, type PlayerPersonaSnapshot,
} from "@dreamtalk/api-client";
import { PersonaSourcePicker } from "./PersonaSourcePicker";
import "./player-persona.css";

function normalized(draft: PlayerPersonaDraft): PlayerPersonaDraft {
  return { identity_name: draft.identity_name ?? "", public_identity: draft.public_identity ?? "",
    story_start: draft.story_start ?? "", source: draft.source ?? null, recognitions: draft.recognitions ?? [] };
}

export function PlayerPersonaEditor({ client, worldId, onDirtyChange }: {
  client: CoreClient;
  worldId: string;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const id = useId();
  const [saved, setSaved] = useState<PlayerPersonaSnapshot | null>(null);
  const [draft, setDraft] = useState<PlayerPersonaDraft>(normalized({}));
  const [preview, setPreview] = useState<PlayerPersonaPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [page, setPage] = useState(0);
  const generation = useRef(0);
  const dirty = saved !== null && JSON.stringify(draft) !== JSON.stringify(normalized(saved.draft));
  const recognitions = draft.recognitions ?? [];

  useEffect(() => {
    const abort = new AbortController();
    generation.current += 1;
    setBusy(false);
    setSaved(null); setPreview(null); setError(""); setNotice("");
    void client.playerPersona(worldId, abort.signal).then(result => {
      if (!abort.signal.aborted) { setSaved(result); setDraft(normalized(result.draft)); setPage(0); }
    }).catch(() => { if (!abort.signal.aborted) setError("设定身份暂时无法读取，请重试。"); });
    return () => { abort.abort(); generation.current += 1; };
  }, [client, worldId, reload]);
  useEffect(() => {
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty, onDirtyChange]);

  function edit(patch: Partial<PlayerPersonaDraft>) {
    setDraft(current => ({ ...current, ...patch })); setPreview(null); setNotice(""); setError("");
  }
  function editRecognition(index: number, patch: Partial<InitialRecognition>) {
    edit({ recognitions: recognitions.map((item, current) => current === index ? { ...item, ...patch } : item) });
  }
  async function prepare() {
    if (!saved?.player_id || busy) return;
    setBusy(true); setError(""); setNotice("");
    const current = generation.current;
    try {
      const result = await client.previewPlayerPersona(worldId, draft, saved.revision, saved.player_id);
      if (generation.current === current) setPreview(result);
    }
    catch (failure) {
      if (generation.current !== current) return;
      setError(failure instanceof CoreRequestError && failure.status === 409
        ? "身份或来源已变化，你的输入仍保留。请重新读取身份，或重新选择有效来源后再预览。"
        : "预览未完成，请检查身份名称和所选资料后重试。输入仍保留。");
    } finally { if (generation.current === current) setBusy(false); }
  }
  async function confirm() {
    if (!preview || busy) return;
    setBusy(true); setError("");
    const current = generation.current;
    try {
      const result = await client.confirmPlayerPersona(worldId, preview.preview_id);
      if (generation.current !== current) return;
      setSaved(result); setDraft(normalized(result.draft)); setPreview(null); setNotice("设定身份已采用。");
    } catch {
      if (generation.current !== current) return;
      setError("确认未完成，输入与预览仍保留。可重试确认；若来源变化或预览已过期，请返回编辑后重新预览。");
    } finally { if (generation.current === current) setBusy(false); }
  }

  return <section className="player-persona-editor" aria-labelledby={`${id}-heading`}>
    <div className="section-heading"><h2 id={`${id}-heading`}>设定身份与初始认识</h2>
      <p>明确你在这个世界对应谁，以及哪些角色原本就认识你。这里的公开介绍会提供给与你交流的角色；每位角色的初始认识只提供给该角色。</p>
    </div>
    {error && <p role="alert">{error}</p>}
    <button type="button" className="text-action" disabled={busy} onClick={() => {
      if (!dirty || window.confirm("重新读取会放弃尚未确认的身份修改，是否继续？")) setReload(value => value + 1);
    }}>重新读取身份</button>
    {!saved && !error && <p role="status">正在读取设定身份…</p>}
    {saved && !saved.player_id && <p className="inline-hint">请先在这个世界进入聊天并建立玩家身份，再设置初始认识。</p>}
    {saved?.player_id && <>
      {saved.source_state === "changed" && <p role="status">绑定的资料已被替换、停用或移除。该设定暂不提供给角色，请重新选择来源并确认。</p>}
      <fieldset disabled={busy || !!preview} className="persona-fields">
        <details><summary>从世界书或角色卡选择身份</summary>
          <p className="inline-hint">只读取当前世界已接受的资料。同名不会自动绑定；采用后请核对公开介绍，删除不应让所有角色知道的秘密。</p>
          <PersonaSourcePicker client={client} worldId={worldId} onChoose={source => {
            edit({ source: source.reference, identity_name: Array.from(source.title).slice(0, 120).join(""), public_identity: Array.from(source.text).slice(0, 2000).join("") });
            setNotice("已填入资料开头作为草稿。请核对公开范围和故事阶段，再预览确认。");
          }} />
        </details>
        <p className="inline-hint">{draft.source ? "已选择资料来源。修改后需重新确认才会生效。" : "当前为原创身份，也可手动填写。"}
          {draft.source && <button type="button" className="text-action" onClick={() => edit({ source: null })}>改为原创身份</button>}</p>
        <div className="field"><label htmlFor={`${id}-name`}>设定人物名称</label><input id={`${id}-name`} maxLength={120} value={draft.identity_name ?? ""} onChange={event => edit({ identity_name: event.target.value })} placeholder="例如：哲" /></div>
        <div className="field"><label htmlFor={`${id}-public`}>公开身份介绍</label><textarea id={`${id}-public`} rows={5} maxLength={2000} value={draft.public_identity ?? ""} onChange={event => edit({ public_identity: event.target.value })} placeholder="写明身份、职业及可公开的背景。同名人物请在这里区分。" /></div>
        <div className="field"><label htmlFor={`${id}-stage`}>故事起点</label><textarea id={`${id}-stage`} rows={2} maxLength={600} value={draft.story_start ?? ""} onChange={event => edit({ story_start: event.target.value })} placeholder="采用哪个时期的设定，哪些剧情尚未发生" /></div>
        <details><summary>添加角色的初始认识（{recognitions.length}）</summary>
          <p className="inline-hint">填写故事开始前已有的认识。没有填写不等于陌生；不会据此生成相遇事件或亲历记忆。共同邀请只使用参与角色都能知道的身份信息。</p>
          <PersonaSourcePicker client={client} worldId={worldId} characters onChoose={source => {
            if (!source.root_import_id) return;
            const index = recognitions.findIndex(item => item.character_import_id === source.root_import_id);
            if (index >= 0) { setPage(Math.floor(index / 12)); return; }
            edit({ recognitions: [...recognitions, { character_import_id: source.root_import_id, character_name: Array.from(source.title).slice(0, 120).join(""), relationship: "", known_details: "" }] });
            setPage(Math.floor(recognitions.length / 12));
          }} />
        </details>
        {recognitions.slice(page * 12, page * 12 + 12).map((item, offset) => {
          const index = page * 12 + offset;
          return <div className="persona-recognition" key={item.character_import_id}>
            <h3>{item.character_name || "已选角色"}</h3>
            <div className="field"><label htmlFor={`${id}-${index}-relation`}>与{item.character_name || "该角色"}的初始关系</label><input id={`${id}-${index}-relation`} maxLength={240} value={item.relationship ?? ""} onChange={event => editRecognition(index, { relationship: event.target.value })} /></div>
            <div className="field"><label htmlFor={`${id}-${index}-known`}>{item.character_name || "该角色"}起初知道什么</label><textarea id={`${id}-${index}-known`} rows={3} maxLength={1600} value={item.known_details ?? ""} onChange={event => editRecognition(index, { known_details: event.target.value })} /></div>
            <button type="button" className="text-action" onClick={() => { edit({ recognitions: recognitions.filter((_, current) => current !== index) }); setPage(Math.min(page, Math.max(0, Math.ceil((recognitions.length - 1) / 12) - 1))); }}>移除这项初始认识</button>
          </div>;
        })}
        {recognitions.length > 12 && <div className="profile-actions"><button type="button" disabled={page === 0} onClick={() => setPage(value => value - 1)}>上一页角色</button><span>{page + 1} / {Math.ceil(recognitions.length / 12)}</span><button type="button" disabled={(page + 1) * 12 >= recognitions.length} onClick={() => setPage(value => value + 1)}>下一页角色</button></div>}
      </fieldset>
      {!preview && <div className="profile-actions"><button type="button" className="primary-button" disabled={busy || (!dirty && saved.source_state !== "changed")} onClick={() => void prepare()}>预览身份修改</button><span role="status">{notice || (dirty ? "尚未确认" : "")}</span></div>}
      {preview && <section className="persona-preview" aria-label="身份修改预览">
        <h3>确认本世界的设定身份</h3><p>确认后，后续对话将采用以下设置。已有聊天与玩家身份保持连续。</p>
        <dl><dt>身份</dt><dd>{preview.draft.identity_name || "未填写"}</dd><dt>来源</dt><dd>{preview.source_title || "原创身份"}</dd><dt>公开介绍</dt><dd className="persona-text">{preview.draft.public_identity || "未填写"}</dd><dt>故事起点</dt><dd className="persona-text">{preview.draft.story_start || "未限定"}</dd></dl>
        {(preview.draft.recognitions ?? []).slice(page * 12, page * 12 + 12).map(item => <details key={item.character_import_id}><summary>仅{item.character_name}的初始认识</summary><p className="persona-text">{item.relationship || "未填写关系"}</p><p className="persona-text">{item.known_details || "未填写已知详情"}</p></details>)}
        {(preview.draft.recognitions ?? []).length > 12 && <div className="profile-actions"><button type="button" disabled={page === 0 || busy} onClick={() => setPage(value => value - 1)}>上一页认识预览</button><span>{page + 1} / {Math.ceil((preview.draft.recognitions ?? []).length / 12)}</span><button type="button" disabled={(page + 1) * 12 >= (preview.draft.recognitions ?? []).length || busy} onClick={() => setPage(value => value + 1)}>下一页认识预览</button></div>}
        <div className="profile-actions"><button type="button" className="primary-button" disabled={busy} onClick={() => void confirm()}>确认采用身份</button><button type="button" className="text-action" disabled={busy} onClick={() => { setPreview(null); setError(""); }}>返回编辑</button></div>
        <p className="inline-hint">预览有效期为十分钟。资料来源变化后需重新预览确认。</p>
      </section>}
    </>}
  </section>;
}
