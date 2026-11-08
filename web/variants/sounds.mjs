// The Variants view's Sounds tab (Step 4.6g; Modkit's Sounds tab, Step 2.164b, D384, D386): the recipe's sounds (its
// own, or Garret's), its voice (its own, or silent) and its wavs, a WAV a take for each role the engine lists (the
// loader's DROP_ROLES), Add WAV copying the file into the variant's folder (sdk.add_wav; a saved variant's only: the
// site keeps the copy in this browser beside its recipe) and × clearing the role. Voice and WAVs grey with Garret's
// sounds, and on a base with sounds of its own (sdk.own_sounds: the build binds every slot from one folder, so it
// refuses them), saying why, with no Add WAV or × then; Garret's greys while any are set. A recipe from another shows
// that one's sounds, read-only; on garret4's own body Garret's sounds are his own, so its sounds stay its own. Its sfx
// and shouts are listed (JSON work), and the Sound line edits the numbers of a sound its generator makes (a whoosh's;
// a number back at its default dropping its key).
import { columnTitle, cut, el, finite, shown } from "./common.mjs";

const PLAYER = "garret4";
const SOUND_TITLES = { own: "its own", garret4: "Garret's" };
const VOICE_TITLES = { own: "its own", silent: "silent" };
const ROLE_TITLES = { fall: "Long fall" };
const ROLE_TIPS = { fall: "A long fall's landing.", climb: "Climbing a ledge or a ladder's top.", idle: "While it stands.",
                    footstep: "Each step.", land: "A landing." };
const WAV_CHARS = 18;   // a role's files as shown, characters (the whole list in its title)
const TIP = "Sounds: its own or Garret's. Voice: its own or silent. WAVs: a file a take.";
const WAV_TIP = "Copies a PCM WAV (8 to 32 bits, any rate) into its folder.";
const HINT = "Its sounds, voice and WAVs.";
const OPTIONAL = { whoosh: [["takes", 1]] };   // a generator's numbers a recipe may leave out, and their defaults
const BOXES = 8;   // the most number boxes a sound shows (the rest JSON work)
const isObject = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const roleTitle = (role) => ROLE_TITLES[role] ?? role.charAt(0).toUpperCase() + role.slice(1);

// A generator's numbers, as the recipe gives them (its optional ones at their defaults where left out); its lists,
// objects, names and switches are JSON work.
const numbersOf = (params) => [...Object.entries(params).filter(([, x]) => typeof x === "number"),
                               ...(OPTIONAL[params.generator] ?? []).filter(([k]) => !(k in params))];
export const parentOf = (recipe) => typeof recipe.from === "string" ? recipe.from
  : Array.isArray(recipe.from) ? recipe.from.map(String).join(", ") : "";

