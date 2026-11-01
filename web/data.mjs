// The Data tab (Step 4.7a; Modkit's Game Data editor, D151, D262, D986): config.xbr's cells, edited before an image is
// picked (the engine reads the vanilla config.xbr AzurKit ships). Six views, like the Randomizer tab's Settings ·
// Tracker: Player; Critters, Items, Armor and Weapons, each a picker (web/picker.mjs, its search box by name) and the
// chosen entity's cells of every table that holds it, as sections of mini-tables; and All tables, the 18 tables by
// category (the list filtered by table name), a table as a grid with an entity a row and a property a column, sorted by
// a column's header, Changed only. A cell edits on a click, Enter or F2: a number cell takes any number (never
// clamped: its range is a hint), a value set is a dropdown or a checkbox, an empty cell with a known default shows it
// greyed; the engine checks every edit (tools/data's check) and a refusal is one red line under the cell saying why.
// A changed cell is marked ● with its vanilla value in its note, a cell a ticked pack's slider also writes ⚠ (the data
// edit wins: the build says so). Revert (a cell), Reset table, Undo, Redo, Clear edits and the count of edits. The edits
// are the recipe's xbr set operations, which this tab keeps (ops(), load(ops)) and the page builds with, remembers and
// links; byte edits a mods file brought list read-only, removable. The tab needs no image: its line says the edits join
// each build, which waits for the image (D979). The engine decides everything shown (sdk.data, sdk.data_edit): this
// page sends the tab's choices and draws what comes back. Text only (textContent), no eval.
import { picker } from "./picker.mjs";

const VIEWS = [["player", "Player"], ["critter", "Critters"], ["item", "Items"], ["armor", "Armor"],
               ["weapon", "Weapons"], ["tables", "All tables"]];
