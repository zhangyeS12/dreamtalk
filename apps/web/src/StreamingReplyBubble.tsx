import { ContactAvatar } from "./ContactSocial";

export function StreamingReplyBubble({ name, text, avatarUrl }: { name: string; text: string; avatarUrl?: string }) {
  return <li className="message-row" aria-label={`${name}正在回复`}>
    <ContactAvatar name={name} url={avatarUrl} className="message-portrait" />
    <div className="message-bubble streaming-bubble">
      <span className="message-sender">{name}</span>
      <p className="streaming-text">{text || "正在准备回复…"}</p>
      <small className="streaming-label">正在生成 · 完成后保存</small>
    </div>
  </li>;
}
