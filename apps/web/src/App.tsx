import { useEffect, useState } from "react";
import { CoreClient, type CoreConnection } from "@livingworld/api-client";

interface Props {
  discover: () => Promise<CoreConnection>;
  onReady?: (generation: string) => Promise<void>;
}

export function App({ discover, onReady }: Props) {
  const [state, setState] = useState<"Connecting" | "Ready" | "Failed">("Connecting");
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => { controller.abort(); if (active) setState("Failed"); }, 15_000);
    async function connect() {
      try {
        const connection = await discover();
        if (!active || controller.signal.aborted) throw new Error("connection_cancelled");
        await new CoreClient(connection).health(controller.signal);
        if (active) {
          setState("Ready");
          await onReady?.(connection.generation);
        }
      } catch {
        if (active) setState("Failed");
      } finally { clearTimeout(timeout); }
    }
    void connect();
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [discover, onReady]);
  return <main><h1>LivingWorld</h1><p role="status" aria-live="polite">Core {state}</p></main>;
}
