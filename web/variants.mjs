// The Characters tab's Variants view (Step 4.6c; Modkit's Variants page, D372, D480, D1087): your own player models,
// each a recipe over a base body (the engine's tools/characters/_player_variants.py), made and kept here in your
// library, a folder each in Modkit's format, which the Models view's Yours group lists and a build wears by name.
// The list: the built-ins (those whose files come from Azurik-Custom-Content marked community), then yours, a refused
// one marked, its refusal in the status line. New (a base species from the shared picker), New from this (a new
// folder of the one open: a built-in's recipe laid whole with its files copied, so every field is its own), Save, Save
// as (the name in its box) and Delete (after a yes); Import (an Export's zip, or a recipe.json alone) and Export (a
// zip, naming the files in it that aren't yours to share). The Base, fixed once chosen; Gameplay, the recipe's mode.
// Body: its size (its own or Garret's height), scale, arms out, rotate, title and notes; Shape and Jiggle (each a
// module of web/variants/, as each later tab is): its shape sliders and its springs; Moves and Attacks (Step 4.6f,
// variants/moves.mjs and variants/attacks.mjs): the clips its slots and attack columns play, its weapon and attack
// numbers; Sounds and Effects (Step 4.6g, web/variants/sounds.mjs and effects.mjs: its sounds, voice and WAVs, and its
// effects rows); JSON: the whole recipe, whose Apply checks it first and keeps the old one on a refusal. Check with
// game data dresses it on your image as a build does (greyed until one is picked, D979), its bar the bottom bar's, and
// draws it. The status line: its recipe's sha256[:12], its grade (unseen for an edit: no sitting graded it), saved or
// not, checked or not. Unsaved edits are asked about before another opens, before a Build of that variant and before
// the page closes. The engine decides every recipe (sdk.variants, variant_open, variant_read, variant_save,
// variant_delete, variant_import, variant_export, variant_check, move_sources, variant_weapons): this view sends the
// recipe and draws the answers. The app keeps
// your variants in the user data folder (where Modkit keeps them); the site keeps them in this browser (IndexedDB's
// azurkit-variants, which the Tools tab's Storage names and its Clear removes) and hands them to its engine as the page
// starts and after each change. Text reaches the page through textContent only.
import { keeper } from "./content.mjs";
import { picker } from "./picker.mjs";
import { attacksTab } from "./variants/attacks.mjs";
import { coloursTab } from "./variants/colours.mjs";
import { effectsTab } from "./variants/effects.mjs";
import { jiggleTab } from "./variants/jiggle.mjs";
import { bodyClips, menus, movesTab } from "./variants/moves.mjs";
import { shapeTab } from "./variants/shape.mjs";
import { soundsTab } from "./variants/sounds.mjs";

const $ = (id) => document.getElementById(id);
const CHOOSE = "Choose your image first (1.)";   // D979's line on what waits for an image
const MODES = { own: "Balanced", garret4: "Skin only" };
const SIZES = { own: "its own", garret4: "Garret's height" };
const JSON_NOTE = "Every field, as the recipe file holds it.";
const LEGEND = "✓ green: fully playable · ~ yellow: rough edges · ✕ red: not playable · ? grey: not yet tested";   // the Models view's
const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i;
const typed = (text) => NUMBER.test(text.trim()) && Number.isFinite(Number(text)) ? Number(text) : text;
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
// A recipe's text with its keys sorted at every depth: an edit that puts a field back reads unedited.
const canon = (value) => JSON.stringify(value, (_, v) => v && typeof v === "object" && !Array.isArray(v)
  ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, v[k]])) : v);
const bytesOf = (data) => typeof data === "string" ? Uint8Array.from(atob(data), (ch) => ch.charCodeAt(0)) : data;
// A refusal's lead, the loader's "variant 'name' (its file): ", left to the line's title.
const reason = (why) => why.replace(/^variant '[^']*'(?: \(.*?\))?: /, "");
// Undo (Modkit's AZ-797): its most steps kept, and edits closer than this, ms, one step (a drag's moves).
const UNDO_STEPS = 100, UNDO_GAP = 600;
const TYPED = "input[type=text], input[type=search], textarea";   // a box with its own undo

