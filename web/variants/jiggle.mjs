// The Variants view's Jiggle tab (Step 4.6d; Modkit's JiggleTab, D445): a row per real-time spring of the recipe's
// jiggle (its jiggle bones', jiggle.bones[].spring, and jiggle.springs[], on the body's own bones), its stiffness (freq
// Hz, or stiffness N/m for a row given one with a mass), damping and strength (gain), the numbers the game swings it
// by, each box any number (D23; text that isn't one named and the old one kept). A springs row is added on a bone of
// the body no row swings (the last Check's dressed body's, else its base's own from the image), its spring the last
// row's, up to the rows the game swings, or removed. A recipe from another shows that one's springs, copied into its
// own jiggle at the first edit; one with no jiggle says why. Its other fields (frees, new jiggle bones) are JSON work.
const FIELDS = [["stiffness", "Stiffness (Hz)"], ["damping", "Damping"], ["gain", "Strength"]];
const TIP = "Stiffness: how fast it swings (Hz). Damping: how soon it stops (0-1). Strength: how far (0 rigid).";
const NO_JIGGLE = "No jiggle: it needs a recipe with a mesh of its own.";
const HINT = "A spring per bone.";
const NEW_SPRING = { freq: 2.0, damping: 0.3, travel: 0.05, gravity: 0.0, rot_share: 1.0, pivot: "origin" };
const isObject = (x) => Boolean(x) && typeof x === "object" && !Array.isArray(x);
const shown = (x) => typeof x === "number" ? String(x) : "";
const parentOf = (recipe) => typeof recipe.from === "string" ? recipe.from
  : Array.isArray(recipe.from) ? recipe.from[0] : null;

