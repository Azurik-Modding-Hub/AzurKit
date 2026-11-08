// The Variants view's Attacks tab (Step 4.6f; Modkit's AttacksTab, D480, D495, D804): per attack column (the image's
// list but the roll, else the recipe's own; labelled in words, its name in the title) the clip it plays, picked as the
// Moves tab picks (moves.mjs); whom its life drain takes life from; X33's columns that move with the stick (carry) and
// that a held A or B chains (held), a box each in a menu; each recipe clip a column plays, whether it turns to its
// target as the attack starts (seek), and its generator's numbers. Above them, in either gameplay mode: the weapon
// (sdk.variant_weapons, the Models view's list for its base: Default leaves the key out; greyed, saying why, while the
// recipe plays clips of its own, which a weapon's moveset replaces) and its attack numbers (reach, damage, speed:
// multipliers, 1 leaving the key out; any finite number, D23: no clamp) and switches (balance and reaches the ground
// show the mode's own while unset, hits through walls off). A recipe from another shows that one's, read-only, and
// says which weapon plays over its moves; garret4's own body has no weapon or numbers here. The note alone for a
// recipe whose weapon plays every column.
import { canon, clipsOf, el, named, number, picksTab, repr, shownText, weaponOf, whyFixed } from "./moves.mjs";

export const DRAIN_CHOICES = ["nearest", "all"];   // drain.targets, the first the loader's default (the key left out)
export const FLAG_LISTS = [
  ["carry", "Moves with stick:", "These columns' swings follow the stick; a held A or B chains them."],
  ["held", "Chains held:", "A held A or B chains these columns' swings."]];
export const FLAG_CHARS = 12;   // a column list longer than this shows its count, the whole in its title
export const ATTACK_NUMBERS = [["reach", "Reach"], ["damage", "Damage"], ["speed", "Speed"]];
export const ATTACK_SWITCHES = [["balance", "Balance", "Evened to Garret's attacks."],
                                ["ground", "Reaches the ground", "Its melee hits reach the ground."],
                                ["through_walls", "Hits through walls", "Its hits pass through walls."]];
// Each gameplay mode's balance and reach to the ground where a recipe gives none, while the engine's answer
// (variant_read's attack_defaults) is missing: a refused recipe's.
const ATTACK_DEFAULTS = { garret4: [false, false], own: [true, true] };
export const OPTIONAL_NUMBERS = { whoosh: [["takes", 1]] };   // a generator's numbers a recipe may leave out at these
const WEAPON_TIP = "Default: its own. Another weapon plays every attack with its moves.";
const NUMBER_TIP = "1 is its own; the box takes any number.";
const TIP = "Each column: — the build's pick, a clip of this body or the recipe, or another body's (its submenu).";

const object = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const laidOf = (recipe, read) => "from" in recipe && read && !read.refusal ? read.laid ?? null : null;

// An attacks_anims column as the tab labels it: basic1 Basic 1, hose_attack_3 Hose 3, sweep ledge Sweep ledge.
export function columnTitle(column) {
  const words = column.replaceAll("_", " ").replace(/(?<=[a-z])(?=\d)/g, " ").split(/\s+/).filter(Boolean);
  const kept = words.filter((w, i) => !(w === "attack" && i > 0 && i < words.length - 1 && /^\d+$/.test(words[i + 1])));
  const text = kept.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}
