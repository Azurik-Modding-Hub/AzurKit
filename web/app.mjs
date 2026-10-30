// The page (D866): pick your image, choose packs and set their sliders, Build, then Save. One page for both hosts,
// the site and the app; it decides no output byte (WEB §3.1). host.json names the host's engine, and the engine, azurkit.sdk, plans and
// checks the build. The site's, siteEngine(), is the wheel under Pyodide in a fresh module worker for each build: it
// returns the build as segments, which this page joins into a Blob of slices of your own file and the bytes the
// build writes (WEB §3.4), and Save downloads it. The app's, appEngine(), is azurkit.sdk on CPython behind the app's
// own server on 127.0.0.1 (azurkit.app), in its window or a browser alike: it reads the image at the path you give
// and writes the build where you save it. Text reaches the page only through textContent. No eval: the CSP has no
// 'unsafe-eval', and no host evaluates script in the page (4.1b2).
//
// A recipe travels as a share link (WEB §4.1, §4.2): Copy link asks the engine for the #p=… fragment of the packs,
// their sliders and the config.xbr cells a loaded recipe set (sdk.preset_encode), and a page opened with one loads
// it (sdk.preset_decode): the packs ticked, the sliders set, each value it changed marked ●, never a build. Picking an
// AzurKit build as the image offers its recipe the same way (sdk.open_build), to build again from a vanilla image.
//
// Its design is A, the dense tool (D900): the toolbar's tabs come from the catalog, those whose area works (D898,
// D901, D902); the Patches tab groups the packs by the catalog's categories, each group folding, and each pack with
// settings has a Settings opener with their count (D903), which shows them beside the list; Build and Save sit in a
// bar along the window's bottom. Dark whatever the system's setting, until the toolbar's toggle picks light (D897).
// A pack's settings are locked until its pack is ticked (D907), and a setting that only picks whether a left-stick
// click flips another in game shows as a small L3 toggle at the end of that one's row (D909).
//
// The page remembers its setup between visits (D915): the site in this browser's storage, the app in its config. It
// comes back when the page opens, before you pick an image, less whatever no longer applies (named in the status
// line); a share link, or a build's recipe you load, takes its place; Reset to defaults forgets it.
//
// The Randomizer tab (Step 4.2c1, RANDOMIZER_PLAN §5.5): Randomize (off by default, the tab's one switch, which
// unlocks its settings, D907), the seed and New, the options with D144's defaults, the share string, the item rows
// (each a category it shuffles) and the skips a setting can turn on, and the spoiler of the last randomized build. The
// engine reads the settings (sdk.randomizer_settings) and gives back what the tab shows; Build and Save are the
// bottom bar's, which build the randomizer's plan first (Modkit's order). A link and a build's recipe carry it.
//
// Its Tracker view (Step 4.2c2, tracker.mjs): the item tracker of a randomized build, of the seed the Settings view
// holds, or of a plan file, in both hosts; Live, which reads a running xemu, in the app alone (D882).
import { tracker } from "./tracker.mjs";

const $ = (id) => document.getElementById(id);
const R = (id) => $(`rando-${id}`);
const state = { engine: null, app: false, dialogs: false, ready: false, building: false, saving: false, file: null,
                packs: null, sent: null, build: null, url: null, saved: null, poll: null, violations: [],
                vanilla: null, asked: null, xbr: [], link: null, pending: null, loaded: null, opened: null,
                site: null, theme: "dark", tab: null, remembered: null, kept: null, restoring: false, plain: true,
                later: null, spoiler: null, tracker: null, call: null,
                rando: { view: null, overrides: {}, ticket: 0, waiting: false, given: null, load: null, later: null,
                         note: null, noted: null, asked: null, groups: new Set() } };
globalThis.azurkit = state;   // the last build and save, for the tests and the console

// The theme (D897): dark, or light once the toggle picks it, which is remembered: by the site in this browser's
// storage, by the app in its settings (host.json's theme; api/theme), since its page has a new address each launch.
// theme.js, a classic script in the head, sets the remembered one before the first paint; this module runs after it.
const THEME = "azurkit.theme";
function theme(name, keep = false) {
  const light = name === "light";
  state.theme = document.documentElement.dataset.theme = light ? "light" : "dark";
  $("theme").textContent = light ? "☾ Dark" : "☀ Light";
  $("theme").title = `Switch to the ${light ? "dark" : "light"} theme (AzurKit remembers it)`;
  if (!keep) return;
  if (state.app) return state.engine.theme(state.theme);
  try {
    localStorage.setItem(THEME, state.theme);
  } catch {}   // storage refused (a private window, say): the theme lasts this visit
}

// The setup the page remembers (D915): the packs ticked, each setting whose value differs from its default (its pack
// ticked or not: an unticked pack keeps its values, D907; a value that isn't a number isn't kept) and a loaded recipe's
// config.xbr cells (set: names and numbers, Q174). Never the image, its path or anything read from it: the site
// keeps it in this browser's storage, the app in its config (api/setup), and the page at its defaults keeps nothing.
const SETUP = "azurkit.setup";
function setup() {
  const values = {};
  for (const pack of state.packs.packs) {
    for (const slider of pack.sliders) {
      const value = given(document.getElementById(`${pack.name}.${slider.name}`));
      if (typeof value === "number" && value !== slider.default) (values[pack.name] ??= {})[slider.name] = value;
    }
  }
  const ticked = state.packs.packs.filter((pack) => $("packs").querySelector(`input[data-pack="${pack.name}"]`).checked)
    .map((pack) => pack.name);
  const rando = randoSetup();
  return { ticked, values, xbr: state.xbr.filter((op) => op.op === "set"), ...(rando ? { randomizer: rando } : {}) };
}

// Keep the page's setup (none at its defaults), once it is the page's own: after the remembered one is back.
function remember() {
  clearTimeout(state.later);
  if (!state.packs || state.restoring) return;
  const kept = setup(), defaults = state.packs.packs.filter((pack) => pack.default_on).map((pack) => pack.name);
  state.plain = !kept.xbr.length && !Object.keys(kept.values).length && kept.ticked.join() === defaults.join()
    && !kept.randomizer;
  $("reset").disabled = state.building || state.plain;
  const text = state.plain ? null : JSON.stringify(kept);
  if (text === state.kept) return;
  state.kept = text;
  if (state.app) return state.engine.setup(state.plain ? null : kept);
  try {
    if (state.plain) localStorage.removeItem(SETUP);
    else localStorage.setItem(SETUP, text);
  } catch {}   // storage refused (a private window, say): the setup lasts this visit
}

// What the site's storage holds (the app's comes in host.json): the setup to restore, as the engine reads it.
function stored() {
  try {
    state.kept = localStorage.getItem(SETUP);
  } catch {}
  if (state.kept == null) return null;
  try {
    return JSON.parse(state.kept);
  } catch {
    return state.kept;   // the engine names it unreadable
  }
}

function say(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
}

function stop(text) {
  document.body.replaceChildren(Object.assign(document.createElement("p"), { textContent: text }));
}

const bytes = (n) => `${n.toLocaleString("en-US")} B`;

