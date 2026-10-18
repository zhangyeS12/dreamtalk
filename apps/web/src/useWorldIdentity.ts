import { useCallback, useEffect, useReducer, useRef } from "react";
import type { CoreClient, PlayerAvailability, SelectablePlayer, SelectedPlayerState } from "@dreamtalk/api-client";

type Identity = { players: SelectablePlayer[]; selected: SelectedPlayerState | null; choice: string };
type Action = { type: "reset" } | { type: "loaded"; players: SelectablePlayer[]; selected: SelectedPlayerState }
  | { type: "choice"; choice: string } | { type: "availability"; player: string; selected: SelectedPlayerState };
const empty: Identity = { players: [], selected: null, choice: "" };
function reduce(state: Identity, action: Action): Identity {
  switch (action.type) {
    case "reset": return empty;
    case "choice": return { ...state, choice: action.choice };
    case "loaded": return { players: action.players, selected: action.selected,
      choice: action.selected.player_id ?? action.players[0]?.player_id ?? "" };
    case "availability": return state.selected?.player_id === action.player && action.selected.player_id === action.player
      ? { ...state, selected: action.selected } : state;
  }
}

export function useWorldIdentity(client: CoreClient, worldId: string, onError: (message: string) => void) {
  const [state, dispatch] = useReducer(reduce, empty);
  const revision = useRef(0);
  const mounted = useRef(false);
  const reload = useCallback(async () => {
    const request = ++revision.current;
    const [players, selected] = await Promise.all([client.listPlayers(worldId), client.selectedPlayer(worldId)]);
    if (mounted.current && request === revision.current) dispatch({ type: "loaded", players, selected });
  }, [client, worldId]);
  useEffect(() => {
    mounted.current = true;
    dispatch({ type: "reset" });
    const request = revision.current + 1;
    void reload().catch(() => { if (mounted.current && revision.current === request) onError("无法读取当前世界的玩家身份。"); });
    return () => { mounted.current = false; ++revision.current; };
  }, [reload, onError]);
  const setPlayerChoice = useCallback((choice: string) => dispatch({ type: "choice", choice }), []);
  const bind = useCallback(async (player: string) => {
    const request = revision.current;
    await client.bindPlayer(worldId, player);
    if (mounted.current && request === revision.current) await reload();
  }, [client, worldId, reload]);
  const startAtHome = useCallback(async () => {
    const request = revision.current;
    await client.startAtHome(worldId);
    if (mounted.current && request === revision.current) await reload();
  }, [client, worldId, reload]);
  const availability = useCallback(async (next: PlayerAvailability, expectedRevision: number, player: string) => {
    const request = revision.current;
    await client.setPlayerAvailability(worldId, next, expectedRevision, crypto.randomUUID());
    const selected = await client.selectedPlayer(worldId);
    if (mounted.current && request === revision.current) dispatch({ type: "availability", selected, player });
  }, [client, worldId]);
  return { players: state.players, selectedPlayer: state.selected?.player_id ?? null,
    selectedPlayerState: state.selected, playerChoice: state.choice, setPlayerChoice, bind, startAtHome, availability };
}
