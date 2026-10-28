// The page (D866): pick your image, choose packs, Build, then Save. One page for both hosts, the site and the app;
// it decides no output byte (WEB §3.1). The engine, azurkit.sdk, plans and checks the build and returns it as
// segments, which this page joins into a Blob of slices of your own file and the bytes the build writes (WEB §3.4).
// The site's engine is siteEngine(): the wheel under Pyodide in a fresh module worker for each build. Text reaches
// the page only through textContent. No eval: the CSP has no 'unsafe-eval', and a webview host calls in through a
// bridge, never by evaluating script (4.1b2).
const $ = (id) => document.getElementById(id);
const state = { engine: null, ready: false, building: false, file: null, packs: null, build: null, url: null,
                violations: [] };
globalThis.azurkit = state;   // the last build ({report, size, segments, blob}), for the tests and the console

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
  $("cancel").hidden = !on;
  for (const box of $("packs").querySelectorAll("input")) box.disabled = on;
}

function forget() {
  if (state.url) URL.revokeObjectURL(state.url);
  state.build = state.url = null;
  $("save").disabled = true;
}

function main() {
  if (window.top !== window.self) return stop("AzurKit doesn't run inside another page: open it on its own.");
  if (!("WebAssembly" in window) || !("Worker" in window)) {
    return stop("This browser can't run AzurKit (it needs WebAssembly and workers): use the desktop app.");
  }
  if (navigator.serviceWorker?.controller) return stop("A service worker controls this page: AzurKit won't run.");
  document.addEventListener("securitypolicyviolation", (e) => {
    state.violations.push(`page: ${e.violatedDirective} ${e.blockedURI}`);
    say(`The page's security policy refused ${e.violatedDirective}`, true);
  });

  state.engine = siteEngine({
    ready(catalog, version) {
      state.ready = true;
      if (!state.packs) {
        state.packs = catalog;
        renderPacks(catalog);
        $("version").textContent = `AzurKit ${version}`;
      }
      busy(state.building);
    },
    built({ report, size, segments }) {
      const file = state.file;
      const parts = segments.map((s) => s.kind === "copy" ? file.slice(s.offset, s.offset + s.size)
        : s.kind === "bytes" ? s.data : new Uint8Array(s.size));
      const blob = new Blob(parts, { type: "application/octet-stream" });
      busy(false);
      if (blob.size !== size) return say(`The build's pieces make ${bytes(blob.size)}, not ${bytes(size)}`, true);
      state.build = { report, size, segments, blob };
      state.url = URL.createObjectURL(blob);
      $("save").disabled = false;
      const changed = Object.keys(report.result);
      say(`Ready · ${report.label} · ${bytes(size)} · changed: ${changed.length ? changed.join(", ") : "nothing"}`
          + report.conflicts.map((c) => ` · conflict: ${c}`).join(""));
    },
    refused({ message }) {
      busy(false);
      say(message, true);
    },
    failed(message) {
      busy(false);
      say(message, true);
    },
  });

  $("iso").addEventListener("change", () => {
    forget();
    state.file = $("iso").files[0] ?? null;
    $("picked").textContent = state.file ? `${state.file.name} · ${bytes(state.file.size)}` : "";
    say("");
    busy(false);
  });
  $("packs").addEventListener("change", forget);
  $("build").addEventListener("click", () => {
    forget();
    state.ready = false;   // the engine is replaced after each build
    busy(true);
    say("Checking your image and building…");
    state.engine.build(state.file, chosen());
  });
  $("cancel").addEventListener("click", () => {
    state.ready = false;
    state.engine.cancel();
    busy(false);
    say("Cancelled");
  });
  $("save").addEventListener("click", () => {
    const a = Object.assign(document.createElement("a"), {
      href: state.url, download: `${state.file.name.replace(/\.x?iso$/i, "")} (AzurKit).iso` });
    document.body.append(a);
    a.click();
    a.remove();
    say(`Saving ${a.download} (${bytes(state.build.size)}): your browser's download shows its progress`);
  });
}

main();