const WRITTEN = "A ticked pack's slider also writes this cell; your edit wins, and the build says so.";
const BUILDS = "Your edits join each build, after the packs";
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// dataTab({ call, root, say, packs, changed, image }): call is the engine's (the site's worker, the app's api), root
// the tab's panel, say(text) the page's status line, packs() the Patches tab's ticks (the engine marks the cells they
// write), changed(ops) runs when the edits change (the page builds with them and remembers them) and image() the
// picked image, if any. The page calls open() each time the tab shows (the ticks may have changed), ops() for a
// build's recipe, load(ops) when a mods file, a link or the remembered setup brings edits, and imaged() on each pick.
export function dataTab({ call, root, say, packs, changed, image }) {
  const d = { ops: [], undo: [], redo: [], index: null, view: "player", chosen: {}, table: null, answer: null,
              ticket: 0, changedOnly: false, sort: null, opened: false };
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
  const reset = button("Reset table", () => commit(d.ops.filter((op) => op.op !== "set" || op.table !== d.table)));
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
  const imaged = () => {
    builds.textContent = image() ? `${BUILDS}.` : `${BUILDS}: pick your image (1.) to build.`;
  };
  imaged();
  root.replaceChildren(bar, builds,
                       el("div", { className: "data-body" }, pick.element, el("div", {}, others, body, note)));

  const ask = (what, given = {}) => call("data", { given: { what, ops: d.ops, packs: packs(), ...given } });
  const refused = (reply) => {
    if (!("refused" in reply)) return false;
    say(reply.refused);
    return true;
  };

  // The index (the tables and the pickers' lists), then the view shown.
  const open = async () => {
    d.opened = true;
    say("Reading the game data…");
    const reply = await ask("index");
    if (refused(reply)) return;
    d.index = reply;
    say("");
    choose(d.view);
  };
  const choose = (view) => {
    d.view = view;
    for (const [id, b] of tabs) b.setAttribute("aria-selected", String(id === view));
    pick.element.hidden = view === "player";
    onlyLabel.hidden = reset.hidden = view !== "tables";
    if (!d.index) return;
    const entries = view === "tables"
      ? d.index.tables.map((t) => ({ name: t.name, label: `${t.label} (${t.name})`, group: t.category,
                                     title: `${t.cols} entities, ${t.rows} properties` }))
      : view === "player" ? [] : d.index.pickers[view].map((e) => ({
        name: e.name, label: e.label ?? e.name, group: e.group,
        title: e.info.map(([label, text]) => `${label}: ${text}`).join("\n") }));
    const first = view === "tables" ? d.table ?? entries[0]?.name : d.chosen[view] ?? entries[0]?.name;
    pick.set(entries, first);
    show(first);
  };
  const chosen = (name) => {
    if (d.view === "tables") d.table = name;
    else d.chosen[d.view] = name;
    pick.choose(name);
    show(name);
  };
  // Ask the engine for the view or grid; an answer to an older ask is dropped.
  const show = async (name = d.view === "tables" ? d.table : d.chosen[d.view]) => {
    const mine = ++d.ticket;
    if (d.view === "tables") d.table = name;
    else if (d.view !== "player") d.chosen[d.view] = name;
    const reply = d.view === "tables" ? await ask("table", { table: name })
      : await ask("view", { kind: d.view, name: d.view === "player" ? null : name });
    if (mine !== d.ticket || refused(reply)) return;
    d.answer = reply;
    draw();
  };

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
        ? String(Number(v.toPrecision(6))) : v };
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
    body.replaceChildren(...d.view === "tables" ? [el("h3", { textContent: `${a.label} (${a.name})` }), grid(a)]
      : a.sections.map((s) => el("section", {}, el("h3", { textContent: s.title }), ...s.blocks.map(block))));
    const sets = d.ops.filter((op) => op.op === "set").length, bytes = d.ops.length - sets;
    count.textContent = `${sets} edit${sets === 1 ? "" : "s"}`;
    clear.disabled = !d.ops.length;
    undo.disabled = !d.undo.length;
    redo.disabled = !d.redo.length;
    reset.disabled = !d.ops.some((op) => op.op === "set" && op.table === d.table);
    others.replaceChildren(...bytes ? [`${bytes} byte edit${bytes === 1 ? "" : "s"} from a mods file (read-only) `,
                                       button("Remove them", () => commit(d.ops.filter((op) => op.op === "set")))]
      : []);
  };

  // Editing: a click, Enter or F2 on a cell opens its editor; Enter (or a dropdown's or checkbox's change) commits,
  // Escape or leaving it cancels. A refusal is one line under the cell's table; Revert is the editor's empty text.
  const editor = (node) => {
    const cell = JSON.parse(node.dataset.cell);
    const choices = cell.choices;
    let input;
    if (choices?.kind === "yes_no") {
      input = el("input", { type: "checkbox", checked: cell.text !== "" && cell.text !== "0" });
    } else if (choices?.kind === "one") {
      input = el("select", {}, el("option", { value: "", textContent: "(vanilla)" }),
                 ...choices.values.map((v) => el("option", { value: v, textContent: v })));
      input.value = cell.text;
    } else {
      input = el("input", { type: "text", value: cell.text, spellcheck: false, autocomplete: "off" });
      if (choices?.values?.length) {
        const list = el("datalist", { id: `data-values-${d.ticket}` },
                        ...choices.values.map((v) => el("option", { value: v })));
        node.append(list);
        input.setAttribute("list", list.id);
      }
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
    input.addEventListener("blur", (event) => {
      if (!done && event.relatedTarget !== revert) setTimeout(() => { if (!done) draw(); }, 0);
    });
    node.replaceChildren(input, revert);
    input.focus();
  };
  const edit = async (node, cell, value) => {
    const [table, col, row] = cell.ref;
    const reply = await call("data_edit", { given: { edit: { table, col, row, value }, ops: d.ops } });
    if ("refused" in reply) {
      draw();
      const at = body.querySelector(`td[data-cell="${CSS.escape(node.dataset.cell)}"]`)?.closest("table");
      at?.after(el("p", { className: "refused", textContent: reply.refused }));
      return;
    }
    if (!same(reply.ops, d.ops)) commit(reply.ops);
    else draw();
  };
  const commit = (ops) => {
    d.undo.push(d.ops);
    d.redo = [];
    d.ops = ops;
    changed(ops);
    show();
  };
  const step = (from, to) => {
    if (!from.length) return;
    to.push(d.ops);
    d.ops = from.pop();
    changed(d.ops);
    show();
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
    },
    imaged,
    state: d,   // the tests' and the perf gate's
  };
}
