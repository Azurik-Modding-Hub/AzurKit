// The tracker's maps (Step 4.2c3): Modkit's map view (gui/rando_view.py's MapView, R1.41 and R1.43) on a canvas, over
// Modkit's pictures, shipped with the page (web/art.mjs, Step 4.3f). The world map shows every level's main floor on
// its grid, a line for each pair of levels an exit joins (coloured by what it needs, dashed one way) and, for each
// level reached now, a badge counting its spots reachable now (amber when only a skip reaches them); a click on a
// level shows its map. A level's map shows a floor (its floor buttons pick another), its features (save points, key
// locks, disc seals, teleporter pads), barriers, tracked spots and exits at their vanilla places, each spot ringed
// green while reachable now, amber while only a skip reaches it, grey otherwise, its item once collected or with
// Spoiler, a check once collected (blue: Live marked it); a click marks a spot, or opens an exit's level. The wheel
// zooms about the pointer, a drag pans a zoomed map, a double click (or Fit) shows it whole, and the map fills its
// room as the window resizes. With Gems (R1.43) each gem spot not all taken is a tiny dot in its gem's colour,
// gone once Live sees it taken, with the gems taken and left under the title and on the floor buttons. With Live,
// a you-are-here dot (the world map's ring round the player's level); Find me shows it, a zoomed map centred on them,
// and Follow shows the floor they stand on (floors.json's table, Step 4.3's floors) as it changes.
// Zoomed past its own pixels, a coarse level's map shows its floor's detail picture (Step 4.3l, Modkit's R1.41: the
// floor drawn again finer, shipped with the page), read when the zoom comes within a notch of needing it.
// Every verdict is the engine's (sdk.tracker's view): this draws what it says (marks(), the tests' too). Before a plan
// is tracked (no view) the world map shows its picture and the levels' names alone.
const DARK = "#1b1f24";
// Modkit's TRACK: reachable now, only by a skip (R1.41's amber), not yet, a live mark or the player
export const TRACK = { near: "#3fb950", skip: "#ff8800", far: "#6e7681", live: "#58a6ff" };
const GEMS = { emerald: "#3fd17a", diamond: "#e6edf3", ruby: "#ff5c5c", sapphire: "#5b8cff" };
const NOTHING = "#c9d1d9";
const SPOT = { major: "Item spot", obsidian: "Obsidian spot", consumable: "Fuel or health spot" };
const STATE = { got: "collected", live: "collected (live)", skip: "reachable now with a skip", near: "reachable now",
                far: "not reachable yet" };
const BADGE_AT = [[8, 8], [-8, 8], [8, -8], [-8, -8]];
const STEP = 1.25, METRE_PX = 8, DRAG_PX = 4, MARGIN = 40, MIN_ROOM = 320;
// Follow's floor (Step 4.3's floors): ground this near the feet is what they stand on; at a seam the floor they were
// on holds while its ground lies this near
const FOOT_M = 1.5, HOLD_M = 2;
const KINDS = { level: [["conn", "Connections"], ["item", "Items"], ["barrier", "Barriers"], ["feature", "Features"]],
                world: [["conn", "Connections"], ["spot", "Spots"]] };
const NEED_ORDER = ["nothing", "keys", "fragments", "event", "air", "water", "fire", "earth", "ice block",
                    "acid block", "smash wall", "crystal", "powers", "unreachable"];

// An item's icon (Modkit's item_icon): a key its own model's where the icons hold one, else the life key's
const ICONS = [["key_", "key_life1"], ["all_fuel", "fuel"], ["all_health", "health"], ["obsidian", "obsidian"]];
export function itemIcon(item, have = () => false) {
  if (item.startsWith("key_")) return have(item) ? item : "key_life1";
  const found = ICONS.find(([p]) => item.startsWith(p));
  if (found) return found[1];
  if (/^frag_[a-z]+_\d$/.test(item)) return item.replace(/_\d$/, "");
  if (["diamond", "emerald", "ruby", "sapphire"].includes(item)) return `gem_${item}`;
  return item === "power_water_a3" ? "power_water" : item;
}
const gemName = (item) => item.charAt(0).toUpperCase() + item.slice(1).replace(/_/g, " ");

// What a level's map draws of the tracker's view (Modkit's track() and gem_dots()): each tracked spot of the level
// (sorted) with its ring (skip, near or far), whether it is reachable now (a thick ring), the icon it shows (its
// item, once collected or with Spoiler; else none: a dot), faint (out of reach and not collected), and its check
// (got, live or none); with Gems each gem spot not all taken (its colour's gem, a cluster's dot larger). The tests
// hold these to Modkit's map verdicts.
export function marks(view, level, have = () => false) {
  const spots = Object.entries(view.spots).filter(([, s]) => s.level === level).sort(([a], [b]) => a < b ? -1 : 1)
    .map(([loc, s]) => {
      const got = s.state === "got" || s.state === "live", near = s.state === "near" || s.state === "skip";
      return { loc, ring: s.state === "skip" ? "skip" : near ? "near" : "far", near,
               icon: s.item ? itemIcon(s.item, have) : null, faint: !(got || near), check: got ? s.state : null };
    });
  const gems = Object.entries(view.gems?.spots ?? {}).filter(([, g]) => g.level === level && g.taken < g.full)
    .sort(([a], [b]) => a < b ? -1 : 1).map(([loc, g]) => ({ loc, item: g.item, full: g.full, taken: g.taken }));
  return { spots, gems };
}

