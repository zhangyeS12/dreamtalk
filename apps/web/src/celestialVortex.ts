import * as THREE from "three";

export interface VortexController { enter(): void; setPaused(paused: boolean): void; dispose(): void }

// Real world-space ribbon paths. The local XY pair is only the ribbon's UV grid;
// depth, orbital tilt, perspective and camera travel are evaluated in 3D.
const ribbonVertex = `
  uniform float uTime, uPhase, uDepth, uRadius, uWidth, uSpeed;
  varying vec2 vRibbon;
  vec3 orbit(float age) {
    float theta = uPhase + uTime * uSpeed - age * 2.1;
    float radius = uRadius + age * .32;
    return vec3(cos(theta) * radius, sin(theta) * radius * .68,
      uDepth + sin(theta) * 4.6 - age * 1.8);
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
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.1;
  renderer.domElement.setAttribute("aria-hidden", "true");
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(46, 1, .1, 200);
  const focus = new THREE.Vector3(0, 0, -7);
  const orbit = new THREE.Group(); orbit.rotation.set(.24, -.16, -.32); scene.add(orbit);
  const geometries = new Set<THREE.BufferGeometry>(), materials = new Set<THREE.Material>();
  const track = <T extends THREE.Material>(material: T): T => { materials.add(material); return material; };
  const geometry = ribbonGeometry(); geometries.add(geometry);
  const texture = lightTexture();
  const pearl = new THREE.Color("#d7e3ff"), gold = new THREE.Color("#f7ce94");
  const meteors = Array.from({ length: 20 }, (_, i) => {
    const layer = i % 4;
    const depth = 3 - layer * 5.5 + Math.sin(i * 2.4) * .8;
    const phase = i * 2.399963;
    const radius = 10.8 - layer * .68 + Math.cos(i * 1.7) * .42;
    const speed = .22 + layer * .018;
    const color = i % 3 === 0 ? gold : pearl;
    const material = track(new THREE.ShaderMaterial({
      vertexShader: ribbonVertex, fragmentShader: ribbonFragment,
      uniforms: { uTime: { value: 0 }, uPhase: { value: phase }, uDepth: { value: depth },
        uRadius: { value: radius }, uWidth: { value: .13 + (i % 4) * .024 }, uSpeed: { value: speed },
        uColor: { value: color }, uOpacity: { value: .90 - layer * .10 } },
      transparent: true, depthWrite: false, depthTest: true, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    }));
    const ribbon = new THREE.Mesh(geometry, material); ribbon.frustumCulled = false; orbit.add(ribbon);
    const tip = new THREE.Sprite(track(new THREE.SpriteMaterial({ map: texture, color, transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false, opacity: .94 - layer * .1 })));
    tip.scale.setScalar(.48 + (i % 3) * .12); orbit.add(tip);
    return { material, tip, phase, depth, radius, speed };
  });

  // Two opaque, lit bodies frame the original logo without replacing it.
  // The rear ribbons depth-test against them; silhouettes are real spheres.
  const nucleusGeometry = new THREE.SphereGeometry(1.6, 48, 32); geometries.add(nucleusGeometry);
  const nucleusMaterial = track(new THREE.MeshPhysicalMaterial({ color: 0x7186af, metalness: .42, roughness: .39,
    emissive: 0x101727, emissiveIntensity: .16, clearcoat: .55 }));
  const nucleus = new THREE.Mesh(nucleusGeometry, nucleusMaterial); nucleus.position.set(-6.4, 2.8, -9); scene.add(nucleus);
  const solar = new THREE.Mesh(nucleusGeometry, track(new THREE.MeshStandardMaterial({ color: 0xd8b77d, metalness: .3,
    roughness: .55, emissive: 0x79502a, emissiveIntensity: .65 })));
  solar.scale.setScalar(.5); solar.position.set(6.1, -2.4, -13); scene.add(solar);
  scene.add(new THREE.AmbientLight(0x8499c9, .45));
  const sun = new THREE.DirectionalLight(0xffe3bb, 4.5); sun.position.set(-8, 5, -2); scene.add(sun);
  const moon = new THREE.DirectionalLight(0x91b6ff, 1.4); moon.position.set(5, -3, 1); scene.add(moon);
  const solarGlow = new THREE.Sprite(track(new THREE.SpriteMaterial({ map: texture, color: 0xe6b76e, transparent: true,
    opacity: .6, blending: THREE.AdditiveBlending, depthWrite: false })));
  solarGlow.position.copy(solar.position); solarGlow.position.z -= 1; solarGlow.scale.setScalar(5.5); scene.add(solarGlow);
  const aura = new THREE.Sprite(track(new THREE.SpriteMaterial({ map: texture, color: 0xe1b782, transparent: true,
    opacity: .3, blending: THREE.AdditiveBlending, depthWrite: false })));
  aura.position.set(0, 0, -9); aura.scale.setScalar(14); scene.add(aura);
  const haloGeometry = new THREE.TorusGeometry(8.2, .009, 6, 180); geometries.add(haloGeometry);
  const halo = new THREE.Mesh(haloGeometry, track(new THREE.MeshBasicMaterial({ color: 0xcdb79a, transparent: true,
    opacity: .24, depthWrite: false, blending: THREE.AdditiveBlending })));
  halo.position.copy(focus); halo.rotation.set(1.0, .25, -.4); scene.add(halo);

  // A single point cloud adds a fine orbital dust band without postprocessing.
  const dustPositions: number[] = [], dustColors: number[] = [];
  for (let i = 0; i < 1400; i++) {
    const theta = i * 2.399963;
    const scatter = Math.sin(i * 78.233) * .5 + Math.cos(i * 12.9898) * .5;
    const radius = 10.3 + scatter * .7;
    dustPositions.push(Math.cos(theta) * radius, Math.sin(theta) * radius * .68, -5 + Math.sin(theta) * 4.6 + scatter * .4);
    const color = i % 3 ? pearl : gold;
    dustColors.push(color.r, color.g, color.b);
  }
  const dustGeometry = new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(dustPositions, 3))
    .setAttribute("color", new THREE.Float32BufferAttribute(dustColors, 3)); geometries.add(dustGeometry);
  const dust = new THREE.Points(dustGeometry, track(new THREE.PointsMaterial({ map: texture, size: .075, sizeAttenuation: true,
    vertexColors: true, opacity: .45, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })));
  orbit.add(dust);

  const stars: number[] = [], sizes: number[] = [];
  for (let i = 0; i < 650; i++) {
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
    const advance = travel * travel * travel;
    const cameraDistance = camera.aspect < 1 ? 30 / Math.max(.55, camera.aspect) : 30;
    camera.position.set(Math.sin(elapsed * .13) * .3 * (1 - travel), .5 * (1 - travel), cameraDistance - advance * (cameraDistance + 15));
    camera.lookAt(0, 0, -40);
    orbit.rotation.z = -.32 + Math.sin(elapsed * .08) * .04;
    orbit.rotation.y = -.16 + Math.sin(elapsed * .11) * .06;
    dust.rotation.z = elapsed * .025;
    for (const meteor of meteors) {
      meteor.material.uniforms.uTime.value = elapsed;
      const theta = meteor.phase + elapsed * meteor.speed;
      meteor.tip.position.set(Math.cos(theta) * meteor.radius, Math.sin(theta) * meteor.radius * .68,
        meteor.depth + Math.sin(theta) * 4.6);
    }
    aura.material.opacity = .3 * (1 - travel);
    solarGlow.material.opacity = .6 * (1 - travel);
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