// The columns' rows: the image's list (sources), else the recipe's own by name (a recipe from another: that one's).
export const columnsOf = (sources, recipe, read) => {
  if (sources) return sources.columns;
  const laid = laidOf(recipe, read), columns = laid ? laid.columns : recipe.columns;
  return object(columns) ? Object.keys(columns).sort() : [];
};
// Why the columns are left out beyond whyFixed ("" when they aren't): a weapon plays every one.
export const offOf = (recipe) => {
  const weapon = weaponOf(recipe);
  return weapon ? `Its weapon ${weapon} plays every attack: Weapon Default picks clips.` : "";
};
// whyFixed, and for a recipe from one whose weapon plays over its moves, which pick plays them (booblord's Axion staff,
// her spins Booblord spin's).
export function attacksWhyFixed(recipe, read) {
  const [fixed, shown] = whyFixed(recipe, read), over = laidOf(recipe, read)?.over;
  if (!over) return [fixed, shown];
  const theirs = over.pick ? `; these moves are its ${over.pick} pick's` : "";
  return [`${fixed} Its ${over.weapon} plays every attack${theirs}.`, shown];
}
// The recipe's carry or held columns (a recipe from another: that one's, as the loader lays them).
export function listed(recipe, read, key) {
  if ("from" in recipe) return [...laidOf(recipe, read)?.[key] ?? []];
  return Array.isArray(recipe[key]) ? recipe[key].filter((c) => typeof c === "string") : [];
}
// column in or out of the recipe's carry or held, in the columns' order (none left: the key out).
export function setFlag(recipe, read, key, column, on, names) {
  let out = listed(recipe, read, key).filter((c) => c !== column);
  if (on) {
    const at = (c) => names.includes(c) ? names.indexOf(c) : names.length;
    out = [...out, column].sort((a, b) => at(a) - at(b));
  }
  if (out.length) recipe[key] = out;
  else delete recipe[key];
}
// A column list's button text and title: its columns in words, or past FLAG_CHARS their count.
export function flagText(columns, tip) {
  const words = columns.map(columnTitle).join(", ") || "none";
  const text = words.length <= FLAG_CHARS ? words : `${columns.length} columns`;
  return [text, text === words ? tip : `${tip}\n${words}.`];
}
// drain.targets from its choice (nearest, the default: the key out).
export function setDrain(recipe, value) {
  if (value === DRAIN_CHOICES[0]) delete recipe.drain;
  else recipe.drain = { targets: value };
}
// The recipe clip clip's seek (off: the key out).
export function setSeek(recipe, clip, on) {
  const params = recipe.clips?.[clip];
  if (!object(params)) return;
  if (on) params.seek = true;
  else delete params.seek;
}
// A generator's numbers, as the recipe gives them (its optional ones at their defaults where left out); its lists,
// objects, names and switches are JSON work.
export function numbersOf(params) {
  const out = Object.entries(params).filter(([, v]) => typeof v === "number");
  for (const [k, d] of OPTIONAL_NUMBERS[params.generator] ?? []) if (!(k in params)) out.push([k, d]);
  return out;
}
// The recipe clips the columns play (their seeks' boxes), and of those each made by a generator with numbers: [clip,
// its title, its numbers, the columns that play it in words] (the clips' number rows).
export function playedOf(recipe, read, names) {
  const clips = clipsOf(recipe, read), picks = named(recipe, read);
  const played = [...new Set([...picks].filter(([at, c]) => at.startsWith("columns ") && object(clips[c]))
    .map(([, c]) => c))].sort();
  const on = (clip) => names.filter((c) => picks.get(`columns ${c}`) === clip).map(columnTitle).join(", ");
  return [played, played.filter((clip) => clips[clip].generator !== "bake" && numbersOf(clips[clip]).length)
    .map((clip) => [clip, `${clip} (${clips[clip].generator})`, numbersOf(clips[clip]), `on ${on(clip)}`])];
}
// A number of the recipe clip clip's generator (an optional one back at its default: the key out).
export function setNumber(recipe, clip, key, value) {
  const params = recipe.clips?.[clip];
  if (!object(params)) return;
  if ((OPTIONAL_NUMBERS[params.generator] ?? []).some(([k, d]) => k === key && d === value)) delete params[key];
  else params[key] = value;
}
const attacksOf = (recipe) => object(recipe.attacks) ? recipe.attacks : {};
const writeAttacks = (recipe, attacks) => {
  if (Object.keys(attacks).length) recipe.attacks = attacks;
  else delete recipe.attacks;
};
// attacks.<key> from its box (1, the body's own: the key out, and attacks with its last).
export function setAttack(recipe, key, value) {
  const attacks = { ...attacksOf(recipe) };
  if (value === 1) delete attacks[key];
  else attacks[key] = value;
  if (canon(attacks) !== canon(attacksOf(recipe))) writeAttacks(recipe, attacks);
}
// attacks.<key> from its box (the mode's default, or off for through walls: the key out).
export function setSwitch(recipe, key, value, defaults) {
  const attacks = { ...attacksOf(recipe) }, fallback = { balance: defaults[0], ground: defaults[1] }[key] ?? false;
  if (value === fallback) delete attacks[key];
  else attacks[key] = value;
  writeAttacks(recipe, attacks);
}
// weapon from its pick (Default, null: the key out).
export function setWeapon(recipe, name) {
  if (name === null) delete recipe.weapon;
  else recipe.weapon = name;
}
// The weapon row from the recipe and the engine's list (offers: variant_weapons' weapons, null while unread): hidden on
// garret4's own body; a recipe from another's read-only; refused while the recipe plays clips of its own.
export function kitOf(recipe, read, offers) {
  const r = read && !read.refusal ? read : null, base = r ? r.base : recipe.base;
  if (base === "garret4") return { hidden: true };
  const parent = "from" in recipe, mode = r ? r.mode : recipe.mode ?? "own";
  const defaults = r?.attack_defaults ?? ATTACK_DEFAULTS[mode] ?? ATTACK_DEFAULTS.own;
  let weapon, values, switches;
  if (parent) {
    const laid = r?.laid?.attacks;
    weapon = r?.weapon ?? null;
    values = laid ? Object.fromEntries(ATTACK_NUMBERS.map(([k]) => [k, laid[k]])) : {};
    switches = laid ? { balance: laid.balance, ground: laid.ground, through_walls: laid.through_walls } : {};
  } else {
    const attacks = attacksOf(recipe);
    weapon = recipe.weapon ?? null;
    values = Object.fromEntries(ATTACK_NUMBERS.map(([k]) => [k, typeof attacks[k] === "number" ? attacks[k] : 1]));
    switches = { balance: attacks.balance ?? defaults[0], ground: attacks.ground ?? defaults[1],
                 through_walls: attacks.through_walls ?? false };
  }
  // (the site's engine hands a null name as undefined: Default's is null here, as the app's JSON has it)
  const weapons = (offers ?? [{ name: null, label: "Default" }]).map((w) => ({ name: w.name ?? null, label: w.label }));
  if (weapon !== null && !weapons.some((w) => w.name === weapon)) weapons.push({ name: weapon, label: String(weapon) });
  const played = ["clips", "columns", "carry", "held"].filter((k) => {
    const value = recipe[k];
    return Array.isArray(value) ? value.length : object(value) ? Object.keys(value).length : Boolean(value);
  });
  const refused = played.length && weapon === null && !parent
    ? `A weapon plays every attack column: clear its ${played.join(", ")} first.` : "";
  const live = !parent && !refused && weapons.length > 1;
  return { hidden: false, parent, defaults, weapon, weapons, values, switches, refused,
           label: weapons.find((w) => w.name === weapon)?.label ?? "Default",
           open: live || weapon !== null && !parent };
}

