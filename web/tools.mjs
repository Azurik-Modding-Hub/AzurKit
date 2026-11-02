// The Tools tab (Step 4.7c, D986; D919's list): the image you picked, its files, recipes and reports, on the site and
// in the app alike (D882). Your image: its release, size and kind (vanilla, an AzurKit build with its version and
// layers, or modded with the first file that differs) and how much of it the gate checked; Verify every file (the
// engine's gate against the release's manifest, its bar the bottom bar's, then kept by the image's stamp, so again
// it reads nothing: core/gate.py); its file list with a name filter; Extract a file (the site: a slice of your own
// File as a download, no copy; the app: a new file where its dialog says, never the image or iso/, D36). Recipes and
// files, no image needed: Open a build… (any AzurKit build, its recipe: Load it, Save its mods file, and a randomized
// one's Track this build: the tracker on its own plan, replayed from its seed and share string), Load a mods
// file…, Save the setup as a mods file…, a plan file's spoiler (View, Save) and the last build's report (View, Save).
// AzurKit's storage: what it keeps on this computer, by name, and Clear (the site: its own named keys and databases
// in this browser; the app: the named entries its engine lists, never an image or the folder, SEC-10). Everything
// that waits for an image is greyed with the line that says so until one is picked (D979). The engine decides every
// answer; this page asks and draws what comes back, through textContent only (the CSP: no eval).
//
// app.mjs makes it with tools({...}) once the engine is ready (index.html's #tools panel) and tells it when the image
// changes and a build is made or saved; the hosts answer its asks (the site's worker, the app's api/<ask>).
// tools({root, call, app, say, image, out, pick, setup, load}): root the panel; call(type, body) the engine's ask, its
// reply or {refused}; app whether the host is the app; say(text, error) the status line; image() the picked image
// (the site's File, the app's path) or null; out(name, kind) (the app's) where a file the tab saves goes: a path (its
// save dialog's), "" (no dialogs: the engine's place, the Downloads folder) or null (the dialog cancelled); pick()
// (the app's, with dialogs) an AzurKit build's path from its open dialog, or null; setup() the page's recipe now (what
// its share link and mods file carry: packs, xbr, randomizer, character); load(preset, from) sets the page to a
// preset; track(preset, from) tracks a randomized build's plan. The asks (body -> reply), where the site's worker
// mounts `file` (or `build`) and hands its path to the
// engine as the app's `iso`:
//   info         {iso | file}                -> {release, label, size, kind, whole, version?, layers?, differs?}
//   verify_all   {iso | file}                -> {release, label, whole: true}; refused: the first file that differs
//   files        {iso | file}                -> {files: [[path, offset, size]]}
//   extract      {iso, path, out}  (the app) -> {out, size, sha256}
//   open         {iso | build}  (a build)    -> {preset}
//   mods_file    {text}                      -> {preset}; {recipe | preset} -> {text} (the site), with out (the app)
//                                               -> {out, size}
//   plan_spoiler {plan}                      -> {lines}
//   report       {text, out, name} (the app) -> {out, size}: a report or spoiler the tab shows, as a new file
//   storage      {clear?}  (the app)         -> {entries: [{name, what, size}], cleared?}
// It returns {open(), imaged(), built(report, saved?), state}: open when the tab shows, imaged when the picked image
// changes, built after each build (its report, sdk.image's) and each save ({out, size, sha256}).

import { listed, sweep } from "./outputs.mjs";

export const CHOOSE = "Choose your image first (1.)";   // D979's line on what waits for an image
export const VANILLA = "Only a vanilla image is checked against its release";   // Verify, for another image
export const MODS = "AzurKit mods.json";

// What the site keeps in this browser, by name: Clear removes these and nothing else.
export const KEPT = {
  local: [["azurkit.setup", "Your setup (packs, settings and choices)"],
          ["azurkit.tracker", "The tracker's plans and marks"],
          ["azurkit.content_source", "Where community content comes from"],
          ["azurkit.show_objects", "Whether the Characters tab lists objects"],
          ["azurkit.theme", "The light or dark theme"]],
  databases: [["azurkit-stamp", "Your image's check (its files' sha256)"],
              ["azurkit-snapshot", "The engine's quick start (no image in it)"],
              ["azurkit-content", "Installed community content"]],
};

const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
export const bytes = (n) => `${n.toLocaleString("en-US")} B`;
export const sized = (n) => n >= 1e9 ? `${(n / 1e9).toFixed(2)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB`
  : n >= 1e3 ? `${(n / 1e3).toFixed(1)} KB` : `${n} B`;
