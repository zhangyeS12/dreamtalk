import { useEffect, useId, useRef } from "react";
import type { Person } from "./diagramLayout";
import { ContactAvatar } from "../ContactSocial";

export function RelationPairSheet({ first, second, connected, reasons, factionNames, urls, onClose, onProfile, onCenter }: {
  first: Person; second: Person; connected: boolean; reasons: string[]; factionNames: (id: string) => string[];
  urls: Record<string, string>; onClose: () => void; onProfile: (id: string) => void; onCenter: (id: string) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null), title = useId();
  useEffect(() => {
    const element = ref.current; if (!element) return;
    if (typeof element.showModal === "function") element.showModal(); else element.setAttribute("open", "");
    return () => { if (element.open && typeof element.close === "function") element.close(); };
  }, []);
  return <dialog ref={ref} className="relation-pair-sheet" aria-labelledby={title}
    onClose={event => { if (!event.currentTarget.open) onClose(); }} onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (event.target === event.currentTarget) {
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
    } }}>
    <header><span className="atlas-eyebrow">两人关系</span><button autoFocus onClick={onClose} aria-label="关闭两人详情">关闭</button></header>
    <div className="atlas-pair-portraits"><ContactAvatar name={first.name} url={urls[first.avatar_digest ?? ""]} />
      <span aria-hidden="true">{connected ? "—" : "·"}</span><ContactAvatar name={second.name} url={urls[second.avatar_digest ?? ""]} /></div>
    <h3 id={title}>{first.name}<span> 与 </span>{second.name}</h3>
    <p className={"atlas-pair-state" + (connected ? " is-known" : "")}>{connected ? "已确认相识" : "尚无已确认相识记录"}</p>
    {connected && <p className="atlas-pair-origin">{reasons.length ? "相识依据：阵营「" + reasons.join("」、「") + "」" : "相识依据：已有相识记录"}</p>}
    <div className="atlas-pair-profiles">{[first, second].map(person => <section key={person.root_import_id}>
      <h4>{person.name}</h4><p>{factionNames(person.root_import_id).join("、") || "尚未加入阵营"}</p>
      <button onClick={() => onProfile(person.root_import_id)}>查看{person.name}资料</button>
    </section>)}</div>
    <p className="diagram-help">这里只展示已有相识与阵营资料；没有记录时保留未知，不推断关系类型或展示隐藏数值。</p>
    <footer><button onClick={onClose}>返回关系网</button><button className="primary-button" onClick={() => onCenter(second.root_import_id)}>聚焦{second.name}</button></footer>
  </dialog>;
}
