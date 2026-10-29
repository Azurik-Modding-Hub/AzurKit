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
const $ = (id) => document.getElementById(id);
const state = { engine: null, app: false, dialogs: false, ready: false, building: false, saving: false, file: null,
                packs: null, sent: null, build: null, url: null, saved: null, poll: null, violations: [],
                vanilla: null, asked: null, xbr: [], link: null, pending: null, loaded: null, opened: null,
                site: null, theme: "dark", tab: null };
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
function siteEngine({ ready, built, refused, failed, vanilla, opened, shared, decoded }) {
  let worker = null, loaded = false;
  const start = () => {
    loaded = false;
    const entry = new URL("worker.mjs", location.href).href;
    const url = URL.createObjectURL(new Blob([`import ${JSON.stringify(entry)};\n`], { type: "text/javascript" }));
    worker = new Worker(url, { type: "module" });
    worker.onmessage = ({ data }) => {
      if (data.type === "ready") {
        URL.revokeObjectURL(url);
        loaded = true;
        ready(data.catalog, data.version);
      } else if (data.type === "vanilla") {
        const { type, ...read } = data;
        vanilla(read);
      } else if (data.type === "opened") {
        opened(data.preset);
      } else if (data.type === "preset") {
        shared(data.fragment);
      } else if (data.type === "decoded") {
        decoded(data.preset);
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
    build: (file, packs, xbr) => worker.postMessage({ type: "build", file, packs, xbr }),
    vanilla: (file) => worker.postMessage({ type: "vanilla", file }),
    preset: (recipe, report) => worker.postMessage({ type: "preset", recipe, report }),
    decode: (text) => worker.postMessage({ type: "decode", text }),
    cancel: restart,
  };
}

// The app's engine: azurkit.sdk on CPython behind this launch's server (azurkit.app), the same in the app's window
// and in a browser. The page posts JSON to it, and a refusal comes back as {refused}. A build's reply that arrives
// after Cancel is dropped; a save's is awaited, since the server says whether it wrote anything.
function appEngine(host, { ready, built, refused, failed, saved, vanilla, opened, shared, decoded }) {
  let ticket = 0;
  const post = async (path, body) => {
    const reply = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
                                      body: JSON.stringify(body) });
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
    build: (iso, packs, xbr) => run("api/build", { iso, packs, xbr }, built),
    vanilla: (iso) => post("api/vanilla", { iso }).then((read) => "refused" in read
      || ("opened" in read ? opened(read.opened) : vanilla(read))).catch(() => {}),
    preset: (recipe, report) => ask("api/preset", { recipe, report }, (reply) => shared(reply.fragment)),
    decode: (text) => ask("api/decode", { text }, (reply) => decoded(reply.preset)),
    save: (recipe, out) => run("api/save", { recipe, out }, saved),
    progress: async () => (await fetch("api/progress", { cache: "no-store" })).json(),
    choose: async (kind, path) => (await post("api/choose", { kind, path })).path ?? null,
    theme: (name) => post("api/theme", { theme: name }).catch(() => {}),   // remembering is a convenience
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
  $("iso").disabled = on || !state.packs;
  for (const id of ["iso-path", "iso-choose", "out-path"]) $(id).disabled = on;
  $("save").disabled = on || !state.build;
  $("cancel").hidden = !on;
  lock();
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
}

// Load a recipe (a share link's, or an AzurKit build's: a preset, already checked by the engine) into the page:
// tick exactly its packs, set their sliders (the others to their defaults), keep its config.xbr cells for the build,
// and mark ● each tick and value it changed; its packs' settings unlock, the others' lock (D907). It never starts a
// build.
function load(preset, from) {
  const packs = preset.layers.find((layer) => layer.tool === "mods")?.recipe;
  const mark = (element, on) => {
    element.textContent = on ? "●" : "";
    element.title = on ? `Changed by ${from}` : "";
  };
  forget();
  for (const item of $("packs").querySelectorAll(".pack")) {
    const box = item.querySelector("input[data-pack]");
    const pack = state.packs.packs.find((p) => p.name === item.dataset.pack);
    const on = packs ? pack.name in packs : box.checked;
    mark(item.querySelector(".name .mark"), box.checked !== on);
    box.checked = on;
    for (const field of item.querySelectorAll("input[data-slider]")) {
      const slider = pack.sliders.find((s) => s.name === field.dataset.slider);
      const value = String(packs?.[pack.name]?.[slider.name] ?? slider.default);
      mark(field.closest(".l3, .slider").querySelector(".mark"), shown(field) !== value);
      if (field.type === "checkbox") field.checked = value === "1";
      else field.value = value;
      field.closest(".slider").fit();
    }
  }
  tally();
  lock();
  pick("patches");
  state.xbr = preset.layers.find((layer) => layer.tool === "data")?.recipe.ops ?? [];
  state.loaded = preset;
  const made = preset.azurkit ? ` (made with AzurKit ${preset.azurkit})` : "";
  const cells = state.xbr.length ? ` and ${state.xbr.length} config.xbr edit${state.xbr.length > 1 ? "s" : ""}` : "";
  $("xbr-note").textContent = state.xbr.length ? `The loaded recipe also sets ${state.xbr.length} config.xbr `
    + `value${state.xbr.length > 1 ? "s" : ""}, which each build applies.` : "";
  say(`Loaded ${from}'s recipe${made}: ${packs ? Object.keys(packs).length : 0} packs${cells}, marked ●. `
      + "Pick your vanilla image, then Build.");
}

// The share link: the engine makes the fragment of what the page holds (with the build's hashes when it is the
// page's current build); the link is shown, and copied where the browser lets it.
function share() {
  if (!state.ready) return say("AzurKit is still loading: try again in a moment", true);
  state.engine.preset({ packs: chosen(), xbr: state.xbr }, state.build?.report ?? null);
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
  $("picked").textContent = `◆ AzurKit build · ${label} · ${packs} packs: load its recipe, then pick your vanilla `
    + "image to build it again.";
  $("load-build").hidden = false;
}

function unopen() {
  state.opened = null;
  $("load-build").hidden = true;
}

function ready(catalog, version) {
  state.ready = true;
  if (!state.packs) {
    state.packs = catalog;
    renderTabs(catalog.tabs);
    renderPacks(catalog);
    $("version").textContent = `AzurKit ${version}`;
    $("about-version").textContent = `This is AzurKit ${version}.`;
  }
  busy(state.building);
  if (state.pending) state.engine.decode(state.pending);
  askVanilla();
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
  const changed = Object.keys(made.result);
  report(`Ready · ${made.label} · ${bytes(size)} · changed: ${changed.length ? changed.join(", ") : "nothing"}`
         + made.conflicts.map((c) => ` · conflict: ${c}`).join("") + made.notes.map((n) => ` · note: ${n}`).join(""));
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
  const callbacks = { ready, built, saved, vanilla, opened, shared, decoded,
                      refused: ({ message }) => report(message, true), failed: (message) => report(message, true) };
  if (location.hash.startsWith("#p=")) state.pending = location.hash;
  state.site = host.site ?? null;
  if (host.engine === "app") {
    state.engine = appEngine(host, callbacks);
    pickInApp(host);
    theme(host.theme);
  } else if (!("WebAssembly" in window) || !("Worker" in window)) {
    return stop("This browser can't run AzurKit (it needs WebAssembly and workers): use the desktop app.");
  } else {
    state.engine = siteEngine(callbacks);
    $("iso").addEventListener("change", () => {
      forget();
      unopen();
      state.file = $("iso").files[0] ?? null;
      $("picked").textContent = state.file ? `${state.file.name} · ${bytes(state.file.size)}` : "";
      say("");
      busy(false);
      askVanilla();
    });
  }

  $("packs").addEventListener("change", () => {
    forget();
    tally();
    lock();
  });
  $("packs").addEventListener("input", forget);
  $("packs").addEventListener("toggle", place, true);   // a group's fold: "toggle" doesn't bubble
  addEventListener("resize", place);
  $("share").addEventListener("click", share);
  $("load-build").addEventListener("click", () => {
    $("load-build").hidden = true;
    load(state.opened, "your build");
  });
  $("build").addEventListener("click", () => {
    forget();
    if (!state.app) state.ready = false;   // the site's engine is replaced after each build
    busy(true);
    say("Checking your image and building…");
    state.sent = chosen();
    state.engine.build(state.file, state.sent, state.xbr);
  });
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
