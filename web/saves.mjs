// Saves in the Tools tab (Step 4.7e; D919's save editor): open a save slot (its folder) or read the slots straight from
// an xemu HDD image, read-only; see what each file holds; change a text save's line; sign it again with your own BIOS
// files (your flash image and MCPX boot ROM, read in memory for that one ask, never kept, never sent); Save the slot (the
// app: a new folder; the site: a zip). Nothing writes into the HDD image (D36). A slot needs no image; signing does (the
// game's own key is in its XBE), so it is greyed with that line until one is picked (D979). The engine decides every
// answer (sdk.saves); this page asks and draws through textContent only.
const CHOOSE = "Choose your image first (1.): the game's key for your saves is in it";
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// saves({root, call, app, say, image, out, pick}): root the Tools tab's panel; call the engine's ask; app whether the host
// is the app; say the status line; image() the picked image; out(name) (the app's) where a folder saves: a path, "" (no
// dialogs: the Downloads folder) or null (cancelled); pick(kind) (the app's, with dialogs) a computer path, or null.
export function savesSection({ root, call, app, say, image, out, pick = null }) {
  const s = { slots: [], slot: null, signed: null, asking: false };
  const button = (id, text, fn) => {
    const node = el("button", { id, type: "button", textContent: text });
    node.addEventListener("click", fn);
    return node;
  };
  const path = (id, hint) => el("input", { id, type: "text", placeholder: hint, spellcheck: false, autocomplete: "off" });
  const ui = {
    folderFile: app ? null : el("input", { id: "saves-folder", type: "file", webkitdirectory: true }),
    hddFile: app ? null : el("input", { id: "saves-hdd", type: "file" }),
    folderPath: app ? path("saves-folder-path", "A save slot's folder") : null,
    hddPath: app ? path("saves-hdd-path", "An xemu HDD image") : null,
    line: el("p", { id: "saves-line", className: "note" }),
    which: el("span", { id: "saves-which" }),   // a button a slot (WebKit reports a <select> made here as an inline style)
    rows: el("tbody", { id: "saves-rows" }),
    flashFile: app ? null : el("input", { id: "saves-flash", type: "file" }),
    mcpxFile: app ? null : el("input", { id: "saves-mcpx", type: "file" }),
    flashPath: app ? path("saves-flash-path", "Your flash image") : null,
    mcpxPath: app ? path("saves-mcpx-path", "Your MCPX boot ROM") : null,
    signLine: el("p", { id: "saves-sign-line", className: "note" }),
  };
  ui.sign = button("saves-sign", "Sign it again", () => sign());
  ui.save = button("saves-save", app ? "Save as a folder…" : "Save as a zip", () => save());
  ui.table = el("table", { hidden: true }, el("thead", {}, el("tr", {}, el("th", { textContent: "File" }),
    el("th", { textContent: "Size" }), el("th", { textContent: "What it holds" }))), ui.rows);
  const section = el("div", { id: "tools-saves" }, el("h2", { textContent: "Saves" }),
    el("p", {}, ...(app ? ["A slot's folder ", ui.folderPath, " ", button("saves-open", "Open", () => opened({ folder: ui.folderPath.value.trim() })),
                           ...(pick ? [" ", button("saves-open-choose", "Choose…", () => chosen("folder"))] : []),
                           " or an xemu HDD image ", ui.hddPath, " ", button("saves-read", "Read its slots", () => opened({ image: ui.hddPath.value.trim() })),
                           ...(pick ? [" ", button("saves-read-choose", "Choose…", () => chosen("hdd"))] : [])]
      : [el("label", {}, "A slot's folder ", ui.folderFile), " ", el("label", {}, "or an xemu HDD image ", ui.hddFile)])),
    ui.line, el("p", {}, ui.which), ui.table,
    el("p", {}, "Your BIOS files ", ...(app ? [ui.flashPath, " ", ui.mcpxPath] : [
      el("label", {}, "flash image ", ui.flashFile), " ", el("label", {}, "MCPX boot ROM ", ui.mcpxFile)]), " ", ui.sign, " ", ui.save),
    ui.signLine);
  root.querySelector("h2:last-of-type").before(section);

  const summary = (file) => file.kind === "meta" ? file.fields.map(([k, v]) => `${k}: ${v}`).join(" · ")
    : file.kind === "binary" ? `a binary save, version ${file.version}${"records" in file ? `, ${file.records} records` : ""}${
      file.clock != null ? `, clock ${file.clock}` : ""}` : file.kind === "signature" ? "its signature"
      : file.kind === "image" ? "a picture" : file.kind === "text" ? "" : "a file";

  const held = (slot) => {   // the engine's answer: this slot as it is now
    s.slot = slot;
    s.slots = s.slots.map((other) => other.id === slot.id ? slot : other);
  };

  const edit = async (file, line, value) => {
    const reply = await call("saves", { given: { do: "edit", id: s.slot.id, edits: [{ file, line, value }] } });
    if ("refused" in reply) {
      say(`${file}: ${reply.refused}`, true);
    } else {
      held(reply.slot);
      s.signed = false;
      say(`${file} changed: sign it again before the game will take it`);
    }
    draw();
  };

  const row = (file) => {
    const what = el("td", { textContent: summary(file) });
    if (file.kind === "text") {
      what.append(...file.lines.map((text, line) => {
        const box = el("input", { type: "text", value: text, spellcheck: false });
        box.dataset.file = file.path;
        box.dataset.line = line;
        box.addEventListener("change", () => edit(file.path, line, box.value));
        return box;
      }));
    }
    return el("tr", {}, el("td", { textContent: file.path }), el("td", { textContent: file.size.toLocaleString("en-US") }), what);
  };

  function draw() {
    ui.which.replaceChildren(...(s.slots.length < 2 ? [] : s.slots.map((slot) => {
      const one = el("button", { type: "button", textContent: slot.id, disabled: slot.id === s.slot?.id });
      one.addEventListener("click", () => {
        s.slot = slot;
        s.signed = null;
        draw();
      });
      return one;
    })));
    ui.table.hidden = !s.slot;
    ui.rows.replaceChildren(...(s.slot?.files ?? []).map(row));
    ui.line.textContent = s.asking ? "Reading…" : !s.slots.length ? "Nothing is written into a save or HDD image: a slot saves new."
      : `${s.slot.id} · ${s.slot.files.length} files · ${s.slots.length} slot${s.slots.length === 1 ? "" : "s"} read`;
    ui.sign.disabled = !s.slot || !image() || s.asking;
    ui.save.disabled = !s.slot || s.asking;
    ui.sign.title = image() ? "" : CHOOSE;
    ui.signLine.textContent = !image() ? CHOOSE : s.signed === true ? "Signed for your console. Your BIOS files were read for that alone: nothing kept."
      : s.signed === false ? "Changed: sign it again before the game will take it." : "";
  }

  const answered = (reply) => {
    s.asking = false;
    if ("refused" in reply) {
      say(reply.refused, true);
      draw();
      return null;
    }
    return reply;
  };

  async function opened(given, files = {}) {
    s.asking = true;
    draw();
    const reply = answered(await call("saves", { given: { do: "open", ...given }, ...files }));
    if (reply) {
      s.slots = reply.slots;
      s.slot = reply.slots[0] ?? null;
      s.signed = null;
      say(reply.slots.length ? `Read ${reply.slots.length} save slot${reply.slots.length === 1 ? "" : "s"}` : "No Azurik save there");
    }
    draw();
  }

  // The site's folder pick: each File by its path under the folder, whose own name is the slot's id.
  const folder = (list) => {
    const given = [...list], id = given[0]?.webkitRelativePath.split("/")[0] || "slot";
    const files = Object.fromEntries(given.map((file) => [file.webkitRelativePath.split("/").slice(1).join("/") || file.name, file]));
    return opened({ id }, { files });
  };

  async function chosen(kind) {
    const given = await pick(kind === "folder" ? "folder" : "replacement");
    if (!given) return;
    (kind === "folder" ? ui.folderPath : ui.hddPath).value = given;
    opened(kind === "folder" ? { folder: given } : { image: given });
  }

  async function sign() {
    s.asking = true;
    draw();
    const body = app ? { given: { do: "sign", id: s.slot.id, iso: image(), flash_file: ui.flashPath.value.trim(),
                                  mcpx_file: ui.mcpxPath.value.trim() } }
      : { given: { do: "sign", id: s.slot.id }, file: image(), flash: ui.flashFile.files[0], mcpx: ui.mcpxFile.files[0] };
    const reply = answered(await call("saves", body));
    if (reply) {
      held(reply.slot);
      s.signed = true;
      say(`Signed ${s.slot.id} for your console${reply.was ? " (it was already)" : ""}`);
    }
    draw();
  }

  async function save() {
    if (app) {
      const to = await out(s.slot.id);
      if (to === null) return;
      const reply = answered(await call("saves", { given: { do: "save", id: s.slot.id, out: to } }));
      if (reply) say(`Saved the slot: ${reply.out}`);
    } else {
      const reply = answered(await call("saves", { given: { do: "zip", id: s.slot.id } }));
      if (reply) {
        const url = URL.createObjectURL(new Blob([reply.data], { type: "application/zip" }));
        const a = el("a", { href: url, download: reply.name });
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        say(`Saved ${reply.name}: your browser's download shows it`);
      }
    }
    draw();
  }

  ui.folderFile?.addEventListener("change", () => ui.folderFile.files.length && folder(ui.folderFile.files));
  ui.hddFile?.addEventListener("change", () => ui.hddFile.files[0] && opened({}, { hdd: ui.hddFile.files[0] }));
  draw();

  return { imaged: draw, folder, state: s };
}