// The Attacks tab: the weapon row, then the column pickers, life drain and the column lists, the seeks and the clips'
// numbers. weapons: the engine's list for the recipe less its weapon, its attacks and labels, read once a recipe.
export function attacksTab(ctx) {
  const tab = picksTab(ctx, { id: "var-attacks", tip: TIP });
  const kitNote = el("span", { id: "var-kit-note", className: "note warn" });
  const weapon = el("button", { id: "var-weapon", type: "button", className: "var-pick", title: WEAPON_TIP });
  const switches = Object.fromEntries(ATTACK_SWITCHES.map(([key, label, tip]) => {
    const box = el("input", { type: "checkbox", id: `var-${key.replaceAll("_", "-")}` });
    return [key, [box, el("label", { className: "on", title: tip }, box, ` ${label}`)]];
  }));
  const boxes = Object.fromEntries(ATTACK_NUMBERS.map(([key]) => [key, el("input", {
    type: "text", id: `var-attack-${key}`, inputMode: "decimal", size: 5, title: NUMBER_TIP })]));
  const kit = el("p", { id: "var-kit", className: "rando-row" }, el("span", { textContent: "Weapon:" }), weapon,
                 ...Object.values(switches).map(([, label]) => label),
                 ...ATTACK_NUMBERS.map(([key, label]) => el("label", { className: "field" }, label, " ", boxes[key],
                                                            el("span", { className: "unit", textContent: "×" }))),
                 kitNote);
  tab.element.insertBefore(kit, tab.note);
  const columns = el("div", { id: "var-columns", className: "var-columns" });
  const drains = DRAIN_CHOICES.map((value) => el("input", { type: "radio", name: "var-drain", value }));
  const flags = Object.fromEntries(FLAG_LISTS.map(([key]) => [key, el("button", {
    type: "button", id: `var-${key}`, className: "var-pick" })]));
  const seeks = el("p", { id: "var-seeks", className: "rando-row" });
  const made = el("div", { id: "var-made" });
  const madeNote = el("p", { id: "var-made-note", className: "note warn" });
  tab.content.append(columns,
    el("p", { className: "rando-row", title: "nearest: the critter it picks; all: every critter its hit touches." },
       el("span", { textContent: "Life drain takes:" }),
       ...drains.map((input) => el("label", { className: "on" }, input, ` ${input.value}`)),
       ...FLAG_LISTS.flatMap(([key, label]) => [el("span", { textContent: label }), flags[key]])),
    seeks, made, madeNote);
  let names = null, offers = { key: null, image: null, reply: null }, shape = null;

  const changed = (set) => {   // a write into the recipe, read again only where it changed
    const before = canon(ctx.v.recipe);
    set(ctx.v.recipe);
    if (canon(ctx.v.recipe) !== before) ctx.edit();
  };
  // The weapons the recipe takes (sdk.variant_weapons), asked again only for a recipe other but for its weapon,
  // attacks, labels and colours, or another image (Modkit's key); [their entries | null, why not yet].
  const weapons = () => {
    const r = ctx.read();
    if (!r) return [offers.reply?.weapons ?? null, "Reading the recipe…"];   // the last list meanwhile
    if (r.refusal) return [null, "The loader refuses the recipe: see the status line."];
    const { weapon: _w, attacks: _a, title: _t, notes: _n, colours: _c, ...rest } = ctx.v.recipe;
    const key = canon([ctx.given().name, rest]);
    if (offers.key !== key || offers.image !== ctx.image()) {
      offers = { key, image: ctx.image(), reply: null };
      const mine = offers;
      ctx.ask("variant_weapons", ctx.given()).then((reply) => {
        mine.reply = reply;
        if (mine === offers) show();
      });
    }
    if (!offers.reply) return [null, "Reading the weapons it takes…"];
    if ("refused" in offers.reply) return [null, `Its weapons couldn't be read: ${offers.reply.refused}`];
    return [offers.reply.weapons, ctx.image() ? "" : `${ctx.choose} to see how each weapon fits.`];
  };

  const showKit = () => {
    const recipe = ctx.v.recipe, [listedOffers, why] = weapons(), k = kitOf(recipe, ctx.read(), listedOffers);
    kit.hidden = k.hidden;
    if (k.hidden) return;
    weapon.textContent = k.label;
    weapon.disabled = !k.open;
    weapon.title = k.refused || WEAPON_TIP + (why ? `\n${why}` : "");
    weapon.onclick = () => ctx.menus.open("Weapon: what it plays its attacks with",
                                          k.weapons.map((w) => ({ label: w.label, value: w.name })),
                                          (name) => changed((r) => setWeapon(r, name)));
    for (const [key, [box]] of Object.entries(switches)) {
      box.checked = k.switches[key] === true;
      box.disabled = k.parent;
      box.onchange = () => changed((r) => setSwitch(r, key, box.checked, k.defaults));
    }
    for (const [key, label] of ATTACK_NUMBERS) {
      const box = boxes[key], value = String(typeof k.values[key] === "number" ? k.values[key] : 1);
      if (document.activeElement !== box) box.value = value;
      box.disabled = k.parent;
      box.onchange = () => {
        const typed = box.value.trim(), n = number(typed);
        if (n === null) {
          kitNote.textContent = `${label}: ${repr(typed)} is not a number`;
          box.value = value;
          return;
        }
        kitNote.textContent = "";
        changed((r) => setAttack(r, key, n));
      };
    }
  };

  // The columns' rows follow the image's list (else the recipe's), made again only when it changes.
  const layout = (sources) => {
    const now = columnsOf(sources, ctx.v.recipe, ctx.read());
    if (names && canon(now) === canon(names)) return;
    names = now;
    tab.rows.length = 0;
    columns.replaceChildren(...names.map((name) => tab.row("columns", name, `${columnTitle(name)}:`, name)));
  };

  const show = () => {
    if (tab.element.hidden) return;
    showKit();
    const [sources] = ctx.clips();
    layout(sources);
    const recipe = ctx.v.recipe, r = ctx.read();
    const { fixed } = tab.draw({ off: offOf(recipe) });
    const [why] = attacksWhyFixed(recipe, r);
    if (why) tab.note.textContent = why;
    const laid = laidOf(recipe, r);
    const drain = "from" in recipe ? laid?.drain ?? DRAIN_CHOICES[0]
      : object(recipe.drain) ? recipe.drain.targets ?? DRAIN_CHOICES[0] : DRAIN_CHOICES[0];
    for (const input of drains) {
      input.checked = input.value === String(drain);
      input.disabled = Boolean(fixed);
    }
    for (const [key, , tip] of FLAG_LISTS) {
      const [text, title] = flagText(listed(recipe, r, key), tip);
      flags[key].textContent = text;
      flags[key].title = title;
      flags[key].disabled = Boolean(fixed);
    }
    const clips = clipsOf(recipe, r), [played, numbered] = playedOf(recipe, r, names ?? []);
    seeks.replaceChildren(el("span", { textContent: "Turns to its target:" }), ...played.length ? played.map((clip) => {
      const box = el("input", { type: "checkbox", checked: clips[clip].seek === true, disabled: Boolean(fixed) });
      box.dataset.clip = clip;
      box.addEventListener("change", () => changed((rr) => setSeek(rr, clip, box.checked)));
      return el("label", { className: "on", title: shownText(clip, clips, sources?.names) }, box, ` ${clip}`);
    }) : [el("span", { className: "note", textContent: "a recipe clip a column plays" })]);
    // The clips' number rows, made again only when their clips or numbers change, so a box being typed in stays;
    // else each box not being typed in shows its number as the recipe holds it now.
    const current = (clip, key) => numbersOf(clipsOf(ctx.v.recipe, ctx.read())[clip] ?? {}).find(([k]) => k === key)?.[1];
    const now = canon([numbered.map(([clip, title, numbers, on]) => [clip, title, numbers.map(([k]) => k), on]), fixed]);
    if (now === shape) {
      for (const box of made.querySelectorAll("input")) {
        const clip = box.closest("[data-clip]").dataset.clip;
        if (document.activeElement !== box) box.value = String(current(clip, box.dataset.key));
      }
      return;
    }
    shape = now;
    made.replaceChildren(...numbered.map(([clip, title, numbers, on]) => {
      const row = el("p", { className: "rando-row var-made", title: on }, el("span", { textContent: `Clip ${title}:` }));
      row.dataset.clip = clip;
      for (const [key, value] of numbers) {
        const box = el("input", { type: "text", inputMode: "decimal", size: 5, value: String(value),
                                  disabled: Boolean(fixed) });
        box.dataset.key = key;
        box.addEventListener("change", () => {
          const typed = box.value.trim(), n = number(typed), old = current(clip, key);
          if (n === null) {
            madeNote.textContent = `${key.replaceAll("_", " ")}: ${repr(typed)} is not a number`;
            box.value = String(old);
            return;
          }
          madeNote.textContent = "";
          if (n !== old) changed((rr) => setNumber(rr, clip, key, n));
        });
        row.append(el("label", { className: "field" }, key.replaceAll("_", " "), " ", box));
      }
      return row;
    }));
  };
  for (const input of drains) {
    input.addEventListener("change", () => input.checked && changed((r) => setDrain(r, input.value)));
  }
  for (const [key, label] of FLAG_LISTS) {
    flags[key].addEventListener("click", () => {
      const r = ctx.read(), now = listed(ctx.v.recipe, r, key);
      const all = [...names ?? [], ...now.filter((c) => !(names ?? []).includes(c))];
      ctx.menus.checks(label.replace(/:$/, ""), all.map((c) => ({ label: columnTitle(c), checked: now.includes(c) })),
                       (i, on) => changed((recipe) => setFlag(recipe, r, key, all[i], on, names ?? [])));
    });
  }
  return { element: tab.element, show };
}
