import type { CoreClient, ContentEditorDraft, ContentEditorEntry, ContentEditorPage } from "@dreamtalk/api-client";

type Patch = Parameters<CoreClient["previewContentChanges"]>[2];
const equal = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);

/** Unloaded entries never appear in a deletion list or a whole-book replacement. */
export class ContentEditorPages {
  original: ContentEditorDraft | null = null;
  originals = new Map<string, ContentEditorEntry>();
  pages = new Map<number, ContentEditorEntry[]>();
  offset = 0;
  total = 0;

  reset() { this.original = null; this.originals.clear(); this.pages.clear(); this.offset = 0; this.total = 0; }
  accept(page: ContentEditorPage) {
    this.original ??= { ...page.draft, entries: [] };
    this.total = page.total_entries; this.offset = page.offset;
    this.pages.set(page.offset, page.draft.entries);
    for (const entry of page.draft.entries) if (entry.source_entry_id) this.originals.set(entry.source_entry_id, entry);
  }
  capture(entries: ContentEditorEntry[]) { this.pages.set(this.offset, entries); }
  changed(draft: ContentEditorDraft): boolean {
    const patch = this.patch(draft);
    return Boolean(Object.keys(patch.fields).length || patch.updates?.length || patch.removed?.length || patch.added?.length);
  }
  patch(draft: ContentEditorDraft): Patch {
    if (!this.original) throw new Error("editor_source_required");
    const fields: Patch["fields"] = {};
    for (const key of Object.keys(this.original) as (keyof ContentEditorDraft)[]) {
      if (key === "entries" || key === "kind") continue;
      if (!equal(this.original[key], draft[key])) (fields as Record<string, unknown>)[key] = draft[key];
    }
    const entries = [...this.pages].flatMap(([offset, entries]) => offset === this.offset ? draft.entries : entries);
    const remaining = new Set(entries.flatMap(entry => entry.source_entry_id ? [entry.source_entry_id] : []));
    const updates: Patch["updates"] = [];
    for (const entry of entries) {
      if (!entry.source_entry_id) continue;
      const original = this.originals.get(entry.source_entry_id);
      if (!original) throw new Error("editor_entry_source_required");
      const change: NonNullable<Patch["updates"]>[number]["fields"] = {};
      for (const key of Object.keys(entry) as (keyof ContentEditorEntry)[]) {
        if (key !== "source_entry_id" && !equal(original[key], entry[key])) (change as Record<string, unknown>)[key] = entry[key];
      }
      if (Object.keys(change).length) updates.push({ source_entry_id: entry.source_entry_id, fields: change });
    }
    return { fields, updates, added: entries.filter(entry => !entry.source_entry_id),
      removed: [...this.originals.keys()].filter(id => !remaining.has(id)) };
  }
}
