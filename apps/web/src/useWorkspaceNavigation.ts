import { useCallback, useReducer } from "react";
import type { SettingsPage } from "./SettingsHandbook";

export type WorkspaceTab = "chats" | "contacts" | "settings" | "me";
type Navigation = { tab: WorkspaceTab; meVisited: boolean; contactsVisited: boolean; settingsPage: SettingsPage };
type Action = { type: "tab"; tab: WorkspaceTab } | { type: "settings"; page: SettingsPage };

function reduce(state: Navigation, action: Action): Navigation {
  if (action.type === "settings") return { ...state, settingsPage: action.page };
  return { ...state, tab: action.tab, meVisited: state.meVisited || action.tab === "me",
    contactsVisited: state.contactsVisited || action.tab === "contacts" };
}

export function useWorkspaceNavigation(initialTab: WorkspaceTab) {
  const [state, dispatch] = useReducer(reduce, initialTab, (tab): Navigation => ({ tab,
    meVisited: tab === "me", contactsVisited: tab === "contacts", settingsPage: "model" }));
  const setTab = useCallback((tab: WorkspaceTab) => dispatch({ type: "tab", tab }), []);
  const setSettingsPage = useCallback((page: SettingsPage) => dispatch({ type: "settings", page }), []);
  return { ...state, setTab, setSettingsPage };
}
