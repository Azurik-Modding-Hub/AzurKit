// The page (D866): pick your image, choose packs and set their sliders, Build, then Save. One page for both hosts,
// the site and the app; it decides no output byte (WEB §3.1). host.json names the host's engine, and the engine, azurkit.sdk, plans and
// checks the build. The site's, siteEngine(), is the wheel under Pyodide in two module workers (workers.mjs): it
// returns the build as segments and their Blob, of slices of your own file and the bytes the
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
// Each visit starts at the defaults (D1156, amending D915) unless Remember settings, in the bottom bar, is ticked: then
// the page keeps its setup between visits (D915), the site in this browser's storage, the app in its config. It comes
// back when the page opens, before you pick an image, less whatever no longer applies (named in the status line); a
// share link, or a build's recipe you load, takes its place; Reset to defaults forgets it, the box left as it is.
//
// The Randomizer tab (Step 4.2c1, RANDOMIZER_PLAN §5.5): Randomize (off by default, the tab's one switch, which
// unlocks its settings, D907), the seed and New, the options with D144's defaults, the share string, the item rows
// (each a category it shuffles) and the skips a setting can turn on, and the spoiler of the last randomized build. The
// engine reads the settings (sdk.randomizer_settings) and gives back what the tab shows; Build and Save are the
// bottom bar's, which build the randomizer's plan first (Modkit's order). A link and a build's recipe carry it.
//
// Its Tracker view (Step 4.2c2, tracker.mjs): the item tracker of a randomized build, of the seed the Settings view
// holds, or of a plan file, in both hosts; Live, which reads a running xemu, in the app alone (D882).
//
// The Characters tab (Step 4.3d, characters.mjs): the player's body, a species or a variant (ours from
// Azurik-Custom-Content, marked community, with Install and Update), its options and G4 buttons; Build wears it, a link,
// a build's recipe and the remembered setup carry it.
//
// The Data tab (Step 4.7a, data.mjs): config.xbr's cells in Modkit's views and as grids, edited before an image is
// picked (the engine reads the vanilla file AzurKit ships); its edits are the recipe's xbr set operations, which Build
// applies after the packs, a link and a mods file carry and the page remembers.
//
// The Tools tab (Step 4.7c, tools.mjs): your image (what it is, Verify every file, its files with Extract), recipes
// and files (Open a build… with Track this build, mods files, a plan file's spoiler, the last build's report) and
// AzurKit's storage with Clear; what waits for an image is greyed until one is picked (D979).
//
// A long call shows its progress in the bottom bar (D980, Step 4.3i): its stage and percent (core/progress.py's record)
// on a bar, from the app's api/progress or the site's worker; any ask the engine hasn't answered within 1 s shows
// its line there too, until it answers.
import { characters } from "./characters.mjs";
import { communityGroup } from "./community.mjs";
import { content } from "./content.mjs";
import { dataTab } from "./data.mjs";
import { hashedApart, WAITED } from "./hasher.mjs";
import { replaceFiles } from "./replace.mjs";
import { savesSection } from "./saves.mjs";
import { hold, letGo, sweep, written } from "./outputs.mjs";
import { player } from "./play.mjs";
import { tools } from "./tools.mjs";
import { tracker } from "./tracker.mjs";
import { variantsView } from "./variants.mjs";
import { canon, workers } from "./workers.mjs";

const $ = (id) => document.getElementById(id);
const R = (id) => $(`rando-${id}`);
const state = { engine: null, app: false, dialogs: false, ready: false, building: false, saving: false, file: null,
                packs: null, sent: null, build: null, url: null, saved: null, saveCheck: null, violations: [],
                vanilla: null, asked: null, xbr: [], link: null, pending: null, loaded: null, opened: null,
                site: null, theme: "dark", tab: null, remembered: null, kept: null, restoring: false, plain: true,
                later: null, gen: Date.now(), spoiler: null, tracker: null, call: null, asks: new Map(),
                vouched: new Map(), resting: new Map(), tracking: null, recovered: [], launch: null, played: null,
                rando: { view: null, overrides: {}, ticket: 0, waiting: false, given: null, load: null, later: null,
                         note: null, noted: null, asked: null, plan: null } };
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

// The setup the page remembers while Remember settings is ticked (D915, D1156): the packs ticked, each setting whose
// value differs from its default (its pack ticked or not: an unticked pack keeps its values, D907; a value that isn't a
// number isn't kept) and a loaded recipe's config.xbr cells (set: names and numbers, Q174). Never the image, its path
// or anything read from it: the site keeps it in this browser's storage, the app in its config (api/setup), and the
// page at its defaults keeps nothing.
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
  const rando = randoSetup(), character = state.characters?.setup();
  return state.community.kept({ ticked, values, xbr: state.xbr.filter((op) => op.op === "set"),
                                ...(rando ? { randomizer: rando } : {}), ...(character ? { character } : {}) });
}

// The app's work ahead (D1007): once the setup settles, a typed seed planned with its first tracker view, and the
// setup built, before their click (api/prefetch, api/speculate), with the bodies Track and Build send; each carries
// state.gen, bumped by every change (from the clock: a reloaded page's are newer), so the engine drops an older one at
// its next record, and a setup with nothing to build yet drops it too (the Characters tab offers again once it answers).
// The site's is its second worker's (aheadOnSite).
function ahead() {
  if (!state.app) return aheadOnSite();
  if (!state.ready || state.building || state.saving) return;
  const seed = R("seed").value.trim(), share = state.rando.view?.share, t = state.tracker?.state;
  state.engine.prefetch(state.gen, seed && share && !state.rando.plan ? { seed, share } : null,
                        { spoiler: t?.spoiler, gems: t?.gems });
  const randomizer = randoRecipe();
  if (state.build) return;
  if (!state.file || state.opened || (randomizer && !randomizer.seed && !randomizer.plan) || state.characters?.refused()
      || state.characters?.waiting() || state.community?.waiting()) return void state.engine.speculate(state.gen, null);
  state.engine.speculate(state.gen, state.file, chosen(), state.xbr, randomizer,
                         state.characters?.character() ?? null, extras());
}

// The site's work ahead (D1007), in B, the second worker: the typed seed's plan and first view (with Randomize on or the
// Tracker view open), and, once the picked image is read, Build's build of the page's recipe; each change lists them
// anew, so what no longer matches stops at once (B's job by terminate()) and B starts on the rest once the page holds
// still. A reshaped character isn't built ahead: minutes, and a heap past KEEP terminated by the next slider's change
// would leave its pages resident in WebKit (w-reshape). Its click runs in the one heap. A change of the Characters
// tab's own (a number, an option, Reset: rest) that follows another of them is built ahead once the tab has rested,
// for the same reason: a slider's session (moves, a pause, a drag, Reset) dropped one build ahead a move, 7.2-7.4 GiB
// in WebKit (Step 4.4ci48); one alone is built ahead as any change. A body's build asks with
// the tab's choice before the engine's answer to it, and each build is keyed on the character it sends: the answer
// drops what the body locks or doesn't take (a variant's size, say), so a click takes B's build only when the two match.
const reshaped = (character) => Boolean(character?.shapes && Object.keys(character.shapes).length);
function aheadOnSite(begin = false, rest = 0) {   // none while a Save is checked: checkSave's end asks again
  if (!state.engine?.ahead || !state.packs || state.restoring || state.saveCheck === "running") return;
  const seed = R("seed").value.trim(), share = state.rando.view?.share, rando = randoRecipe(), tracking = !$("tracker").hidden;
  const character = state.characters?.choice() ?? null, plans = [], builds = [];
  if (character || state.vanilla) state.engine.warm();   // numpy and the dress's imports: S14's second, in its head start
  if (seed && share && !state.rando.plan && (rando || tracking)) {
    const asked = { seed, share }, known = JSON.stringify(asked);
    plans.push(state.engine.planning(asked, ({ reply }) => {
      if (!reply?.plan) return;
      state.planned = { known, plan: reply.plan };
      ahead();
    }));
    if (state.planned?.known === known) plans.push(state.engine.viewing(state.tracker.first(state.planned.plan)));
  }
  if (state.vanilla && state.read === state.file && !state.opened && state.replace && !state.characters?.refused()
      && !state.community?.waiting() && (!rando || rando.seed || rando.plan) && !reshaped(character)) {
    builds.push(state.engine.building(state.file, chosen(), state.xbr, rando, character,
                                      { ...extras(), ...state.replace.picked() }));
  }
  state.engine.ahead(tracking ? [...plans, ...builds] : [...builds, ...plans], { begin, rest });
}

// Keep the page's setup (none at its defaults, none with Remember settings unticked), once it is the page's own: after
// the remembered one is back. The app's api/setup takes the choice with it.
function remember() {
  clearTimeout(state.later);
  if (!state.packs || state.restoring) return;
  ahead();
  const kept = setup(), defaults = state.packs.packs.filter((pack) => pack.default_on).map((pack) => pack.name);
  state.plain = !kept.xbr.length && !Object.keys(kept.values).length && kept.ticked.join() === defaults.join()
    && !kept.randomizer && !kept.character && !kept.community;
  $("reset").disabled = state.building || state.plain;
  const keep = $("remember").checked, text = keep && !state.plain ? JSON.stringify(kept) : null;
  if (text === state.kept) return;
  state.kept = text;
  if (state.app) return state.engine.setup(keep, text && kept);
  try {
    if (text) localStorage.setItem(SETUP, text);
    else localStorage.removeItem(SETUP);
  } catch {}   // storage refused (a private window, say): the setup lasts this visit
}

// Remember settings (D1156): off by default, so each visit starts at the defaults; ticked, the page keeps its setup for
// the next visit; unticked, it keeps none and forgets the one it kept at once. The choice itself is kept (the site's
// REMEMBER, the app's config through api/setup): it decides whether the next visit starts fresh. The box works once the
// page is its own (start()), its remembered setup back.
const REMEMBER = "azurkit.remember";
function keepChosen() {
  state.kept = undefined;   // what is kept follows the choice now
  if (!state.app) {
    try {
      if ($("remember").checked) localStorage.setItem(REMEMBER, "1");
      else localStorage.removeItem(REMEMBER);
    } catch {}   // storage refused (a private window, say): nothing is kept anyway
  }
  remember();
}

