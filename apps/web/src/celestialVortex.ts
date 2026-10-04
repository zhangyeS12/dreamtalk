import * as THREE from "three";

export interface VortexController { enter(): void; setPaused(paused: boolean): void; dispose(): void }

// Real world-space ribbon paths. The local XY pair is only the ribbon's UV grid;
// depth, orbital tilt, perspective and camera travel are evaluated in 3D.
const ribbonVertex = `
  uniform float uTime, uPhase, uDepth, uRadius, uWidth;
  varying vec2 vRibbon;
  vec3 orbit(float age) {
    float theta = uPhase + uTime * .34 - age * 1.65;
    float radius = uRadius + age * .55;
    return vec3(cos(theta) * radius, sin(theta) * radius,
      uDepth + sin(theta * .85 + uPhase) * 3.2 - age * 3.0);
  }
  void main() {
    float age = position.x;
    vec4 point = modelViewMatrix * vec4(orbit(age), 1.0);
    vec4 next = modelViewMatrix * vec4(orbit(age + .003), 1.0);
    vec2 tangent = normalize(next.xy - point.xy + vec2(.00001));
    vec2 side = vec2(-tangent.y, tangent.x);
    point.xy += side * position.y * uWidth * (.24 + .76 * (1.0 - age));
    gl_Position = projectionMatrix * point;
    vRibbon = vec2(age, position.y);
  }
`;
const ribbonFragment = `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying vec2 vRibbon;
  void main() {
    float cross = abs(vRibbon.y);
    float halo = exp(-cross * cross * 4.5);
    float core = exp(-cross * cross * 100.0);
    float tail = pow(1.0 - vRibbon.x, 1.6) * (1.0 - smoothstep(.96, 1.0, vRibbon.x));
    vec3 light = mix(uColor, vec3(1.0, .97, .9), core * .8);
    gl_FragColor = vec4(light, (halo * .3 + core * .7) * tail * uOpacity);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

function ribbonGeometry() {
  const segments = 64;
  const positions: number[] = [], indices: number[] = [];
  for (let i = 0; i <= segments; i++) positions.push(i / segments, -1, 0, i / segments, 1, 0);
  for (let i = 0; i < segments; i++) {
    const a = i * 2;
    indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
  }
  return new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(positions, 3)).setIndex(indices);
}

function lightTexture() {
  const canvas = document.createElement("canvas"); canvas.width = canvas.height = 128;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("light_texture_unavailable");
  const glow = context.createRadialGradient(64, 64, 0, 64, 64, 64);
  glow.addColorStop(0, "rgba(255,255,255,1)");
  glow.addColorStop(.075, "rgba(255,255,255,.98)");
  glow.addColorStop(.18, "rgba(255,255,255,.35)");
  glow.addColorStop(.48, "rgba(255,255,255,.065)");
  glow.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = glow; context.fillRect(0, 0, 128, 128);
  const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export function createCelestialVortex(container: HTMLElement, onPaint: () => void): VortexController {
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.65));
  renderer.setClearColor(0x080a14, 0); renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.15;
  renderer.domElement.setAttribute("aria-hidden", "true");
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(48, 1, .1, 200);
  const focus = new THREE.Vector3(0, 0, -7);
  const orbit = new THREE.Group(); orbit.rotation.set(.37, -.25, -.16); scene.add(orbit);
  const geometries = new Set<THREE.BufferGeometry>(), materials = new Set<THREE.Material>();
  const track = <T extends THREE.Material>(material: T): T => { materials.add(material); return material; };
  const geometry = ribbonGeometry(); geometries.add(geometry);
  const texture = lightTexture();
  const pearl = new THREE.Color("#d7e3ff"), gold = new THREE.Color("#f7ce94");
  const meteors = Array.from({ length: 26 }, (_, i) => {
    const layer = i % 5;
    const depth = 8 - layer * 7 + Math.sin(i * 2.4) * 1.8;
    const phase = i * 2.399963;
    const radius = 9.1 - layer * .76 + Math.cos(i * 1.7) * .65;
    const color = i % 3 === 0 ? gold : pearl;
    const material = track(new THREE.ShaderMaterial({
      vertexShader: ribbonVertex, fragmentShader: ribbonFragment,
      uniforms: { uTime: { value: 0 }, uPhase: { value: phase }, uDepth: { value: depth },
        uRadius: { value: radius }, uWidth: { value: .16 + (i % 4) * .027 },
        uColor: { value: color }, uOpacity: { value: .83 - layer * .07 } },
      transparent: true, depthWrite: false, depthTest: true, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    }));
    const ribbon = new THREE.Mesh(geometry, material); ribbon.frustumCulled = false; orbit.add(ribbon);
    const tip = new THREE.Sprite(track(new THREE.SpriteMaterial({ map: texture, color, transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false, opacity: .94 - layer * .1 })));
    tip.scale.setScalar(.6 + (i % 3) * .14); orbit.add(tip);
    return { material, tip, phase, depth, radius };
  });

  // Opaque pearl nucleus occludes the rear trails; it is not a flat CSS disc.
  const nucleusGeometry = new THREE.SphereGeometry(1.25, 48, 32); geometries.add(nucleusGeometry);
  const nucleusMaterial = track(new THREE.MeshPhysicalMaterial({ color: 0x8d9fb7, metalness: .38, roughness: .43,
    emissive: 0x25324c, emissiveIntensity: .4, clearcoat: .65 }));
  const nucleus = new THREE.Mesh(nucleusGeometry, nucleusMaterial); nucleus.position.copy(focus); scene.add(nucleus);
  scene.add(new THREE.AmbientLight(0x8499c9, 1.5));
  const sun = new THREE.DirectionalLight(0xffe3bb, 4.5); sun.position.set(-5, 5, 8); scene.add(sun);
  const moon = new THREE.DirectionalLight(0x91b6ff, 2); moon.position.set(5, -3, 2); scene.add(moon);
  const aura = new THREE.Sprite(track(new THREE.SpriteMaterial({ map: texture, color: 0xe1b782, transparent: true,
    opacity: .3, blending: THREE.AdditiveBlending, depthWrite: false })));
  aura.position.set(0, 0, -9); aura.scale.setScalar(14); scene.add(aura);
  const haloGeometry = new THREE.TorusGeometry(2.45, .012, 8, 128); geometries.add(haloGeometry);
  const halo = new THREE.Mesh(haloGeometry, track(new THREE.MeshBasicMaterial({ color: 0xcdb79a, transparent: true,
    opacity: .2, depthWrite: false, blending: THREE.AdditiveBlending })));
  halo.position.copy(focus); halo.rotation.set(1.13, .25, -.5); scene.add(halo);

  const stars: number[] = [], sizes: number[] = [];
  for (let i = 0; i < 900; i++) {
    const angle = i * 2.399963, radius = 10 + ((i * 67) % 370) / 10;
    stars.push(Math.cos(angle) * radius, Math.sin(angle) * radius, -75 + ((i * 31) % 800) / 10);
    sizes.push(.025 + (i % 5) * .012);
  }
  const starGeometry = new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(stars, 3))
    .setAttribute("aSize", new THREE.Float32BufferAttribute(sizes, 1)); geometries.add(starGeometry);
  const starMaterial = track(new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uTexture: { value: texture }, uPixelRatio: { value: renderer.getPixelRatio() } },
    vertexShader: `attribute float aSize; uniform float uTime, uPixelRatio; varying float vLight;
      void main() { vec4 point = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * point;
        gl_PointSize = clamp(aSize * 450.0 * uPixelRatio / max(1.0, -point.z), 1.5, 7.0);
        vLight = .32 + .18 * sin(uTime * .4 + position.x * 5.0); }`,
    fragmentShader: `uniform sampler2D uTexture; varying float vLight;
      void main() { gl_FragColor = vec4(.78, .85, 1.0, texture2D(uTexture, gl_PointCoord).a * vLight);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  }));
  scene.add(new THREE.Points(starGeometry, starMaterial));
  let disposed = false, paused = false, contextLost = false, painted = false, frame = 0, elapsed = 0, previous = 0;
  let entryStart: number | null = null;
  const size = () => {
    const width = Math.max(1, container.clientWidth), height = Math.max(1, container.clientHeight);
    renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix();
  };
  const draw = (now: number) => {
    frame = 0;
    if (disposed || document.hidden || paused || contextLost) { previous = 0; return; }
    elapsed += previous ? Math.min((now - previous) / 1000, .05) : 0; previous = now;
    const travel = entryStart === null ? 0 : Math.min(1, (now - entryStart) / 850);
    const advance = travel * travel * (3 - 2 * travel);
    camera.position.set(Math.sin(elapsed * .13) * .4 * (1 - travel), .8 * (1 - travel), 27 - advance * 42);
    camera.lookAt(0, 0, -40);
    orbit.rotation.z = -.16 + Math.sin(elapsed * .08) * .075;
    orbit.rotation.y = -.25 + Math.sin(elapsed * .11) * .07;
    for (const meteor of meteors) {
      meteor.material.uniforms.uTime.value = elapsed;
      const theta = meteor.phase + elapsed * .34;
      meteor.tip.position.set(Math.cos(theta) * meteor.radius, Math.sin(theta) * meteor.radius,
        meteor.depth + Math.sin(theta * .85 + meteor.phase) * 3.2);
    }
    nucleus.visible = halo.visible = travel < .18;
    aura.material.opacity = .3 * (1 - travel);
    starMaterial.uniforms.uTime.value = elapsed;
    renderer.render(scene, camera);
    if (!painted) { painted = true; onPaint(); }
    if (travel < 1) frame = requestAnimationFrame(draw);
  };
  const resume = () => {
    if (!disposed && !paused && !contextLost && !document.hidden && !frame) frame = requestAnimationFrame(draw);
  };
  const visibility = () => { if (document.hidden) { cancelAnimationFrame(frame); frame = 0; previous = 0; } else resume(); };
  const lost = (event: Event) => { event.preventDefault(); contextLost = true; cancelAnimationFrame(frame); frame = 0; };
  const restored = () => { contextLost = false; resume(); };
  const observer = new ResizeObserver(size); observer.observe(container); size();
  document.addEventListener("visibilitychange", visibility);
  renderer.domElement.addEventListener("webglcontextlost", lost);
  renderer.domElement.addEventListener("webglcontextrestored", restored);
  resume();
  return {
    enter() { entryStart = performance.now(); resume(); },
    setPaused(value) { paused = value; if (value) { cancelAnimationFrame(frame); frame = 0; previous = 0; } else resume(); },
    dispose() {
      if (disposed) return; disposed = true;
      cancelAnimationFrame(frame); observer.disconnect(); document.removeEventListener("visibilitychange", visibility);
      renderer.domElement.removeEventListener("webglcontextlost", lost);
      renderer.domElement.removeEventListener("webglcontextrestored", restored);
      geometries.forEach(item => item.dispose()); materials.forEach(item => item.dispose()); texture.dispose();
      scene.clear(); renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
    },
  };
}
