/** 32-bit FNV-1a over code points: a stable, non-cryptographic choice from a name or ID. */
export function stableHash(text: string): number {
  let hash = 2166136261;
  for (const char of text) hash = Math.imul(hash ^ char.codePointAt(0)!, 16777619);
  return hash >>> 0;
}
