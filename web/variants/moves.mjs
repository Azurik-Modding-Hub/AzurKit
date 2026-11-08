// The Variants view's Moves tab (Step 4.6f; Modkit's MovesTab over its _Picks, D768, D785): per slot the clip it plays,
// in a menu of the build's own pick (the key left out), the body's own clips, the recipe's and, a submenu each, another
// humanoid body's through the bake (garret4's first, the townsfolk in one submenu, a lender's many clips grouped by
// their first word) and each built-in's Blender clips; a pick of another's adds a "bake" clip to the recipe's clips
// under a short name, dropped once nothing plays it. Idles (the base, six fidgets, each after the one before it, and
// the wait between them), Victory (six, and the seconds before a push of the stick ends one), Jump and Gait. Only what
// the loader takes is offered: a fidget waits for the slot before it, a recipe whose weapon plays every attack names no
// clip of another's, and a body the bake doesn't serve takes none. A recipe from another shows that one's, read-only;
// Skin only its note alone. The Attacks tab (attacks.mjs) shares its pickers, its menus and the bodies' clips.
// The pure parts (lentName, pick, prune, named, menuOf ...) take the recipe and the engine's answers, so Node runs
// them as the page does; the tab draws them through textContent only.

export const AS_BUILT = "—";   // what a slot plays when the recipe names nothing there
export const HINT = "— is the build's own pick.";
export const GROUP_OVER = 20;    // a lender with more clips than this has them grouped by their first word
export const LENT_NAME_MAX = 10;   // a lent clip's recipe name's longest (lentName)
export const PLAYER = "garret4";
export const IDLE_ROWS = [["idles", "idle", "Base:"],
                          ...[1, 2, 3, 4, 5, 6].map((k) => ["idles", `idle_${k}`, `Fidget ${k}:`])];
export const VICTORY_ROWS = [1, 2, 3, 4, 5, 6].map((k) => ["slots", `victory_${k}`, `Victory ${k}:`]);
export const JUMP_ROWS = [["slots", "jump", "Jump:"], ["slots", "jump_standing", "Standing:"],
                          ["slots", "superjump", "Superjump:"], ["slots", "climb_drop", "Ladder drop:"]];
export const GAIT_ROWS = [["slots", "walk", "Walk:"], ["slots", "run", "Run:"], ["slots", "walk_backwards", "Walk back:"],
                          ["slots", "run_backwards", "Run back:"]];
const TIP = "Each slot: — the build's pick, a clip of this body or the recipe, or another body's (its submenu).";

const object = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const say = (value) => value === undefined || value === null ? "None" : String(value);   // as Python's f-string
// A value's text with its keys sorted at every depth: two clips' parameters equal whatever their order.
export const canon = (value) => JSON.stringify(value, (_, v) => object(v)
  ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]])) : v);
// text as a finite number, else null (Modkit's _number: any finite number, D23).
export const number = (text) => {
  const t = String(text).trim();
  return /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(t) && Number.isFinite(Number(t)) ? Number(t) : null;
};
// A typed text as Python's repr names it in a note ('fast').
export const repr = (text) => text.includes("'") && !text.includes('"') ? `"${text}"`
  : `'${text.replaceAll("\\", "\\\\").replaceAll("'", "\\'")}'`;

// A recipe clip name for lender's clip, none of taken: <tag>_<clip> when that is LENT_NAME_MAX characters or fewer,
// else <tag>_<n>; the tag garret4's g4, else the initials of the lender's name and its numbers (town_male_1: tm1).
// Short, since W3 holds a column's v/<name> in a vanilla Anim string (18 characters at most, the free ones fewer).
export function lentName(taken, lender, clip) {
  const parts = lender.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  let tag = lender === PLAYER ? "g4" : parts.map((p) => /^\d+$/.test(p) ? p : p[0]).join("") || "l";
  if (!/^[a-z]/i.test(tag)) tag = `l${tag}`;
  const name = `${tag}_${[...clip.toLowerCase()].map((c) => /^[a-z0-9_]$/.test(c) ? c : "_").join("")}`;
  if ([...name].length <= LENT_NAME_MAX && !taken.has(name)) return name;
  let n = 1;
  while (taken.has(`${tag}_${n}`)) n++;
  return `${tag}_${n}`;
}

