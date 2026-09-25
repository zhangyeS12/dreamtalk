import { useEffect, useState, type FormEvent } from "react";
import { CoreClient, CoreRequestError, type GroupChatConversation, type WorldContentItem } from "@livingworld/api-client";

export function GroupChatSetup({ client, worldId, onCreated, onBack }: {
  client: CoreClient;
  worldId: string;
  onCreated: (group: GroupChatConversation) => void;
  onBack: () => void;
}) {
  const [contacts, setContacts] = useState<WorldContentItem[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [pending, setPending] = useState<{ importIds: string[]; requestId: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void client.worldContent(worldId).then(items => {
      if (active) setContacts(items.filter(item => item.kind === "character" && item.characters.length === 1));
    }).catch(() => { if (active) setError("无法读取当前世界的角色，请重试。"); });
    return () => { active = false; };
  }, [client, worldId]);

  const toggle = (importId: string) => {
    if (pending) return;
    setSelected(current => current.includes(importId) ? current.filter(id => id !== importId) : [...current, importId]);
  };
  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (saving || (!pending && selected.length < 2)) return;
    const attempt = pending ?? { importIds: selected, requestId: crypto.randomUUID() };
    setPending(attempt);
    setSaving(true);
    setError("");
    try {
      onCreated(await client.createGroupConversation(worldId, attempt.importIds, attempt.requestId));
      setPending(null);
    } catch (failure) {
      if (failure instanceof CoreRequestError && [404, 409, 422].includes(failure.status)) {
        setPending(null);
        setError("所选角色已变化或不属于当前世界。请重新选择成员。");
      } else {
        setError("群聊保存结果尚未确认。可以重试同一次创建，不会重复建立会话。");
      }
    } finally { setSaving(false); }
  };

  return <section className="group-setup" aria-label="创建群聊">
    <div className="thread-heading"><button type="button" className="text-action" onClick={onBack}>返回聊天</button><h2>新建群聊</h2></div>
    <form onSubmit={event => void create(event)}>
      <p className="inline-hint">从当前世界选择至少两位角色。群聊发言功能尚未开放。</p>
      {contacts === null ? <p className="thread-hint">正在读取角色…</p> : contacts.length < 2 ? <p className="thread-hint">当前世界至少需要两张已确认的角色卡。</p> : <div className="group-contact-list">{contacts.map(item => <label key={item.import_id} className="group-contact"><input type="checkbox" checked={selected.includes(item.import_id)} disabled={saving || !!pending} onChange={() => toggle(item.import_id)} /><span>{item.characters[0].name}</span></label>)}</div>}
      {error ? <p className="app-alert" role="alert">{error}</p> : null}
      <div className="group-actions"><button type="submit" className="primary-button" disabled={saving || (selected.length < 2 && !pending)}>{saving ? "正在创建…" : pending ? "重试创建" : "创建群聊"}</button></div>
    </form>
  </section>;
}

export function GroupChatDetails({ group, onBack }: { group: GroupChatConversation; onBack: () => void }) {
  return <section className="group-details" aria-label="群聊成员">
    <div className="thread-heading"><button type="button" className="text-action" onClick={onBack}>返回聊天</button><h2>{group.participants.map(item => item.character_name).join("、")}</h2><span>群聊</span></div>
    <div className="group-members"><h3>成员</h3><ul>{group.participants.map(item => <li key={item.character_id}>{item.character_name}</li>)}</ul></div>
    <p className="thread-hint">群聊已保存在当前世界。发言调度与整轮 Token 额度接线完成后，才能在这里发送消息。</p>
  </section>;
}