const named = (path) => path.split(/[\\/]/).pop();

// The files whose path holds every word of the filter, any case, in the list's order.
export function filtered(files, filter) {
  const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
  return words.length ? files.filter(([path]) => words.every((word) => path.toLowerCase().includes(word))) : files;
}

// What the image is, in one line: its release, size and kind, and how much of it the gate checked.
export function imageLine(info) {
  const kind = info.kind === "build"
    ? `an AzurKit build${info.version ? ` (AzurKit ${info.version})` : ""}${info.layers?.length
      ? `: ${info.layers.join(", ")}` : ""}`
    : info.kind === "modded" ? `modded (${info.differs ?? "a file differs"})` : "vanilla";
  const checked = info.kind !== "vanilla" ? "" : info.whole ? " · every file checked" : " · its build files checked";
  return `${info.label} · ${bytes(info.size)} · ${kind}${checked}`;
}

// A build's report as text (Modkit's build log): its release, each layer's sites and bytes, every conflict (D28)
// and note, the randomizer's verdict, each file it changed, and where it was saved with its sha256.
export function reportText(report, saved = null) {
  const lines = [`AzurKit build · ${report.label}`];
  for (const layer of report.layers ?? []) lines.push(`layer ${layer.id}: ${layer.sites} sites, ${bytes(layer.bytes)}`);
  for (const conflict of report.conflicts ?? []) lines.push(`conflict: ${conflict}`);
  for (const note of report.notes ?? []) lines.push(`note: ${note}`);
  const verdict = report.randomizer;
  if (verdict) {
    lines.push(`randomizer: seed ${verdict.seed} · logic ${verdict.logic_verified ? "verified" : "not verified"}`);
    for (const why of verdict.why_not ?? []) lines.push(`  why not: ${why}`);
  }
  for (const [path, sha] of Object.entries(report.result ?? {})) lines.push(`changed ${path}: sha256 ${sha}`);
  if (saved) lines.push(`saved ${saved.out} · ${bytes(saved.size)} · sha256 ${saved.sha256}`);
  return `${lines.join("\n")}\n`;
}

