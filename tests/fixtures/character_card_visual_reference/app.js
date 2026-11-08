"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const escape = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const modulo = (v, n) => ((v % n) + n) % n;
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const themes = [
    { name: "月夜蓝", color: "#253e57", accent: "#f0d5a0" },
    { name: "暮色紫", color: "#49354e", accent: "#f3d6ba" },
    { name: "松林绿", color: "#25463e", accent: "#e8dbb4" },
    { name: "赤陶红", color: "#673b3c", accent: "#f4d9b6" },
    { name: "银墨黑", color: "#252c3e", accent: "#d2dfed" }
  ];
  const stickerNames = { "☾": "新月", "✦": "四芒星", "✧": "空心星", "❖": "菱花", "✿": "小花", "⌁": "波纹" };
  let serial = 10;
  function face(theme, name, role, back = false) {
    return { ...theme, layout: back ? "notes" : "portrait", material: "matte", frame: true, image: null, sourceImage: null, imageCrop: null, imageOpacity: 100,
      layers: back ? [{ id: `layer-${serial++}`, kind: "text", text: "每一次相遇\n都从一页空白开始。", x: 50, y: 53, size: 22, rotation: 0, opacity: 100, color: theme.accent }] : [
        { id: `layer-${serial++}`, kind: "name", text: name, x: 28, y: 66, size: 31, rotation: 0, opacity: 100, color: theme.accent },
        { id: `layer-${serial++}`, kind: "role", text: role, x: 28, y: 81, size: 12, rotation: 0, opacity: 88, color: theme.accent }
      ] };
  }
  function card(id, name, role, theme, glyph) {
    return { id, name, role, glyph, front: face(theme, name, role), back: face(theme, name, role, true) };
  }
  function initialData() {
    return {
      cards: [card("c-moon", "林见月", "档案修复师", themes[0], "月"), card("c-tide", "陆听澜", "星轨调查员", themes[1], "澜"), card("c-forest", "白榆", "森林里的风信使", themes[2], "榆"), card("c-night", "沈砚", "夜航记录员", themes[4], "砚")],
      worlds: [
        { id: "w-train", name: "月下列车", color: "#344762", glyph: "☾", locations: ["观景车厢", "月台", "餐车"], members: [] },
        { id: "w-harbor", name: "雾港来信", color: "#33515a", glyph: "⌁", locations: ["灯塔", "旧港口", "书店"], members: [] },
        { id: "w-island", name: "无声群岛", color: "#5a4260", glyph: "✧", locations: ["海岸", "白塔"], members: [] },
        { id: "w-sun", name: "远日档案", color: "#6a4b3c", glyph: "✦", locations: ["天文台", "档案馆"], members: [] },
        { id: "w-forest", name: "森林回廊", color: "#304b42", glyph: "❖", locations: ["林间小屋", "回廊"], members: [] },
        { id: "w-rain", name: "雨夜茶馆", color: "#3a3b54", glyph: "⌁", locations: ["茶馆", "长街"], members: [] }
      ]
    };
  }
  let data = initialData();
  let view = "worlds", selectedCard = null, selectedWorld = null;
  let rotating = false, yaw = -8, pitch = 7, draft = null, designFace = "front", activeLayer = null;
  let symmetryUndo = null, cropSession = null, cropSequence = 0;
  let drag = null, gesture = null, suppressClick = false, switchTimer = null, dropWorld = null, pendingCard = null;
  let cancelledPointer = false;
  let toastTimer, createType = "cards";
  const offsets = { worlds: 2.5 * 85, cards: 0 };
  const nodes = { worlds: [], cards: [] };
  const animations = { worlds: 0, cards: 0 };
  const stage = $("stage"), app = $("app"), archive = $("archive");
  const nativeFrame = $("native-worlds");
  function syncNativeWorlds() {
    nativeFrame.contentWindow?.postMessage({source:"dreamtalk-card-preview",type:"worlds",worlds:data.worlds.map(({id,name,color}) => ({id,name,color}))}, "*");
  }
  window.addEventListener("message", event => {
    if (event.source !== nativeFrame.contentWindow || event.data?.source !== "dreamtalk-native-shelf") return;
    if (event.data.type === "request-worlds") syncNativeWorlds();
    if (event.data.type === "selected") selectedWorld = event.data.id;
    if (event.data.type === "notice") toast(event.data.text);
  });

  function currentCard() { return draft || data.cards.find(c => c.id === selectedCard); }
  function restPose(id) {
    let hash = 5381;
    for (const char of id) hash = ((hash * 33) ^ char.charCodeAt(0)) >>> 0;
    hash = Math.imul(hash ^ (hash >>> 16), 0x45d9f3b);
    hash = Math.imul(hash ^ (hash >>> 16), 0x45d9f3b);
    hash = (hash ^ (hash >>> 16)) >>> 0;
    return {roll:(hash % 111) - 55, yaw:((hash >>> 5) % 67) - 33, pitch:((hash >>> 11) % 41) - 20, y:((hash >>> 17) % 75) - 37, phase:(hash % 360) / 57.3};
  }
  let floatFrame = null;
  function wakeFloat() {
    if (floatFrame !== null || view !== "cards" || rotating || draft || drag || document.hidden || reducedMotion.matches) return;
    floatFrame = requestAnimationFrame(() => { floatFrame = null; draw(); wakeFloat(); });
  }
  function popMotion() {
    nodes.cards.forEach(n => n.el.classList.add("pop-transition"));
    setTimeout(() => nodes.cards.forEach(n => n.el.classList.remove("pop-transition")), 470);
  }
  function returnCard() {
    popMotion(); rotating = false; selectedCard = null; activeLayer = null;
    updateInfo(); draw(); wakeFloat();
  }
  function toast(message) {
    clearTimeout(toastTimer); $("toast").textContent = message; $("toast").hidden = false;
    toastTimer = setTimeout(() => { $("toast").hidden = true; }, 3400);
  }
  function cardFaceMarkup(c, side) {
    const f = c[side];
    return `<span class="card-face card-${side} ${f.frame ? "with-frame" : ""}" data-side="${side}" data-material="${f.material}" style="--face-color:${f.color};--face-accent:${f.accent}">
      ${f.image ? `<img class="card-image" src="${escape(f.image)}" alt="" draggable="false" style="opacity:${f.imageOpacity / 100}">` : ""}
      ${(f.layout || (side === "front" ? "portrait" : "notes")) === "portrait" ? `<span class="card-art"><span class="card-orbit"></span><span class="card-glyph">${escape(c.glyph)}</span></span><span class="card-brand">dreamtalk</span><span class="card-corner-star">✦</span>` : `<span class="back-tag">${escape(c.name)} · 角色档案</span><span class="back-rule"></span><span class="back-sign">在不同的世界，留下不同的故事。</span>`}
      <span class="card-foil"></span>
      ${f.layers.map(l => `<span class="card-layer ${l.id === activeLayer ? "active-layer" : ""}" data-layer="${l.id}" data-kind="${l.kind}" style="left:${l.x}%;top:${l.y}%;font-size:calc(var(--W)*${l.size / 410});--layer-px:${l.size}px;--r:${l.rotation}deg;opacity:${l.opacity / 100};color:${l.color}">${escape(l.text)}</span>`).join("")}
      <span class="card-number">DT · ${escape(c.id.replace("c-", "").slice(0, 8).toUpperCase())}</span>
    </span>`;
  }
  function cardMarkup(c) { return cardFaceMarkup(c, "front") + cardFaceMarkup(c, "back"); }
  function renderCards() {
    for (const node of nodes.cards) {
      if (!node.item.blank) {
        const c = node.item.id === selectedCard ? currentCard() : data.cards.find(item => item.id === node.item.id);
        node.el.innerHTML = cardMarkup(c);
        node.el.setAttribute("aria-label", `选择角色卡：${c.name}`);
      }
    }
    draw();
  }
  function rebuild(which) {
    if (which === "worlds") { nodes.worlds = []; syncNativeWorlds(); updateCounts(); return; }
    const ring = $(which === "worlds" ? "world-ring" : "card-ring");
    const items = [...data[which], ...Array.from({length:Math.max(which === "worlds" ? 1 : 2, (which === "worlds" ? 12 : 8) - data[which].length)}, (_, i) => ({id:`blank-${i}`, blank:true}))];
    ring.replaceChildren(); nodes[which] = [];
    for (let lap = -1; lap <= 1; lap++) {
      items.forEach((item, i) => {
        const el = document.createElement("button"); el.type = "button"; el.dataset.id = item.id;
        el.className = `${which === "worlds" ? "world-object" : "card-object"}${item.blank ? " blank" : ""}`;
        el.dataset.index = String(i + lap * items.length);
        if (which === "worlds") {
          el.style.setProperty("--case", item.color || "#141b2b");
          el.setAttribute("aria-label", item.blank ? "创建新世界" : `查看世界：${item.name}`);
          el.innerHTML = `<span class="book-face book-spine"><span class="book-band"></span><span class="spine-title">${item.blank ? "＋" : escape(item.name)}</span>${item.blank ? "" : `<span class="spine-glyph">${item.glyph}</span>`}<span class="spine-brand">dreamtalk</span></span><span class="book-face book-cover"><strong>${item.blank ? "新的世界" : escape(item.name)}</strong><span class="cover-orbit"></span></span><span class="book-face book-back"></span><span class="book-face book-edge"></span>`;
        } else {
          el.setAttribute("aria-label", item.blank ? "创建新角色卡" : `选择角色卡：${item.name}`);
          el.innerHTML = item.blank ? `<span class="card-face card-front"><span class="blank-card-body"><b>＋</b><span>下一次相遇</span><small>创建一张新的角色卡</small></span></span>` : cardMarkup(item.id === selectedCard ? currentCard() : item);
        }
        ring.append(el); nodes[which].push({ el, item, index:i + lap * items.length, total:items.length * 3, dx:0 });
      });
    }
    updateCounts(); draw();
  }
  function step(which = view) {
    if (which === "worlds") return innerWidth <= 680 ? 66 : 85;
    const first = nodes.cards[0]?.el;
    const width = first ? parseFloat(getComputedStyle(first).getPropertyValue("--W")) || 410 : 410;
    return width + (innerWidth <= 680 ? 40 : 75);
  }
  function draw() {
    if (view === "worlds") return;
    const width = stage.clientWidth, spacing = step(), list = nodes[view];
    if (!list.length) return;
    const total = list[0].total * spacing;
    let nearestSelected = null;
    for (const node of list) {
      node.dx = modulo(node.index * spacing - offsets[view] + total / 2, total) - total / 2;
      if (node.item.id === selectedCard && (!nearestSelected || Math.abs(node.dx) < Math.abs(nearestSelected.dx))) nearestSelected = node;
    }
    for (const node of list) {
      const dx = node.dx;
      const isCard = view === "cards", selected = isCard && node === nearestSelected;
      const isolated = isCard && (rotating || draft);
      const visible = (isolated && selected) || Math.abs(dx) < width / 2 + (isCard ? 330 : 220);
      node.el.style.visibility = visible ? "visible" : "hidden";
      node.el.setAttribute("aria-hidden", String(!visible));
      node.el.tabIndex = visible ? 0 : -1;
      node.el.classList.toggle("selected", selected && !node.item.blank);
      node.el.classList.toggle("chosen-layer", !!draft && selected);
      node.el.classList.toggle("chosen", !isCard && selectedWorld === node.item.id);
      node.el.classList.toggle("source-dragging", !!drag && drag.card.id === node.item.id);
      node.el.setAttribute("aria-pressed", String(isCard ? selected : selectedWorld === node.item.id));
      if (isCard) {
        const x = isolated && selected ? 0 : dx;
        const rest = restPose(node.item.id);
        const z = isolated && selected ? 100 : -dx * dx / 3000 - (isolated ? 100 : 0);
        const yRot = isolated && selected ? yaw : clamp(-dx * .018 + rest.yaw, -45, 45);
        const xRot = isolated && selected ? pitch : rest.pitch;
        const bob = reducedMotion.matches || isolated ? 0 : Math.sin(performance.now() / 1900 + rest.phase) * 7;
        const y = isolated && selected ? -14 : rest.y + bob;
        const roll = isolated && selected ? 0 : rest.roll;
        node.el.style.transform = `translate3d(${x}px,${y}px,${z}px) rotateZ(${roll}deg) rotateX(${xRot}deg) rotateY(${yRot}deg)`;
        node.el.style.opacity = String(visible ? (isolated && !selected ? .12 : clamp(1 - Math.abs(dx) / (width * 1.3), .28, 1)) : 0);
        node.el.style.pointerEvents = isolated && !selected ? "none" : "auto";
        if (visible && !node.item.blank) {
          const frontFacing = Math.cos(yRot * Math.PI / 180) * Math.cos(xRot * Math.PI / 180) >= 0;
          node.el.querySelector(".card-front").hidden = !frontFacing;
          node.el.querySelector(".card-back").hidden = frontFacing;
        }
        node.el.style.zIndex = selected ? "3" : "1";
      } else {
        const yRot = clamp(-dx * .019, -34, 34);
        node.el.style.transform = `translate3d(${dx}px,0,${-dx * dx / 2800 - 120}px) rotateY(${yRot}deg)`;
      }
    }
  }
  function animateTo(target, which = view) {
    const version = ++animations[which], start = offsets[which], time = performance.now();
    const tick = now => {
      if (animations[which] !== version) return;
      const t = reducedMotion.matches ? 1 : clamp((now - time) / 340, 0, 1);
      offsets[which] = start + (target - start) * (1 - (1 - t) ** 4);
      if (which === view) draw();
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  function updateCounts() {
    $("world-count").textContent = data.worlds.length;
    $("card-count").textContent = data.cards.length;
    $("collection-count").textContent = view === "worlds" ? `${data.worlds.length} 个世界` : `${data.cards.length} 张角色卡`;
  }
  function updateInfo() {
    const c = currentCard();
    $("selected-info").hidden = view !== "cards" || !c || !rotating;
    if (c) { $("selected-name").textContent = c.name; $("selected-role").textContent = c.role || "尚未填写身份描述"; }
    $("rotation-tools").hidden = !rotating || !!draft;
    $("stage-hint").textContent = drag ? (view === "cards" ? "保持按住 · 拖到下方胶囊切换世界书" : "拖到目标世界书上松手 · Esc 取消") : draft ? "卡片位置已固定 · 可拖动卡面内的组件" : rotating ? "拖动可旋转 · 归位后才能拿起卡片投放" : view === "worlds" ? "左右拖动书架 · 首尾相接 · 点击书本查看世界" : "拖动空白处浏览 · 拖动悬浮卡片投放 · 点击展开查看";
    archive.classList.toggle("is-rotating", rotating);
  }
  function setView(next, carrying = false) {
    if (draft || (drag && !carrying)) return;
    view = next; rotating = false;
    app.classList.toggle("native-worlds-active", next === "worlds");
    nativeFrame.classList.toggle("inactive", next !== "worlds");
    nativeFrame.inert = next !== "worlds";
    nativeFrame.setAttribute("aria-hidden", String(next !== "worlds"));
    archive.dataset.view = next;
    $("world-ring").hidden = next !== "worlds"; $("card-ring").hidden = next !== "cards";
    for (const which of ["worlds", "cards"]) {
      const tab = $(which === "worlds" ? "world-tab" : "card-tab");
      tab.setAttribute("aria-selected", String(next === which)); tab.tabIndex = next === which ? 0 : -1;
    }
    $("collection-name").textContent = next === "worlds" ? "世界书架" : "角色卡库";
    stage.setAttribute("aria-label", next === "worlds" ? "世界书架，左右拖动浏览" : "角色卡库，拖动空白处浏览，选中卡片可拖入世界");
    $("world-detail").hidden = true;
    updateCounts(); updateInfo(); draw(); wakeFloat();
  }
  function selectCard(node) {
    if (node.item.blank) return create("cards");
    popMotion(); selectedCard = node.item.id; activeLayer = null; rotating = true; yaw = 0; pitch = 0;
    updateInfo(); draw();
  }
  function change(direction) {
    if (rotating || draft || drag) return;
    const target = Math.round(offsets[view] / step()) + direction;
    if (view === "cards") {
      const logical = modulo(target, nodes.cards.length / 3);
      const item = nodes.cards.find(n => n.index === logical)?.item;
      selectedCard = null;
      updateInfo();
    }
    animateTo(target * step());
  }
  function selectClosest() {
    if (view === "cards") {
      const nearest = nodes.cards.reduce((a, b) => Math.abs(a.dx) < Math.abs(b.dx) ? a : b);
      selectedCard = null;
      updateInfo(); draw();
    }
  }
  function showWorld(id) {
    const world = data.worlds.find(w => w.id === id);
    if (!world) return;
    selectedWorld = id; $("world-title").textContent = world.name; $("world-detail").hidden = false;
    const root = $("world-members"); root.replaceChildren();
    if (!world.members.length) { const p = document.createElement("p"); p.className = "empty-world"; p.textContent = "这里还没有角色。拿一张角色卡，开启第一次相遇。"; root.append(p); }
    world.members.forEach(member => {
      const row = document.createElement("div"); row.className = "member-row";
      row.innerHTML = `<div><strong>${escape(member.name)}</strong><small>${member.location ? "已设置初始地点" : "无法移动 · 不显示在地点图中"}</small></div><span class="place-tag">${escape(member.location || "无地点")}</span>`;
      root.append(row);
    });
    draw();
  }
  function openAdd(cardId, worldId = null) {
    pendingCard = cardId; const c = data.cards.find(item => item.id === cardId);
    if (!c) return;
    $("add-title").textContent = `将${c.name}加入世界`;
    $("add-description").textContent = "为这次相遇选择一本世界书。";
    $("target-world").innerHTML = data.worlds.map(w => `<option value="${w.id}">${escape(w.name)}</option>`).join("");
    $("target-world").value = worldId || selectedWorld || data.worlds[0].id;
    updateLocations(); $("add-dialog").showModal();
  }
  function updateLocations() {
    const w = data.worlds.find(item => item.id === $("target-world").value);
    $("initial-place").innerHTML = `<option value="">无</option>` + w.locations.map(loc => `<option value="${escape(loc)}">${escape(loc)}</option>`).join("");
    $("initial-place").value = "";
    const exists = w.members.some(m => m.cardId === pendingCard);
    $("confirm-add").disabled = exists;
    $("add-description").textContent = exists ? "这张角色卡已加入此世界，可以选择其他世界。" : "为这次相遇选择一本世界书。";
    updateLocationNote();
  }
  function updateLocationNote() {
    $("location-note").textContent = $("initial-place").value ? "角色会出现在所选地点中，可参与该世界的地点活动。" : "无地点的角色不能移动，也不显示在地点图中。";
  }
  $("target-world").addEventListener("change", updateLocations);
  $("initial-place").addEventListener("change", updateLocationNote);
  $("add-form").addEventListener("submit", event => {
    event.preventDefault();
    const w = data.worlds.find(item => item.id === $("target-world").value), c = data.cards.find(item => item.id === pendingCard);
    if (!c || !w || w.members.some(m => m.cardId === c.id)) return;
    w.members.push({ cardId: c.id, name: c.name, location: $("initial-place").value || null });
    $("add-dialog").close();
    if (view !== "worlds") setView("worlds");
    showWorld(w.id);
    nodes.worlds.filter(n => n.item.id === w.id).forEach(n => { n.el.classList.add("just-added"); setTimeout(() => n.el.classList.remove("just-added"), 750); });
    toast(`${c.name}已加入「${w.name}」 · 原卡仍保留在卡库中`);
  });

  function beginDrag(c, x, y) {
    drag = {card:c, x, y}; selectedCard = c.id; rotating = false; selectedWorld = null; $("world-detail").hidden = true;
    app.classList.add("is-dragging");
    $("drag-ghost").innerHTML = `<span class="card-object">${cardMarkup(c)}</span>`;
    $("drag-ghost").querySelector(".card-back").hidden = true;
    $("drag-ghost").hidden = false; $("drag-caption").hidden = false;
    updateInfo(); draw(); updateDrag(x, y);
  }
  function clearSwitch() {
    clearTimeout(switchTimer); switchTimer = null; $("collection-switch").classList.remove("drag-over");
  }
  function updateDrag(x, y) {
    if (!drag) return;
    drag.x = x; drag.y = y;
    const gx = clamp(x - 110, -110, innerWidth - 100), gy = y - 70;
    $("drag-ghost").style.transform = `translate3d(${gx}px,${gy}px,0)`;
    const cap = $("drag-caption");
    cap.textContent = view === "cards" ? "拖到胶囊，保持按住" : dropWorld ? "松手，加入这本世界书" : "选择一本世界书，松手加入";
    cap.style.left = `${clamp(x - 80, 12, innerWidth - 215)}px`; cap.style.top = `${clamp(y + 90, 12, innerHeight - 43)}px`;
    const r = $("collection-switch").getBoundingClientRect();
    const overSwitch = x >= r.left - 8 && x <= r.right + 8 && y >= r.top - 8 && y <= r.bottom + 8;
    if (view === "cards" && overSwitch && !switchTimer) {
      $("collection-switch").classList.add("drag-over");
      switchTimer = setTimeout(() => { if (drag) { setView("worlds", true); clearSwitch(); updateDrag(drag.x, drag.y); } }, 550);
    } else if (!overSwitch || view !== "cards") clearSwitch();
    let target = null;
    if (view === "worlds") {
      try {
        const frameRect = nativeFrame.getBoundingClientRect();
        target = nativeFrame.contentDocument?.elementFromPoint(x - frameRect.left, y - frameRect.top)?.closest("[data-preview-world]");
      } catch { /* Use the served local preview for cross-page pointer hit testing. */ }
    }
    dropWorld = target?.dataset.previewWorld || null;
    nativeFrame.contentWindow?.postMessage({source:"dreamtalk-card-preview",type:"highlight",id:dropWorld}, "*");
  }
  function finishDrag(cancelled = false) {
    if (!drag) return;
    const c = drag.card, w = dropWorld;
    drag = null; dropWorld = null; clearSwitch();
    app.classList.remove("is-dragging"); $("drag-ghost").hidden = true; $("drag-caption").hidden = true;
    nodes.worlds.forEach(n => n.el.classList.remove("drop-target"));
    nativeFrame.contentWindow?.postMessage({source:"dreamtalk-card-preview",type:"highlight",id:null}, "*");
    selectedCard = null; updateInfo(); draw(); wakeFloat();
    if (w && !cancelled) openAdd(c.id, w);
    else toast("已放回卡库，没有添加角色。");
  }
  stage.addEventListener("pointerdown", event => {
    if (event.button !== 0) return;
    if (cancelledPointer) { cancelledPointer = false; suppressClick = false; }
    const object = event.target.closest(".card-object,.world-object"), layer = event.target.closest(".card-layer");
    const node = object ? nodes[view].find(n => n.el === object) : null;
    animations[view]++;
    gesture = {id:event.pointerId, x:event.clientX, y:event.clientY, offset:offsets[view], node, moved:false, mode:"pan", yaw, pitch};
    if (draft && layer && object?.classList.contains("selected")) {
      const current = draft[designFace].layers.find(l => l.id === layer.dataset.layer);
      activeLayer = current.id; gesture.mode = "layer"; gesture.layer = current; gesture.lx = current.x; gesture.ly = current.y;
      gesture.rect = layer.closest(".card-face").getBoundingClientRect(); renderCards(); fillLayerEditor();
    } else if (draft) { gesture = null; return; }
    else if (rotating && node?.item.id === selectedCard) gesture.mode = "rotate";
    else if (rotating) gesture.mode = "outside";
    else if (view === "cards" && node && !node.item.blank) gesture.mode = "card";
  });
  stage.addEventListener("pointermove", event => {
    if (!gesture || gesture.id !== event.pointerId) return;
    const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
    if (!gesture.moved && Math.hypot(dx, dy) > 6) {
      gesture.moved = true; suppressClick = true; stage.setPointerCapture(event.pointerId);
    }
    if (!gesture.moved) return;
    if (gesture.mode === "card") {
      if (!drag) beginDrag(data.cards.find(c => c.id === gesture.node.item.id), event.clientX, event.clientY);
      updateDrag(event.clientX, event.clientY);
    } else if (gesture.mode === "rotate") {
      yaw = gesture.yaw + dx * .65; pitch = clamp(gesture.pitch - dy * .4, -65, 65); draw();
    } else if (gesture.mode === "layer") {
      gesture.layer.x = clamp(gesture.lx + dx / gesture.rect.width * 100, 5, 95);
      gesture.layer.y = clamp(gesture.ly + dy / gesture.rect.height * 100, 5, 95); renderCards();
    } else if (gesture.mode === "pan") {
      offsets[view] = gesture.offset - dx; draw();
    }
  });
  function endGesture(event, cancelled = false) {
    if (!gesture || gesture.id !== event.pointerId) return;
    const last = gesture; gesture = null;
    if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
    if (drag) finishDrag(cancelled);
    else if (last.moved && last.mode === "pan") { selectClosest(); animateTo(Math.round(offsets[view] / step()) * step()); }
    setTimeout(() => { suppressClick = false; }, 0);
  }
  stage.addEventListener("pointerup", e => endGesture(e));
  stage.addEventListener("pointercancel", e => endGesture(e, true));
  stage.addEventListener("lostpointercapture", () => { if (gesture) { gesture = null; if (drag) finishDrag(true); } });
  stage.addEventListener("click", event => {
    if (suppressClick || draft || drag) return;
    const el = event.target.closest(".card-object,.world-object");
    if (!el) { if (rotating) returnCard(); return; }
    if (rotating) return;
    const node = nodes[view].find(n => n.el === el);
    if (view === "cards") selectCard(node);
    else if (node.item.blank) create("worlds");
    else { animateTo(offsets.worlds + node.dx); showWorld(node.item.id); }
  });
  stage.addEventListener("wheel", event => {
    if (draft || rotating || drag) return;
    event.preventDefault(); animations[view]++;
    offsets[view] += Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY * .7;
    draw(); clearTimeout(stage.wheelTimer);
    stage.wheelTimer = setTimeout(() => { selectClosest(); animateTo(Math.round(offsets[view] / step()) * step()); }, 160);
  }, {passive:false});
  $("previous").onclick = () => change(-1); $("next").onclick = () => change(1);
  $("world-tab").onclick = () => setView("worlds"); $("card-tab").onclick = () => setView("cards");
  $("collection-switch").addEventListener("keydown", event => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); const next = event.key === "ArrowLeft" ? "worlds" : "cards"; setView(next); $(next === "worlds" ? "world-tab" : "card-tab").focus(); }
  });
  $("close-world").onclick = () => { selectedWorld = null; $("world-detail").hidden = true; draw(); };
  $("add-button").onclick = () => openAdd(selectedCard);
  $("rotation-done").onclick = returnCard;
  $("turn-front").onclick = () => { yaw = Math.round(yaw / 360) * 360; pitch = 0; draw(); };
  $("turn-back").onclick = () => { yaw = Math.round((yaw - 180) / 360) * 360 + 180; pitch = 0; draw(); };

  function fillDesigner() {
    const f = draft[designFace];
    $("edit-name").value = draft.name; $("edit-role").value = draft.role;
    $("edit-material").value = f.material; $("edit-frame").checked = f.frame;
    $("design-front").setAttribute("aria-pressed", String(designFace === "front")); $("design-back").setAttribute("aria-pressed", String(designFace === "back"));
    $("swatches").innerHTML = themes.map(t => `<button type="button" aria-label="${t.name}" aria-pressed="${t.color === f.color}" data-theme="${t.name}" style="--swatch:${t.color}"></button>`).join("");
    $("image-controls").hidden = !f.image; $("image-opacity").value = f.imageOpacity;
    $("undo-symmetry").hidden = !symmetryUndo;
    fillLayerEditor();
  }
  function fillLayerEditor() {
    const l = draft?.[designFace].layers.find(item => item.id === activeLayer);
    $("layer-editor").hidden = !l;
    if (!l) return;
    $("layer-text-label").hidden = l.kind === "sticker";
    $("layer-text").value = l.text; $("layer-size").value = l.size; $("layer-rotation").value = l.rotation;
    $("layer-opacity").value = l.opacity; $("layer-color").value = l.color;
  }
  $("design-button").onclick = () => {
    draft = structuredClone(data.cards.find(c => c.id === selectedCard)); designFace = "front"; activeLayer = null; symmetryUndo = null;
    rotating = true; yaw = 0; pitch = 0; app.classList.add("design-open"); $("designer").hidden = false;
    fillDesigner(); updateInfo(); renderCards();
  };
  function endDesign(save) {
    if (!draft) return;
    if (save) { const index = data.cards.findIndex(c => c.id === selectedCard); data.cards[index] = draft; }
    draft = null; activeLayer = null; $("designer").hidden = true; app.classList.remove("design-open");
    renderCards(); updateInfo(); toast(save ? "卡面设计已保存到这次预览。" : "已取消，保留原来的卡面。");
  }
  $("cancel-design").onclick = $("revert-design").onclick = () => endDesign(false);
  $("save-design").onclick = () => { if (!draft.name.trim()) { toast("请填写角色名称。"); $("edit-name").focus(); return; } endDesign(true); };
  function chooseFace(side) { designFace = side; activeLayer = null; yaw = side === "front" ? 0 : 180; pitch = 0; fillDesigner(); renderCards(); }
  $("design-front").onclick = () => chooseFace("front"); $("design-back").onclick = () => chooseFace("back");
  $("apply-symmetry").onclick = () => {
    symmetryUndo = structuredClone(draft.back);
    draft.back = structuredClone(draft.front);
    draft.back.layers.forEach(l => { l.id = `layer-${serial++}`; });
    activeLayer = null; fillDesigner(); renderCards(); toast("正面设计已应用到背面，两面仍可独立修改。");
  };
  $("undo-symmetry").onclick = () => {
    if (!symmetryUndo) return;
    draft.back = symmetryUndo; symmetryUndo = null; activeLayer = null;
    fillDesigner(); renderCards(); toast("已恢复对称操作前的背面设计。");
  };
  $("edit-name").oninput = event => { draft.name = event.target.value; const l = draft.front.layers.find(l => l.kind === "name"); if (l) l.text = draft.name; renderCards(); updateInfo(); };
  $("edit-role").oninput = event => { draft.role = event.target.value; const l = draft.front.layers.find(l => l.kind === "role"); if (l) l.text = draft.role; renderCards(); updateInfo(); };
  $("swatches").onclick = event => {
    const theme = themes.find(t => t.name === event.target.closest("button")?.dataset.theme); if (!theme) return;
    Object.assign(draft[designFace], theme);
    draft[designFace].layers.filter(l => ["name","role"].includes(l.kind)).forEach(l => { l.color = theme.accent; });
    fillDesigner(); renderCards();
  };
  $("edit-material").onchange = e => { draft[designFace].material = e.target.value; renderCards(); };
  $("edit-frame").onchange = e => { draft[designFace].frame = e.target.checked; renderCards(); };
  $("upload-image").onchange = event => {
    const file = event.target.files[0], snapshot = draft, side = designFace;
    if (!file) return;
    if (!["image/png","image/jpeg","image/webp"].includes(file.type) || file.size > 10 * 1024 * 1024) { toast("请选择不超过10 MB的PNG、JPG或WebP图片。"); event.target.value = ""; return; }
    const reader = new FileReader();
    reader.onload = () => { if (draft === snapshot) openCrop(side, reader.result); };
    reader.onerror = () => toast("没有读到这张图片，请重新选择。"); reader.readAsDataURL(file); event.target.value = "";
  };
  $("image-opacity").oninput = e => { draft[designFace].imageOpacity = Number(e.target.value); renderCards(); };
  $("recrop-image").onclick = () => { const f = draft[designFace]; openCrop(designFace, f.sourceImage || f.image, f.imageCrop); };
  $("remove-image").onclick = () => { Object.assign(draft[designFace], {image:null,sourceImage:null,imageCrop:null}); fillDesigner(); renderCards(); };
  const cropFrame = $("crop-frame");
  function sendCropSession() {
    if (!cropSession) return;
    cropFrame.contentWindow?.postMessage({source:"dreamtalk-crop-host",type:"open",id:cropSession.id,image:cropSession.image,initial:cropSession.initial}, "*");
  }
  function openCrop(side, image, initial = null) {
    if (!draft || !image) return;
    cropSession = {id:`crop-${++cropSequence}`,owner:draft,side,image,initial};
    $("crop-title").textContent = `裁剪${side === "front" ? "正面" : "背面"}图片`;
    $("crop-error").hidden = true; $("crop-apply").disabled = true; $("crop-apply").textContent = "应用到卡面";
    $("crop-dialog").showModal(); sendCropSession();
  }
  cropFrame.addEventListener("load", sendCropSession);
  $("crop-apply").onclick = () => {
    if (!cropSession) return;
    $("crop-apply").disabled = true; $("crop-apply").textContent = "正在处理…";
    cropSession.busy = true;
    cropFrame.contentWindow?.postMessage({source:"dreamtalk-crop-host",type:"apply",id:cropSession.id}, "*");
  };
  $("crop-dialog").addEventListener("close", () => { cropSession = null; });
  window.addEventListener("message", event => {
    if (event.source !== cropFrame.contentWindow || event.data?.source !== "dreamtalk-crop-editor") return;
    const message = event.data;
    if (message.type === "ready") { sendCropSession(); return; }
    if (!cropSession || message.id !== cropSession.id) return;
    if (message.type === "cancel") { $("crop-dialog").close(); return; }
    if (message.type === "area") { if (!cropSession.busy) $("crop-apply").disabled = false; return; }
    if (message.type === "error") {
      cropSession.busy = false;
      $("crop-error").textContent = message.text; $("crop-error").hidden = false;
      $("crop-apply").disabled = false; $("crop-apply").textContent = "应用到卡面"; return;
    }
    if (message.type === "result" && cropSession.owner === draft && typeof message.image === "string" && message.image.startsWith("data:image/png")) {
      Object.assign(draft[cropSession.side], {image:message.image,sourceImage:cropSession.image,imageCrop:message.crop});
      $("crop-dialog").close(); fillDesigner(); renderCards(); toast("裁剪已应用到当前卡面，原图已保留。");
    }
  });
  $("sticker-palette").innerHTML = Object.entries(stickerNames).map(([glyph, name]) => `<button type="button" aria-label="添加${name}贴纸" data-sticker="${glyph}">${glyph}</button>`).join("");
  function addLayer(kind, text) {
    const layers = draft[designFace].layers;
    if (layers.length >= 24) return toast("这一面已有24个组件，请先整理后再添加。");
    const l = {id:`layer-${serial++}`, kind, text, x:60, y:40, size:kind === "sticker" ? 38 : 18, rotation:0, opacity:100, color:draft[designFace].accent};
    layers.push(l); activeLayer = l.id; fillLayerEditor(); renderCards();
  }
  $("sticker-palette").onclick = event => { const glyph = event.target.closest("button")?.dataset.sticker; if (glyph) addLayer("sticker", glyph); };
  $("add-text").onclick = () => { addLayer("text", "写下自己的故事"); $("layer-editor").scrollIntoView({block:"nearest"}); $("layer-text").focus(); };
  for (const [id, key, numeric] of [["layer-text","text",false],["layer-size","size",true],["layer-rotation","rotation",true],["layer-opacity","opacity",true],["layer-color","color",false]]) {
    $(id).oninput = event => { const l = draft?.[designFace].layers.find(l => l.id === activeLayer); if (l) { l[key] = numeric ? Number(event.target.value) : event.target.value; renderCards(); } };
  }
  $("delete-layer").onclick = () => { draft[designFace].layers = draft[designFace].layers.filter(l => l.id !== activeLayer); activeLayer = null; fillLayerEditor(); renderCards(); };

  function create(which) {
    createType = which; $("create-title").textContent = which === "cards" ? "一张新的角色卡" : "一本新的世界书";
    $("create-description").textContent = which === "cards" ? "写下名字，把新的相遇放进卡库。" : "为一个新的故事，留下一本空白的书。";
    $("create-role-label").hidden = which !== "cards";
    $("create-name").placeholder = which === "cards" ? "为角色取个名字" : "为世界取个名字";
    $("create-form").reset(); $("create-dialog").showModal();
  }
  $("create-form").onsubmit = event => {
    event.preventDefault(); const name = $("create-name").value.trim(); if (!name) return;
    const id = `${createType === "cards" ? "c" : "w"}-${serial++}`;
    if (createType === "cards") {
      data.cards.push(card(id, name, $("create-role").value.trim(), themes[data.cards.length % themes.length], Array.from(name)[0]));
      selectedCard = id; rotating = true; yaw = 0; pitch = 0; rebuild("cards"); offsets.cards = (data.cards.length - 1) * step("cards");
    } else {
      data.worlds.push({id,name,color:themes[data.worlds.length % themes.length].color,glyph:"✧",locations:["起始地点"],members:[]});
      rebuild("worlds"); offsets.worlds = (data.worlds.length - 1) * step("worlds");
    }
    $("create-dialog").close(); updateInfo(); draw(); toast(`「${name}」已加入${createType === "cards" ? "卡库" : "书架"}。`);
  };
  $("map-button").onclick = () => {
    const world = data.worlds.find(w => w.id === selectedWorld);
    $("map-title").textContent = `${world.name} · 地点图`;
    const present = world.members.filter(m => m.location !== null);
    const root = $("map-content");
    root.innerHTML = present.length ? `<div class="map-grid">${world.locations.filter(loc => present.some(m => m.location === loc)).map(loc => `<div class="map-place"><strong>${escape(loc)}</strong>${present.filter(m => m.location === loc).map(m => `<span>${escape(m.name)}</span>`).join("")}</div>`).join("")}</div>` : `<div class="map-empty"><b>⌁</b>暂无位于地点中的角色</div>`;
    const absent = world.members.filter(m => m.location === null).length;
    if (absent) { const note = document.createElement("p"); note.className = "map-footnote"; note.textContent = `${absent} 位角色的地点为“无”，未显示在图中，也不能移动。`; root.append(note); }
    $("map-dialog").showModal();
  };
  $("guide-button").onclick = () => $("guide-dialog").showModal();
  document.querySelectorAll("[data-close]").forEach(button => { button.onclick = () => $(button.dataset.close).close(); });
  document.querySelectorAll("dialog").forEach(dialog => { dialog.addEventListener("click", e => { if (e.target === dialog) { const r = dialog.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close(); } }); });
  document.addEventListener("keydown", event => {
    if (document.querySelector("dialog[open]") || event.target.matches("input,select,textarea")) return;
    if (event.key === "Escape") {
      if (drag) {
        const pointer = gesture?.id; gesture = null; finishDrag(true); cancelledPointer = true;
        if (pointer !== undefined && stage.hasPointerCapture(pointer)) stage.releasePointerCapture(pointer);
      }
      else if (draft) endDesign(false);
      else if (rotating) returnCard();
      else { selectedWorld = null; $("world-detail").hidden = true; draw(); }
    } else if (["ArrowLeft","ArrowRight"].includes(event.key) && !draft) {
      event.preventDefault();
      if (rotating) { yaw += event.key === "ArrowLeft" ? -15 : 15; draw(); }
      else change(event.key === "ArrowLeft" ? -1 : 1);
    }
  });
  $("reset-button").onclick = () => {
    if (drag) finishDrag(true);
    if (draft) endDesign(false);
    document.querySelectorAll("dialog[open]").forEach(d => d.close());
    data = initialData(); selectedCard = null; selectedWorld = null; offsets.worlds = 2.5 * step("worlds"); offsets.cards = 0;
    rebuild("worlds"); rebuild("cards"); setView("worlds"); toast("演示已重置。");
  };
  let lastSteps = {worlds:step("worlds"), cards:410 + 75};
  new ResizeObserver(() => {
    for (const which of ["worlds","cards"]) { const next = step(which); offsets[which] = offsets[which] / lastSteps[which] * next; lastSteps[which] = next; }
    draw();
  }).observe(stage);
  rebuild("worlds"); rebuild("cards"); setView("worlds");
  document.addEventListener("visibilitychange", wakeFloat);
  document.addEventListener("pointerup", () => {
    if (cancelledPointer) { cancelledPointer = false; setTimeout(() => { suppressClick = false; }, 0); }
  }, true);
  reducedMotion.addEventListener("change", wakeFloat);
})();
