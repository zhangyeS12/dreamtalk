import { useMemo, useReducer } from "react";

const sections = ["background", "media", "speech", "worldContent", "worldLocations", "characterActivity",
  "worldProfile", "generalProfile", "chat", "model"] as const;
type Section = typeof sections[number];
type Drafts = Record<Section, boolean>;
type Action = { section: Section; dirty: boolean };

function reduce(state: Drafts, { section, dirty }: Action): Drafts {
  return state[section] === dirty ? state : { ...state, [section]: dirty };
}

export function useWorkspaceDrafts() {
  const [dirty, dispatch] = useReducer(reduce, undefined, () => Object.fromEntries(
    sections.map(section => [section, false]),
  ) as Drafts);
  // Stable callbacks keep child effects from treating a parent render as an edit.
  const onDirty = useMemo(() => Object.fromEntries(sections.map(section => [section,
    (dirty: boolean) => dispatch({ section, dirty }),
  ])) as Record<Section, (dirty: boolean) => void>, []);
  return { dirty, onDirty, hasDrafts: sections.some(section => dirty[section]) };
}
