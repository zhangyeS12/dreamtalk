import type { CoverFace, WorldCover } from "@dreamtalk/api-client";

export type BookAppearance = { cover: Pick<WorldCover, "mode" | "title" | "show_title">; urls: Partial<Record<CoverFace, string>> };
export function BookFaces({ name, number = "01", blank = false, appearance }: {
  name: string; number?: string; blank?: boolean; appearance?: BookAppearance;
}) {
  const title = blank ? "下一个世界" : (appearance?.cover.title ?? name).trim();
  const urls = appearance?.cover.mode === "image" ? appearance.urls : {};
  const show = appearance?.cover.show_title ?? true;
  const image = (face: CoverFace) => urls[face] && <img className="book-art" src={urls[face]} alt="" draggable={false} />;
  return <>
    <span className={`book-front book-face ${urls.front ? "has-cover-art" : ""}`}>
      {image("front")}<small className="book-brand">dreamtalk</small>
      {title && (!urls.front || show) && <strong className="book-title">{title}</strong>}
      {!urls.front && <><span>{blank ? "创建 · 导入" : "世界档案"}</span><i>{number}</i></>}
    </span>
    <span className={`book-back book-face ${urls.back ? "has-cover-art" : ""}`}>
      {image("back")}{!urls.back && <><small>dreamtalk</small><span>{blank ? "等待一段新的故事" : title}</span></>}
    </span>
    <span className={`book-spine book-face ${urls.spine ? "has-cover-art" : ""}`}>
      {image("spine")}{!urls.spine && <small>{number}</small>}
      {title && (!urls.spine || show) && <strong className="book-title">{blank ? "未命名世界" : title}</strong>}
      {!urls.spine && <span>dreamtalk</span>}
    </span>
    <span className="book-pages book-face" /><span className="book-top book-face" /><span className="book-bottom book-face" />
  </>;
}
