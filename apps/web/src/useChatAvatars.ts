import { useEffect, useMemo, useState } from "react";
import type { CoreClient } from "@dreamtalk/api-client";

// Read only requested avatar bindings; never build the world relationship graph.
export function useChatAvatars(client: CoreClient, worldId: string, roots: string[], visible: boolean) {
  const key = [...new Set(roots)].sort().join(",");
  const token = useMemo(() => Symbol("avatar read"), [client, worldId, key, visible]);
  const [result, setResult] = useState<{ token: symbol; urls: Record<string, string> } | null>(null);
  useEffect(() => {
    if (!visible || !key) return;
    const abort = new AbortController();
    const created: string[] = [];
    let active = true;
    void client.avatarDigests(worldId, key.split(","), abort.signal).then(async people => {
      if (!active) return;
      const digests = [...new Set(people.map(person => person.digest))];
      const byDigest = new Map<string, string>();
      // Keep optional artwork downloads bounded even with many conversations.
      for (let offset = 0; offset < digests.length && active; offset += 8) {
        const images = await Promise.all(digests.slice(offset, offset + 8).map(async digest => {
          try {
            const blob = await client.coverImage(worldId, digest, abort.signal);
            if (!active) return null;
            const url = URL.createObjectURL(blob); created.push(url);
            return [digest, url] as const;
          } catch { return null; }
        }));
        for (const pair of images) if (pair) byDigest.set(pair[0], pair[1]);
      }
      if (!active) return;
      setResult({ token, urls: Object.fromEntries(people.flatMap(person => {
        const url = byDigest.get(person.digest);
        return url ? [[person.root_import_id, url]] : [];
      })) });
    }).catch(() => { /* Avatars are optional; the actual character name remains available. */ });
    return () => { active = false; abort.abort(); created.forEach(URL.revokeObjectURL); };
  }, [client, worldId, key, visible, token]);
  return visible && result?.token === token ? result.urls : {};
}
