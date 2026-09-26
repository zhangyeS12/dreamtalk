import { useEffect, useId, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type LocalProfile } from "@dreamtalk/api-client";

export function ProfileEditor({ client, worldId, onDirtyChange }: {
  client: CoreClient;
  worldId?: string;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const formId = useId();
  const [saved, setSaved] = useState<LocalProfile | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  const dirty = saved !== null && (name !== saved.name || description !== saved.description);

  useEffect(() => {
    let active = true;
    setSaved(null); setError(""); setNotice("");
    void client.profile(worldId).then(profile => {
      if (!active) return;
      setSaved(profile); setName(profile.name); setDescription(profile.description);
    }).catch(() => { if (active) setError("资料暂时无法读取，请重试。"); });
    return () => { active = false; };
  }, [client, worldId, reload]);

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    if (!dirty) return;
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, [dirty]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!saved || saving || !dirty) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await client.saveProfile({ name, description, revision: saved.revision }, worldId);
      setSaved(result); setNotice("已保存。");
    } catch (failure) {
      setError(failure instanceof CoreRequestError && failure.status === 409
        ? "资料已在其他窗口修改。你的输入仍保留，请重新读取后再编辑。"
        : "保存未完成，你的输入仍保留，请重试。");
    } finally { setSaving(false); }
  }

  return <section className="settings-section">
    <div className="section-heading"><h2>{worldId ? "世界专属描述" : "通用个人信息"}</h2><p>{worldId ? "填写你在当前世界的身份。与通用描述冲突时，以这里为准。" : "例如你的称呼、性别和爱好，适用于所有世界。"}</p></div>
    {error && <div className="profile-feedback"><p role="alert">{error}</p><button type="button" className="text-action" disabled={saving} onClick={() => { if (!dirty || window.confirm("重新读取会放弃尚未保存的输入，是否继续？")) setReload(value => value + 1); }}>重新读取</button></div>}
    {saved ? <form className="profile-form" onSubmit={event => void save(event)}>
      <div className="field"><label htmlFor={`${formId}-name`}>{worldId ? "世界中的称呼" : "我的称呼"}</label><input id={`${formId}-name`} maxLength={120} value={name} disabled={saving} onChange={event => { setName(event.target.value); setNotice(""); }} placeholder={worldId ? "留空则使用通用称呼" : "你希望被怎样称呼"} /></div>
      <div className="field"><label htmlFor={`${formId}-description`}>{worldId ? "我在这个世界的身份" : "关于我"}</label><textarea id={`${formId}-description`} rows={5} maxLength={8000} value={description} disabled={saving} onChange={event => { setDescription(event.target.value); setNotice(""); }} placeholder={worldId ? "例如职业、经历，以及与这个世界的关系" : "写下你愿意让角色了解的个人描述"} /></div>
      <div className="profile-actions"><button className="primary-button" type="submit" disabled={saving || !dirty}>{saving ? "正在保存…" : worldId ? "保存世界身份" : "保存通用信息"}</button><span role="status">{notice || (dirty ? "尚未保存" : "")}</span></div>
    </form> : !error ? <p className="inline-hint" role="status">正在读取资料…</p> : null}
  </section>;
}
