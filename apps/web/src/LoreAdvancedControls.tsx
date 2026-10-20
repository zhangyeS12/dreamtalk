import type { LoreControls } from "@dreamtalk/api-client";

const defaults: LoreControls = { probability: 100, use_probability: false, sticky: 0, cooldown: 0, delay: 0,
  recursion_level: 0, exclude_recursion: false, prevent_recursion: false, scan_depth: null, insertion_depth: null, group: "" };

export function LoreAdvancedControls({ value, onChange }: { value?: LoreControls | null; onChange: (value: LoreControls) => void }) {
  const controls = { ...defaults, ...value };
  const update = (part: Partial<LoreControls>) => onChange({ ...controls, ...part });
  return <details className="lore-advanced"><summary>高级触发与插入位置</summary>
    <p className="inline-hint">计数单位是当前路线中的消息。持续期间不重复抽概率，结束后进入冷却。递归仅扫描已获公开授权的条目。修改条件后需预览、确认，并重新确认公开范围。</p>
    <label className="checkbox-field"><input type="checkbox" checked={controls.use_probability} onChange={event => update({ use_probability: event.target.checked })} />启用概率触发</label>
    <div className="editor-columns">
      {([['probability', '触发概率（%）', 100], ['sticky', '持续消息数', 1000000], ['cooldown', '冷却消息数', 1000000], ['delay', '最少聊天消息数', 1000000], ['recursion_level', '最早递归层级（0为直接）', 32]] as const).map(([key, label, max]) =>
        <label key={key} className="field"><span>{label}</span><input type="number" min={0} max={max} step={1} value={controls[key]} onChange={event => update({ [key]: Number(event.target.value) })} /></label>)}
      <label className="field"><span>关键词扫描深度（留空沿用世界书）</span><input type="number" min={0} max={32} step={1} value={controls.scan_depth ?? ""} onChange={event => update({ scan_depth: event.target.value === "" ? null : Number(event.target.value) })} /></label>
      <label className="field"><span>历史插入深度（留空放在背景区；0在历史后）</span><input type="number" min={0} max={32} step={1} value={controls.insertion_depth ?? ""} onChange={event => update({ insertion_depth: event.target.value === "" ? null : Number(event.target.value) })} /></label>
      <label className="field"><span>互斥组名称（同组取最高优先级）</span><input maxLength={200} value={controls.group} onChange={event => update({ group: event.target.value })} /></label>
    </div>
    <label className="checkbox-field"><input type="checkbox" checked={controls.exclude_recursion} onChange={event => update({ exclude_recursion: event.target.checked })} />仅从聊天触发，不被递归内容触发</label>
    <label className="checkbox-field"><input type="checkbox" checked={controls.prevent_recursion} onChange={event => update({ prevent_recursion: event.target.checked })} />此条目不触发下一层递归</label>
    <p className="inline-hint">后台日常规划不使用聊天计时条件。正则、向量触发、脚本与扩展插件不在此入口执行。</p>
  </details>;
}