// Why a tab of picks is read-only ("" when it isn't) and whether its pickers show: a recipe from another shows that
// one's picks; Skin only plays Garret's moves, its note alone.
export function whyFixed(recipe, read) {
  if ("from" in recipe) {
    const parent = typeof recipe.from === "string" ? recipe.from
      : Array.isArray(recipe.from) ? recipe.from.map(say).join(", ") : say(recipe.from);
    return [`${parent}'s moves (read-only): New from this… makes one to edit.`, true];
  }
  const mode = read && !read.refusal ? read.mode : recipe.mode ?? "own";
  if (mode === "garret4") return ["Skin only plays Garret's moves.", false];
  return ["", true];
}
// The weapon the recipe wears, which plays every attack column (so it names no clips), if any.
export const weaponOf = (recipe) => typeof recipe.weapon === "string" && !["default", "own"].includes(recipe.weapon)
  ? recipe.weapon : null;
// What the loader laid of a recipe from another (sdk.variant_read's laid), else null.
const laidOf = (recipe, read) => "from" in recipe && read && !read.refusal ? read.laid ?? null : null;
// Map "field key" -> clip as the recipe names them (a recipe from another: that one's, as the loader lays them).
export function named(recipe, read) {
  const laid = laidOf(recipe, read);
  const given = "from" in recipe ? laid ?? {} : recipe;
  const out = new Map();
  for (const field of ["idles", "slots", "columns"]) {
    if (!object(given[field])) continue;
    for (const [key, clip] of Object.entries(given[field])) {
      if (key !== "wait" && typeof clip === "string") out.set(`${field} ${key}`, clip);
    }
  }
  return out;
}
export const clipsOf = (recipe, read) => {
  const laid = laidOf(recipe, read), clips = laid ? laid.clips : recipe.clips;
  return object(clips) ? clips : {};
};
// A picker's text: the build's pick, a base clip, a recipe clip (its generator) or a lent one (its clip, then its
// body's species or the built-in it is a Blender clip of).
export function shownText(clip, clips, names = {}) {
  if (clip === undefined || clip === null) return AS_BUILT;
  const p = clips[clip];
  if (!object(p)) return clip;
  if (p.generator === "bake") return `${say(p.clip)} · ${say(p.variant || names[say(p.body).toLowerCase()] || p.body)}`;
  return `${clip} (${say(p.generator)})`;
}
// A fidget waits for the slot before it: the game plays the run of filled idle slots from the base.
export function gated(field, key, picks) {
  if (field !== "idles" || key === "idle") return false;
  const k = Number(key.replace(/^idle_/, ""));
  return !picks.has(`idles ${k === 1 ? "idle" : `idle_${k - 1}`}`);
}

// A lender's submenu of clips; past GROUP_OVER grouped by their first word (a word with one clip under "other").
function clipMenu(clips, spec) {
  const item = (clip) => ({ label: clip, value: { generator: "bake", ...spec, clip } });
  if (clips.length <= GROUP_OVER) return clips.map(item);
  const words = new Map();
  for (const clip of clips) {
    const word = clip.split("_")[0];
    if (!words.has(word)) words.set(word, []);
    words.get(word).push(clip);
  }
  const other = [...words.values()].filter((names) => names.length === 1).flat();
  return [...[...words].filter(([, names]) => names.length > 1), ...other.length ? [["other", other]] : []]
    .map(([word, names]) => ({ label: `${word} (${names.length})`, entries: names.map(item) }));
}
// A slot's menu (Modkit's _fill): the build's pick, the body's own clips, the recipe's own and, unless its weapon plays
// every column, a submenu per body (the townsfolk in one) and built-in the bake lends from. An entry is {label, value}
// (value: null the build's pick, a name, or a bake clip's parameters), {separator} or {label, entries}.
export function menuOf(sources, recipe, read) {
  const out = [{ label: `${AS_BUILT} the build's pick`, value: null }];
  const own = sources?.own ?? [];
  if (own.length) out.push({ separator: true });
  out.push(...own.map((clip) => ({ label: clip, value: clip })));
  const clips = clipsOf(recipe, read);
  const mine = Object.keys(clips).filter((c) => object(clips[c]) && clips[c].generator !== "bake").sort();
  if (mine.length) out.push({ separator: true });
  out.push(...mine.map((clip) => ({ label: `${clip} (${say(clips[clip].generator)})`, value: clip })));
  const lends = sources && (Object.keys(sources.lenders).length || Object.keys(sources.variants).length);
  if (!lends || weaponOf(recipe) !== null) return out;
  out.push({ separator: true });
  const folders = new Map();
  for (const [body, lent] of Object.entries(sources.lenders)) {
    const at = body.lastIndexOf("/"), folder = at < 0 ? "" : body.slice(0, at);
    const entry = { label: sources.names?.[body] ?? body, entries: clipMenu(lent, { body }) };
    if (!folder) {
      out.push(entry);
      continue;
    }
    if (!folders.has(folder)) {
      const title = folder.replaceAll("_", " ");
      folders.set(folder, { label: title.charAt(0).toUpperCase() + title.slice(1).toLowerCase(), entries: [] });
      out.push(folders.get(folder));
    }
    folders.get(folder).entries.push(entry);
  }
  for (const [name, [on, lent]] of Object.entries(sources.variants)) {
    out.push({ label: `${name} (Blender clips)`, entries: clipMenu(lent, { body: on, variant: name }) });
  }
  return out;
}

