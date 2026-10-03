import { useEffect, useRef, useState } from "react";
import { CoreClient, type ChatContextReports } from "@dreamtalk/api-client";

export function ContextReferencePanel({ client, worldId, conversationId, turnId, names, onClose }: {
  client: CoreClient; worldId: string; conversationId: string; turnId: string;
  names: Map<string, string>; onClose: () => void;
}) {
  const panel = useRef<HTMLElement>(null);
  const [result, setResult] = useState<ChatContextReports | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setResult(null); setFailed(false);
    const frame = requestAnimationFrame(() => panel.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
    client.chatContextReports(worldId, conversationId, turnId, controller.signal).then(value => {
      if (!controller.signal.aborted) setResult(value);
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => { controller.abort(); cancelAnimationFrame(frame); };
  }, [client, worldId, conversationId, turnId]);
  return <section ref={panel} className="context-references" aria-label="本次参考内容">
    <div className="thread-heading"><h3>本次参考内容</h3><button type="button" className="text-action" onClick={onClose}>关闭</button></div>
    <p>查看生成前准备的资料，不会调用模型。数量只统计本次选出的候选，不代表全部存档；Token 上界是预留额度，实际用量以服务账单为准。</p>
    {failed ? <p role="alert">未能读取，请关闭后重试。</p> : result === null ? <p role="status">正在读取…</p> : result.reports.length === 0 ? <p>此轮没有参考记录，可能来自旧版本或生成前已停止。</p> : result.reports.map((report, index) => <article key={`${report.speaker_id}-${index}`}>
      <h4>{names.get(report.speaker_id) ?? "角色"}</h4>
      <p>{report.retrieval === "hybrid_memory_only" ? "关键词＋本地中文语义检索（磁盘缓存不可用，暂用内存）" : report.retrieval === "hybrid_partial" ? "关键词＋本地中文语义检索（较早历史正在逐步建立本地索引）" : report.retrieval === "hybrid" ? "关键词＋本地中文语义检索" : report.retrieval === "keyword_fallback" ? "本地语义组件不可用，本次使用关键词检索" : "关键词检索"} · 输入预留上界 {report.input_upper_bound.toLocaleString("zh-CN")} · 回复最多 {report.output_upper_bound.toLocaleString("zh-CN")} Token</p>
      {report.context_reduced ? <p>本次容量有限，已优先保留当前问题、角色设定、当前活动和重要记忆。</p> : null}
      <ul>{report.categories.map(category => <li key={category.label}>{category.label}：参考 {category.included} 条{category.omitted ? `，本次省略 ${category.omitted} 条` : ""}</li>)}</ul>
      {report.references_omitted ? <p>查看记录容量有限，另有 {report.references_omitted} 条来源未展开；这不会改变已经准备的模型输入。</p> : null}
      {report.references.length ? <details><summary>长期记忆与历史原句来源（{report.references.length}）</summary>{report.references.map((reference, refIndex) => <blockquote key={`${reference.id}-${refIndex}`}><p>{reference.text}</p>{reference.source && reference.source !== reference.text ? <p>原句：{reference.source}</p> : null}<small>来源：{reference.source_kind === "player" ? "我" : names.get(reference.source_sender_id) ?? "曾参与群聊的角色"} · 记录时间：{reference.time ? new Date(reference.time).toLocaleString("zh-CN") : "来源时间未记录"}</small></blockquote>)}</details> : <p>本次未引用长期记忆或旧原句。</p>}
    </article>)}
  </section>;
}