// What the site's storage holds (the app's comes in host.json): whether it remembers, and if so the setup to restore,
// as the engine reads it. A setup kept with no choice (AzurKit 1.0's, which always kept one) is removed unread.
function stored() {
  let keep = false;
  try {
    keep = localStorage.getItem(REMEMBER) === "1";
    if (keep) state.kept = localStorage.getItem(SETUP);
    else localStorage.removeItem(SETUP);
  } catch {}
  $("remember").checked = keep;
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

const READYING = "Getting your image ready to save";
// Progress (D980): one bar for both hosts. Each ask in flight is kept (asking(kind) -> its id, answered(id)) with the
// last record the engine gave for it (the app's api/progress, polled every 250 ms from the click while any ask is in
// flight; the site's worker's posts); the newest that is a build, a save, Track this seed's plan or a plan file's
// spoiler, has a record, or has waited 1 s shows: its label and percent, or a moving stripe while it has no count.
const LABELS = { build: "Building", save: "Saving", save_check: "Saving", vanilla: "Checking your image", check: "Checking your image",
                 start: "Starting the engine", plan: "Planning the seed", tracker: "Reading the seed's logic",
                 randomizer: "Reading the randomizer",
                 restore: "Restoring your setup", pickers: "Reading the models", preview: "Drawing the model",
                 match: "Matching garret4", content: "Reading the community content", install: "Installing",
                 content_check: "Checking the download", spoiler: "Writing the spoiler", preset: "Making the link",
                 decode: "Reading the link", info: "Reading your image", verify_all: "Checking every file",
                 files: "Listing its files", extract: "Extracting the file", open: "Reading the build",
                 mods_file: "Reading the mods file", plan_spoiler: "Writing the spoiler", report: "Saving the report",
                 storage: "Reading AzurKit's storage", data: "Reading the game data", data_edit: "Checking the edit",
                 play: "Starting xemu", attach: "Attaching to xemu", tray: "Reading xemu's disc", logs: "Opening the log",
                 variants: "Reading your variants", variant_open: "Opening the variant", variant_read: "Reading the recipe",
                 variant_save: "Saving the variant", variant_delete: "Deleting the variant",
                 variant_import: "Importing the variant", variant_export: "Exporting the variant",
                 variant_check: "Checking with game data", variant_pictures: "Drawing the variant",
                 variant_preview: "Previewing the shape", variant_colours: "Recolouring the variant",
                 export_pngs: "Exporting its PNGs", add_png: "Importing the PNG", move_sources: "Reading the bodies' clips",
                 variant_weapons: "Reading the weapons it takes", own_sounds: "Reading its base's sounds",
                 kit_throw: "Reading its base's weapon", add_wav: "Adding the WAV", flat: READYING };
const AT_ONCE = new Set(["build", "save"]);   // shown from the click, over with the build or save; any other from its
// first record, else after 1 s. Shown from the click too: Track this seed's plan and a plan file's spoiler (the logic's
// read), and the site's Save's check, which is over when it is: no later Build, Cancel, pick or engine's ready ends it
const FOLLOWED = new Set([...AT_ONCE, "plan", "plan_spoiler", "save_check", "flat"]);
const PAGES = new Set(["save_check", "flat"]);   // the page's own waits, with their own records: never a worker's
let asked = 0, ticking = null;
// A slow launch of the app's (D980: past 1 s an op shows where it is): one whose server had run SLOW_LAUNCH s by its
// host.json answer (its age) shows its stages on the bar, the host read and the page drawn of the three (its setup
// restored the last), until the page is ready (start()).
const SLOW_LAUNCH = 0.5;

function launched(done) {
  const ask = state.asks.get(state.launch);
  if (!ask) return;
  ask.record = { stage: "launch", label: "Starting AzurKit", done, total: 3, percent: Math.round(100 * done / 3) };
  showing();
}

// The bar shows ``step`` (none: hidden), each of its parts written only when it changes: a write of what it already
// shows draws it again all the same, a round trip to the browser's drawing process (WebKit's GPU process, which a busy
// computer starves), and the tick and the worker's records rewrote it 23 times a second, half of them unchanged.
function progressed(step) {
  const row = $("progress-row"), bar = $("progress"), line = $("progress-line");
  const value = step?.percent == null ? null : String(step.percent);
  if (row.hidden !== !step) row.hidden = !step;
  if (bar.getAttribute("value") !== value) value === null ? bar.removeAttribute("value") : bar.setAttribute("value", value);
  const text = step && `${step.label}…${value === null ? "" : ` ${value} %`}`;
  if (step && line.textContent !== text) line.textContent = text;
}

function asking(kind, until = null) {
  const id = ++asked;
  state.asks.set(id, { kind, since: performance.now(), record: null, until });
  ticking ??= setInterval(tick, 250);
  showing();
  return id;
}

function answered(id) {
  state.asks.delete(id);
  showing();
}

// The newest ask that shows (its record, or its kind's line), or none: the bar hidden.
function showing() {
  const now = performance.now();
  for (const [id, ask] of state.asks) if (ask.until !== null && now > ask.until) state.asks.delete(id);
  const ask = [...state.asks.values()].findLast((a) => a.record || FOLLOWED.has(a.kind) || now - a.since >= 1000);
  progressed(ask && (ask.record ?? { label: LABELS[ask.kind] ?? "Working", percent: null }));
}

async function tick() {
  if (!state.asks.size) {
    clearInterval(ticking);
    ticking = null;
    return progressed(null);
  }
  if (state.app) {   // each ask's record from its click: a G4 match's bar, polled from 750 ms, moved only past 1 s
    const at = performance.now();
    const reply = await state.engine.progress().catch(() => null);
    for (const ask of state.asks.values()) {
      const step = reply?.calls?.[ask.kind];
      if (step?.stage && ask.since <= at) ask.record = step;   // never a record of a call of its kind that ended before it
    }
  }
  showing();
}

// The site's worker's record: its start's on the worker's start ask (siteEngine's, answered at ready); else the
// build's while one runs; else a check's (before the call it came with: its own, gone with the worker's next answer,
// else a moment after it is whole or 1.5 s after its last), else the newest ask's that is the worker's.
function posted(step, start = null) {
  const asks = [...state.asks.values()];
  let ask = step.stage === "start" ? state.asks.get(start) : asks.findLast((a) => a.kind === "build")
    ?? (step.stage === "check" ? asks.findLast((a) => a.kind === "check") : asks.findLast((a) => !PAGES.has(a.kind)));
  if (!ask && step.stage === "check") ask = state.asks.get(asking("check"));
  if (!ask) return;
  ask.record = step;
  if (ask.kind === "check") ask.until = performance.now() + (step.percent === 100 ? 250 : 1500);
  showing();
}

// The site's worker answered (or stopped): it answers in order, so each check posted before the answer is over and its
// bar goes, whatever the clock says: a build answered within a check's moment never shows the check again, nor does a
// Cancel during a check (Step 4.3 train).
function unchecked() {
  const checks = [...state.asks].filter(([, ask]) => ask.kind === "check");
  for (const [id] of checks) state.asks.delete(id);
  if (checks.length) showing();
}

// The site's engine: two module workers (web/workers.mjs, Step 4.3r4l: F answers the page's asks, B works ahead), each
// started from its own URL once sw.js controls the page (sw.js sends it the page's CSP as a header and serves its
// imports: Firefox sends a blob: worker's past it), else from a blob: URL so that it keeps the page's CSP. A worker a
// job grew stays for the next heavy job, wasm memory
// never shrinking (one heap, workers.mjs); one past its line is replaced, "Preparing the engine…" meanwhile, by B at once
// when B is idle and small. A seed's build comes without its spoiler, which the worker sends next (built's spoiled: a
// promise of it). A click whose key is B's finished job takes its answer; one B is still working on follows B's records.
// The key holds everything an answer reads: the recipe, the picked File (by identity: a new pick is a new key), what this
// browser keeps installed and the engine's version.
const SMALL = new Set(["pickers", "tracker", "data", "data_edit", "variants", "variant_open", "variant_read",
                       "variant_save", "variant_delete", "variant_import", "variant_export", "add_wav"]);   // an ask B answers while F builds
const ASIDE = new Set(["content", "pickers", "content_check"]);   // sent no image, B answers while F runs anything: an
                                                                  // Install's list never waits for a check (Step 4.3r4m)
function siteEngine({ ready, built, refused, failed, vanilla, opened, shared, decoded, restored, rando }) {
  let calls = 0, content = null, engine = null, picks = 0, warmed = false, library = 0;
  let starting = null;   // the ask a loading F's start records show on, answered at its ready or its stop
  const picked = new WeakMap();
  const start = (role) => {
    if (role === "f") {
      answered(starting);
      starting = asking("start");
    }
    const entry = new URL("worker.mjs", location.href).href;
    const url = ours() ? entry
      : URL.createObjectURL(new Blob([`import ${JSON.stringify(entry)};\n`], { type: "text/javascript" }));
    const worker = new Worker(url, { type: "module" });
    worker.addEventListener("message", ({ data }) => {
      if (data?.type === "ready" && url !== entry) URL.revokeObjectURL(url);
      if (data?.type === "native") {   // every worker's, for the perf gate's native assert (a worker's ends with it)
        state.calls = { kernel: (state.calls?.kernel ?? 0) + (data.kernel ?? 0),
                        twin: (state.calls?.twin ?? 0) + (data.twin ?? 0) };
      }
      if (data?.out) hold(data.out).then(() => worker.postMessage({ type: "held" }));   // its build file: this page's now
      if (data?.type === "vouched") state.vouched.set(data.id, { ...state.vouched.get(data.id), ...data.digests });
      if (data?.type === "resting" || data?.type === "rested") rested(data, worker);
    });
    const terminate = worker.terminate.bind(worker);
    worker.terminate = () => {   // the pool's: a rest it was hashing ends with it
      terminate();
      for (const [id, rest] of state.resting) if (rest.worker === worker) rested({ type: "rested", id }, worker);
    };
    return worker;
  };
  const back = () => {   // the page's engine answers again (the same worker, or B's answer taken)
    if (engine && !state.ready && pool.up()) ready(...engine);
  };
  const pool = workers({
    start,
    held: (messages) => messages.reduce((n, m) => n + (m.held ?? 0), 0),
    free: (messages) => messages.forEach((m) => m.out && letGo(m.out)),
    ready: (data) => {
      answered(starting);
      starting = null;
      engine = [data.catalog, data.version, data.commit, data.platform];
      state.workers = (state.workers ?? 0) + 1;   // the workers that took F's place, for the tests
      ready(...engine);
    },
    told: (data) => {
      if (data.type === "progress") {
        const { type, ...step } = data;
        posted(step, starting);
      } else if (data.type === "csp") {
        state.violations.push(`worker: ${data.directive} ${data.blocked}`);
        failed(`The page's security policy refused ${data.directive} in the engine`);
      } else if (data.type === "failed") {
        answered(starting);
        starting = null;
        failed(data.message);
      }
    },
    // A worker whose engine trapped was started again (D1126): the page says so where it sends the player's ask again,
    // and keeps where each trap was (worker.mjs's located()) for the tests and CI, its cause being open. The ask's bar
    // drops the trapped attempt's stage: the next engine's start and warm-up post none of the ask's.
    restarted: (data, redo) => {
      state.recovered.push(data.message);
      if (!redo) return;
      say(`The engine stopped and started again: ${(LABELS[redo] ?? "working").toLowerCase()} again`);
      for (const ask of state.asks.values()) if (ask.kind === redo) ask.record = null;
      showing();
    },
  });
  state.pool = pool;   // for the tests
  const progress = ({ type, ...step }) => posted(step);
  const plain = ({ type, heap, ...rest }) => rest;
  const stopped = (data) => data.type === "failed" ? data.message
    : `The engine stopped (${data.message || "out of memory?"}): try again, or use the desktop app`;
  const key = (what) => {
    try {
      return canon({ ...what, installed: content?.installed ?? null, library, code: engine?.[1] ?? null });
    } catch {
      return null;   // a recipe no key holds: no work ahead, and the click asks F
    }
  };
  const image = (file) => file ? picked.get(file) ?? (picked.set(file, ++picks), picks) : null;
  // (a replaced file's picked File is no JSON: no key, so such a build is never made ahead)
  const buildKey = (file, packs, xbr, randomizer, character, extra = {}) =>
    key({ build: { packs, xbr, randomizer, character, ...extra }, image: image(file) });
  const viewKey = ({ plan, ...rest }) => key({ view: rest, plan: plan?.sha256 ?? null });
  // An ask answered by one kind of message: its bar, its answer, and a stopped worker's failure named.
  const asked = (message, options, done) => pool.ask(message, { progress, ...options }).then((data) => {
    unchecked();
    if (data.type === "failed" || data.type === "stopped") failed(stopped(data));
    else if (data.type !== "cancelled") done(data);
    back();
  });
  const waits = new Map();   // the newest Randomizer tab's ask and restore: their bar
  const wait = (kind, message, options, done) => {   // settled once answered, or failed
    answered(waits.get(kind));
    const id = asking(kind);
    waits.set(kind, id);
    return asked(message, options, done).finally(() => {
      if (waits.get(kind) !== id) return;
      answered(id);
      waits.delete(kind);
    });
  };
  return {
    build: (file, packs, xbr, randomizer, character, extra = {}) => {
      let give = null;
      const shown = (data) => {   // the build (a seed's before its spoiler), or its refusal
        if (data.type !== "built" && data.type !== "refused") return;
        unchecked();
        state.heap = data.heap ?? null;
        if (data.type === "built") {
          pool.hold(data.held ?? 0);   // what the page's Blob holds in memory
          state.took = pool.took(data);   // from B's work ahead, for the tests
          if (data.report.plan && !("spoiler" in data.report)) data.spoiled = new Promise((g) => give = g);
        }
        (data.type === "built" ? built : refused)(data);
        back();
      };
      pool.hold(0);   // the last build is gone (forget())
      pool.ask({ type: "build", file, packs, xbr, randomizer, character, ...extra },
               { key: buildKey(file, packs, xbr, randomizer, character, extra), heavy: true, progress,
                 answer: shown }).then((data) => {
        unchecked();
        if (data.type === "spoiled") give?.(plain(data));
        else if (data.type === "built" || data.type === "refused") shown(data);
        else {
          give?.({ refused: "The engine stopped before it gave the spoiler: build the seed again" });
          if (data.type !== "cancelled") failed(stopped(data));
        }
        back();
      });
    },
    randomizer: (given, ticket, file) => wait("randomizer", { type: "randomizer", given, ticket, ...(file ? { file } : {}) },
                                              { anywhere: true }, (data) => rando(data.reply, data.ticket)),
    vanilla: (file) => asked({ type: "vanilla", file }, {}, (data) => {   // each answer with the file it is about
      if (data.type === "vanilla") {   // with the image's info for the Tools tab (worker.mjs's vanilla)
        const { info, ...read } = plain(data);
        vanilla(read, info, file);
      } else if (data.type === "opened") opened(data.preset, file);
    }),
    preset: (recipe, report) => asked({ type: "preset", recipe, report }, { anywhere: true }, (data) => {
      if (data.type === "preset") shared(data.fragment);
      else failed(data.message);
    }),
    decode: (text) => asked({ type: "decode", text }, {}, (data) => {
      if (data.type === "decoded") decoded(data.preset);
      else failed(data.message);
    }),
    restore: (setup) => wait("restore", { type: "restore", setup }, {}, (data) => restored(plain(data))),
    // after: an ask sent before this one, which this one waits behind in F's queue (Check with game data's pictures,
    // drawn by the worker that dressed it): its line on the bar only once that one is answered, whose records it shows.
    call: (type, body, { once = false, after = null } = {}) => new Promise((resolve) => {
      let id = after ? null : asking(type), done = false;
      after?.then(() => { if (!done) id = asking(type); });
      const aside = ASIDE.has(type) && !body.file;
      pool.ask({ type, call: ++calls, ...body }, {
        once, heavy: once, anywhere: SMALL.has(type) || aside, aside, progress,
        key: type === "plan" ? key({ plan: body.recipe }) : type === "tracker" ? viewKey(body.given) : null,
      }).then((data) => {
        if (data.type !== "reply" || body.file) unchecked();   // one that stood on no image may overtake a check (Step 4.3r4m)
        done = true;
        if (id !== null) answered(id);
        back();
        resolve(data.type === "reply" ? data.reply
          : { refused: data.type === "cancelled" ? "Cancelled"
            : "The engine stopped before it answered (out of memory?): try again, or use the desktop app" });
      });
    }),
    content: (files, installed) => {
      content = { files, installed };
      pool.share({ type: "content", ...content });
      ahead();
    },
    library: (folders) => {   // your variants as this browser keeps them: the engine's library, whole (each change)
      library++;
      pool.share({ type: "library", folders });
      ahead();
    },
    cancel: () => {
      pool.cancel();
      setTimeout(sweep, 1000);   // a stopped job's build file, once its lock is gone
      unchecked();   // nor finishes a check
      for (const ask of state.asks.values()) ask.record = null;   // nor runs a stage it reported (Step 4.3 train)
      queueMicrotask(back);
    },
    // The work ahead's items: Track this seed's plan and its first view, and Build's build of the page's recipe.
    planning: (recipe, kept) => {
      const k = key({ plan: recipe });
      return k && { key: k, message: { type: "plan", call: 0, recipe }, kept };
    },
    viewing: (given) => {
      const k = viewKey(given);
      return k && { key: k, message: { type: "tracker", call: 0, given } };
    },
    building: (file, packs, xbr, randomizer, character, extra = {}) => {
      const k = buildKey(file, packs, xbr, randomizer, character, extra);
      return k && { key: k, heavy: true, message: { type: "build", file, packs, xbr, randomizer, character, ...extra } };
    },
    warm: () => warmed || (warmed = true, pool.share({ type: "warm" })),   // each worker's, a new one's too
    ahead: (items, options) => {
      const stopped = pool.state().dropped;
      pool.want(items.filter(Boolean), options);
      if (pool.state().dropped !== stopped) setTimeout(sweep, 1000);   // a dropped job's build file, once its lock is gone
    },
  };
}

// The app's engine: azurkit.sdk on CPython behind this launch's server (azurkit.app), the same in the app's window
// and in a browser. The page posts JSON to it, and a refusal comes back as {refused}. A build's reply that arrives
// after Cancel is dropped; a save's is awaited, since the server says whether it wrote anything.
function appEngine(host, { ready, built, refused, failed, saved, vanilla, opened, shared, decoded, restored, rando }) {
  let ticket = 0, telling = Promise.resolve();
  const followed = (kind, asked) => {   // an ask's progress shown until it answers
    const id = asking(kind);
    return asked.finally(() => answered(id));
  };
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
  setTimeout(() => ready(host.catalog, host.version, host.commit, host.platform));
  const ask = (path, body, done) => post(path, body)
    .then((reply) => "refused" in reply ? failed(reply.refused) : done(reply))
    .catch((error) => failed(`The app's engine didn't answer (${error.message}): restart AzurKit`));
  return {
    build: (iso, packs, xbr, randomizer, character, extra) => run("api/build", { iso, packs, xbr, randomizer, character,
                                                                                 ...extra }, built),
    randomizer: (given, ticket, iso) => followed("randomizer", post("api/randomizer", { given: iso ? { ...given, iso }
                                                                                       : given }))
      .then((reply) => rando(reply, ticket))
      .catch((error) => rando({ refused: `The app's engine didn't answer (${error.message})` }, ticket)),
    spoiler: (out) => ask("api/spoiler", { out }, (reply) => say(`Saved the spoiler: ${reply.spoiler.out}`)),
    vanilla: (iso) => followed("vanilla", post("api/vanilla", { iso })).then((read) => "refused" in read
      || ("opened" in read ? opened(read.opened, iso) : vanilla(read, null, iso))).catch(() => {}),
    preset: (recipe, report) => ask("api/preset", { recipe, report }, (reply) => shared(reply.fragment)),
    decode: (text) => ask("api/decode", { text }, (reply) => decoded(reply.preset)),
    restore: (setup) => followed("restore", ask("api/restore", { setup }, restored)),
    setup: (remember, setup) => post("api/setup", { remember, setup }, true).catch(() => {}),   // a convenience
    // a head start only: the click asks again either way
    prefetch: (gen, recipe, view) => post("api/prefetch", { gen, recipe, view }).catch(() => {}),
    speculate: (gen, iso, packs, xbr, randomizer, character, extra) => post("api/speculate",
      { gen, iso, packs, xbr, randomizer, character, ...extra }).catch(() => {}),
    save: (recipe, out, build) => run("api/save", { recipe, out, build }, saved),   // that build's image, kept
    progress: async () => (await fetch("api/progress", { cache: "no-store" })).json(),
    choose: async (kind, path) => (await post("api/choose", { kind, path })).path ?? null,
    theme: (name) => post("api/theme", { theme: name }).catch(() => {}),   // remembering is a convenience
    call: (type, body) => followed(type, post(`api/${type}`, type === "install" ? { ...body, gen: ++state.gen } : body))
      .catch((error) => ({ refused: `The app's engine didn't answer (${error.message}): restart AzurKit` })),
    content: () => {},   // the app's engine reads its content folder itself
    library: () => {},   // and its library of your variants
    // remembering is a convenience; not keepalive: a plan and its marks may pass keepalive's 64 KiB
    tracked: (kept) => post("api/tracked", { tracker: kept }).catch(() => {}),
    // whether the Variants view holds edits not saved, which the window asks about as it closes: each told once the
    // last is answered, so the server holds the newest
    unsaved: (yes) => (telling = telling.then(() => post("api/unsaved", { unsaved: yes })).catch(() => {})),
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
// constant), shown beside it and held by its track (D42), and (the site's) the engine's info of it, which the Tools tab
// shows with no ask of its own. A reply for an image no longer picked (file, the one it was asked of) is dropped.
function vanilla(read, info = null, file = state.file) {
  if (file !== state.file) return;
  state.vanilla = read;
  state.imageInfo = info;
  state.read = state.file;
  for (const pack of state.packs?.packs ?? []) {
    for (const slider of pack.sliders) {
      const value = read.packs[pack.name]?.[slider.name];
      if (value === undefined) continue;
      slider.vanilla = value;
      document.getElementById(`${pack.name}.${slider.name}`)?.closest(".slider").fit();
    }
  }
  lines();
  ahead();   // the picked image's setup, built ahead
}

// Ask the engine for the picked image's values once it is ready (the site's is replaced after each build).
function askVanilla() {
  if (!state.ready || !state.file || state.asked === state.file || state.building) return;
  state.asked = state.file;
  state.engine.vanilla(state.file);
}

// Each group's line of what the last tick moved and why.
function moved(changed, lines) {
  for (const note of $("packs").querySelectorAll(".moved")) note.textContent = "";
  if (changed) changed.closest(".group").querySelector(".moved").textContent = lines.join(" ");
}

// Ticking a pack ticks the packs it requires, and unticking one unticks the packs that require it (D588), each move
// said beside its group (the rule and its words are mods.settle's), so the page never sends a recipe the engine refuses
// for a missing pack.
function linked(changed) {
  const boxes = Object.fromEntries([...$("packs").querySelectorAll("input[data-pack]")].map((b) => [b.dataset.pack, b]));
  const requires = Object.fromEntries(state.packs.packs.map((p) => [p.name, p.requires]));
  const why = Object.fromEntries(state.packs.packs.map((p) => [p.name, p.requires_why])), lines = [];
  const todo = [changed.dataset.pack];
  while (todo.length) {
    const name = todo.pop(), on = boxes[name].checked;
    const next = on ? requires[name] : Object.keys(requires).filter((other) => requires[other].includes(name));
    for (const other of next) {
      if (boxes[other].checked !== on) {
        boxes[other].checked = on;
        todo.push(other);
        lines.push(on ? `Also ticked ${other}: ${name} ${why[name]}.` : `Also unticked ${other}: it ${why[other]}.`);
      }
    }
  }
  moved(changed, lines);
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
  if (pack.requires.length) {
    what.append(Object.assign(document.createElement("span"), {
      className: "needs", textContent: ` Needs ${pack.requires.join(", ")}.`, title: `${pack.name} ${pack.requires_why}.` }));
  }
  what.append(where);
  label.append(box, name, what);
  const sliders = Object.assign(document.createElement("div"), { className: "sliders", id: `${pack.name}-settings` });
  sliders.setAttribute("role", "group");
  sliders.setAttribute("aria-label", pack.name);
  const flipped = flips(pack), toggles = new Set(flipped.values());
  const rows = pack.sliders.filter((slider) => !toggles.has(slider))
    .map((slider) => sliderRow(pack, slider, flipped.get(slider.name)));
  sliders.append(...rows);
  if (pack.sliders.some((slider) => slider.vanilla == null)) {   // its vanilla values are the image's (D42, D979)
    sliders.prepend(Object.assign(document.createElement("p"), {
      className: "note vanilla-note", textContent: "Pick your image (1.): its own values show beside these." }));
  }
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
    const note = Object.assign(document.createElement("p"), { className: "note moved" });
    note.setAttribute("role", "status");
    group.append(summary, ...packs.map(packRow), note);
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
    const owned = state.community?.owns(item.dataset.pack);   // a ticked community pack's: locked while it is
    box.disabled = state.building || owned;
    for (const field of item.querySelectorAll(".sliders input")) field.disabled = state.building || !box.checked || owned;
  }
  state.community?.lock(state.building);
}

// Each group's count of its packs ticked, which a folded group still shows.
function tally() {
  for (const group of $("packs").querySelectorAll(".group[data-category]")) {
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
  if (id === "randomizer" && state.packs) {   // the Patches tab's packs may have changed (at once)
    syncWarp();
    askRando(null, 0);
  }
  if (id === "characters" && state.characters) state.characters.open();
  if (id === "characters" && state.variants && state.charPane === "variants") state.variants.open();
  if (id === "data" && state.data) state.data.open();   // the Patches tab's ticks may have changed: its ⚠ marks
  if (id === "tools" && state.tools) state.tools.open();
  for (const tab of $("tabs").children) tab.setAttribute("aria-selected", String(tab.dataset.tab === id));
  for (const panel of document.querySelectorAll("[role=tabpanel]")) panel.hidden = panel.dataset.tab !== id;
  place();
}

// The ticked packs, each with its sliders' values as typed: the engine normalizes them and names what it refuses.
// What a recipe holds beside its packs, xbr, randomizer and character, as a build's ask and a link's recipe carry it.
function extras() {
  const pins = state.community.pins(), files = state.replace.entries();
  return { ...(pins.length ? { community: pins } : {}), ...(files.length ? { files } : {}) };
}

function chosen() {
  const packs = {};
  for (const item of $("packs").querySelectorAll(".pack")) {
    if (!item.querySelector("input[data-pack]").checked) continue;
    packs[item.dataset.pack] = Object.fromEntries(
      [...item.querySelectorAll("input[data-slider]")].map((field) => [field.dataset.slider, given(field)]));
  }
  return packs;
}

const unready = () => Boolean(state.build?.flat && !state.url);   // Firefox's Blob isn't made yet: Save waits greyed

function busy(on) {
  state.building = on;
  $("share").disabled = on || !state.packs;
  $("reset").disabled = on || state.plain;
  $("iso").disabled = on || !state.packs;
  for (const id of ["iso-path", "iso-choose", "out-path"]) $(id).disabled = on;
  $("save").disabled = on || !state.build || unready();
  $("play").disabled = on || !state.played;
  $("cancel").hidden = !on;
  gate();
  lock();
  lockRando();
  if (!on) {
    state.saving = false;
    for (const [id, ask] of state.asks) if (AT_ONCE.has(ask.kind)) answered(id);
  }
}

// D979: a control that can't work yet is greyed, with the line that says what it waits for: Build until an image is
// picked (a vanilla one: an AzurKit build only offers its recipe) and the engine is ready, and while the Randomizer
// tab's items can't make a seed (the line names the row to tick, its ⚠ line why: Step 4.4u1), Save until a build; the
// settings of a pack whose vanilla values the image holds say so until it is read, and the spoiler's line names the
// image too.
function gate() {
  $("build").disabled = state.building || !state.file || !state.ready || Boolean(state.opened) || Boolean(randoStarved());
  lines();
}

function lines() {
  const refused = randoStarved();
  const why = state.building ? "" : !state.file ? "Pick your image (1.) to build"
    : state.opened ? "Pick your vanilla image (1.) to build: this one is an AzurKit build"
    : !state.ready ? "Preparing the engine…"
    : refused ? `${refused.preflight_tick ?? "Change the items"} on the Randomizer tab to build`
    : !state.build ? "Save follows a build"
    : unready() ? `${READYING}…` : "";
  $("build-line").textContent = why;
  $("build").title = $("build").disabled ? why : "";
  $("save").title = $("save").disabled && !state.building ? (state.build ? why : "Save follows a build") : "";
  $("play").title = state.played ? `Launch xemu with ${state.played.out} in its tray, then track it with Live on`
    : "Save a build first, then play it in xemu";
  $("spoiler-note").textContent = state.file ? "Build with Randomize ticked to see its spoiler."
    : "Pick your image (1.), then build with Randomize ticked to see its spoiler.";
  for (const note of $("packs").querySelectorAll(".vanilla-note")) note.hidden = Boolean(state.vanilla);
}

function forget() {
  if (state.url) URL.revokeObjectURL(state.url);
  for (const name of [state.build?.out, state.build?.between]) if (name) letGo(name, state.build.saved);
  state.build = state.url = null;
  $("save").disabled = true;
  lines();
  $("out-row").hidden = true;
  spoiler(null);
  ingame([]);
}

// D1153: the in-game controls the build adds (sdk._ingame: the save warp, LB's attack sets, L3's speed toggle, the
// roll's RB where it moved, photo mode), in a line beside its result; none hides it, as a build forgotten or begun does
function ingame(controls) {
  $("ingame").textContent = controls.length ? `In game: ${controls.join(" · ")}` : "";
  $("ingame").hidden = !controls.length;
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
  moved();
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
  state.data?.load(xbr);
  noteXbr();
}

// The Patches tab's line for the Data tab's edits (the recipe's xbr operations), which each build applies.
function noteXbr() {
  const n = state.xbr.length;
  $("xbr-note").textContent = n ? `The Data tab holds ${n} config.xbr edit${n > 1 ? "s" : ""}, which each build `
    + "applies." : "";
}

// Load a recipe (a share link's, or an AzurKit build's: a preset, already checked by the engine) into the page, marked,
// in place of the remembered setup, which it becomes with Remember settings ticked (D915, D1156). Without a packs
// layer (Modkit's mod file), the ticks and every setting stay as they are.
function load(preset, from) {
  const packs = preset.layers.find((layer) => layer.tool === "mods")?.recipe;
  state.community.clear();
  const ticked = [...$("packs").querySelectorAll("input[data-pack]:checked")].map((box) => box.dataset.pack);
  const values = () => Object.fromEntries([...$("packs").querySelectorAll(".pack")].map((item) => [item.dataset.pack,
    Object.fromEntries([...item.querySelectorAll("input[data-slider]")].map((field) => [field.dataset.slider,
                                                                                        shown(field)]))]));
  setTo(new Set(packs ? Object.keys(packs) : ticked), packs ?? values(),
        preset.layers.find((layer) => layer.tool === "data")?.recipe.ops ?? [], from);
  const rando = preset.layers.find((layer) => layer.tool === "randomizer")?.recipe;
  loadRando(rando, from);
  const character = preset.layers.find((layer) => layer.tool === "characters")?.recipe ?? null;
  state.characters.set(character);
  state.community.set(preset.layers.find((layer) => layer.tool === "community")?.recipe.packs ?? []).then(remember);
  state.replace.set(preset.layers.find((layer) => layer.tool === "files")?.recipe.files ?? []);
  pick(rando ? "randomizer" : character ? "characters" : "patches");
  state.loaded = preset;
  remember();
  const made = preset.azurkit ? ` (made with AzurKit ${preset.azurkit})` : "";
  const cells = state.xbr.length ? ` and ${state.xbr.length} config.xbr edit${state.xbr.length > 1 ? "s" : ""}` : "";
  const seed = (rando ? ` and the randomizer (${rando.plan ? "a plan file, " : ""}seed ${rando.seed ?? rando.plan.seed})`
    : "") + (character ? ` and ${character.species}` : "");
  say(`Loaded ${from}'s recipe${made}: ${packs ? `${Object.keys(packs).length} packs` : "the packs as ticked"}${cells}`
      + `${seed}, marked ●. `
      + `${(preset.settled ?? []).join(" ")}${preset.settled ? " " : ""}Pick your vanilla image, then Build.`);
}

// The remembered setup, as the engine gives it back (sdk.restore): what still applies, and what doesn't, by name.
function restored({ ticked, values, xbr, dropped, randomizer, character, community }) {
  state.restoring = false;
  state.community.clear();
  setTo(new Set(ticked), values, xbr);
  setRando(randomizer ?? randoDefaults());
  state.characters.set(character ?? null);
  say(dropped.length ? `Restored your last setup, without ${dropped.join("; ")}`
    : `Restored your last setup: ${ticked.length} pack${ticked.length === 1 ? "" : "s"} on. Reset to defaults clears it.`);
  const back = () => {
    remember();   // what is left of it
    start();
  };
  if (community?.length) state.community.set(community).finally(back);
  else back();
}

// Reset to defaults: the packs on by default, every setting at its default, no config.xbr cell; a remembered setup
// forgotten, Remember settings left as it is (ticked, the next change is remembered again, so the status says what
// happened, not what is kept; it names a forgotten setup only when one was kept).
function reset() {
  const kept = state.kept != null;
  state.community.clear();
  state.replace.set([]);
  setTo(new Set(state.packs.packs.filter((pack) => pack.default_on).map((pack) => pack.name)), {}, []);
  setRando(randoDefaults());
  state.characters.set(null);
  state.loaded = null;
  unlinked();
  pick("patches");
  remember();
  say("Reset to the defaults: the packs on by default, every setting at its default, Randomize off"
      + (kept ? "; the remembered setup is forgotten." : "."));
}

// The page's address drops a link's #p= once the page no longer holds that recipe, so a reload restores the setup.
function unlinked() {
  if (!state.app && location.hash) history.replaceState(null, "", location.pathname + location.search);
}

// The share link: the engine makes the fragment of what the page holds (with the build's hashes when it is the
// page's current build); the link is shown, and copied where the browser lets it.
function share() {
  if (!state.ready) return say("AzurKit is still loading: try again in a moment", true);
  state.engine.preset(recipe(), state.build?.report ?? null);
}

// What the page holds as a recipe (a share link's, a mods file's): the ticked packs, a loaded recipe's config.xbr
// operations, the randomizer while Randomize is ticked and the character worn.
function recipe() {
  const randomizer = randoRecipe(), character = state.characters.character();
  return { packs: chosen(), xbr: state.xbr, ...(randomizer ? { randomizer } : {}), ...(character ? { character } : {}),
           ...extras() };
}

// Where the Tools tab's save goes in the app: its save dialog's choice beside the build's output (null: cancelled),
// else "" (no dialogs: the engine's place, the Downloads folder).
async function toolsOut(name, kind) {
  if (!state.dialogs) return "";
  const beside = $("out-path").value ? $("out-path").value.replace(/[^\\/]*$/, name) : name;
  return state.engine.choose(kind, beside).catch((error) => (say(error.message, true), null));
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

// The picked image is an AzurKit build: offer its recipe (sdk.open_build checked the files it changed against it). A
// reply for an image no longer picked (file, the one it was asked of) is dropped, as vanilla()'s.
function opened(preset, file = state.file) {
  if (file !== state.file) return;
  state.opened = preset;
  const packs = Object.keys(preset.layers.find((layer) => layer.tool === "mods")?.recipe ?? {}).length;
  const label = preset.base?.release === "europe" ? "Europe" : "USA";
  const rando = preset.layers.find((layer) => layer.tool === "randomizer")?.recipe, seed = rando?.seed ?? rando?.plan?.seed;
  $("picked").textContent = `◆ AzurKit build · ${label} · ${packs} packs${seed === undefined ? "" : ` · seed ${seed}`}: `
    + "load its recipe, then pick your vanilla image to build it again.";
  $("load-build").hidden = false;
  busy(state.building);   // Build greyed: an AzurKit build isn't built from
}

function unopen() {
  state.opened = null;
  $("load-build").hidden = true;
  busy(state.building);
}

// The engine is ready (the site's again after each build). The first time, the page draws the catalog and asks for the
// remembered setup back (only Remember settings keeps one, D1156), unless a link brought a recipe (D915: the link
// wins); it is ready once that is back.
function ready(catalog, version, commit, platform) {
  if (!state.packs) {
    if (!state.app && "serviceWorker" in navigator) registered();
    state.packs = catalog;
    renderTabs(catalog.tabs);
    renderPacks(catalog);
    renderRando(catalog.randomizer);
    state.tracker = tracker({ call: state.engine.call, app: state.app, say, kept: state.tracked, keep: keepTracked,
                              image: () => state.file, tray: state.app ? trackTray : null });
    if (state.app) {
      player({ call: state.engine.call, say, saved: () => state.played, attach: state.host.attach,
               choose: state.dialogs ? () => state.engine.choose("xemu", "") : null,
               track: (plan) => {   // Play's build: its seed tracked, Live on (its xemu holds no disc yet to read)
                 pick("randomizer");
                 randoPane("tracker");
                 state.tracker.open(plan);
                 return state.tracker.live(true, false);
               },
               live: () => {
                 pick("randomizer");
                 randoPane("tracker");
                 return state.tracker.live(true);
               } });
    }
    const shared = content({ call: state.engine.call, app: state.app, host: { ...state.host, catalog },
                             handoff: state.engine.content });
    state.characters = characters({ call: state.engine.call, app: state.app, host: { ...state.host, catalog }, say,
                                    image: () => state.file, packs: chosen, changed: state.changed, shared,
                                    settled: ahead, busy: () => state.building || state.saving,
                                    edit: (name) => {
                                      charPane("variants", false);
                                      state.variants.edit(name);
                                    } });
    state.variants = variantsView({ root: $("variants"), call: state.engine.call, app: state.app, say,
                                    image: () => state.file, packs: chosen, share: state.engine.library,
                                    dialog: state.dialogs ? (kind, path) => state.engine.choose(kind, path) : null,
                                    changed: () => state.characters.relist(), shared, unsaved: state.engine.unsaved });
    state.community = communityGroup({ root: $("packs"), call: state.engine.call, shared, say, catalog,
                                       settled: () => { tally(); lock(); } });
    state.data = dataTab({ call: state.engine.call, root: $("data"), say, packs: chosen, image: () => state.file,
                           app: state.app, changed: (ops) => {
                             state.xbr = ops;
                             noteXbr();
                             state.changed();
                           } });
    state.tools = tools({ root: $("tools"), call: state.engine.call, app: state.app, say, image: () => state.file,
                          known: () => (state.read === state.file && state.imageInfo ? { ...state.imageInfo } : null),
                          out: toolsOut, pick: state.dialogs ? () => state.engine.choose("build", "") : null,
                          setup: recipe, load, track: trackBuild });
    state.replace = replaceFiles({ root: $("tools"), call: state.engine.call, app: state.app, say,
                                   image: () => state.file, changed: state.changed,
                                   pick: state.dialogs ? () => state.engine.choose("replacement", "") : null });
    state.saves = savesSection({ root: $("tools"), call: state.engine.call, app: state.app, say, image: () => state.file,
                                 out: (name) => toolsOut(name, "saves"),
                                 pick: state.dialogs ? (kind) => state.engine.choose(kind, "") : null });
    $("version").textContent = `AzurKit ${version}`;
    $("about-version").textContent = `This is AzurKit ${version}, ${commit ? `built from commit ${commit.slice(0, 12)}`
      : "its commit is unknown (built or run without git)"}.`;   // the engine's azurkit.commit()
    $("about-platform").textContent = `Platform: ${platform}${state.app ? "" : ", in your browser"}.`;   // azurkit.platform()
    launched(2);
    if (!state.pending && state.remembered != null) {
      state.restoring = true;   // a remembered community pack is read from what the site hands its engine first
      return Promise.all([state.remembered.community ? shared.ready : null, state.variants.ready])   // yours worn too
        .then(() => state.engine.restore(state.remembered))
        .finally(() => {   // a restore that failed (refused, or its engine stopped): the page is its own all the same
          if (!state.restoring) return;   // restored() took it
          state.restoring = false;
          if (!state.ready) start();
        });
    }
  }
  start();
}

function start() {
  state.ready = true;
  $("remember").disabled = false;
  if (state.launch) answered(state.launch);
  state.launch = null;
  busy(state.building);
  // a link's community pack or variant is checked against what the site hands its engine first
  if (state.pending) state.community.ready.then(() => state.engine.decode(state.pending));
  askVanilla();
  if (state.rando.waiting) askRando(state.rando.given);
}

function report(text, error = false) {
  busy(false);
  say(text, error);
}

// Firefox's blob: URL of a Blob of more than about 8 parts (or a part of 1 MiB in memory) makes its parent process copy the
// whole Blob into memory at createObjectURL, and hold about 2 GiB more over a download; a Blob of few parts, each a slice
// of a file, it reads by reference, its tree flat. So there the KEPT longest copies stay the
// File's slices and all between them goes once into a build file of its own (outputs.mjs's written(): a worker's sync
// writes, a run of FLAT_RUN at a time, heard(the share written) after each, so its bar moves, D980): at most
// 2 x KEPT + 1 parts, the same bytes, {blob, name}. It runs ahead of the Save, after the build's answer, Save greyed and
// its own bar moving until it ends, so a click never waits for it (D979, D1053). A Response's Blob of those bytes (the
// temporary file Firefox keeps it in) took 3.7x the CPU: a seed's 835 MB 1.4 s and 4.1 CPU-s against 0.9 s and 1.1 on a
// quiet box, and on a busy one R24 waited 4-7 s for it (Step 4.5q). A private window
// refuses the origin's private file system (and keeps a Response's Blob in memory, a part that brings the parent's copy
// back on top of the tab's: 7.2 GiB against the plain Blob's 4.8), so it keeps the plain Blob. Where the file system
// is there but the writer fails (a full disk's quota, a refused handle, its worker stopped), the bytes go into a
// Response's Blob, Firefox's temporary file, as before Step 4.5q (copied()); its failure too leaves the plain Blob, so
// Save always opens (Step 4.5u). The worker joined the build's Blob (Step 4.3r4l); its pieces are its slices, each
// segment's, a copy's a slice of the File.
const URL_COPIES = /Firefox\//.test(navigator.userAgent), KEPT = 3, FLAT_RUN = 16 << 20;
async function byReference(segments, blob, heard = () => {}) {
  await navigator.storage.getDirectory();
  let start = 0;
  const parts = segments.map((s) => blob.slice(start, start += s.size));
  const kept = new Set(segments.map((s, i) => [s, i]).filter(([s]) => s.kind === "copy")
    .sort((a, b) => b[0].size - a[0].size).slice(0, KEPT).map(([, i]) => i));
  const rest = new Blob(parts.filter((_, i) => !kept.has(i)));
  heard(0);
  const { file: between, name } = await written(rest, FLAT_RUN, heard).catch(() => copied(rest, heard));
  heard(1);
  const flat = [];
  let at = 0, run = 0;
  const stretch = () => {
    if (run) flat.push(between.slice(at, at + run));
    at += run;
    run = 0;
  };
  for (const [i, part] of parts.entries()) {
    if (kept.has(i)) {
      stretch();
      flat.push(part);
    } else {
      run += segments[i].size;
    }
  }
  stretch();
  return { blob: new Blob(flat, { type: "application/octet-stream" }), name };
}

// rest's bytes as a Response's Blob, read a run of FLAT_RUN at a time, heard(the share read) after each: {file}.
async function copied(rest, heard) {
  let read = 0;
  heard(0);
  const file = await new Response(new ReadableStream({
    async pull(out) {
      if (read >= rest.size) return out.close();
      out.enqueue(new Uint8Array(await rest.slice(read, read += FLAT_RUN).arrayBuffer()));
      heard(Math.min(read / rest.size, 1));
    },
  }, { highWaterMark: 0 })).blob();
  return { file };
}

function built(reply) {
  const { report: made, size } = reply;
  if (state.app) {
    state.build = { report: made, size, recipe: reply.recipe, out: reply.out, id: reply.build };
    $("out-path").value = reply.out;
    $("out-row").hidden = state.dialogs;
  } else {
    const { blob } = reply;   // joined in the worker, off this thread
    if (blob.size !== size) return report(`The build's pieces make ${bytes(blob.size)}, not ${bytes(size)}`, true);
    const build = { report: made, size, segments: reply.segments, file: state.file, blob, checks: reply.checks,
                    late: reply.late, out: reply.out, saved: false };
    state.build = build;
    if (URL_COPIES) {
      const making = asking("flat");
      const heard = (share) => {   // the bar's record, shown at each percent
        const ask = state.asks.get(making), percent = Math.floor(share * 100);
        if (!ask || ask.record?.percent === percent) return;
        ask.record = { stage: "write", label: READYING, done: percent, total: 100, percent };
        showing();
      };
      build.flat = byReference(reply.segments, blob, heard).catch(() => ({ blob })).then(({ blob: flat, name }) => {
        answered(making);   // none: still its bytes
        build.blob = flat;
        build.between = name;
        if (state.build !== build) return void (name && letGo(name));   // forgotten while it was made
        state.url = URL.createObjectURL(flat);
        busy(state.building);
      });
    } else {
      state.url = URL.createObjectURL(blob);
    }
  }
  const changed = Object.keys(made.result), rz = made.randomizer;
  const verdict = !rz ? "" : ` · seed ${rz.seed} · ${rz.share} · ${rz.logic_verified ? "promised beatable"
    : `⚠ not promised beatable: ${rz.why_not[0]}${rz.why_not.length > 1 ? ` (+${rz.why_not.length - 1} more)` : ""}`}`;
  const communal = made.layers.filter((layer) => layer.id.startsWith("community ")).map((layer) => ` · ${layer.id}`);
  report(`Ready · ${made.label} · ${bytes(size)}${verdict}${communal.join("")}` + made.conflicts.map((c) => ` · conflict: ${c}`).join("")
         + made.notes.map((n) => ` · note: ${n}`).join("")
         + ` · changed: ${changed.length ? changed.join(", ") : "nothing"}`);   // the file list last: it runs long
  ingame(made.ingame);
  spoiler(made.spoiler ?? null, !made.plan || made.spoiler ? null : reply.spoiled ? () => reply.spoiled
    : () => state.engine.call("spoiler", {}));   // the app's engine makes it when View or Save asks
  if (made.plan && state.saveCheck === "running") state.tracking = made.plan;   // after the check (checkSave)
  else if (made.plan) state.tracker.open(made.plan);   // the Tracker view tracks the build's seed
  state.tools.built(made);
}

// The site's Save: while the browser writes the Blob, the same Blob's files are hashed against the build's and, for the
// files a build doesn't read, the release's (sdk.image_checks; D35). A File changed on disk since the pick fails the read
// in WebKit and Chromium, at the Build as at the Save, and reads otherwise in Firefox, silently; the build's own shas
// would pass one changed before the Build, being hashed from it, so where a read may be silent (READS_REFUSED false) the
// File's copy of each file the build changed is hashed against the release's first. (Everywhere, it costs S50/lag 4.1 s.)
// A browser's download can't be stopped from here, so the Save fails by name, with what to do. Its bar is the page's own
// (D1053). Where a read is refused (Step 4.4ba), a file of the Blob that is a copy of the File at its own offset, and
// there in the File too (the build's segments and checks say so), is known by the sha256 the page was told of it,
// hashed from that File (state.vouched by the image's id: worker.mjs's vouched(), and the files a Save here passed),
// so only the rest is hashed, beside one read of the File, which the browser refuses once it changed. A changed file's
// bytes are the build's, hashed at every Save. state.saveCheck: "running", "held", or the failure's line. The site's
// work ahead and a built seed's Tracker view wait for it (aheadOnSite, built()). A Save while the image's rest is
// hashed in the background (state.resting by the image's id, the worker's "resting" messages) waits for those digests
// for the in-place files the page doesn't know yet, its bar moving with the rest's, and hashes only the build's files
// meanwhile, then any the rest didn't vouch for (its worker stopped, a read refused): the same files read and hashed
// twice at once made S06/lag wait on its check, 1.5-1.8 s against the download's 1.3-1.6 (Step 4.4bl). It holds
// hasher.mjs's WAITED while it waits, so the rest no longer gives way to a dress and reads at a Save's width.
const READS_REFUSED = /AppleWebKit/.test(navigator.userAgent);
function rested(data, worker) {   // a worker's rest of the image data.id: its progress, or its end
  let rest = state.resting.get(data.id);
  if (data.type === "resting") {
    if (!rest) {
      rest = { worker, done: 0, total: 0, heard: new Set() };
      rest.settled = new Promise((settle) => { rest.settle = settle; });
      state.resting.set(data.id, rest);
    }
    Object.assign(rest, { done: data.done, total: data.total });
    rest.heard.forEach((heard) => heard());
  } else if (rest?.worker === worker) {
    state.resting.delete(data.id);
    rest.settle();
  }
}
function inPlace(segments) {   // whether [start, end) of the Blob is the File's own bytes there
  const spans = [];
  let at = 0;
  for (const s of segments) {
    if (s.kind === "copy" && s.offset === at) {
      if (spans.at(-1)?.[1] === at) spans.at(-1)[1] += s.size;
      else spans.push([at, at + s.size]);
    }
    at += s.size;
  }
  return (start, end) => spans.some(([from, to]) => from <= start && end <= to);
}
async function checkSave(build, name) {
  if (build.checking) return;
  build.checking = true;
  state.saveCheck = "running";
  const id = asking("save_check");
  const sized = (rows) => rows.reduce((n, [, , size]) => n + size, 0);
  const copied = READS_REFUSED ? inPlace(build.segments) : () => false;
  const own = ([, at, size, , from]) => from === at && copied(at, at + size);
  const knows = (row) => state.vouched.get(build.checks.id)?.[row[0]] === row[3];   // read again once a rest ends
  const rows = build.checks.image.filter((row) => !(own(row) && knows(row)));
  const rest = READS_REFUSED && state.resting.get(build.checks.id), waits = rest ? rows.filter(own) : [];
  const passes = [[build.blob, rest ? rows.filter((row) => !own(row)) : rows]];
  if (!READS_REFUSED) passes.unshift([build.file, build.checks.input]);
  const whole = passes.reduce((n, [, rows]) => n + sized(rows), 0) + sized(waits);
  let before = 0, now = 0, waited = 0, wrong = null;
  const show = () => {
    const ask = state.asks.get(id), at = Math.floor(before + now + waited);
    if (ask) ask.record = { stage: "write", label: "Saving", done: at, total: whole, percent: Math.floor(at * 100 / whole) };
    showing();
  };
  const heard = (share) => (done, total) => {
    now = share * done / total;
    show();
  };
  const hashed = async (source, rows, progress) => {
    const digests = await hashedApart(source, rows.map(([path, at, size]) => [path, at, size]), progress);
    const file = rows.find(([path, , , sha]) => digests[path] !== sha)?.[0];
    return file ? `its ${file} isn't the build's or the game's` : null;
  };
  const hashing = async () => {
    for (const [source, rows] of passes) {
      if (!rows.length) continue;
      const share = sized(rows), failed = await hashed(source, rows, heard(share));
      if (failed) return failed;
      before += share;
      now = 0;
    }
    return null;
  };
  const waiting = async () => {   // the rest's digests for the in-place files, then a hash of those it didn't vouch for
    if (!waits.length) return null;
    const share = sized(waits), heard = () => {
      waited = share * (rest.total ? rest.done / rest.total : 0);
      show();
    };
    rest.heard.add(heard);
    heard();
    navigator.locks?.request(WAITED, { mode: "shared" }, () => rest.settled).catch(() => null);   // Locks refused: no rest
    await rest.settled;
    rest.heard.delete(heard);
    const left = waits.filter((row) => !knows(row)), from = waited;
    if (!left.length) {
      waited = share;
      show();
      return null;
    }
    return hashed(build.blob, left, (done, total) => {
      waited = from + (share - from) * done / total;
      show();
    });
  };
  try {
    const checks = await Promise.all([hashing(), waiting(), READS_REFUSED && build.file.slice(0, 1).arrayBuffer()]);
    wrong = checks[0] ?? checks[1] ?? null;
  } catch (error) {
    wrong = `reading it failed (${error.message})`;
  }
  if (!wrong && READS_REFUSED && build.checks.id) {   // its own copies hashed now are known for the next Save
    const vouched = { ...state.vouched.get(build.checks.id) };
    for (const row of [...passes[0][1], ...waits]) if (own(row)) vouched[row[0]] = row[3];
    state.vouched.set(build.checks.id, vouched);
  }
  answered(id);
  build.checking = false;
  state.saveCheck = wrong ? `Save failed: your image changed since you picked it or isn't a clean copy, so ${name} is `
    + `wrong: ${wrong}. Delete the saved file, choose a clean image and build again` : "held";
  if (wrong) {
    if (state.build === build) forget();
    say(state.saveCheck, true);
  } else if (state.build === build) {
    say(`Saved ${name} (${bytes(build.size)}), each of its files the build's; your browser's download shows its progress`);
  }
  const tracked = state.tracking;   // what waited for the check
  state.tracking = null;
  if (tracked) state.tracker.open(tracked);
  ahead();
}

function saved({ saved: done }) {
  state.saved = done;
  state.played = { out: done.out, plan: state.build?.report.plan ?? null };   // what Play plays (the app's)
  state.tools.built(done, done);   // the save's report (its build's, or the one it built again) and where it went
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
  asking("save");
  state.engine.save(state.build.recipe, out, state.build.id);   // the image Build made, hashed since
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
    state.gen++;
    state.file = $("iso-path").value.trim() || null;
    $("picked").textContent = host.dialogs ? "Type the image's full path, or Choose… it."
      : "Type the image's full path: a browser can't tell AzurKit where a file is.";
    say("");
    busy(false);
    askVanilla();
    state.tracker?.draw();   // the tracker's maps are drawn from it, if they aren't yet
    state.characters?.imaged();
    state.data?.imaged();
    state.tools?.imaged();
    state.replace?.imaged();
    state.saves?.imaged();
    state.variants?.imaged();
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
// Its options come from the catalog (sdk.catalog's randomizer: D144's defaults, the tiers and ceilings,
// the item rows); the engine reads what they give (sdk.randomizer_settings): the share string, each skip a setting can
// turn on, what a build would leave unverified (the ⚠ line) and the preflight's refusal. The page holds the settings
// as a settings file's table in format /2 (each unticked row's category, as it is) and decides no plan.
const randoOptions = () => state.packs.randomizer;
const WARP = "qol_save_warp";   // the save-point warp's pack: the tab's Save-point warp box mirrors its tick (D1154)
const warpPack = () => $("packs").querySelector(`input[data-pack="${WARP}"]`);

// The tab's Save-point warp box as the pack's tick (the logic counts the warp while it is ticked); a loaded setting
// that counts the warp ticks the pack, marked ● where `from` changed it.
function syncWarp(settings = null, from = null) {
  const box = warpPack();
  if (box && settings?.save_warp && !box.checked) {
    box.checked = true;
    linked(box);
    tally();
    lock();
    const mark = box.closest(".pack").querySelector(".name .mark");
    mark.textContent = from ? "●" : "";
    mark.title = from ? `Changed by ${from}` : "";
  }
  R("warp").checked = Boolean(box?.checked);
}
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
  choices(R("difficulty"), options.seed_difficulty, options.tips.seed_difficulty);
  R("cost-note").textContent = `vanilla ${options.obsidian_cost}`;   // D910
  // Each item row: its box, its icons (the icon sheet's tiles), its name, how many the base game places, its note
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
// toggles the skip list's.
function randoSettings() {
  const { defaults, categories } = randoOptions();
  const kept = new Set([...R("items").querySelectorAll("input[data-category]")].filter((box) => !box.checked)
    .map((box) => box.dataset.category));
  const ceiling = Number(R("ceiling").value), level = R("difficulty").value;
  return { format: defaults.format, skip_ceiling: ceiling, movement_tier: R("movement").value,
           dark_fire: defaults.dark_fire, ...(level !== "Normal" ? { seed_difficulty: level } : {}),
           ...(warpPack()?.checked ? { save_warp: true } : {}),
           exclude_categories: categories.filter((c) => kept.has(c)),
           skip_override: Object.fromEntries(Object.entries(state.rando.overrides).sort()) };
}

// A skip as it stands: its toggle, else the ceiling's state of it: true, false, or null (some of a batch's variants).
function skipOn(skip) {
  return state.rando.overrides[skip.id] ?? byCeiling(skip);
}

// The ceiling's state of a skip by the Skips select as it is now, not by the last answer's: a click right after a
// Skips change writes its toggles against the new ceiling.
function byCeiling(skip) {
  const ceiling = Number(R("ceiling").value), n = skip.ratings.filter((rating) => rating <= ceiling).length;
  return n > 0 && n < skip.ratings.length ? null : n === skip.ratings.length;
}

// A skip group's tick turns on all its picks, whatever their rating, its untick all off (D1061, amending D258), each by
// a toggle only where the ceiling doesn't say so already: what's on is what the plan uses.
function turnGroup(id, on) {
  const { groups, skips } = state.rando.view;
  for (const pick of groups.find((group) => group.id === id).picks) {
    if (byCeiling(skips.find((skip) => skip.id === pick.id)) === on) delete state.rando.overrides[pick.id];
    else state.rando.overrides[pick.id] = on;
  }
}

// The skip groups' boxes, each what's on of it (ticked all, half some, empty none), so a loaded setting's show too,
// with how many of its picks are on and its highest rating, so a tick hides no Frame-perfect pick; and the closed
// list's count of what's on.
function renderGroups() {
  const view = state.rando.view, all = (view?.skips ?? []).map(skipOn);
  const part = all.filter((value) => value === null).length;
  if (view) R("skip-count").textContent = `${all.filter((value) => value === true).length} of ${all.length} on`
    + (part ? ` · ${part} in part` : "");
  R("groups").replaceChildren(...(view?.groups ?? []).map((group) => {
    const on = group.picks.map((pick) => skipOn(view.skips.find((skip) => skip.id === pick.id)));
    const full = on.filter((value) => value === true).length;
    const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: full === on.length,
                                                                 indeterminate: full < on.length && on.some((value) => value !== false),
                                                                 disabled: state.building || !R("on").checked
                                                                   || Boolean(state.rando.plan) });
    box.dataset.group = group.id;
    const row = Object.assign(document.createElement("label"), { className: "group", title: [
      ...(group.tip ? [group.tip] : []),
      ...group.picks.map((p, i) => `${on[i] === true ? "☑" : on[i] === false ? "☐" : "◪"} ${p.name}: ${p.rating}`)].join("\n") });
    row.append(box, group.label, Object.assign(document.createElement("span"), { className: "note",
                                                                                textContent: `${full} of ${on.length} · up to ${group.top}` }));
    return row;
  }));
}

// The obsidian cost as the engine gets it: none at vanilla's (or an empty box), else the number or the text typed.
function randoCost() {
  const text = R("cost").value.trim(), cost = text ? typed(text) : randoOptions().obsidian_cost;
  return cost === randoOptions().obsidian_cost ? {} : { obsidian_cost: cost };
}

// The build's randomizer: the seed, the settings and the obsidian cost (or an open plan file and the cost), or null
// while Randomize is off.
function randoRecipe() {
  if (!state.packs || !R("on").checked) return null;
  if (state.rando.plan) return { plan: state.rando.plan.doc, ...randoCost() };
  return { seed: R("seed").value.trim(), settings: randoSettings(), ...randoCost() };
}

// The engine's answer while Randomize is on and its preflight refuses the items as they are ticked (AZ-454: too few
// proven spots for the progression items once some rows stay vanilla), else null: Build greys on it (Step 4.4u1). An
// answer for other items is stale: the next one decides.
function randoStarved() {
  const view = state.rando.view;
  if (!state.packs || !R("on").checked || !view?.preflight) return null;
  return String(view.settings.exclude_categories) === String(randoSettings().exclude_categories) ? view : null;
}

// What the page remembers of the tab with Remember settings ticked (D915, D1156): nothing at its defaults (off, D144's
// settings, vanilla's cost). The settings' save_warp is the qol_save_warp pack's tick (D1155), which the setup's packs
// keep: alone it leaves the tab at its defaults. A seed past SEED_MAX characters (any one builds) is left out, the rest
// kept: the engine remembers none longer (randomizer.remembered), and refused it would take the whole setup with it.
const SEED_MAX = 256;
function randoSetup() {
  const settings = randoSettings(), cost = randoCost(), seed = R("seed").value;   // its characters, as Python counts
  const plain = !R("on").checked && !("obsidian_cost" in cost)
    && JSON.stringify({ ...settings, save_warp: undefined }) === JSON.stringify(randoOptions().defaults);
  return plain ? null : { on: R("on").checked, seed: [...seed].length <= SEED_MAX ? seed : "", settings,
                          ...(typeof cost.obsidian_cost === "number" ? cost : {}) };
}

// Set the tab to `rando` (the engine's: its settings as the tab holds them, and the plan file it builds, if any),
// marked ● where `from` (a link, a build, a plan file) changed it; then ask the engine what they give.
function setRando({ on, seed, settings, obsidian_cost: cost, plan = null }, from = null) {
  const before = JSON.stringify(randoSetup());
  state.rando.plan = plan;
  renderPlan();
  state.rando.note = null;
  R("on").checked = on;
  R("seed").value = seed;
  R("movement").value = settings.movement_tier;
  R("ceiling").value = String(settings.skip_ceiling);
  for (const box of R("items").querySelectorAll("input[data-category]")) {
    box.checked = !settings.exclude_categories.includes(box.dataset.category);
  }
  state.rando.overrides = { ...settings.skip_override };
  R("difficulty").value = settings.seed_difficulty ?? "Normal";
  R("cost").value = String(cost ?? randoOptions().obsidian_cost);
  syncWarp(settings, from);
  const mark = $("randomizer").querySelector(".on .mark");
  mark.textContent = from && JSON.stringify(randoSetup()) !== before ? "●" : "";
  mark.title = mark.textContent ? `Changed by ${from}` : "";
  offered();
  lockRando();
  gate();
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
    gate();
    return;
  }
  const plan = rando.plan ? { doc: rando.plan, name: from } : null;
  state.rando.load = { on: true, seed: String(rando.seed ?? rando.plan.seed), obsidian_cost: rando.obsidian_cost, from,
                       plan };
  askRando({ ...(plan ? { plan: plan.doc } : rando.share !== undefined ? { share: rando.share }   // a seed alone: D144's
                 : { settings: rando.settings ?? randoOptions().defaults }),   // defaults
             obsidian_cost: rando.obsidian_cost ?? randoOptions().obsidian_cost });
}

// Ask the engine what the tab's settings give (or `given`'s: a recipe's or a typed share string, whose settings become
// the tab's), once it is ready, while the tab shows, Randomize is ticked (Build greys on the answer, a restored setup's
// too) or a recipe waits on it (the database loads at the first ask); only the latest ask's answer is taken, `wait` ms
// after the last change (a tab's open: at once).
function askRando(given = null, wait = 100) {
  clearTimeout(state.rando.later);
  const ticket = ++state.rando.ticket;
  if (given) state.rando.given = given;
  if (given) state.rando.asked = given.share ?? null;   // a share string loaded: its AZ-383 note's own
  if (!state.rando.given && state.tab !== "randomizer" && !R("on").checked) return;
  state.rando.waiting = true;
  if (!state.ready || state.building) return;
  state.rando.later = setTimeout(() => {
    const asked = state.rando.given ?? (state.rando.plan ? { plan: state.rando.plan.doc } : { settings: randoSettings() });
    state.rando.given = null;
    const character = state.characters?.character() ?? null;   // its size folds into the walk and roll, as a build's
    state.engine.randomizer({ ...randoCost(), ...asked, packs: chosen(), ...(character ? { character } : {}) }, ticket,
                            character ? state.file : null);
  }, wait);
}

// The engine's answer: the settings it read (a loaded recipe's become the tab's), the share string, the skips, the
// facts and the ⚠ line; a refusal shows on the ⚠ line, the tab as it was.
function randoView(reply, ticket) {
  if (ticket !== state.rando.ticket) return;
  state.rando.waiting = false;
  if ("refused" in reply) {
    const from = state.rando.load?.plan ? `${state.rando.load.from}: ` : "";   // a plan file refused: named
    state.rando.load = null;
    return warn([from + reply.refused], true);
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
  renderLevels(reply.difficulty);
  R("share").value = reply.share;
  R("held").textContent = `${reply.skips.length} turnable · ${reply.held} held (no setting turns one on)`;
  R("facts").textContent = `Accessibility: full · Victory: Spideyzar · Excluded: lock 10 + full-clear · `
    + `${reply.forfeitable} forfeitable`;
  renderSkips();
  renderGroups();
  gate();
  const note = reply.note ?? state.rando.note;
  warn([...(reply.preflight ? [`Can't make a seed: ${reply.preflight}.`] : []), ...(note ? [note] : []),
        ...(reply.body ? [reply.body] : []),
        ...reply.why_not.map((why) => `Not promised beatable (flagged, not refused): ${why}`)], Boolean(reply.preflight));
  remember();
}

// The engine's levels (D1157: each offered at any settings): the line under the select the chosen level's; the
// tooltip holds them all.
function renderLevels({ levels }) {
  const select = R("difficulty"), chosen = levels.find(([value]) => value === select.value);
  for (const option of select.options) option.title = levels.find(([value]) => value === option.value)[3];
  select.title = [randoOptions().tips.seed_difficulty, ...levels.map(([, name, , line]) => `${name}: ${line}`)].join("\n");
  R("difficulty-line").textContent = chosen?.[3] ?? "";
  R("difficulty-line").hidden = false;
}

function warn(lines, error = false) {
  R("warn").hidden = !lines.length;
  R("warn").textContent = lines.map((line) => `⚠ ${line}`).join("\n");
  R("warn").classList.toggle("error", error);
}

// The skips a setting can turn on, filtered, in their groups' order under a thin heading: each ticked when it is on
// (half when only some of a batch's variants are, by the ceiling), by the ceiling or by its own toggle, which a click
// sets and a click back to the ceiling's clears. The rows stay rendered while their list is closed.
function renderSkips() {
  const filter = R("filter").value.trim().toLowerCase(), view = state.rando.view;
  const shown = (s) => !filter || `${s.name} ${s.id} ${s.rating}`.toLowerCase().includes(filter);
  R("skips").replaceChildren(...(view?.groups ?? []).flatMap((group) => {
    const rows = group.picks.map((pick) => view.skips.find((skip) => skip.id === pick.id)).filter(shown);
    return rows.length ? [Object.assign(document.createElement("h4"), { textContent: group.label }), ...rows.map(skipRow)] : [];
  }));
}

function skipRow(skip) {
  const toggle = state.rando.overrides[skip.id] ?? null, on = skipOn(skip);
  const row = Object.assign(document.createElement("label"), { className: `skip${toggle === null ? "" : " toggled"}`,
                                                               title: `${skip.name} (${skip.id}): ${skip.rating}` });
  const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: on === true,
                                                               indeterminate: on === null });
  box.dataset.skip = skip.id;
  box.disabled = state.building || !R("on").checked || Boolean(state.rando.plan);
  row.append(box, Object.assign(document.createElement("span"), { className: "name", textContent: skip.name }),
             Object.assign(document.createElement("span"), { className: "rating", textContent: skip.rating }),
             Object.assign(document.createElement("span"), { className: "by", textContent: toggle !== null ? "toggle" : "ceiling" }));
  return row;
}

// A click turns a skip (a batch whole) the other way: by a toggle, or by none when the ceiling now gives that.
function toggleSkip(id) {
  const def = byCeiling(state.rando.view.skips.find((s) => s.id === id));
  const toggle = state.rando.overrides[id] ?? null, turned = (toggle === null ? def : toggle) !== true;
  if (turned === def || (def === null && toggle === false)) delete state.rando.overrides[id];
  else state.rando.overrides[id] = turned;
}

// The tab's settings are locked (still readable) until Randomize is ticked, and while a build runs (D907); an open plan
// file locks its seed and settings too, all but the obsidian cost (Modkit's --plan takes --obsidian-cost).
function lockRando() {
  const off = state.building || !R("on").checked, open = new Set(["cost", "copy", "save", "filter", "plan", "plan-close"]);
  R("on").disabled = state.building || !state.packs;
  for (const field of $("randomizer").querySelectorAll(".rando-top :is(input, select, button), #rando-share, "
    + "#rando-copy, #rando-filter, #rando-clear, #rando-items input[data-category], #rando-skips input, "
    + "#rando-groups input, #rando-load, #rando-save, #rando-warp, #rando-plan, #rando-plan-close")) {
    if (field !== R("on")) field.disabled = off || (Boolean(state.rando.plan) && !open.has(field.id.slice(6)));
  }
}

// Open a plan… (Modkit's randomize-full --plan, P31): a plan file's object, which the engine reads back and checks
// beatable under its own settings (sdk.randomizer_settings' plan) and a build takes as it is: the tab shows its seed
// and settings, locked, until Close plan; a refusal names the file.
async function openPlan() {
  const file = R("plan").files[0];
  R("plan").value = "";
  if (!file) return;
  let doc = null;
  try {
    doc = JSON.parse(await file.text());
  } catch {}
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) {
    return warn([`${file.name}: not a plan file (not a JSON object)`], true);
  }
  const plan = { doc, name: file.name };
  state.rando.load = { on: true, seed: String(doc.seed), obsidian_cost: randoCost().obsidian_cost, from: file.name, plan };
  askRando({ plan: doc, ...randoCost() });
}

