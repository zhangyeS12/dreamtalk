import { useEffect, useMemo, useState } from "react";
import { BookOpen, ChevronRight, Moon, Sparkles } from "lucide-react";
import type { CoreClient, WorldSettings } from "@dreamtalk/api-client";

export function MobileWorldCards({ client, worlds, onEnter }: { client: CoreClient; worlds: WorldSettings[]; onEnter: (world: WorldSettings) => void }) {
  const key = worlds.slice(0, 12).map(world => world.world_id).sort().join(",");
  const scope = useMemo(() => ({ client, key }), [client, key]);
  const [art, setArt] = useState<{ scope: typeof scope; urls: Record<string, string> } | null>(null);
  useEffect(() => {
    if (!key) return;
    const abort = new AbortController(), urls: string[] = [];
    let active = true;
    async function read() {
      try {
        const covers = await client.listWorldCovers(), wanted = new Set(key.split(","));
        const selected = covers.filter(cover => wanted.has(cover.world_id) && cover.faces.front?.display).slice(0, 12);
        const result: Record<string, string> = {};
        for (let offset = 0; active && offset < selected.length; offset += 2) {
          await Promise.all(selected.slice(offset, offset + 2).map(async cover => {
            try {
              const blob = await client.coverImage(cover.world_id, cover.faces.front!.display.digest, abort.signal);
              if (!active) return;
              const bitmap = await createImageBitmap(blob);
              try {
                if (!active) return;
                const canvas = document.createElement("canvas"); canvas.width = 640; canvas.height = 360;
                const context = canvas.getContext("2d"); if (!context) return;
                const scale = Math.max(640 / bitmap.width, 360 / bitmap.height);
                context.drawImage(bitmap, (640 - bitmap.width * scale) / 2, (360 - bitmap.height * scale) / 2, bitmap.width * scale, bitmap.height * scale);
                const thumbnail = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/webp", .82));
                if (!active || !thumbnail) return;
                const url = URL.createObjectURL(thumbnail); urls.push(url); result[cover.world_id] = url;
              } finally { bitmap.close(); }
            } catch { /* Optional artwork never prevents opening a real world. */ }
          }));
          if (active) setArt({ scope, urls: { ...result } });
        }
      } catch { /* Keep world names and navigation usable when covers are unavailable. */ }
    }
    void read();
    return () => { active = false; abort.abort(); urls.forEach(URL.revokeObjectURL); };
  }, [client, key, scope]);
  const urls = art?.scope === scope ? art.urls : {};
  return <ul className="mobile-world-cards">{worlds.map((world, index) => <li key={world.world_id}><button type="button" className="mobile-world-card"
    data-tone={index % 3} onClick={() => onEnter(world)}>
    {urls[world.world_id] ? <img className="mobile-world-art" src={urls[world.world_id]} alt=""/> : <span className="mobile-world-pattern" aria-hidden="true"><Moon/><Sparkles/><span/></span>}
    <span className="mobile-world-card-copy"><small><BookOpen size={12}/>{world.clock_state === "paused" ? "世界已暂停" : "我的世界"}</small><strong>{world.name}</strong><span>进入世界<ChevronRight size={16}/></span></span>
  </button></li>)}</ul>;
}
