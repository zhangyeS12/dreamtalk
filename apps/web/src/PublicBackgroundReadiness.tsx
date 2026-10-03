import { useCallback, useEffect, useRef, useState } from "react";
import { CoreClient } from "@dreamtalk/api-client";

interface Snapshot { books: number; entries: number; common: number; enabled: number; rules: Array<{ id: string; title: string; summary: string }>; checkedAt: string }

/** Counts saved exposure only. Trigger evaluation stays authoritative in Core. */
export function PublicBackgroundReadiness({ client, worldId, visible, onManage, disabled = false }: { client: CoreClient; worldId: string; visible: boolean; onManage?: () => void; disabled?: boolean }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [failed, setFailed] = useState(false);
  const [reading, setReading] = useState(false);
  const serial = useRef(0);
  const read = useCallback(async () => {
    const request = ++serial.current; setReading(true);
    try {
      const items = (await client.worldContent(worldId)).filter(item => item.kind === "lorebook");
      if (request !== serial.current) return;
      const entries = items.flatMap(item => item.entries);
      const common = entries.filter(entry => entry.common);
      setSnapshot({ books: items.reduce((total, item) => total + item.lorebooks.length, 0), entries: entries.length, common: common.length, enabled: common.filter(entry => entry.enabled).length,
        rules: items.flatMap(item => item.entries.filter(entry => entry.common && entry.enabled).map(entry => ({ id: `${item.import_id}:${entry.id}`, title: entry.title || "未命名条目", summary: entry.planning_activation_summary ?? "参与条件尚未读取，请在世界书条目中核对。" }))), checkedAt: new Date().toLocaleTimeString("zh-CN") });
      setFailed(false);
    } catch { if (request === serial.current) setFailed(true); }
    finally { if (request === serial.current) setReading(false); }
  }, [client, worldId]);
  useEffect(() => {
    if (!visible) return;
    void read();
    return () => { ++serial.current; };
  }, [visible, read]);
  return <div className="background-readiness">
    <div className="background-readiness-heading"><h3>公共背景准备情况</h3><button type="button" className="text-action" disabled={reading || disabled} onClick={() => void read()}>{reading ? "读取中…" : "刷新背景"}</button></div>
    {failed ? <p role="alert">未能核对已保存的公开范围。请刷新背景；不能据此判断没有公共背景。</p> : snapshot ? <>
      <p>{snapshot.books}份世界书 · {snapshot.entries}条条目 · 已公开{snapshot.common}条，其中启用{snapshot.enabled}条。<small> 核对于{snapshot.checkedAt}</small></p>
      <p className="inline-hint">{snapshot.books === 0 ? "先保存世界书，再逐条确认公开范围。" : snapshot.common === 0 ? "当前条目尚未设为公共背景，隐藏条目不会提供给后台模型。" : snapshot.enabled === 0 ? "已公开条目在来源中均被禁用，请检查条目设置。" : "已公开、已启用不等于本次已触发；还需满足关键词、提供条件和背景容量。"}</p>
      {snapshot.rules.length > 0 && <details><summary>查看已公开条目的参与条件（{snapshot.rules.length}）</summary><p className="inline-hint">以下是核心返回的日常规划规则。活动规划匹配角色名和当前地点名；世界动态匹配世界名与公开条目标题。后台生成类型、次级关键词、常驻和容量规则仍以核心为准。</p><ul>{snapshot.rules.map(rule => <li key={rule.id}><strong>{rule.title}</strong><p>{rule.summary}</p></li>)}</ul></details>}
    </> : <p>{reading ? "正在核对已保存的世界书…" : "尚未核对公共背景。"}</p>}
    {onManage && <button type="button" className="text-action" disabled={disabled} onClick={onManage}>返回书架管理世界书</button>}
    <p className="inline-hint">刷新背景只读取已保存内容，不会公开条目、重规划或调用模型。</p>
  </div>;
}