// The site's engine: one worker per build, started from a blob: URL so that it keeps the page's CSP; it is
// replaced after each build or cancel (wasm memory never shrinks), and not after one that never loaded.
function siteEngine({ ready, built, refused, failed, vanilla, opened, shared, decoded, restored, rando }) {
  let worker = null, loaded = false, calls = 0;
  const pending = new Map();   // the tracker's asks in flight (call id -> its message and answer), sent again to a
                               // worker that replaces one stopped before it answered
  const start = () => {
    loaded = false;
    const entry = new URL("worker.mjs", location.href).href;
    const url = URL.createObjectURL(new Blob([`import ${JSON.stringify(entry)};\n`], { type: "text/javascript" }));
    worker = new Worker(url, { type: "module" });
    worker.onmessage = ({ data }) => {
      if (data.type === "ready") {
        URL.revokeObjectURL(url);
        loaded = true;
        for (const [, { message }] of pending) worker.postMessage(message);
        ready(data.catalog, data.version);
      } else if (data.type === "reply") {
        pending.get(data.call)?.done(data.reply);
        pending.delete(data.call);
      } else if (data.type === "vanilla") {
        const { type, ...read } = data;
        vanilla(read);
      } else if (data.type === "opened") {
        opened(data.preset);
      } else if (data.type === "preset") {
        shared(data.fragment);
      } else if (data.type === "decoded") {
        decoded(data.preset);
      } else if (data.type === "restored") {
        const { type, ...setup } = data;
        restored(setup);
      } else if (data.type === "rando") {
        rando(data.reply, data.ticket);
      } else if (data.type === "refused" && data.quiet) {
        failed(data.message);
      } else if (data.type === "built" || data.type === "refused") {
        restart();
        (data.type === "built" ? built : refused)(data);
      } else if (data.type === "csp") {
        state.violations.push(`worker: ${data.directive} ${data.blocked}`);
        failed(`The page's security policy refused ${data.directive} in the engine`);
      } else if (data.type === "failed") {
        restart();
        failed(data.message);
      }
    };
    worker.onerror = (e) => {
      e.preventDefault();
      restart();
      failed(`The engine stopped (${e.message || "out of memory?"}): try again, or use the desktop app`);
    };
  };
  const restart = () => {
    worker.terminate();
    if (loaded) start();
  };
  start();
  return {
    build: (file, packs, xbr, randomizer) => worker.postMessage({ type: "build", file, packs, xbr, randomizer }),
    randomizer: (given, ticket) => worker.postMessage({ type: "randomizer", given, ticket }),
    vanilla: (file) => worker.postMessage({ type: "vanilla", file }),
    preset: (recipe, report) => worker.postMessage({ type: "preset", recipe, report }),
    decode: (text) => worker.postMessage({ type: "decode", text }),
    restore: (setup) => worker.postMessage({ type: "restore", setup }),
    call: (type, body) => new Promise((done) => {
      const message = { type, call: ++calls, ...body };
      pending.set(message.call, { message, done });
      if (loaded) worker.postMessage(message);
    }),
    cancel: restart,
  };
}

// The app's engine: azurkit.sdk on CPython behind this launch's server (azurkit.app), the same in the app's window
// and in a browser. The page posts JSON to it, and a refusal comes back as {refused}. A build's reply that arrives
// after Cancel is dropped; a save's is awaited, since the server says whether it wrote anything.
function appEngine(host, { ready, built, refused, failed, saved, vanilla, opened, shared, decoded, restored, rando }) {
  let ticket = 0;
  const post = async (path, body, keepalive = false) => {
    const reply = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
                                      body: JSON.stringify(body), keepalive });
    if (!reply.ok) throw new Error(`${path}: HTTP ${reply.status}`);
    return reply.json();
  };
  const run = async (path, body, done) => {
    const mine = ++ticket;
    try {
      const reply = await post(path, body);
      if (mine !== ticket) return;
      if ("refused" in reply) refused({ message: reply.refused });
      else done(reply);
    } catch (error) {
      if (mine === ticket) failed(`The app's engine didn't answer (${error.message}): restart AzurKit`);
    }
  };
  setTimeout(() => ready(host.catalog, host.version));
  const ask = (path, body, done) => post(path, body)
    .then((reply) => "refused" in reply ? failed(reply.refused) : done(reply))
    .catch((error) => failed(`The app's engine didn't answer (${error.message}): restart AzurKit`));
  return {
    build: (iso, packs, xbr, randomizer) => run("api/build", { iso, packs, xbr, randomizer }, built),
    randomizer: (given, ticket) => post("api/randomizer", { given }).then((reply) => rando(reply, ticket))
      .catch((error) => rando({ refused: `The app's engine didn't answer (${error.message})` }, ticket)),
    spoiler: (out) => ask("api/spoiler", { out }, (reply) => say(`Saved the spoiler: ${reply.spoiler.out}`)),
    vanilla: (iso) => post("api/vanilla", { iso }).then((read) => "refused" in read
      || ("opened" in read ? opened(read.opened) : vanilla(read))).catch(() => {}),
    preset: (recipe, report) => ask("api/preset", { recipe, report }, (reply) => shared(reply.fragment)),
    decode: (text) => ask("api/decode", { text }, (reply) => decoded(reply.preset)),
    restore: (setup) => ask("api/restore", { setup }, restored),
    setup: (setup) => post("api/setup", { setup }, true).catch(() => {}),   // remembering is a convenience
    save: (recipe, out) => run("api/save", { recipe, out }, saved),
    progress: async () => (await fetch("api/progress", { cache: "no-store" })).json(),
    choose: async (kind, path) => (await post("api/choose", { kind, path })).path ?? null,
    theme: (name) => post("api/theme", { theme: name }).catch(() => {}),   // remembering is a convenience
    call: (type, body) => post(`api/${type}`, body)
      .catch((error) => ({ refused: `The app's engine didn't answer (${error.message}): restart AzurKit` })),
    // remembering is a convenience; not keepalive: a plan and its marks may pass keepalive's 64 KiB
    tracked: (kept) => post("api/tracked", { tracker: kept }).catch(() => {}),
    cancel: () => {
      if (!state.saving) ticket++;
      post("api/cancel", {}).catch(() => {});
    },
  };
}

const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i;
// What a slider's box holds, as the engine gets it: a number, or the text as typed, which the engine refuses by name.
const typed = (text) => NUMBER.test(text.trim()) && Number.isFinite(Number(text)) ? Number(text) : text;
// A setting's field as the engine gets it (an L3 toggle's tick as 1 or 0), and as the page shows it.
const given = (field) => field.type === "checkbox" ? Number(field.checked) : typed(field.value);
const shown = (field) => field.type === "checkbox" ? String(Number(field.checked)) : field.value;

// The L3 toggles (D909), from the catalog: a whole 0-or-1 setting named toggle_<other> picks whether a left-stick
// click (L3) flips <other>, a setting of the same pack, to vanilla and back in game (player_physics' speed toggle,
// D713). It shows as a small L3 toggle at the end of <other>'s row, not as a row of its own. {other: the toggle}
function flips(pack) {
  const names = new Set(pack.sliders.map((slider) => slider.name));
  return new Map(pack.sliders.filter(({ name, whole }) => name.startsWith("toggle_") && names.has(name.slice(7))
    && whole?.[0] === 0 && whole?.[1] === 1).map((toggle) => [toggle.name.slice(7), toggle]));
}

