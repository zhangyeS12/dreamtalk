import { useId, useMemo } from "react";
import type { Person, Connection } from "./diagramLayout";
import { radialPositions, shortLabel } from "./diagramLayout";
import { DiagramCanvas } from "./DiagramCanvas";

export function RelationshipDiagram({ people, connections, center, focused, urls, onSelect, resetKey }: {
  people: Person[]; connections: Connection[]; center: string | null; focused: string | null;
  urls: Record<string, string>; onSelect: (root: string) => void; resetKey: string;
}) {
  const prefix = useId().replace(/:/g, "");
  const positions = useMemo(() => radialPositions(people.map(person => person.root_import_id), center), [people, center]);
  return <DiagramCanvas key={resetKey} label="二维人物关系图">{canActivate => <>
    <g aria-hidden="true" className="diagram-links">{connections.map(link => {
      const first = positions.get(link.first_root_import_id), second = positions.get(link.second_root_import_id);
      return first && second ? <line key={link.first_root_import_id + ":" + link.second_root_import_id}
        data-connection={link.first_root_import_id + ":" + link.second_root_import_id}
        x1={first.x} y1={first.y} x2={second.x} y2={second.y} vectorEffect="non-scaling-stroke"
        className={link.first_root_import_id === focused || link.second_root_import_id === focused ? "is-focused" : ""} /> : null;
    })}</g>
    {people.map((person, index) => {
      const point = positions.get(person.root_import_id)!;
      const active = focused === person.root_import_id, central = center === person.root_import_id;
      const radius = central ? 42 : 34, clip = prefix + "-portrait-" + index;
      return <g key={person.root_import_id} className={"diagram-person" + (active ? " is-selected" : "")}
        role="button" tabIndex={0} aria-label={person.name + (central ? "，中心角色" : "") + (center ? "，查看相识" : "，选择角色")}
        onClick={() => { if (canActivate()) onSelect(person.root_import_id); }}
        onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(person.root_import_id); } }}>
        <title>{person.name}</title>
        <circle cx={point.x} cy={point.y} r={48} className="diagram-hit" />
        <circle cx={point.x} cy={point.y} r={radius + 5} className="diagram-avatar-ring" vectorEffect="non-scaling-stroke" />
        <defs><clipPath id={clip}><circle cx={point.x} cy={point.y} r={radius} /></clipPath></defs>
        {urls[person.avatar_digest ?? ""] ? <image href={urls[person.avatar_digest ?? ""]} x={point.x - radius} y={point.y - radius}
          width={radius * 2} height={radius * 2} preserveAspectRatio="xMidYMid slice" clipPath={"url(#" + clip + ")"} />
          : <text x={point.x} y={point.y} className="diagram-initial" textAnchor="middle" dominantBaseline="central">{Array.from(person.name.trim())[0] ?? "?"}</text>}
        <text x={point.x} y={point.y + radius + 35} className="diagram-name" textAnchor="middle">{shortLabel(person.name)}</text>
      </g>;
    })}
  </>}</DiagramCanvas>;
}