// key of field plays clip (Modkit's pick): null the build's pick (the key left out; an idle slot's fidgets after it
// too), a name (the body's or the recipe's clip), or a bake clip's parameters (one the recipe has, else added under a
// name of its body and clip); a lent clip nothing plays any more is dropped. Writes into recipe.
export function pick(recipe, field, key, clip, sources = null) {
  if (object(clip)) {
    if (!object(recipe.clips)) recipe.clips = {};
    const clips = recipe.clips;
    let name = Object.keys(clips).find((n) => canon(clips[n]) === canon(clip));
    if (name === undefined) {
      name = lentName(new Set([...Object.keys(clips), ...sources?.own ?? []]),
                      clip.variant || sources?.names?.[clip.body] || clip.body, clip.clip);
      clips[name] = clip;
    }
    clip = name;
  }
  const slots = object(recipe[field]) ? recipe[field] : {};
  if (clip === null) {
    delete slots[key];
    if (field === "idles") {
      const order = IDLE_ROWS.map(([, k]) => k);
      for (const later of order.slice(order.indexOf(key) + 1)) delete slots[later];
    }
  } else {
    slots[key] = clip;
  }
  if (Object.keys(slots).some((k) => k !== "wait")) recipe[field] = slots;
  else delete recipe[field];
  prune(recipe);
}
// Each bake clip no idle, slot, column, arm turn or pose names dropped (an empty clips too).
export function prune(recipe) {
  const clips = recipe.clips;
  if (!object(clips)) return;
  const played = new Set();
  for (const field of ["idles", "slots", "columns"]) {
    if (object(recipe[field])) for (const [k, c] of Object.entries(recipe[field])) if (k !== "wait") played.add(c);
  }
  if (object(recipe.arms) && object(recipe.arms.clips)) for (const c of Object.keys(recipe.arms.clips)) played.add(c);
  if (Array.isArray(recipe.poses)) for (const p of recipe.poses) if (object(p)) played.add(p.clip);
  for (const [name, p] of Object.entries(clips)) {
    if (object(p) && p.generator === "bake" && !played.has(name)) delete clips[name];
  }
  if (!Object.keys(clips).length) delete recipe.clips;
}

// idles.wait from its two boxes (both numbers, or both blank: the game's own 10-10 s): the note it leaves ("" none).
export function setWait(recipe, ends) {
  const texts = ends.map((t) => String(t).trim()), numbers = texts.map(number);
  const idles = recipe.idles;
  const note = texts.some(Boolean) && numbers.includes(null) ? "Wait: give both ends as numbers, or neither"
    : texts.some(Boolean) && !object(idles) ? "Wait: pick an idle base first" : "";
  if (note || !object(idles)) return note;
  if (texts.every(Boolean)) idles.wait = numbers;
  else delete idles.wait;
  return "";
}
// victory_cancel from its box (blank: a victory plays whole): the note it leaves ("" none).
export function setCancel(recipe, text) {
  const t = String(text).trim(), value = number(t);
  if (t && value === null) return `Cancel after: ${repr(t)} is not a number`;
  if (value === null) delete recipe.victory_cancel;
  else recipe.victory_cancel = value;
  return "";
}

const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
export { el };