// variantsView({root, call, app, say, image, packs, dialog, share, changed, shared}): root the view's element; call the
// engine's ask; app whether the host is the app; say the page's status line; image() the picked image (the site's File,
// the app's path); packs() the Patches tab's ticks (a Check dresses over them); dialog(kind) the app's file dialog (null
// without one); share(folders) hands the site's engine what this browser keeps; changed() runs when the library
// changes (the Models view lists it again); shared the page's community content (web/content.mjs), whose manifest marks
// the built-ins whose files are a community entry's, as the Models view marks them; unsaved(yes) tells the app's server
// whether edits would be lost (lost()), which its window asks about as it closes (the site's: none).
export function variantsView({ root, call, app, say, image, packs, dialog = null, share = () => {}, changed = () => {},
                               shared = null, unsaved = () => {} }) {
  const v = { list: null, kind: "new", name: null, recipe: {}, saved: null, read: null, readFor: null, reading: false,
              again: false, checked: null, checking: null, ticket: 0, tab: "body", shown: "", folder: "", opened: false,
              ships: null, folders: null, listed: 0, manifest: null, undo: [], now: "{}", editAt: -Infinity,
              lostTold: false };
  const kept = app ? null : keeper(globalThis.indexedDB, "azurkit-variants");

  // The view, built once: the list, the pictures with the status, and the editor.
  const button = (id, text, title = "") => el("button", { id, type: "button", textContent: text, title });
  const field = (label, input, unit = "") => el("label", { className: "field" }, label, " ", input,
                                                ...unit ? [el("span", { className: "unit", textContent: unit })] : []);
  const text = (id, props = {}) => el("input", { id, type: "text", spellcheck: false, autocomplete: "off", ...props });
  const ui = {
    filter: el("input", { id: "var-filter", type: "search", placeholder: "Search the variants", spellcheck: false,
                          autocomplete: "off" }),
    legend: el("p", { id: "var-legend", className: "note", textContent: LEGEND }),
    items: el("div", { id: "var-items", className: "picker-list" }),
    front: el("canvas", { id: "var-front", width: 160, height: 160 }),
    back: el("canvas", { id: "var-back", width: 160, height: 160 }),
    pictureNote: el("p", { id: "var-picture-note", className: "note" }),
    name: el("h3", { id: "var-name" }),
    status: el("p", { id: "var-status", className: "note" }),
    checkNote: el("p", { id: "var-check-note", className: "note" }),
    new: button("var-new", "New…", "A new variant on a species' body"),
    from: button("var-from", "New from this…", "A new variant copied from this one, every field yours to edit"),
    as: text("var-as", { placeholder: "new name", title: "The new variant's name: Save as saves the one open under it" }),
    saveAs: button("var-save-as", "Save as"),
    delete: button("var-delete", "Delete", "Delete this variant's folder and every file in it"),
    file: app ? null : el("input", { id: "var-import", type: "file", accept: ".zip,.json,application/zip,application/json" }),
    path: app ? text("var-import-path", { placeholder: "Your zip's full path" }) : null,
    importIt: app ? button("var-import-use", "Import", "An Export's zip, or a recipe.json alone") : null,
    choose: app && dialog ? button("var-import-choose", "Choose…") : null,
    export: button("var-export", "Export…", "This variant as a zip: its recipe and the files it names"),
    base: el("span", { id: "var-base" }),
    // WebKit refuses a <select> made by script (its own inline style, CSP's style-src-attr): the page's own, parsed
    mode: root.querySelector("#var-mode"),
    reach: el("span", { id: "var-reach", className: "note" }),
    previews: null,   // the pictures' row, marked Preview while it shows the nearest shape held (D1011)
    sfxPick: root.querySelector("#var-sfx-pick"),   // the Sounds tab's Sound line's, parsed as the mode's
    fxColour: root.querySelector("#var-fx-colour"),   // the Effects tab's swatches' picker
    bodyNote: el("p", { id: "var-body-note", className: "note" }),
    sizes: Object.keys(SIZES).map((value) => el("input", { type: "radio", name: "var-size", value })),
    scale: text("var-scale", { inputMode: "decimal", size: 6 }),
    arms: text("var-arms", { inputMode: "decimal", size: 6 }),
    rotate: el("input", { id: "var-rotate", type: "checkbox" }),
    title: text("var-title", { size: 28 }),
    notes: el("textarea", { id: "var-notes", rows: 3, spellcheck: true }),
    apply: button("var-apply", "Apply", "The recipe below in place of this one, once the engine takes it"),
    revert: button("var-revert", "Revert", "The recipe as it is, again"),
    jsonNote: el("span", { id: "var-json-note", className: "note", textContent: JSON_NOTE }),
    json: el("textarea", { id: "var-text", rows: 18, spellcheck: false, wrap: "off" }),
    save: button("var-save", "Save", "Write this variant's recipe again (yours only)"),
    check: button("var-check", "Check with game data", "Dress it on your image as a build does, and draw it"),
    undo: button("var-undo", "Undo", "Undo the last edit (⌘Z, Ctrl+Z)"),
    asked: el("dialog", { id: "var-ask", className: "weapon-popup" }),
  };
  ui.mode.append(...Object.entries(MODES).map(([value, title]) => el("option", { value, textContent: title })));
  ui.mode.title = "Balanced: its own size and attacks, evened. Skin only: Garret's attacks.";
  ui.items.setAttribute("role", "listbox");
  ui.items.setAttribute("aria-label", "Variants");
  ui.front.setAttribute("aria-label", "The variant from the front");
  ui.back.setAttribute("aria-label", "The variant from behind");
  const body = el("div", { id: "var-body" }, ui.bodyNote,
    el("p", { className: "rando-row" }, el("span", { className: "field", textContent: "Size" }),
       ...ui.sizes.map((input) => el("label", { className: "on" }, input, ` ${SIZES[input.value]}`)),
       field("Scale", ui.scale, "×"), field("Arms out", ui.arms, "°")),
    el("p", { className: "rando-row" }, el("label", { className: "on", id: "var-rotate-box" }, ui.rotate,
                                           " Rotate: its basic attacks play its attack clips in turn")),
    el("p", { className: "rando-row" }, field("Title", ui.title)),
    el("p", { className: "rando-row var-notes" }, field("Notes", ui.notes)));
  const json = el("div", { id: "var-json", hidden: true },
    el("p", { className: "rando-row" }, ui.apply, ui.revert, ui.jsonNote), el("p", { className: "rando-row" }, ui.json));
  // The tabs, in Modkit's order: each {name, title, element, button?, load?(read), checked?(), show?(), shown?(on)},
  // its button var-tab-<name> (its own, else made here); a module's tab builds on what the view hands it (ctx: the
  // recipe open, its read, an edit, the engine, the pictures).
  const ctx = {
    root, state: v, app, el, button, text, field, typed, reason, canon, CHOOSE,
    call, image,
    read: () => v.readFor === now() ? v.read : null,   // the read of the recipe as it is (null: one is out)
    edit: () => edit(),
    asked: () => ({ ...app ? {} : { file: image() },
                    given: { ...given(), iso: app ? image() : null, packs: packs() } }),
    check: () => check(),
    // The last Check asked again as it was (the site's worker the pool replaced: its kept dress, so at once), so the
    // calls that stand on its dress find it in the engine; whether it dressed.
    recheck: async () => {
      if (!v.checkedBody) return false;
      const reply = await call("variant_check", v.checkedBody, { once: true });
      return !("refused" in reply) && !reply.refusal;
    },
    picture: (front, back, { note, preview = false }) => drawn(front, back, note, preview),
    note: (said) => {
      ui.pictureNote.textContent = said;
      if (painting) painting.note = said;
    },
    mark: (preview) => {
      ui.previews.toggleAttribute("data-preview", preview);
      if (painting) painting.preview = preview;
    },
  };
  const colours = coloursTab({ state: v, call, app, image, packs, dialog, say, given: () => given(), edit: () => edit(),
                               ask: (question) => ask(question), folderOf: (name) => folderOf(name),
                               keep: (name, file, data) => keepFolder(name, { ...v.folders?.[name] ?? {}, [file]: data }) });
  // The Moves and Attacks tabs (Step 4.6f): the recipe open, as read, its edits read again, the engine asked with the
  // image (the site's File, the app's path), their menus in a dialog of the page's own.
  const engineAsk = (type, asked) => call(type, app ? { given: { ...asked, iso: image() || null } }
    : { ...image() ? { file: image() } : {}, given: asked })
    .catch((error) => ({ refused: error?.message ?? String(error) }));
  const movesCtx = { v, choose: CHOOSE, image: () => image(), read: () => v.readFor === now() ? v.read : null,
                     edit: () => edit(), given: () => given(), ask: engineAsk, menus: menus() };
  movesCtx.clips = bodyClips(movesCtx, () => {
    moves.show();
    attacks.show();
  });
  const moves = movesTab(movesCtx), attacks = attacksTab(movesCtx);
  // The tabs' own (Step 4.6g): what each reads of the view and writes back. A base's reads (sdk.own_sounds, kit_throw,
  // move_sources) are asked once an image and a base, the tabs drawn again as each answers.
  const bases = new Map();
  let basesOf = null;
  const fxCtx = {
    app, call, dialog, image, choose: CHOOSE,
    ask: (...asked) => ask(...asked),   // the page's own question (made below)
    recipe: () => v.recipe,
    read: () => v.readFor === now() && v.read && !v.read.refusal ? v.read : null,
    lists: () => v.list?.editor ?? null,
    folder: () => v.kind === "yours" ? v.folder : null,
    checked: () => v.checked?.[0] === now() ? v.checked[1] : null,
    edited: () => edit(),
    base: (kind, species) => {
      if (basesOf !== image()) {
        bases.clear();
        basesOf = image();
      }
      const key = `${kind} ${species}`, file = image();
      if (!bases.has(key)) {
        bases.set(key, {});
        call(kind, { ...app ? {} : { file }, given: { iso: app ? file : null, species } }).then((reply) => {
          if (basesOf !== file) return;
          bases.set(key, "refused" in reply ? { why: reply.refused } : { value: reply });
          if (v.opened) shown(false);
        });
      }
      return bases.get(key);
    },
    // A file added to the variant's folder (the site's: this browser keeps it beside its recipe), else why it didn't.
    keepFile: async (path, data) => {
      const lost = await keepFolder(v.name, { ...v.folders?.[v.name] ?? {}, [path]: data });
      return lost ? `Added ${path}, but this browser didn't keep it (${lost}): Save, then Export it to keep a copy` : "";
    },
  };
  const tabs = [{ name: "body", title: "Body", element: body }, shapeTab(ctx), jiggleTab(ctx),
                { name: "colours", title: "Colours", element: colours.pane, button: colours.tab, shown: colours.shown,
                  checked: () => colours.load() },   // Step 4.6e: a body its build changes recoloured on the Check's dress
                { name: "moves", title: "Moves", element: moves.element, load: () => moves.show(),
                  shown: () => moves.show() },   // Step 4.6f: both shown again at a read and at any tab's click
                { name: "attacks", title: "Attacks", element: attacks.element, load: () => attacks.show(),
                  shown: () => attacks.show() },
                { name: "sounds", title: "Sounds", ...soundsTab(fxCtx, ui.sfxPick) },   // Step 4.6g
                { name: "effects", title: "Effects", ...effectsTab(fxCtx, ui.fxColour) },
                { name: "json", title: "JSON", element: json, show: () => showJson() }];
  const tabButtons = tabs.map((t) => t.button ?? el("button", { id: `var-tab-${t.name}`, type: "button", role: "tab",
                                                                textContent: t.title }));
  tabs.forEach((t, i) => {
    t.element.hidden = i > 0;
    tabButtons[i].setAttribute("aria-selected", String(i === 0));
  });
  ui.previews = el("p", { className: "previews" }, ui.front, ui.back);
  root.replaceChildren(el("div", { className: "chars-cols var-cols" },
    el("div", { className: "chars-list" }, el("p", { className: "rando-row" }, ui.filter), ui.legend, ui.items,
       el("p", { className: "rando-row" }, ...app ? [ui.path, ui.importIt, ...ui.choose ? [ui.choose] : []]
         : [el("label", { className: "file", id: "var-import-box", title: "An Export's zip, or a recipe.json alone" },
               "Import… ", ui.file)], ui.export)),
    el("div", { className: "chars-info" }, ui.previews, ui.pictureNote, ui.name, ui.status, ui.checkNote),
    el("div", { className: "chars-options" },
       el("p", { className: "rando-row" }, ui.new, ui.from, ui.as, ui.saveAs, ui.delete),
       el("p", { className: "rando-row" }, ui.base, field("Gameplay", ui.mode), ui.reach),
       el("p", { className: "views", role: "tablist", ariaLabel: "The variant's fields" }, ...tabButtons),
       ...tabs.map((t) => t.element), el("p", { className: "rando-row" }, ui.save, ui.check, ui.undo))));
  document.body.append(ui.asked);   // asked from any tab (a Build's question too), so never inside a hidden one

  // A question in the page's own dialog (no window of the browser's): a yes or a no, or with value a name (null: no).
  const ask = (question, value = null) => new Promise((done) => {
    const input = value === null ? null : text("var-ask-name", { value, size: 24 });
    const yes = button("var-ask-yes", value === null ? "Yes" : "OK"), no = button("var-ask-no", value === null ? "No"
      : "Cancel");
    ui.asked.replaceChildren(el("p", { className: "note", id: "var-ask-text", textContent: question }),
                             ...input ? [el("p", { className: "rando-row" }, input)] : [],
                             el("p", { className: "rando-row" }, yes, no));
    const end = (answer) => {
      ui.asked.close();
      done(answer);
    };
    yes.addEventListener("click", () => end(input ? input.value.trim() || null : true));
    no.addEventListener("click", () => end(input ? null : false));
    input?.addEventListener("keydown", (event) => event.key === "Enter" && end(input.value.trim() || null));
    ui.asked.addEventListener("cancel", () => end(input ? null : false), { once: true });
    ui.asked.show();
    (input ?? yes).focus();
  });

  const shipped = () => v.ships ??= fetch("characters/index.json").then((reply) => reply.ok ? reply.json() : null)
    .catch(() => null);
  const working = () => v.kind === "yours" ? v.name : v.list?.unsaved ?? "unsaved";
  const folderOf = (name) => `${v.list?.root ?? "variants"}/${name}`;
  const edited = () => v.saved !== canon(v.recipe);
  const given = () => v.kind === "built-in" && !edited() ? { name: v.name }
    : { name: working(), recipe: v.recipe, folder: folderOf(working()) };
  const now = () => canon(v.recipe);
  const label = () => v.kind === "new" ? "(new, unsaved)" : v.kind === "built-in" && edited() ? `${v.name} (edited)` : v.name;

  // The site's library: what this browser keeps, by folder, handed to its engine (none: the app's engine reads its own).
  // Why this browser refused to keep it (a quota, a Clear meanwhile), else null: the engine has it this visit only.
  const keepFolder = async (name, files) => {
    if (app) return null;
    v.folders = { ...(v.folders ?? {}), ...(files ? { [name]: files } : {}) };
    if (!files) delete v.folders[name];
    const lost = await kept.put([["folders", v.folders]]).then(() => null,
      (error) => error?.message || error?.name || "it refused the write");
    share(v.folders);
    return lost;
  };
  const told = (said, lost) => say(lost ? `${said}, but this browser didn't keep it (${lost}): Export it to keep a copy`
    : said, Boolean(lost));
  const ready = app ? Promise.resolve() : kept.get("folders").then((folders) => {
    v.folders = folders ?? {};
    share(v.folders);
  });

  // The list, the engine's: the built-ins (community ones marked, by the community list the page last read), then yours
  // (a refused one marked); the last one asked drawn. A new community list lists them again, and a list a newer one
  // overtook ends with that one, so the view's first open opens a variant whenever the community list comes in.
  const list = () => (v.newest = listing());
  const listing = async () => {
    await ready;
    const mine = ++v.listed;
    v.manifest = shared?.state.manifest ?? null;
    const reply = await call("variants", { given: { content: { manifest: v.manifest } } });
    if (mine !== v.listed) return v.newest;
    if ("refused" in reply) return say(reply.refused, true);
    v.list = reply;
    draw();
  };
  shared?.on((state) => v.opened && state.manifest !== v.manifest && list());
  const entries = () => {
    if (!v.list) return [];
    const wanted = ui.filter.value.trim().toLowerCase();
    const shown = (e) => !wanted || e.name.includes(wanted) || (e.title ?? "").toLowerCase().includes(wanted);
    const grade = (e) => e.grade ?? "unseen";
    return [...v.list.builtins.filter(shown).map((e) => ({ ...e, group: e.community ? "Community" : "Built-in",
                                                           label: e.name, grade: grade(e), kind: "built-in" })),
            ...v.list.yours.filter(shown).map((e) => ({ ...e, group: "Yours", kind: "yours",
                                                        label: e.refusal ? `${e.name} (refused)` : e.name,
                                                        grade: e.refusal ? null : grade(e) }))];
  };
  // A row's grade as the Models view draws a model's: its mark (app.css's data-grade ::after), its colour through its
  // theme's --grade-* (the engine's colour where the theme has none) and its words in its title.
  const tint = (button, grade, colours) => {
    button.dataset.grade = grade;
    button.style.color = `var(--grade-${grade}, ${colours?.[grade] ?? "currentColor"})`;
  };
  const draw = () => {
    const groups = new Map(["Built-in", "Community", "Yours"].map((group) => [group, []]));
    for (const e of entries()) groups.get(e.group).push(e);
    if (v.kind === "new") groups.set("Unsaved", [{ name: "", label: label(), kind: "new" }]);
    ui.items.replaceChildren(...[...groups].filter(([, rows]) => rows.length).flatMap(([group, rows]) => [
      el("h3", { className: "picker-group", textContent: group }),
      ...rows.map((e) => {
        const words = e.grade ? v.list?.grades?.[e.grade] : null;
        const row = el("button", { type: "button", className: "picker-entry model", textContent: e.kind === v.kind
          && e.name === v.name && v.kind === "built-in" ? label() : e.label,
                                   title: e.refusal ?? [e.title ? `${e.title}, on ${e.base}` : e.label, words]
                                     .filter(Boolean).join(" · ") });
        row.dataset.name = e.name;
        row.dataset.kind = e.kind;
        if (e.grade) tint(row, e.grade, v.list?.colours);
        if (e.refusal) row.classList.add("refused");
        row.setAttribute("role", "option");
        row.setAttribute("aria-selected", String(e.kind === v.kind && e.name === (v.kind === "new" ? "" : v.name)));
        return row;
      })]));
  };
  ui.items.addEventListener("click", (event) => {
    const row = event.target.closest?.("button[data-kind]");
    if (row && row.dataset.kind !== "new") choose(row.dataset.kind, row.dataset.name);
  });
  ui.filter.addEventListener("input", draw);

  // Whether leaving the recipe open loses edits: its edits not saved, a New one's too (Save as keeps it), but none
  // before a variant opens (the view's empty New). The recipe open may be left at once without, else after a yes.
  const lost = () => edited() && !(v.kind === "new" && v.saved === null && !Object.keys(v.recipe).length);
  const leave = async () => !lost() || ask(`Leave ${label()} and lose its unsaved edits?`);
  const choose = async (kind, name) => {
    if (kind === v.kind && name === v.name) return;
    if (await leave()) await open(kind, name);
  };

  // Another variant opened: the last one's Check is no longer waited for (its answer dropped) and its pictures go, the
  // variant's own shown (what ships for a built-in) until a Check draws it.
  const open = async (kind, name) => {
    const mine = ++v.ticket;
    const reply = await call("variant_open", { given: { name } });
    if (mine !== v.ticket) return;
    if ("refused" in reply) return say(reply.refused, true);
    Object.assign(v, { kind: reply.kind, name: reply.name, recipe: reply.recipe, saved: canon(reply.recipe),
                       read: reply.read, readFor: canon(reply.recipe), checked: null, checkedBody: null, checking: null,
                       folder: reply.folder });
    ui.as.value = "";
    restart();
    shown(true);
    pictures();
  };
  const fresh = async (species) => {   // New: a recipe on species' own body (garret4: his own build)
    if (!await leave()) return;
    v.ticket++;
    Object.assign(v, { kind: "new", name: null, recipe: species === "garret4" ? { base: species }
      : { base: species, mode: "own" }, saved: null, read: null, readFor: null, checked: null, checkedBody: null,
                       checking: null });
    restart();
    shown(true);
    reread();
    pictures();
  };

  // The recipe read as the library would hold it (sdk.variant_read): its sha, base, mode and body, or its refusal; one
  // ask at a time, the last edit's asked once it answers.
  const reread = async () => {
    if (v.reading) return void (v.again = true);
    v.reading = true;
    const mine = v.ticket, asked = now();
    const reply = await call("variant_read", { given: { name: working(), recipe: v.recipe,
                                                        ...v.kind === "built-in" ? { built_in: v.name } : {} } });
    v.reading = false;
    if (mine === v.ticket && !("refused" in reply)) {
      v.read = reply;
      v.readFor = asked;
      shown(false);
    }
    if (v.again) {
      v.again = false;
      reread();
    }
  };
  // A control wrote into the recipe: the status, the JSON and the list follow, the recipe read again, and Undo keeps the
  // recipe before it (edits closer than UNDO_GAP one step: a drag's).
  const remember = () => {
    const text = JSON.stringify(v.recipe);
    if (text === v.now) return;
    if (performance.now() - v.editAt > UNDO_GAP) v.undo = [...v.undo, v.now].slice(-UNDO_STEPS);
    Object.assign(v, { now: text, editAt: performance.now() });
  };
  const edit = () => {
    remember();
    shown(false);
    reread();
  };
  // Another recipe opened: nothing to undo, its Colours tab from its first row.
  const restart = () => {
    Object.assign(v, { undo: [], now: JSON.stringify(v.recipe), editAt: -Infinity });
    colours.opened();
  };
  // Undo (Modkit's AZ-797: no edit could be undone but by leaving it): the recipe as it was before the last edit, every
  // control from it; ⌘Z (Ctrl+Z) too, but in a text box, which has its own.
  const undo = () => {
    if (!v.undo.length) return;
    Object.assign(v, { now: v.undo.at(-1), undo: v.undo.slice(0, -1), editAt: -Infinity });
    v.recipe = JSON.parse(v.now);
    shown(true);
    reread();
  };
  ui.undo.addEventListener("click", undo);
  document.addEventListener("keydown", (event) => {
    if (!(event.metaKey || event.ctrlKey) || event.shiftKey || event.altKey || event.key.toLowerCase() !== "z"
        || !v.opened || !root.isConnected || root.closest("[hidden]") || event.target?.closest?.(TYPED)) return;
    event.preventDefault();
    undo();
  });

  // The status line, the base and gameplay rows, the buttons and (controls) every field, from the recipe as read.
  const shown = (controls = true) => {
    const r = v.readFor === now() ? v.read : null, base = r?.base ?? v.recipe.base ?? "?", from = "from" in v.recipe;
    ui.name.textContent = label();
    ui.base.textContent = `Base: ${base}`;
    if (r && !r.refusal || base === "garret4") {
      ui.reach.textContent = base === "garret4" ? "his own body: only he wears it, so its look is made on him"
        : r.mesh ? "its mesh: the player's own, NPCs keep theirs" : "colours: the player's own, NPCs keep theirs";
    }
    const fixed = base === "garret4" ? "garret4's own build: Skin only is his own already"
      : from ? "a recipe from another takes its mode" : "";
    ui.mode.value = r?.mode ?? v.recipe.mode ?? "own";
    ui.mode.disabled = Boolean(fixed);
    ui.mode.title = fixed || "Balanced: its own size and attacks, evened. Skin only: Garret's attacks.";
    ui.save.disabled = v.kind !== "yours";
    ui.delete.disabled = v.kind !== "yours";
    ui.export.disabled = v.kind !== "yours" || edited();
    ui.export.title = v.kind !== "yours" ? "Save it as yours first: Export packs a saved variant"
      : edited() ? "Save first: Export packs it as saved" : "This variant as a zip: its recipe and the files it names";
    ui.from.disabled = v.kind === "new";
    ui.undo.disabled = !v.undo.length;
    ui.check.disabled = !image() || Boolean(v.checking);
    ui.check.title = image() ? "Dress it on your image as a build does, and draw it" : CHOOSE;
    status(r);
    if (lost() !== v.lostTold) unsaved(v.lostTold = lost());   // as the status line says it: saved or not
    showJson();
    if (controls) fields(r);
    for (const t of tabs) t.load?.(r);   // each module's tab: its rows from the read (none: as they are)
    if (controls) colours.load();
    draw();
  };
  const status = (r) => {
    const saved = { "built-in": edited() ? "built in: Save as keeps your edits" : "built in",
                    new: "unsaved: Save as keeps it", yours: edited() ? "unsaved edits" : "saved" }[v.kind];
    const check = !image() ? `${CHOOSE} to check it` : v.checking ? "checking with game data…"
      : !v.checked ? "not checked" : v.checked[0] !== now() ? "edited since the check"
        : v.checked[1].refusal ? "the check refused it" : "checked: it builds";
    ui.status.classList.toggle("warn", Boolean(r?.refusal || v.checked?.[0] === now() && v.checked[1].refusal));
    if (!r) {
      ui.status.textContent = `reading… · ${saved}`;
    } else if (r.refusal) {
      ui.status.textContent = `refused: ${reason(r.refusal)} · ${saved}`;
      ui.status.title = r.refusal;
    } else {
      const words = v.list?.grades?.[r.grade] ?? r.grade;
      const refused = v.checked?.[0] === now() && v.checked[1].refusal;
      ui.status.textContent = refused ? `the check refused it: ${reason(refused)} · recipe ${r.sha} · ${words} · ${saved}`
        : `recipe ${r.sha} · ${words} · ${saved} · ${check}`;
      ui.status.title = refused || ui.status.textContent;
    }
  };

  // Body (Modkit's): a number's key written once it moves off its default and dropped back on it (any value: the engine
  // refuses what isn't a finite number, by name, D23); a recipe from another shows that one's body, read-only.
  const fields = (r) => {
    const from = typeof v.recipe.from === "string" ? v.recipe.from : Array.isArray(v.recipe.from) ? v.recipe.from[0] : null;
    const base = r?.base ?? v.recipe.base;
    const arms = v.recipe.arms && typeof v.recipe.arms === "object" ? v.recipe.arms : {};
    const size = r && !r.refusal ? r.size : v.recipe.size ?? "own";
    for (const input of ui.sizes) {
      input.checked = input.value === (size in SIZES ? size : "own");
      input.disabled = Boolean(from) || base === "garret4";
    }
    const set = (input, value) => {
      if (document.activeElement !== input) input.value = String(value);
      input.disabled = Boolean(from);
    };
    set(ui.scale, r && !r.refusal && from ? r.scale : v.recipe.scale ?? 1);
    set(ui.arms, r && !r.refusal && from ? r.arms : arms.out_deg ?? 0);
    const mode = r?.mode ?? v.recipe.mode ?? "own", weapon = r?.weapon ?? null;
    const why = from ? `${from}'s body (read-only): New from this… makes one to edit.`
      : mode === "garret4" ? "Skin only plays Garret's combo." : weapon ? `Its weapon ${weapon} plays every attack.` : "";
    ui.rotate.checked = Boolean(r && !r.refusal ? r.rotate : v.recipe.rotate === true);
    ui.rotate.disabled = Boolean(why);
    $("var-rotate-box").title = why || "Its basic attacks play its attack clips in turn.";
    for (const [input, key] of [[ui.title, "title"], [ui.notes, "notes"]]) {
      const value = typeof v.recipe[key] === "string" ? v.recipe[key] : "";
      if (document.activeElement !== input && input.value !== value) input.value = value;
    }
    ui.bodyNote.textContent = from   // only the body's fields are greyed: Title and Notes stay the recipe's own
      ? `${from}'s body is read-only (New from this… makes one to edit); Title and Notes can be edited.`
      : base === "garret4" ? "garret4's own body: his height is garret4's; its scale, arms and rotate are made on his own build."
        : "Its size. Title and Notes are what the Models view shows for it.";
  };
  for (const input of ui.sizes) {
    input.addEventListener("change", () => {
      if (input.value === "own") delete v.recipe.size;
      else v.recipe.size = input.value;
      edit();
    });
  }
  const number = (input, put) => input.addEventListener("input", () => {
    put(input.value.trim() === "" ? undefined : typed(input.value));
    edit();
  });
  number(ui.scale, (value) => value === 1 || value === undefined ? delete v.recipe.scale : v.recipe.scale = value);
  number(ui.arms, (value) => {
    const arms = v.recipe.arms && typeof v.recipe.arms === "object" ? { ...v.recipe.arms } : {};
    if ((value === 0 || value === undefined) && Object.keys(arms).every((k) => k === "out_deg")) delete v.recipe.arms;
    else v.recipe.arms = { ...arms, out_deg: value ?? 0 };
  });
  ui.rotate.addEventListener("change", () => {
    if (ui.rotate.checked) v.recipe.rotate = true;
    else delete v.recipe.rotate;
    edit();
  });
  for (const [input, key] of [[ui.title, "title"], [ui.notes, "notes"]]) {
    input.addEventListener("input", () => {
      if (input.value) v.recipe[key] = input.value;
      else delete v.recipe[key];
      edit();
    });
  }
  ui.mode.addEventListener("change", () => {
    v.recipe.mode = ui.mode.value;
    edit();
  });

  // JSON: the recipe's text, unless the box holds an edit not applied yet; Apply puts an edit in its place once the
  // engine reads it (else keeps the old, saying why).
  const showJson = (force = false) => {
    const shownText = JSON.stringify(v.recipe, null, 1);
    if (force || ui.json.value === v.shown) {
      ui.json.value = shownText;
      v.shown = shownText;
      ui.jsonNote.textContent = JSON_NOTE;
      ui.jsonNote.classList.remove("warn");
    }
  };
  const keptOld = (why) => {
    ui.jsonNote.textContent = `Kept the old recipe: ${why}`;
    ui.jsonNote.classList.add("warn");
  };
  ui.apply.addEventListener("click", async () => {
    let recipe;
    try {
      recipe = JSON.parse(ui.json.value);
    } catch (error) {
      return keptOld(`not JSON: ${error.message}`);
    }
    if (!recipe || typeof recipe !== "object" || Array.isArray(recipe)) return keptOld("not an object of recipe fields");
    const mine = v.ticket;
    const reply = await call("variant_read", { given: { name: working(), recipe } });
    if (mine !== v.ticket) return;
    if ("refused" in reply || reply.refusal) return keptOld(reply.refused ?? reply.refusal);
    const old = v.readFor === now() && v.read?.base ? v.read.base : v.recipe.base;
    if (v.kind !== "new" && old && reply.base !== old) return keptOld(`the base is ${old}, fixed once chosen: New makes another`);
    v.recipe = recipe;
    v.read = reply;
    v.readFor = now();
    remember();
    showJson(true);
    shown(true);
  });
  ui.revert.addEventListener("click", () => showJson(true));
  tabs.forEach((t, i) => tabButtons[i].addEventListener("click", () => {
    v.tab = t.name;
    tabs.forEach((other, k) => {
      tabButtons[k].setAttribute("aria-selected", String(other === t));
      other.element.hidden = other !== t;
      other.shown?.(other === t);
    });
    t.show?.();
  }));

  // Save, Save as, New from this and Delete: the engine writes (whole or nothing, a refusal named); the site keeps the
  // folder's files it hands back.
  const refused = (why) => {
    ui.status.textContent = `refused: ${reason(why)}`;
    ui.status.title = why;
    ui.status.classList.add("warn");
    say(`Not saved: ${reason(why)}`, true);
  };
  const wrote = async (reply) => {
    const lost = await keepFolder(reply.name, reply.files);
    changed();
    await list();
    return lost;
  };
  ui.save.addEventListener("click", async () => {   // what it sends is what it marks saved: an edit typed meanwhile isn't
    if (v.kind !== "yours") return;
    const mine = v.ticket, name = v.name, recipe = structuredClone(v.recipe);
    const reply = await call("variant_save", { given: { name, recipe, files: !app } });
    if ("refused" in reply) return refused(reply.refused);
    if (mine === v.ticket) v.saved = canon(recipe);
    const lost = await wrote(reply);
    shown(false);
    told(`Saved ${name}`, lost);
  });
  const copyAs = async (name) => {
    if (!name) return;
    const reply = await call("variant_save", { given: { name: working(), recipe: v.recipe, as: name,
                                                        from: v.kind === "yours" ? v.name : null, files: !app } });
    if ("refused" in reply) return refused(reply.refused);
    const lost = await wrote(reply);
    await open("yours", reply.name);
    told(`Saved ${reply.name}`, lost);
  };
  ui.saveAs.addEventListener("click", () => copyAs(ui.as.value.trim()));
  ui.as.addEventListener("keydown", (event) => event.key === "Enter" && copyAs(ui.as.value.trim()));
  const free = () => {   // the open variant's name with the first free _2, _3 ...
    const stem = (v.name ?? "mine").replace(/_\d+$/, "");
    const taken = new Set([...(v.list?.builtins ?? []), ...(v.list?.yours ?? [])].map((e) => e.name)
      .concat(v.list?.species ?? []));
    for (let n = 2; ; n++) if (!taken.has(`${stem}_${n}`)) return `${stem}_${n}`;
  };
  ui.from.addEventListener("click", async () => {
    if (v.kind === "new") return;
    await copyAs(await ask(`A new variant from ${v.name}, named:`, free()));
  });
  ui.delete.addEventListener("click", async () => {
    if (v.kind !== "yours" || !await ask(`Delete ${v.name}: its folder and every file in it?`)) return;
    const gone = v.name, reply = await call("variant_delete", { given: { name: gone } });
    if ("refused" in reply) return refused(reply.refused);
    v.saved = canon(v.recipe);   // nothing left to ask about
    const lost = await keepFolder(gone, null);
    changed();
    await list();
    await open("built-in", v.list.builtins[0].name);
    say(lost ? `Deleted ${gone}, but this browser didn't keep that (${lost}): it may list it again next visit`
      : `Deleted ${gone}`, Boolean(lost));
  });
  // New's species, each in its grade's colour and mark as the Models view first lists it (the shipped answer's), the
  // species then the objects, each group counted in the lead.
  const newPicker = picker({ label: "Species", placeholder: "Search the species", count: null, pick: (name) => {
    ui.asked.close();
    fresh(name);
  }, decorate: (row, e) => e.grade && tint(row, e.grade, e.colours) });
  ui.new.addEventListener("click", async () => {
    const ships = await shipped();
    const species = v.list?.species ?? [], seen = new Map((ships?.view?.species ?? []).map((s) => [s.name, s]));
    const colours = ships?.view?.colours ?? v.list?.colours ?? {}, words = v.list?.grades ?? {};
    const gradeOf = (colour) => colour && Object.keys(colours).find((grade) => colours[grade] === colour);
    const objects = species.filter((name) => seen.get(name)?.object).length;
    newPicker.set(species.map((name) => {
      const s = seen.get(name), grade = gradeOf(s?.colour);
      return { name, label: name === "garret4" ? `${name}  (his own body)` : s?.label ?? name, colours,
               group: s?.object ? "Objects" : "Species",
               ...grade ? { grade, title: `${name} · ${words[grade] ?? grade}` } : {},
               ...ships?.species?.[name] ? { picture: `characters/${ships.species[name]}.front.png` } : {} };
    }), null);
    const cancel = button("var-new-cancel", "Cancel");
    cancel.addEventListener("click", () => ui.asked.close());
    ui.asked.replaceChildren(el("p", { className: "note", id: "var-new-lead", textContent: "A new variant on a species' "
                               + `body: ${species.length - objects} species, then ${objects} objects.` }),
                             newPicker.element, el("p", { className: "rando-row" }, cancel));
    ui.asked.show();
  });

  // Import and Export: the site reads your File and downloads the zip; the app reads and writes by path.
  const imported = async (body) => {
    const reply = await call("variant_import", body);
    if ("refused" in reply) return say(`Not imported: ${reason(reply.refused)}`, true);
    const lost = await wrote(reply);
    if (await leave()) await open("yours", reply.name);
    told(`Imported ${reply.name}`, lost);
  };
  ui.file?.addEventListener("change", async () => {
    const picked = ui.file.files[0];
    ui.file.value = "";
    if (picked) await imported({ given: { files: true }, data: new Uint8Array(await picked.arrayBuffer()) });
  });
  ui.importIt?.addEventListener("click", () => ui.path.value.trim()
    && imported({ path: ui.path.value.trim() }));
  ui.choose?.addEventListener("click", async () => {
    const path = await dialog("variant_file", "");
    if (path) imported({ path });
  });
  ui.export.addEventListener("click", async () => {
    if (v.kind !== "yours") return;
    const held = (names) => names.length ? `; ${names.join(", ")} ${names.length === 1 ? "isn't" : "aren't"} yours to `
      + "share (made from the game's files): keep it to yourself" : "";
    if (app) {
      const out = dialog ? await dialog("variant", `${v.name}.zip`) : "";
      if (out === null) return;
      const reply = await call("variant_export", { name: v.name, out });
      if ("refused" in reply) return say(reply.refused, true);
      return say(`Saved ${reply.out}${held(reply.unshareable)}`);
    }
    const reply = await call("variant_export", { given: { name: v.name } });
    if ("refused" in reply) return say(reply.refused, true);
    const url = URL.createObjectURL(new Blob([bytesOf(reply.zip)], { type: "application/zip" }));
    const a = el("a", { href: url, download: reply.name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    say(`Saving ${reply.name}: your browser's download shows it${held(reply.unshareable)}`);
  });

  // Check with game data (the engine's variant_check: dressed as a build dresses it, over the ticked packs): its load
  // against the build's lines, or the check's refusal, then its pictures (variant_pictures, drawn from the dress the
  // engine kept: the answer first). A Check of an older recipe is dropped once another opens.
  const paint = async (canvas, data) => {
    const g = canvas.getContext("2d");
    g.clearRect(0, 0, canvas.width, canvas.height);
    if (!data) return;
    const bitmap = await createImageBitmap(new Blob([bytesOf(data)], { type: "image/png" }));
    g.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  };
  const pictures = async () => {
    const mine = v.ticket, file = v.kind === "built-in" ? (await shipped())?.variants?.[v.name] : null;
    if (mine !== v.ticket) return;
    v.pictured = painting = null;   // a tab's picture still decoding never lands over these
    ui.previews.removeAttribute("data-preview");
    if (!file) {
      await Promise.all([paint(ui.front, null), paint(ui.back, null)]);
      ui.pictureNote.textContent = image() ? "Check with game data draws it." : `${CHOOSE} to draw it.`;
      return;
    }
    const views = await Promise.all(["front", "back"].map((side) => fetch(`characters/${file}.${side}.png`)
      .then((reply) => reply.ok ? reply.blob() : null).catch(() => null)));
    if (mine !== v.ticket) return;
    await Promise.all([[ui.front, views[0]], [ui.back, views[1]]].map(async ([canvas, blob]) => {
      const g = canvas.getContext("2d");
      g.clearRect(0, 0, canvas.width, canvas.height);
      if (blob) g.drawImage(await createImageBitmap(blob), 0, 0, canvas.width, canvas.height);
    }));
    v.pictured = "shipped";
    ui.pictureNote.textContent = "From the front and from behind, as it ships.";
  };
  // A tab's pictures (the Shape tab's preview, D1011's nearest shape) on the view's two, marked Preview when they are:
  // decoded, then drawn only if no newer one was asked meanwhile (a drag asks one a move), its note and mark the newest
  // the tab gave (ctx.note, ctx.mark) while it decoded.
  let painting = null;
  const drawn = async (front, back, note, preview) => {
    const mine = painting = { note, preview };
    const views = await Promise.all([front, back].map((data) => data
      ? createImageBitmap(new Blob([bytesOf(data)], { type: "image/png" })) : null));
    if (painting !== mine) return;
    painting = null;
    for (const [canvas, view] of [[ui.front, views[0]], [ui.back, views[1]]]) {
      const g = canvas.getContext("2d");
      g.clearRect(0, 0, canvas.width, canvas.height);
      if (view) g.drawImage(view, 0, 0, canvas.width, canvas.height);
    }
    v.pictured = "tab";
    ui.previews.toggleAttribute("data-preview", mine.preview);
    ui.pictureNote.textContent = mine.note;
  };
  const mib = (n) => (n / 2 ** 20).toFixed(2);
  // A Check (a dress: the site's heavy worker's, which keeps it) and, on the site, its pictures asked with it: they wait
  // in F's queue behind it, an ask that isn't heavy, so the worker that dressed it draws them. Asked after its answer,
  // a heavy ask, the pool ran them in the bigger heap, or swapped its workers for work ahead between the two
  // (workers.mjs's one heap), and the other worker keeps no Check. The app's one engine is asked after the answer.
  const checking = (body) => {
    const answer = call("variant_check", body, { once: true });
    return [answer, app ? null : call("variant_pictures", body, { after: answer })];
  };
  const check = async () => {
    if (!image() || v.checking) return;
    const mine = v.ticket, asked = now(), ticket = {}, body = ctx.asked();
    v.checking = ticket;
    shown(false);
    ui.checkNote.textContent = "";
    const [answer, drawing] = checking(body);
    const reply = await answer;
    if (v.checking === ticket) v.checking = null;
    if (mine !== v.ticket) return;
    if ("refused" in reply) {
      v.checked = [asked, { refusal: reply.refused }];
    } else {
      v.checked = [asked, reply];
      v.checkedBody = reply.refusal ? null : body;
      if (!reply.refusal) {
        const load = reply.load;
        ui.checkNote.textContent = load ? `Its own load ${mib(load.own)} MiB (the build warns past `
          + `${mib(load.warning)} MiB and refuses past ${mib(load.error)} MiB).` : "";
      }
    }
    shown(false);
    if (!("refused" in reply || reply.refusal)) {   // its pictures, drawn from the dress the engine kept (Step 4.6q)
      ui.pictureNote.textContent = "Drawing it as it builds…";
      let views = await (drawing ?? call("variant_pictures", body));
      // Drawn by a worker that keeps no Check (the one that dressed it replaced: grown past its line, or stopped): the
      // Check asked again with its pictures, once, as the Shape tab's preview asks it again.
      if (/Check with game data dresses it/.test(views.refused ?? "") && mine === v.ticket && v.checked?.[1] === reply) {
        const [again, redrawn] = checking(body), second = await again;
        if (!("refused" in second || second.refusal)) views = await (redrawn ?? call("variant_pictures", body));
      }
      if (mine !== v.ticket || v.checked?.[1] !== reply) return;
      if ("refused" in views) {
        ui.pictureNote.textContent = `Not drawn: ${views.refused}`;
      } else {
        Object.assign(reply, { front: views.front, back: views.back });   // the Shape tab holds them (Step 4.6d)
        painting = null;
        await Promise.all([paint(ui.front, views.front), paint(ui.back, views.back)]);
        v.pictured = "checked";
        ui.previews.removeAttribute("data-preview");
        ui.pictureNote.textContent = "From the front and from behind, as it builds.";
      }
    }
    for (const t of tabs) t.checked?.();
  };
  ui.check.addEventListener("click", check);

  // Unsaved edits: asked about before the page closes (the site's, a browser's own question), a New one's too, as
  // leaving it in the page is (Modkit's AZ-792); the app's window asks its own (shown() tells its server).
  if (!app) {
    addEventListener("beforeunload", (event) => {
      if (lost()) event.preventDefault();
    });
  }

  return {
    // The view shown: the list read once and the first saved one (else the first built-in) opened; again, the list.
    open: async () => {
      if (v.opened) return list();
      v.opened = true;
      await list();
      if (!v.list) return;
      const yours = v.list.yours.find((e) => !e.refusal);
      await open(yours ? "yours" : "built-in", yours?.name ?? v.list.builtins[0].name);
    },
    // Edit name (the Models view's Edit): the Variants view on it, once any unsaved edits may go.
    edit: async (name) => {
      if (!v.opened) {
        v.opened = true;
        await list();
      }
      const kind = v.list?.yours.some((e) => e.name === name) ? "yours" : "built-in";
      await choose(kind, name);
    },
    imaged: () => {
      if (v.opened) shown(false);
      if (v.opened && !v.pictured) pictures();
      if (v.opened) colours.load();
    },
    // The open variant's name while it has edits not saved (a built-in's, yours), else null: what a build of that name
    // leaves out (it builds the saved recipe).
    unsaved: () => v.kind !== "new" && edited() ? v.name : null,
    ask,
    ready,
    state: v,
    colours: colours.state,
  };
}
