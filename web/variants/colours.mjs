// The Variants view's Colours tab (Step 4.6e; Modkit's ColoursTab and its colour wheel, D772, D809 (a), Step 2.203,
// D544): the recipe's `colours`, a row's (or every row's) main colour moved on a colour wheel, its hue and saturation
// where the wheel is clicked or dragged (one `hsv` op), its value on the bar beside it, each in a box too (any finite
// number, D23) with the colour's hex; the hues it touches (Only hues, a soft edge); swaps from its palette, each to a
// colour picked on the wheel (pickColour: the wheel, a value bar and a hex box, in place of the system's picker, D809
// (a)); Reset row. The engine recolours (sdk.variant_colours): each row's tile, the row's palette before its ops and
// after them, and the body from the front and from behind, a portrait as wide as it draws; one ask at a time, the
// newest edit's asked once it answers, so a drag's last value is drawn as soon as the one before it is. Export PNGs
// writes each row's texture as its build recolours it (the app: a folder, Downloads' by default; the site: a zip,
// the browser's download); Import PNG copies an edited one into your saved variant's folder as the chosen row's `png`
// op, after a yes where the row has colour edits (an exported PNG holds them already). Undo is the view's. Text
// reaches the page through textContent only, and every colour by CSSOM (the CSP refuses style attributes).

const WHEEL = 131;   // the wheel's side, px (odd: its centre a pixel's)
const RIM = 8;   // the disc's inset from the wheel's edge: the marker's radius and half its outline, so a rim colour's is whole
const COLOURED = 0.15;   // a palette colour with a hue (saturation at least this): the wheel's
const GATE = 0.05;   // paint.GATE: a grey's saturation, which no swap can turn
const VIEW = 160;   // the engine's pictures' side, px (colour_preview.SIZE)
// The hsv op's numbers: its key, its box's label and unit, its default; the value bar's track is a hint (D23).
const HSV = [["hue", "Hue", "°", 0], ["sat", "Saturation", "×", 1], ["value", "Value", "×", 1]];
const DEFAULTS = Object.fromEntries(HSV.map(([key, , , d]) => [key, d]));
const VALUE_TRACK = [0, 3, 0.05];
const TIP = "Pick where the row's main colour (the ring) goes; the bar sets its value. Click a palette colour to swap it.";
const PNG_TIP = "Export: each row's texture as built, a PNG each. Import: an edited one becomes the chosen row's.";
const CHOOSE = "Choose your image first (1.)";   // D979's line on what waits for an image

const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
const button = (id, text, title = "") => el("button", { ...id ? { id } : {}, type: "button", textContent: text, title });
const box = (id, size = 6) => el("input", { id, type: "text", size, spellcheck: false, autocomplete: "off",
                                            inputMode: "decimal" });
const bytesOf = (data) => typeof data === "string" ? Uint8Array.from(atob(data), (ch) => ch.charCodeAt(0)) : data;
const mod = (x, n) => ((x % n) + n) % n;   // Python's %
const clip = (x, lo, hi) => Math.min(Math.max(x, lo), hi);
const fixed = (x, places) => Number(x.toFixed(places));   // Python's round(x, places), but for exact ties
const rounded = (x) => {   // Python's round(x): half to even
  const f = Math.floor(x), d = x - f;
  return d > 0.5 ? f + 1 : d < 0.5 ? f : f % 2 === 0 ? f : f + 1;
};
const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i;
const number = (text) => NUMBER.test(text.trim()) && Number.isFinite(Number(text)) ? Number(text) : null;
const reason = (why) => why.replace(/^variant '[^']*'(?: \(.*?\))?: /, "");

// The colour wheel's maths (Modkit's colour_wheel.py, the engine's paint.hsv_of and rgb_of: the hexcone's).
export const hexOf = (rgb) => `#${rgb.map((c) => rounded(c).toString(16).padStart(2, "0")).join("")}`;
export const rgbOfHex = (text) => {
  const found = /^#?([0-9a-f]{6})$/i.exec(text.trim());
  return found && [0, 2, 4].map((k) => parseInt(found[1].slice(k, k + 2), 16));
};
// rgb (0-255 each) as hue (degrees), saturation and value (0-1).
export function hsv(rgb) {
  const [r, g, b] = rgb.map((c) => c / 255), v = Math.max(r, g, b), c = v - Math.min(r, g, b);
  const h = c <= 0 ? 0 : v === r ? mod((g - b) / c, 6) : v === g ? (b - r) / c + 2 : (r - g) / c + 4;
  return [c > 0 ? h * 60 : 0, v > 0 ? c / v : 0, v];
}
const hexcone = (h, s, v) => {   // paint.rgb_of: 0-1 each
  const h6 = mod(h, 360) / 60, k = Math.floor(h6), f = h6 - k;
  const p = v * (1 - s), q = v * (1 - s * f), t = v * (1 - s * (1 - f));
  return [[v, q, p, p, t, v], [t, v, v, q, p, p], [p, p, t, v, v, q]].map((choose) => choose[mod(k, 6)]);
};
// Hue (degrees), saturation and value (each clipped to 0-1, the colour's ends) as 0-255 each.
export const rgb = (h, s, v) => hexcone(h, clip(s, 0, 1), clip(v, 0, 1)).map((c) => rounded(255 * c));

