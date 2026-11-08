// The Variants view's Effects tab (Step 4.6g; Modkit's Effects tab, D538's E4, D771, Step 2.164b): the recipe's
// effects rows, each its group and where it plays, its template (another of those the build has room for), its colour
// (a swatch: the page's colour picker), the attack columns that play it (another row's greyed with its template's
// name; a row keeps one), a projectile's Seek and each param of its template as a track and a box (the track's range a
// hint, D23: the box takes any finite number; auto where the param takes one), a value back at the template's default
// dropping its key; Add an effect (a template, greyed with why where the build takes no more of its group: one
// projectile a build, none where the base's bare-hands kit throws, three shields and beams, none with fx_ring false)
// and ×. After a Check each row shows the bytes it adds (or, where the Check refused a row, that it was refused) and
// the body's own load runs. A recipe from another lays its rows over that one's (the engine's from_effects), so they
// are editable; garret4's own body takes them too. Its fx edits, fx_grafts and fx_ring are listed read-only (JSON
// work). The templates and their params are the engine's (sdk.variants' editor).
import { columnTitle, copy, cut, el, finite, shown } from "./common.mjs";

const GROUPS = { projectile: "Projectile", shield: "Shield", beam: "Beam" };
const ANCHORS = { hand: "from the hand", centre: "round the body", feet: "at its feet", front: "ahead of it" };
const UNITS = { speed: "m/s", life: "s", fade: "s", radius: "m", range: "m", ahead: "m", "projectile size": "m" };
const COLUMN_CHARS = 12;   // a row's columns as its menu shows them (the whole list in its title)
const TIP = "Each row plays an effect on the attack columns ticked in it.";
const HINT = "Each row plays on the attack columns ticked.";
const NONE = "No effects: Add an effect.";
const isObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const canon = (value) => JSON.stringify(value, (_, x) => isObject(x)
  ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, x[k]])) : x);
const hex = (rgb) => `#${rgb.map((c) => Math.round(255 * Math.min(Math.max(c, 0), 1)).toString(16).padStart(2, "0")).join("")}`;
const mib = (n) => (n / 2 ** 20).toFixed(2);
// A drag's step for a param's display range: a power of ten about a fiftieth of it.
const stepOf = ([lo, hi]) => 10 ** Math.floor(Math.log10((hi - lo) / 50));

