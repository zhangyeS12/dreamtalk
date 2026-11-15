import { useCallback, useRef, useState } from "react";
import type { CoreClient } from "@dreamtalk/api-client";
import { WorldContacts, WorldImports } from "../WorldContent";
import type { ChatVisualState } from "../useChatVisuals";
import { mobileInvoke } from "./native";

export function MobileContacts({ client, worldId, refreshKey, busy, onOpenChat, onSaved, onDirtyChange, visualState, onSelectedRootChange }: {
  client: CoreClient; worldId: string; refreshKey: number; busy: boolean;
  onOpenChat: (importId: string) => Promise<void>; onSaved: () => void; onDirtyChange: (dirty: boolean) => void;
  visualState: ChatVisualState; onSelectedRootChange: (root: string | null) => void;
}) {
  const [imports, setImports] = useState(false), [importDraft, setImportDraft] = useState(false);
  const parts = useRef({ imports: false, catalog: false, position: false });
  const report = useCallback((part: keyof typeof parts.current, dirty: boolean) => {
    parts.current[part] = dirty; if (part === "imports") setImportDraft(dirty); onDirtyChange(Object.values(parts.current).some(Boolean));
  }, [onDirtyChange]);
  const importDirty = useCallback((dirty: boolean) => report("imports", dirty), [report]);
  const catalogDirty = useCallback((dirty: boolean) => report("catalog", dirty), [report]);
  const positionDirty = useCallback((dirty: boolean) => report("position", dirty), [report]);
  const showImports = () => setImports(true);
  return <section className="mobile-contacts mobile-settings">
    <div className="mobile-section-heading"><h2>通讯录</h2><button aria-expanded={imports} onClick={() => {
      if (!imports || !parts.current.imports || window.confirm("角色卡或世界书有未保存的编辑，确定收起吗？")) setImports(value => !value);
    }}>{imports ? "收起卡片管理" : "角色卡／世界书"}</button></div>
    {imports && <section className="mobile-contact-panel" aria-label="角色卡和世界书管理"><WorldImports client={client} worldId={worldId} refreshKey={refreshKey} onSaved={onSaved} onDirtyChange={importDirty} /></section>}
    <WorldContacts compact nativeInvoke={mobileInvoke} client={client} worldId={worldId} refreshKey={refreshKey}
      onSettings={showImports} onIdentity={() => {}} onOpenChat={async id => {
        if (parts.current.imports && !window.confirm("角色卡或世界书有未保存的编辑，确定打开会话吗？")) return;
        await onOpenChat(id);
      }} canOpenChat openingChat={busy} removalDisabled={busy || importDraft} onRemoved={onSaved}
      onLocationDirty={catalogDirty} onCharacterLocationDirty={positionDirty}
      visualState={visualState} onSelectedRootChange={onSelectedRootChange} />
  </section>;
}