// One slider, inline: its label, its track, its box and unit, and its L3 toggle if it has one (flip). The box holds
// the value (any finite number, D23); the track's ends are hints that widen to hold the vanilla value (D42) and
// whatever the box holds, so nothing clamps.
function sliderRow(pack, slider, flip) {
  const row = Object.assign(document.createElement("div"), { className: "slider", title: slider.description });
  const mark = Object.assign(document.createElement("span"), { className: "mark" });
  const id = `${pack.name}.${slider.name}`;
  const track = Object.assign(document.createElement("input"), {
    type: "range", step: slider.whole ? Math.max(1, slider.step) : slider.step, ariaLabel: `${slider.label} (track)` });
  const box = Object.assign(document.createElement("input"), {
    type: "text", id, value: String(slider.default), inputMode: "decimal", spellcheck: false, autocomplete: "off" });
  box.dataset.slider = slider.name;
  const unit = Object.assign(document.createElement("span"), { className: "unit" });
  const l3 = flip && Object.assign(document.createElement("input"), {
    type: "checkbox", id: `${pack.name}.${flip.name}`, checked: flip.default === 1,
    ariaLabel: `L3: a left-stick click flips ${slider.label} to vanilla and back` });
  const fit = () => {
    unit.textContent = slider.unit + (slider.vanilla == null ? "" : ` · vanilla ${slider.vanilla}`);
    const value = typed(box.value), ends = [slider.min, slider.max, slider.default, slider.vanilla, value];
    const held = ends.filter((v) => typeof v === "number");
    track.min = String(Math.min(...held));
    track.max = String(Math.max(...held));
    if (typeof value === "number") track.value = String(value);
    box.classList.toggle("changed", value !== slider.default);
    l3?.classList.toggle("changed", given(l3) !== flip.default);
  };
  track.addEventListener("input", () => {
    box.value = track.value;
    fit();
  });
  box.addEventListener("input", fit);
  const label = Object.assign(document.createElement("label"), { htmlFor: id, textContent: slider.label });
  label.prepend(mark);
  row.append(label, track, box, unit);
  if (l3) {
    l3.dataset.slider = flip.name;
    l3.addEventListener("change", fit);
    const toggle = Object.assign(document.createElement("label"), {
      className: "l3", title: `On: in game, a left-stick click (L3) flips ${slider.label} to vanilla and back` });
    toggle.append(Object.assign(document.createElement("span"), { className: "mark" }), l3, "L3");
    row.append(toggle);
  }
  fit();
  row.fit = fit;
  return row;
}

// The picked image's own value of each slider at its XBE's sites (the catalog has none: the wheel holds no game
// constant), shown beside it and held by its track (D42). A reply for an image no longer picked is dropped.
function vanilla(read) {
  if (state.asked !== state.file) return;
  state.vanilla = read;
  for (const pack of state.packs?.packs ?? []) {
    for (const slider of pack.sliders) {
      const value = read.packs[pack.name]?.[slider.name];
      if (value === undefined) continue;
      slider.vanilla = value;
      document.getElementById(`${pack.name}.${slider.name}`)?.closest(".slider").fit();
    }
  }
}

// Ask the engine for the picked image's values once it is ready (the site's is replaced after each build).
function askVanilla() {
  if (!state.ready || !state.file || state.asked === state.file || state.building) return;
  state.asked = state.file;
  state.engine.vanilla(state.file);
}

// Ticking a pack ticks the packs it requires, and unticking one unticks the packs that require it (D588), so the
// page never sends a recipe the engine refuses for a missing pack.
function linked(changed) {
  const boxes = Object.fromEntries([...$("packs").querySelectorAll("input[data-pack]")].map((b) => [b.dataset.pack, b]));
  const requires = Object.fromEntries(state.packs.packs.map((p) => [p.name, p.requires]));
  const todo = [changed.dataset.pack];
  while (todo.length) {
    const name = todo.pop(), on = boxes[name].checked;
    const next = on ? requires[name] : Object.keys(requires).filter((other) => requires[other].includes(name));
    for (const other of next) {
      if (boxes[other].checked !== on) {
        boxes[other].checked = on;
        todo.push(other);
      }
    }
  }
}

// One pack's row: its tick, name, description and releases; with settings, its Settings opener (the count of their
// rows: an L3 toggle sits in its setting's) and the settings themselves, which show beside the list while the pack
// is open.
function packRow(pack) {
  const item = Object.assign(document.createElement("div"), { className: "pack" });
  item.dataset.pack = pack.name;
  const label = document.createElement("label");
  const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: pack.default_on });
  box.dataset.pack = pack.name;
  box.addEventListener("change", () => linked(box));
  const name = Object.assign(document.createElement("span"), { className: "name", textContent: pack.name });
  name.prepend(Object.assign(document.createElement("span"), { className: "mark" }));
  const what = Object.assign(document.createElement("span"), { textContent: pack.description });
  const where = Object.assign(document.createElement("span"), {
    className: "releases", textContent: ` ${pack.releases.map((r) => r === "usa" ? "USA" : "Europe").join(", ")}` });
  what.append(where);
  label.append(box, name, what);
  const sliders = Object.assign(document.createElement("div"), { className: "sliders", id: `${pack.name}-settings` });
  sliders.setAttribute("role", "group");
  sliders.setAttribute("aria-label", pack.name);
  const flipped = flips(pack), toggles = new Set(flipped.values());
  const rows = pack.sliders.filter((slider) => !toggles.has(slider))
    .map((slider) => sliderRow(pack, slider, flipped.get(slider.name)));
  sliders.append(...rows);
  const opener = Object.assign(document.createElement("button"), {
    type: "button", className: "toggle", textContent: `Settings · ${rows.length}`,
    title: `${pack.name}'s settings`, hidden: !rows.length });
  opener.setAttribute("aria-expanded", "false");
  opener.setAttribute("aria-controls", sliders.id);
  opener.addEventListener("click", () => show(item));
  item.append(label, opener, sliders);
  return item;
}

// The packs in their categories' groups, in the catalog's order; each group folds. The first pack with settings
// opens.
function renderPacks(catalog) {
  const list = $("packs");
  list.replaceChildren();
  for (const category of catalog.categories) {
    const packs = catalog.packs.filter((pack) => pack.category === category.id);
    if (!packs.length) continue;
    const group = Object.assign(document.createElement("details"), { className: "group", open: true });
    group.dataset.category = category.id;
    const summary = document.createElement("summary");
    summary.append(Object.assign(document.createElement("b"), { textContent: category.title }),
                   Object.assign(document.createElement("span"), { className: "tally" }),
                   Object.assign(document.createElement("span"), { className: "line", textContent: category.description }));
    group.append(summary, ...packs.map(packRow));
    list.append(group);
  }
  tally();
  lock();
  show(list.querySelector(".pack:has(.slider)"));
}

// Open one pack's settings and close the others' (a wide page shows them beside the list), or close it again.
function show(item) {
  const on = !item?.classList.contains("open");
  for (const pack of $("packs").querySelectorAll(".pack")) {
    pack.classList.toggle("open", on && pack === item);
    pack.querySelector(".toggle").setAttribute("aria-expanded", String(on && pack === item));
  }
  place();
}

// The open pack's settings start beside its row, so a pack low in a scrolled list shows them in view; placed again
// when a group folds, the window's width moves the rows or the tab comes back (a hidden tab's rows have no place).
function place() {
  const item = $("packs").querySelector(".pack.open");
  if (item?.offsetParent) item.querySelector(".sliders").style.top = `${item.offsetTop}px`;
}

