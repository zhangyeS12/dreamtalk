import { useEffect, useState } from "react";
import { CoreClient, type CoreConnection } from "@livingworld/api-client";
import { Inspector } from "./Inspector";

interface Props {
  discover: () => Promise<CoreConnection>;
  onReady?: (generation: string) => Promise<void>;
}

export function App({ discover, onReady }: Props) {
  const [state, setState] = useState<"Connecting" | "Ready" | "Failed">("Connecting");
  const [client, setClient] = useState<CoreClient | null>(null);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => { controller.abort(); if (active) setState("Failed"); }, 15_000);
    async function connect() {
      try {
        const connection = await discover();
        if (!active || controller.signal.aborted) throw new Error("connection_cancelled");
        const connected = new CoreClient(connection);
        await connected.health(controller.signal);
        if (active) {
          setState("Ready");
          setClient(connected);
          await onReady?.(connection.generation);
        }
      } catch {
        if (active) setState("Failed");
      } finally { clearTimeout(timeout); }
    }
    void connect();
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [discover, onReady]);
  const stateLabel = { Connecting: "正在连接核心", Ready: "核心已就绪", Failed: "核心连接失败" }[state];
  return <main><div className="brand"><h1>LivingWorld</h1><p role="status" aria-live="polite">{stateLabel}</p></div>{state === "Ready" && client ? <Inspector client={client} /> : null}</main>;
}