// The tabs' menus, in one dialog of the page's own (no window of the browser's), each made as it opens: a slot's
// entries ({label, value}, {separator}, {label, entries} a submenu that folds), a weapon's, or a box per column. Every
// entry and submenu carries its path of labels (data-path, joined by " › ").
export function menus() {
  const dialog = el("dialog", { id: "var-menu", className: "weapon-popup" });
  document.body.append(dialog);
  const close = () => dialog.open && dialog.close();
  dialog.addEventListener("cancel", close);
  // A click elsewhere or Escape closes it, as a menu closes.
  document.addEventListener("pointerdown", (event) => dialog.open && !dialog.contains(event.target) && close());
  document.addEventListener("keydown", (event) => event.key === "Escape" && close());
  const frame = (title, ...rows) => {
    const done = el("button", { id: "var-menu-close", type: "button", textContent: "Close" });
    done.addEventListener("click", close);
    dialog.replaceChildren(el("p", { className: "note", id: "var-menu-title", textContent: title }),
                           el("div", { className: "var-menu-list" }, ...rows), el("p", { className: "rando-row" }, done));
    dialog.show();
  };
  const items = (entries, chosen, path = []) => entries.map((entry) => {
    if (entry.separator) return el("hr");
    const at = [...path, entry.label].join(" › ");
    if (entry.entries) {
      const fold = el("details", {}, el("summary", { textContent: entry.label }), ...items(entry.entries, chosen,
                                                                                            [...path, entry.label]));
      fold.dataset.path = at;
      return fold;
    }
    const button = el("button", { type: "button", className: "var-menu-entry", textContent: entry.label });
    button.dataset.path = at;
    button.addEventListener("click", () => {
      close();
      chosen(entry.value);
    });
    return button;
  });
  return {
    dialog,
    close,
    // A menu of entries: chosen(value) on a click, the menu closed first.
    open: (title, entries, chosen) => frame(title, ...items(entries, chosen)),
    // A box per row ({label, checked}): toggled(i, on) on each tick, the menu left open.
    checks: (title, rows, toggled) => frame(title, ...rows.map((row, i) => {
      const box = el("input", { type: "checkbox", checked: row.checked });
      box.addEventListener("change", () => toggled(i, box.checked));
      const label = el("label", { className: "on var-menu-check" }, box, ` ${row.label}`);
      label.dataset.path = row.label;
      return label;
    })),
  };
}

// The bodies' clips the Moves and Attacks tabs offer the recipe's base (sdk.move_sources), read once an image and a
// base, and again for another: [sources | null, why there are none yet]. drawn() runs when an answer lands.
export function bodyClips(ctx, drawn) {
  let kept = { image: null, base: null, reply: null, asking: false };
  return () => {
    const r = ctx.read(), base = r && !r.refusal ? r.base : ctx.v.recipe.base;
    if (!ctx.image()) return [null, `${ctx.choose} to offer the bodies' clips`];
    if (typeof base !== "string") return [null, r ? "The loader refuses the recipe: see the status line." : "Reading the recipe…"];
    if (kept.image !== ctx.image() || kept.base !== base) {
      kept = { image: ctx.image(), base, reply: null, asking: true };
      const mine = kept;
      ctx.ask("move_sources", { species: base }).then((reply) => {
        mine.asking = false;
        mine.reply = reply;
        if (mine === kept) drawn();
      });
    }
    if (kept.asking) return [null, "Reading the bodies' clips…"];
    return "refused" in kept.reply ? [null, `The clips couldn't be read: ${kept.reply.refused}`] : [kept.reply, ""];
  };
}

