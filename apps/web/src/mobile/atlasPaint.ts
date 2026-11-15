import type { Connection } from "./diagramLayout";
import { atlasNodes, atlasNeighbors, visibleAtlasNodes, type AtlasLayout, type AtlasView } from "./atlasLayout";

/** Event-driven Canvas2D painter: no simulation, timer, particle system or idle frame loop. */
export function paintAtlas(ctx: CanvasRenderingContext2D, layout: AtlasLayout, connections: Connection[],
  view: AtlasView, width: number, center: string | null, pair: string | null,
  portraits: ReadonlyMap<string, CanvasImageSource>) {
  ctx.clearRect(0, 0, width, width);
  ctx.save(); ctx.scale(width / view.size, width / view.size); ctx.translate(-view.x, -view.y);
  const nodes = atlasNodes(layout, center), byId = new Map(nodes.map(node => [node.id, node]));
  const neighbors = atlasNeighbors(connections, center);
  const lineScale = view.size / width;
  // Only fixed stars. Their positions never depend on time or change between redraws.
  ctx.fillStyle = "#a9b5d1";
  for (let index = 0; index < 56; index++) {
    ctx.globalAlpha = .12 + index % 3 * .045;
    ctx.beginPath(); ctx.arc((index * 157 + 43) % 1000, (index * 293 + 71) % 1000, index % 7 ? .8 : 1.4, 0, Math.PI * 2); ctx.fill();
  }
  for (const group of layout.groups) {
    ctx.globalAlpha = center ? .3 : .72; ctx.strokeStyle = group.color; ctx.lineWidth = 1.1 * lineScale;
    ctx.beginPath(); ctx.arc(500, 500, 412, group.start, group.end); ctx.stroke();
    const mid = (group.start + group.end) / 2, x = 500 + Math.cos(mid) * 451, y = 500 + Math.sin(mid) * 451;
    ctx.save(); ctx.translate(x, y); let rotation = mid + Math.PI / 2;
    if (mid > 0 && mid < Math.PI) rotation += Math.PI;
    ctx.rotate(rotation); ctx.globalAlpha = .95; ctx.fillStyle = "#cbd3e7";
    const label = group.name.split(" / ").at(-1)!;
    const count = Math.min(10, Math.floor((group.end - group.start) * 451 / (12 * lineScale)));
    ctx.font = "500 " + 12 * lineScale + "px system-ui, sans-serif"; ctx.textAlign = "center";
    if (count >= 2) ctx.fillText(Array.from(label).slice(0, count).join("") + (Array.from(label).length > count ? "…" : ""), 0, 0);
    ctx.restore();
  }
  for (const edge of connections) {
    const a = byId.get(edge.first_root_import_id), b = byId.get(edge.second_root_import_id);
    if (!a || !b || (center && a.id !== center && b.id !== center)) continue;
    const selectedPair = pair && (a.id === pair || b.id === pair);
    ctx.globalAlpha = center ? selectedPair ? .95 : .54 : .16;
    ctx.strokeStyle = selectedPair ? "#f0cb85" : center ? "#cfdaed" : a.color;
    ctx.lineWidth = (selectedPair ? 2 : center ? 1.3 : .8) * lineScale;
    ctx.beginPath(); ctx.moveTo(a.x, a.y);
    ctx.bezierCurveTo(500 + (a.x - 500) * .22, 500 + (a.y - 500) * .22,
      500 + (b.x - 500) * .22, 500 + (b.y - 500) * .22, b.x, b.y); ctx.stroke();
  }
  const visible = visibleAtlasNodes(nodes, view);
  for (const node of visible) {
    const selected = node.id === center, target = node.id === pair;
    const relevant = !center || selected || target || neighbors.has(node.id);
    if (selected) {
      const glow = ctx.createRadialGradient(node.x, node.y, node.r, node.x, node.y, node.r + 38);
      glow.addColorStop(0, "#d7b36755"); glow.addColorStop(1, "#d7b36700");
      ctx.globalAlpha = 1; ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(node.x, node.y, node.r + 38, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = relevant ? 1 : .23;
    ctx.fillStyle = "#1c2947"; ctx.beginPath(); ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2); ctx.fill();
    const image = node.person.avatar_digest ? portraits.get(node.person.avatar_digest) : null;
    if (image) {
      ctx.save(); ctx.beginPath(); ctx.arc(node.x, node.y, Math.max(.25, node.r - 1), 0, Math.PI * 2); ctx.clip();
      ctx.drawImage(image, node.x - node.r, node.y - node.r, node.r * 2, node.r * 2); ctx.restore();
    } else if (node.r * width / view.size > 7) {
      ctx.fillStyle = relevant ? "#e6eaf3" : "#b7c2d8"; ctx.font = "500 " + Math.round(node.r * 1.05) + "px system-ui, sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(Array.from(node.person.name.trim())[0] ?? "?", node.x, node.y);
    }
    ctx.strokeStyle = selected || target ? "#f0cb85" : node.color; ctx.lineWidth = (selected || target ? 2 : 1.2) * lineScale;
    ctx.beginPath(); ctx.arc(node.x, node.y, node.r + 2, 0, Math.PI * 2); ctx.stroke();
    if (selected || target || (view.size < 470 && relevant)) {
      ctx.globalAlpha = 1; ctx.font = "500 " + (selected ? 17 * lineScale : 13 * lineScale) + "px system-ui, sans-serif";
      ctx.fillStyle = selected || target ? "#f7dfaa" : "#e2e7f1"; ctx.textAlign = "center"; ctx.textBaseline = "top";
      ctx.fillText(node.person.name, node.x, node.y + node.r + 9 * lineScale);
    }
  }
  ctx.restore();
}
