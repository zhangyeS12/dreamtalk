import { useEffect, useRef } from "react";
import type { WorldSettings } from "@dreamtalk/api-client";

export function WorldShelf({ worlds, selectedId, disabled, loading, onSelect, onCreate }: {
  worlds: WorldSettings[]; selectedId: string; disabled: boolean; loading: boolean;
  onSelect: (id: string) => void; onCreate: () => void;
}) {
  const shelf = useRef<HTMLDivElement>(null);
  const selectedBook = useRef<HTMLButtonElement>(null);
  useEffect(() => { selectedBook.current?.scrollIntoView({ block: "nearest", inline: "center", behavior: "instant" }); }, [selectedId, worlds.length]);
  const scroll = (direction: number) => shelf.current?.scrollBy({ left: direction * shelf.current.clientWidth * .7,
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  return <section className="archive-shelf-section" aria-label="世界书架">
    <div className="archive-shelf-heading"><span>{loading ? "正在读取世界档案…" : `${worlds.length} 个世界档案`}</span>
      <div className="archive-scroll-actions"><button type="button" aria-label="向左浏览书架" onClick={() => scroll(-1)}>←</button><button type="button" aria-label="向右浏览书架" onClick={() => scroll(1)}>→</button></div>
    </div>
    <div className="archive-shelf" ref={shelf}>
      {worlds.map((world, index) => <button type="button" className={`archive-book ${selectedId === world.world_id ? "is-selected" : ""}`} key={world.world_id}
        ref={selectedId === world.world_id ? selectedBook : undefined} disabled={disabled} aria-pressed={selectedId === world.world_id} aria-label={`预览世界：${world.name}`} onClick={() => onSelect(world.world_id)}>
        <span className="book-volume" aria-hidden="true"><span className="book-spine"><span>{world.name}</span><small>{String(index + 1).padStart(2, "0")}</small></span>
          <span className="book-front"><small>dreamtalk / WORLD ARCHIVE</small><strong>{world.name}</strong><span>世界档案</span><i>{String(index + 1).padStart(2, "0")}</i></span></span>
        <span className="book-caption"><strong>{world.name}</strong><small>{world.runtime_state === "degraded" ? "运行需要处理" : world.clock_state === "paused" ? "世界时间已暂停" : "世界时间运行中"}</small></span>
      </button>)}
      {Array.from({ length: 6 }, (_, index) => <button type="button" key={`blank:${index}`} className="archive-book blank-book" disabled={disabled || loading}
        aria-label="创建或导入一个新世界" onClick={onCreate}>
        <span className="book-volume" aria-hidden="true"><span className="book-spine"><span>未命名世界</span><small>＋</small></span>
          <span className="book-front"><small>dreamtalk / WORLD ARCHIVE</small><strong>留给下一个世界</strong><span>创建 · 导入</span><i>＋</i></span></span>
        <span className="book-caption"><strong>新建世界</strong><small>创建或导入世界书</small></span>
      </button>)}
    </div>
    <p className="archive-shelf-hint">横向浏览书架，选择一本书查看世界。空白书位可以随时添加。</p>
  </section>;
}
