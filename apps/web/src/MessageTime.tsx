import type { ChatMessage } from "@dreamtalk/api-client";
export function MessageTime({ message, compact = false }: { message: ChatMessage; compact?: boolean }) {
  const shown = message.story_sent_at_utc ?? message.created_at_utc;
  const full = new Date(shown).toLocaleString("zh-CN");
  // Script lines sit under a day divider, so the clock alone is enough; the full stamp stays in the tooltip.
  return <><time dateTime={shown} title={compact ? full : undefined}>{compact ? new Date(shown).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : full}</time>
    {message.story_sent_at_utc && <details className="inline-hint"><summary>时间详情</summary>
      <small>离线期间的剧情时间；实际生成于 {new Date(message.created_at_utc).toLocaleString("zh-CN")}。</small>
    </details>}
  </>;
}
