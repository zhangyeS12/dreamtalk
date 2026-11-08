import type { CharacterEvolutionEntry, CharacterEvolutionOperation } from "@dreamtalk/api-client";

function changeLabel(entry: CharacterEvolutionEntry): string {
  return entry.change_kind === "addition" ? "新增内容"
    : entry.change_kind === "replacement" ? "修改原有内容" : "历史版本";
}

function mark(entry: CharacterEvolutionEntry, active: boolean): string {
  if (!active) return "evolution-mark evolution-deleted";
  return entry.change_kind === "addition" ? "evolution-mark evolution-added"
    : entry.change_kind === "replacement" ? "evolution-mark evolution-changed" : "evolution-mark";
}

export function EvolutionLegend() {
  return <p className="evolution-legend">
    <span>动态变化会自动生效，点击标记查看历史或回退。</span>
    <span className="evolution-mark evolution-changed">实线：修改原有内容</span>
    <span className="evolution-mark evolution-added">波浪线：新增内容</span>
    <span className="evolution-mark evolution-deleted">灰色删除线：已停用</span>
  </p>;
}

export function EvolutionFieldTimeline({ entries, baseline, onChange, busy }: {
  entries: CharacterEvolutionEntry[];
  baseline: string;
  onChange: (entry: CharacterEvolutionEntry, operation: CharacterEvolutionOperation) => void;
  busy: boolean;
}) {
  const grouped = new Map<string, CharacterEvolutionEntry[]>();
  for (const entry of entries) grouped.set(entry.scope, [...(grouped.get(entry.scope) ?? []), entry]);
  return <div className="inline-evolution-history">
    {[...grouped.entries()].map(([scope, values]) => {
      const history = [...values].sort((left, right) =>
        left.created_at_utc.localeCompare(right.created_at_utc) || left.entry_id.localeCompare(right.entry_id));
      const current = history.find(entry => entry.selected && entry.state === "active");
      const visible = current ?? history.at(-1);
      if (!visible) return null;
      const locked = !!current?.locked;
      const anotherScopeActive = entries.some(entry => entry.scope !== scope && entry.selected && entry.state === "active");
      return <details key={scope} className="inline-evolution">
        <summary title="展开版本历史，可恢复旧版本或原始内容">
          <span className={mark(visible, !!current)}>{visible.text}</span>
          <small>{scope === "global" ? "当前世界" : "玩家专属"} · {current ? `当前生效 · ${changeLabel(current)}` : "已停用"}{locked ? " · 已锁定" : ""}</small>
        </summary>
        <div className="inline-evolution-timeline">
          {current && <div className="inline-evolution-actions">
            <button type="button" className="text-action" disabled={busy || locked}
              title={locked ? "请先解锁当前版本" : undefined}
              onClick={() => onChange(current, "deactivate")}>{anotherScopeActive ? "停用此范围版本" : baseline.trim() ? "恢复原始内容" : "撤销新增内容"}</button>
          </div>}
          {history.map(entry => {
            const active = entry.entry_id === current?.entry_id;
            return <div key={entry.entry_id} className={`inline-evolution-version ${active ? "evolution-active" : ""}`}>
              <div>
                <span className={mark(entry, active)}>{entry.text}</span>
                <small>{new Date(entry.created_at_utc).toLocaleString()} · {entry.source === "model" ? "模型变化" : entry.source === "import" ? "导入版本" : "用户版本"} · {changeLabel(entry)} · {active ? "当前生效" : "已停用"}{entry.locked ? " · 已锁定" : ""}</small>
                {entry.quote && <small className="evolution-evidence">依据：“{entry.quote}”</small>}
              </div>
              <div className="inline-evolution-actions">
                <button type="button" className="text-action" disabled={busy || active || locked}
                  title={locked && !active ? "请先解锁当前版本" : undefined}
                  onClick={() => onChange(entry, "restore")}>{active ? "当前版本" : "恢复此版本"}</button>
                <button type="button" className="text-action" disabled={busy}
                  onClick={() => onChange(entry, entry.locked ? "unlock" : "lock")}>{entry.locked ? "解锁" : "锁定"}</button>
              </div>
            </div>;
          })}
        </div>
      </details>;
    })}
  </div>;
}