// What the world map's badges say (Modkit's _draw_world): each level reached now, its spots reachable now and how many
// only with a skip, and its collected.
export function badges(view) {
  const out = {};
  for (const level of view.status.levels) {
    const mine = Object.values(view.spots).filter((s) => s.level === level);
    out[level] = { n: mine.filter((s) => s.state === "near" || s.state === "skip").length,
                   k: mine.filter((s) => s.state === "skip").length,
                   got: mine.filter((s) => s.state === "got" || s.state === "live").length };
  }
  return out;
}

// The floor under a point of a level (floors.json's table, art.mjs's decodeFloors) at its pixel (px, py) and height
// z: the floor all the pixel's storeys are on, else that of the storey nearest z within FOOT_M m (the higher on a
// tie); null where none is (no ground there, or the point in the air).
export function floorAt(t, px, py, z) {
  const x = Math.floor(px), y = Math.floor(py);
  if (!t || x < 0 || y < 0 || x >= t.w || y >= t.h) return null;
  const p = y * t.w + x, c = t.code[p];
  if (c !== 255) return c ? c - 1 : null;
  let best = -1, gap = Infinity;
  for (let i = t.first[p]; i < t.first[p] + t.count[p]; i++) {
    const g = Math.max(t.lo[i] - z, z - t.hi[i], 0);
    if (g <= FOOT_M && (g < gap || (g === gap && t.lo[i] > t.lo[best]))) [best, gap] = [i, g];
  }
  return best < 0 ? null : t.floor[best];
}

// The floor the player is on, from the one they were on (held): floorAt's, but held at a seam while held's ground
// lies within HOLD_M m round them (s: the map's px a metre), and held where floorAt finds none.
export function floorUnder(t, px, py, z, held, s) {
  const here = floorAt(t, px, py, z);
  if (here === null || here === held || held === null || held === undefined) return here ?? held ?? null;
  const r = Math.max(1, Math.ceil(HOLD_M * s));
  for (let dy = -r; dy <= r; dy++) {
    for (let dx = -r; dx <= r; dx++) {
      if (dx * dx + dy * dy > r * r) continue;
      const x = Math.floor(px) + dx, y = Math.floor(py) + dy;
      if (x < 0 || y < 0 || x >= t.w || y >= t.h) continue;
      const p = y * t.w + x, c = t.code[p];
      if (c === held + 1) return held;
      if (c !== 255) continue;
      for (let i = t.first[p]; i < t.first[p] + t.count[p]; i++) {
        if (t.floor[i] === held && Math.max(t.lo[i] - z, z - t.hi[i], 0) <= FOOT_M) return held;
      }
    }
  }
  return here;
}

