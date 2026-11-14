// The Data tab (Step 4.7a; Modkit's Game Data editor, D151, D262, D986): config.xbr's cells, edited before an image is
// picked (the engine reads the vanilla config.xbr AzurKit ships). Six views, like the Randomizer tab's Settings ·
// Tracker: Player; Critters, Items, Armor and Weapons, each a picker (web/picker.mjs, its search box by name) and the
// chosen entity's cells of every table that holds it, as sections of mini-tables; All tables, the 18 tables by
// category (the list filtered by table name), a table as a grid with an entity a row and a property a column, sorted by
// a column's header, Changed only; and Changes, every cell the edits change (a loaded mods file's too) with its vanilla
// value beside it, table by table, and the byte edits and level moves a mods file brought: what a build will change, before it. A cell edits on a click, Enter or F2: a number cell takes any number (never
// clamped: its range is a hint), a value set is a dropdown (each value the cell can't take yet greyed, saying what it
// needs), a word list a checklist or a yes/no a checkbox, an empty cell with a known default shows it
// greyed; the engine checks every edit (tools/data's check) and a refusal is one red line under the cell saying why.
// A changed cell is marked ● with its vanilla value in its note, a cell a ticked pack's slider also writes ⚠ (the data
// edit wins: the build says so). Revert (a cell), Reset table, Undo, Redo, Clear edits and the count of edits. The edits
// are the recipe's xbr set operations, which this tab keeps (ops(), load(ops)) and the page builds with, remembers and
// links; the byte edits and level moves a mods file brought list read-only, counted apart, removable. The tab needs no image: its line says the edits join
// each build, which waits for the image (D979). All files… under the tables' list (Step 4.6h, Modkit's): every .xbr of
// the picked image, config.xbr first, each opening to its keyed tables read from the image (only config.xbr holds any
// in a vanilla image), the search box narrowing them too; a table there shows and edits as any other (another file's
// asks carry the image). It waits for the image, greyed with its line (D979). The engine decides everything shown
// (sdk.data, sdk.data_edit): this page sends the tab's choices and draws what comes back. The Critters and Items pickers
// show each one's body (the index's body) in the picture the Characters tab ships of it (characters/index.json names
// each species' file: its body's path, / as --), before an image too, as Modkit's pickers drew them from the image; a
// body none ships (none the game holds) lists as text. Text only (textContent), no eval.
import { option, picker } from "./picker.mjs";

const VIEWS = [["player", "Player"], ["critter", "Critters"], ["item", "Items"], ["armor", "Armor"],
               ["weapon", "Weapons"], ["tables", "All tables"], ["changes", "Changes"]];
const UNCHANGED = "Nothing changed yet: edit a cell, or load a mods file in the Tools tab.";
const WRITTEN = "A ticked pack's slider also writes this cell; your edit wins, and the build says so.";
const BUILDS = "Your edits join each build, after the packs";
const CONFIG = "gamedata/config.xbr";
const FILES_WAIT = "Pick your image (1.) to list its files.";
const SHIPPED = "characters/index.json";   // the Characters tab's shipped answer: each species' picture file
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
// A dropdown editor's box: a clone of index.html's template's, never one made in the page by script (createElement, or
// a clone of one in the page): WebKit gives such a select an inline style the page's CSP refuses (style-src-attr, which
// the status line would say), but not one cloned from a template's content.
const select = () => document.getElementById("data-select").content.firstElementChild.cloneNode(true);

