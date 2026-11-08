import type { WorldSettings } from "@dreamtalk/api-client";
import type { CoverAppearance } from "../../useWorldCovers";
import { skyAt, skyOf } from "../sky";
import type { BookLook, ShelfAppearance } from "./Book3D";
import { designFor } from "./bookDesign";

/** What a saved cover gives its book: the design (old covers get an equivalent one) and image URLs. */
export function shelfAppearance(cover: CoverAppearance | undefined, name: string): ShelfAppearance {
  return {
    design: designFor(cover?.full, name), uploads: cover?.uploads ?? {},
    art: { front: cover?.urls.front, spine: cover?.urls.spine, back: cover?.urls.back, jacket: cover?.jacket, jacketAspect: cover?.jacketAspect },
  };
}

/** Everything a book needs to draw itself, including the sky over its world right now. */
export function bookLook(world: WorldSettings | undefined, appearance: ShelfAppearance | undefined, name = world?.name ?? "世界档案"): BookLook {
  return {
    name, design: appearance?.design ?? designFor(undefined, name), art: appearance?.art ?? {}, uploads: appearance?.uploads ?? {},
    sky: skyOf(world) ?? skyAt(0), paused: world?.clock_state === "paused",
  };
}