function download(blob, name) {   // the site's: the browser's download of a Blob (a File's slice is no copy)
  const url = URL.createObjectURL(blob);
  const a = el("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export function tools({ root, call, app, say, image, out, pick = null, setup, load, track }) {
  const t = { info: null, files: null, opened: null, plan: null, spoiler: null, report: null, saved: null,
              shown: false, ticket: 0, opening: 0, refused: null };
  const asked = () => app ? { iso: image() } : { file: image() };

  // The panel, drawn once.
  const button = (id, text, onclick) => el("button", { id, type: "button", textContent: text, onclick });
  const line = (id, text = "") => el("p", { id, className: "note", textContent: text });
  const chooser = (id, accept, onchange) => el("input", { id, type: "file", accept, onchange });
  const ui = {
    imageLine: line("tools-image-line", CHOOSE),
    verify: button("tools-verify", "Verify every file", verify),
    list: button("tools-list", "Show its files", list),
    filter: el("input", { id: "tools-filter", type: "search", placeholder: "Filter by name",
                          oninput: () => drawFiles() }),
    count: el("span", { id: "tools-count", className: "note" }),
    rows: el("tbody", { id: "tools-rows" }),
    openFile: app ? null : chooser("tools-open-file", ".iso,.xiso", (event) => opened(event.target)),
    openPath: app ? el("input", { id: "tools-open-path", type: "text", placeholder: "An AzurKit build's path" })
      : null,
    openLine: line("tools-open-line"),
    openLoad: button("tools-open-load", "Load it", () => t.opened && load(t.opened.preset, t.opened.from)),
    openSave: button("tools-open-save", "Save its mods file", () => t.opened && saveMods({ preset: t.opened.preset })),
    openTrack: button("tools-open-track", "Track this build", () => t.opened && track(t.opened.preset, t.opened.from)),
    mods: chooser("tools-mods-file", ".json,.txt", (event) => loadMods(event.target)),
    modsSave: button("tools-mods-save", "Save the setup as a mods file…", () => saveMods({ recipe: setup() })),
    plan: chooser("tools-plan-file", ".json", (event) => readPlan(event.target)),
    planView: button("tools-plan-view", "View", () => shown(ui.planText, ui.planView)),
    planSave: button("tools-plan-save", "Save", () => saveText(t.spoiler, `${t.plan.stem} spoiler.txt`)),
    planText: el("pre", { id: "tools-plan-text", hidden: true }),
    reportView: button("tools-report-view", "View", () => shown(ui.reportText, ui.reportView)),
    reportSave: button("tools-report-save", "Save", () => saveText(reportText(t.report, t.saved),
                                                                   "AzurKit build report.txt")),
    reportLine: line("tools-report-line", "Build first to see its report."),
    reportText: el("pre", { id: "tools-report-text", hidden: true }),
    storage: el("tbody", { id: "tools-storage" }),
    clear: button("tools-clear", "Clear", clear),
    storageLine: line("tools-storage-line"),
  };
  ui.files = el("div", { id: "tools-files", hidden: true }, el("p", {}, ui.filter, " ", ui.count),
                el("table", {}, el("thead", {}, el("tr", {}, el("th", { textContent: "File" }),
                                                   el("th", { textContent: "Size" }), el("th"))), ui.rows));
  root.replaceChildren(
    el("h2", { textContent: "Your image" }), ui.imageLine, el("p", {}, ui.verify, " ", ui.list), ui.files,
    el("h2", { textContent: "Recipes and files" }),
    el("p", {}, "Open a build… ", ...(app ? [ui.openPath, " ", button("tools-open", "Open", () => opened(null)),
                                            ...(pick ? [" ", button("tools-open-choose", "Choose…", choosing)] : [])]
                                         : [ui.openFile])),
    ui.openLine, el("p", {}, ui.openLoad, " ", ui.openSave, " ", ui.openTrack),
    el("p", {}, el("label", {}, "Load a mods file… ", ui.mods), " ", ui.modsSave),
    el("p", {}, el("label", {}, "A plan file's spoiler ", ui.plan), " ", ui.planView, " ", ui.planSave), ui.planText,
    el("p", {}, "The last build's report ", ui.reportView, " ", ui.reportSave), ui.reportLine, ui.reportText,
    el("h2", { textContent: "AzurKit's storage" }),
    el("table", {}, el("thead", {}, el("tr", {}, el("th", { textContent: "What" }), el("th", { textContent: "Size" }))),
       ui.storage),
    el("p", {}, ui.clear), ui.storageLine);

  // D979: what waits for an image is greyed with the line that says so (an image the engine refused: its refusal;
  // Verify: a vanilla image); the opened build, the plan and the report wait for theirs.
  function lines() {
    const none = !image() || !t.info, why = !image() ? CHOOSE : t.refused ?? (t.info ? "" : "Reading your image…");
    for (const node of [ui.verify, ui.list, ui.filter]) {
      node.disabled = none;
      node.title = why;
    }
    if (t.info && t.info.kind !== "vanilla") {
      ui.verify.disabled = true;
      ui.verify.title = VANILLA;
    }
    if (none) ui.files.hidden = true;
    ui.list.textContent = ui.files.hidden ? "Show its files" : "Hide its files";
    ui.openLoad.disabled = ui.openSave.disabled = !t.opened;
    const seeded = t.opened?.preset.layers.some((layer) => layer.tool === "randomizer");
    ui.openTrack.disabled = !seeded;
    ui.openTrack.title = seeded ? "The tracker on this build's own plan (its seed and share string)"
      : t.opened ? "This build isn't randomized: it has no plan to track" : "Open a randomized build first";
    ui.planView.disabled = ui.planSave.disabled = !t.spoiler;
    ui.reportView.disabled = ui.reportSave.disabled = !t.report;
    ui.reportLine.hidden = Boolean(t.report);
  }

  function shown(text, toggle) {
    text.hidden = !text.hidden;
    toggle.textContent = text.hidden ? "View" : "Hide";
  }

  // The image: what it is, asked once a picked image (and again once it changes).
  async function info() {
    const ticket = ++t.ticket;
    t.info = t.files = t.refused = null;
    ui.rows.replaceChildren();
    ui.imageLine.textContent = image() ? "Reading your image…" : CHOOSE;
    lines();
    if (!image()) return;
    const reply = await call("info", asked());
    if (ticket !== t.ticket) return;
    if ("refused" in reply) {
      ui.imageLine.textContent = t.refused = reply.refused;
      return lines();
    }
    t.info = reply;
    ui.imageLine.textContent = imageLine(reply);
    lines();
  }

  async function verify() {
    const ticket = t.ticket;
    ui.verify.disabled = true;
    const reply = await call("verify_all", asked());
    if (ticket !== t.ticket) return;
    if ("refused" in reply) {
      say(reply.refused, true);
      ui.imageLine.textContent = `${imageLine(t.info)} · ${reply.refused}`;
    } else {
      t.info = { ...t.info, whole: true };
      ui.imageLine.textContent = imageLine(t.info);
      say(`Every file of your ${reply.label} image matches its release's`);
    }
    lines();
  }

  async function list() {
    if (!ui.files.hidden) {   // a second click collapses them; the filter's text stays
      ui.files.hidden = true;
      return lines();
    }
    const ticket = t.ticket;
    if (!t.files) {
      ui.list.disabled = true;
      const reply = await call("files", asked());
      if (ticket !== t.ticket) return;
      if ("refused" in reply) {
        lines();
        return say(reply.refused, true);
      }
      t.files = reply.files;
    }
    ui.files.hidden = false;
    lines();
    drawFiles();
  }

  function drawFiles() {
    if (!t.files) return;
    const matching = filtered(t.files, ui.filter.value), rows = document.createDocumentFragment();
    for (const entry of matching) {
      const [path, , size] = entry;
      rows.append(el("tr", {}, el("td", { textContent: path }), el("td", { textContent: sized(size) }),
                     el("td", {}, el("button", { type: "button", textContent: "Extract",
                                                 onclick: () => extract(entry) }))));
    }
    ui.rows.replaceChildren(rows);
    const count = (n) => n.toLocaleString("en-US");
    ui.count.textContent = matching.length === t.files.length ? `${count(t.files.length)} files`
      : `${count(matching.length)} of ${count(t.files.length)} files`;
  }

  // Extract a file: the site downloads its slice of your File (no copy); the app writes it where its dialog says.
  async function extract([path, at, size]) {
    if (!app) {
      download(image().slice(at, at + size), named(path));
      return say(`Saving ${named(path)} (${bytes(size)}): your browser's download shows it`);
    }
    const where = await out(named(path), "extract");
    if (where === null) return;
    const reply = await call("extract", { iso: image(), path, out: where || null });
    if ("refused" in reply) return say(reply.refused, true);
    say(`Saved ${reply.out} · ${bytes(reply.size)} · sha256 ${reply.sha256.slice(0, 12)}`);
  }

  // Open a build…: any AzurKit build's recipe (the site: a File you pick; the app: a path), to load or save.
  async function opened(input) {
    const file = input?.files?.[0] ?? null;
    if (input) input.value = "";
    const path = app ? ui.openPath.value.trim() : null;
    if (!(file || path)) return;
    const ticket = ++t.opening;   // the last open asked is the one shown
    t.opened = null;
    ui.openLine.textContent = "Reading the build…";
    lines();
    const reply = await call("open", app ? { iso: path } : { build: file });
    if (ticket !== t.opening) return;
    if ("refused" in reply) {
      ui.openLine.textContent = reply.refused;
      return lines();
    }
    const { preset } = reply, from = file ? file.name : named(path);
    const recipe = (tool) => preset.layers.find((layer) => layer.tool === tool)?.recipe;
    const packs = Object.keys(recipe("mods") ?? {}).length, seed = recipe("randomizer")?.seed;
    const character = recipe("characters"), ops = recipe("data")?.ops?.length ?? 0;
    t.opened = { preset, from };
    ui.openLine.textContent = [`${from}: ${preset.base?.release === "europe" ? "Europe" : "USA"}`,
                               `${packs} packs`, ...(seed === undefined ? [] : [`seed ${seed}`]),
                               ...(character ? [`wears ${character.species ?? character.variant ?? "a variant"}`] : []),
                               ...(ops ? [`${ops} data edits`] : []),
                               ...(preset.azurkit ? [`made with AzurKit ${preset.azurkit}`] : [])].join(" · ");
    lines();
  }

  async function choosing() {
    const path = await pick();
    if (!path) return;
    ui.openPath.value = path;
    opened(null);
  }

  // Mods files (Q268): the engine reads one (naming what it refuses) and writes the setup's, or an opened build's.
  async function loadMods(input) {
    const file = input.files[0];
    input.value = "";
    if (!file) return;
    const reply = await call("mods_file", { text: await file.text() });
    if ("refused" in reply) return say(`${file.name}: ${reply.refused}`, true);
    load(reply.preset, file.name);
  }

  async function saveMods(given) {
    if (!app) {
      const reply = await call("mods_file", given);
      if ("refused" in reply) return say(reply.refused, true);
      download(new Blob([reply.text], { type: "application/json" }), MODS);
      return say(`Saving ${MODS}: your browser's download shows it`);
    }
    const where = await out(MODS, "mods");
    if (where === null) return;
    const reply = await call("mods_file", { ...given, out: where || null });
    if ("refused" in reply) return say(reply.refused, true);
    say(`Saved the mods file: ${reply.out}`);
  }

  // A plan file's spoiler: the engine's, of the plan (a plan from another database or an edited one is refused).
  async function readPlan(input) {
    const file = input.files[0];
    input.value = "";
    if (!file) return;
    t.plan = t.spoiler = null;
    ui.planText.hidden = true;
    ui.planView.textContent = "View";
    lines();
    let plan;
    try {
      plan = JSON.parse(await file.text());
    } catch {
      return say(`${file.name} is not a plan file (it isn't JSON)`, true);
    }
    const reply = await call("plan_spoiler", { plan });
    if ("refused" in reply) return say(`${file.name}: ${reply.refused}`, true);
    t.plan = { stem: file.name.replace(/\.json$/i, "") };
    t.spoiler = `${reply.lines.join("\n")}\n`;
    ui.planText.textContent = t.spoiler;
    lines();
  }

  // A text the tab shows (a spoiler, a report): the site's download; the app writes it as a new file.
  async function saveText(text, name) {
    if (!app) {
      download(new Blob([text], { type: "text/plain" }), name);
      return say(`Saving ${name}: your browser's download shows it`);
    }
    const where = await out(name, "report");
    if (where === null) return;
    const reply = await call("report", { text, out: where || null, name });
    if ("refused" in reply) return say(reply.refused, true);
    say(`Saved ${reply.out}`);
  }

  // AzurKit's storage, by name: the site's own keys and databases here; the app's from its engine (SEC-10).
  async function storage() {
    const rows = [];
    if (app) {
      const reply = await call("storage", {});
      if ("refused" in reply) return say(reply.refused, true);
      rows.push(...reply.entries.map(({ what, size }) => [what, size]));
    } else {
      for (const [key, what] of KEPT.local) {
        let value = null;
        try {
          value = localStorage.getItem(key);
        } catch {}   // storage refused (a private window): nothing kept
        if (value !== null) rows.push([what, new Blob([value]).size]);
      }
      const have = await indexedDB.databases?.().catch(() => null);
      for (const [name, what] of KEPT.databases) {
        if (!have || have.some((db) => db.name === name)) rows.push([what, null]);
      }
      const files = await listed();
      if (files.length) rows.push(["Built images' files, until they're saved", files.reduce((n, f) => n + f.size, 0)]);
      const usage = (await navigator.storage?.estimate?.().catch(() => null))?.usage;
      ui.storageLine.textContent = usage == null ? "" : `This site keeps ${sized(usage)} in this browser in all.`;
    }
    const row = ([what, size]) => el("tr", {}, el("td", { textContent: what }),
                                     el("td", { textContent: size == null ? "" : sized(size) }));
    ui.storage.replaceChildren(...rows.map(row));
    if (!rows.length) ui.storage.append(el("tr", {}, el("td", { textContent: "Nothing kept" }), el("td")));
    ui.clear.disabled = !rows.length;
  }

  async function clear() {
    ui.clear.disabled = true;
    if (app) {
      const reply = await call("storage", { clear: true });
      if ("refused" in reply) return say(reply.refused, true);
      say(`Cleared what AzurKit kept: ${reply.cleared.join(", ") || "nothing"}`);
      return storage();
    }
    for (const [key] of KEPT.local) {
      try {
        localStorage.removeItem(key);
      } catch {}
    }
    await sweep();   // those no page or worker holds
    const later = (await Promise.all(KEPT.databases.map(([name]) => new Promise((done) => {
      const request = indexedDB.deleteDatabase(name);
      request.onsuccess = request.onerror = () => done(false);
      request.onblocked = () => done(true);   // open in this page or another: deleted once those close
    })))).some(Boolean);
    say(`Cleared what AzurKit kept in this browser${later ? " (the rest once the page reloads)" : ""}: reload the page `
        + "to start fresh");
    storage();
  }

  lines();
  return {
    open: () => {
      if (!t.shown) {
        t.shown = true;
        info();
      }
      storage();
    },
    imaged: () => {
      if (t.shown) info();
      else lines();
    },
    built: (report, saved = null) => {
      t.report = report;
      t.saved = saved;
      ui.reportText.textContent = report ? reportText(report, saved) : "";
      if (!report) ui.reportText.hidden = true;
      lines();
    },
    state: t,
  };
}
