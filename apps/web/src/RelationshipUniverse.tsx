import { useEffect, useRef, useState } from "react";
import ForceGraph3D, { type ForceGraph3DInstance, type NodeObject, type LinkObject } from "3d-force-graph";
import {
  AmbientLight, BackSide, BufferGeometry, CanvasTexture, Color, DirectionalLight, Float32BufferAttribute,
  FogExp2, Group, Mesh, MeshBasicMaterial, MeshStandardMaterial, MOUSE, PerspectiveCamera,
  Points, PointsMaterial, ShaderMaterial, SphereGeometry, Sprite, SpriteMaterial, SRGBColorSpace,
  TOUCH, TorusGeometry, Vector3, type Material, type Texture,
} from "three";
import type { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { SocialSnapshot } from "@dreamtalk/api-client";

type PlanetNode = NodeObject & { id: string; name: string; digest: string | null; phase: number; base?: Vector3 };
type PlanetLink = LinkObject<PlanetNode>;
type Universe = ForceGraph3DInstance<PlanetNode, PlanetLink>;
type Actions = { focus: (root: string) => void; overview: () => void; zoom: (factor: number) => void };
type Portrait = {
  group: Group; face: Group; body: MeshStandardMaterial; ring: Mesh; label: Sprite;
  canvas: HTMLCanvasElement; texture: CanvasTexture; url?: string; image?: HTMLImageElement;
};

const RADIUS = 18;
const COLORS = ["#91baab", "#94aabe", "#b4b29a", "#aca4ba", "#a4bbb7"];

function hash(value: string): number {
  let result = 2166136261;
  for (const point of value) result = Math.imul(result ^ point.codePointAt(0)!, 16777619);
  return result >>> 0;
}

function avatarPaint(canvas: HTMLCanvasElement, name: string, color: string, image?: HTMLImageElement) {
  const context = canvas.getContext("2d")!;
  const size = canvas.width;
  context.clearRect(0, 0, size, size);
  if (image) {
    const side = Math.min(image.naturalWidth, image.naturalHeight);
    context.drawImage(image, (image.naturalWidth - side) / 2, (image.naturalHeight - side) / 2, side, side, 0, 0, size, size);
  } else {
    const paint = context.createLinearGradient(0, 0, size, size);
    paint.addColorStop(0, color); paint.addColorStop(1, "#314449");
    context.fillStyle = paint; context.fillRect(0, 0, size, size);
    context.fillStyle = "#f1f6f3"; context.textAlign = "center"; context.textBaseline = "middle";
    context.font = `600 ${size * .42}px "Microsoft YaHei", system-ui, sans-serif`;
    context.fillText(Array.from(name.trim())[0] ?? "?", size / 2, size * .51);
  }
}

function portrait(node: PlanetNode, sphere: SphereGeometry, cap: SphereGeometry, ringShape: TorusGeometry): Portrait {
  const color = COLORS[hash(node.id) % COLORS.length];
  const group = new Group(), face = new Group();
  const body = new MeshStandardMaterial({ color, roughness: .48, metalness: .25, emissive: "#16322a", emissiveIntensity: .12 });
  group.add(new Mesh(sphere, body));
  const canvas = document.createElement("canvas"); canvas.width = canvas.height = 384;
  avatarPaint(canvas, node.name, color);
  const texture = new CanvasTexture(canvas); texture.colorSpace = SRGBColorSpace;
  face.add(new Mesh(cap, new MeshStandardMaterial({ map: texture, roughness: .72, metalness: .02 })));
  const ring = new Mesh(ringShape, new MeshBasicMaterial({ color: "#acd8c4", transparent: true, opacity: .72 }));
  ring.visible = false; face.add(ring); group.add(face);

  const atmosphere = new Mesh(new SphereGeometry(RADIUS * 1.10, 28, 20), new ShaderMaterial({
    uniforms: { tint: { value: new Color(color) } }, transparent: true, side: BackSide, depthWrite: false,
    vertexShader: `varying vec3 worldNormal; varying vec3 eye; void main() {
      vec4 world = modelMatrix * vec4(position, 1.0);
      worldNormal = normalize(mat3(modelMatrix) * normal); eye = normalize(cameraPosition - world.xyz);
      gl_Position = projectionMatrix * viewMatrix * world;
    }`,
    fragmentShader: `uniform vec3 tint; varying vec3 worldNormal; varying vec3 eye; void main() {
      float rim = pow(1.0 - abs(dot(normalize(worldNormal), normalize(eye))), 2.7);
      gl_FragColor = vec4(tint, rim * 0.25);
    }`,
  }));
  atmosphere.raycast = () => {}; group.add(atmosphere);

  const nameCanvas = document.createElement("canvas"), nameContext = nameCanvas.getContext("2d")!;
  nameContext.font = '500 36px "Microsoft YaHei", system-ui, sans-serif';
  nameCanvas.width = Math.min(1536, Math.max(180, Math.ceil(nameContext.measureText(node.name).width + 40)));
  nameCanvas.height = 80;
  nameContext.font = '500 36px "Microsoft YaHei", system-ui, sans-serif';
  nameContext.fillStyle = "#ebf4ef"; nameContext.textAlign = "center"; nameContext.textBaseline = "middle";
  nameContext.shadowColor = "#070e13"; nameContext.shadowBlur = 8;
  nameContext.fillText(node.name, nameCanvas.width / 2, 40, nameCanvas.width - 28);
  const nameTexture = new CanvasTexture(nameCanvas); nameTexture.colorSpace = SRGBColorSpace;
  const label = new Sprite(new SpriteMaterial({ map: nameTexture, transparent: true, opacity: .85, depthWrite: false }));
  label.position.set(0, -RADIUS * 1.57, 0); label.scale.set(nameCanvas.width / 7.5, nameCanvas.height / 7.5, 1);
  label.raycast = () => {}; group.add(label);
  return { group, face, body, ring, label, canvas, texture };
}

function starField(): Points {
  const coordinates: number[] = [], colors: number[] = [];
  let seed = 97531;
  const random = () => { seed = Math.imul(seed, 1664525) + 1013904223 >>> 0; return seed / 4294967296; };
  for (let index = 0; index < 760; index++) {
    const azimuth = random() * Math.PI * 2, height = random() * 2 - 1, radius = 1800 + random() * 1900;
    const circle = Math.sqrt(1 - height * height);
    coordinates.push(radius * circle * Math.cos(azimuth), radius * height, radius * circle * Math.sin(azimuth));
    const light = .28 + random() * .5; colors.push(light * .86, light, light * .96);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(coordinates, 3));
  geometry.setAttribute("color", new Float32BufferAttribute(colors, 3));
  const stars = new Points(geometry, new PointsMaterial({ size: 4.6, vertexColors: true, transparent: true, opacity: .85, depthWrite: false }));
  stars.raycast = () => {}; return stars;
}

export default function RelationshipUniverse({ social, urls, selected, onSelect }: {
  social: SocialSnapshot; urls: Record<string, string>; selected: string | null; onSelect: (root: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const actions = useRef<Actions | null>(null);
  const current = useRef({ urls, selected, onSelect, drifting: true, reduced: false });
  const [drifting, setDrifting] = useState(true);
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => { current.current = { urls, selected, onSelect, drifting, reduced }; }, [urls, selected, onSelect, drifting, reduced]);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReduced(preference.matches);
    preference.addEventListener("change", change); return () => preference.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let graph: Universe | undefined, observer: ResizeObserver | undefined, alive = true;
    let initialized = false, interacting = false, hovered: string | null = null, phase = 0, lastFrame = performance.now(), lastSelection: string | null = null;
    const portraits = new Map<string, Portrait>();
    const sphere = new SphereGeometry(RADIUS, 36, 28);
    const cap = new SphereGeometry(RADIUS * 1.005, 40, 28, 0, Math.PI * 2, 0, 1.10);
    cap.rotateX(Math.PI / 2);
    const coordinates = cap.getAttribute("position"), uv = cap.getAttribute("uv"), faceWidth = 2 * RADIUS * Math.sin(1.10);
    for (let index = 0; index < coordinates.count; index++) uv.setXY(index, .5 + coordinates.getX(index) / faceWidth, .5 + coordinates.getY(index) / faceWidth);
    const ring = new TorusGeometry(RADIUS * 1.18, .15, 8, 96);
    const nodes: PlanetNode[] = [...social.characters].sort((a, b) => a.root_import_id.localeCompare(b.root_import_id)).map((person, index) => {
      const value = hash(person.root_import_id), angle = index * 2.399963229728653;
      const spread = 110 + 38 * Math.sqrt(index);
      return { id: person.root_import_id, name: person.name, digest: person.avatar_digest, phase: value % 628 / 100,
        x: Math.cos(angle) * spread, y: Math.sin(angle) * spread * .6, z: (value % 200 - 100) * .8 };
    });
    const identities = new Set(nodes.map(node => node.id));
    const links: PlanetLink[] = social.connections.filter(link => identities.has(link.first_root_import_id) && identities.has(link.second_root_import_id))
      .map(link => ({ source: link.first_root_import_id, target: link.second_root_import_id }));
    for (const node of nodes) portraits.set(node.id, portrait(node, sphere, cap, ring));
    const stars = starField();
    const escapedLabel = document.createElement("span");
    let canvas: HTMLCanvasElement | undefined, controls: OrbitControls | undefined;

    const overview = () => {
      if (!graph || !initialized) return;
      if (!nodes.length) return;
      // Use settled data coordinates: mesh matrices are not updated on the first engine tick yet.
      const minimum = new Vector3(Infinity, Infinity, Infinity), maximum = new Vector3(-Infinity, -Infinity, -Infinity);
      for (const node of nodes) {
        const position = new Vector3(node.x ?? 0, node.y ?? 0, node.z ?? 0);
        minimum.min(position); maximum.max(position);
      }
      const camera = graph.camera() as PerspectiveCamera;
      const center = minimum.clone().add(maximum).multiplyScalar(.5);
      const radius = Math.max(90, maximum.distanceTo(minimum) / 2 + 55);
      const field = Math.atan(Math.tan(camera.fov * Math.PI / 360) * Math.min(1, camera.aspect));
      const distance = radius / Math.sin(field) * 1.08;
      graph.cameraPosition(center.clone().add(new Vector3(.15, .19, 1).normalize().multiplyScalar(distance)), center, current.current.reduced ? 0 : 260);
    };
    const focus = (root: string) => {
      if (!graph || !initialized) return;
      const node = nodes.find(item => item.id === root); if (!node) return;
      const target = new Vector3(node.x ?? 0, node.y ?? 0, node.z ?? 0);
      const camera = graph.camera(), direction = camera.position.clone().sub(controls?.target ?? new Vector3()).normalize();
      if (direction.lengthSq() === 0) direction.set(0, 0, 1);
      graph.cameraPosition(target.clone().add(direction.multiplyScalar(205)), target, current.current.reduced ? 0 : 260);
    };
    const zoom = (factor: number) => {
      if (!graph || !controls) return;
      const target = controls.target.clone(), offset = graph.camera().position.clone().sub(target);
      const distance = Math.min(controls.maxDistance, Math.max(controls.minDistance, offset.length() * factor));
      graph.cameraPosition(target.clone().add(offset.normalize().multiplyScalar(distance)), target, current.current.reduced ? 0 : 180);
    };
    const start = () => { interacting = true; };
    const end = () => { interacting = false; };
    const visibility = () => {
      lastFrame = performance.now();
      if (document.hidden) graph?.pauseAnimation(); else graph?.resumeAnimation();
    };
    const lost = (event: Event) => { event.preventDefault(); graph?.pauseAnimation(); setError(true); };
    const keyboard = (event: KeyboardEvent) => {
      if (!graph || !controls) return;
      if (event.key === "+" || event.key === "=") zoom(.8);
      else if (event.key === "-") zoom(1.25);
      else if (event.key === "Home") overview();
      else if (event.key === "Escape") current.current.onSelect("");
      else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
        const camera = graph.camera(), distance = camera.position.distanceTo(controls.target) * .06;
        const horizontal = event.key === "ArrowLeft" || event.key === "ArrowRight";
        const offset = new Vector3().setFromMatrixColumn(camera.matrix, horizontal ? 0 : 1).multiplyScalar(distance * (["ArrowLeft", "ArrowDown"].includes(event.key) ? -1 : 1));
        graph.cameraPosition(camera.position.clone().add(offset), controls.target.clone().add(offset));
      } else return;
      event.preventDefault();
    };
    try {
      setError(false);
      graph = new ForceGraph3D(element, { controlType: "orbit", rendererConfig: { antialias: true, alpha: true, powerPreference: "low-power" } }) as unknown as Universe;
      graph.backgroundColor("#0b1119").showNavInfo(false).enableNodeDrag(false).enablePointerInteraction(true)
        .nodeLabel(node => { escapedLabel.textContent = node.name; return escapedLabel; })
        .linkLabel(() => "").linkColor(() => "#76928d").linkOpacity(.38).linkWidth(.18).linkResolution(4)
        .nodeThreeObject(node => portraits.get(node.id)!.group)
        .onNodeHover(node => { hovered = node?.id ?? null; })
        .onNodeClick(node => { focus(node.id); current.current.onSelect(node.id); })
        .onBackgroundClick(() => current.current.onSelect(""))
        .showPointerCursor(object => object != null && "id" in object && typeof object.id === "string" && identities.has(object.id))
        .warmupTicks(110).cooldownTicks(Infinity).cooldownTime(Infinity).d3AlphaMin(0).d3VelocityDecay(.5)
        .onEngineTick(() => {
          if (!graph || !alive) return;
          const now = performance.now();
          if (current.current.drifting && !current.current.reduced && !interacting) phase += Math.min(100, now - lastFrame) / 1000;
          lastFrame = now;
          if (!initialized) {
            for (const node of nodes) node.base = new Vector3(node.x ?? 0, node.y ?? 0, node.z ?? 0);
            graph.d3Force("charge", null).d3Force("link", null).d3Force("center", null);
            initialized = true; overview();
          }
          for (const node of nodes) {
            const base = node.base!, angle = phase * .075 + node.phase;
            node.x = node.fx = base.x + Math.sin(angle) * 4;
            node.y = node.fy = base.y + Math.sin(angle * .81 + 1) * 5;
            node.z = node.fz = base.z + Math.cos(angle * .63) * 3;
            const visual = portraits.get(node.id)!, chosen = current.current.selected === node.id;
            visual.face.quaternion.copy(graph.camera().quaternion);
            const scale = chosen ? 1.10 : hovered === node.id ? 1.035 : 1;
            visual.group.scale.setScalar(visual.group.scale.x + (scale - visual.group.scale.x) * (current.current.reduced ? 1 : .16));
            visual.ring.visible = chosen; visual.body.emissiveIntensity = chosen ? .24 : hovered === node.id ? .18 : .08;
            visual.label.material.opacity = chosen ? 1 : .82;
            const url = current.current.urls[node.digest ?? ""];
            if (visual.url !== url) {
              visual.url = url;
              if (visual.image) { visual.image.onload = null; visual.image.onerror = null; }
              avatarPaint(visual.canvas, node.name, COLORS[hash(node.id) % COLORS.length]); visual.texture.needsUpdate = true;
              if (url) {
                const image = new Image(); visual.image = image;
                image.onload = () => { if (alive && visual.url === url && image.naturalWidth && image.naturalHeight) { avatarPaint(visual.canvas, node.name, "", image); visual.texture.needsUpdate = true; } };
                image.src = url;
              }
            }
          }
          if (lastSelection !== current.current.selected) {
            lastSelection = current.current.selected;
            if (lastSelection) focus(lastSelection);
          }
        });
      const charge = graph.d3Force("charge");
      if (charge && "strength" in charge) (charge as typeof charge & { strength: (strength: number) => unknown }).strength(-1300);
      const link = graph.d3Force("link");
      if (link && "distance" in link) (link as typeof link & { distance: (distance: number) => unknown }).distance(145);
      const scene = graph.scene(); scene.fog = new FogExp2("#0b1119", .00028); scene.add(stars);
      const key = new DirectionalLight("#eaf4ef", 2.5); key.position.set(-250, 350, 550);
      const rim = new DirectionalLight("#759ebc", 1.7); rim.position.set(300, -100, -250);
      graph.lights([new AmbientLight("#c4dbce", 1.15), key, rim]);
      const camera = graph.camera() as PerspectiveCamera; camera.fov = 45; camera.far = 10000; camera.near = 1; camera.updateProjectionMatrix();
      const renderer = graph.renderer(); renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
      canvas = renderer.domElement; canvas.tabIndex = 0;
      canvas.setAttribute("aria-label", "三维人物关系网：点击头像查看人物，拖动移动，右键拖动旋转，滚轮缩放。方向键移动，Home查看全部。");
      canvas.addEventListener("keydown", keyboard); canvas.addEventListener("webglcontextlost", lost);
      controls = graph.controls() as OrbitControls;
      controls.mouseButtons = { LEFT: MOUSE.PAN, MIDDLE: MOUSE.DOLLY, RIGHT: MOUSE.ROTATE };
      controls.touches = { ONE: TOUCH.PAN, TWO: TOUCH.DOLLY_ROTATE };
      controls.enableDamping = true; controls.dampingFactor = .09; controls.minDistance = 75; controls.maxDistance = 12000;
      controls.addEventListener("start", start); controls.addEventListener("end", end);
      document.addEventListener("visibilitychange", visibility);
      actions.current = { focus, overview, zoom };
      const resize = () => {
        const box = element.getBoundingClientRect();
        if (box.width > 0 && box.height > 0 && graph) graph.width(box.width).height(box.height);
      };
      observer = new ResizeObserver(resize); observer.observe(element); resize();
      graph.graphData({ nodes, links }); visibility();
    } catch { setError(true); }
    return () => {
      alive = false; observer?.disconnect(); actions.current = null;
      document.removeEventListener("visibilitychange", visibility);
      canvas?.removeEventListener("keydown", keyboard); canvas?.removeEventListener("webglcontextlost", lost);
      controls?.removeEventListener("start", start); controls?.removeEventListener("end", end);
      const renderer = graph?.renderer();
      graph?._destructor(); renderer?.forceContextLoss();
      const geometries = new Set<BufferGeometry>([sphere, cap, ring, stars.geometry]);
      const materials = new Set<Material>([stars.material as Material]), textures = new Set<Texture>();
      for (const visual of portraits.values()) {
        if (visual.image) { visual.image.onload = null; visual.image.onerror = null; }
        visual.group.traverse(object => {
          if (object instanceof Mesh || object instanceof Sprite) {
            if (object instanceof Mesh) geometries.add(object.geometry);
            const found = Array.isArray(object.material) ? object.material : [object.material];
            for (const material of found) { materials.add(material); if ("map" in material && material.map) textures.add(material.map as Texture); }
          }
        });
        textures.add(visual.texture);
      }
      geometries.forEach(geometry => geometry.dispose()); materials.forEach(material => material.dispose()); textures.forEach(texture => texture.dispose());
      element.replaceChildren();
    };
  }, [social, retry]);

  return <>
    <div className="social-universe" ref={host} />
    {error && <div className="social-scene-error" role="alert"><strong>三维视图暂时无法显示</strong><p>可用下方“定位角色”查看资料，或重试视图。</p><button type="button" onClick={() => setRetry(value => value + 1)}>重试视图</button></div>}
    <div className="social-scene-controls" aria-label="关系网视图操作">
      <label><span className="sr-only">定位角色</span><select value={selected ?? ""} onChange={event => { actions.current?.focus(event.target.value); onSelect(event.target.value); }}><option value="">定位角色</option>{social.characters.map(person => <option key={person.root_import_id} value={person.root_import_id}>{person.name}</option>)}</select></label>
      <button type="button" onClick={() => { onSelect(""); actions.current?.overview(); }} aria-label="查看全部人物" title="查看全部人物">全览</button>
      <button type="button" onClick={() => actions.current?.zoom(.8)} aria-label="放大关系网" title="放大">＋</button>
      <button type="button" onClick={() => actions.current?.zoom(1.25)} aria-label="缩小关系网" title="缩小">−</button>
      <button type="button" onClick={() => setDrifting(value => !value)} disabled={reduced} aria-pressed={drifting && !reduced}>{reduced ? "静止视图" : drifting ? "暂停漂浮" : "继续漂浮"}</button>
    </div>
  </>;
}
