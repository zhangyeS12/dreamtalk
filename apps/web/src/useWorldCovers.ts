import { useCallback, useEffect, useRef, useState } from "react";
import { CoreClient, type WorldCover } from "@dreamtalk/api-client";
import type { BookAppearance } from "./BookFaces";

export function useWorldCovers(client: CoreClient, worldId?: string, enabled = true) {
  const [covers, setCovers] = useState<WorldCover[]>([]);
  const [appearances, setAppearances] = useState<Record<string, BookAppearance>>({});
  const [metadataReady, setMetadataReady] = useState(false);
  const [error, setError] = useState("");
  const live = useRef(true);
  const sequence = useRef(0);
  const cache = useRef(new Map<string, string>());
  const refresh = useCallback(async () => {
    if (!enabled) return;
    const epoch = ++sequence.current;
    setMetadataReady(false);
    try {
      const result = await client.listWorldCovers();
      if (live.current && sequence.current === epoch) {
        setCovers(worldId ? result.filter(cover => cover.world_id === worldId) : result); setError("");
      }
    } catch {
      if (live.current && sequence.current === epoch) setError("封面暂时无法读取，已保留默认文字外观。刷新书架可重试。");
    } finally { if (live.current && sequence.current === epoch) setMetadataReady(true); }
  }, [client, worldId, enabled]);
  useEffect(() => {
    live.current = true; setAppearances({}); void refresh();
    const urls = cache.current;
    return () => { live.current = false; sequence.current += 1; urls.forEach(url => URL.revokeObjectURL(url)); urls.clear(); };
  }, [refresh]);
  useEffect(() => {
    if (!enabled || !metadataReady) return;
    const controller = new AbortController();
    const epoch = sequence.current;
    let cancelled = false;
    const active = () => !cancelled && live.current && sequence.current === epoch;
    // Optional local artwork must never hold the launch hostage. On timeout,
    // finish every book's text appearance; explicit refresh can retry the images.
    const timer = window.setTimeout(() => controller.abort(), 5000);
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
          if (!url && !controller.signal.aborted) {
            try {
              const blob = await client.coverImage(cover.world_id, display.digest, controller.signal);
              if (!active()) return;
              url = URL.createObjectURL(blob); cache.current.set(key, url);
            } catch {
              if (!active()) return;
              setError("部分封面图片无法读取，已保留文字外观。刷新书架可重试。");
            }
          }
          if (url) urls[face] = url;
        }
        result[cover.world_id] = { cover, urls };
      }
      clearTimeout(timer);
      if (active()) setAppearances(result);
    };
    void load();
    return () => { cancelled = true; clearTimeout(timer); controller.abort(); };
  }, [client, covers, enabled, metadataReady, worldId]);
  useEffect(() => {
    // Effects run after the new appearance commits. Keep the old artwork while
    // its replacement loads, and protect current keys that a load may reuse.
    const displayed = new Set(Object.values(appearances).flatMap(appearance => Object.values(appearance.urls)));
    const needed = new Set<string>();
    if (enabled) for (const cover of covers) {
      if (cover.mode !== "image" || worldId && cover.world_id !== worldId) continue;
      for (const face of ["front", "spine", "back"] as const) {
        const display = cover.faces[face]?.display;
        if (display) needed.add(`${cover.world_id}:${display.digest}`);
      }
    }
    for (const [key, url] of cache.current) {
      if (needed.has(key) || displayed.has(url)) continue;
      URL.revokeObjectURL(url);
      cache.current.delete(key);
    }
  }, [appearances, covers, enabled, worldId]);
  const saved = useCallback((cover: WorldCover) => {
    sequence.current += 1;
    setMetadataReady(true); setError(""); setCovers(current => [...current.filter(item => item.world_id !== cover.world_id), cover]);
  }, []);
  const ready = !enabled || metadataReady && covers.every(cover => appearances[cover.world_id]?.cover === cover);
  return { appearances, error, ready, refresh, saved };
}