// A pack's settings are locked (greyed, still readable, not editable) until its pack is ticked, and every field while
// a build runs (D907): ticking a pack unlocks its settings with their values as they were, and unticking it locks them
// again, the values kept for later. A share link or a build's recipe sets the ticks and the values together.
function lock() {
  for (const item of $("packs").querySelectorAll(".pack")) {
    const box = item.querySelector("input[data-pack]");
    box.disabled = state.building;
    for (const field of item.querySelectorAll(".sliders input")) field.disabled = state.building || !box.checked;
  }
}

// Each group's count of its packs ticked, which a folded group still shows.
function tally() {
  for (const group of $("packs").querySelectorAll(".group")) {
    const boxes = [...group.querySelectorAll("input[data-pack]")];
    group.querySelector(".tally").textContent = `${boxes.filter((box) => box.checked).length} of ${boxes.length} on`;
  }
}

// The toolbar's tabs: the catalog's, in its order, each that this page has a panel for; one panel shows at a time.
function renderTabs(tabs) {
  const strip = $("tabs");
  strip.replaceChildren();
  for (const { id, title } of tabs) {
    const panel = [...document.querySelectorAll("[role=tabpanel]")].find((p) => p.dataset.tab === id);
    if (!panel) continue;
    const tab = Object.assign(document.createElement("button"), { type: "button", id: `tab-${id}`, textContent: title });
    tab.dataset.tab = id;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", panel.id);
    tab.addEventListener("click", () => pick(id));
    strip.append(tab);
  }
  pick(strip.firstElementChild?.dataset.tab ?? null);
}

function pick(id) {
  state.tab = id;
  if (id === "randomizer" && state.packs) askRando();   // the Patches tab's packs may have changed
  for (const tab of $("tabs").children) tab.setAttribute("aria-selected", String(tab.dataset.tab === id));
  for (const panel of document.querySelectorAll("[role=tabpanel]")) panel.hidden = panel.dataset.tab !== id;
  place();
}

// The ticked packs, each with its sliders' values as typed: the engine normalizes them and names what it refuses.
function chosen() {
  const packs = {};
  for (const item of $("packs").querySelectorAll(".pack")) {
    if (!item.querySelector("input[data-pack]").checked) continue;
    packs[item.dataset.pack] = Object.fromEntries(
      [...item.querySelectorAll("input[data-slider]")].map((field) => [field.dataset.slider, given(field)]));
  }
  return packs;
}

function busy(on) {
  state.building = on;
  $("build").disabled = on || !state.file || !state.ready;
  $("share").disabled = on || !state.packs;
  $("reset").disabled = on || state.plain;
  $("iso").disabled = on || !state.packs;
  for (const id of ["iso-path", "iso-choose", "out-path"]) $(id).disabled = on;
  $("save").disabled = on || !state.build;
  $("cancel").hidden = !on;
  lock();
  lockRando();
  if (!on) {
    clearInterval(state.poll);
    state.saving = false;
  }
}

function forget() {
  if (state.url) URL.revokeObjectURL(state.url);
  state.build = state.url = null;
  $("save").disabled = true;
  $("out-row").hidden = true;
  spoiler(null);
}

// Set the page to a recipe: tick exactly the packs `on` names, set each setting to `values`' value, else its default,
// and keep the config.xbr cells `xbr` for the build; the ticked packs' settings unlock, the others' lock (D907). With
// `from` (a link, a build) each tick and value it changed is marked ●, without it every mark is cleared. Never a build.
function setTo(on, values, xbr, from = null) {
  const mark = (element, changed) => {
    element.textContent = from && changed ? "●" : "";
    element.title = from && changed ? `Changed by ${from}` : "";
  };
  forget();
  for (const item of $("packs").querySelectorAll(".pack")) {
    const box = item.querySelector("input[data-pack]");
    const pack = state.packs.packs.find((p) => p.name === item.dataset.pack);
    mark(item.querySelector(".name .mark"), box.checked !== on.has(pack.name));
    box.checked = on.has(pack.name);
    for (const field of item.querySelectorAll("input[data-slider]")) {
      const slider = pack.sliders.find((s) => s.name === field.dataset.slider);
      const value = String(values[pack.name]?.[slider.name] ?? slider.default);
      mark(field.closest(".l3, .slider").querySelector(".mark"), shown(field) !== value);
      if (field.type === "checkbox") field.checked = value === "1";
      else field.value = value;
      field.closest(".slider").fit();
    }
  }
  tally();
  lock();
  state.xbr = xbr;
  $("xbr-note").textContent = xbr.length ? `The loaded recipe also sets ${xbr.length} config.xbr `
    + `value${xbr.length > 1 ? "s" : ""}, which each build applies.` : "";
}

// Load a recipe (a share link's, or an AzurKit build's: a preset, already checked by the engine) into the page, marked,
// in place of the remembered setup, which it becomes (D915). Without a packs layer, the ticks stay as they are.
function load(preset, from) {
  const packs = preset.layers.find((layer) => layer.tool === "mods")?.recipe;
  const ticked = [...$("packs").querySelectorAll("input[data-pack]:checked")].map((box) => box.dataset.pack);
  setTo(new Set(packs ? Object.keys(packs) : ticked), packs ?? {},
        preset.layers.find((layer) => layer.tool === "data")?.recipe.ops ?? [], from);
  const rando = preset.layers.find((layer) => layer.tool === "randomizer")?.recipe;
  loadRando(rando, from);
  pick(rando ? "randomizer" : "patches");
  state.loaded = preset;
  remember();
  const made = preset.azurkit ? ` (made with AzurKit ${preset.azurkit})` : "";
  const cells = state.xbr.length ? ` and ${state.xbr.length} config.xbr edit${state.xbr.length > 1 ? "s" : ""}` : "";
  const seed = rando ? ` and the randomizer (seed ${rando.seed})` : "";
  say(`Loaded ${from}'s recipe${made}: ${packs ? Object.keys(packs).length : 0} packs${cells}${seed}, marked ●. `
      + "Pick your vanilla image, then Build.");
}

// The remembered setup, as the engine gives it back (sdk.restore): what still applies, and what doesn't, by name.
function restored({ ticked, values, xbr, dropped, randomizer }) {
  state.restoring = false;
  setTo(new Set(ticked), values, xbr);
  setRando(randomizer ?? randoDefaults());
  say(dropped.length ? `Restored your last setup, without ${dropped.join("; ")}`
    : `Restored your last setup: ${ticked.length} pack${ticked.length === 1 ? "" : "s"} on. Reset to defaults clears it.`);
  remember();   // what is left of it
  start();
}

// Reset to defaults: the packs on by default, every setting at its default, no config.xbr cell; the remembered setup
// forgotten (the next change is remembered again, so the status says what happened, not what is kept).
function reset() {
  setTo(new Set(state.packs.packs.filter((pack) => pack.default_on).map((pack) => pack.name)), {}, []);
  setRando(randoDefaults());
  state.loaded = null;
  unlinked();
  pick("patches");
  remember();
  say("Reset to the defaults: the packs on by default, every setting at its default, Randomize off; the remembered "
      + "setup is forgotten.");
}

// The page's address drops a link's #p= once the page no longer holds that recipe, so a reload restores the setup.
function unlinked() {
  if (!state.app && location.hash) history.replaceState(null, "", location.pathname + location.search);
}

// The share link: the engine makes the fragment of what the page holds (with the build's hashes when it is the
// page's current build); the link is shown, and copied where the browser lets it.
function share() {
  if (!state.ready) return say("AzurKit is still loading: try again in a moment", true);
  const randomizer = randoRecipe();
  state.engine.preset({ packs: chosen(), xbr: state.xbr, ...(randomizer ? { randomizer } : {}) },
                      state.build?.report ?? null);
}