// jiggleTab(ctx): the tab ({name, title, element, load(read), checked()}) on the view's ctx (web/variants.mjs).
export function jiggleTab(ctx) {
  const { el, button, state: v } = ctx;
  const ui = {
    note: el("p", { id: "var-jiggle-note", className: "note", title: TIP }),
    rows: el("tbody", { id: "var-springs" }),
    // WebKit refuses a <select> made by script (its own inline style, CSP's style-src-attr): the page's own, parsed
    bone: ctx.root.querySelector("#var-bone"),
    add: button("var-spring-add", "Add"),
    addNote: el("span", { id: "var-spring-note", className: "note" }),
    entry: el("p", { id: "var-jiggle-entry", className: "note warn" }),
  };
  ui.bone.title = "A bone of the body no row swings";
  const addLine = el("p", { className: "rando-row", id: "var-spring-line" },
    el("label", { className: "field" }, "Add a spring on bone ", ui.bone), ui.add, ui.addNote);
  const element = el("div", { id: "var-jiggle", hidden: true }, ui.note,
    el("div", { className: "var-springs" }, el("table", { id: "var-springs-table" }, el("thead", {}, el("tr", {},
      ...["Spring", ...FIELDS.map(([, title]) => title)].map((title, i) => el("th", { textContent: title,
        title: i === 1 ? "Hz (N/m for a row given a mass: its box says so)" : "" })), el("th"))), ui.rows)),
    addLine, ui.entry);
  // The tab's own: the variant open (its ticket), the jiggle shown (the recipe's own, or the one it is from's as read),
  // its rows ({kind, i, role, bone, key}), their boxes, the rows' shape as built, and the base's bones read for it.
  const t = { ticket: null, laid: null, rows: [], boxes: [], built: "", base: null, asking: null };

  // The jiggle as it builds: the recipe's own, else (a recipe from another) that one's as read. own: copied into the
  // recipe first (an edit's).
  const jiggle = (own = false) => {
    if (isObject(v.recipe.jiggle)) return v.recipe.jiggle;
    if (!t.laid) return null;
    if (!own) return t.laid;
    v.recipe.jiggle = structuredClone(t.laid);
    return v.recipe.jiggle;
  };
  const rowsOf = (doc) => ["bones", "springs"].flatMap((kind) => (Array.isArray(doc?.[kind]) ? doc[kind] : [])
    .map((b, i) => isObject(b) && isObject(b.spring) ? { kind, i, role: String(b.role ?? ""), bone: String(b.bone ?? ""),
                                                          key: "freq" in b.spring ? "freq" : "stiffness" } : null)
    .filter(Boolean));

  // A row's box into its spring (Modkit's _commit): any finite number (D23); anything else named, the old one shown.
  const commit = (row, field, box) => {
    const key = field === "stiffness" ? row.key : field;
    const spring = jiggle()[row.kind][row.i].spring, old = spring[key] ?? (key === "gain" ? 1 : null);
    const value = ctx.typed(box.value);
    if (typeof value !== "number") {
      ui.entry.textContent = `${row.role} ${field}: '${box.value.trim()}' is not a number`;
      box.value = shown(old);
      return;
    }
    ui.entry.textContent = "";
    if (value === old) return;
    jiggle(true)[row.kind][row.i].spring[key] = value;
    ctx.edit();
  };
  const remove = (row) => {
    const doc = jiggle(true);
    doc[row.kind].splice(row.i, 1);
    if (!doc[row.kind].length) delete doc[row.kind];
    ctx.edit();
    draw();
  };
  const build = () => {
    t.boxes = t.rows.map((row) => {
      const spring = jiggle()[row.kind][row.i].spring;
      const boxes = Object.fromEntries(FIELDS.map(([field, title]) => {
        const key = field === "stiffness" ? row.key : field;
        const box = el("input", { type: "text", size: 6, inputMode: "decimal", spellcheck: false, autocomplete: "off",
                                  value: shown(spring[key] ?? (key === "gain" ? 1 : null)),
                                  ariaLabel: `${row.role} ${title}`,
                                  title: key === "stiffness" ? "N/m: this row's spring is a stiffness with a mass" : "" });
        box.addEventListener("change", () => commit(row, field, box));
        return [field, box];
      }));
      const drop = row.kind === "springs" ? button(`var-spring-drop-${row.i}`, "×", "Remove this spring") : null;
      drop?.addEventListener("click", () => remove(row));
      const title = row.role.replaceAll("_", " ");
      ui.rows.append(el("tr", {}, el("td", { textContent: title.charAt(0).toUpperCase() + title.slice(1),
        title: `${row.role}: bone ${row.bone}, ${row.kind === "bones" ? "a jiggle bone its mesh makes" : "the body's own"}` }),
        ...FIELDS.map(([field]) => el("td", {}, boxes[field])), el("td", {}, ...drop ? [drop] : [])));
      return boxes;
    });
  };

  // The Add line's bones (Modkit's _show_bones): the last Check's (its dressed body's, or its base's where it refused),
  // else its base's own read from the image, each but those a row swings and a root (it hangs from none).
  const bones = () => {
    const answer = v.checked?.[1];
    if (Array.isArray(answer?.bones)) return { bones: answer.bones, dressed: !answer.refusal };
    return t.base?.ticket === v.ticket && t.base.bones ? { bones: t.base.bones, dressed: false, base: true } : null;
  };
  const baseBones = async (base) => {   // its base's own, once a variant opened (none of a Check yet)
    const asked = `${v.ticket}|${base}`;
    if (t.asking === asked || t.base?.asked === asked) return;
    t.asking = asked;
    const body = ctx.asked();
    const reply = await ctx.call("base_bones", { ...body, given: { species: base, iso: body.given.iso } });
    if (t.asking === asked) t.asking = null;
    t.base = { asked, ticket: Number(asked.split("|")[0]), bones: "refused" in reply ? null : reply.bones,
               why: reply.refused ?? null };
    showBones();
  };
  const showBones = () => {
    const doc = jiggle(), r = ctx.read();
    if (!doc) return;
    const found = bones(), taken = new Set(["bones", "springs"].flatMap((kind) => (doc[kind] ?? []).map((b) => b?.bone)));
    const free = (found?.bones ?? []).filter(([name, parent]) => parent && !taken.has(name)).map(([name]) => name);
    const full = t.rows.length >= (r?.rows_max ?? Infinity);
    if ([...ui.bone.options].map((o) => o.value).join("|") !== free.join("|")) {
      const was = ui.bone.value;
      ui.bone.replaceChildren(...free.map((name) => el("option", { value: name, textContent: name })));
      if (free.includes(was)) ui.bone.value = was;
    }
    ui.bone.disabled = ui.add.disabled = !free.length || full;
    ui.addNote.textContent = full ? `the game swings ${r.rows_max} rows at most`
      : !found ? !ctx.image() ? `${ctx.CHOOSE} to list its bones` : t.base?.why ?? "Reading its base's bones…"
        : !free.length ? "every bone has a row"
          : !found.dressed && !found.base ? "its base's bones (the check refused it)"
            : found.base ? "its base's bones: Check with game data lists its dressed body's" : "";
    if (!found && ctx.image() && r && !r.refusal && !element.hidden) baseBones(r.base);   // read once it shows
  };
  // Add (Modkit's _add_row): a springs row on the chosen bone, its parent the body's, its role the bone's name as a role
  // may be (taken: _2, _3 ..), its spring the last springs row's, else NEW_SPRING.
  ui.add.addEventListener("click", () => {
    const parents = new Map(bones()?.bones ?? []), bone = ui.bone.value;
    if (!jiggle() || !parents.has(bone)) return;
    const doc = jiggle(true), springs = Array.isArray(doc.springs) ? doc.springs : [];
    const roles = new Set(["bones", "springs"].flatMap((kind) => (doc[kind] ?? []).map((b) => b?.role)));
    let role = bone.toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
    role = /^[a-z]/.test(role) ? role : `j_${role}`;
    for (let n = 2, stem = role; roles.has(role); n++) role = `${stem}_${n}`;
    const last = [...springs].reverse().find((b) => isObject(b?.spring))?.spring;
    springs.push({ role, bone, parent: parents.get(bone), spring: structuredClone(last ?? NEW_SPRING) });
    doc.springs = springs;
    ctx.edit();
    draw();
  });

  // The rows as they stand: rebuilt when their shape changes, each box set but where it is being typed in.
  const draw = () => {
    const doc = jiggle();
    t.rows = doc ? rowsOf(doc) : [];
    const built = JSON.stringify(t.rows);
    if (built !== t.built) {
      t.built = built;
      ui.rows.replaceChildren();
      build();
    } else {
      t.rows.forEach((row, k) => {
        const spring = doc[row.kind][row.i].spring;
        for (const [field] of FIELDS) {
          const key = field === "stiffness" ? row.key : field, box = t.boxes[k][field];
          if (document.activeElement !== box) box.value = shown(spring[key] ?? (key === "gain" ? 1 : null));
        }
      });
    }
    addLine.hidden = !doc;
    showBones();
  };

  // From the read (Modkit's JiggleTab.load): the jiggle it builds with (none: null on the app, undefined from the
  // site's worker), the note and the rows.
  const load = (r) => {
    if (t.ticket !== v.ticket) Object.assign(t, { ticket: v.ticket, laid: null, built: "", base: null, asking: null });
    if (!r) return;
    t.laid = r.refusal ? null : r.jiggle;
    const parent = parentOf(v.recipe);
    if (r.refusal || r.jiggle == null) {
      ui.note.textContent = r.refusal ? "The loader refuses the recipe: see the status line." : NO_JIGGLE;
      t.laid = null;
      ui.rows.replaceChildren();
      Object.assign(t, { rows: [], boxes: [], built: "" });
      addLine.hidden = true;
      return;
    }
    draw();
    ui.note.textContent = !t.rows.length ? "Its jiggle is baked into its clips."
      : parent && !isObject(v.recipe.jiggle) ? `${parent}'s springs: an edit makes them yours.`
        : parent ? `Its own springs, over ${parent}'s body.` : HINT;
  };

  return { name: "jiggle", title: "Jiggle", element, load, checked: showBones, show: showBones };
}
