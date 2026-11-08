import type { WorldSettings } from "@dreamtalk/api-client";
import type { CoverAppearance } from "../../useWorldCovers";
import { FaceArt } from "./Book3D";
import { BOOK_FACE, BOOK_HEIGHT } from "./bookDesign";
import { bookLook, shelfAppearance } from "./bookLook";

/** The world's front cover, scaled down, for places that only need to recognise the book. */
export function BookThumb({ world, appearance, width = 60 }: { world: WorldSettings | undefined; appearance?: CoverAppearance; width?: number }) {
  const name = world?.name ?? "世界档案";
  const look = bookLook(world, shelfAppearance(appearance, name), name);
  const scale = width / BOOK_FACE;
  return <span aria-hidden="true" style={{ position: "relative", display: "block", flex: "none", width, height: BOOK_HEIGHT * scale, overflow: "hidden", borderRadius: 4, boxShadow: "0 8px 18px -8px rgb(0 0 0 / .7)" }}>
    <span style={{ position: "absolute", left: 0, top: 0, width: BOOK_FACE, height: BOOK_HEIGHT, transform: `scale(${scale})`, transformOrigin: "top left" }}>
      <FaceArt look={look} face="front" />
    </span>
  </span>;
}
