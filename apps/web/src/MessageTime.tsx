import type { ChatMessage } from "@dreamtalk/api-client";
export function MessageTime({ message }: { message: ChatMessage }) {
  const shown = message.story_sent_at_utc ?? message.created_at_utc;
  return <><time dateTime={shown}>{new Date(shown).toLocaleString("zh-CN")}</time>
    {message.story_sent_at_utc && <details className="inline-hint"><summary>时间详情</summary>
      <small>离线期间的剧情时间；实际生成于 {new Date(message.created_at_utc).toLocaleString("zh-CN")}。</small>
    </details>}
  </>;
}
