import { useState } from "react";
import { PlaceDiagram } from "./PlaceDiagram";
import { locationPaths } from "./diagramLayout";
export { ContactRelations } from "./ContactRelations";
import type { ActivityCharacterDirectory, ActivityLocation, SocialSnapshot } from "@dreamtalk/api-client";

const PAGE_SIZE = 30;
function Pages({ page, total, onPage }: { page: number; total: number; onPage: (page: number) => void }) {
  const last = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
  return total > PAGE_SIZE ? <div className="profile-actions" aria-label="列表分页"><button disabled={!page} onClick={() => onPage(page - 1)}>上一页</button><span>{page + 1} / {last + 1}</span><button disabled={page === last} onClick={() => onPage(page + 1)}>下一页</button></div> : null;
}
export function ContactPlaces({ locations, directory, social, onSelect, onEdit, urls = {}, onAvatarDigests }: {
  locations: ActivityLocation[]; directory: ActivityCharacterDirectory | null; social: SocialSnapshot;
  onSelect: (root: string) => void; onEdit: () => void;
  urls?: Record<string, string>; onAvatarDigests?: (digests: string) => void;
}) {
  const [query, setQuery] = useState(""), [page, setPage] = useState(0);
  const [presentation, setPresentation] = useState<"map" | "list">("map");
  const paths = locationPaths(locations);
  const people = social.characters.filter(person => person.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const shownPage = Math.min(page, Math.max(0, Math.ceil(people.length / PAGE_SIZE) - 1));
  return <section className="mobile-contact-panel"><h3>地点与角色位置</h3><p className="inline-hint">地点作者视图。这里只显示已保存的位置；聊天成员不等于在场者。</p><button onClick={onEdit}>添加／编辑地点</button>
    <div className="diagram-switches" role="group" aria-label="地点显示方式"><button type="button" aria-pressed={presentation === "map"} onClick={() => setPresentation("map")}>地点图</button><button type="button" aria-pressed={presentation === "list"} onClick={() => setPresentation("list")}>列表</button></div>
    {presentation === "map" ? <PlaceDiagram locations={locations} directory={directory} social={social} onSelect={onSelect} urls={urls} onAvatarDigests={onAvatarDigests} /> : <>
    <details><summary>地点目录（{locations.length}）</summary>{locations.map(place => <p key={place.location_id}>{paths.get(place.location_id)}{place.hidden ? " · 隐藏分支" : ""}</p>)}{!locations.length && <p>尚未添加地点。</p>}</details>
    <label className="field">搜索位置列表中的角色<input type="search" value={query} onChange={event => { setQuery(event.target.value); setPage(0); }} /></label>
    <ul className="mobile-list">{people.slice(shownPage * PAGE_SIZE, (shownPage + 1) * PAGE_SIZE).map(person => {
      const item = directory?.items.find(entry => entry.root_import_id === person.root_import_id);
      return <li key={person.root_import_id}><button onClick={() => onSelect(person.root_import_id)}><span><strong>{person.name}</strong><small>{!directory || !item ? "位置尚未读取" : item.initialized && item.current_location_id ? paths.get(item.current_location_id) ?? "目录外地点" : "尚未设置初始地点"}</small></span><span aria-hidden="true">›</span></button></li>;
    })}</ul>{!people.length && <p role="status">没有匹配的角色。</p>}<Pages page={shownPage} total={people.length} onPage={setPage} />
  </>}</section>;
}
