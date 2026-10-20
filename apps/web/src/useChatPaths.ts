import { useEffect, useRef, useState } from "react";
import { CoreClient, type ChatPathSnapshot } from "@dreamtalk/api-client";

export function useChatPaths(client: CoreClient, worldId: string, conversationId: string) {
  const key = `${worldId}/${conversationId}`;
  const current = useRef(key); current.current = key;
  const [state, setState] = useState<{ key: string; snapshot: ChatPathSnapshot | null; failed: boolean }>({ key, snapshot: null, failed: false });
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); let active = true;
    void client.chatPaths(worldId, conversationId, undefined, controller.signal)
      .then(snapshot => { if (active) setState({ key, snapshot, failed: false }); })
      .catch(() => { if (active) setState(value => ({ key, snapshot: value.key === key ? value.snapshot : null, failed: true })); });
    return () => { active = false; controller.abort(); };
  }, [client, worldId, conversationId, key, refresh]);
  const reload = async () => {
    const snapshot = await client.chatPaths(worldId, conversationId);
    if (current.current === key) setState({ key, snapshot, failed: false });
    return snapshot;
  };
  return { snapshot: state.key === key ? state.snapshot : null, failed: state.key === key && state.failed,
    busy, setBusy, open, setOpen, reload, refresh: () => setRefresh(value => value + 1) };
}

export type ChatPathsController = ReturnType<typeof useChatPaths>;