let disc = null;   // the wheel's picture, made once a page: each hue at its angle (0, red, to the right, anticlockwise)
function discImage() {   // and saturation out from the centre at value 1, its edge's pixels as covered
  if (disc) return disc;
  disc = new ImageData(WHEEL, WHEEL);
  const c = (WHEEL - 1) / 2, r = WHEEL / 2 - 1 - RIM;
  for (let y = 0; y < WHEEL; y++) {
    for (let x = 0; x < WHEEL; x++) {
      const dx = x - c, dy = c - y, d = Math.hypot(dx, dy), at = 4 * (y * WHEEL + x);
      const px = hexcone(mod(Math.atan2(dy, dx) * 180 / Math.PI, 360), clip(d / r, 0, 1), 1);
      for (let k = 0; k < 3; k++) disc.data[at + k] = rounded(255 * px[k]);
      disc.data[at + 3] = rounded(255 * clip(r + 0.5 - d, 0, 1));
    }
  }
  return disc;
}

// A hue and saturation wheel: pick(hue, sat) on a press and each move of a drag (outside the disc: its rim's). show()
// puts the picked colour's marker on it, a ring where it started and a dot for each other colour; off, it shows none
// and takes no press.
export function colourWheel(pick, id = "") {
  const canvas = el("canvas", { width: WHEEL, height: WHEEL, className: "wheel", ...id ? { id } : {} });
  canvas.setAttribute("role", "img");
  const g = canvas.getContext("2d"), c = (WHEEL - 1) / 2, r = WHEEL / 2 - 1 - RIM;
  let on = true, marks = null, held = false;
  const at = (hue, sat) => {
    const a = hue * Math.PI / 180, d = r * clip(sat, 0, 1);
    return [c + d * Math.cos(a), c - d * Math.sin(a)];
  };
  const pickAt = (x, y) => [mod(Math.atan2(c - y, x - c) * 180 / Math.PI, 360), Math.min(Math.hypot(x - c, c - y) / r, 1)];
  const ring = ([x, y], radius, stroke, fill = null, width = 2) => {
    g.beginPath();
    g.arc(x, y, radius, 0, 2 * Math.PI);
    if (fill) {
      g.fillStyle = fill;
      g.fill();
    }
    g.lineWidth = width;
    g.strokeStyle = stroke;
    g.stroke();
  };
  const paint = () => {
    g.putImageData(discImage(), 0, 0);
    if (!on || !marks) return;
    for (const [h, s, fill] of marks.dots) ring(at(h, s), 3, "#000000", fill, 1);
    if (marks.start) ring(at(...marks.start), 5, "#ffffff");
    ring(at(marks.hue, marks.sat), 7, "#000000", marks.colour);
  };
  const pointer = (event) => {
    const box = canvas.getBoundingClientRect();
    const x = (event.clientX - box.left - canvas.clientLeft) * WHEEL / (canvas.clientWidth || WHEEL);
    const y = (event.clientY - box.top - canvas.clientTop) * WHEEL / (canvas.clientHeight || WHEEL);
    pick(...pickAt(x, y));
  };
  canvas.addEventListener("pointerdown", (event) => {
    if (!on) return;
    held = true;
    try {
      canvas.setPointerCapture(event.pointerId);
    } catch {
      // a pointer the browser doesn't know (a script's): the drag's moves still reach the canvas
    }
    pointer(event);
  });
  canvas.addEventListener("pointermove", (event) => on && held && pointer(event));
  for (const end of ["pointerup", "pointercancel"]) canvas.addEventListener(end, () => { held = false; });
  paint();
  return {
    canvas, at, pickAt,
    enable: (flag) => {
      on = flag;
      canvas.classList.toggle("off", !on);
      paint();
    },
    // The marker at (hue, sat) filled with colour, a ring at start ([hue, sat]) and a dot at each of dots ([hue, sat,
    // colour] each).
    show: (hue, sat, colour, start = null, dots = []) => {
      marks = { hue, sat, colour, start, dots };
      paint();
    },
  };
}

