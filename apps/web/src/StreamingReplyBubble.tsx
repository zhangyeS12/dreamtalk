import type { CSSProperties } from "react";
import { ChatMessageBody } from "./ChatMessageBody";
import { threadStyles as styles } from "./world/chat/ThreadParts";

/** The reply as it arrives, laid out like a finished script line. */
export function StreamingReplyBubble({ name, text, tint }: { name: string; text: string; tint?: string }) {
  return <li className={`${styles.line} ${styles.streaming}`} style={tint ? { "--tint": tint } as CSSProperties : undefined} aria-label={`${name}正在回复`}>
    <div className={styles.name}><span>{name}</span></div>
    <div className={styles.text}>
      {text ? <ChatMessageBody text={text} character /> : <p className={styles.streamingLabel}>正在准备回复…</p>}
      <small className={styles.streamingLabel}><i /><i /><i />正在生成 · 完成后保存</small>
    </div>
  </li>;
}
