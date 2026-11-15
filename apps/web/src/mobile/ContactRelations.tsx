import { useCallback, useEffect, useMemo, useState } from "react";
import type { SocialSnapshot } from "@dreamtalk/api-client";
import { ContactAvatar } from "../ContactSocial";
import { confirmedConnections } from "./diagramLayout";
import { atlasFactionPaths, atlasNeighbors, layoutAtlas } from "./atlasLayout";
import { RelationshipAtlas } from "./RelationshipAtlas";
import { RelationPairSheet } from "./RelationPairSheet";

export function ContactRelations({ social, selected, onChoose, onProfile, urls = {}, onAvatarDigests }: {
  social: SocialSnapshot; selected: string | null; onChoose: (root: string) => boolean | void;
  onProfile: (root: string) => void; urls?: Record<string, string>; onAvatarDigests?: (digests: string) => void;
}) {
  const [presentation, setPresentation] = useState<"graph" | "list">("graph");
  const [query, setQuery] = useState(""), [faction, setFaction] = useState(""), [page, setPage] = useState(0);
  const [focus, setFocus] = useState<string | null>(null), [pairId, setPairId] = useState<string | null>(null);
  const [atlasDigests, setAtlasDigests] = useState("");
  const [graphFailure, setGraphFailure] = useState<string | null>(null);
  const graphFailed = useCallback((reason: string) => {
    setGraphFailure(reason); setPresentation("list"); setPairId(null);
  }, []);
  const sorted = useMemo(() => [...new Map(social.characters.map(person => [person.root_import_id, person])).values()]
    .sort((a, b) => a.name.localeCompare(b.name) || a.root_import_id.localeCompare(b.root_import_id)), [social.characters]);
  const people = useMemo(() => new Map(sorted.map(person => [person.root_import_id, person])), [sorted]);
  const paths = useMemo(() => atlasFactionPaths(social), [social]);
  const edges = useMemo(() => confirmedConnections(social), [social]);
  const factionId = paths.has(faction) ? faction : "";
  const filtered = useMemo(() => {
    const members = new Set(social.memberships.filter(member => member.faction_id === factionId).map(member => member.root_import_id));
    return sorted.filter(person => (!factionId || members.has(person.root_import_id)) &&
      person.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  }, [sorted, factionId, query, social.memberships]);
  const layout = useMemo(() => layoutAtlas(filtered, social, factionId), [filtered, social, factionId]);
  const roots = useMemo(() => new Set(filtered.map(person => person.root_import_id)), [filtered]);
  const shownEdges = useMemo(() => edges.filter(edge => roots.has(edge.first_root_import_id) && roots.has(edge.second_root_import_id)), [edges, roots]);
  const focusedPerson = people.get(focus ?? "") ?? null;
  const center = presentation === "list" ? focusedPerson : roots.has(focus ?? "") ? focusedPerson : null;
  const other = center && pairId !== center.root_import_id && roots.has(pairId ?? "") ? people.get(pairId!) ?? null : null;
  const pairEdge = center && other ? edges.find(edge => edge.first_root_import_id === center.root_import_id && edge.second_root_import_id === other.root_import_id ||
    edge.second_root_import_id === center.root_import_id && edge.first_root_import_id === other.root_import_id) : undefined;
  const neighbors = useMemo(() => atlasNeighbors(edges, center?.root_import_id ?? null), [edges, center]);
  const listPeople = focusedPerson ? filtered.filter(person => neighbors.has(person.root_import_id)) : filtered;
  const last = Math.max(0, Math.ceil(listPeople.length / 30) - 1), shownPage = Math.min(page, last);
  const shown = listPeople.slice(shownPage * 30, (shownPage + 1) * 30);
  const listDigests = [...new Set(shown.flatMap(person => person.avatar_digest ? [person.avatar_digest] : []))].sort().join(",");
  const digests = graphFailure ? "" : presentation === "graph" ? atlasDigests : listDigests;
  useEffect(() => { onAvatarDigests?.(digests); return () => onAvatarDigests?.(""); }, [digests, onAvatarDigests]);
  function factionNames(root: string) {
    return [...new Set(social.memberships.filter(member => member.root_import_id === root).flatMap(member => paths.get(member.faction_id) ?? []))];
  }
  function chooseCenter(root: string) {
    if (!people.has(root) || onChoose(root) === false) return;
    setGraphFailure(null); setFocus(root); setPairId(null); setPresentation("graph"); setQuery(""); setPage(0);
    if (factionId && !social.memberships.some(member => member.faction_id === factionId && member.root_import_id === root)) setFaction("");
  }
  function select(root: string) {
    if (!center) chooseCenter(root);
    else if (root !== center.root_import_id) setPairId(root);
  }
  return <section className="mobile-contact-panel relation-atlas-panel">
    <header className="atlas-heading"><div><span className="atlas-eyebrow">RELATIONSHIPS</span><h3>人物关系网</h3></div>
      <span className="atlas-heading-count">{sorted.length} 位角色</span></header>
    {graphFailure && <div className="atlas-failure" role="alert">
      <p>关系图暂时未能绘制，已显示人物列表。</p>
      <button onClick={() => { setGraphFailure(null); setPresentation("graph"); }}>重新绘图</button>
      <small>错误码：{graphFailure}</small>
    </div>}
    <div className="diagram-switches" role="group" aria-label="关系显示方式">
      <button type="button" aria-pressed={presentation === "graph" && !center} onClick={() => { setGraphFailure(null); setFocus(null); setPairId(null); setPresentation("graph"); }}>全局总览</button>
      <button type="button" aria-pressed={presentation === "graph" && !!center} disabled={!filtered.length}
        onClick={() => chooseCenter(center?.root_import_id ?? (roots.has(selected ?? "") ? selected! : filtered[0].root_import_id))}>个人关系</button>
      <button type="button" aria-pressed={presentation === "list"} onClick={() => { setPresentation("list"); setPairId(null); setPage(0); }}>列表</button>
    </div>
    <div className="atlas-search"><label className="field">搜索关系图角色<input type="search" value={query} maxLength={120}
      placeholder="输入姓名，快速找到人物" onChange={event => { setQuery(event.target.value); setPairId(null); setPage(0); }} /></label>
      <label className="field">筛选阵营<select value={factionId} onChange={event => { setFaction(event.target.value); setPairId(null); setPage(0); }}>
        <option value="">所有阵营</option>{social.factions.map(item => <option key={item.faction_id} value={item.faction_id}>{paths.get(item.faction_id)}</option>)}</select></label></div>
    {presentation === "graph" && query.trim() && filtered.length > 0 && <div className="atlas-search-results" aria-label="搜索结果">
      {filtered.slice(0, 8).map(person => <button key={person.root_import_id} onClick={() => chooseCenter(person.root_import_id)}>聚焦{person.name}</button>)}
      {filtered.length > 8 && <small>其余结果可在列表中查看</small>}</div>}
    <div className="atlas-summary"><span>{presentation === "list" ? listPeople.length + (focusedPerson ? " 位已确认相识符合筛选" : " 位角色符合筛选") :
      filtered.length + " 位角色 · " + shownEdges.length + " 条已确认相识"}</span>
      {(query || factionId) && <button onClick={() => { setQuery(""); setFaction(""); setPairId(null); setPage(0); }}>清除筛选</button>}</div>
    {presentation === "graph" && filtered.length > 0 && <RelationshipAtlas key={[factionId, query, center?.root_import_id].join("|")}
      layout={layout} connections={shownEdges} center={center?.root_import_id ?? null} pair={other?.root_import_id ?? null}
      urls={urls} onSelect={select} onAvatarDigests={setAtlasDigests} onFailure={graphFailed} />}
    {presentation === "graph" && center && <div className="atlas-focus-card" aria-label="图中选中角色">
      <ContactAvatar name={center.name} url={urls[center.avatar_digest ?? ""]} />
      <div><strong>{center.name}</strong><small>{factionNames(center.root_import_id).join("、") || "尚未加入阵营"}</small>
        <span>{neighbors.size} 位已确认相识 · 再选一人查看详情</span></div>
      <button onClick={() => onProfile(center.root_import_id)}>查看资料</button></div>}
    {presentation === "list" && <ul className="mobile-list atlas-person-list">{shown.map(person => <li key={person.root_import_id}>
      <button onClick={() => onProfile(person.root_import_id)} aria-label={"查看" + person.name + "资料"}><ContactAvatar name={person.name} url={urls[person.avatar_digest ?? ""]} />
        <span><strong>{person.name}</strong><small>{center ? "已确认相识" : atlasNeighbors(edges, person.root_import_id).size + " 位已确认相识"}</small>
          <small>{factionNames(person.root_import_id).join("、") || "尚未加入阵营"}</small></span></button>
      <button onClick={() => chooseCenter(person.root_import_id)} aria-label={"聚焦" + person.name}>聚焦</button></li>)}</ul>}
    {presentation === "list" && listPeople.length > 30 && <div className="diagram-pagination" aria-label="关系列表分页">
      <button disabled={!shownPage} onClick={() => setPage(shownPage - 1)}>上一页</button><span>{shownPage + 1} / {last + 1}</span>
      <button disabled={shownPage === last} onClick={() => setPage(shownPage + 1)}>下一页</button></div>}
    {!sorted.length ? <p role="status">先添加角色，再查看相识关系。</p> : !(presentation === "list" ? listPeople.length : filtered.length) && <p role="status">{presentation === "list" && focusedPerson ? "没有匹配的相识角色。" : "没有匹配的角色。"}</p>}
    {other && center && <RelationPairSheet first={center} second={other} connected={!!pairEdge} urls={urls} factionNames={factionNames}
      reasons={pairEdge?.faction_ids.flatMap(id => paths.get(id) ?? []) ?? []} onClose={() => setPairId(null)}
      onProfile={onProfile} onCenter={chooseCenter} />}
    <p className="diagram-help">连线表示已有的相识；同处一个分区不会自动建立关系。人物只出现一次，分区只用于排版，不代表实际地点。</p>
  </section>;
}