function shared(fragment) {
  state.link = `${state.site ?? location.href.split("#")[0].split("?")[0]}${fragment}`;
  $("link").value = state.link;
  $("link-row").hidden = false;
  if (!state.app) history.replaceState(null, "", fragment);
  const copied = navigator.clipboard?.writeText(state.link);
  (copied ?? Promise.reject()).then(() => say("Link copied: it holds the recipe, never your image"),
                                    () => say("Copy the link below: it holds the recipe, never your image"));
}

function decoded(preset) {
  state.pending = null;
  load(preset, "the link");
}

// The picked image is an AzurKit build: offer its recipe (sdk.open_build checked the files it changed against it).
function opened(preset) {
  if (state.asked !== state.file) return;
  state.opened = preset;
  const packs = Object.keys(preset.layers.find((layer) => layer.tool === "mods")?.recipe ?? {}).length;
  const label = preset.base?.release === "europe" ? "Europe" : "USA";
  const seed = preset.layers.find((layer) => layer.tool === "randomizer")?.recipe.seed;
  $("picked").textContent = `◆ AzurKit build · ${label} · ${packs} packs${seed === undefined ? "" : ` · seed ${seed}`}: `
    + "load its recipe, then pick your vanilla image to build it again.";
  $("load-build").hidden = false;
}

function unopen() {
  state.opened = null;
  $("load-build").hidden = true;
}

// The engine is ready (the site's again after each build). The first time, the page draws the catalog and asks for the
// remembered setup back, unless a link brought a recipe (D915: the link wins); it is ready once that is back.
function ready(catalog, version) {
  if (!state.packs) {
    state.packs = catalog;
    renderTabs(catalog.tabs);
    renderPacks(catalog);
    renderRando(catalog.randomizer);
    state.tracker = tracker({ call: state.engine.call, app: state.app, say, kept: state.tracked, keep: keepTracked,
                              image: () => state.file });
    $("version").textContent = `AzurKit ${version}`;
    $("about-version").textContent = `This is AzurKit ${version}.`;
    if (!state.pending && state.remembered != null) {
      state.restoring = true;
      return state.engine.restore(state.remembered);
    }
  }
  start();
}

function start() {
  state.ready = true;
  busy(state.building);
  if (state.pending) state.engine.decode(state.pending);
  askVanilla();
  if (state.rando.waiting) askRando(state.rando.given);
}

function report(text, error = false) {
  busy(false);
  say(text, error);
}

function built(reply) {
  const { report: made, size } = reply;
  if (state.app) {
    state.build = { report: made, size, recipe: reply.recipe, out: reply.out };
    $("out-path").value = reply.out;
    $("out-row").hidden = state.dialogs;
  } else {
    const file = state.file;
    const parts = reply.segments.map((s) => s.kind === "copy" ? file.slice(s.offset, s.offset + s.size)
      : s.kind === "bytes" ? s.data : new Uint8Array(s.size));
    const blob = new Blob(parts, { type: "application/octet-stream" });
    if (blob.size !== size) return report(`The build's pieces make ${bytes(blob.size)}, not ${bytes(size)}`, true);
    state.build = { report: made, size, segments: reply.segments, blob };
    state.url = URL.createObjectURL(blob);
  }
  const changed = Object.keys(made.result), rz = made.randomizer;
  const verdict = !rz ? "" : ` · seed ${rz.seed} · ${rz.share} · ${rz.logic_verified ? "logic verified"
    : `⚠ logic unverified: ${rz.why_not[0]}${rz.why_not.length > 1 ? ` (+${rz.why_not.length - 1} more)` : ""}`}`;
  report(`Ready · ${made.label} · ${bytes(size)}${verdict}` + made.conflicts.map((c) => ` · conflict: ${c}`).join("")
         + made.notes.map((n) => ` · note: ${n}`).join("")
         + ` · changed: ${changed.length ? changed.join(", ") : "nothing"}`);   // the file list last: it runs long
  spoiler(made.spoiler ?? null);
  if (made.plan) state.tracker.open(made.plan);   // the Tracker view tracks the build's seed
}

function saved({ saved: done }) {
  state.saved = done;
  report(`Saved ${done.out} · ${bytes(done.size)} · sha256 ${done.sha256.slice(0, 12)}`);
}

async function saveInApp() {
  let out = $("out-path").value;
  if (state.dialogs) {
    out = await state.engine.choose("out", state.build.out).catch((error) => report(error.message, true));
    if (!out) return;
  }
  busy(true);
  state.saving = true;
  say("Saving…");
  state.poll = setInterval(async () => {
    const { done, total } = await state.engine.progress().catch(() => ({}));
    if (state.saving && total) say(`Saving… ${Math.floor((100 * done) / total)} %`);
  }, 400);
  state.engine.save(state.build.recipe, out);
}

function pickInApp(host) {
  state.app = true;
  state.dialogs = host.dialogs;
  $("iso").hidden = true;
  $("iso-row").hidden = false;
  $("iso-choose").hidden = !host.dialogs;
  $("iso-path").value = host.iso;
  $("save").textContent = host.dialogs ? "Save ISO…" : "Save";
  const picked = () => {
    forget();
    unopen();
    state.file = $("iso-path").value.trim() || null;
    $("picked").textContent = host.dialogs ? "Type the image's full path, or Choose… it."
      : "Type the image's full path: a browser can't tell AzurKit where a file is.";
    say("");
    busy(false);
    askVanilla();
    state.tracker?.draw();   // the tracker's maps are drawn from it, if they aren't yet
  };
  picked();
  $("iso-path").addEventListener("input", picked);
  $("iso-choose").addEventListener("click", async () => {
    const path = await state.engine.choose("iso", $("iso-path").value).catch((error) => say(error.message, true));
    if (path) {
      $("iso-path").value = path;
      picked();
    }
  });
}

// ---- The Randomizer tab (Step 4.2c1) ----
// Its options come from the catalog (sdk.catalog's randomizer: D144's defaults, the tiers, ceilings and fire levels,
// the item rows); the engine reads what they give (sdk.randomizer_settings): the share string, each skip a setting can
// turn on, what a build would leave unverified (the ⚠ line) and the preflight's refusal. The page holds the settings
// as a settings file's table in format /2 (each unticked row's category, as it is) and decides no plan.
const randoOptions = () => state.packs.randomizer;
const draw = () => String(crypto.getRandomValues(new Uint32Array(1))[0] % 1000000);   // a seed, 0-999999 (Modkit's)

function choices(select, values, tip) {
  select.replaceChildren(...values.map(([value, label]) => Object.assign(document.createElement("option"),
                                                                       { value: String(value), textContent: label })));
  if (tip) select.title = tip;
}

// A loaded setting's tier or ceiling that the tab doesn't offer (safe; ceiling 1) shows only while it is the one set.
function offered() {
  const { loaded } = randoOptions();
  for (const [key, select] of [["movement_tier", R("movement")], ["skip_ceiling", R("ceiling")]]) {
    for (const option of select.options) option.hidden = option.value === String(loaded[key]) && !option.selected;
  }
}

