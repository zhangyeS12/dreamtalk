export type PrivacySpan = { start: number; end: number; character_id: string };
export type PrivacyPerson = { character_id: string; name: string };
const boundary = (text: string, index: number) => index === 0 || index === text.length
  || !(text.charCodeAt(index - 1) >= 0xD800 && text.charCodeAt(index - 1) <= 0xDBFF && text.charCodeAt(index) >= 0xDC00 && text.charCodeAt(index) <= 0xDFFF);

export function mentionedPeople(text: string, people: PrivacyPerson[]) {
  return people.filter(person => {
    const name = person.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(^|\\s)@${name}(?=$|\\s|[,.!?，。！？：:（(])`, "u").test(text);
  });
}

/** Keep inserted/replaced text private when the edit touches a private span. */
export function movePrivacy(before: string, after: string, spans: PrivacySpan[]): PrivacySpan[] {
  if (before === after) return spans;
  let start = 0, oldEnd = before.length, newEnd = after.length;
  while (start < oldEnd && start < newEnd && before[start] === after[start]) start++;
  while (oldEnd > start && newEnd > start && before[oldEnd - 1] === after[newEnd - 1]) { oldEnd--; newEnd--; }
  if (!boundary(before, start) || !boundary(after, start)) start--;
  if (!boundary(before, oldEnd) || !boundary(after, newEnd)) { oldEnd++; newEnd++; }
  const delta = newEnd - oldEnd;
  return spans.flatMap(span => {
    if (span.end < start || (span.end === start && oldEnd !== start)) return [span];
    if (span.start > oldEnd || (span.start === oldEnd && oldEnd !== start)) return [{ ...span, start: span.start + delta, end: span.end + delta }];
    const next = { ...span, start: Math.min(span.start, start), end: span.end > oldEnd ? span.end + delta : newEnd };
    return next.end > next.start ? [next] : [];
  });
}

export function privacyError(text: string, spans: PrivacySpan[], people: PrivacyPerson[]): string | null {
  let previous = 0;
  if (spans.length > 32) return "一条消息最多标记 32 段私密内容。";
  for (const span of spans) {
    const targets = mentionedPeople(text.slice(span.start, span.end), people);
    if (span.start < previous || span.end <= span.start || span.end > text.length || !boundary(text, span.start) || !boundary(text, span.end) || targets.length !== 1 || targets[0].character_id !== span.character_id) {
      return "私密片段需要保留一个明确的 @群成员。请修正文字或明确取消该段私密标记后再发送。";
    }
    previous = span.end;
  }
  return null;
}

export function privacyPieces(text: string, spans: PrivacySpan[]) {
  const pieces: { text: string; owner?: string }[] = [];
  let offset = 0;
  for (const span of spans) {
    if (span.start > offset) pieces.push({ text: text.slice(offset, span.start) });
    pieces.push({ text: text.slice(span.start, span.end), owner: span.character_id });
    offset = span.end;
  }
  if (offset < text.length) pieces.push({ text: text.slice(offset) });
  return pieces;
}