function renderPlan() {
  const plan = state.rando.plan;
  R("plan-line").hidden = !plan;
  R("plan-name").textContent = plan ? `Building a plan file as it is (${plan.name}: seed ${plan.doc.seed}, plan `
    + `${String(plan.doc.sha256).slice(0, 12)}): its seed and settings are locked.` : "";
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
// site's download, or where the app's dialog (else beside the image it saves) says. A seed's build leaves it out, so
// the build shows sooner: later() gives it (the site's worker sends it after the build; the app's engine makes it at
// the first View or Save), asked once.
let later = null, coming = null;
function spoiler(text, ask = null) {
  state.spoiler = text;
  later = text ? null : ask;
  coming = null;
  $("spoiler-view").disabled = $("spoiler-save").disabled = !text && !later;
  $("spoiler-note").hidden = Boolean(text || later);
  if (!text) $("spoiler").hidden = true;
  $("spoiler").textContent = text ?? "";
  $("spoiler-view").textContent = $("spoiler").hidden ? "View" : "Hide";
}

async function spoilt() {   // the spoiler's text, null when the engine refused it (said)
  if (state.spoiler === null && later) {
    const mine = later, reply = await (coming ??= later());
    if (mine !== later) return null;   // another build since
    if ("refused" in reply) {
      coming = null;
      say(reply.refused, true);
      return null;
    }
    spoiler(reply.text);
  }
  return state.spoiler;
}

async function saveSpoiler() {
  const stem = (state.app ? $("out-path").value.split(/[\\/]/).pop() : state.file.name).replace(/\.x?iso$/i, "")
    .replace(/ \(AzurKit\)$/, "");
  const name = `${stem} (AzurKit) spoiler.txt`;
  if (!state.app) {
    if (!await spoilt()) return;
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

// Track this build (the Tools tab's Open a build…): a randomized build's own plan, replayed by the engine from the seed
// and share string its manifest holds (sdk.plan: the plan its build wrote), on the Randomizer tab's Tracker; nothing
// is retyped, and the tab's settings stay as they are.
async function trackBuild(preset, from) {
  const rando = preset.layers.find((layer) => layer.tool === "randomizer")?.recipe;
  if (!rando) return say(`${from} isn't randomized: it has no plan to track`, true);
  if (rando.plan) {   // built from a plan file: that plan
    pick("randomizer");
    randoPane("tracker");
    return state.tracker.open(rando.plan, from);
  }
  const { seed, share, settings } = rando;
  say(`Planning ${from}'s seed ${seed} to track it…`);
  const asked = { seed, ...(share !== undefined ? { share } : { settings }) };
  const reply = await state.engine.call("plan", { recipe: asked });
  if ("refused" in reply) return say(reply.refused, true);
  pick("randomizer");
  randoPane("tracker");
  state.tracker.open(reply.plan, from);
}

// The seed in xemu's tray (the app's, D261; Modkit's Tracker opened it): a running xemu's disc, when it is a randomized
// AzurKit build whose seed isn't the one tracked, is tracked instead (Track this build's way) before Live goes on.
async function trackTray() {
  const reply = await state.engine.call("tray", {});
  const rando = reply.preset?.layers.find((layer) => layer.tool === "randomizer")?.recipe, now = state.tracker.state.plan;
  if (!rando || now && String(rando.seed) === String(now.seed) && (rando.share ?? now.share) === now.share) return;
  await trackBuild(reply.preset, `${reply.name} in xemu's tray`);
}

// The Randomizer tab's two views: its settings, and the tracker.
function randoPane(view) {
  for (const id of ["settings", "tracker"]) $(`rando-view-${id}`).setAttribute("aria-selected", String(id === view));
  $("rando-settings").hidden = view !== "settings";
  $("tracker").hidden = view !== "tracker";
  if (view === "tracker") state.tracker?.draw();   // its maps, drawn from the image the first time they show
  ahead();
}

// The Characters tab's two views: the models, and the Variants editor (Step 4.6c).
function charPane(view, opening = true) {
  state.charPane = view;
  for (const id of ["model", "variants"]) $(`char-view-${id}`).setAttribute("aria-selected", String(id === view));
  $("char-model").hidden = view !== "model";
  $("variants").hidden = view !== "variants";
  if (view === "variants" && opening) state.variants?.open();
  if (view === "model") state.characters?.open();
}

// Track this seed: the Settings view's seed and settings (their share string, with the Patches tab's movement
// sliders, so the plan is the one a build of them makes) planned by the engine, then tracked.
async function trackSeed() {
  const seed = R("seed").value.trim(), share = state.rando.view?.share;
  if (state.rando.plan) return state.tracker.open(state.rando.plan.doc, state.rando.plan.name);   // the plan file open
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
    gate();
    edited();
  });
  for (const id of ["movement", "ceiling"]) {
    R(id).addEventListener("change", () => {
      offered();
      renderGroups();
      renderSkips();
      edited();
    });
  }
  R("difficulty").addEventListener("change", edited);
  R("warp").addEventListener("change", () => {   // ticks or unticks the pack itself, as its own box does
    const box = warpPack();
    if (box) {
      box.checked = R("warp").checked;
      box.dispatchEvent(new Event("change", { bubbles: true }));
    }
    R("warp").checked = Boolean(box?.checked);
    edited();
  });
  R("items").addEventListener("change", () => {
    edited();
    gate();   // the answer for the items as they were is stale
  });
  R("groups").addEventListener("change", (e) => {
    turnGroup(e.target.dataset.group, e.target.checked);
    if (e.target.checked) R("skip-list").open = true;   // D1061: a tick shows which skips it turned on
    renderSkips();
    renderGroups();
    edited();
  });
  R("load").addEventListener("change", loadSettings);
  R("save").addEventListener("click", saveSettings);
  R("plan").addEventListener("change", openPlan);
  R("plan-close").addEventListener("click", () => {
    state.rando.plan = null;
    renderPlan();
    lockRando();
    edited();
    say("Closed the plan file: Build plans the seed and settings shown");
  });
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
    renderGroups();
    edited();
  });
  $("spoiler-view").addEventListener("click", async () => {
    if ($("spoiler").hidden && !await spoilt()) return;
    $("spoiler").hidden = !$("spoiler").hidden;
    $("spoiler-view").textContent = $("spoiler").hidden ? "View" : "Hide";
  });
  $("spoiler-save").addEventListener("click", saveSpoiler);
}

