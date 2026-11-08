import * as THREE from "three";

/**
 * "Night reading": a closed book with the original logo on its cover lies in a
 * pool of lamplight. It opens by itself and paper scenery pops up out of the
 * gutter like a pop-up book: a night sky, a moon, clouds and three ranges of
 * hills. When the archive is ready, `enter()` flies the camera between the
 * paper layers into the sky, which the bookshelf then takes over.
 *
 * Everything is a handful of boxes and planes with canvas-drawn textures; no
 * shadow maps, no post-processing. Nothing here depicts a real world's content.
 */
export interface StartupScene { enter(): void; setPaused(paused: boolean): void; dispose(): void }

const ENTER_MS = 1100;
const W = 4, D = 5.6, T = .34; // page width, page depth, block thickness

type Draw = (context: CanvasRenderingContext2D, width: number, height: number) => void;
function canvasTexture(width: number, height: number, draw: Draw): THREE.CanvasTexture {
  const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("startup_texture_unavailable");
  draw(context, width, height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace; texture.anisotropy = 4;
  return texture;
}
const random = (seed: number) => { const x = Math.sin(seed * 12.9898) * 43758.5453; return x - Math.floor(x); };

/**
 * Fine paper grain, so flat colours read as card rather than plastic. One small
 * noise tile is made once and laid over each texture as a pattern; per-pixel
 * loops over every large canvas cost seconds on slow machines.
 */
let noiseTile: HTMLCanvasElement | null = null;
function grain(context: CanvasRenderingContext2D, width: number, height: number, strength: number) {
  if (!noiseTile) {
    noiseTile = document.createElement("canvas"); noiseTile.width = noiseTile.height = 128;
    const tile = noiseTile.getContext("2d")!, image = tile.createImageData(128, 128);
    for (let i = 0; i < image.data.length; i += 4) {
      const n = random(i * .37) * 255;
      image.data[i] = image.data[i + 1] = image.data[i + 2] = n; image.data[i + 3] = 255;
    }
    tile.putImageData(image, 0, 0);
  }
  const pattern = context.createPattern(noiseTile, "repeat");
  if (!pattern) return;
  context.save();
  context.globalCompositeOperation = "source-atop"; context.globalAlpha = Math.min(.5, strength / 60);
  context.fillStyle = pattern; context.globalCompositeOperation = "soft-light"; context.fillRect(0, 0, width, height);
  context.restore();
}

/** A cut-paper silhouette of rolling hills with a lighter edge where the lamp catches it. */
function hills(fill: string, edge: string, seed: number, crest: number, house?: number): Draw {
  return (context, width, height) => {
    context.beginPath(); context.moveTo(0, height);
    for (let x = 0; x <= width; x += 8) {
      const y = height * (crest + .12 * Math.sin(x / width * 5.1 + seed) + .07 * Math.sin(x / width * 13.3 + seed * 2.1)
        + .02 * Math.sin(x / width * 41 + seed * 3.7));
      context.lineTo(x, y);
    }
    context.lineTo(width, height); context.closePath();
    context.fillStyle = fill; context.fill();
    context.lineWidth = 5; context.strokeStyle = edge; context.stroke();
    if (house !== undefined) {
      // A small cottage on the ridge; its window is lit separately in the scene.
      const x = width * house, ground = height * (crest + .12 * Math.sin(house * 5.1 + seed) + .07 * Math.sin(house * 13.3 + seed * 2.1)) + 6;
      const w = width * .05, h = w * .8;
      context.fillStyle = fill; context.strokeStyle = edge; context.lineWidth = 3;
      context.beginPath(); context.moveTo(x - w / 2, ground); context.lineTo(x - w / 2, ground - h); context.lineTo(x, ground - h * 1.7);
      context.lineTo(x + w / 2, ground - h); context.lineTo(x + w / 2, ground); context.closePath(); context.fill(); context.stroke();
      context.fillStyle = "#ffcf7a"; context.fillRect(x - w * .14, ground - h * .72, w * .28, h * .34);
    }
    grain(context, width, height, 10);
  };
}

export function createStartupScene(container: HTMLElement, onPaint: () => void): StartupScene {
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
  renderer.setClearColor(0x000000, 0); renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.15;
  renderer.domElement.setAttribute("aria-hidden", "true");
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, .05, 120);
  const disposables: Array<{ dispose(): void }> = [];
  const keep = <T extends { dispose(): void }>(item: T): T => { disposables.push(item); return item; };

  // ---------- Desk and lamplight ----------
  const deskTexture = keep(canvasTexture(512, 512, (context, width, height) => {
    const pool = context.createRadialGradient(width * .5, height * .5, 0, width * .5, height * .5, width * .5);
    // The desk fades out to transparent, so it melts into the page background instead of ending in a horizon.
    pool.addColorStop(0, "rgba(58,44,34,1)"); pool.addColorStop(.35, "rgba(27,21,32,1)"); pool.addColorStop(.7, "rgba(8,9,18,.85)"); pool.addColorStop(1, "rgba(8,9,18,0)");
    context.fillStyle = pool; context.fillRect(0, 0, width, height);
    // Faint wood grain inside the lamp pool.
    context.globalAlpha = .06; context.strokeStyle = "#f2c38c";
    for (let i = 0; i < 46; i++) {
      context.beginPath(); const y = i * height / 46 + random(i) * 6;
      context.moveTo(0, y); context.bezierCurveTo(width * .3, y + 8 * Math.sin(i), width * .7, y - 6, width, y + 4); context.stroke();
    }
  }));
  const desk = new THREE.Mesh(keep(new THREE.PlaneGeometry(26, 26)), keep(new THREE.MeshBasicMaterial({ map: deskTexture, transparent: true, depthWrite: false, fog: false })));
  desk.rotation.x = -Math.PI / 2; scene.add(desk);
  const shadowTexture = keep(canvasTexture(256, 256, (context, width, height) => {
    const blob = context.createRadialGradient(width / 2, height / 2, width * .12, width / 2, height / 2, width / 2);
    blob.addColorStop(0, "rgba(0,0,0,.75)"); blob.addColorStop(1, "rgba(0,0,0,0)");
    context.fillStyle = blob; context.fillRect(0, 0, width, height);
  }));
  const shadow = new THREE.Mesh(keep(new THREE.PlaneGeometry(1, 1)), keep(new THREE.MeshBasicMaterial({ map: shadowTexture, transparent: true, depthWrite: false })));
  shadow.rotation.x = -Math.PI / 2; shadow.position.y = .01; scene.add(shadow);

  scene.add(new THREE.AmbientLight(0x2c3266, .55));
  const lamp = new THREE.SpotLight(0xffd6a0, 3.2, 0, .62, .75, 0); lamp.position.set(-3.5, 9, 4.5); lamp.target.position.set(0, 0, -.4);
  scene.add(lamp, lamp.target);
  const rim = new THREE.DirectionalLight(0x7d95ff, 1.1); rim.position.set(2, 4, -8); scene.add(rim);

  // ---------- The book ----------
  const book = new THREE.Group(); scene.add(book);
  const paperTexture = keep(canvasTexture(512, 720, (context, width, height) => {
    context.fillStyle = "#efe4cf"; context.fillRect(0, 0, width, height);
    const shade = context.createLinearGradient(0, 0, width, 0);
    shade.addColorStop(0, "rgba(90,60,30,.22)"); shade.addColorStop(.12, "rgba(90,60,30,0)");
    context.fillStyle = shade; context.fillRect(0, 0, width, height);
    grain(context, width, height, 14);
  }));
  const edgeTexture = keep(canvasTexture(64, 256, (context, width, height) => {
    context.fillStyle = "#e6d8bd"; context.fillRect(0, 0, width, height);
    for (let x = 0; x < width; x += 2) { context.fillStyle = x % 4 ? "rgba(120,90,60,.18)" : "rgba(255,255,255,.2)"; context.fillRect(x, 0, 1, height); }
  }));
  const clothColor = "#1d2348";
  const coverTexture = keep(canvasTexture(768, 1076, (context, width, height) => {
    context.fillStyle = clothColor; context.fillRect(0, 0, width, height);
    // Woven cloth: two faint crossed line sets.
    context.globalAlpha = .08; context.strokeStyle = "#9fb0ff";
    for (let i = 0; i < width; i += 4) { context.beginPath(); context.moveTo(i, 0); context.lineTo(i, height); context.stroke(); }
    context.strokeStyle = "#000"; for (let i = 0; i < height; i += 4) { context.beginPath(); context.moveTo(0, i); context.lineTo(width, i); context.stroke(); }
    context.globalAlpha = 1;
    // Gold-foil frame.
    context.strokeStyle = "#d9b26f"; context.lineWidth = 6; context.strokeRect(46, 46, width - 92, height - 92);
    context.lineWidth = 2; context.strokeRect(64, 64, width - 128, height - 128);
    grain(context, width, height, 12);
  }));
  const coverMaterial = keep(new THREE.MeshLambertMaterial({ map: coverTexture }));
  const clothMaterial = keep(new THREE.MeshLambertMaterial({ color: clothColor }));
  const pageMaterial = keep(new THREE.MeshLambertMaterial({ map: paperTexture }));
  const edgeMaterial = keep(new THREE.MeshLambertMaterial({ map: edgeTexture }));
  const blockGeometry = keep(new THREE.BoxGeometry(W, T, D));
  // Box faces: +x, -x, +y, -y, +z, -z.
  const right = new THREE.Mesh(blockGeometry, [edgeMaterial, clothMaterial, pageMaterial, clothMaterial, edgeMaterial, edgeMaterial]);
  right.position.set(W / 2, T / 2, 0); book.add(right);
  // The left half turns on the gutter: open at 0, closed (lying on the right half, cover up) at -PI.
  const hinge = new THREE.Group(); hinge.position.set(0, T, 0); book.add(hinge);
  const left = new THREE.Mesh(blockGeometry, [clothMaterial, edgeMaterial, pageMaterial, coverMaterial, edgeMaterial, edgeMaterial]);
  left.position.set(-W / 2, -T / 2, 0); hinge.add(left);

  // The logo is drawn onto the cover once the original PNG has decoded.
  let logoReady = false;
  const logo = new Image(); logo.decoding = "async"; logo.src = "/brand/dreamtalk-logo.png";
  void logo.decode().then(() => {
    const context = coverTexture.image.getContext("2d") as CanvasRenderingContext2D;
    const width = coverTexture.image.width, height = coverTexture.image.height, size = width * .56;
    context.save();
    // The cover is the box's underside turned over, which shows the texture rotated half a turn.
    context.translate(width, height); context.rotate(Math.PI);
    context.shadowColor = "rgba(240,200,140,.45)"; context.shadowBlur = 40;
    context.drawImage(logo, (width - size) / 2, height * .3, size, size * logo.naturalHeight / logo.naturalWidth);
    context.restore();
    coverTexture.needsUpdate = true; logoReady = true;
  }).catch(() => { logoReady = true; });

  // ---------- Pop-up paper scenery, hinged at the gutter line ----------
  const stage = new THREE.Group(); stage.position.y = T + .002; book.add(stage);
  const skyTexture = keep(canvasTexture(1024, 820, (context, width, height) => {
    context.beginPath(); context.moveTo(0, height); context.lineTo(0, height * .32);
    context.quadraticCurveTo(width / 2, -height * .18, width, height * .32); context.lineTo(width, height); context.closePath();
    const sky = context.createLinearGradient(0, 0, 0, height);
    sky.addColorStop(0, "#0a0f33"); sky.addColorStop(.55, "#2d2a6e"); sky.addColorStop(.82, "#7a4f86"); sky.addColorStop(1, "#d79a6c");
    context.fillStyle = sky; context.fill();
    context.save(); context.clip();
    for (let i = 0; i < 220; i++) {
      const x = random(i + 1) * width, y = random(i + 50) * height * .62, r = 1 + random(i + 99) * 2.6;
      context.globalAlpha = .4 + random(i + 7) * .6; context.fillStyle = "#fff6e0";
      context.beginPath(); context.arc(x, y, r, 0, Math.PI * 2); context.fill();
    }
    context.restore();
    context.lineWidth = 10; context.strokeStyle = "rgba(240,210,160,.55)"; context.stroke();
    grain(context, width, height, 3);
  }));
  const moonTexture = keep(canvasTexture(256, 512, (context, width) => {
    context.fillStyle = "#cbb79a"; context.fillRect(width / 2 - 2, 200, 4, 312); // the stick it stands on
    context.fillStyle = "#fff1cf"; context.beginPath(); context.arc(width / 2, 110, 92, 0, Math.PI * 2); context.fill();
    // Cut the crescent out of the full disc.
    context.globalCompositeOperation = "destination-out";
    context.beginPath(); context.arc(width / 2 + 46, 84, 82, 0, Math.PI * 2); context.fill();
    context.globalCompositeOperation = "source-over";
  }));
  const cloudTexture = keep(canvasTexture(512, 256, (context, width, height) => {
    context.fillStyle = "#c9c2ec";
    for (const [x, y, r] of [[.28, .62, .2], [.45, .48, .26], [.64, .56, .22], [.78, .66, .16], [.16, .7, .13]]) {
      context.beginPath(); context.arc(x * width, y * height, r * height * 1.4, 0, Math.PI * 2); context.fill();
    }
    context.fillRect(width * .12, height * .62, width * .74, height * .3);
    context.globalCompositeOperation = "destination-out"; context.fillRect(0, height * .9, width, height);
    context.globalCompositeOperation = "source-over"; grain(context, width, height, 10);
  }));
  const layerSpecs: Array<{ texture: THREE.Texture; w: number; h: number; z: number; x?: number; delay: number; glow?: number }> = [
    { texture: skyTexture, w: W * 1.9, h: W * 1.52, z: -D * .42, delay: 0, glow: .55 },
    { texture: moonTexture, w: .75, h: 1.5, z: -D * .36, x: W * .5, delay: .08, glow: 1.2 },
    { texture: cloudTexture, w: 1.9, h: .95, z: -D * .3, x: -W * .45, delay: .14, glow: .25 },
    { texture: keep(canvasTexture(1024, 360, hills("#272a68", "rgba(150,160,255,.6)", 1.3, .42))), w: W * 1.85, h: 1.55, z: -D * .2, delay: .2 },
    { texture: cloudTexture, w: 1.4, h: .7, z: -D * .12, x: W * .55, delay: .26, glow: .2 },
    { texture: keep(canvasTexture(1024, 300, hills("#3a2c6e", "rgba(220,170,255,.55)", 4.1, .38, .7))), w: W * 1.88, h: 1.15, z: -D * .02, delay: .32 },
    { texture: keep(canvasTexture(1024, 260, hills("#15163a", "rgba(255,200,150,.6)", 2.7, .32))), w: W * 1.92, h: .82, z: D * .16, delay: .4 },
  ];
  const quad = keep(new THREE.PlaneGeometry(1, 1).translate(0, .5, 0));
  const layers = layerSpecs.map(spec => {
    const material = keep(new THREE.MeshLambertMaterial({ map: spec.texture, transparent: true, alphaTest: .4, side: THREE.DoubleSide,
      emissive: spec.glow ? 0xffffff : 0x000000, emissiveMap: spec.glow ? spec.texture : null, emissiveIntensity: spec.glow ?? 0 }));
    const pivot = new THREE.Group(); pivot.position.set(spec.x ?? 0, 0, spec.z); stage.add(pivot);
    const mesh = new THREE.Mesh(quad, material); mesh.scale.set(spec.w, spec.h, 1); pivot.add(mesh);
    return { pivot, mesh, spec };
  });

  // A shooting star crosses the paper sky every few seconds.
  const streakTexture = keep(canvasTexture(512, 32, (context, width, height) => {
    const tail = context.createLinearGradient(0, 0, width, 0);
    tail.addColorStop(0, "rgba(255,240,210,0)"); tail.addColorStop(.85, "rgba(255,240,210,.8)"); tail.addColorStop(1, "rgba(255,255,255,1)");
    context.fillStyle = tail; context.beginPath(); context.moveTo(0, height / 2); context.lineTo(width, height * .2); context.lineTo(width, height * .8); context.fill();
  }));
  const streakMaterial = keep(new THREE.MeshBasicMaterial({ map: streakTexture, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
  const streak = new THREE.Mesh(keep(new THREE.PlaneGeometry(1.6, .05)), streakMaterial);
  streak.rotation.z = -.32; streak.position.z = .02; layers[0].pivot.add(streak);

  // Warm light spilling out of the gutter, and dust drifting in the lamp beam.
  const glowTexture = keep(canvasTexture(256, 256, (context, width) => {
    const glow = context.createRadialGradient(width / 2, width / 2, 0, width / 2, width / 2, width / 2);
    glow.addColorStop(0, "rgba(255,255,255,1)"); glow.addColorStop(.25, "rgba(255,255,255,.35)"); glow.addColorStop(1, "rgba(255,255,255,0)");
    context.fillStyle = glow; context.fillRect(0, 0, width, width);
  }));
  const spill = new THREE.Sprite(keep(new THREE.SpriteMaterial({ map: glowTexture, color: 0xffc98a, transparent: true, opacity: 0,
    blending: THREE.AdditiveBlending, depthWrite: false })));
  spill.position.set(0, 1.4, -D * .3); spill.scale.set(9, 5, 1); book.add(spill);
  const moonGlow = new THREE.Sprite(keep(new THREE.SpriteMaterial({ map: glowTexture, color: 0xffe2b0, transparent: true, opacity: 0,
    blending: THREE.AdditiveBlending, depthWrite: false })));
  moonGlow.scale.setScalar(2.2); book.add(moonGlow);
  // The cottage window on the middle ridge glows; its position follows the drawing in `hills`.
  const windowGlow = new THREE.Sprite(keep(new THREE.SpriteMaterial({ map: glowTexture, color: 0xffb85c, transparent: true, opacity: 0,
    blending: THREE.AdditiveBlending, depthWrite: false })));
  {
    const spec = layerSpecs[5], house = .7, seed = 4.1, crest = .38, pxW = 1024, pxH = 300;
    const ground = pxH * (crest + .12 * Math.sin(house * 5.1 + seed) + .07 * Math.sin(house * 13.3 + seed * 2.1)) + 6;
    const windowY = ground - pxW * .05 * .8 * .55;
    windowGlow.position.set((house - .5) * spec.w, spec.h * (1 - windowY / pxH), .04);
    windowGlow.scale.setScalar(.38);
  }
  layers[5].pivot.add(windowGlow);
  const moteCount = 260, motes = new Float32Array(moteCount * 3);
  const moteGeometry = keep(new THREE.BufferGeometry()); moteGeometry.setAttribute("position", new THREE.BufferAttribute(motes, 3));
  const moteMaterial = keep(new THREE.PointsMaterial({ map: glowTexture, color: 0xffd9a8, size: .07, transparent: true, opacity: 0,
    depthWrite: false, blending: THREE.AdditiveBlending }));
  scene.add(new THREE.Points(moteGeometry, moteMaterial));

  // ---------- Motion ----------
  let disposed = false, paused = false, contextLost = false, painted = false, frame = 0, elapsed = 0, previous = 0;
  let entryStart: number | null = null;
  const size = () => {
    const width = Math.max(1, container.clientWidth), height = Math.max(1, container.clientHeight);
    renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix();
  };
  const clamp = (x: number) => Math.min(1, Math.max(0, x));
  const smooth = (x: number) => { const t = clamp(x); return t * t * (3 - 2 * t); };
  const outBack = (x: number) => { const t = clamp(x), c = 1.5; return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2; };
  const inOut = (x: number) => { const t = clamp(x); return t < .5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2; };
  const eye = new THREE.Vector3(), look = new THREE.Vector3(), diveEye = new THREE.Vector3(0, 2.6, -D * .25), diveLook = new THREE.Vector3(0, 2.9, -12);

  const draw = (now: number) => {
    frame = 0;
    if (disposed || document.hidden || paused || contextLost) { previous = 0; return; }
    if (!logoReady) { frame = requestAnimationFrame(draw); return; }
    // Real time, capped per frame so a stall does not jump the story; down to 10 fps it keeps pace.
    elapsed += previous ? Math.min((now - previous) / 1000, .1) : 0; previous = now;
    const warp = entryStart === null ? 0 : clamp((now - entryStart) / ENTER_MS), dive = inOut(warp);
    // If the archive is ready before the pop-up has finished, the dive finishes it on the way in.
    const story = Math.max(elapsed, 1.6 * Math.min(1, dive * 2.5));

    // The cover swings open over 0.15–1.05 s while the book slides to the centre.
    const open = inOut((story - .15) / .9);
    hinge.rotation.z = -Math.PI * (1 - open);
    book.position.x = -W / 2 * (1 - open);
    shadow.scale.set(W * (1.3 + open) * 1.25, D * 1.5, 1); shadow.position.x = book.position.x + W / 2 * (1 - open);

    // Each paper layer stands up after the cover passes the vertical, back to front, with a slight overshoot.
    for (const [index, layer] of layers.entries()) {
      const rise = outBack((story - .42 - layer.spec.delay * 1.2) / .55);
      const sway = Math.sin(elapsed * .9 + index * 1.3) * .012 * clamp(rise);
      layer.pivot.rotation.x = -Math.PI / 2 * (1 - rise) + sway;
      layer.mesh.visible = open > .55;
      if (layer.spec.texture === cloudTexture) layer.pivot.position.x = (layer.spec.x ?? 0) + Math.sin(elapsed * .35 + index) * .18;
    }
    const shoot = ((elapsed - 1.5) % 4.2) / .7;
    streakMaterial.opacity = elapsed > 1.5 && shoot < 1 ? Math.sin(Math.PI * shoot) * .9 : 0;
    streak.position.set(-2.4 + shoot * 4.2, 5.2 - shoot * 1.3, .02);
    const moon = layers[1];
    moonGlow.position.set(moon.pivot.position.x, moon.spec.h * .78 * Math.sin(Math.PI / 2 + moon.pivot.rotation.x) + T, moon.pivot.position.z + .05);
    moonGlow.material.opacity = .55 * smooth((elapsed - .9) / .6) * (1 + dive);
    windowGlow.material.opacity = (.75 + .2 * Math.sin(elapsed * 3.1) * Math.sin(elapsed * 1.3)) * smooth((elapsed - 1.1) / .5);
    spill.material.opacity = (.32 + .05 * Math.sin(elapsed * 1.7)) * smooth((elapsed - .4) / .8) * (1 - dive * .4);

    for (let i = 0; i < moteCount; i++) {
      const s = random(i + 3), u = random(i + 17), v = random(i + 31);
      const y = ((u * 6 + elapsed * (.08 + v * .1)) % 6);
      motes[i * 3] = -3.6 + s * 6.4 + Math.sin(elapsed * .3 + i) * .25 - y * .32;
      motes[i * 3 + 1] = .3 + y;
      motes[i * 3 + 2] = -2.6 + v * 6 + y * .2;
    }
    moteGeometry.attributes.position.needsUpdate = true;
    moteMaterial.opacity = .55 * smooth(elapsed / 1.2);

    // Camera: settle from a high three-quarter view to the front, sway gently, then dive into the sky.
    const portrait = camera.aspect < 1 ? 1.25 / Math.max(.55, camera.aspect) : 1;
    // Start almost straight above the closed cover, so its logo sits where the flat logo was.
    const settle = smooth(story / 1.6);
    eye.set(.4 * (1 - settle) + Math.sin(elapsed * .21) * .35 * settle, 9.6 - settle * 4.5 + Math.sin(elapsed * .17) * .12 * settle, (2.6 + settle * 8.4) * portrait);
    look.set(0, .25 + settle * 1.8, -.1 - settle * 1.0);
    eye.lerp(diveEye, dive); look.lerp(diveLook, dive);
    camera.position.copy(eye); camera.lookAt(look);
    camera.fov = 38 + dive * 22; camera.updateProjectionMatrix();

    renderer.render(scene, camera);
    if (!painted) { painted = true; onPaint(); }
    if (warp < 1) frame = requestAnimationFrame(draw);
  };
  const resume = () => { if (!disposed && !paused && !contextLost && !document.hidden && !frame) frame = requestAnimationFrame(draw); };
  const visibility = () => { if (document.hidden) { cancelAnimationFrame(frame); frame = 0; previous = 0; } else resume(); };
  const lost = (event: Event) => { event.preventDefault(); contextLost = true; cancelAnimationFrame(frame); frame = 0; };
  const restored = () => { contextLost = false; resume(); };
  const observer = new ResizeObserver(size); observer.observe(container); size();
  document.addEventListener("visibilitychange", visibility);
  renderer.domElement.addEventListener("webglcontextlost", lost);
  renderer.domElement.addEventListener("webglcontextrestored", restored);
  resume();
  return {
    enter() { if (entryStart === null) entryStart = performance.now(); resume(); },
    setPaused(value) { paused = value; if (value) { cancelAnimationFrame(frame); frame = 0; previous = 0; } else resume(); },
    dispose() {
      if (disposed) return; disposed = true;
      cancelAnimationFrame(frame); observer.disconnect(); document.removeEventListener("visibilitychange", visibility);
      renderer.domElement.removeEventListener("webglcontextlost", lost);
      renderer.domElement.removeEventListener("webglcontextrestored", restored);
      disposables.forEach(item => item.dispose());
      scene.clear(); renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
    },
  };
}
