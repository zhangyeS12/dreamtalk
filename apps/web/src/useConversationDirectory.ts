import { useCallback, useEffect, useReducer } from "react";
import type { CoreClient, ChatConversation, GroupChatConversation } from "@dreamtalk/api-client";

type Scope = { worldId: string; playerId: string };
type Directory<T> = Scope & { items: T[] };
type Selection = { kind: "direct" | "group"; id: string } | null;
type State = {
  direct: Directory<ChatConversation> | null; groups: Directory<GroupChatConversation> | null;
  selection: Selection; groupSetupOpen: boolean; loading: boolean; failed: boolean; refresh: number; search: string;
};
type Action =
  | { type: "read-started" | "read-failed" | "read-finished" | "refresh" | "begin-group" | "close-group" }
  | { type: "direct-loaded"; scope: Scope; items: ChatConversation[] }
  | { type: "groups-loaded"; scope: Scope; items: GroupChatConversation[] }
  | { type: "direct-opened"; scope: Scope; item: ChatConversation }
  | { type: "group-created"; scope: Scope; item: GroupChatConversation }
  | { type: "pinned"; scope: Scope; kind: "direct" | "group"; id: string; pinned: boolean }
  | { type: "group-removed"; scope: Scope; id: string }
  | { type: "select"; selection: Selection }
  | { type: "search"; value: string };

const initialState: State = { direct: null, groups: null, selection: null, groupSetupOpen: false,
  loading: false, failed: false, refresh: 0, search: "" };
function sameScope(value: Scope | null, scope: Scope): boolean {
  return value?.worldId === scope.worldId && value.playerId === scope.playerId;
}
function mergeRead<T extends { conversation_id: string }>(current: Directory<T> | null, scope: Scope, items: T[]): Directory<T> {
  const local = sameScope(current, scope) ? current!.items : [];
  return { ...scope, items: [...items, ...local.filter(item => !items.some(remote => remote.conversation_id === item.conversation_id))] };
}
function upsert<T extends { conversation_id: string }>(current: Directory<T> | null, scope: Scope, item: T): Directory<T> {
  return { ...scope, items: [...(sameScope(current, scope) ? current!.items : []).filter(old => old.conversation_id !== item.conversation_id), item] };
}
function reduce(state: State, action: Action): State {
  switch (action.type) {
    case "read-started": return { ...state, loading: true, failed: false };
    case "read-failed": return { ...state, failed: true };
    case "read-finished": return { ...state, loading: false };
    case "refresh": return { ...state, refresh: state.refresh + 1 };
    case "direct-loaded": return { ...state, direct: mergeRead(state.direct, action.scope, action.items) };
    case "groups-loaded": return { ...state, groups: mergeRead(state.groups, action.scope, action.items) };
    case "direct-opened": return { ...state, direct: upsert(state.direct, action.scope, action.item),
      selection: { kind: "direct", id: action.item.conversation_id }, groupSetupOpen: false };
    case "group-created": return { ...state, groups: upsert(state.groups, action.scope, action.item),
      selection: { kind: "group", id: action.item.conversation_id }, groupSetupOpen: false };
    case "pinned": {
      if (action.kind === "direct") {
        if (!sameScope(state.direct, action.scope)) return state;
        return { ...state, direct: { ...state.direct!, items: state.direct!.items.map(item => item.conversation_id === action.id ? { ...item, pinned: action.pinned } : item) } };
      }
      if (!sameScope(state.groups, action.scope)) return state;
      return { ...state, groups: { ...state.groups!, items: state.groups!.items.map(item => item.conversation_id === action.id ? { ...item, pinned: action.pinned } : item) } };
    }
    case "group-removed": return { ...state, groups: sameScope(state.groups, action.scope)
      ? { ...state.groups!, items: state.groups!.items.filter(item => item.conversation_id !== action.id) } : state.groups, selection: null };
    case "select": return { ...state, selection: action.selection, groupSetupOpen: false };
    case "begin-group": return { ...state, groupSetupOpen: true, selection: null };
    case "close-group": return { ...state, groupSetupOpen: false };
    case "search": return { ...state, search: action.value };
  }
}

export function useConversationDirectory(client: CoreClient, worldId: string, playerId: string | null,
  enabled: boolean, contactsRefresh: number, unreadDirectoryKey: string, onError: (message: string) => void) {
  const [state, dispatch] = useReducer(reduce, initialState);
  useEffect(() => {
    let active = true;
    if (!worldId || !playerId || !enabled) return;
    const controller = new AbortController();
    const scope = { worldId, playerId };
    dispatch({ type: "read-started" });
    const direct = client.conversations(worldId, controller.signal).then(items => {
      if (active) dispatch({ type: "direct-loaded", scope, items });
    }).catch(() => { if (active) { dispatch({ type: "read-failed" }); onError("无法读取当前世界的会话，请重新读取或检查核心连接。"); } });
    const groups = client.groupConversations(worldId, controller.signal).then(items => {
      if (active) dispatch({ type: "groups-loaded", scope, items });
    }).catch(() => { if (active) { dispatch({ type: "read-failed" }); onError("无法读取当前世界的群聊，请重新读取或检查核心连接。"); } });
    void Promise.allSettled([direct, groups]).finally(() => { if (active) dispatch({ type: "read-finished" }); });
    return () => { active = false; controller.abort(); };
  }, [client, worldId, playerId, enabled, contactsRefresh, unreadDirectoryKey, state.refresh, onError]);
  const select = useCallback((kind: "direct" | "group", id: string) => dispatch({ type: "select", selection: { kind, id } }), []);
  const clearSelection = useCallback(() => dispatch({ type: "select", selection: null }), []);
  const beginGroup = useCallback(() => dispatch({ type: "begin-group" }), []);
  const closeGroup = useCallback(() => dispatch({ type: "close-group" }), []);
  const refresh = useCallback(() => dispatch({ type: "refresh" }), []);
  const search = useCallback((value: string) => dispatch({ type: "search", value }), []);
  const opened = useCallback((scope: Scope, item: ChatConversation) => dispatch({ type: "direct-opened", scope, item }), []);
  const created = useCallback((scope: Scope, item: GroupChatConversation) => dispatch({ type: "group-created", scope, item }), []);
  const removed = useCallback((scope: Scope, id: string) => dispatch({ type: "group-removed", scope, id }), []);
  const setPinned = useCallback((scope: Scope, kind: "direct" | "group", id: string, pinned: boolean) => dispatch({ type: "pinned", scope, kind, id, pinned }), []);
  const scope = { worldId, playerId: playerId ?? "" };
  return { conversations: sameScope(state.direct, scope) ? state.direct!.items : [],
    groups: sameScope(state.groups, scope) ? state.groups!.items : [],
    selectedConversationId: state.selection?.kind === "direct" ? state.selection.id : null,
    selectedGroupId: state.selection?.kind === "group" ? state.selection.id : null,
    groupSetupOpen: state.groupSetupOpen, conversationsLoading: state.loading, conversationsFailed: state.failed,
    conversationSearch: state.search, select, clearSelection, beginGroup, closeGroup, refresh, search, opened, created, removed, setPinned };
}