// soundsTab(ctx, pick): ctx the view's (recipe, read, lists, folder, base, image, edited, app, call, dialog, ask,
// keepFile, choose); pick the page's own parsed <select> of the Sound line (WebKit refuses one made by script).
export function soundsTab(ctx, pick) {
  const radio = (name, value, title) => {
    const input = el("input", { type: "radio", name: `var-${name}`, value, id: `var-${name}-${value}` });
    return [input, el("label", { className: "on" }, input, ` ${title}`)];
  };
  const sounds = Object.entries(SOUND_TITLES).map(([value, title]) => radio("sounds", value, title));
  const voice = Object.entries(VOICE_TITLES).map(([value, title]) => radio("voice", value, title));
  const ui = {
    note: el("p", { id: "var-sounds-note", className: "note", title: TIP }),
    choices: el("p", { className: "rando-row", id: "var-sounds-choices" }, el("span", { className: "field",
      textContent: "Sounds" }), ...sounds.map(([, box]) => box), el("span", { className: "field", textContent: "Voice" }),
      ...voice.map(([, box]) => box)),
    chosen: el("p", { className: "rando-row", id: "var-sounds-chosen", hidden: true }),
    title: el("p", { className: "note", id: "var-wavs-title" }),
    grid: el("div", { className: "var-wavs", id: "var-wavs" }),
    others: el("p", { className: "note", id: "var-sfx-note" }),
    made: el("p", { className: "rando-row", id: "var-sfx-line", hidden: true }),
    warn: el("p", { className: "note warn", id: "var-sounds-warn" }),
    rows: new Map(),
    boxes: [],
  };
  pick.title = "";
  ui.made.append(el("span", { className: "field", textContent: "Sound" }), pick);
  for (let i = 0; i < BOXES; i++) {
    const label = el("span"), input = el("input", { type: "text", size: 5, inputMode: "decimal", spellcheck: false,
                                                     autocomplete: "off", id: `var-sfx-${i}` });
    const group = el("label", { className: "field" }, label, " ", input);
    input.addEventListener("change", () => commit(i));
    ui.boxes.push({ group, label, input });
    ui.made.append(group);
  }
  const element = el("div", { id: "var-sounds", hidden: true }, ui.note, ui.choices, ui.chosen, ui.title, ui.grid,
                     ui.others, ui.made, ui.warn);
  const warn = (text) => {
    ui.warn.textContent = text;
  };

  // The roles' rows: its title, its files, Add WAV (the site's a file pick, the app's its dialog or a typed path) and ×.
  const roles = () => ctx.lists()?.roles ?? [];
  const build = () => {
    for (const role of roles()) {
      if (ui.rows.has(role)) continue;
      const files = el("span", { className: "var-wav-files", id: `var-wav-${role}` });
      const clear = el("button", { type: "button", className: "drop", id: `var-wav-${role}-clear`, textContent: "×",
                                   title: "Clear the role's WAVs." });
      let add, pickBox = null;
      if (ctx.app) {
        add = el("button", { type: "button", id: `var-wav-${role}-add`, textContent: "Add WAV…", title: WAV_TIP });
        add.addEventListener("click", () => added(role, null));
      } else {
        pickBox = el("input", { type: "file", id: `var-wav-${role}-add`, accept: ".wav,audio/wav,audio/x-wav" });
        add = el("label", { className: "file", title: WAV_TIP }, "Add WAV… ", pickBox);
        pickBox.addEventListener("change", () => {
          const picked = pickBox.files[0];
          pickBox.value = "";
          if (picked) added(role, picked);
        });
      }
      clear.addEventListener("click", () => cleared(role));
      const element = el("div", { className: "var-wav" }, el("span", { className: "var-wav-role",
        textContent: `${roleTitle(role)}:`, title: ROLE_TIPS[role] ?? "" }), files, add, clear);
      ui.rows.set(role, { element, files, add, input: pickBox ?? add, clear });
      ui.grid.append(element);
    }
  };

  // Its sounds, voice, wavs, sfx and shouts' files: a recipe from another's as the loader lays them (its last read
  // while an edit's is out), else as written.
  let laid = null;
  const given = () => {
    const recipe = ctx.recipe(), r = ctx.read() ?? laid;
    laid = r;
    if ("from" in recipe && r) {
      return [r.sounds, r.voice, { ...r.wavs }, { ...r.sfx }, r.shouts.length ? r.shouts : null];
    }
    const { wavs, sfx, shouts } = recipe;
    return [recipe.sounds ?? "own", recipe.voice ?? "own", isObject(wavs) ? wavs : {}, isObject(sfx) ? sfx : {},
            isObject(shouts) && Array.isArray(shouts.files) ? shouts.files : null];
  };
  // The roles its base's own sounds take (read from the image once a base), or null and why not (yet).
  const baseSounds = (base) => {
    if (typeof base !== "string") return [null, ""];
    if (!ctx.image()) return [null, `${ctx.choose} to read its base's sounds.`];
    const got = ctx.base("own_sounds", base);
    return got.why ? [null, `Its base's sounds couldn't be read: ${got.why}`]
      : got.value ? [got.value.roles, ""] : [null, "Reading its base's sounds…"];
  };

  // The controls from the recipe, greyed where its build would refuse them (the note says why).
  const load = () => {
    const lists = ctx.lists();
    if (!lists) return;
    build();
    const recipe = ctx.recipe(), r = ctx.read(), base = r?.base ?? recipe.base, parent = parentOf(recipe);
    const [sound, spoken, wavs, sfx, shouts] = given();
    const [own, unknown] = base === PLAYER || parent ? [null, ""] : baseSounds(base);
    const fixed = parent ? `${parent}'s sounds (read-only): New from this… makes one to edit.` : "";
    const why = fixed || (sound === "garret4" ? "Garret's sounds play: Sounds its own plays its voice and WAVs."
      : own?.length ? `${base} has sounds of its own: its voice and WAVs stay ${base}'s.` : "");
    const mine = spoken !== "own" || Object.keys(wavs).length > 0 || Object.keys(sfx).length > 0 || Boolean(shouts?.length);
    for (const [input] of sounds) {
      input.checked = input.value === (sound in SOUND_TITLES ? sound : "own");
      input.disabled = Boolean(fixed) || mine && input.value === "garret4" && sound !== "garret4"
        || base === PLAYER && input.value === "garret4";   // his own sounds are Garret's
    }
    sounds[1][1].title = mine && sound !== "garret4" ? "Its voice, WAVs, sfx and shouts need its own sounds: clear them "
      + "first." : "Garret's every sound, his voice too.";
    for (const [input] of voice) {   // greyed, but a value it can't take may go back to the default
      input.checked = input.value === (spoken in VOICE_TITLES ? spoken : "own");
      input.disabled = Boolean(fixed) || !(!why || input.value === "own" && spoken !== "own");
    }
    voice[1][1].title = why || "silent: no hurt, death, idle or taunt voice (its WAVs still play).";
    ui.choices.hidden = Boolean(fixed);
    ui.chosen.hidden = !fixed;
    ui.chosen.textContent = fixed && base !== PLAYER ? `Sounds: ${SOUND_TITLES[sound] ?? sound} · Voice: `
      + `${VOICE_TITLES[spoken] ?? spoken}` : "";
    const folder = ctx.folder(), shownRoles = [];
    for (const role of lists.roles) {
      const row = ui.rows.get(role), files = Array.isArray(wavs[role]) ? wavs[role].map(String) : [];
      const text = files.join(", ") || "none";
      row.files.textContent = cut(text, WAV_CHARS);
      row.files.title = text.length > WAV_CHARS ? text : "";
      row.files.classList.toggle("none", !files.length);
      row.input.disabled = Boolean(why) || !folder || files.length >= lists.takes;
      row.clear.disabled = Boolean(fixed) || !files.length;
      if (files.length || !why) shownRoles.push(role);
    }
    // greyed or read-only: only the roles with files, and no Add WAV or × (no wall of dead buttons)
    const locked = Boolean(why) && (Boolean(fixed) || !shownRoles.some((role) => wavs[role]?.length));
    for (const role of lists.roles) {
      const row = ui.rows.get(role);
      row.element.hidden = !shownRoles.includes(role);
      row.add.hidden = locked;
      row.clear.hidden = locked;
    }
    ui.grid.hidden = !shownRoles.length;
    ui.title.textContent = shownRoles.length ? "WAVs, a file a take:" : "WAVs: none";
    const garret = mine && sound !== "garret4" && !fixed ? "Garret's sounds: clear its voice, WAVs, sfx and shouts "
      + "first." : "";
    ui.note.textContent = [why || unknown || (folder ? HINT : "Save as first to add WAVs."), garret].filter(Boolean)
      .join(" ");
    const made = Object.entries(sfx).filter(([, p]) => isObject(p) && p.generator !== "wav" && numbersOf(p).length)
      .map(([name, p]) => [name, `${name} (${p.generator})`, numbersOf(p), `on ${(Array.isArray(p.columns) ? p.columns
        : []).filter((c) => typeof c === "string").map(columnTitle).join(", ")}`]);
    const named = new Set(made.map(([name]) => name));
    const whole = Object.entries(sfx).filter(([name, p]) => isObject(p) && !named.has(name))
      .map(([name, p]) => `${name} (${p.generator ?? "none"})`);
    ui.others.textContent = `Its moves' sounds (sfx): ${!Object.keys(sfx).length ? "none (JSON work)"
      : `their columns are JSON work${whole.length ? `, and ${whole.join(", ")} whole` : ""}`}${shouts?.length
      ? `; its shouts under another weapon: ${shouts.length} takes` : ""}.`;
    present(made, !fixed);
  };

  // The Sound line: a sound its generator makes (of those with numbers), a box per number (any finite number, D23;
  // the loader names what it refuses), what plays it in the pick's title; read-only where the recipe is another's.
  let entries = [], editable = false;
  const present = (made, canEdit) => {
    entries = made;
    editable = canEdit;
    ui.made.hidden = !made.length;
    const titles = made.map(([, title]) => title), was = pick.value;
    if ([...pick.options].map((o) => o.value).join("\n") !== titles.join("\n")) {
      pick.replaceChildren(...titles.map((title) => el("option", { value: title, textContent: title })));
    }
    pick.value = titles.includes(was) ? was : titles[0] ?? "";
    fill();
  };
  const chosen = () => entries.find(([, title]) => title === pick.value) ?? null;
  const fill = () => {
    const entry = chosen(), numbers = entry?.[2] ?? [];
    ui.boxes.forEach(({ group, label, input }, i) => {
      group.hidden = i >= numbers.length;
      if (i < numbers.length) {
        label.textContent = numbers[i][0].replace(/_/g, " ");
        if (document.activeElement !== input) input.value = shown(numbers[i][1]);
      }
      input.readOnly = !editable;
    });
    pick.title = entry?.[3] ?? "";
  };
  pick.addEventListener("change", fill);
  const commit = (i) => {
    const entry = chosen(), input = ui.boxes[i].input;
    if (!entry || i >= entry[2].length || !editable) return;
    const [key, old] = entry[2][i], text = input.value.trim(), value = finite(text);
    if (value === null) {
      warn(`${key.replace(/_/g, " ")}: '${text}' is not a number`);
      input.value = shown(old);
      return;
    }
    warn("");
    if (value === old) return;
    entry[2][i] = [key, value];
    const params = ctx.recipe().sfx?.[entry[0]];
    if (!isObject(params)) return;
    if ((OPTIONAL[params.generator] ?? []).some(([k, d]) => k === key && d === value)) delete params[key];
    else params[key] = value;
    ctx.edited();
  };

  // Sounds and Voice: its own, the default, leaves the key out.
  for (const [key, group] of [["sounds", sounds], ["voice", voice]]) {
    for (const [input] of group) {
      input.addEventListener("change", () => {
        if (!input.checked) return;
        warn("");
        const recipe = ctx.recipe();
        if (input.value === "own") delete recipe[key];
        else recipe[key] = input.value;
        ctx.edited();
      });
    }
  }
  // A WAV copied into the variant's folder as a take of role; one the build can't read refused, nothing copied.
  const added = async (role, picked) => {
    const folder = ctx.folder();
    if (!folder) return;
    let reply, data = null;
    if (ctx.app) {
      const file = ctx.dialog ? await ctx.dialog("wav", "") : await ctx.ask(`A WAV for ${roleTitle(role)}: its full path`, "");
      if (!file) return;
      reply = await ctx.call("add_wav", { given: { folder, file } });
    } else {
      data = new Uint8Array(await picked.arrayBuffer());
      reply = await ctx.call("add_wav", { given: { folder, file: picked.name }, data });
    }
    if ("refused" in reply) return warn(`Not added: ${reply.refused}`);
    warn(data ? await ctx.keepFile(reply.name, data) : "");
    const recipe = ctx.recipe(), wavs = isObject(recipe.wavs) ? recipe.wavs : {};
    wavs[role] = [...Array.isArray(wavs[role]) ? wavs[role] : [], reply.name];
    recipe.wavs = wavs;
    ctx.edited();
  };
  // role's WAVs taken out of the recipe (an empty wavs with them; the files stay, but the site keeps a saved recipe's).
  const cleared = (role) => {
    const recipe = ctx.recipe();
    if (!isObject(recipe.wavs) || !(role in recipe.wavs)) return;
    delete recipe.wavs[role];
    if (!Object.keys(recipe.wavs).length) delete recipe.wavs;
    warn("");
    ctx.edited();
  };

  return { element, load };
}
