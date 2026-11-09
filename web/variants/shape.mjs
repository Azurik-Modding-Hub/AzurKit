// The Variants view's Shape tab (Step 4.6d; Modkit's ShapeTab, D455): a slider per shape the recipe declares (a recipe
// from another: that one's shapes, the values its own), each a track (a display hint) and a box that takes any number
// (D23), what it sizes in its title, then its mesh's ops, the sized first. A recipe from another writes a value as
// shapes.<name>.value, dropped back at that one's own (so it builds as that one does there); one of its own sets its
// shape's value. A drag shows at once the nearest shape this view holds of the recipe as it is but its shapes' values
// (the last Check's, a quick preview's, else the pictures shown), marked Preview (D1011); once let go, the engine's
// quick preview of those values (sdk.variant_preview: the Check's dress, its vertices moved, none of the finer
// triangles a build makes; seconds, with the bar) replaces it, or, with no Check of it yet (none, or the recipe edited
// since beyond its shapes and colours: Modkit's _base_key), the Check itself (the build's own dress): never a dress
// mid-drag (Modkit's AZ-793).
const HINT = "1 is the recipe's own look.";
const TIP = "1 is the recipe's own look. A drag previews it; Check with game data draws it as built.";
const NEAREST = "Preview: the nearest shape drawn";
const QUICK = "A quick preview of these values (its vertices moved, not the finer triangles a build makes): Check with "
  + "game data draws it as built.";
const KEPT = 8;   // the pictures held for the nearest shape: the Check's and the last quick previews'
const isObject = (x) => Boolean(x) && typeof x === "object" && !Array.isArray(x);
const parentOf = (recipe) => typeof recipe.from === "string" ? recipe.from
  : Array.isArray(recipe.from) ? recipe.from[0] : null;

