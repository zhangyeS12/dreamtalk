import { useCallback, useEffect, useRef, useState } from "react";
import { CoreClient, type WorldCover } from "@dreamtalk/api-client";
import type { BookAppearance } from "./BookFaces";

export function useWorldCovers(client: CoreClient, worldId?: string, enabled = true) {
  const [covers, setCovers] = useState<WorldCover[]>([]);
  const [appearances, setAppearances] = useState<Record<string, BookAppearance>>({});
  const [error, setError] = useState("");
  const live = useRef(true);
  const sequence = useRef(0);
  const cache = useRef(new Map<string, string>());
  const refresh = useCallback(async () => {
    if (!enabled) return;
    const epoch = ++sequence.current;
    try {
      const result = await client.listWorldCovers();
      if (live.current && sequence.current === epoch) { setCovers(worldId ? result.filter(cover => cover.world_id === worldId) : result); setError(""); }
    } catch { if (live.current && sequence.current === epoch) setError("封面暂时无法读取，已保留默认文字外观。刷新书架可重试。"); }
  }, [client, worldId, enabled]);
  useEffect(() => {
    live.current = true; setAppearances({}); void refresh();
    const urls = cache.current;
    return () => { live.current = false; sequence.current += 1; urls.forEach(url => URL.revokeObjectURL(url)); urls.clear(); };
  }, [refresh]);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const load = async () => {
      const result: Record<string, BookAppearance> = {};
      for (const cover of covers) {
        if (worldId && cover.world_id !== worldId) continue;
        const urls: BookAppearance["urls"] = {};
        if (cover.mode === "image") for (const face of ["front", "spine", "back"] as const) {
          const display = cover.faces[face]?.display;
          if (!display) continue;
          const key = `${cover.world_id}:${display.digest}`;
          let url = cache.current.get(key);
          if (!url) {
            try {
              const blob = await client.coverImage(cover.world_id, display.digest, controller.signal);
              if (controller.signal.aborted) return;
              url = URL.createObjectURL(blob); cache.current.set(key, url);
            } catch {
              if (controller.signal.aborted) return;
              setError("部分封面图片无法读取，已保留文字外观。刷新书架可重试。");
            }
          }
          if (url) urls[face] = url;
        }
        result[cover.world_id] = { cover, urls };
      }
      if (!controller.signal.aborted) setAppearances(result);
    };
    void load();
    return () => controller.abort();
  }, [client, covers, enabled, worldId]);
  const saved = useCallback((cover: WorldCover) => {
    sequence.current += 1;
    setError(""); setCovers(current => [...current.filter(item => item.world_id !== cover.world_id), cover]);
  }, []);
  return { appearances, error, refresh, saved };
}
