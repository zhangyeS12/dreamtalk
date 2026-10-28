/**
 * A stable personal colour per character, used only for names, avatar
 * fallbacks and the script rule beside their lines. Derived from the
 * identity string; it carries no relationship or status meaning.
 */
const TINTS = ["#f2c6d4", "#ffd9a3", "#b9d4ff", "#cfc6ff", "#bfe8d8", "#ffc8b0", "#dde8a8", "#a8e0f0", "#f0c2ec", "#c8d8c0", "#ffe3c2", "#d4c2ff"] as const;

function slot(identity: string): number {
  let hash = 2166136261;
  for (const char of identity) hash = Math.imul(hash ^ char.codePointAt(0)!, 16777619);
  return (hash >>> 0) % TINTS.length;
}

export function characterTint(identity: string): string {
  return TINTS[slot(identity)];
}

/** Tints for people shown together: each keeps their own colour unless two would collide. */
export function companyTints(identities: readonly string[]): Map<string, string> {
  const used = new Set<number>(), result = new Map<string, string>();
  for (const identity of identities) {
    let index = slot(identity);
    for (let step = 0; step < TINTS.length && used.has(index); step++) index = (index + 1) % TINTS.length;
    used.add(index); result.set(identity, TINTS[index]);
  }
  return result;
}
