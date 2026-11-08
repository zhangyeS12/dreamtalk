import { useLayoutEffect, useRef, useState, type RefObject, type KeyboardEventHandler } from "react";
import { ChatMessageBody } from "./ChatMessageBody";
import { maskedMarkdown } from "./privateMarkdown";
import { mentionedPeople, privacyPieces, type PrivacyPerson, type PrivacySpan } from "./chatPrivacy";
import styles from "./PrivateChat.module.css";

function alignDraftMirror(input: HTMLTextAreaElement | null, mirror: HTMLDivElement | null) {
  if (!input || !mirror?.parentElement) return;
  const layer = mirror.parentElement, computed = getComputedStyle(input);
  layer.style.font = computed.font;
  layer.style.letterSpacing = computed.letterSpacing;
  layer.style.padding = computed.padding;
  layer.style.paddingRight = `${parseFloat(computed.paddingRight) + input.offsetWidth - input.clientWidth}px`;
  mirror.style.transform = `translate(${-input.scrollLeft}px, ${-input.scrollTop}px)`;
}

export function PrivacyButton({ text, spans, people, selection, disabled, onChange, inputRef }: {
  text: string; spans: PrivacySpan[]; people: PrivacyPerson[]; selection: [number, number]; disabled: boolean;
  onChange: (spans: PrivacySpan[]) => void;
  inputRef?: RefObject<HTMLTextAreaElement | null>;
}) {
  const [start, end] = selection;
  const overlap = spans.filter(span => span.start < end && span.end > start);
  const targets = mentionedPeople(text.slice(start, end), people);
  const removing = overlap.length === 1;
  const allowed = end > start && (removing || (targets.length === 1 && overlap.length === 0 && spans.length < 32));
  const label = removing ? "取消所选片段的私密标记" : "将选中文字设为私密";
  return <button type="button" className={styles.glasses} aria-label={label} title={allowed ? label : "先选中文字，选区内须包含一个明确的 @群成员"} disabled={disabled || !allowed}
    onMouseDown={event => event.preventDefault()} onClick={() => { onChange(removing
      ? spans.filter(span => span !== overlap[0])
      : [...spans, { start, end, character_id: targets[0].character_id }].sort((a, b) => a.start - b.start));
      requestAnimationFrame(() => { inputRef?.current?.focus(); inputRef?.current?.setSelectionRange(end, end); });
    }}>
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M2 9h20M3 9l1 6c.5 2 6 2 6.5 0L11 11h2l.5 4c.5 2 6 2 6.5 0l1-6M4 9l1-3m14 3-1-3" /><path d="M4 10h6l-.5 4.5h-5zm10 0h6l-.5 4.5h-5z" fill="currentColor" /></svg>
    <span className="sr-only">{label}</span>
  </button>;
}

export function PrivateAudienceHint({ spans, people }: { spans: PrivacySpan[]; people: PrivacyPerson[] }) {
  if (!spans.length) return null;
  const names = [...new Set(spans.map(span => people.find(person => person.character_id === span.character_id)?.name ?? "已失效的角色"))];
  return <span className={styles.audiences}>{spans.length} 段私密内容 · 各段仅对应角色可见：{names.join("、")}</span>;
}

export function PrivateDraft({ text, spans, inputRef, disabled, onChange, onSelection, onKeyDown }: {
  text: string; spans: PrivacySpan[]; inputRef: RefObject<HTMLTextAreaElement | null>; disabled: boolean;
  onChange: (text: string) => void; onSelection: (selection: [number, number]) => void;
  onKeyDown: KeyboardEventHandler<HTMLTextAreaElement>;
}) {
  const mirror = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const input = inputRef.current;
    const align = () => alignDraftMirror(input, mirror.current);
    align();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(align);
    if (input) observer?.observe(input);
    return () => observer?.disconnect();
  }, [inputRef, text, spans]);
  return <div className={`${styles.draft} ${spans.length ? styles.masked : ""}`}>
    {spans.length > 0 && <div className={styles.mirror} aria-hidden="true"><div ref={mirror}>{privacyPieces(text, spans).map((part, index) => part.owner
      ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>)}{"\n"}</div></div>}
    <label htmlFor="group-chat-draft" className="sr-only">发送群聊消息</label>
    <textarea ref={inputRef} id="group-chat-draft" value={text} onChange={event => onChange(event.target.value)} onKeyDown={onKeyDown}
      onSelect={event => onSelection([event.currentTarget.selectionStart, event.currentTarget.selectionEnd])}
      onScroll={event => alignDraftMirror(event.currentTarget, mirror.current)}
      disabled={disabled} maxLength={65536} placeholder="说点什么，或用 @角色名 指定下一位发言者……" rows={1} />
  </div>;
}

function PrivateInlinePart({ text, name, character }: { text: string; name: string; character: boolean }) {
  const [open, setOpen] = useState(false);
  const control = useRef<HTMLSpanElement>(null), collapse = useRef<HTMLButtonElement>(null);
  const interacted = useRef(false);
  useLayoutEffect(() => {
    if (interacted.current) (open ? collapse.current : control.current)?.focus();
  }, [open]);
  const audience = character ? `仅你与 ${name} 可见` : `仅 ${name} 可见`;
  const toggle = (value: boolean) => { interacted.current = true; setOpen(value); };
  if (!open) return <span ref={control} role="button" tabIndex={0} className={styles.blackout} aria-expanded={false}
    aria-label={`查看私密片段，${audience}`} title={`私密 · ${audience} · 点击查看`}
    onClick={() => toggle(true)} onKeyDown={event => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(true); }
    }}><span aria-hidden="true">{text.replace(/[^\s]/gu, "█")}</span></span>;
  return <span className={styles.revealed}>
    <ChatMessageBody text={text} character={character} inline />
    <button ref={collapse} type="button" className={styles.collapse} aria-expanded={true}
      aria-label={`收起私密片段，${audience}`} title={audience} onClick={() => toggle(false)}>收起</button>
  </span>;
}

export function PrivateMessageBody({ text, spans, character, nameOf, fallback }: {
  text: string; spans: PrivacySpan[]; character: boolean; nameOf: (id: string) => string;
  fallback?: boolean | null;
}) {
  if (!spans.length) return <ChatMessageBody text={text} character={character} />;
  const { source, prefix, slots } = maskedMarkdown(text, spans);
  return <div className={styles.body} key={JSON.stringify([text, spans, character])}>
    {character && fallback === true && <p className={styles.protection}>这条回复的公开／私密范围未能确认，暂按私密保护。</p>}
    <ChatMessageBody text={source} character={character} masks={{ prefix, count: slots.length,
      render: index => <PrivateInlinePart key={index} text={slots[index].text} name={nameOf(slots[index].owner)} character={character} /> }} />
  </div>;
}
