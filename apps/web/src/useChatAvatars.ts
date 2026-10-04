import { useEffect, useMemo, useState } from "react";
import type { CoreClient } from "@dreamtalk/api-client";

// One world-local read for the directory and transcript; never one request per bubble.
export function useChatAvatars(client: CoreClient, worldId: string, roots: string[], visible: boolean) {
  const key = [...new Set(roots)].sort().join(",");
  const token = useMemo(() => Symbol("avatar read"), [client, worldId, key, visible]);
  const [result, setResult] = useState<{ token: symbol; urls: Record<string, string> } | null>(null);
  useEffect(() => {
    if (!visible || !key) return;
    const abort = new AbortController();
    const created: string[] = [];
    let active = true;
    void client.socialSnapshot(worldId, abort.signal).then(async social => {
      const wanted = new Set(key.split(","));
      const people = social.characters.filter(person => wanted.has(person.root_import_id) && person.avatar_digest);
      const digests = [...new Set(people.map(person => person.avatar_digest!))];
      const images = await Promise.all(digests.map(async digest => {
        try {
          const blob = await client.coverImage(worldId, digest, abort.signal);
          if (!active) return null;
          const url = URL.createObjectURL(blob); created.push(url);
          return [digest, url] as const;
        } catch { return null; }
      }));
      if (!active) return;
      const byDigest = new Map(images.filter((image): image is readonly [string, string] => !!image));
      setResult({ token, urls: Object.fromEntries(people.flatMap(person => {
        const url = byDigest.get(person.avatar_digest!);
        return url ? [[person.root_import_id, url]] : [];
      })) });
    }).catch(() => { /* Avatars are optional; the actual character name remains available. */ });
    return () => { active = false; abort.abort(); created.forEach(URL.revokeObjectURL); };
  }, [client, worldId, key, visible, token]);
  return visible && result?.token === token ? result.urls : {};
}