function renderRando(options) {
  choices(R("movement"), options.movement, options.tips.movement);
  choices(R("ceiling"), options.ceilings, options.tips.ceiling);
  choices(R("dark"), options.dark_fire.map((level) => [level, `Fire ${level}`]));
  R("cost-note").textContent = `vanilla ${options.obsidian_cost}`;   // D910
  // Each item row: its box, its icons (the page's own drawings), its name, how many the base game places, its note
  R("items").replaceChildren(...options.items.map(([category, label, note, count, icons]) => {
    const row = Object.assign(document.createElement("label"), { className: "item" });
    const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: Boolean(category) });
    if (category) box.dataset.category = category;
    else box.disabled = box.dataset.vanilla = true;
    const strip = Object.assign(document.createElement("span"), { className: "icons" });
    strip.append(...icons.map((icon) => Object.assign(document.createElement("span"), { className: `glyph ${icon}` })));
    row.append(box, strip, Object.assign(document.createElement("span"), { textContent: label }),
               Object.assign(document.createElement("span"), { className: "count", textContent: count.toLocaleString("en-US"),
                                                               title: "How many the base game places" }),
               Object.assign(document.createElement("span"), { textContent: note }));
    return row;
  }));
  setRando(randoDefaults());
}

function randoDefaults() {
  return { on: false, seed: R("seed").value || draw(), settings: randoOptions().defaults };
}

// The tab's settings as the build reads them: a settings file's table, its categories in the database's order, its
// toggles the skip list's picks and, for each pick a ticked skip group turns on that the ceiling doesn't, a true one
// (D258, Modkit's).
function randoSettings() {
  const { defaults, categories } = randoOptions();
  const kept = new Set([...R("items").querySelectorAll("input[data-category]")].filter((box) => !box.checked)
    .map((box) => box.dataset.category));
  const ceiling = Number(R("ceiling").value), overrides = { ...state.rando.overrides };
  for (const pick of byGroup()) {
    if (!(pick.id in overrides) && !pick.levels.every((level) => level <= ceiling)) overrides[pick.id] = true;
  }
  return { format: defaults.format, skip_ceiling: ceiling, movement_tier: R("movement").value,
           dark_fire: Number(R("dark").value), exclude_categories: categories.filter((c) => kept.has(c)),
           skip_override: Object.fromEntries(Object.entries(overrides).sort()) };
}

// D258: the picks the ticked skip groups turn on at the Movement tier: each of theirs rated at or below it (a batch,
// D275, once each of its in-logic variants is); none before the engine has given the groups.
function byGroup() {
  const level = (state.rando.view?.tiers ?? []).indexOf(R("movement").value) + 1;
  return (state.rando.view?.groups ?? []).filter((group) => state.rando.groups.has(group.id))
    .flatMap((group) => group.picks).filter((pick) => pick.levels.every((l) => l <= level));
}

// The skip groups' boxes (unticked by default), each with how many of its picks the Movement tier takes in.
function renderGroups() {
  const view = state.rando.view, level = (view?.tiers ?? []).indexOf(R("movement").value) + 1;
  R("groups").replaceChildren(...(view?.groups ?? []).map((group) => {
    const taken = group.picks.filter((pick) => pick.levels.every((l) => l <= level));
    const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: state.rando.groups.has(group.id),
                                                                 disabled: state.building || !R("on").checked });
    box.dataset.group = group.id;
    const row = Object.assign(document.createElement("label"), { className: "group", title: [
      `${taken.length} of these ${group.picks.length} at ${R("movement").selectedOptions[0]?.textContent ?? ""}:`,
      ...group.picks.map((p) => `${taken.includes(p) ? "☑" : "☐"} ${p.name}: ${p.rating}`)].join("\n") });
    row.append(box, group.label, Object.assign(document.createElement("span"), { className: "note",
                                                                                textContent: `${taken.length} of ${group.picks.length}` }));
    return row;
  }));
}

// The obsidian cost as the engine gets it: none at vanilla's (or an empty box), else the number or the text typed.
function randoCost() {
  const text = R("cost").value.trim(), cost = text ? typed(text) : randoOptions().obsidian_cost;
  return cost === randoOptions().obsidian_cost ? {} : { obsidian_cost: cost };
}

// The build's randomizer: the seed, the settings and the obsidian cost, or null while Randomize is off.
function randoRecipe() {
  if (!state.packs || !R("on").checked) return null;
  return { seed: R("seed").value.trim(), settings: randoSettings(), ...randoCost() };
}

// What the page remembers of the tab (D915): nothing at its defaults (off, D144's settings, vanilla's cost).
function randoSetup() {
  const settings = randoSettings(), cost = randoCost();
  const plain = !R("on").checked && !("obsidian_cost" in cost)
    && JSON.stringify(settings) === JSON.stringify(randoOptions().defaults);
  return plain ? null : { on: R("on").checked, seed: R("seed").value, settings,
                          ...(typeof cost.obsidian_cost === "number" ? cost : {}) };
}

// Set the tab to `rando` (the engine's: its settings as the tab holds them), marked ● where `from` (a link, a build)
// changed it; then ask the engine what they give.
function setRando({ on, seed, settings, obsidian_cost: cost }, from = null) {
  const before = JSON.stringify(randoSetup());
  state.rando.note = null;
  state.rando.groups.clear();   // shown exactly: its toggles the skip list's picks, no group ticked (Modkit's)
  R("on").checked = on;
  R("seed").value = seed;
  R("movement").value = settings.movement_tier;
  R("ceiling").value = String(settings.skip_ceiling);
  R("dark").value = String(settings.dark_fire);
  for (const box of R("items").querySelectorAll("input[data-category]")) {
    box.checked = !settings.exclude_categories.includes(box.dataset.category);
  }
  state.rando.overrides = { ...settings.skip_override };
  R("cost").value = String(cost ?? randoOptions().obsidian_cost);
  const mark = $("randomizer").querySelector(".on .mark");
  mark.textContent = from && JSON.stringify(randoSetup()) !== before ? "●" : "";
  mark.title = mark.textContent ? `Changed by ${from}` : "";
  offered();
  lockRando();
  askRando();
}

// A recipe's randomizer (a link's or a build's), or none: Randomize off. Its settings go through the engine first
// (a build's manifest holds its share string; a settings table of format /1 reads otherwise than the tab's).
function loadRando(rando, from) {
  if (!rando) {
    const mark = $("randomizer").querySelector(".on .mark");
    mark.textContent = R("on").checked ? "●" : "";
    R("on").checked = false;
    lockRando();
    return;
  }
  state.rando.load = { on: true, seed: rando.seed, obsidian_cost: rando.obsidian_cost, from };
  askRando({ ...(rando.share !== undefined ? { share: rando.share }   // a seed alone: D144's defaults
                 : { settings: rando.settings ?? randoOptions().defaults }),
             obsidian_cost: rando.obsidian_cost ?? randoOptions().obsidian_cost });
}

// Ask the engine what the tab's settings give (or `given`'s: a recipe's or a typed share string, whose settings become
// the tab's), once it is ready, while the tab shows or a recipe waits on it (the database loads at the first ask); only
// the latest ask's answer is taken.
function askRando(given = null) {
  clearTimeout(state.rando.later);
  const ticket = ++state.rando.ticket;
  if (given) state.rando.given = given;
  if (given) state.rando.asked = given.share ?? null;   // a share string loaded: its AZ-383 note's own
  if (!state.rando.given && state.tab !== "randomizer") return;
  state.rando.waiting = true;
  if (!state.ready || state.building) return;
  state.rando.later = setTimeout(() => {
    const asked = state.rando.given ?? { settings: randoSettings() };
    state.rando.given = null;
    state.engine.randomizer({ ...randoCost(), ...asked, packs: chosen() }, ticket);
  }, 100);
}