// The site's service worker (web/sw.js, D1013), registered by the site only (the app's address is new each launch), once
// its engine is first ready: a first visit never waits for it (its release is kept in the background, the page running
// uncontrolled, as before), and each later page of the site comes from that release at once, cross-origin isolated,
// offline too. A controlled page shows when the next release waits ("An update is ready: Reload": sw.js posts
// "installed"; Firefox shows a registration's new worker late), asks sw.js to look for one every half hour, and its
// Reload asks the waiting release to take over, which it refuses while another of the site's pages is open: the page
// names how many.
const WORKER = "sw.js";
const ours = () => navigator.serviceWorker?.controller?.scriptURL === new URL(WORKER, location.href).href;
const told = (worker, message) => new Promise((done) => {
  const channel = new MessageChannel();
  channel.port1.onmessage = ({ data }) => done(data);
  worker.postMessage(message, [channel.port2]);
});

function registered() {
  const sw = navigator.serviceWorker;
  if (ours()) return sw.getRegistration().then((reg) => reg && updates(reg));
  sw.register(WORKER).catch(() => {});   // none (a private window, a refusal): the page runs as it is
}

function updates(reg) {
  const sw = navigator.serviceWorker;
  $("update").hidden = !reg.waiting;
  sw.addEventListener("message", ({ data }) => data?.type === "installed" && ($("update").hidden = false));
  sw.startMessages();
  $("update-reload").addEventListener("click", async () => {
    if (!reg.waiting) return say("The update is still being kept: Reload again in a moment");
    const reload = () => location.reload();
    sw.addEventListener("controllerchange", reload);
    const answer = await told(reg.waiting, { type: "reload" });
    if (answer.ok) return;
    sw.removeEventListener("controllerchange", reload);
    say(`Close AzurKit's ${answer.others === 1 ? "other page" : `${answer.others} other pages`} to update it`, true);
  });
  setInterval(() => ours() && told(sw.controller, { type: "check" }), 30 * 60 * 1000);
}

