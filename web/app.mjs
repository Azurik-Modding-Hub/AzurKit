// The page (D866): pick your image, choose packs, Build, then Save. One page for both hosts, the site and the app;
// it decides no output byte (WEB §3.1). host.json names the host's engine, and the engine, azurkit.sdk, plans and
// checks the build. The site's, siteEngine(), is the wheel under Pyodide in a fresh module worker for each build: it
// returns the build as segments, which this page joins into a Blob of slices of your own file and the bytes the
// build writes (WEB §3.4), and Save downloads it. The app's, appEngine(), is azurkit.sdk on CPython behind the app's
// own server on 127.0.0.1 (azurkit.app), in its window or a browser alike: it reads the image at the path you give
// and writes the build where you save it. Text reaches the page only through textContent. No eval: the CSP has no
// 'unsafe-eval', and no host evaluates script in the page (4.1b2).
const $ = (id) => document.getElementById(id);
const state = { engine: null, app: false, dialogs: false, ready: false, building: false, saving: false, file: null,
                packs: null, build: null, url: null, saved: null, poll: null, violations: [] };
globalThis.azurkit = state;   // the last build and save, for the tests and the console

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
function siteEngine({ ready, built, refused, failed }) {
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
    build: (file, packs) => worker.postMessage({ type: "build", file, packs }),
    cancel: restart,
  };
}

// The app's engine: azurkit.sdk on CPython behind this launch's server (azurkit.app), the same in the app's window
// and in a browser. The page posts JSON to it, and a refusal comes back as {refused}. A build's reply that arrives
// after Cancel is dropped; a save's is awaited, since the server says whether it wrote anything.
function appEngine(host, { ready, built, refused, failed, saved }) {
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
  return {
    build: (iso, packs) => run("api/build", { iso, packs }, built),
    save: (recipe, out) => run("api/save", { recipe, out }, saved),
    progress: async () => (await fetch("api/progress", { cache: "no-store" })).json(),
    choose: async (kind, path) => (await post("api/choose", { kind, path })).path ?? null,
    cancel: () => {
      if (!state.saving) ticket++;
      post("api/cancel", {}).catch(() => {});
    },
  };
}

function renderPacks(catalog) {
  const list = $("packs");
  list.replaceChildren();
  for (const pack of catalog.packs) {
    const label = document.createElement("label");
    const box = Object.assign(document.createElement("input"), { type: "checkbox", checked: pack.default_on });
    box.dataset.pack = pack.name;
    const params = Object.entries(pack.parameters).map(([k, v]) => ` (${k} ${v})`).join("");
    const name = Object.assign(document.createElement("span"), { className: "name", textContent: pack.name });
    const what = Object.assign(document.createElement("span"), { textContent: pack.description + params });
    const where = Object.assign(document.createElement("span"), {
      className: "releases", textContent: ` ${pack.releases.map((r) => r === "usa" ? "USA" : "Europe").join(", ")}` });
    what.append(where);
    label.append(box, name, what);
    list.append(label);
  }
}

function chosen() {
  const packs = {};
  for (const box of $("packs").querySelectorAll("input[data-pack]")) {
    if (box.checked) packs[box.dataset.pack] = {};
  }
  return packs;
}

function busy(on) {
  state.building = on;
  $("build").disabled = on || !state.file || !state.ready;
  $("iso").disabled = on || !state.packs;
  for (const id of ["iso-path", "iso-choose", "out-path"]) $(id).disabled = on;
  $("save").disabled = on || !state.build;
  $("cancel").hidden = !on;
  for (const box of $("packs").querySelectorAll("input")) box.disabled = on;
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

function ready(catalog, version) {
  state.ready = true;
  if (!state.packs) {
    state.packs = catalog;
    renderPacks(catalog);
    $("version").textContent = `AzurKit ${version}`;
  }
  busy(state.building);
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
         + made.conflicts.map((c) => ` · conflict: ${c}`).join(""));
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
    state.file = $("iso-path").value.trim() || null;
    $("picked").textContent = host.dialogs ? "Type the image's full path, or Choose… it."
      : "Type the image's full path: a browser can't tell AzurKit where a file is.";
    say("");
    busy(false);
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
  const callbacks = { ready, built, saved, refused: ({ message }) => report(message, true),
                      failed: (message) => report(message, true) };
  if (host.engine === "app") {
    state.engine = appEngine(host, callbacks);
    pickInApp(host);
  } else if (!("WebAssembly" in window) || !("Worker" in window)) {
    return stop("This browser can't run AzurKit (it needs WebAssembly and workers): use the desktop app.");
  } else {
    state.engine = siteEngine(callbacks);
    $("iso").addEventListener("change", () => {
      forget();
      state.file = $("iso").files[0] ?? null;
      $("picked").textContent = state.file ? `${state.file.name} · ${bytes(state.file.size)}` : "";
      say("");
      busy(false);
    });
  }

  $("packs").addEventListener("change", forget);
  $("build").addEventListener("click", () => {
    forget();
    if (!state.app) state.ready = false;   // the site's engine is replaced after each build
    busy(true);
    say("Checking your image and building…");
    state.engine.build(state.file, chosen());
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
