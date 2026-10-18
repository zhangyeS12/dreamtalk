import { useCallback, useEffect, useReducer, useRef } from "react";
import type { CoreClient, WorldSettings } from "@dreamtalk/api-client";

type State = { world: WorldSettings | undefined; scale: string };
type Action = { type: "read"; world: WorldSettings | undefined } | { type: "scale"; value: string };
function reduce(state: State, action: Action): State {
  if (action.type === "scale") return { ...state, scale: action.value };
  return { world: action.world, scale: action.world && action.world.time_scale !== state.world?.time_scale ? action.world.time_scale : state.scale };
}
const readError = "世界状态暂时无法更新，请检查核心连接。";

export function useWorkspaceWorld(client: CoreClient, worldId: string, onError: (value: string | ((current: string) => string)) => void) {
  const [state, dispatch] = useReducer(reduce, { world: undefined, scale: "1" });
  const active = useRef(false), revision = useRef(0);
  const read = useCallback(async (signal?: AbortSignal) => {
    const request = ++revision.current;
    const worlds = await client.listProductWorlds(signal);
    if (active.current && request === revision.current) dispatch({ type: "read", world: worlds.find(item => item.world_id === worldId) });
  }, [client, worldId]);
  useEffect(() => {
    active.current = true;
    let alive = true;
    let timer: number | undefined, failures = 0;
    const controller = new AbortController();
    const poll = async () => {
      try { await read(controller.signal); if (alive) { failures = 0; onError(current => current === readError ? "" : current); } }
      catch { if (alive) { ++failures; onError(readError); } }
      finally { if (alive) timer = window.setTimeout(() => void poll(), failures ? 10_000 : 2_000); }
    };
    void poll();
    return () => { alive = false; active.current = false; ++revision.current; controller.abort(); window.clearTimeout(timer); };
  }, [read, onError]);
  const setScale = useCallback((value: string) => dispatch({ type: "scale", value }), []);
  return { ...state, setScale, refresh: read };
}
