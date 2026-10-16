import { useCallback, useEffect, useState } from "react";
import { CoreClient, type CoreConnection } from "@dreamtalk/api-client";
import { Inspector } from "./Inspector";
import { ProductApp } from "./ProductApp";
import { StartupSplash } from "./StartupSplash";
import { Brand } from "./Brand";
import { SaveSafetyGate } from "./SaveBackups";
import { DesktopUpdateEntry, DesktopUpdateProvider } from "./DesktopUpdates";

interface Props {
  discover: () => Promise<CoreConnection>;
  recover?: () => Promise<CoreConnection>;
  onReady?: (generation: string) => Promise<void>;
}

export function App({ discover, recover, onReady }: Props) {
  const [ready, setReady] = useState(false);
  const revealed = useCallback(() => setReady(true), []);
  return <DesktopUpdateProvider ready={ready}><SaveSafetyGate>{storageReady => <ConnectedApp storageReady={storageReady} discover={discover} recover={recover} onReady={onReady} onRevealed={revealed} />}</SaveSafetyGate></DesktopUpdateProvider>;
}

function ConnectedApp({ discover, recover, onReady, onRevealed, storageReady }: Props & { onRevealed: () => void; storageReady: boolean }) {
  const [state, setState] = useState<"Connecting" | "Ready" | "Failed">("Connecting");
  const [client, setClient] = useState<CoreClient | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [archive, setArchive] = useState<"Pending" | "Ready" | "Failed">("Pending");
  const [revealed, setRevealed] = useState(false);
  const developer = new URLSearchParams(window.location.search).get("developer") === "1";
  const archiveStatus = useCallback((success: boolean) => setArchive(current => current === "Pending" ? success ? "Ready" : "Failed" : current), []);
  const complete = useCallback(() => { setRevealed(true); onRevealed(); }, [onRevealed]);
  const retry = useCallback(() => {
    setState("Connecting"); setClient(null); setArchive("Pending"); setRevealed(false);
    setAttempt(value => value + 1);
  }, []);
  useEffect(() => {
    // Keep the original splash mounted while the save gate is pending. Discovery
    // and its timeout start only after the existing storage checks allow access.
    if (!storageReady) {
      setState("Connecting"); setClient(null); setArchive("Pending"); setRevealed(false);
      return;
    }
    let active = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => { controller.abort(); if (active) setState("Failed"); }, 60_000);
    async function connect() {
      try {
        const connection = await (attempt > 0 && recover ? recover() : discover());
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
  }, [discover, recover, onReady, attempt, storageReady]);
  useEffect(() => {
    if (!client || developer || archive !== "Pending") return;
    const timer = setTimeout(() => setArchive("Failed"), 15_000);
    return () => clearTimeout(timer);
  }, [client, developer, archive]);
  const ready = storageReady && state === "Ready" && (developer || archive === "Ready");
  const failed = storageReady && (state === "Failed" || archive === "Failed");
  return <>
    {storageReady && client && state === "Ready" && <div className="startup-destination" inert={!revealed} aria-hidden={!revealed}>
      {developer ? <main><div className="brand"><Brand /><p role="status">核心已就绪</p></div><Inspector client={client} /></main>
        : <ProductApp key={attempt} client={client} onStartupStatus={archiveStatus} />}
    </div>}
    {(!storageReady || !revealed) && <StartupSplash key={attempt} ready={ready} failed={failed} onRetry={retry} onComplete={complete} />}
    {failed && <div className="startup-update-entry"><DesktopUpdateEntry /></div>}
  </>;
}