// A colour picked on the wheel (Modkit's WheelPicker): the wheel (hue and saturation), a value bar and a hex box, the
// old colour beside the new; OK keeps the new (0-255 each), Cancel or Escape none (null). In the page's own dialog.
let picking = null;
export function pickColour(colour, title) {
  if (!picking) {
    const ui = { title: el("p", { id: "var-pick-title", className: "note" }),
                 value: el("input", { id: "var-pick-value", type: "range", min: 0, max: 1, step: 0.01,
                                      ariaLabel: "Value" }),
                 hex: box("var-pick-hex", 9), old: el("span", { className: "var-swatch" }),
                 new: el("span", { id: "var-pick-new", className: "var-swatch" }),
                 note: el("p", { id: "var-pick-note", className: "note warn" }),
                 ok: button("var-pick-ok", "OK"), cancel: button("var-pick-cancel", "Cancel") };
    ui.wheel = colourWheel((h, s) => set({ h, s }), "var-pick-wheel");
    ui.dialog = el("dialog", { id: "var-pick", className: "weapon-popup" }, ui.title,
      el("div", { className: "var-wheel" }, ui.wheel.canvas,
         el("div", { className: "var-pick-side" }, el("p", { className: "rando-row" }, "Value", ui.value),
            el("p", { className: "rando-row" }, "Hex", ui.hex),
            el("p", { className: "rando-row", title: "The old colour, then the new" }, ui.old, ui.new), ui.note)),
      el("p", { className: "rando-row" }, ui.ok, ui.cancel));
    document.body.append(ui.dialog);
    let hsvNow = [0, 0, 1], done = null;
    const show = () => {
      const [h, s, v] = hsvNow, colour = hexOf(rgb(h, s, v));
      ui.wheel.show(h, s, colour);
      ui.value.value = String(v);
      ui.hex.value = colour;
      ui.new.style.background = colour;
    };
    const set = ({ h = hsvNow[0], s = hsvNow[1], v = hsvNow[2] }) => {
      hsvNow = [h, s, v];
      show();
    };
    const typed = () => {
      const found = rgbOfHex(ui.hex.value);
      ui.note.textContent = found ? "" : "a colour is #rrggbb";
      if (found) {
        const [h, s, v] = hsv(found);
        hsvNow = [s > 0 ? h : hsvNow[0], s, v];
      }
      show();
    };
    const end = (picked) => {
      ui.dialog.close();
      done?.(picked);
      done = null;
    };
    ui.value.addEventListener("input", () => set({ v: Number(ui.value.value) }));
    ui.hex.addEventListener("change", typed);
    ui.ok.addEventListener("click", () => {
      typed();
      end(rgb(...hsvNow));
    });
    ui.cancel.addEventListener("click", () => end(null));
    ui.dialog.addEventListener("cancel", () => end(null));
    picking = { ui, open: (old, said) => new Promise((resolve) => {
      done?.(null);
      done = resolve;
      hsvNow = hsv(old);
      ui.title.textContent = said;
      ui.old.style.background = hexOf(old);
      ui.note.textContent = "";
      show();
      ui.dialog.show();
      ui.ok.focus();
    }) };
  }
  return picking.open(colour ?? [255, 255, 255], title);
}