// A refusal of the page's policy is the page's own unless it is an inline style or script with no file of the page's
// origin (sourceFile) behind it: Chromium, Firefox and WebKit name the page's script that inserted the refused <style>
// or set the refused style, but a load checked once the page's code has returned (an <img>'s src, a stylesheet's
// @import or @font-face, an Audio) may name no file at all, though the page's own code asked it. An inline one with
// none is another's (an extension's content script; Playwright's evaluate, or its WebKit screenshot's
// <style>body {}</style>: Step 4.4u4): it goes to the violations the tests read, never to the status line.
function refusal(e) {
  let own = e.blockedURI !== "inline";
  try {
    own ||= new URL(e.sourceFile).origin === location.origin;
  } catch {}
  if (!own) return void state.violations.push(`page: ${e.violatedDirective} ${e.blockedURI}, not the page's `
                                              + `(${e.sourceFile || "no file"})`);
  state.violations.push(`page: ${e.violatedDirective} ${e.blockedURI}`);
  say(`The page's security policy refused ${e.violatedDirective}`, true);
}

async function main() {
  if (window.top !== window.self) return stop("AzurKit doesn't run inside another page: open it on its own.");
  if (navigator.serviceWorker?.controller && !ours()) {
    return stop("A service worker controls this page: AzurKit won't run.");
  }
  theme(document.documentElement.dataset.theme);   // theme.js's
  $("theme").addEventListener("click", () => theme(state.theme === "light" ? "dark" : "light", true));
  document.addEventListener("securitypolicyviolation", refusal);
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
  state.host = host;
  if (host.engine === "app") {
    if (host.age >= SLOW_LAUNCH) {
      state.launch = asking("launch");
      launched(1);
    }
    state.engine = appEngine(host, callbacks);
    $("remember").checked = host.remember === true;
    state.remembered = host.setup ?? null;   // none unless Remember settings was ticked (D1156)
    state.kept = state.remembered && JSON.stringify(state.remembered);
    state.tracked = host.tracker ?? null;
    pickInApp(host);
    theme(host.theme);
  } else if (!("WebAssembly" in window) || !("Worker" in window)) {
    return stop("This browser can't run AzurKit (it needs WebAssembly and workers): use the desktop app.");
  } else {
    state.engine = siteEngine(callbacks);
    sweep();   // a crashed page's build files
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
      ahead();   // what the last image held stops now
      state.tracker?.draw();   // the tracker's maps are drawn from it, if they aren't yet
      state.characters?.imaged();
      if (state.characters?.character()) askRando();   // the worn body's size folds in from the image
      state.data?.imaged();
      state.tools?.imaged();
      state.replace?.imaged();
      state.saves?.imaged();
      state.variants?.imaged();
    });
  }

  const changed = state.changed = (event) => {
    state.gen++;   // the work ahead of the setup before is dropped at its next record
    forget();
    unlinked();
    clearTimeout(state.later);
    state.later = setTimeout(remember, 250);
    if (!state.app) aheadOnSite(event?.now, event?.rest);   // the site's: what no longer matches stops now
  };
  $("packs").addEventListener("change", () => {
    changed();
    tally();
    lock();
    syncWarp();
  });
  $("packs").addEventListener("input", changed);
  addEventListener("pagehide", remember);
  $("reset").addEventListener("click", reset);
  $("remember").addEventListener("change", keepChosen);
  $("packs").addEventListener("toggle", place, true);   // a group's fold: "toggle" doesn't bubble
  addEventListener("resize", place);
  $("share").addEventListener("click", share);
  $("load-build").addEventListener("click", () => {
    $("load-build").hidden = true;
    load(state.opened, "your build");
  });
  $("build").addEventListener("click", async () => {
    const randomizer = randoRecipe(), character = state.characters.character();
    if (randomizer && !randomizer.seed && !randomizer.plan) {
      return say("Type a seed on the Randomizer tab, or press New", true);
    }
    if (state.characters.refused()) return say(state.characters.refused(), true);
    if (state.community.waiting()) return say("Reading the community packs: try again in a moment", true);
    const unsaved = state.variants.unsaved();   // a build reads a variant's saved recipe: its edits asked about first
    if (unsaved && character?.species === unsaved && !await state.variants.ask(
      `${unsaved} has unsaved edits in the Variants view, and a build uses its saved recipe. Build without them?`)) return;
    forget();
    if (!state.app) state.ready = false;   // until the site's engine answers: then kept, or replaced
    busy(true);
    say((randomizer?.plan ? "Checking your image and the plan file and building…"
      : randomizer ? "Checking your image, planning the seed and building…" : "Checking your image and building…")
        + (character ? ` (as ${character.species})` : ""));
    state.sent = chosen();
    asking("build");
    state.engine.build(state.file, state.sent, state.xbr, randomizer, character,
                       { ...extras(), ...(state.app ? {} : state.replace.picked()) });
  });
  randoEvents(changed);
  for (const view of ["model", "variants"]) $(`char-view-${view}`).addEventListener("click", () => charPane(view));
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
    state.build.saved = true;
    say(`Saving ${a.download} (${bytes(state.build.size)}): your browser's download shows its progress`);
    checkSave(state.build, a.download);
  });
}

main();