// dataTab({ call, root, say, packs, changed, image, app }): call is the engine's (the site's worker, the app's api),
// root the tab's panel, say(text) the page's status line, packs() the Patches tab's ticks (the engine marks the cells
// they write), changed(ops) runs when the edits change (the page builds with them and remembers them), image() the
// picked image, if any, and app whether the host is the app (its image a path, the site's a File). The page calls
// open() each time the tab shows (the ticks may have changed), ops() for a build's recipe, load(ops) when a mods file,
// a link or the remembered setup brings edits, and imaged() on each pick.
export function dataTab({ call, root, say, packs, changed, image, app = false }) {
  const d = { ops: [], undo: [], redo: [], index: null, view: "player", chosen: {}, table: null, file: null,
              answer: null, ticket: 0, changedOnly: false, sort: null, opened: false,
              files: null, listing: 0, tablesOf: {}, reading: {}, openFiles: new Set(), pictured: null };
  const tabs = VIEWS.map(([id, label]) => {
    const button = el("button", { type: "button", textContent: label });
    button.setAttribute("role", "tab");
    button.addEventListener("click", () => choose(id));
    return [id, button];
  });
  const views = el("p", { className: "views" }, ...tabs.map(([, b]) => b));
  views.setAttribute("role", "tablist");
  views.setAttribute("aria-label", "The Data tab's views");
  const count = el("span", { className: "note" });
  const button = (label, act) => {
    const b = el("button", { type: "button", textContent: label });
    b.addEventListener("click", act);
    return b;
  };
  const undo = button("Undo", () => step(d.undo, d.redo));
  const redo = button("Redo", () => step(d.redo, d.undo));
  const ofTable = (op) => op.op === "set" && op.table === d.table && op.file === (d.file ?? CONFIG);   // the shown one's
  const reset = button("Reset table", () => commit(d.ops.filter((op) => !ofTable(op))));
  const clear = button("Clear edits", () => commit([]));
  const only = el("input", { type: "checkbox" });
  only.addEventListener("change", () => {
    d.changedOnly = only.checked;
    draw();
  });
  const onlyLabel = el("label", { className: "note" }, only, " Changed only");
  const bar = el("p", { className: "data-bar" }, views, " ", count, " ", undo, redo, reset, clear, onlyLabel);
  const pick = picker({ label: "Entities", placeholder: "Search by name", pick: (name) => chosen(name) });
  const others = el("p", { className: "note" });
  const body = el("div", { className: "data-view" });
  const note = el("p", { className: "note data-note" });
  const builds = el("p", { className: "note data-builds" });
  // All files…: its line (what it waits for, its listing, a refusal) and the files, each a row opening to its tables.
  const filesLine = el("p", { className: "note" });
  const filesList = el("div", { className: "data-file-list" });
  const files = el("details", { className: "data-files" }, el("summary", { textContent: "All files…" }), filesLine,
                   filesList);
  pick.element.append(files);
  const search = pick.element.querySelector(".picker-search input");
  const imaged = () => {
    builds.textContent = image() ? `${BUILDS}.` : `${BUILDS}: pick your image (1.) to build.`;
    d.files = null;   // another image's files and tables: asked again, an older image's answers dropped
    d.tablesOf = {};
    d.reading = {};
    if (files.open && image()) listFiles();
    else drawFiles();
    if (d.file && d.view === "tables" && d.answer) show();
  };
  root.replaceChildren(bar, builds,
                       el("div", { className: "data-body" }, pick.element, el("div", {}, others, body, note)));

  // An ask of another file than config.xbr reads it from the image: the app's by its path, the site's File mounted.
  const imaging = (given) => app ? { given: { ...given, iso: image() } } : { file: image(), given };
  const ask = (what, given = {}) => given.file && given.file !== CONFIG
    ? call("data", imaging({ what, ops: d.ops, ...given }))
    : call("data", { given: { what, ops: d.ops, packs: packs(), ...given } });
  const refused = (reply) => {
    if (!("refused" in reply)) return false;
    say(reply.refused);
    return true;
  };

  // The pictures the page ships (a set of their files; none when they can't be read: the pickers list text), and a
  // body's, if one ships.
  const shipped = () => fetch(SHIPPED).then((reply) => reply.ok ? reply.json() : null).catch(() => null)
    .then((found) => (d.pictured = new Set(Object.values(found?.species ?? {}))));
  const picture = (body) => {
    const file = body?.replaceAll("/", "--");
    return file && d.pictured?.has(file) ? { picture: `characters/${file}.front.png` } : {};
  };

  // The index (the tables and the pickers' lists) and the shipped pictures, then the view shown.
  const open = async () => {
    d.opened = true;
    say("Reading the game data…");
    const [reply] = await Promise.all([ask("index"), shipped()]);
    if (refused(reply)) return;
    d.index = reply;
    say("");
    choose(d.view);
  };
  const choose = (view) => {
    d.view = view;
    for (const [id, b] of tabs) b.setAttribute("aria-selected", String(id === view));
    pick.element.hidden = view === "player" || view === "changes";
    onlyLabel.hidden = reset.hidden = files.hidden = view !== "tables";
    if (!d.index) return;
    const entries = view === "tables"
      ? d.index.tables.map((t) => ({ name: t.name, label: `${t.label} (${t.name})`, group: t.category,
                                     title: `${t.cols} entities, ${t.rows} properties` }))
      : view === "player" || view === "changes" ? [] : d.index.pickers[view].map((e) => ({
        name: e.name, label: e.label ?? e.name, group: e.group, ...picture(e.body),
        title: e.info.map(([label, text]) => `${label}: ${text}`).join("\n") }));
    const first = view === "tables" ? d.table ?? entries[0]?.name : d.chosen[view] ?? entries[0]?.name;
    pick.set(entries, view === "tables" && d.file ? null : first);
    show(first);
  };
  const chosen = (name, file = null) => {
    if (d.view === "tables") [d.table, d.file] = [name, file === CONFIG ? null : file];
    else d.chosen[d.view] = name;
    pick.choose(d.view === "tables" && d.file ? null : name);
    drawFiles();
    show(name);
  };
  // Ask the engine for the view or grid; an answer to an older ask is dropped.
  const show = async (name = d.view === "tables" ? d.table : d.chosen[d.view]) => {
    const mine = ++d.ticket;
    if (d.view === "tables") d.table = name;
    else if (d.view !== "player" && d.view !== "changes") d.chosen[d.view] = name;
    const reply = d.view === "tables" ? await ask("table", { table: name, ...d.file ? { file: d.file } : {} })
      : await ask("view", { kind: d.view, name: d.view === "player" || d.view === "changes" ? null : name });
    if (mine !== d.ticket || refused(reply)) return;
    d.answer = reply;
    draw();
  };

  // All files…: the image's files, asked each time it opens (the search narrows them by file or table name), and a
  // file's keyed tables (only config.xbr's need no image), asked each time its row opens and again for each open row
  // (reread, Modkit's _mark_tree) once the files are listed (another image's) and after each change of the edits (their
  // ● marks); an answer an ask since (a later one, another image's) overtook is dropped.
  const listFiles = async () => {
    const ticket = ++d.listing;
    d.files = null;
    drawFiles();
    const reply = await call("data", imaging({ what: "files" }));
    if (ticket !== d.listing) return;
    d.files = "refused" in reply ? reply : reply.files;
    reread();
    drawFiles();
  };
  const openFile = async (file) => {
    const mine = d.reading[file] = {};
    const reply = await ask("tables", { file });
    if (d.reading[file] !== mine) return;
    d.tablesOf[file] = "refused" in reply ? reply : reply.tables;
    drawFiles();
  };
  const reread = () => {
    if (image() && Array.isArray(d.files)) for (const { file } of d.files) if (d.openFiles.has(file)) openFile(file);
  };
  const drawFiles = () => {
    files.classList.toggle("waits", !image());
    const rows = [];
    filesLine.textContent = !image() ? FILES_WAIT : !d.files ? "Listing your image's files…" : d.files.refused ?? "";
    const wanted = search.value.trim().toLowerCase();
    for (const { file } of image() && Array.isArray(d.files) ? d.files : []) {
      const name = file.replace(/^gamedata\//, ""), got = d.tablesOf[file];
      const named = !wanted || name.toLowerCase().includes(wanted);
      const hits = Array.isArray(got) ? got.filter((t) => named || t.name.toLowerCase().includes(wanted)) : [];
      if (!named && !hits.length) continue;
      const open = d.openFiles.has(file);
      const row = el("button", { type: "button", className: "data-file", textContent: `${open ? "▾" : "▸"} ${name}` });
      row.dataset.file = file;
      rows.push(row);
      if (!open) continue;
      if (got === undefined || got.refused || !got.length) {
        rows.push(el("p", { className: got?.refused ? "refused" : "note",
                            textContent: got === undefined ? "Reading its tables…" : got.refused ?? "(no keyed tables)" }));
        continue;
      }
      for (const t of hits) {
        const entry = option({ name: t.name, label: `${t.changed ? "● " : ""}${t.name}`,
                               title: `${t.cols} entities, ${t.rows} properties` },
                             (d.file ?? CONFIG) === file ? d.table : null);
        entry.dataset.file = file;
        rows.push(entry);
      }
    }
    filesList.replaceChildren(...rows);
  };
  files.addEventListener("toggle", () => {
    if (files.open && image()) listFiles();
  });
  search.addEventListener("input", drawFiles);
  filesList.addEventListener("click", (event) => {
    const row = event.target.closest?.("button");
    if (!row) return;
    const { file, name } = row.dataset;
    if (name !== undefined) return chosen(name, file);
    if (d.openFiles.delete(file)) return drawFiles();
    d.openFiles.add(file);
    delete d.tablesOf[file];   // read anew: its marks may have changed while it was closed
    drawFiles();
    openFile(file);
  });
  imaged();

  // A cell: its text (a default greyed), ● when changed, ⚠ where a ticked pack writes it, its note as its title.
  const noteOf = (cell) => [cell.label && cell.note ? `${cell.label}: ${cell.note}` : cell.note,
                            cell.unit || cell.range ? [cell.unit, cell.range && `range ${cell.range.join(" to ")} `
                              + "(a hint, not a limit)"].filter(Boolean).join(", ") : "",
                            cell.int32 && `The game reads it as a 32-bit integer (it ${cell.int32 === "round"
                              ? "rounds" : "truncates"} a fraction).`,
                            "vanilla" in cell && `Changed: vanilla ${cell.vanilla || "(empty)"}.`,
                            cell.written && WRITTEN].filter(Boolean).join("\n");
  const td = (cell) => {
    if (!cell) return el("td");
    if (!cell.ref) return el("td", { className: "read", textContent: cell.read, title: cell.note || "" });
    const shown = cell.text || (cell.default != null ? `${cell.default} (default)` : "");
    const node = el("td", { className: "cell", textContent: shown, tabIndex: 0, title: noteOf(cell) });
    node.classList.toggle("empty", !cell.text);
    node.classList.toggle("changed", "vanilla" in cell);
    node.classList.toggle("written", Boolean(cell.written));
    if ("vanilla" in cell) node.prepend("● ");
    if (cell.written) node.append(" ⚠");
    node.dataset.cell = JSON.stringify(cell);
    return node;
  };
  const block = (b) => {
    const head = b.columns.some(Boolean) ? [el("tr", {}, el("th"), ...b.columns.map((c) => el("th", { textContent: c })))]
      : [];
    const table = el("table", { className: "data-block" }, ...head,
                     ...b.rows.map(([label, cells]) => el("tr", {}, el("th", { textContent: label }), ...cells.map(td))));
    if (!b.title) return table;
    const details = el("details", {}, el("summary", { textContent: b.title }), table);
    details.open = b.open;
    return details;
  };
  // The grid: an entity a row, a property (each row of the table but its names) a column, sorted by a header's click.
  const grid = (g) => {
    const props = g.rows.map((_, r) => r).slice(1);
    const changedAt = new Map(g.changed.map(([c, r, v]) => [`${c}:${r}`, v]));
    const writtenAt = new Set(g.written.map(([c, r]) => `${c}:${r}`));
    let cols = g.cols.map((_, c) => c);
    if (d.changedOnly) cols = cols.filter((c) => props.some((r) => changedAt.has(`${c}:${r}`)));
    if (d.sort) {
      const { row, down } = d.sort;
      const key = (c) => {
        const v = g.cells[c][row];
        return v == null ? [2, 0, ""] : typeof v === "number" ? [0, v, ""] : [1, 0, String(v).toLowerCase()];
      };
      const filled = cols.filter((c) => g.cells[c][row] != null), empty = cols.filter((c) => g.cells[c][row] == null);
      filled.sort((a, b) => {
        const [x, y] = [key(a), key(b)];
        return (x[0] - y[0] || x[1] - y[1] || x[2].localeCompare(y[2])) * (down ? -1 : 1);
      });
      cols = [...filled, ...empty];
    }
    const meta = (c, r) => g.rows_meta[r] ?? g.cols_meta?.[c] ?? {};
    const head = el("tr", {}, el("th", { textContent: "entity" }), ...props.map((r) => {
      const th = el("th", { textContent: g.rows[r] || "(no name)", title: meta(0, r).note ?? "" });
      th.dataset.row = String(r);
      return th;
    }));
    const rows = cols.map((c) => el("tr", {}, el("th", { textContent: g.cols[c] || "(no name)" }), ...props.map((r) => {
      const v = g.cells[c][r], m = meta(c, r);
      const cell = { ...m, ref: [g.name, c, r], value: v, text: v == null ? "" : typeof v === "number"
        ? String(Number(v.toPrecision(6))) : v, ...g.file !== CONFIG ? { file: g.file } : {} };
      if (changedAt.has(`${c}:${r}`)) cell.vanilla = changedAt.get(`${c}:${r}`);
      if (writtenAt.has(`${c}:${r}`)) cell.written = true;
      return td(cell);
    })));
    const table = el("table", { className: "data-grid" }, head, ...rows);
    head.addEventListener("click", (event) => {
      const row = Number(event.target.closest?.("th")?.dataset.row);
      if (!row) return;
      d.sort = d.sort?.row === row ? { row, down: !d.sort.down } : { row, down: false };
      draw();
    });
    return table;
  };
  const draw = () => {
    const a = d.answer;
    if (!a) return;
    body.replaceChildren(...d.view === "tables" ? [el("h3", { textContent: a.file === CONFIG ? `${a.label} (${a.name})`
      : `${a.file.replace(/^gamedata\//, "")} · ${a.name}` }), grid(a)]
      : a.kind === "changes" && !a.sections.length ? [el("p", { className: "note", textContent: UNCHANGED })]
      : a.sections.map((s) => el("section", {}, el("h3", { textContent: s.title }), ...s.blocks.map(block))));
    const sets = d.ops.filter((op) => op.op === "set").length, moves = d.ops.filter((op) => op.op === "move").length;
    const bytes = d.ops.length - sets - moves;   // a mods file's replace_bytes; a move is a level item's new place
    const brought = [bytes && `${bytes} byte edit${bytes === 1 ? "" : "s"}`, moves && `${moves} move${moves === 1 ? "" : "s"}`]
      .filter(Boolean);
    count.textContent = `${sets} edit${sets === 1 ? "" : "s"}`;
    clear.disabled = !d.ops.length;
    undo.disabled = !d.undo.length;
    redo.disabled = !d.redo.length;
    reset.disabled = !d.ops.some(ofTable);
    others.replaceChildren(...brought.length ? [`${brought.join(" and ")} from a mods file (read-only) `,
                                                button("Remove them", () => commit(d.ops.filter((op) => op.op === "set")))]
      : []);
  };

  // Editing: a click, Enter or F2 on a cell opens its editor; Enter (or a dropdown's or checkbox's change, or a
  // checklist's Set) commits, Escape or leaving it cancels. A refusal is one line under the cell's table; Revert is the
  // editor's empty text. A dropdown greys (disables) each value the cell can't take yet, saying what it needs, and a
  // word list is a checklist (Modkit's, Step 2.100), each as the engine answers (grey()). A click in the editor
  // anywhere but its box leaves the box the focus, so a word ticked, Set or Revert never cancels it.
  const editor = (node) => {
    const cell = JSON.parse(node.dataset.cell);
    const choices = cell.choices;
    let input, more = [];
    if (choices?.kind === "yes_no") {
      input = el("input", { type: "checkbox", checked: cell.text !== "" && cell.text !== "0" });
    } else if (choices?.kind === "one") {
      input = select();
      input.append(el("option", { value: "", textContent: "(vanilla)" }),
                   ...choices.values.map((v) => el("option", { value: v, textContent: v })));
      input.value = cell.text;
      grey(cell, choices.values).then((needs) => {
        for (const option of input.options) {
          if (!Object.hasOwn(needs, option.value)) continue;
          option.disabled = true;
          option.textContent = `${option.value} · ${needs[option.value]}`;
        }
      });
    } else {
      input = el("input", { type: "text", value: cell.text, spellcheck: false, autocomplete: "off" });
      if (choices?.kind === "words") more = [button("Set", () => send(input.value)), checklist(cell, choices, input)];
    }
    const revert = button("Revert", () => send(""));
    revert.disabled = !("vanilla" in cell);
    let done = false;
    const send = (value) => {
      if (done) return;
      done = true;
      edit(node, cell, value);
    };
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") send(input.type === "checkbox" ? (input.checked ? "1" : "0") : input.value);
      if (event.key === "Escape") draw();
    });
    if (input.tagName === "SELECT" || input.type === "checkbox") {
      input.addEventListener("change", () => send(input.type === "checkbox" ? (input.checked ? "1" : "0")
        : input.value));
    }
    node.addEventListener("mousedown", (event) => {
      if (!input.contains(event.target)) event.preventDefault();
    });
    node.addEventListener("focusout", (event) => {   // leaving the editor, not for its own words or buttons (a key's Tab)
      if (!done && !node.contains(event.relatedTarget)) setTimeout(() => { if (!done) draw(); }, 0);
    });
    node.replaceChildren(input, ...more.slice(0, 1), revert, ...more.slice(1));
    input.focus();
  };
  // What each of texts the cell can't take yet needs ({text: what}; the engine's check, sdk.data_edit's texts).
  const grey = async (cell, texts) => {
    if (!texts.length) return {};
    const [table, col, row] = cell.ref;
    const given = { edit: { table, col, row, ...cell.file ? { file: cell.file } : {} }, texts, ops: d.ops };
    const reply = await call("data_edit", cell.file ? imaging(given) : { given });
    return "refused" in reply ? {} : reply.needs;
  };
  // A word list's checklist (Modkit's): a box a word of the cell's value set, ticked for each the text holds; a tick
  // adds its word to the text, an untick takes it out, and typing ticks them. Once the text holds as many words as the
  // game does (max_words) the unticked ones are disabled, and a word whose toggle gives a text the cell can't take yet
  // is greyed (it still ticks, toward a text it can), the line under the words saying what grey needs.
  const checklist = (cell, choices, input) => {
    let asked = 0;
    const line = el("span", { className: "note" });
    const words = choices.values.map((word) => {
      const box = el("input", { type: "checkbox" });
      box.addEventListener("change", () => {
        const kept = input.value.split(/\s+/).filter((w) => w && w !== word);
        input.value = [...kept, ...box.checked ? [word] : []].join(" ");
        sync();
      });
      return { word, box, label: el("label", {}, box, word) };
    });
    const sync = async () => {
      const held = input.value.split(/\s+/).filter(Boolean);
      const full = Boolean(cell.max_words) && held.length >= cell.max_words;
      for (const w of words) {
        w.box.checked = held.includes(w.word);
        w.box.disabled = full && !w.box.checked;
        const other = w.box.checked ? held.filter((h) => h !== w.word) : [...held, w.word];
        w.toggled = other.length && !w.box.disabled ? other.join(" ") : null;   // an empty text resets: never grey
      }
      const mine = ++asked, needs = await grey(cell, [...new Set(words.map((w) => w.toggled).filter(Boolean))]);
      if (mine !== asked) return;
      const said = new Set();
      for (const w of words) {
        const what = w.toggled && Object.hasOwn(needs, w.toggled) ? needs[w.toggled] : null;
        w.label.classList.toggle("needs", Boolean(what));
        w.label.title = what ? `${w.word}: ${what}` : "";
        if (what) said.add(what);
      }
      line.textContent = said.size ? `Grey: ${[...said].join(", ")}` : "";
    };
    input.addEventListener("input", sync);
    sync();
    return el("div", { className: "data-words" }, ...words.map((w) => w.label), line);
  };
  // One edit asked at a time, each with the edits as they stand once the one before it is in (an edit sent before
  // the last one's answer would drop it), and asked again if Undo, Redo, Clear, Reset or a load changes the edits while
  // it waits, so its answer never brings back what they took.
  let editing = Promise.resolve();
  const edit = (node, cell, value) => {
    const job = editing.then(async () => {
      const [table, col, row] = cell.ref;
      const made = { table, col, row, value, ...cell.file ? { file: cell.file } : {} };
      let sent, reply;
      do {
        sent = d.ops;
        const given = { edit: made, ops: sent };
        reply = await call("data_edit", cell.file ? imaging(given) : { given });
      } while (sent !== d.ops);
      if ("refused" in reply) {
        draw();
        const at = body.querySelector(`td[data-cell="${CSS.escape(node.dataset.cell)}"]`)?.closest("table");
        at?.after(el("p", { className: "refused", textContent: reply.refused }));
        return;
      }
      if (!same(reply.ops, d.ops)) commit(reply.ops);
      else draw();
    });
    editing = job.catch(() => {});
    return job;
  };
  const commit = (ops) => {
    d.undo.push(d.ops);
    d.redo = [];
    d.ops = ops;
    changed(ops);
    show();
    reread();
  };
  const step = (from, to) => {
    if (!from.length) return;
    to.push(d.ops);
    d.ops = from.pop();
    changed(d.ops);
    show();
    reread();
  };
  body.addEventListener("click", (event) => {
    const node = event.target.closest?.("td.cell");
    if (node && !node.querySelector("input, select")) editor(node);
  });
  body.addEventListener("keydown", (event) => {
    const node = event.target.closest?.("td.cell");
    if (node && event.target === node && (event.key === "Enter" || event.key === "F2")) {
      event.preventDefault();
      editor(node);
    }
  });
  body.addEventListener("focusin", (event) => {
    const node = event.target.closest?.("td.cell, td.read");
    if (node) note.textContent = node.title;
  });

  return {
    open: () => d.opened ? show() : open(),
    ops: () => d.ops,
    load(ops) {
      d.ops = ops ?? [];
      d.undo = [];
      d.redo = [];
      if (d.opened) show();
      reread();
    },
    imaged,
    state: d,   // the tests' and the perf gate's
  };
}