// coloursTab({state, call, app, image, packs, given, edit, keep, ask, say, dialog, folderOf}) -> {tab, pane, load,
// state}: state the Variants view's (its recipe, kind and name, ticket); given() the edit as the engine takes it;
// edit() after the tab wrote into the recipe (the view's status, JSON and Undo follow); keep(name, file, data) keeps a
// file the engine copied into your variant's folder (the site's: this browser's copy, null or why it didn't);
// folderOf(name) its folder as the engine names it.
export function coloursTab({ state: v, call, app, image, packs, given, edit, keep, ask, say, dialog = null, folderOf }) {
  const c = { row: null, reference: null, answer: null, asking: false, again: false, drawn: null, found: [], shown: [],
              rows: [], exporting: false, stale: true, asks: 0 };
  const ui = {
    tab: el("button", { id: "var-tab-colours", type: "button", role: "tab", textContent: "Colours" }),
    rows: el("span", { id: "var-rows", className: "views", role: "group", ariaLabel: "The row it edits" }),
    reset: button("var-colour-reset", "Reset row", "Drop this row's colour edits"),
    value: el("input", { id: "var-value", type: "range", min: VALUE_TRACK[0], max: VALUE_TRACK[1], step: VALUE_TRACK[2],
                         ariaLabel: "Value: darker left, brighter right", title: "Value: darker left, brighter right" }),
    boxes: { hex: box("var-hex", 8), ...Object.fromEntries(HSV.map(([key]) => [key, box(`var-${key}`)])) },
    pickNote: el("p", { id: "var-pick-note-row", className: "note warn" }),
    window: [box("var-window-lo", 4), box("var-window-hi", 4)], soft: box("var-soft", 4),
    windowNote: el("span", { id: "var-window-note", className: "note warn" }),
    swatches: Array.from({ length: 6 }, (_, i) => el("button", { type: "button", className: "var-swatch",
                                                                 title: "Swap this colour for another" })),
    swaps: el("span", { id: "var-swaps" }),
    export: button("var-png-export", "Export PNGs…", "Each row's texture as its build recolours it, a PNG each"),
    file: app ? null : el("input", { id: "var-png", type: "file", accept: ".png,image/png" }),
    path: app ? box("var-png-path", 24) : null,
    use: app ? button("var-png-use", "Import PNG", "An edited PNG of the chosen row's texture, by its full path") : null,
    choose: app && dialog ? button("var-png-choose", "Choose…") : null,
    pngNote: el("span", { id: "var-png-note", className: "note" }),
    tiles: el("div", { id: "var-tiles", className: "var-tiles" }),
    front: el("canvas", { id: "var-colour-front", width: VIEW, height: VIEW }),
    back: el("canvas", { id: "var-colour-back", width: VIEW, height: VIEW }),
    caption: el("p", { id: "var-colour-caption", className: "note" }),
  };
  ui.tab.setAttribute("aria-selected", "false");
  ui.path && (ui.path.placeholder = "Your PNG's full path");
  ui.path && (ui.path.inputMode = "text");
  for (const [k, input] of [["lo", ui.window[0]], ["hi", ui.window[1]], ["soft", ui.soft]]) input.ariaLabel = `Only hues: ${k}`;
  ui.front.setAttribute("aria-label", "In its colours, from the front");
  ui.back.setAttribute("aria-label", "In its colours, from behind");
  const wheel = colourWheel((hue, sat) => wheeled(hue, sat), "var-wheel");
  const field = (label, input, unit) => [el("span", { textContent: label }), input,
                                         el("span", { className: "unit", textContent: unit })];
  const pane = el("div", { id: "var-colours", hidden: true, className: "var-colours" },
    el("div", { className: "var-colour-controls" },
      el("p", { className: "rando-row" }, el("span", { className: "field", textContent: "Row" }), ui.rows,
         el("span", { className: "note", textContent: "ⓘ", title: TIP }), ui.reset),
      el("div", { className: "var-wheel" }, el("div", {}, wheel.canvas, ui.value),
         el("div", { className: "var-boxes" }, ...field("Hex", ui.boxes.hex, ""),
            ...HSV.flatMap(([key, label, unit]) => field(label, ui.boxes[key], unit)), ui.pickNote)),
      el("p", { className: "rando-row", id: "var-window" }, el("span", { className: "field", textContent: "Only hues" }),
         ui.window[0], "–", ui.window[1], "°  soft", ui.soft, "°", ui.windowNote),
      el("p", { className: "rando-row" }, el("span", { className: "field", textContent: "Palette" }),
         el("span", { id: "var-palette" }, ...ui.swatches), el("span", { className: "field", textContent: "Swaps" }), ui.swaps),
      el("p", { className: "rando-row" }, ui.export, ...app ? [ui.path, ui.use, ...ui.choose ? [ui.choose] : []]
        : [el("label", { className: "file", id: "var-png-box", title: PNG_TIP }, "Import PNG… ", ui.file)],
         el("span", { className: "note", textContent: "ⓘ", title: PNG_TIP })),
      el("p", { className: "rando-row" }, ui.pngNote), ui.tiles),
    el("div", { className: "var-colour-views" }, el("p", { className: "previews" }, ui.front, ui.back), ui.caption));

  // The recipe's entry for the row (none: every row's), and its hsv op; created on asking.
  const recipe = () => v.recipe;
  const entry = (create = false) => {
    const rows = Array.isArray(recipe().colours) ? recipe().colours : [];
    const found = rows.find((e) => e && typeof e === "object" && (e.row ?? null) === c.row);
    if (found || !create) return found ?? null;
    const made = c.row === null ? { ops: [] } : { row: c.row, ops: [] };
    recipe().colours = [...rows, made];
    return made;
  };
  const hsvOp = (create = false) => {
    const e = entry(create), ops = Array.isArray(e?.ops) ? e.ops : [];
    let op = ops.find((o) => o && typeof o === "object" && o.op === "hsv") ?? null;
    if (!op && create) {
      op = { op: "hsv" };
      e.ops.splice(ops[0]?.op === "png" ? 1 : 0, 0, op);   // after the row's PNG, which its value turns
    }
    return op;
  };
  const prune = () => {   // an hsv op left with nothing to do, an entry with no ops and an empty colours dropped
    const rows = recipe().colours;
    if (!Array.isArray(rows)) return;
    for (const e of rows) {
      if (e && Array.isArray(e.ops)) e.ops = e.ops.filter((o) => !(o?.op === "hsv" && Object.keys(o).length === 1));
    }
    recipe().colours = rows.filter((e) => !(e && Array.isArray(e.ops) && !e.ops.length));
    if (!recipe().colours.length) delete recipe().colours;
  };
  const changed = () => {   // a colour written: the view's status, Undo and the engine's recolour follow
    prune();
    edit();
    showWheel();
    recolour();
  };
  const numbers = () => {
    const op = hsvOp() ?? {};
    return Object.fromEntries(HSV.map(([key, , , d]) => [key, typeof op[key] === "number" ? op[key] : d]));
  };
  const put = (given) => {   // the hsv op's numbers, each at its default dropped
    const op = hsvOp(Object.entries(given).some(([k, x]) => x !== DEFAULTS[k]));
    if (!op) return;
    for (const [k, x] of Object.entries(given)) {
      if (x === DEFAULTS[k]) delete op[k];
      else op[k] = x;
    }
    changed();
  };
  const wheeled = (hue, sat) => {   // the row's main colour to that hue and saturation, its value kept
    if (!c.reference) return;
    const [h0, s0] = c.reference;
    put({ hue: fixed(mod(hue - h0 + 180, 360) - 180, 1), sat: fixed(sat / s0, 2) });
    showNumbers();
  };
  ui.value.addEventListener("input", () => {
    const step = VALUE_TRACK[2];
    put({ value: fixed(Math.round(Number(ui.value.value) / step) * step, 9) });
    showNumbers();
  });
  const hexShown = () => {   // the row's main colour as its hsv op turns it ("" for a row of greys)
    if (!c.reference) return "";
    const [h0, s0, v0] = c.reference, n = numbers();
    return hexOf(rgb(h0 + n.hue, s0 * n.sat, v0 * n.value));
  };
  const typed = (key) => {   // a box's number (any finite one, D23) or hex colour (the row's main colour to it)
    const text = ui.boxes[key].value.trim(), now = numbers();
    let given;
    if (key === "hex") {
      const found = rgbOfHex(text);
      const why = text.toLowerCase() === hexShown() ? "" : !found ? `'${text}' is not a colour (#rrggbb)`
        : !c.reference ? "its colours are greys: no hue to turn" : null;
      if (why !== null) {
        ui.pickNote.textContent = why;
        return showNumbers();
      }
      const [h0, s0, v0] = c.reference, [h, sat, val] = hsv(found);
      given = { hue: sat > 0 ? fixed(mod(h - h0 + 180, 360) - 180, 1) : now.hue, sat: fixed(sat / s0, 3),
                value: v0 > 0 ? fixed(val / v0, 3) : now.value };
    } else {
      const value = number(text);
      if (value === null) {
        ui.pickNote.textContent = `'${text}' is not a number`;
        return showNumbers();
      }
      given = { [key]: value };
    }
    ui.pickNote.textContent = "";
    if (Object.entries(given).some(([k, x]) => x !== now[k])) put(given);
    showNumbers();
  };
  for (const key of Object.keys(ui.boxes)) ui.boxes[key].addEventListener("change", () => typed(key));
  const showNumbers = () => {   // the boxes from the hsv op as written (the value bar's thumb held to its track)
    const op = hsvOp() ?? {};
    for (const [key, , , d] of HSV) ui.boxes[key].value = String(op[key] ?? d);
    ui.value.value = String(clip(numbers().value, VALUE_TRACK[0], VALUE_TRACK[1]));
    ui.boxes.hex.value = hexShown();
  };
  const setWindow = () => {   // the window of hues (both ends, or neither) and its soft edge into the hsv op
    const ends = ui.window.map((input) => input.value.trim()), soft = ui.soft.value.trim(), given = ends.map(number);
    const note = ends.some(Boolean) && !ends.every(Boolean) || ends.some((t, i) => t && given[i] === null)
      ? "give both ends as numbers, or neither" : soft && number(soft) === null ? `soft '${soft}' is not a number` : "";
    ui.windowNote.textContent = note;
    if (note) return;
    let op = hsvOp();
    const window = ends.every(Boolean) ? given : null;
    if (!op && !window && !soft) return;
    op ??= hsvOp(true);
    const old = JSON.stringify([op.window, op.soft]);
    for (const [key, value] of [["window", window], ["soft", soft ? number(soft) : null]]) {
      if (value === null) delete op[key];
      else op[key] = value;
    }
    if (JSON.stringify([op.window, op.soft]) !== old) changed();
  };
  for (const input of [...ui.window, ui.soft]) input.addEventListener("change", setWindow);
  ui.reset.addEventListener("click", () => {   // the chosen row's entry dropped (its hsv op, swaps and PNG)
    const e = entry();
    if (e) {
      recipe().colours = recipe().colours.filter((x) => x !== e);
      changed();
    }
    load();
  });

  // A palette colour's click: a swap from it (as it shows now) to a colour picked on the wheel; a grey has no hue.
  ui.swatches.forEach((swatch, i) => swatch.addEventListener("click", async () => {
    const from = c.shown[i];
    if (!from) return;
    if (hsv(from)[1] < GATE) return void (ui.windowNote.textContent = "a grey has no hue to swap");
    const to = await pickColour(from, "Swap this colour for");
    if (!to) return;
    entry(true).ops.push({ op: "swap", from: from.map((x) => fixed(x / 255, 3)), to: to.map((x) => fixed(x / 255, 3)) });
    changed();
    showSwaps();
  }));
  const showSwaps = () => {
    const swaps = (entry()?.ops ?? []).filter((o) => o?.op === "swap");
    ui.swaps.replaceChildren(...swaps.length ? swaps.flatMap((op) => {
      const chip = (key) => {
        const chip = el("span", { className: "var-swatch small" });
        chip.style.background = hexOf((Array.isArray(op[key]) ? op[key] : [0, 0, 0]).map((x) => 255 * clip(x, 0, 1)));
        return chip;
      };
      const drop = button("", "×", "Drop this swap");
      drop.classList.add("var-drop");
      drop.addEventListener("click", () => {
        const e = entry();
        if (e) e.ops = e.ops.filter((o) => o !== op);
        changed();
        showSwaps();
      });
      return [el("span", { className: "var-swap" }, chip("from"), "→", chip("to"), drop)];
    }) : [el("span", { className: "note", textContent: "none" })]);
  };

  // The wheel from the row's palette (found, and shown as its ops recolour it): its main colour (the most texels' with
  // a hue) where it was (a ring) and where the hsv op turns it (the marker), the others where its ops take them
  // (dots); off for a row of greys or none.
  const showWheel = () => {
    const coloured = c.found.map((x, i) => [x, i]).filter(([x]) => hsv(x)[1] >= COLOURED).map(([, i]) => i);
    c.reference = coloured.length ? hsv(c.found[coloured[0]]) : null;
    wheel.enable(Boolean(c.reference));
    if (c.reference) {
      const [h0, s0, v0] = c.reference, n = numbers();
      const dots = coloured.slice(1).filter((i) => c.shown[i]).map((i) => [...hsv(c.shown[i]).slice(0, 2), hexOf(c.shown[i])]);
      wheel.show(h0 + n.hue, s0 * n.sat, hexOf(rgb(h0 + n.hue, s0 * n.sat, v0 * n.value)), [h0, s0], dots);
    }
    if (!Object.values(ui.boxes).includes(document.activeElement)) showNumbers();   // a box being typed in keeps its text
  };

  // The rows: All rows, then each the body draws (before an answer, those the recipe names).
  const showRows = () => {
    const named = (Array.isArray(recipe().colours) ? recipe().colours : []).map((e) => e?.row).filter(Number.isInteger);
    const rows = [...new Set([...c.rows.length ? c.rows : named, ...c.row === null ? [] : [c.row]])].sort((a, b) => a - b);
    ui.rows.replaceChildren(...[null, ...rows].map((row) => {
      const pick = el("button", { type: "button", textContent: row === null ? "All rows" : String(row) });
      pick.dataset.row = row === null ? "" : String(row);
      pick.setAttribute("aria-pressed", String(row === c.row));
      pick.addEventListener("click", () => select(row));
      return pick;
    }));
    ui.reset.textContent = c.row === null ? "Reset all rows" : "Reset row";
  };
  // Another row chosen: the last row's palette dropped till this one's answer (the wheel off, the swatches doing
  // nothing), so no wheel press, swap or hex box reads its colours against the last row's.
  const choose = (row) => {
    if (row !== c.row) Object.assign(c, { row, found: [], shown: [] });
  };
  const select = (row) => {
    choose(row);
    load();
  };

  // The engine's recolour: one ask at a time, the newest edit's asked once it answers; shown only while the tab is.
  const key = () => JSON.stringify([v.ticket, c.row, given()]);
  const bitmap = async (data) => createImageBitmap(new Blob([bytesOf(data)], { type: "image/png" }));
  const recolour = async () => {
    if (pane.hidden) return void (c.stale = true);
    c.stale = false;
    if (!image()) {
      ui.caption.textContent = `${CHOOSE} to draw it in its colours.`;
      return;
    }
    if (c.asking) return void (c.again = true);
    c.asking = true;
    const mine = v.ticket, asked = key(), row = c.row;
    if (!c.answer) ui.caption.textContent = "Drawing…";
    c.asks++;
    const reply = await call("variant_colours", { ...app ? {} : { file: image() },
                                                  given: { ...given(), iso: app ? image() : null, packs: packs(), row } });
    if (mine === v.ticket && row === c.row) await drawn(reply);
    c.drawn = asked;
    c.asking = false;
    if (c.again || asked !== key()) {
      c.again = false;
      recolour();
    }
  };
  const drawn = async (reply) => {
    if ("refused" in reply) {
      ui.caption.textContent = reason(reply.refused);
      ui.caption.classList.add("warn");
      return;
    }
    ui.caption.classList.remove("warn");
    c.answer = reply;
    c.rows = Object.keys(reply.rows).map(Number).sort((a, b) => a - b);
    c.found = reply.palette.found;
    c.shown = reply.palette.shown;
    showRows();
    ui.swatches.forEach((swatch, i) => {
      swatch.hidden = !c.shown[i];
      if (c.shown[i]) swatch.style.background = hexOf(c.shown[i]);
    });
    showWheel();
    if (ui.tiles.childElementCount !== c.rows.length
        || [...ui.tiles.children].some((tile, i) => tile.dataset.row !== String(c.rows[i]))) {
      ui.tiles.replaceChildren(...c.rows.map((row) => {
        const tile = el("button", { type: "button", className: "var-tile", title: `Row ${row}` },
                        el("canvas", { width: 64, height: 64 }), el("span", { textContent: String(row) }));
        tile.dataset.row = String(row);
        tile.addEventListener("click", () => select(row));
        return tile;
      }));
    }
    const crop = Math.min(VIEW, Math.ceil(reply.across * (VIEW - 2)) + 4), at = Math.floor((VIEW - crop) / 2);
    const [front, back, ...tiles] = await Promise.all([reply.front, reply.back, ...c.rows.map((r) => reply.rows[r].tile)]
      .map(bitmap));
    for (const [canvas, picture] of [[ui.front, front], [ui.back, back]]) {
      canvas.width = crop;
      canvas.getContext("2d").drawImage(picture, at, 0, crop, VIEW, 0, 0, crop, VIEW);
    }
    [...ui.tiles.children].forEach((tile, i) => {
      tile.setAttribute("aria-pressed", String(c.rows[i] === c.row));
      const g = tile.firstChild.getContext("2d");
      g.drawImage(tiles[i], 0, 0);
    });
    ui.caption.textContent = reply.dressed ? "Front, back: as its build dresses it" : `Front, back: ${reply.body}`;
  };

  // Export PNGs: the rows' textures as the edit's build recolours them (unsaved edits too): the app's into a folder (its
  // dialog's, else a new one in Downloads), the site's a zip, the browser's download.
  const pngSaid = (text, warn = false) => {
    ui.pngNote.textContent = text;
    ui.pngNote.classList.toggle("warn", warn);
  };
  ui.export.addEventListener("click", async () => {
    if (!image()) return pngSaid(CHOOSE, true);
    if (c.exporting) return pngSaid("Exporting…");
    const out = app && dialog ? await dialog("folder", "") : "";
    if (out === null) return;
    c.exporting = true;
    ui.export.disabled = true;
    pngSaid("Exporting…");
    const reply = await call("export_pngs", { ...app ? {} : { file: image() },
                                              given: { ...given(), iso: app ? image() : null, packs: packs(),
                                                       ...app ? { out } : {} } }, { once: true });
    c.exporting = false;
    ui.export.disabled = !image();
    if ("refused" in reply) return pngSaid(`Not exported: ${reason(reply.refused)}`, true);
    if (app) return pngSaid(`${reply.files.length} PNGs in ${reply.out}: ${reply.files.join(", ")}`);
    const url = URL.createObjectURL(new Blob([bytesOf(reply.zip)], { type: "application/zip" }));
    const a = el("a", { href: url, download: reply.name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    pngSaid(`${reply.files.length} PNGs in ${reply.name}: ${reply.files.join(", ")}`);
    say(`Saving ${reply.name}: your browser's download shows it`);
  });

  // Import PNG: an edited PNG of the chosen row's texture (its size) copied into your saved variant's folder and named
  // by the row's png op, its only op: the row's other colour edits go after a yes (an exported PNG holds them already;
  // Undo takes it back).
  const imported = async (read) => {
    const size = c.answer?.rows?.[c.row]?.size;
    const why = v.kind !== "yours" ? "Save as first: Import copies the PNG into the variant's folder"
      : c.row === null ? "Choose a row: a PNG is one row's texture" : !size?.length ? "Its body isn't read yet" : "";
    if (why) return pngSaid(why, true);
    const ops = (entry()?.ops ?? []).map((o) => o?.op);
    const count = (op) => ops.filter((o) => o === op).length;
    const edits = [["hsv", "wheel edit"], ["swap", "swap"], ["png", "PNG"]].filter(([op]) => count(op))
      .map(([op, word]) => `${count(op)} ${word}${count(op) > 1 ? "s" : ""}`).join(", ");
    if (ops.length && !await ask(`The PNG replaces row ${c.row}'s colour edits (${edits || ops.length}); an exported PNG `
                                 + "holds them already. Replace them? (Undo takes it back.)")) return;
    const name = v.name, row = c.row;
    pngSaid("Importing…");   // at once: the note never holds the last import's line while this one runs
    const picked = await read();
    if (!picked) return pngSaid("");
    const reply = await call("add_png", app ? { name, path: picked.path, size }
      : { given: { folder: folderOf(name), file: picked.name, size }, data: picked.data });
    if ("refused" in reply) return pngSaid(`Not imported: ${reason(reply.refused)}`, true);
    const lost = app ? null : await keep(name, reply.name, picked.data);
    if (name !== v.name) return;
    choose(row);
    entry(true).ops = [{ op: "png", file: reply.name, sha256: reply.sha256 }];
    edit();
    load();
    pngSaid(lost ? `Row ${row}'s texture is ${reply.name}, but this browser didn't keep the file (${lost})`
      : `Row ${row}'s texture is ${reply.name}`, Boolean(lost));
  };
  ui.file?.addEventListener("change", async () => {
    const file = ui.file.files[0];
    ui.file.value = "";
    if (file) await imported(async () => ({ name: file.name, data: new Uint8Array(await file.arrayBuffer()) }));
  });
  ui.use?.addEventListener("click", () => ui.path.value.trim() && imported(async () => ({ path: ui.path.value.trim() })));
  ui.choose?.addEventListener("click", () => imported(async () => {
    const path = await dialog("replacement", "");
    return path ? { path } : null;
  }));

  // The controls from the recipe's entry for the row, then the engine's recolour (the tab shown: else when it shows).
  const load = () => {
    const op = hsvOp() ?? {};
    showRows();
    showNumbers();
    const window = Array.isArray(op.window) && op.window.length === 2 ? op.window : ["", ""];
    ui.window.forEach((input, i) => { input.value = String(window[i]); });
    ui.soft.value = typeof op.soft === "number" ? String(op.soft) : "";
    ui.windowNote.textContent = "";
    ui.pickNote.textContent = "";
    showSwaps();
    showWheel();
    ui.export.disabled = !image() || c.exporting;   // greyed with D979's line until an image is picked
    ui.export.title = image() ? "Each row's texture as its build recolours it, a PNG each" : CHOOSE;
    recolour();
  };
  return {
    tab: ui.tab, pane, load,
    // Another recipe opened: the first row's every-row entry, its last answer dropped.
    opened: () => {
      Object.assign(c, { row: null, answer: null, found: [], shown: [], rows: [], drawn: null });
      ui.tiles.replaceChildren();
      for (const canvas of [ui.front, ui.back]) canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
      pngSaid("");
    },
    shown: (on) => {
      pane.hidden = !on;
      ui.tab.setAttribute("aria-selected", String(on));
      if (on && c.stale) load();
    },
    // For a test or the perf gate: whether the last answer drawn is the edit's as it stands.
    state: Object.assign(c, { current: () => c.drawn === key() && !c.asking }),
  };
}