// A tab of slot pickers (Modkit's _Picks): its note, its groups of rows (a label and a picker each) and the rows'
// pickers, each opening its slot's menu. picks.rows: [field, key, label, button].
export function picksTab(ctx, { id, tip = TIP }) {
  const note = el("p", { id: `${id}-note`, className: "note", title: tip });
  const content = el("div", { id: `${id}-content` });
  const element = el("div", { id, hidden: true }, note, content);
  const rows = [];
  const row = (field, key, label, title = "") => {
    const button = el("button", { type: "button", className: "var-pick" });
    button.dataset.field = field;
    button.dataset.key = key;
    button.addEventListener("click", () => {
      const [sources] = ctx.clips();
      ctx.menus.open(`${label.replace(/:$/, "")}: the clip it plays`, menuOf(sources, ctx.v.recipe, ctx.read()), (clip) => {
        pick(ctx.v.recipe, field, key, clip, sources);
        ctx.edit();
      });
    });
    rows.push([field, key, label, button]);
    return el("p", { className: "var-pick-row" }, el("span", { className: "var-pick-label", textContent: label, title }),
              button);
  };
  // The pickers from the recipe (gate(field, key, picks): whether a slot waits for another), and the note.
  const draw = ({ off = "", gate = () => false } = {}) => {
    const recipe = ctx.v.recipe, r = ctx.read(), [sources, why] = ctx.clips(), [fixed, shown] = whyFixed(recipe, r);
    content.hidden = !shown || Boolean(off);
    const picks = named(recipe, r), clips = clipsOf(recipe, r);
    for (const [field, key, , button] of rows) {
      const text = shownText(picks.get(`${field} ${key}`), clips, sources?.names);
      button.textContent = text;
      button.title = text;
      button.disabled = Boolean(fixed || off || gate(field, key, picks));
    }
    const weapon = weaponOf(recipe);
    note.textContent = fixed || off || why || (weapon ? `Its weapon ${weapon} plays every attack.` : HINT);
    return { recipe, r, fixed, clips, picks, sources };
  };
  return { element, content, note, row, rows, draw };
}

// A row of number boxes (any finite number, D23), committed on Enter or leaving one.
function numbers(label, ids, commit, unit = "s") {
  const boxes = ids.map((id) => el("input", { id, type: "text", inputMode: "decimal", size: 5 }));
  for (const box of boxes) box.addEventListener("change", commit);
  const parts = boxes.flatMap((box, i) => i ? [" – ", box] : [box]);
  return [el("p", { className: "var-pick-row" }, el("span", { className: "var-pick-label", textContent: label }), ...parts,
             el("span", { className: "unit", textContent: ` ${unit}` })), boxes];
}
const shownNumber = (value) => typeof value === "number" ? String(value) : "";

// The Moves tab: Idles over its wait, Victory over its cancel, Jump and Gait, as many columns as the width holds.
export function movesTab(ctx) {
  const tab = picksTab(ctx, { id: "var-moves" });
  const group = (title, rows, ...more) => el("div", { className: "var-pick-group" }, el("h4", { textContent: title }),
                                             ...rows.map(([field, key, label]) => tab.row(field, key, label)), ...more);
  const entry = el("p", { id: "var-moves-entry", className: "note warn" });
  const commit = (set) => {   // the box's note, and the recipe read again only where it changed
    const before = canon(ctx.v.recipe);
    entry.textContent = set(ctx.v.recipe);
    if (canon(ctx.v.recipe) !== before) ctx.edit();
  };
  const [waitRow, wait] = numbers("Wait:", ["var-wait-from", "var-wait-to"],
                                  () => commit((recipe) => setWait(recipe, wait.map((box) => box.value))));
  const [cancelRow, [cancel]] = numbers("Cancel after:", ["var-cancel"],
                                        () => commit((recipe) => setCancel(recipe, cancel.value)));
  tab.content.append(el("div", { className: "var-picks" }, group("Idles", IDLE_ROWS, waitRow),
                        group("Victory", VICTORY_ROWS, cancelRow),
                        el("div", { className: "var-pick-group" }, el("h4", { textContent: "Jump" }),
                           ...JUMP_ROWS.map(([field, key, label]) => tab.row(field, key, label)),
                           el("h4", { textContent: "Gait" }),
                           ...GAIT_ROWS.map(([field, key, label]) => tab.row(field, key, label)))), entry);
  const show = () => {
    if (tab.element.hidden) return;
    const { recipe, r, fixed } = tab.draw({ gate: gated });
    const laid = laidOf(recipe, r);
    const ends = "from" in recipe ? laid?.wait ?? ["", ""]
      : Array.isArray(recipe.idles?.wait) && recipe.idles.wait.length === 2 ? recipe.idles.wait : ["", ""];
    const after = "from" in recipe ? laid?.cancel : recipe.victory_cancel;
    for (const [box, value] of [[wait[0], ends[0]], [wait[1], ends[1]], [cancel, after]]) {
      if (document.activeElement !== box) box.value = shownNumber(value);
      box.disabled = Boolean(fixed);
    }
  };
  return { element: tab.element, show, entry };
}