export class MapView {
  // els: {side, room, canvas, back, fit, switches, floors, key, note, hint, tip}; hooks: {view(), art, spoiler(),
  // gems(), toggle(loc), navigated(level, byHand), following(): Follow is on}
  constructor(els, hooks) {
    Object.assign(this, { els, hooks, level: null, floor: 0, size: null, s: 1, fitted: 1, o: [0, 0], want: 1,
                          shown: {}, hits: [], press: null, clicked: undefined, here: null, drawnFor: null,
                          detail: null });
    this.ctx = els.canvas.getContext("2d");
    const c = els.canvas;
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = c.getBoundingClientRect();
      const notches = Math.max(-3, Math.min(3, -e.deltaY / (e.deltaMode ? 3 : 100)));
      this.zoom(notches, [e.clientX - r.left, e.clientY - r.top]);
    }, { passive: false });
    c.addEventListener("pointerdown", (e) => {
      const r = c.getBoundingClientRect();
      this.press = [e.clientX - r.left, e.clientY - r.top, false];
      this.tip(null);
    });
    c.addEventListener("pointermove", (e) => {
      const r = c.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
      if (!this.press) return this.tip([x, y]);
      this.dragged(x, y);
    });
    c.addEventListener("pointerleave", () => this.tip(null));
    c.addEventListener("pointerup", (e) => {
      const r = c.getBoundingClientRect(), press = this.press;
      this.press = null;
      if (!press) return;
      if (press[2]) this.clicked = true;
      else this.clicked = this.click([e.clientX - r.left, e.clientY - r.top]);
    });
    c.addEventListener("dblclick", () => {
      if (this.clicked === null) this.fitWhole();
    });
    els.back.addEventListener("click", () => this.show(null, true));
    els.fit.addEventListener("click", () => this.fitWhole());
    new ResizeObserver(() => this.resized()).observe(els.room);
    addEventListener("resize", () => {   // (a headless browser may never deliver the observer's)
      this.fill();
      this.resized();
    });
  }

  // ---- what is shown
  index() {
    return this.hooks.art.status.index;
  }

  entry(level) {
    return this.index()?.levels[level] ?? this.hooks.art.status.levels[level] ?? null;
  }

  ready(level) {
    return level === null ? Boolean(this.index()) : Boolean(this.entry(level));
  }

  // The world map (null) or a level's, on its main floor, whole; byHand: the player's click (Follow ends when it
  // leaves Follow's level).
  show(level, byHand = false) {
    this.level = level;
    this.detail = null;   // its detail picture, {name, bitmap, error} (the shown floor's, or another's: one held)
    this.hooks.art.drop();
    if (!this.ready(level)) {   // not drawn yet: the tracker shows its grid or chips
      this.pictures = [];
      return this.hooks.navigated(level, byHand);
    }
    const e = level === null ? null : this.entry(level);
    this.floor = e ? e.main : 0;
    this.onFloor = null;   // the floor Follow last found the player on
    const pictures = this.pictures = (e ? e.floors : ["world"]).map((name) => ({ name, bitmap: null }));
    for (const p of pictures) {
      this.hooks.art.bitmap(p.name).then((b) => {
        p.bitmap = b;
        if (this.pictures !== pictures) return;
        if (level === null && this.want <= this.fitted * 1.0001) this.fitWhole(false);   // its size is the bitmap's
        this.draw();
      });
    }
    this.switches();
    this.fitWhole(false);
    this.hooks.navigated(level, byHand);
    this.draw();
  }

  pictureSize() {
    if (this.level !== null) return this.entry(this.level)?.size ?? null;
    const b = this.pictures?.[0]?.bitmap;
    return b ? [b.width, b.height] : null;
  }

  // The column's switches: the overlay boxes and a level's floors (with Gems, each floor's gems left).
  switches() {
    const { switches, back } = this.els;
    back.disabled = this.level === null;
    switches.replaceChildren(...KINDS[this.level === null ? "world" : "level"].map(([kind, text]) => {
      this.shown[kind] ??= true;
      const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: this.shown[kind] });
      box.dataset.kind = kind;
      box.addEventListener("change", () => {
        this.shown[kind] = box.checked;
        this.draw();
      });
      const label = Object.assign(document.createElement("label"), { className: "on" });
      label.append(box, ` ${text}`);
      return label;
    }));
    this.floorButtons();
  }

  // What a click does, set at each draw: a level opens from the world map only once a seed is tracked (its view).
  hint() {
    const text = (this.level !== null ? "Click a spot to mark it collected, an exit to open its level."
      : this.hooks.view() ? "Click a level to open its map." : "Track a seed to open a level's map.")
      + " Scroll to zoom, drag to pan.";
    if (this.els.hint.textContent !== text) this.els.hint.textContent = text;
  }

  floorButtons() {
    const { floors } = this.els, e = this.level === null ? null : this.entry(this.level);
    if (!e || e.floors.length < 2) return floors.replaceChildren();
    const left = new Array(e.floors.length).fill(0), gems = this.hooks.gems() && this.hooks.view()?.gems;
    if (gems) {
      for (const g of e.gems ?? []) {
        const s = gems.spots[g.id];
        if (s) left[g.at[2]] += s.full - s.taken;
      }
    }
    floors.classList.toggle("gems", Boolean(gems));
    floors.replaceChildren(Object.assign(document.createElement("span"), { className: "note", textContent: "Floor" }),
      ...e.floors.map((_, k) => {
        const radio = Object.assign(document.createElement("input"), { type: "radio", name: "track-floor",
                                                                      checked: k === this.floor });
        radio.dataset.floor = String(k);
        radio.addEventListener("change", () => {
          this.floor = k;
          this.draw();
        });
        const label = Object.assign(document.createElement("label"), { className: "on" });
        label.append(radio, ` ${gems ? `${k + 1} · ${left[k]}` : k + 1}`);
        return label;
      }));
  }

  // ---- the view: a picture's pixel u shows at canvas u * s - o (plus a margin centring a map smaller than its room)
  room() {
    const { clientWidth: w, clientHeight: h } = this.els.room;
    return [Math.max(w, 1), Math.max(h, 1)];
  }

  // The map's room fills what the tab shows below it (at least MIN_ROOM px high), so the whole map is in view.
  fill() {
    const room = this.els.room, section = room.closest("section");
    if (!section || room.offsetParent === null) return;
    const want = `${Math.max(MIN_ROOM, Math.floor(section.getBoundingClientRect().bottom
      - room.getBoundingClientRect().top - 10))}px`;
    if (room.style.height !== want) room.style.height = want;
  }

  margin() {
    const size = this.pictureSize(), [cw, ch] = this.room();
    return size ? [Math.max(0, (cw - size[0] * this.s) / 2), Math.max(0, (ch - size[1] * this.s) / 2)] : [0, 0];
  }

  at(x, y) {
    const [mx, my] = this.margin();
    return [x * this.s - this.o[0] + mx, y * this.s - this.o[1] + my];
  }

  fitWhole(redraw = true) {
    const size = this.pictureSize(), [cw, ch] = this.room();
    this.fitted = size ? Math.min(cw / size[0], ch / size[1]) : 1;
    this.s = this.want = this.fitted;
    this.o = [0, 0];
    this.els.fit.disabled = true;
    if (redraw) this.draw();
  }

  top() {
    const s = 4 * this.fitted;
    return this.level === null ? s : Math.max(s, METRE_PX / this.entry(this.level).frame[2]);
  }

  zoom(notches, at = null) {
    if (!this.pictureSize() || !notches) return;
    this.view(Math.min(Math.max(this.want * STEP ** notches, this.fitted), this.top()), at);
  }

  view(want, at = null) {
    if (want <= this.fitted * 1.0001) return this.fitWhole();
    const [cw, ch] = this.room(), [cx, cy] = at ?? [cw / 2, ch / 2];
    const [mx, my] = this.margin();
    const u = [(cx - mx + this.o[0]) / this.s, (cy - my + this.o[1]) / this.s];   // the picture's pixel there
    this.s = this.want = want;
    const [nx, ny] = this.margin();
    this.move(u[0] * this.s - (cx - nx), u[1] * this.s - (cy - ny));
    this.els.fit.disabled = false;
    this.draw();
  }

  move(ox, oy) {
    const [w, h] = this.pictureSize(), [cw, ch] = this.room();
    const next = [Math.min(Math.max(ox, 0), Math.max(w * this.s - cw, 0)),
                  Math.min(Math.max(oy, 0), Math.max(h * this.s - ch, 0))];
    const moved = [this.o[0] - next[0], this.o[1] - next[1]];
    this.o = next;
    return moved;
  }

  dragged(x, y) {
    if (!this.press || this.s <= this.fitted * 1.0001) return;
    const [x0, y0, dragging] = this.press;
    if (!dragging && Math.abs(x - x0) + Math.abs(y - y0) < DRAG_PX) return;
    this.move(this.o[0] - (x - x0), this.o[1] - (y - y0));
    this.press = [x, y, true];
    this.draw();
  }

  resized() {
    if (!this.pictureSize() || this.els.room.offsetParent === null) return;
    const zoomed = this.want > this.fitted * 1.0001;
    const size = this.pictureSize(), [cw, ch] = this.room();
    this.fitted = Math.min(cw / size[0], ch / size[1]);
    if (!zoomed) return this.fitWhole();
    this.view(Math.max(this.want, this.fitted));
  }

  // Keep the picture's pixel (x, y) in view (Follow): a zoomed map it lies off, or near the edge of, moves to centre
  // it (centre, Find me: wherever it lies).
  see(x, y, centre = false) {
    if (!this.pictureSize() || this.want <= this.fitted * 1.0001 || this.press?.[2]) return;
    const [cx, cy] = this.at(x, y), [cw, ch] = this.room();
    if (!centre && MARGIN <= cx && cx <= cw - MARGIN && MARGIN <= cy && cy <= ch - MARGIN) return;
    this.move(x * this.s - cw / 2, y * this.s - ch / 2);
    this.draw();
  }

  // ---- drawing
  draw() {
    this.fill();
    this.hint();
    if (this.want <= this.fitted * 1.0001 && this.els.room.offsetParent !== null) this.fitWhole(false);   // its room now
    const view = this.hooks.view(), c = this.els.canvas, ctx = this.ctx;
    const [cw, ch] = this.room(), ratio = window.devicePixelRatio || 1;
    if (c.width !== Math.round(cw * ratio) || c.height !== Math.round(ch * ratio)) {
      c.width = Math.round(cw * ratio);
      c.height = Math.round(ch * ratio);
      c.style.width = `${cw}px`;
      c.style.height = `${ch}px`;
    }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.fillStyle = DARK;
    ctx.fillRect(0, 0, cw, ch);
    this.hits = [];
    if (!view && (this.level !== null || !this.index())) return;
    const pic = this.pictures[this.level === null ? 0 : this.floor]?.bitmap, size = this.pictureSize();
    const detail = this.wantDetail(), finer = this.s > 1 ? detail?.bitmap : null, [x, y] = this.at(0, 0);
    ctx.imageSmoothingEnabled = false;
    if (finer) {   // a detail pixel is the map's pixel u * factor: drawn at s / factor
      const r = this.s / this.factor();
      ctx.drawImage(finer, x, y, finer.width * r, finer.height * r);
    } else if (pic && size) {
      ctx.drawImage(pic, x, y, size[0] * this.s, size[1] * this.s);
    }
    const kinds = this.level === null ? this.drawWorld(view) : this.drawLevel(view);
    this.key(kinds);
    this.drawnFor = { level: this.level, floor: this.floor, s: this.s, o: [...this.o], detail: Boolean(finer) };
    if (this.here) this.you(this.here.seen, this.here.lost);
  }

  // How many times finer than its map the shown level's detail pictures are (null: none, index.json's detail).
  factor() {
    return this.level === null ? null : this.hooks.art.status.detail?.[this.level] ?? null;
  }

  // The shown floor's detail picture once it is in (null: not yet, or none): read when the map is zoomed within a
  // notch of its own pixels (or fits past them), drawn again once it is; a floor's replaces another's.
  wantDetail() {
    if (!this.factor()) return null;
    const name = this.entry(this.level).floors[this.floor];
    if (this.detail?.name !== name && this.want * STEP > 1) {
      const held = this.detail = { name, bitmap: null, error: null };
      this.hooks.art.detail(name).then(({ bitmap, error }) => {
        Object.assign(held, { bitmap, error });
        if (this.detail === held) this.draw();
      });
    }
    return this.detail?.name === name ? this.detail : null;
  }

  on(kind) {
    return this.shown[kind] !== false;
  }

  label(x, y, text, font, box = true) {
    const ctx = this.ctx;
    ctx.font = font;
    ctx.textBaseline = "top";
    const w = ctx.measureText(text).width, h = Number(/(\d+)px/.exec(font)[1]) + 3;
    if (box) {
      ctx.fillStyle = DARK;
      ctx.fillRect(x - 1, y - 1, w + 2, h + 1);
    }
    ctx.fillStyle = "#ffffff";
    ctx.fillText(text, x, y);
    return [x, y, x + w, y + h];
  }

  halo(x, y, r, ring = "#ffffff", width = 1.5) {
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI);
    ctx.fillStyle = DARK;
    ctx.fill();
    ctx.lineWidth = width;
    ctx.strokeStyle = ring;
    ctx.stroke();
  }

  // What the pointer finds at (x, y) within r (a box: [x, y, w, h], a world map's level, under every badge).
  hit(x, y, r, tip, act = null, box = null) {
    this.hits.push({ x, y, r, tip, act, box });
  }

  // The fire barrier's flame (Modkit's GUI draws it: the barrier is particles, no model the engine can draw), a
  // 20 px orange flame on its disc.
  flame(x, y) {
    const ctx = this.ctx, g = ctx.createLinearGradient(0, y + 8, 0, y - 8);
    g.addColorStop(0, "#b23a24");
    g.addColorStop(1, "#f0a03e");
    ctx.beginPath();
    ctx.moveTo(x, y - 8);
    ctx.quadraticCurveTo(x + 7, y - 1, x + 6, y + 4);
    ctx.quadraticCurveTo(x + 4, y + 8, x, y + 8);
    ctx.quadraticCurveTo(x - 4, y + 8, x - 6, y + 4);
    ctx.quadraticCurveTo(x - 7, y - 1, x, y - 8);
    ctx.fillStyle = g;
    ctx.fill();
  }

  // An icon the engine drew (icons/<name>), centred on (x, y), read once (drawn again once it is).
  icon(x, y, name, faint = false) {
    if (name === "fire_barrier") return this.flame(x, y);
    const b = this.iconCache?.[name];
    if (b) {
      this.ctx.globalAlpha = faint ? 0.35 : 1;
      this.ctx.drawImage(b, x - b.width / 2, y - b.height / 2);
      this.ctx.globalAlpha = 1;
      return;
    }
    this.iconCache ??= {};
    if (this.iconCache[name] === undefined) {
      this.iconCache[name] = null;
      this.hooks.art.bitmap(`icons/${name}`).then((bitmap) => {
        if (!bitmap) return delete this.iconCache[name];
        this.iconCache[name] = bitmap;
        this.draw();
      });
    }
  }

  drawLevel(view) {
    const ctx = this.ctx, level = this.level, e = this.entry(level), maps = view.world.maps.levels[level];
    const here = (at) => at[2] === this.floor;
    const gemsOn = this.hooks.gems() && view.gems, held = this.hooks.art.status.icons;
    const have = (name) => Boolean(held?.includes(`icons/${name}`));
    // the title, and with Gems the level's gems taken and left and the key of the colours its dots show
    let [, , , bottom] = this.label(8, 6, level, "bold 13px system-ui, sans-serif");
    if (gemsOn) {
      const [got, total] = view.gems.counts[level] ?? [0, 0];
      [, , , bottom] = this.label(8, bottom + 2, `Gems: ${got} taken, ${total - got} left`, "10px system-ui, sans-serif");
      const left = new Set((e.gems ?? []).map((g) => view.gems.spots[g.id]).filter((s) => s && s.taken < s.full)
        .map((s) => s.item));
      let x = 8;
      for (const gem of Object.keys(GEMS).filter((g) => left.has(g))) {
        ctx.font = "9px system-ui, sans-serif";
        const w = ctx.measureText(gem).width;
        ctx.fillStyle = DARK;
        ctx.fillRect(x, bottom + 1, w + 16, 12);
        ctx.beginPath();
        ctx.arc(x + 5.5, bottom + 7, 2.5, 0, 2 * Math.PI);
        ctx.fillStyle = GEMS[gem];
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.fillText(gem, x + 11, bottom + 2);
        x += w + 18;
      }
      // the dots: under every other overlay
      for (const g of marks(view, level).gems) {
        const at = e.gems.find((p) => p.id === g.loc)?.at;
        if (!at || !here(at)) continue;
        const [x0, y0] = this.at(at[0], at[1]), r = g.full === 1 ? 2.5 : 3.5;
        ctx.beginPath();
        ctx.arc(x0, y0, r, 0, 2 * Math.PI);
        ctx.fillStyle = GEMS[g.item] ?? NOTHING;
        ctx.fill();
        ctx.lineWidth = 1;
        ctx.strokeStyle = DARK;
        ctx.stroke();
        this.hit(x0, y0, r + 1, gemName(g.item) + (g.full > 1 ? ` cluster: ${g.taken} of its ${g.full} gems taken` : ""));
      }
    }
    const rings = e.exits.flatMap((x) => x.at.filter(here).map((p) => this.at(p[0], p[1])));
    // the exits' halos under every icon and ring
    if (this.on("conn")) for (const [x, y] of rings) this.halo(x, y, 10);
    if (this.on("feature")) {
      for (const f of e.features) {
        if (!here(f.at)) continue;
        const [x, y] = this.at(f.at[0], f.at[1]), look = maps.features[f.id] ?? { letter: "?", colour: NOTHING, tip: f.kind };
        ctx.fillStyle = look.colour;
        ctx.fillRect(x - 6, y - 6, 12, 12);
        ctx.strokeStyle = DARK;
        ctx.lineWidth = 1;
        ctx.strokeRect(x - 6, y - 6, 12, 12);
        ctx.fillStyle = DARK;
        ctx.font = "bold 8px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(look.letter, x, y + 0.5);
        ctx.textAlign = "start";
        this.hit(x, y, 7, look.tip);
      }
    }
    const badgesToDraw = [];
    if (this.on("barrier")) {
      for (const b of e.barriers) {
        const look = maps.barriers[b.id];
        if (!look) continue;
        for (const at of b.at.filter(here)) {
          const [x, y] = this.at(at[0], at[1]);
          this.halo(x, y, 12);
          this.icon(x, y, look.icon);
          this.hit(x, y, 12, look.tip);
          if (look.level) {
            const [dx, dy] = BADGE_AT.find(([bx, by]) => !rings.some(([rx, ry]) => Math.abs(x + bx - rx) < 9
              && Math.abs(y + by - ry) < 9)) ?? BADGE_AT[0];
            badgesToDraw.push([x + dx, y + dy, String(look.level), look.tip]);
          }
        }
      }
    }
    // the exits: a ring in the colour of what using it needs, dashed one way; one with no place at the right edge
    const unplaced = [], kinds = [];
    const [cw] = this.room();
    e.exits.forEach((x, k) => {
      const need = maps.exits[k];
      kinds.push(need.kind);
      let at = x.at.filter(here).map((p) => [...this.at(p[0], p[1]), false]);
      if (!x.at.length) {
        unplaced.push(x.disc ? `${x.spot} fires when the ${x.disc} disc is placed` : x.spot);
        at = [[cw - 14, 40 + 22 * (unplaced.length - 1), true]];
      }
      if (!this.on("conn")) return;
      for (const [cx, cy, edge] of at) {
        if (edge) this.halo(cx, cy, 10);
        ctx.beginPath();
        ctx.arc(cx, cy, 7, 0, 2 * Math.PI);
        ctx.fillStyle = DARK;
        ctx.fill();
        ctx.setLineDash(need.dashed ? [3, 2] : []);
        ctx.lineWidth = 3;
        ctx.strokeStyle = need.colour;
        ctx.stroke();
        ctx.setLineDash([]);
        this.hit(cx, cy, 10, need.tip, () => this.show(x.to, true));
        if (edge) {
          ctx.font = "12px system-ui, sans-serif";
          const text = `${x.spot} → ${x.to}`, w = ctx.measureText(text).width;
          this.label(cx - 13 - w, cy - 7, text, "12px system-ui, sans-serif");
        }
      }
    });
    for (const [x, y, text, tip] of badgesToDraw) {
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, 2 * Math.PI);
      ctx.fillStyle = DARK;
      ctx.fill();
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 9px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(text, x, y + 0.5);
      ctx.textAlign = "start";
      this.hit(x, y, 6, tip);
    }
    // the tracked spots, over the barriers so each stays clickable
    if (this.on("item")) {
      const where = Object.fromEntries([...e.items, ...e.spots].map((i) => [i.id, i.at]));
      for (const m of marks(view, level, have).spots) {
        const at = where[m.loc];
        if (!at || !here(at)) continue;
        const [x, y] = this.at(at[0], at[1]), s = view.spots[m.loc];
        this.halo(x, y, 12, TRACK[m.ring], m.near ? 2.5 : 1.5);
        if (m.icon) {
          this.icon(x, y, m.icon, m.faint);
        } else {
          ctx.beginPath();
          ctx.arc(x, y, 4, 0, 2 * Math.PI);
          ctx.fillStyle = TRACK[m.ring];
          ctx.fill();
        }
        if (m.check) {
          ctx.font = "bold 12px system-ui, sans-serif";
          ctx.textBaseline = "middle";
          ctx.textAlign = "center";
          ctx.fillStyle = m.check === "live" ? TRACK.live : TRACK.near;
          ctx.fillText("✓", x + 9, y + 8);
          ctx.textAlign = "start";
        }
        const name = m.icon ? s.name : SPOT[s.class];
        this.hit(x, y, 12, `${name}: ${STATE[s.state]}`, () => this.hooks.toggle(m.loc));
      }
    }
    const failed = this.s > 1 && this.detail?.error ? `No detail picture for ${level}: ${this.detail.error}.` : "";
    this.els.note.textContent = [unplaced.length ? `At the right edge, with no place: ${unplaced.join("; ")}.` : "",
                                 failed].filter(Boolean).join(" ");
    return kinds;
  }

  drawWorld(view) {
    const ctx = this.ctx, index = this.index(), maps = view?.world.maps;
    const boxes = Object.fromEntries(Object.entries(index.world.levels).map(([lv, [x, y, w, h]]) =>
      [lv, [...this.at(x, y), w * this.s, h * this.s]]));
    const [, , right, below] = this.label(8, 6, index.world.title, "bold 13px system-ui, sans-serif");
    const names = {};
    for (const [lv, [x, y]] of Object.entries(boxes)) {
      names[lv] = this.label(x, x < right ? Math.max(y, below) : y, lv, "9px system-ui, sans-serif");
      this.hit(x, y, 0, null, view && (() => this.show(lv, true)), boxes[lv]);
    }
    const kinds = [];
    if (this.on("conn") && maps) {
      for (const line of maps.lines) {
        kinds.push(line.kind);
        const [ax, ay, aw, ah] = boxes[line.a], [bx, by, bw, bh] = boxes[line.b];
        ctx.beginPath();
        ctx.moveTo(ax + aw / 2, ay + ah / 2);
        ctx.lineTo(bx + bw / 2, by + bh / 2);
        ctx.setLineDash(line.dashed ? [4, 3] : []);
        ctx.strokeStyle = line.colour;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
    if (this.on("spot") && view) {
      for (const [lv, b] of Object.entries(badges(view))) {
        if (!boxes[lv]) continue;
        const [x, y, w, h] = boxes[lv], [, top, end] = names[lv];
        const by = end > x + w - 22 && top < y + 22 ? y + h - 22 : y + 2;
        ctx.beginPath();
        ctx.arc(x + w - 12, by + 10, 10, 0, 2 * Math.PI);
        ctx.fillStyle = b.n > b.k ? TRACK.near : b.k ? TRACK.skip : DARK;
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.stroke();
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 9px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(b.n), x + w - 12, by + 10.5);
        ctx.textAlign = "start";
        this.hit(x + w - 12, by + 10, 10, `${lv}: ${b.n} spots reachable now` + (b.k ? ` (${b.k} only with a skip)` : "")
          + `, ${b.got} collected`, () => this.show(lv, true));
      }
    }
    if (this.hooks.gems() && view?.gems) {
      const counts = view.gems.counts;
      const all = Object.values(counts).reduce((a, [g, t]) => [a[0] + g, a[1] + t], [0, 0]);
      this.label(right + 8, 9, `Gems: ${all[0]} taken, ${all[1] - all[0]} left`, "10px system-ui, sans-serif");
      for (const [lv, [got, total]] of Object.entries(counts)) {
        if (!boxes[lv]) continue;
        const [x, y, , h] = boxes[lv];
        ctx.font = "8px system-ui, sans-serif";
        const w = ctx.measureText(`${got}/${total}`).width;
        ctx.fillStyle = DARK;
        ctx.fillRect(x + 2, y + h - 12, w + 2, 11);
        ctx.fillStyle = got === total ? TRACK.near : "#ffffff";
        ctx.textBaseline = "bottom";
        ctx.fillText(`${got}/${total}`, x + 3, y + h - 2);
        this.hit(x + 3 + w / 2, y + h - 7, 6, `${lv}: ${got} gems taken, ${total - got} left`);
      }
    }
    this.els.note.textContent = "";
    return kinds;
  }

  // The key: the spots' states first (a level's rings, the world's badges), then each colour drawn, two to a row.
  key(kinds) {
    if (!this.hooks.view()) return this.els.key.replaceChildren();
    const rows = (this.level === null ? [["near", "reachable"], ["skip", "with a skip"]]
      : [["near", "reachable"], ["skip", "with a skip"], ["far", "not yet"]])
      .map(([state, text]) => ({ colour: TRACK[state], text, ring: this.level !== null }));
    if (rows.length % 2) rows.push(null);
    const maps = this.hooks.view().world.maps, colours = {};
    for (const x of this.level === null ? maps.lines : maps.levels[this.level].exits) colours[x.kind] = x.colour;
    const order = (k) => [NEED_ORDER.indexOf(NEED_ORDER.includes(k) ? k : "keys"), k];
    for (const kind of [...new Set(kinds)].sort((a, b) => {
      const [x, y] = [order(a), order(b)];
      return x[0] - y[0] || (x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : 0);
    })) rows.push({ colour: colours[kind], text: kind, ring: false });
    this.els.key.replaceChildren(...rows.map((row) => {
      const cell = document.createElement("span");
      if (!row) return cell;
      const dot = Object.assign(document.createElement("i"), { className: row.ring ? "ring" : "dot" });
      dot.style.setProperty("--c", row.colour);
      cell.append(dot, row.text);
      return cell;
    }));
  }

  // The live player: a level's you-are-here (a white disc, a tick the way they face; grey once Live lost xemu),
  // the world map's ring round their level and a dot where they stand. Drawn over the map at each draw.
  place(seen, lost = false) {
    this.here = seen ? { seen, lost } : null;
    this.draw();
  }

  you(seen, lost) {
    const ctx = this.ctx, index = this.index();
    if (this.level === null) {
      const box = index?.world.levels[seen.level], e = this.entry(seen.level);
      if (!box || !e) return;
      const [x, y] = this.at(box[0], box[1]), w = box[2] * this.s, h = box[3] * this.s;
      const [px, py] = [(seen.at[0] - e.frame[0]) * e.frame[2], (e.frame[1] - seen.at[1]) * e.frame[2]];
      ctx.strokeStyle = lost ? TRACK.far : TRACK.live;
      ctx.lineWidth = 2;
      ctx.strokeRect(x - 2, y - 2, w + 4, h + 4);
      ctx.beginPath();
      ctx.arc(x + px * w / e.size[0], y + py * h / e.size[1], 3, 0, 2 * Math.PI);
      ctx.fillStyle = lost ? TRACK.far : TRACK.live;
      ctx.fill();
      return;
    }
    if (seen.level !== this.level) return;
    const e = this.entry(this.level);
    const [x, y] = this.at((seen.at[0] - e.frame[0]) * e.frame[2], (e.frame[1] - seen.at[1]) * e.frame[2]);
    const yaw = seen.yaw ?? 0;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x - 9 * Math.sin(yaw), y - 9 * Math.cos(yaw));
    ctx.strokeStyle = TRACK.live;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, 2 * Math.PI);
    ctx.fillStyle = lost ? TRACK.far : "#ffffff";
    ctx.fill();
    ctx.strokeStyle = DARK;
    ctx.stroke();
    this.hit(x, y, 6, `You (height ${seen.at[2].toFixed(1)} m)`);
  }

  // Follow (Live's): the floor shown is the one under the player each time that changes (or they come into the level;
  // a floor picked by hand stays until then), and a zoomed map keeps them in view (see; centre: Find me's, centred).
  follow(seen, centre = false) {
    if (this.level === null || seen.level !== this.level || !this.entry(this.level)) return;
    const level = this.level, e = this.entry(level), [px, py] = this.pixel(seen);
    this.tables ??= new Map();
    if (!this.tables.has(level)) {   // read once; Follow goes on once it is
      this.tables.set(level, null);
      this.hooks.art.floors(level).then((t) => {
        this.tables.set(level, t);
        if (t && this.level === level && this.here && this.hooks.following()) this.follow(this.here.seen);
      });
    }
    const t = this.tables.get(level), held = this.onFloor?.level === level ? this.onFloor.floor : this.floor;
    const f = t ? floorUnder(t, px, py, seen.at[2], held, e.frame[2]) : held;
    if (this.onFloor?.level !== level || this.onFloor.floor !== f) {
      this.onFloor = { level, floor: f };
      if (f !== this.floor && f !== null && f < e.floors.length) {
        this.floor = f;
        this.floorButtons();
        this.draw();
      }
    }
    this.see(px, py, centre);
  }

  // The player's place on the shown level's picture, in its pixels.
  pixel(seen) {
    const e = this.entry(seen.level);
    return e ? [(seen.at[0] - e.frame[0]) * e.frame[2], (e.frame[1] - seen.at[1]) * e.frame[2]] : null;
  }

  // ---- the pointer
  under([x, y]) {
    return this.hits.filter((h) => h.box ? x >= h.box[0] && x < h.box[0] + h.box[2] && y >= h.box[1]
      && y < h.box[1] + h.box[3] : Math.hypot(h.x - x, h.y - y) <= h.r + 3).reverse();
  }

  click(at) {
    const hit = this.under(at).find((h) => h.act && !h.box) ?? this.under(at).find((h) => h.act);
    if (!hit) return null;
    hit.act();
    return true;
  }

  tip(at) {
    const tip = this.els.tip;
    if (!at) return (tip.hidden = true);
    const texts = [...new Set(this.under(at).map((h) => h.tip).filter(Boolean))];
    if (!texts.length) return (tip.hidden = true);
    tip.textContent = texts.join("\n");
    tip.hidden = false;
    const [cw, ch] = this.room();
    tip.style.left = `${Math.min(at[0] + 14, Math.max(4, cw - tip.offsetWidth - 6))}px`;
    tip.style.top = `${at[1] + 14 + tip.offsetHeight > ch - 6 ? Math.max(4, at[1] - tip.offsetHeight - 14) : at[1] + 14}px`;
  }
}