// effectsTab(ctx, picker): ctx the view's (recipe, read, lists, base, image, checked, edited, choose); picker the page's
// own parsed <input type="color">, the swatches' picker.
export function effectsTab(ctx, picker) {
  const ui = {
    note: el("p", { id: "var-fx-note", className: "note", title: TIP }),
    rows: el("div", { id: "var-fx-rows" }),
    add: el("details", { id: "var-fx-add", className: "var-menu" }),
    load: el("span", { id: "var-fx-load", className: "note" }),
    warn: el("p", { id: "var-fx-warn", className: "note warn" }),
    title: el("p", { id: "var-fx-title", className: "note" }),
    edits: el("tbody"),
  };
  const addList = el("div", { className: "var-menu-list" });
  ui.add.append(el("summary", { textContent: "Add an effect" }), addList);
  const table = el("table", { id: "var-fx-edits", className: "var-fx-edits" },
                   el("thead", {}, el("tr", {}, ...["Edit", "Record", "What"].map((t) => el("th", { textContent: t })))),
                   ui.edits);
  picker.classList.add("var-picker");   // the swatches' picker, out of sight: a swatch opens it
  const element = el("div", { id: "var-effects", hidden: true }, ui.note, ui.rows,
                     el("p", { className: "rando-row" }, ui.add, ui.load, picker), ui.warn, ui.title, table);
  const warn = (text) => {
    ui.warn.textContent = text;
  };
  const templates = () => new Map((ctx.lists()?.templates ?? []).map((t) => [t.name, t]));

  // The rows: the recipe's own, else (a recipe from another without its own) that one's, kept from the last read.
  let parent = [];
  const list = () => {
    const rows = ctx.recipe().effects;
    return Array.isArray(rows) ? rows : "from" in ctx.recipe() ? parent : [];
  };
  // rows into the recipe (the rows it is from another with, or none: the key left out).
  const write = (rows) => {
    const recipe = ctx.recipe();
    if (canon(rows) === canon("from" in recipe ? parent : [])) delete recipe.effects;
    else recipe.effects = rows;
    ctx.edited();
  };
  const edit = (k, change) => {
    const rows = copy(list());
    if (k >= rows.length || !isObject(rows[k])) return;
    change(rows[k]);
    write(rows);
  };
  // The attack columns a row may name: the image's (the Moves tab's list), else those the rows name; and why not yet.
  const columns = () => {
    const base = ctx.read()?.base ?? ctx.recipe().base;
    const got = ctx.image() && typeof base === "string" ? ctx.base("move_sources", base) : null;
    if (got?.value) return [got.value.columns, ""];
    const named = [...new Set(list().flatMap((r) => isObject(r) && Array.isArray(r.columns) ? r.columns : [])
      .filter((c) => typeof c === "string"))];
    return [named, !ctx.image() ? `${ctx.choose} to list its attack columns.` : got?.why
      ? `Its attack columns couldn't be read: ${got.why}` : "Reading the bodies' clips…"];
  };
  // What the base's bare-hands kit throws (sdk.kit_throw), asked once an image and a base: null for none to ask.
  const kitRead = () => {
    const base = ctx.read()?.base ?? ctx.recipe().base;
    return ctx.image() && typeof base === "string" && base !== "garret4" ? ctx.base("kit_throw", base) : null;
  };
  // Why template can't be one more row of rows (or take row at's place): "" when it can.
  const room = (rows, t, at = -1) => {
    const known = templates(), others = rows.filter((r, k) => k !== at && isObject(r)).map((r) => known.get(r.template))
      .filter(Boolean);
    const recipe = ctx.recipe(), r = ctx.read(), lists = ctx.lists();
    if (t.engine === "throw" && others.some((u) => u.engine === "throw")) return "one projectile a build (the game throws one kind)";
    if (t.engine === "throw") {   // the base's bare-hands kit throws on a column the recipe leaves it (only Balanced swings it)
      const read = kitRead(), kit = read?.value;
      if (read && !kit && !read.why) return "its base's bare-hands kit is still being read";
      const weapon = (r ? r.weapon : recipe.weapon) ?? null, mode = r?.mode ?? recipe.mode ?? "own";   // the site's None: undefined
      const left = (kit?.columns ?? []).filter((c) => !(r?.columns ?? []).includes(c));
      if (kit?.throw && mode === "own" && [null, "default"].includes(weapon) && left.length) {
        return `its bare-hands kit throws a ${kit.throw} on ${left.map(columnTitle).join(", ")}: one kind a build `
          + "(give that column a clip on the Attacks tab)";
      }
    }
    if (t.engine === "bound") {
      if (others.filter((u) => u.engine === "bound").length >= lists.bound_rows) return `${lists.bound_rows} shields and beams at most`;
      if (r ? r.fx_ring === false : recipe.fx_ring === false) return "its fx_ring false turns the ring that plays them off (JSON)";
    }
    return "";
  };

  // A row's widgets, made anew when the rows' templates change (an unknown template's: its ×).
  let parts = [], shape = null;
  const build = () => {
    const known = templates();
    parts = list().map((row, k) => {
      const t = isObject(row) ? known.get(row.template) : null;
      const part = { t, sliders: new Map() };
      part.bytes = el("span", { className: "note var-fx-bytes" });
      part.remove = el("button", { type: "button", className: "drop", textContent: "×", title: "Remove the row." });
      part.remove.addEventListener("click", () => {
        const rows = copy(list());
        rows.splice(k, 1);
        write(rows);
      });
      const head = el("p", { className: "rando-row" }, el("b", {
        textContent: t ? `${k + 1}. ${GROUPS[t.group] ?? t.group}` : `${k + 1}. '${row?.template}': no such template`,
        title: t ? `A ${t.group} ${ANCHORS[t.anchor] ?? t.anchor}: ${t.what}` : "" }));
      if (t) {
        part.choice = el("details", { className: "var-menu var-fx-template", title: "Its template (another of the "
                                                                                     + "groups the build has room for)." });
        part.choiceList = el("div", { className: "var-menu-list" });
        part.choiceName = el("summary");
        part.choice.append(part.choiceName, part.choiceList);
        part.swatch = el("button", { type: "button", className: "swatch" });
        part.swatch.addEventListener("click", () => colour(k));
        part.columns = el("details", { className: "var-menu var-fx-columns" });
        part.columnsName = el("summary");
        part.columnsList = el("div", { className: "var-menu-list" });
        part.columns.append(part.columnsName, part.columnsList);
        head.append(part.choice, el("span", { className: "field" }, "Colour ", part.swatch),
                    el("span", { className: "field" }, "Columns ", part.columns));
        if (t.engine === "throw") {
          part.seek = el("input", { type: "checkbox", className: "var-fx-seek" });
          part.seek.addEventListener("change", () => edit(k, (r) => part.seek.checked ? r.seek = true : delete r.seek));
          head.append(el("label", { className: "on", title: "On: each throw flies at the nearest critter ahead; off: "
                                                             + "straight." }, part.seek, " Seek"));
        }
      }
      head.append(part.bytes, part.remove);
      const params = el("div", { className: "var-fx-params" });
      for (const [p, spec] of Object.entries(t?.params ?? {})) {
        const [lo, hi] = spec.range, step = stepOf(spec.range);
        const unit = UNITS[`${t.group} ${p}`] ?? UNITS[p] ?? "", title = `${p.charAt(0).toUpperCase()}${p.slice(1)}`;
        const track = el("input", { type: "range", min: String(lo), max: String(hi), step: String(step) });
        const box = el("input", { type: "text", size: 5, inputMode: "decimal", spellcheck: false, autocomplete: "off" });
        const cell = el("span", { className: "var-fx-param" }, el("span", { className: "var-fx-label",
          textContent: `${title}:`,
          title: `Default ${shown(spec.default)}${unit ? ` ${unit}` : ""}; the box takes any number.` }), track, box,
          el("span", { className: "unit", textContent: unit }));
        const slider = { track, box, value: spec.default };
        const set = (value) => edit(k, (r) => value === spec.default ? delete r[p] : r[p] = value);
        track.addEventListener("input", () => {
          const value = Math.round(Math.round(Number(track.value) / step) * step * 1e9) / 1e9;
          if (value !== slider.value) set(value);
        });
        box.addEventListener("change", () => {
          const text = box.value.trim(), value = finite(text);
          if (value === null) {
            warn(`${title}: '${text}' is not a number`);
            box.value = shown(slider.value);
            return;
          }
          warn("");
          if (value !== slider.value) set(value);
        });
        if ("auto" in spec) {
          slider.auto = el("input", { type: "checkbox" });
          slider.auto.addEventListener("change", () => edit(k, (r) => slider.auto.checked ? r[p] = "auto" : delete r[p]));
          cell.append(el("label", { className: "on", title: `auto: its columns' attack ${spec.auto}.` }, slider.auto,
                         " auto"));
        }
        part.sliders.set(p, slider);
        params.append(cell);
      }
      return Object.assign(part, { element: el("div", { className: "var-fx-row" }, head, params) });
    });
    ui.rows.replaceChildren(...parts.map((part) => part.element));
  };

  // Row k's widgets from its recipe row (and the bytes the Check said it adds, or the Check's refusal naming it).
  const fill = (k, part, row, nbytes, refused) => {
    part.bytes.textContent = refused ? "refused" : nbytes != null ? `${(nbytes / 1024).toFixed(1)} KiB` : "";
    part.bytes.classList.toggle("warn", Boolean(refused));
    part.bytes.title = refused || (nbytes == null ? "the bytes it adds, after a Check" : `${nbytes} bytes it adds (the Check's build)`);
    const t = part.t;
    if (!t || !isObject(row)) return;
    const rows = list(), lists = ctx.lists();
    part.choiceName.textContent = t.title;
    if (!part.choice.open) part.choiceList.replaceChildren(...lists.templates.filter((u) => u.name !== t.name
                                                                                     && !room(rows, u, k)).map((u) => {
      const pickIt = el("button", { type: "button", textContent: u.title });
      pickIt.dataset.template = u.name;
      pickIt.addEventListener("click", () => {
        part.choice.open = false;
        edit(k, (r) => {   // its columns kept, its colour too where the new one takes one; its params the new one's
          const kept = Object.fromEntries(["columns", "colour"].filter((key) => key in r && (key !== "colour" || u.colour))
            .map((key) => [key, r[key]]));
          for (const key of Object.keys(r)) delete r[key];
          Object.assign(r, { template: u.name, ...kept });
        });
      });
      return pickIt;
    }));
    const colour = "colour" in row ? row.colour : t.colour;
    if (Array.isArray(colour) && colour.length === 3 && colour.every((c) => typeof c === "number")) {
      part.swatch.style.background = hex(colour);
      part.swatch.textContent = "";
      part.swatch.title = `${colour.map(shown).join(", ")} (red, green, blue: 1 full)${"colour" in row ? "" : ", the template's"}`;
    } else {
      part.swatch.style.background = "";
      part.swatch.textContent = "—";
      part.swatch.title = t.colour ? "" : `${t.title} takes no colour`;
    }
    part.swatch.disabled = !t.colour;
    const mine = Array.isArray(row.columns) ? row.columns.filter((c) => typeof c === "string") : [];
    const text = mine.map(columnTitle).join(", ") || "none";
    part.columnsName.textContent = cut(text, COLUMN_CHARS);
    part.columns.title = mine.join(", ");
    if (!part.columns.open) part.columnsList.replaceChildren(...columnBoxes(k, rows, mine));
    if (part.seek) part.seek.checked = row.seek === true;
    for (const [p, slider] of part.sliders) {
      const spec = t.params[p], value = p in row ? row[p] : spec.default, auto = value === "auto";
      slider.value = auto || typeof value !== "number" ? spec.default : value;
      if (slider.auto) slider.auto.checked = auto;
      if (document.activeElement !== slider.track) slider.track.value = String(slider.value);
      if (document.activeElement !== slider.box) slider.box.value = shown(slider.value);
      slider.track.disabled = slider.box.disabled = auto;
    }
  };
  // Row k's columns: each attack column, ticked where the row plays it, one another row plays greyed with its
  // template's name; a row keeps one at least (× removes it).
  const columnBoxes = (k, rows, mine) => {
    const taken = new Map(rows.flatMap((r, j) => j !== k && isObject(r) && Array.isArray(r.columns)
      ? r.columns.map((c) => [c, r.template]) : []));
    return columns()[0].map((column) => {
      const box = el("input", { type: "checkbox", checked: mine.includes(column), disabled: taken.has(column),
                                value: column });
      box.addEventListener("change", () => {
        const now = Array.isArray(list()[k]?.columns) ? list()[k].columns : [];
        if (now.length === 1 && now[0] === column) {
          box.checked = true;
          return warn("A row plays on one column at least: × removes it.");
        }
        warn("");
        edit(k, (r) => r.columns = now.includes(column) ? now.filter((c) => c !== column) : [...now, column]);
      });
      return el("label", { className: "on" }, box, ` ${columnTitle(column)}${taken.has(column) ? ` (${taken.get(column)}'s)`
        : ""}`);
    });
  };
  // Row k's colour from the page's colour picker (the template's: the key dropped).
  let picking = -1;
  const colour = (k) => {
    const t = parts[k]?.t, row = list()[k];
    if (!t?.colour || !isObject(row)) return;
    picking = k;
    picker.value = hex(Array.isArray(row.colour) && row.colour.length === 3 ? row.colour : t.colour);
    try {
      picker.showPicker();
    } catch {
      picker.click();
    }
  };
  picker.addEventListener("change", () => {
    const k = picking, t = parts[k]?.t;
    if (!t?.colour) return;
    const rgb = [1, 3, 5].map((i) => Math.round(parseInt(picker.value.slice(i, i + 2), 16) / 255 * 1000) / 1000);
    edit(k, (r) => rgb.every((c, i) => c === t.colour[i]) ? delete r.colour : r.colour = rgb);
  });

  // The Add menu: each template, greyed with why the build takes no more of its group, or no column is free; a new
  // row plays on the first column no row plays, its numbers the template's.
  const fillAdd = () => {
    const rows = list(), [all, why] = columns();
    const taken = new Set(rows.flatMap((r) => isObject(r) && Array.isArray(r.columns) ? r.columns : []));
    const free = all.filter((c) => !taken.has(c));
    let group = null;
    const items = [];
    for (const t of ctx.lists().templates) {
      if (t.group !== group) {
        if (group !== null) items.push(el("hr"));
        group = t.group;
      }
      const not = room(rows, t) || (free.length ? "" : all.length ? "every attack column plays a row"
        : why ? "the attack columns are listed once your image is read" : "");
      const item = el("button", { type: "button", disabled: Boolean(not),
                                  textContent: `${GROUPS[t.group] ?? t.group}: ${t.title}${not ? ` (${not})` : ""}` });
      item.dataset.template = t.name;
      item.addEventListener("click", () => {
        ui.add.open = false;
        if (free.length) write([...copy(list()), { template: t.name, columns: [free[0]] }]);
      });
      items.push(item);
    }
    addList.replaceChildren(...items);
  };
  ui.add.addEventListener("toggle", () => ui.add.open && fillAdd());

  // The fx edits (record, name and type, what they change), fx_grafts and fx_ring, read-only (a recipe from another:
  // that one's, as the loader lays them).
  let laid = null;   // the last read: a recipe from another's fx while an edit's read is out
  const showFx = () => {
    const recipe = ctx.recipe(), r = laid = ctx.read() ?? laid, given = "from" in recipe && r ? r : recipe, rows = [];
    for (const e of Array.isArray(given.fx) ? given.fx : []) {
      if (!isObject(e)) continue;
      const what = Object.keys(e).filter((key) => !["record", "name", "type"].includes(key));
      rows.push([`fx [${e.record}]`, `${e.name} (${e.type})`, what.length === 1 && what[0] === "set" && isObject(e.set)
        ? `sets ${Object.keys(e.set).join(", ")}` : what.join(", ")]);
    }
    for (const g of Array.isArray(given.fx_grafts) ? given.fx_grafts : []) {
      if (isObject(g)) rows.push(["graft", String(g.template ?? g.from ?? ""), "parent" in g ? `under [${g.parent}]` : ""]);
    }
    const ring = given.fx_ring;
    if (ring === false || isObject(ring) && Object.keys(ring).length) {
      rows.push(["fx_ring", ring === false ? "off" : Object.keys(ring).join(", "), ""]);
    }
    ui.edits.replaceChildren(...rows.map((cells) => el("tr", {}, ...cells.map((c) => el("td", { textContent: c })))));
    table.hidden = !rows.length;
    ui.title.textContent = rows.length ? `Its fx edits (${rows.length}, JSON work):`
      : "Its fx edits: none (JSON work: fx, fx_grafts, fx_ring)";
  };

  // The rows from the recipe (made anew when their templates change), the bytes and the load line after a Check, the
  // Add menu (made as it opens) and the fx edits.
  const load = () => {
    if (!ctx.lists()) return;
    const r = ctx.read();
    if (r && "from_effects" in r) parent = r.from_effects;
    else if (!("from" in ctx.recipe())) parent = [];
    const rows = list(), now = canon(rows.map((row) => isObject(row) ? row.template : null));
    if (now !== shape) {
      shape = now;
      build();
    }
    const answer = ctx.checked(), said = answer && !answer.refusal ? answer.effects : null;
    const refusal = answer?.refusal ?? "", named = /\bits (\w+) row\b/.exec(refusal);
    parts.forEach((part, k) => fill(k, part, rows[k], said?.[k] ?? null,
                                    named && isObject(rows[k]) && rows[k].template === named[1] ? refusal : ""));
    const load = answer && !answer.refusal ? answer.load : null;
    ui.load.textContent = load ? `Its own load runs: ${mib(load.own)} MiB (the build's line ${mib(load.error)} MiB)`
      : "Check with game data shows each row's bytes.";
    const [all, why] = columns();
    kitRead();   // asked now, so Add knows what the kit throws by the time it opens
    ui.note.textContent = [all.length ? "" : why, rows.length ? HINT : NONE].filter(Boolean).join(" ");
    if (ui.add.open) fillAdd();
    showFx();
  };

  return { element, load };
}
