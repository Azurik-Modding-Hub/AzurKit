// The Characters tab (Step 4.3d; Modkit's Player page): the models' list, the community group first (D913: our variants
// from Azurik-Custom-Content beside the built-ins, each marked community, with Install and Update) then every species
// the player can wear, in its grade's colour and mark (green fully playable, yellow rough edges, red not playable, grey
// not yet tested: the untested greyed and marked, D877); the chosen model's pictures from the front and from behind (D772,
// D919: the engine's draw.py, on both hosts), its info and its options, each number with a G4 button that sets it to
// match garret4 (P52). The engine decides everything shown (sdk.pickers, sdk.preview, sdk.match): this page sends the
// tab's choices and draws what comes back. Its answer with no image and each species' and built-in variant's two
// pictures ship with the page (Step 4.3f, D961: characters/, scripts/record_goldens.py's characters family), so the
// list and Garret show at the tab's first click and a model's pictures at its click, before an image and with no
// engine call; G4 and the Weapon box wait for the image's answer, saying so (D979). Content from (the source Azurik-Custom-Content is read from) is remembered:
// by the site in this browser's storage, by the app in its config; an Install checks every file's sha256 before
// anything is kept (the site's worker, sdk.content_check; the app's engine, sdk.content_install), and an installed
// entry stays at its version until its Update. The site keeps what it installed in this browser's storage (IndexedDB)
// and hands it to its engine as the page starts (a build from any tab, a link's or the remembered setup's, reads it);
// the app writes it into its content folder.
const $ = (id) => document.getElementById(id);
const SOURCE = "azurkit.content_source";
const NUMBERS = ["scale", "attack_reach", "attack_damage", "attack_speed"];
const JIGGLE = ["jiggle_strength", "jiggle_stiffness"];
const CHOOSE_WEAPONS = "Choose your image to see its weapons";   // the Weapon box with no image read
const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i;
const typed = (text) => NUMBER.test(text.trim()) && Number.isFinite(Number(text)) ? Number(text) : text;
const box = (v) => typeof v === "number" ? String(v) : v ?? "1";
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// This browser's keeping of what the site installed: the last manifest read, installed.json's record and the files.
const idb = (() => {
  let opened = null;
  const open = () => opened ??= new Promise((done, fail) => {
    const request = indexedDB.open("azurkit-content", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("kept");
    request.onsuccess = () => done(request.result);
    request.onerror = () => fail(request.error);
  });
  const run = async (mode, act) => {
    const db = await open();
    return new Promise((done, fail) => {
      const tx = db.transaction("kept", mode), request = act(tx.objectStore("kept"));
      tx.oncomplete = () => done(request?.result);
      tx.onerror = tx.onabort = () => fail(tx.error);
    });
  };
  return { get: (key) => run("readonly", (s) => s.get(key)).catch(() => undefined),
           put: (entries) => run("readwrite", (s) => { for (const [k, v] of entries) s.put(v, k); }) };
})();

const bytesOf = (data) => typeof data === "string" ? Uint8Array.from(atob(data), (ch) => ch.charCodeAt(0)) : data;

// characters({call, app, host, say, image, packs, changed, content}): call is the engine's (the site's worker, the
// app's api), image() the picked image (the site's File, the app's path), packs() the Patches tab's ticks (a dress
// stands on them), changed() runs when the tab's choice changes (the page remembers it) and content(files,
// installed) hands the site's engine what this browser keeps installed.
export function characters({ call, app, host, say, image, packs, changed, content }) {
  const c = { character: { species: "garret4" }, view: null, manifest: null, why: null, ticket: 0, source: null,
              matching: false, drawn: null, opened: false, installing: null, filter: "", read: null };
  const fallback = () => host.catalog?.characters?.source ?? "";
  c.source = app ? host.content_source || fallback() : (() => {
    try {
      return localStorage.getItem(SOURCE) || fallback();
    } catch {
      return fallback();
    }
  })();

  // What this browser keeps installed, handed to the site's engine now, not on the tab's first open.
  const kept = app ? Promise.resolve() : Promise.all([idb.get("files"), idb.get("installed")])
    .then(([files, installed]) => {
      if (files && installed) content(files, installed);
    });

  // The shipped answer and pictures (the file name of each species' and variant's), read at the tab's first open.
  let ships = null, shipping = null;
  const shipped = () => shipping ??= fetch("characters/index.json").then((reply) => reply.ok ? reply.json() : null)
    .catch(() => null).then((found) => ships = found);
  // The engine's answer read the image picked now (D979: G4 and the weapons need it).
  const imaged = () => Boolean(c.view?.from) && c.view.from === image();

  const given = (extra) => app ? { given: { iso: image() || null, ...extra } } : { file: image(), given: { iso: null,
                                                                                                           ...extra } };
  const recipe = (character) => ({ iso: app ? image() || null : null, packs: packs(), character });

  // Ask the engine what the tab shows for its choices; an answer to an older ask is dropped.
  const ask = async () => {
    const mine = ++c.ticket, asked = JSON.stringify(c.character), from = image() || null;
    const reply = await call("pickers", given({ character: c.character, content: { manifest: c.manifest } }));
    if (mine !== c.ticket) return;
    if (!("refused" in reply)) Object.assign(reply, { asked, from });
    if ("refused" in reply) {
      $("char-refused").hidden = false;
      $("char-refused").textContent = reply.refused;
      // a field refused with the image read keeps G4 and the weapons (D979), on every refusal: c.read outlives the view
      const read = Boolean(c.read) && c.read === image();
      c.view = null;
      if (!read) {   // no answer read the image: G4 and the weapons ask for one again, not "Reading"
        $("char-weapon").replaceChildren(el("option", { value: "", textContent: CHOOSE_WEAPONS }));
        $("char-weapon").disabled = true;
        g4();
      }
      return;
    }
    c.view = reply;
    c.read = from;   // the image the last answer read
    render();
    draw();
  };

  // The source's manifest: the app's engine reads it (a URL or a folder), the site fetches it (an http(s) or relative
  // URL, never a folder) and its worker checks it; the last one read is kept, listed while the source can't be read.
  const read = async () => {
    $("char-content-note").textContent = "Reading the community content…";
    if (app) {
      const reply = await call("content", { source: c.source });
      if ("refused" in reply) c.why = reply.refused;
      else ({ manifest: c.manifest, why: c.why } = reply);
    } else {
      c.why = null;
      try {
        if (/^(\/|~|[A-Za-z]:\\)/.test(c.source)) {
          throw Object.assign(new Error("The site reads a URL, not a folder: the desktop app reads a folder of your "
                                        + "own. Every built-in model below works."), { plain: true });
        }
        if (new URL(c.source, location.href).origin !== location.origin) {   // the page's CSP: connect-src 'self'
          throw Object.assign(new Error("Community models come to this site with AzurKit 4.4; the desktop app lists "
                                        + "them now. Every built-in model below works."), { plain: true });
        }
        const reply = await fetch(new URL("manifest.json", new URL(c.source, location.href)), { cache: "no-store" })
          .catch(() => { throw new Error("no answer"); });
        if (!reply.ok) throw new Error(`HTTP ${reply.status}`);
        const text = await reply.text();
        const checked = await call("content_check", { manifest: text });
        if ("refused" in checked) throw new Error(checked.refused);
        c.manifest = checked.manifest;
        await idb.put([["manifest", text]]).catch(() => {});
      } catch (error) {
        c.why = error.plain ? error.message : `Couldn't reach the community list at ${c.source} (${error.message}). `
          + "Every built-in model below works.";
        const kept = await idb.get("manifest");
        if (kept) c.manifest = JSON.parse(kept);
      }
    }
    $("char-content-note").textContent = c.why ? `${c.why}${c.manifest ? " (the last list read is shown)" : ""}` : "";
    await ask();
  };

  // Install or Update an entry: every file's size and sha256 checked before anything is kept (D35).
  const install = async (entry) => {
    if (c.installing) return;
    c.installing = entry.id;
    render();
    say(`Installing ${entry.title}…`);
    try {
      if (app) {
        const reply = await call("install", { id: entry.id, source: c.source });
        if ("refused" in reply) throw new Error(reply.refused);
        ({ manifest: c.manifest, why: c.why } = reply);
      } else {
        const ids = new Map(c.manifest.entries.map((e) => [e.id, e]));
        const need = [], visit = (id) => {
          for (const r of ids.get(id).requires) visit(r);
          if (!need.includes(id)) need.push(id);
        };
        visit(entry.id);
        const kept = (await idb.get("files")) ?? {}, record = (await idb.get("installed")) ?? {};
        const files = {};
        for (const id of need) {
          for (const f of ids.get(id).files) {
            const reply = await fetch(new URL(f.path, new URL(c.source, location.href)), { cache: "no-store" });
            if (!reply.ok) throw new Error(`${f.path}: HTTP ${reply.status}`);
            files[f.path] = new Uint8Array(await reply.arrayBuffer());
          }
        }
        const checked = await call("content_check", { manifest: JSON.stringify(c.manifest), id: entry.id, files });
        if ("refused" in checked) throw new Error(checked.refused);
        for (const id of checked.install) {
          for (const path of Object.keys(record[id]?.files ?? {})) delete kept[path];
          record[id] = { version: ids.get(id).version, source: c.source,
                         files: Object.fromEntries(ids.get(id).files.map((f) => [f.path, f.sha256])) };
          for (const f of ids.get(id).files) kept[f.path] = files[f.path];
        }
        await idb.put([["files", kept], ["installed", record]]);
        content(kept, record);
      }
      say(`Installed ${entry.title} v${entry.version}: its variants are in the list`);
    } catch (error) {
      say(`${entry.title}: nothing was installed: ${error.message}`, true);
    }
    c.installing = null;
    render();
    await ask();
  };

  // The models' list: the community entries (each marked, its state and its variants once installed), then the
  // species, each in its grade's colour, filtered by the search box.
  const pick = (name) => {
    if (name === c.character.species) return;
    const keep = Object.fromEntries(Object.entries(c.character).filter(([k]) => ["size", "scale", ...NUMBERS].includes(k)));
    c.character = { ...keep, species: name };
    changed();
    if (ships?.species[name] || ships?.variants[name]) draw({ name, variant: !ships.species[name] });   // at once
    ask();
  };
  // A grade's name from the engine's colour, and its colour as drawn: through its theme's --grade-* (app.css), so a
  // theme toggle repaints it.
  const gradeOf = (colour) => colour && Object.keys(c.view?.colours ?? {}).find((name) => c.view.colours[name] === colour);
  const paint = (colour) => {
    const grade = gradeOf(colour);
    return grade ? `var(--grade-${grade}, ${colour})` : colour ?? "";
  };
  // A model's row, its grade read without colour too: its mark (app.css's data-grade ::after) and the grade's words as
  // its title.
  const row = (name, label, colour, untested = false) => {
    const grade = gradeOf(colour);
    const button = el("button", { type: "button", className: `model${untested ? " untested" : ""}`, textContent: label,
                                  title: untested ? "Not yet tested: no sitting has graded it"
                                    : c.view.grade_words[grade] ?? name });
    button.dataset.model = name;
    if (grade) button.dataset.grade = grade;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(name === c.character.species));
    button.style.color = paint(colour);
    button.addEventListener("click", () => pick(name));
    return button;
  };
  const render = () => {
    if (!c.view) return;
    const view = c.view, chosen = view.chosen, filter = c.filter.toLowerCase();
    const species = view.species.filter((s) => !filter || s.label.toLowerCase().includes(filter));
    $("char-species").replaceChildren(...species.map((s) => row(s.name, s.label, s.colour, s.untested)));
    $("char-count").textContent = `${view.species.length} species, ${view.species.filter((s) => s.untested).length} `
      + "not yet tested" + (view.why ? ` · ${view.why}` : "");
    const groups = view.community.map((e) => {
      const state = e.state === "install" ? "Install" : e.state === "update" ? `Update to v${e.version}` : null;
      const action = state && el("button", { type: "button", textContent: state, disabled: !!c.installing });
      action?.addEventListener("click", () => install(e));
      const item = el("div", { className: "entry" },
                      el("span", {}, el("span", { className: "community", textContent: "community " }), e.title),
                      action ?? el("span", { className: "note",
                                             textContent: c.installing === e.id ? "installing…" : `installed v${e.installed}` }),
                      el("span", { className: "what", textContent: `${e.author} · ${e.licence} · v${e.version}` }),
                      ...e.variants.filter((v) => !filter || v.name.includes(filter))
                        .map((v) => row(v.name, `${v.name}  (variant of ${v.base})`, v.colour)));
      item.dataset.entry = e.id;
      return item;
    });
    $("char-community").replaceChildren(...groups.length ? groups
      : [el("p", { className: "note", textContent: c.why ? "None read yet." : "None listed." })]);
    $("char-name").textContent = chosen.name + (chosen.community ? "  · community" : "");
    $("char-info").replaceChildren(...chosen.info.map(([label, text, colour]) => {
      const value = el("td", { textContent: text });
      if (colour) value.style.color = paint(colour);
      return el("tr", {}, el("th", { textContent: label }), value);
    }));
    const locked = chosen.locked, live = chosen.live, defaults = chosen.defaults, ch = c.character;
    $("char-mode").replaceChildren(...view.modes.map((m) => el("option", { value: m.id, textContent: m.title })));
    $("char-mode").value = locked.mode ?? ch.mode ?? defaults.mode;
    $("char-mode").disabled = "mode" in locked;
    const weapons = imaged() ? chosen.weapons   // D979: none until the image is read
      : [{ name: null, label: image() ? "Reading your image…" : CHOOSE_WEAPONS }];
    $("char-weapon").replaceChildren(...weapons.map((w) => {
      const option = el("option", { value: w.name ?? "", textContent: w.label, title: w.tip ?? "" });
      if (w.colour) option.style.color = paint(w.colour);
      return option;
    }));
    $("char-weapon").value = imaged() ? chosen.weapon ?? "" : "";
    $("char-weapon").disabled = weapons.length < 2;
    const picked = weapons.find((w) => w.name === (chosen.weapon ?? null));
    $("char-weapon").style.color = paint(picked?.colour);
    $("char-clips").checked = (ch.anims ?? defaults.anims) === "own";
    $("char-clips").disabled = !live.anims;
    $("char-sounds").checked = (locked.sounds ?? ch.sounds ?? "own") === "own";
    $("char-sounds").disabled = "sounds" in locked;
    $("char-height").checked = (locked.size ?? ch.size ?? "own") === "garret4";
    $("char-height").disabled = "size" in locked;
    for (const [id, key] of [["char-balance", "attack_balance"], ["char-ground", "attack_ground"]]) {
      $(id).checked = locked[key] ?? ch[key] ?? (live[key] ? defaults[key] : false);
      $(id).disabled = !live[key];
    }
    const names = [...NUMBERS, ...(chosen.springs ? JIGGLE : [])];
    $("char-numbers").replaceChildren(...names.map((name) => number(name, view.titles[name], view.tracks[name],
                                                                    ch[name], NUMBERS.includes(name))),
                                      ...chosen.shapes.map((s) => number(`shape:${s.name}`, s.title, view.tracks.shape,
                                                                         ch.shapes?.[s.name], false)));
    $("char-refused").hidden = !chosen.refused;
    $("char-refused").textContent = chosen.refused ?? "";
    g4();
  };

  // One number: its title, a track (a hint that widens to hold the value: nothing clamps, D23), its box (any value;
  // the engine refuses what isn't a finite number, by name), and its G4 button for the four that match garret4.
  const number = (name, title, [lo, hi, step], value, matched) => {
    const text = box(value);
    const track = el("input", { type: "range", step, ariaLabel: `${title} (track)` });
    const field = el("input", { type: "text", id: `char-${name}`, value: text, inputMode: "decimal", spellcheck: false,
                                autocomplete: "off" });
    const fit = () => {
      const v = typed(field.value);
      const held = [lo, hi, 1, v].filter((x) => typeof x === "number");
      track.min = String(Math.min(...held));
      track.max = String(Math.max(...held));
      if (typeof v === "number") track.value = String(v);
      field.classList.toggle("changed", v !== 1);
    };
    const set = () => {
      const v = typed(field.value);
      if (name.startsWith("shape:")) {
        const shapes = { ...(c.character.shapes ?? {}) };
        if (v === 1) delete shapes[name.slice(6)];
        else shapes[name.slice(6)] = v;
        c.character = { ...c.character, shapes };
        if (!Object.keys(shapes).length) delete c.character.shapes;
      } else if (v === 1) {
        const { [name]: _, ...rest } = c.character;
        c.character = rest;
      } else {
        c.character = { ...c.character, [name]: v };
      }
      fit();
      changed();
      ask();
    };
    track.addEventListener("input", () => {
      field.value = track.value;
      set();
    });
    field.addEventListener("change", set);
    fit();
    const row = el("div", { className: "number" }, el("label", { htmlFor: field.id, textContent: title }), track, field,
                   el("span", { className: "unit", textContent: "x" }));
    if (matched) {
      const button = el("button", { type: "button", className: "g4", id: `char-g4-${name}`, textContent: "G4",
                                    title: c.view.match_tips[name] });
      button.addEventListener("click", () => match(name));
      row.append(button);
    }
    return row;
  };

  // The G4 buttons: live once the engine has read the image to measure in (D979: greyed, saying so, until then), greyed
  // while one dress measures (seconds; a detailed variant minutes, and on the site it may run out of memory: the app
  // then); the value its box takes, 4 figures rounded up.
  const g4 = () => {
    for (const name of NUMBERS) {
      const button = $(`char-g4-${name}`);
      if (button) button.disabled = c.matching || !imaged();
    }
    $("char-g4-note").textContent = c.matching ? "Measuring the body against garret4…"
      : imaged() ? "G4 sets a number so the body matches garret4." : image() && c.view ? "Reading your image…"
      : "Choose your image to match garret4 (G4).";
  };
  const match = async (name) => {
    if (c.matching || !c.view) return;
    c.matching = true;
    g4();
    const reply = await call("match", { ...(app ? {} : { file: image() }), recipe: recipe(c.view.character) },
                             { once: true });
    c.matching = false;
    g4();
    if ("refused" in reply) return say(`G4: ${reply.refused}`, true);
    if (reply.values[name] == null) return say(`G4: none for ${c.view.titles[name]}: ${reply.why[name]}`, true);
    $(`char-${name}`).value = reply.text[name];
    $(`char-${name}`).dispatchEvent(new Event("change"));
  };

  // The chosen model's two pictures: the page's own where it ships them (no image needed), else a species' drawn at once
  // from its body in the image, a variant's from a dress of it ("Drawing…" until it is, never its base's picture).
  const draw = async (chosen = c.view.chosen) => {
    const file = chosen.variant ? ships?.variants[chosen.name] : ships?.species[chosen.name];
    let key = file ? `shipped|${file}` : `${image()?.name ?? image()}|${chosen.name}`;
    if (c.drawn === key) return;
    c.drawn = key;
    if (file) {
      try {
        const views = await Promise.all(["front", "back"].map(async (view) => {
          const reply = await fetch(`characters/${file}.${view}.png`);
          if (!reply.ok) throw new Error(`HTTP ${reply.status}`);
          return createImageBitmap(await reply.blob());
        }));
        if (c.drawn !== key) return;
        for (const [i, id] of ["char-front", "char-back"].entries()) {
          $(id).getContext("2d").clearRect(0, 0, 160, 160);
          $(id).getContext("2d").drawImage(views[i], 0, 0);
        }
        return void ($("char-preview-note").textContent = "From the front and from behind.");
      } catch {
        if (c.drawn !== key) return;
        c.drawn = key = `${image()?.name ?? image()}|${chosen.name}`;   // drawn from the image instead
      }
    }
    for (const id of ["char-front", "char-back"]) $(id).getContext("2d").clearRect(0, 0, 160, 160);
    if (!image()) return void ($("char-preview-note").textContent = "Pick your image to see the model.");
    $("char-preview-note").textContent = chosen.variant ? "Drawing… (a variant is dressed first: seconds, a detailed "
      + "one minutes)" : "Drawing…";
    const reply = await call("preview", { ...(app ? {} : { file: image() }),
                                          recipe: recipe({ species: chosen.name }) }, { once: true });
    if (c.drawn !== key) return;
    if ("refused" in reply) return void ($("char-preview-note").textContent = reply.refused);
    for (const [view, id] of [["front", "char-front"], ["back", "char-back"]]) {
      const bitmap = await createImageBitmap(new Blob([bytesOf(reply[view])], { type: "image/png" }));
      $(id).getContext("2d").drawImage(bitmap, 0, 0);
    }
    $("char-preview-note").textContent = "From the front and from behind.";
  };

  const defaults = () => c.view?.chosen.defaults ?? { mode: "own", anims: "garret4", attack_balance: true,
                                                     attack_ground: true };
  const option = (key, value, dflt) => {
    const { [key]: _, ...rest } = c.character;
    c.character = value === dflt ? rest : { ...rest, [key]: value };
    changed();
    ask();
  };
  $("char-filter").addEventListener("input", () => {
    c.filter = $("char-filter").value.trim();
    if (c.view) render();
  });
  $("char-mode").addEventListener("change", () => option("mode", $("char-mode").value, defaults().mode));
  $("char-weapon").addEventListener("change", () => option("weapon", $("char-weapon").value || null, null));
  $("char-clips").addEventListener("change", () => option("anims", $("char-clips").checked ? "own" : "garret4",
                                                          defaults().anims));
  $("char-sounds").addEventListener("change", () => option("sounds", $("char-sounds").checked ? "own" : "garret4", "own"));
  $("char-height").addEventListener("change", () => option("size", $("char-height").checked ? "garret4" : "own", "own"));
  $("char-balance").addEventListener("change", () => option("attack_balance", $("char-balance").checked,
                                                            defaults().attack_balance));
  $("char-ground").addEventListener("change", () => option("attack_ground", $("char-ground").checked,
                                                           defaults().attack_ground));
  $("char-reset").addEventListener("click", () => set(null));
  $("char-source").value = c.source;
  $("char-source").addEventListener("change", () => source($("char-source").value.trim() || fallback()));
  $("char-source-reset").addEventListener("click", () => source(fallback()));
  const source = (url) => {
    c.source = url;
    $("char-source").value = url;
    if (app) call("content_source", { source: url === fallback() ? null : url });
    else {
      try {
        if (url === fallback()) localStorage.removeItem(SOURCE);
        else localStorage.setItem(SOURCE, url);
      } catch {}
    }
    read();
  };

  // The tab's choice set from a link, a build's recipe or the remembered setup (null: garret4, every default).
  const set = (character) => {
    c.character = character ? { ...character } : { species: "garret4" };
    delete c.character.variant;
    changed();
    if (c.opened) ask();
  };

  // What a build, a link and the remembered setup take: the engine's recipe of the tab's choice (its answer to this
  // choice; until it comes, the choice), none for garret4 at every default.
  const character = () => {
    const made = c.view?.asked === JSON.stringify(c.character) ? c.view.character : c.character;
    return Object.keys(made).length === 1 && made.species === "garret4" ? null : made;
  };

  return {
    // The tab shown: read the community content once (after what this browser keeps reached the engine), then ask
    // what it shows.
    open: () => {
      if (!c.opened) {
        c.opened = true;
        shipped().then(() => {   // the shipped answer for garret4 at every default, until the engine's comes
          if (!ships || c.view || JSON.stringify(c.character) !== '{"species":"garret4"}') return;
          c.view = { ...ships.view, asked: JSON.stringify(c.character), from: null };
          render();
          draw();
        });
        kept.then(read);
      } else ask();
    },
    imaged: () => {
      c.drawn = null;
      if (c.view) render();   // its weapons and G4 wait for the image's answer
      if (c.opened) ask();
    },
    set,
    character,
    setup: character,
    refused: () => c.view?.asked === JSON.stringify(c.character) ? c.view.chosen.refused : null,
    state: c,
  };
}
