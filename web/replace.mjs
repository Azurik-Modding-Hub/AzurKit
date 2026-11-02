// Replace files in the Tools tab (Step 4.7d; D919's list): a file from your computer stands in for one of the image's,
// whole, at any size, in one layer after every other (edits/files.py: a group it shadows is named, D28). A recipe, a build
// and a mods file name it by path, sha256 and size, never its bytes or where it was; a share link refuses it (Q174), and a
// recipe that names one asks you to pick it again, nothing read until you do (SEC-11). The site keeps your File and reads
// it for each ask and build; the app's engine reads the path you picked, held for this launch, never kept. Greyed until
// an image is picked (D979): its files are the image's. The engine decides what may be replaced; this page sends the
// path and the file and draws what comes back, through textContent only.
const CHOOSE = "Choose your image first (1.)";
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// replaceFiles({root, call, app, say, image, changed, pick}): root the Tools tab's panel, which this joins before its
// storage; call the engine's ask; app whether the host is the app; say the status line; image() the picked image;
// changed() runs when the replaced files change; pick() (the app's, with dialogs) a computer path from its open dialog,
// or null.
export function replaceFiles({ root, call, app, say, image, changed, pick = null }) {
  const r = { held: new Map(), names: null, reading: false };
  const path = el("input", { id: "replace-path", type: "text", placeholder: "The image's file", spellcheck: false,
                             autocomplete: "off" });
  const names = el("datalist", { id: "replace-names" });
  path.setAttribute("list", names.id);
  const file = app ? null : el("input", { id: "replace-file", type: "file" });
  const from = app ? el("input", { id: "replace-from", type: "text", placeholder: "Your file's full path",
                                   spellcheck: false, autocomplete: "off" }) : null;
  const use = app ? el("button", { id: "replace-use", type: "button", textContent: "Use it" }) : null;
  const dialog = pick ? el("button", { id: "replace-choose", type: "button", textContent: "Choose…" }) : null;
  const line = el("p", { id: "replace-line", className: "note" });
  const rows = el("tbody", { id: "replace-rows" });
  const table = el("table", { hidden: true }, el("thead", {}, el("tr", {}, el("th", { textContent: "File" }),
    el("th", { textContent: "Size" }), el("th", { textContent: "State" }), el("th"))), rows);
  const section = el("div", { id: "tools-replace" }, el("h2", { textContent: "Replace files" }),
    el("p", {}, el("label", {}, "Replace ", path), names, " with ", ...(app ? [from, " ", use] : [file]),
       ...(dialog ? [" ", dialog] : [])), line, table);
  root.querySelector("h2:last-of-type").before(section);

  const draw = () => {
    const none = !image() || r.reading;
    for (const node of [path, file, from, use, dialog]) {
      if (!node) continue;
      node.disabled = none;
      node.title = image() ? "" : CHOOSE;
    }
    if (!r.reading) {
      line.textContent = !image() ? CHOOSE
        : "Your file goes in whole, after every other change to the image; the build names what it shadows. "
          + "default.xbe and filelist.txt can't be replaced.";
    }
    table.hidden = !r.held.size;
    rows.replaceChildren(...[...r.held].map(([name, held]) => {
      const again = el("button", { type: "button", textContent: "Pick it again" });
      again.addEventListener("click", () => {
        path.value = name;
        (file ?? from).focus();
      });
      const drop = el("button", { type: "button", textContent: "Remove" });
      drop.addEventListener("click", () => {
        r.held.delete(name);
        draw();
        changed();
      });
      return el("tr", {}, el("td", { textContent: name }), el("td", { textContent: held.entry.size.toLocaleString("en-US") }),
                el("td", { textContent: held.picked ? `sha256 ${held.entry.sha256.slice(0, 12)}`
                  : "Not picked here: pick it again to build" }), el("td", {}, ...(held.picked ? [] : [again, " "]), drop));
    }));
  };

  // The image's files, offered as the path box's choices, asked when it first takes focus.
  const offered = async () => {
    if (r.names === image() || !image()) return;
    r.names = image();
    const reply = await call("files", app ? { iso: image() } : { file: image() });
    if (r.names === image() && !("refused" in reply)) {
      names.replaceChildren(...reply.files.map(([name]) => el("option", { value: name })));
    }
  };

  const chosen = async (picked) => {
    const name = path.value.trim().replace(/^\/+/, "");
    if (!name) return say("Name the image's file to replace first", true);
    r.reading = true;
    line.textContent = `Reading ${app ? picked : picked.name}…`;
    draw();
    const reply = await call("replace", app ? { path: name, file: picked } : { path: name, picked });
    r.reading = false;
    if ("refused" in reply) say(`${name} isn't replaced: ${reply.refused}`, true);
    else {
      r.held.set(name, { entry: reply.entry, picked: app ? true : picked });
      say(`${name} will be replaced at the next build (${reply.entry.size.toLocaleString("en-US")} B)`);
      changed();
    }
    draw();
  };

  path.addEventListener("focus", offered);
  file?.addEventListener("change", () => {
    if (file.files[0]) chosen(file.files[0]);
    file.value = "";
  });
  use?.addEventListener("click", () => from.value.trim() && chosen(from.value.trim()));
  dialog?.addEventListener("click", async () => {
    const given = await pick();
    if (given) chosen(given);
  });
  draw();

  return {
    // The recipe's files (each named, never its bytes) and, for the site's build, the Files themselves.
    entries: () => [...r.held.values()].map((held) => held.entry),
    picked: () => {
      const given = [...r.held].filter(([, held]) => held.picked);
      return given.length ? { picked: Object.fromEntries(given.map(([name, held]) => [name, held.picked])) } : {};
    },
    // A recipe's files: a pick of the same bytes stays; any other waits to be picked (a recipe says which, no more).
    set: (entries) => {
      const before = r.held;
      r.held = new Map(entries.map((entry) => [entry.path, {
        entry, picked: before.get(entry.path)?.entry.sha256 === entry.sha256 ? before.get(entry.path).picked : null }]));
      if (entries.length) say(`${entries.map((e) => e.path).join(", ")}: pick your file again in the Tools tab to build`);
      draw();
    },
    imaged: () => {
      r.names = null;
      draw();
    },
    state: r,
  };
}