// The engine's answer: the settings it read (a loaded recipe's become the tab's), the share string, the skips, the
// facts and the ⚠ line; a refusal shows on the ⚠ line, the tab as it was.
function randoView(reply, ticket) {
  if (ticket !== state.rando.ticket) return;
  state.rando.waiting = false;
  if ("refused" in reply) {
    state.rando.load = null;
    return warn([reply.refused], true);
  }
  if (state.rando.load) {
    const { from, ...rest } = state.rando.load;
    state.rando.load = null;
    setRando({ ...rest, settings: reply.settings }, from);
    state.rando.note = reply.note;   // a loaded share's own (other movement sliders): warned until the tab is edited,
    state.rando.noted = state.rando.asked;   // or until the Patches tab's sliders give that share string again
    return;
  }
  if (state.rando.note && reply.share === state.rando.noted) state.rando.note = null;
  state.rando.view = reply;
  R("share").value = reply.share;
  R("held").textContent = `${reply.skips.length} turnable · ${reply.held} held (no setting turns one on)`;
  R("facts").textContent = `Accessibility: full · Victory: Spideyzar · Excluded: lock 10 + full-clear · `
    + `${reply.forfeitable} forfeitable`;
  renderSkips();
  renderGroups();
  const note = reply.note ?? state.rando.note;
  warn([...(reply.preflight ? [`The build refuses: ${reply.preflight}`] : []), ...(note ? [note] : []),
        ...reply.why_not.map((why) => `Logic unverified (flagged, not refused): ${why}`)], Boolean(reply.preflight));
  remember();
}

function warn(lines, error = false) {
  R("warn").hidden = !lines.length;
  R("warn").textContent = lines.map((line) => `⚠ ${line}`).join("\n");
  R("warn").classList.toggle("error", error);
}

// The skips a setting can turn on, filtered: each ticked when it is on (half when only some of a batch's variants are,
// by the ceiling), by the ceiling or by its own toggle, which a click sets and a click back to the ceiling's clears.
function renderSkips() {
  const filter = R("filter").value.trim().toLowerCase();
  const rows = (state.rando.view?.skips ?? []).filter((s) => !filter || `${s.name} ${s.id} ${s.rating}`.toLowerCase()
    .includes(filter));
  const grouped = new Set(byGroup().map((pick) => pick.id));
  R("skips").replaceChildren(...rows.map((skip) => {
    const toggle = state.rando.overrides[skip.id] ?? null, on = toggle ?? (grouped.has(skip.id) || skip.ceiling);
    const row = Object.assign(document.createElement("label"), { className: `skip${toggle === null ? "" : " toggled"}`,
                                                                 title: `${skip.name} (${skip.id}): ${skip.rating}` });
    const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: on === true,
                                                                 indeterminate: on === null });
    box.dataset.skip = skip.id;
    box.disabled = state.building || !R("on").checked;
    row.append(box, Object.assign(document.createElement("span"), { className: "name", textContent: skip.name }),
               Object.assign(document.createElement("span"), { className: "rating", textContent: skip.rating }),
               Object.assign(document.createElement("span"), { className: "by", textContent: toggle !== null
                                                                 ? "toggle" : grouped.has(skip.id) ? "group" : "ceiling" }));
    return row;
  }));
}

// A click turns a skip (a batch whole) the other way: by a toggle, or by none when the ceiling now gives that.
function toggleSkip(id) {
  const skip = state.rando.view.skips.find((s) => s.id === id);
  const def = byGroup().some((pick) => pick.id === id) || skip.ceiling;
  const toggle = state.rando.overrides[id] ?? null, turned = (toggle === null ? def : toggle) !== true;
  if (turned === def || (def === null && toggle === false)) delete state.rando.overrides[id];
  else state.rando.overrides[id] = turned;
}

// The tab's settings are locked (still readable) until Randomize is ticked, and while a build runs (D907).
function lockRando() {
  const off = state.building || !R("on").checked;
  R("on").disabled = state.building || !state.packs;
  for (const field of $("randomizer").querySelectorAll(".rando-top :is(input, select, button), #rando-share, "
    + "#rando-copy, #rando-filter, #rando-clear, #rando-items input[data-category], #rando-skips input, "
    + "#rando-groups input, #rando-load, #rando-save")) {
    if (field !== R("on")) field.disabled = off;
  }
}

// D144's settings files: Load settings… takes a file's settings (the engine reads it and names what it refuses);
// Save settings… writes the tab's (Modkit's --save-settings file): the site's download, the app's dialog or Downloads.
async function loadSettings() {
  const file = R("load").files[0];
  R("load").value = "";
  if (!file) return;
  state.rando.load = { on: R("on").checked, seed: R("seed").value, obsidian_cost: randoCost().obsidian_cost,
                       from: file.name };
  askRando({ file: await file.text() });
}

