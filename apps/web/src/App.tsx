import { useCallback, useEffect, useState } from "react";
import { CoreClient, type CoreConnection } from "@dreamtalk/api-client";
import { Inspector } from "./Inspector";
import { ProductApp } from "./ProductApp";
import { StartupSplash } from "./StartupSplash";
import { Brand } from "./Brand";

interface Props {
  discover: () => Promise<CoreConnection>;
  onReady?: (generation: string) => Promise<void>;
}

export function App({ discover, onReady }: Props) {
  const [state, setState] = useState<"Connecting" | "Ready" | "Failed">("Connecting");
  const [client, setClient] = useState<CoreClient | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [archive, setArchive] = useState<"Pending" | "Ready" | "Failed">("Pending");
  const [revealed, setRevealed] = useState(false);
  const developer = new URLSearchParams(window.location.search).get("developer") === "1";
  const archiveStatus = useCallback((success: boolean) => setArchive(current => current === "Pending" ? success ? "Ready" : "Failed" : current), []);
  const complete = useCallback(() => setRevealed(true), []);
  const retry = useCallback(() => {
    setState("Connecting"); setClient(null); setArchive("Pending"); setRevealed(false);
    setAttempt(value => value + 1);
  }, []);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => { controller.abort(); if (active) setState("Failed"); }, 15_000);
    async function connect() {
      try {
        const connection = await discover();
        if (!active || controller.signal.aborted) return;
        const connected = new CoreClient(connection);
        await connected.health(controller.signal);
        if (!active || controller.signal.aborted) return;
        await onReady?.(connection.generation);
        if (active && !controller.signal.aborted) { setClient(connected); setState("Ready"); }
      } catch {
        if (active) setState("Failed");
      } finally { clearTimeout(timeout); }
    }
    void connect();
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [discover, onReady, attempt]);
  useEffect(() => {
    if (!client || developer || archive !== "Pending") return;
    const timer = setTimeout(() => setArchive("Failed"), 15_000);
    return () => clearTimeout(timer);
  }, [client, developer, archive]);
  const ready = state === "Ready" && (developer || archive === "Ready");
  const failed = state === "Failed" || archive === "Failed";
  return <>
    {client && state === "Ready" && <div className="startup-destination" inert={!revealed} aria-hidden={!revealed}>
      {developer ? <main><div className="brand"><Brand /><p role="status">核心已就绪</p></div><Inspector client={client} /></main>
        : <ProductApp key={attempt} client={client} onStartupStatus={archiveStatus} startupReady={revealed} />}
    </div>}
    {!revealed && <StartupSplash key={attempt} ready={ready} failed={failed} onRetry={retry} onComplete={complete} />}
  </>;
}