// shapeTab(ctx): the tab ({name, title, element, load(read), checked()}) on the view's ctx (web/variants.mjs).
export function shapeTab(ctx) {
  const { el, state: v } = ctx;
  const ui = {
    note: el("p", { id: "var-shape-note", className: "note", title: TIP }),
    rows: el("div", { id: "var-shapes" }),
    opsTitle: el("p", { id: "var-ops-title", className: "note" }),
    ops: el("tbody"),
  };
  const element = el("div", { id: "var-shape", hidden: true }, ui.note, ui.rows, ui.opsTitle,
    el("div", { className: "var-ops" }, el("table", { id: "var-ops" }, el("thead", {}, el("tr", {},
      ...["Op", "Kind", "Sized by"].map((title) => el("th", { textContent: title })))), ui.ops)));
  // The tab's own: the shapes as last read ({name, title, value, at, sizes}), the track, each row's controls, the
  // pictures held ([{values, key, front, back, exact}]), the values and key it opened at ({values, key}) and the quick
  // preview's asks, all of the variant open (its ticket).
  const t = { ticket: null, shapes: [], track: [0.5, 1.4, 0.05], rows: new Map(), names: "", ops: "", held: [],
              shown: null, opened: null, asking: false, again: false, after: false };

  // Each shape's value in the recipe as it is: its own key's, else (a recipe from another) that one's, else its own.
  const values = (recipe = v.recipe) => Object.fromEntries(t.shapes.map((s) => {
    const own = isObject(recipe.shapes) && isObject(recipe.shapes[s.name]) ? recipe.shapes[s.name].value : undefined;
    return [s.name, typeof own === "number" ? own : s.at ?? s.value];
  }));
  // The recipe but its shapes' values (Modkit's _base_key(shapes=False)): not its title or notes; a recipe from another
  // without its shapes (it lays only values), one of its own each shape without its value; with its colours, the key of
  // the pictures held (they draw them), without, of the dress a quick preview moves (it paints the colours as they are).
  const unshaped = (recipe, colours = true) => {
    const rest = Object.fromEntries(Object.entries(recipe).filter(([k]) => !["title", "notes"].includes(k)
      && (colours || k !== "colours")));
    if (isObject(rest.shapes)) {
      if ("from" in rest) delete rest.shapes;
      else rest.shapes = Object.fromEntries(Object.entries(rest.shapes).map(([n, s]) => [n, isObject(s)
        ? Object.fromEntries(Object.entries(s).filter(([k]) => k !== "value")) : s]));
    }
    return ctx.canon(rest);
  };
  // Whether a let-go previews: the last Check dressed this recipe but its shapes' values and colours (else the Check).
  const dressed = () => Boolean(v.checked && !v.checked[1].refusal)
    && unshaped(JSON.parse(v.checked[0]), false) === unshaped(v.recipe, false);
  const away = (a, b) => Object.keys(a).reduce((n, k) => n + Math.abs(a[k] - (b[k] ?? 1)), 0);
  const hold = (values, key, front, back, exact) => {
    t.held = [{ values, key, front, back, exact },
              ...t.held.filter((p) => p.key !== key || away(p.values, values) > 0)].slice(0, KEPT);
  };

  // A value into the recipe (Modkit's ShapeTab._set): a recipe from another lays shapes.<name>.value over that one's,
  // its key dropped back at that one's own value; one of its own sets its shape's value.
  const put = (shape, value) => {
    const recipe = v.recipe;
    if ("from" in recipe) {
      const shapes = isObject(recipe.shapes) ? recipe.shapes : {};
      if (value === shape.at) delete shapes[shape.name];
      else shapes[shape.name] = { value };
      if (Object.keys(shapes).length) recipe.shapes = shapes;
      else delete recipe.shapes;
    } else if (isObject(recipe.shapes) && isObject(recipe.shapes[shape.name])) {
      recipe.shapes[shape.name].value = value;
    } else {
      return;
    }
    ctx.edit();
  };

  // While the drag runs: the nearest shape held of the recipe as it is but its shapes' values (none: the pictures as
  // they are), marked Preview unless it is these values' own Check, and what letting go does.
  const nearest = () => {
    const now = values(), key = unshaped(v.recipe);
    if (!t.held.length && v.pictured === "shipped" && t.opened?.key === key && away(t.opened.values, now) === 0) {
      ctx.mark(false);   // as it ships
      ctx.note("From the front and from behind, as it ships.");
      return true;
    }
    const near = t.held.reduce((best, p) => p.key !== key ? best
      : !best || away(p.values, now) < away(best.values, now) ? p : best, null);
    const exact = near && away(near.values, now) === 0;
    const next = !ctx.image() ? `${ctx.CHOOSE} to draw these values.` : dressed()
      ? "Let go to preview these values." : "Let go to check these values with game data.";
    const note = exact && near.exact ? "From the front and from behind, as it builds."
      : exact ? QUICK : `${NEAREST}. ${next}`;
    const marked = near ? !(exact && near.exact) : Boolean(v.pictured);
    if (near && near !== t.shown) ctx.picture(near.front, near.back, { note, preview: marked });   // once, not each move
    else {
      ctx.mark(marked);
      ctx.note(note);
    }
    t.shown = near;
    return exact;
  };
  // Let go (Modkit's dress_on_release): the quick preview of the Check's dress, else (no Check of this recipe but its
  // shapes' values and colours: Modkit's _dress_now) the Check, the build's dress; while a Check runs, once it answers.
  // A refusal that no Check of it is kept: the last Check asked again (the site's worker the pool replaced keeps no
  // Check, but its dress is kept: at once) and the preview once more; else (its mesh changed beyond its shapes) the
  // Check.
  const letGo = () => {
    if (!ctx.image() || nearest()) return;
    if (v.checking) return void (t.after = true);
    if (!dressed()) return void ctx.check();
    preview();
  };
  const preview = async (again = false) => {
    if (t.asking) return void (t.again = true);
    t.asking = true;
    const mine = v.ticket, asked = values(), key = unshaped(v.recipe);
    ctx.note("Previewing these values…");
    const reply = await ctx.call("variant_preview", ctx.asked());
    t.asking = false;
    if (mine !== v.ticket) return;
    if ("refused" in reply) {
      if (/Check with game data dresses it/.test(reply.refused) && !t.again) {
        if (!again && await ctx.recheck() && mine === v.ticket) return void preview(true);
        return void (mine === v.ticket && ctx.check());
      }
      ctx.note(`The preview failed: ${ctx.reason(reply.refused)}`);
    } else {
      hold(asked, key, reply.front, reply.back, false);
      if (!t.again) nearest();
    }
    if (t.again) {
      t.again = false;
      preview();
    }
  };

  // A row: the shape's title (what it sizes in its tip), its track and its box; the track spans what it holds (D42).
  const row = (shape) => {
    const [lo, hi, step] = t.track;
    const track = el("input", { type: "range", step, ariaLabel: `${shape.title} (track)` });
    const box = el("input", { type: "text", id: `var-shape-${shape.name}`, inputMode: "decimal", spellcheck: false,
                              autocomplete: "off" });
    const label = el("label", { htmlFor: box.id, textContent: shape.title });
    const fit = (value) => {
      const held = [lo, hi, 1, value].filter((x) => typeof x === "number");
      track.min = String(Math.min(...held));
      track.max = String(Math.max(...held));
      if (typeof value === "number") track.value = String(value);
      box.classList.toggle("changed", value !== (shape.at ?? 1));
    };
    track.addEventListener("input", () => {
      box.value = track.value;
      fit(Number(track.value));
      put(t.rows.get(shape.name).shape, Number(track.value));
      nearest();
    });
    track.addEventListener("change", letGo);   // let go (or a key's step)
    box.addEventListener("change", () => {
      const value = ctx.typed(box.value);   // any finite number; else the engine names the refusal
      fit(value);
      put(t.rows.get(shape.name).shape, value);
      if (typeof value === "number") letGo();
    });
    const line = el("div", { className: "number" }, label, track, box, el("span", { className: "unit", textContent: "×" }));
    t.rows.set(shape.name, { shape, line, label, track, box, fit });
    return line;
  };

  // The rows from the read (Modkit's ShapeTab.load): rebuilt when its shapes change, each value set but where it is
  // being typed or dragged; the mesh's ops listed; the note.
  const load = (r) => {
    if (t.ticket !== v.ticket) {
      Object.assign(t, { ticket: v.ticket, held: [], shown: null, opened: null, asking: false, again: false,
                         after: false });
      ctx.mark(false);
    }
    if (!r) return;
    const parent = parentOf(v.recipe);
    ui.note.textContent = r.refusal ? "The loader refuses the recipe: see the status line."
      : r.shapes.length && parent ? `${parent}'s shapes, the values yours.` : r.shapes.length ? HINT : "No shape sliders.";
    if (r.refusal) return;
    t.shapes = r.shapes;
    t.opened ??= { values: values(), key: unshaped(v.recipe) };   // what a built-in's shipped pictures show
    if (r.track) t.track = r.track;
    const names = JSON.stringify(r.shapes.map((s) => [s.name, s.title, s.at]));
    if (names !== t.names) {
      t.names = names;
      t.rows.clear();
      ui.rows.replaceChildren(...r.shapes.map(row));
    }
    for (const shape of r.shapes) {
      const it = t.rows.get(shape.name);
      it.shape = shape;
      it.label.title = shape.sizes;
      if (document.activeElement !== it.box && document.activeElement !== it.track) {
        it.box.value = String(shape.value);
        it.fit(shape.value);
      }
    }
    const ops = JSON.stringify(r.ops);
    if (ops !== t.ops) {
      t.ops = ops;
      ui.ops.replaceChildren(...r.ops.map((cells) => el("tr", {}, ...cells.map((c) => el("td", { textContent: c })))));
    }
    ui.opsTitle.textContent = r.mesh ? `Its mesh's ops (${r.ops.length}):` : "Its mesh's ops: none";
  };

  // A Check answered: its pictures held at the values it checked (the nearest's exact one), and a let-go that came while
  // it ran previews now (Modkit's _check_again); a drag that moved its shapes' values while it ran or drew shows the
  // nearest again, marked Preview, never those pictures as built.
  const checked = () => {
    const answer = v.checked?.[1], recipe = v.checked ? JSON.parse(v.checked[0]) : null;
    t.shown = null;   // the views show the Check's pictures now
    if (answer && !answer.refusal && answer.front && t.shapes.length) {
      hold(values(recipe), unshaped(recipe), answer.front, answer.back, true);
    }
    if (t.after) {
      t.after = false;
      letGo();
    } else if (recipe && t.shapes.length && unshaped(recipe) === unshaped(v.recipe) && away(values(recipe), values())) {
      nearest();
    }
  };

  return { name: "shape", title: "Shape", element, load, checked };
}