async function saveSettings() {
  const view = state.rando.view;
  if (!view) return;
  if (!state.app) {
    const url = URL.createObjectURL(new Blob([view.file], { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "settings.toml" });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    return say("Saving settings.toml: your browser's download shows it");
  }
  let out = null;
  if (state.dialogs) {
    out = await state.engine.choose("settings", "settings.toml").catch((error) => say(error.message, true));
    if (!out) return;
  }
  const reply = await state.engine.call("settings_file", { out, settings: randoSettings() });
  if ("refused" in reply) return say(reply.refused, true);
  say(`Saved the settings: ${reply.saved.out}`);
}

// The last randomized build's spoiler (Modkit's --spoiler file), viewed in the tab and saved as a text file: the
// site's download, or where the app's dialog (else beside the image it saves) says.
function spoiler(text) {
  state.spoiler = text;
  $("spoiler-view").disabled = $("spoiler-save").disabled = !text;
  $("spoiler-note").hidden = Boolean(text);
  if (!text) $("spoiler").hidden = true;
  $("spoiler").textContent = text ?? "";
  $("spoiler-view").textContent = $("spoiler").hidden ? "View" : "Hide";
}

async function saveSpoiler() {
  const stem = (state.app ? $("out-path").value.split(/[\\/]/).pop() : state.file.name).replace(/\.x?iso$/i, "")
    .replace(/ \(AzurKit\)$/, "");
  const name = `${stem} (AzurKit) spoiler.txt`;
  if (!state.app) {
    const url = URL.createObjectURL(new Blob([state.spoiler], { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    return say(`Saving ${name}: your browser's download shows it`);
  }
  let out = $("out-path").value.replace(/[^\\/]*$/, name);
  if (state.dialogs) {
    out = await state.engine.choose("spoiler", out).catch((error) => say(error.message, true));
    if (!out) return;
  }
  state.engine.spoiler(out);
}

// What the tracker keeps (its plan last tracked and the marks of the last plans): the site in this browser's storage,
// the app in its config (api/tracked). Its plans are the randomizer's own (names and numbers), never the image's.
const TRACKED = "azurkit.tracker";
function keepTracked(kept) {
  if (state.app) return state.engine.tracked(kept);
  try {
    localStorage.setItem(TRACKED, JSON.stringify(kept));
  } catch {}   // storage refused (a private window, say): the marks last this visit
}

function storedTracked() {
  try {
    const kept = JSON.parse(localStorage.getItem(TRACKED));
    return kept && typeof kept === "object" && kept.marks && typeof kept.marks === "object" ? kept : null;
  } catch {
    return null;
  }
}

// The Randomizer tab's two views: its settings, and the tracker.
function randoPane(view) {
  for (const id of ["settings", "tracker"]) $(`rando-view-${id}`).setAttribute("aria-selected", String(id === view));
  $("rando-settings").hidden = view !== "settings";
  $("tracker").hidden = view !== "tracker";
  if (view === "tracker") state.tracker?.draw();   // its maps, drawn from the image the first time they show
}

// Track this seed: the Settings view's seed and settings (their share string, with the Patches tab's movement
// sliders, so the plan is the one a build of them makes) planned by the engine, then tracked.
async function trackSeed() {
  const seed = R("seed").value.trim(), share = state.rando.view?.share;
  if (!seed || !share) return say("Set a seed on the Randomizer tab's Settings first", true);
  $("track-seed").disabled = true;
  say(`Planning seed ${seed} to track it…`);
  const reply = await state.engine.call("plan", { recipe: { seed, share } });
  $("track-seed").disabled = false;
  if ("refused" in reply) return say(reply.refused, true);
  state.tracker.open(reply.plan, `seed ${seed}`);
}

function randoEvents(changed) {
  for (const view of ["settings", "tracker"]) $(`rando-view-${view}`).addEventListener("click", () => randoPane(view));
  $("track-seed").addEventListener("click", trackSeed);
  const edited = () => {
    changed();
    state.rando.note = null;
    askRando();
  };
  R("on").addEventListener("change", () => {
    $("randomizer").querySelector(".on .mark").textContent = "";
    lockRando();
    edited();
  });
  for (const id of ["movement", "ceiling", "dark"]) {
    R(id).addEventListener("change", () => {
      offered();
      renderGroups();
      renderSkips();
      edited();
    });
  }
  R("items").addEventListener("change", edited);
  R("groups").addEventListener("change", (e) => {
    const id = e.target.dataset.group;
    if (e.target.checked) state.rando.groups.add(id);
    else state.rando.groups.delete(id);
    renderSkips();
    edited();
  });
  R("load").addEventListener("change", loadSettings);
  R("save").addEventListener("click", saveSettings);
  R("seed").addEventListener("input", changed);
  R("cost").addEventListener("input", edited);
  R("new").addEventListener("click", () => {
    R("seed").value = draw();
    changed();
  });
  R("share").addEventListener("change", () => {
    const text = R("share").value.trim();
    if (text && text !== state.rando.view?.share) {
      changed();
      state.rando.load = { on: R("on").checked, seed: R("seed").value, obsidian_cost: randoCost().obsidian_cost };
      askRando({ share: text });
    }
  });
  R("copy").addEventListener("click", () => {
    const copied = navigator.clipboard?.writeText(R("share").value);
    (copied ?? Promise.reject()).then(() => say("Share string copied"), () => say("Copy the share string from its box"));
  });
  R("filter").addEventListener("input", renderSkips);
  R("clear").addEventListener("click", () => {
    state.rando.overrides = {};
    edited();
  });
  R("skips").addEventListener("change", (e) => {
    toggleSkip(e.target.dataset.skip);
    renderSkips();
    edited();
  });
  $("spoiler-view").addEventListener("click", () => {
    $("spoiler").hidden = !$("spoiler").hidden;
    $("spoiler-view").textContent = $("spoiler").hidden ? "View" : "Hide";
  });
  $("spoiler-save").addEventListener("click", saveSpoiler);
}

async function main() {
  if (window.top !== window.self) return stop("AzurKit doesn't run inside another page: open it on its own.");
  if (navigator.serviceWorker?.controller) return stop("A service worker controls this page: AzurKit won't run.");
  theme(document.documentElement.dataset.theme);   // theme.js's
  $("theme").addEventListener("click", () => theme(state.theme === "light" ? "dark" : "light", true));
  document.addEventListener("securitypolicyviolation", (e) => {
    state.violations.push(`page: ${e.violatedDirective} ${e.blockedURI}`);
    say(`The page's security policy refused ${e.violatedDirective}`, true);
  });
  let host;
  try {
    const reply = await fetch("host.json", { cache: "no-store" });
    if (!reply.ok) throw new Error(`host.json: HTTP ${reply.status}`);
    host = await reply.json();
  } catch (error) {
    return say(`AzurKit didn't load: ${error.message}`, true);
  }
  const callbacks = { ready, built, saved, vanilla, opened, shared, decoded, restored, rando: randoView,
                      refused: ({ message }) => report(message, true), failed: (message) => report(message, true) };
  if (location.hash.startsWith("#p=")) state.pending = location.hash;
  state.site = host.site ?? null;
  if (host.engine === "app") {
    state.engine = appEngine(host, callbacks);
    state.remembered = host.setup ?? null;
    state.kept = state.remembered && JSON.stringify(state.remembered);
    state.tracked = host.tracker ?? null;
    pickInApp(host);
    theme(host.theme);
  } else if (!("WebAssembly" in window) || !("Worker" in window)) {
    return stop("This browser can't run AzurKit (it needs WebAssembly and workers): use the desktop app.");
  } else {
    state.engine = siteEngine(callbacks);
    state.remembered = stored();
    state.tracked = storedTracked();
    $("iso").addEventListener("change", () => {
      forget();
      unopen();
      state.file = $("iso").files[0] ?? null;
      $("picked").textContent = state.file ? `${state.file.name} · ${bytes(state.file.size)}` : "";
      say("");
      busy(false);
      askVanilla();
      state.tracker?.draw();   // the tracker's maps are drawn from it, if they aren't yet
    });
  }

  const changed = () => {
    forget();
    unlinked();
    clearTimeout(state.later);
    state.later = setTimeout(remember, 250);
  };
  $("packs").addEventListener("change", () => {
    changed();
    tally();
    lock();
  });
  $("packs").addEventListener("input", changed);
  addEventListener("pagehide", remember);
  $("reset").addEventListener("click", reset);
  $("packs").addEventListener("toggle", place, true);   // a group's fold: "toggle" doesn't bubble
  addEventListener("resize", place);
  $("share").addEventListener("click", share);
  $("load-build").addEventListener("click", () => {
    $("load-build").hidden = true;
    load(state.opened, "your build");
  });
  $("build").addEventListener("click", () => {
    const randomizer = randoRecipe();
    if (randomizer && !randomizer.seed) return say("Type a seed on the Randomizer tab, or press New", true);
    forget();
    if (!state.app) state.ready = false;   // the site's engine is replaced after each build
    busy(true);
    say(randomizer ? "Checking your image, planning the seed and building…" : "Checking your image and building…");
    state.sent = chosen();
    state.engine.build(state.file, state.sent, state.xbr, randomizer);
  });
  randoEvents(changed);
  $("cancel").addEventListener("click", () => {
    if (!state.app) state.ready = false;
    state.engine.cancel();
    if (state.saving) return say("Cancelling…");
    busy(false);
    say("Cancelled");
  });
  $("save").addEventListener("click", () => {
    if (state.app) return saveInApp();
    const a = Object.assign(document.createElement("a"), {
      href: state.url, download: `${state.file.name.replace(/\.x?iso$/i, "")} (AzurKit).iso` });
    document.body.append(a);
    a.click();
    a.remove();
    say(`Saving ${a.download} (${bytes(state.build.size)}): your browser's download shows its progress`);
  });
}

main();
