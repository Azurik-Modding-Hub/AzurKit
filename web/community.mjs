// The Patches tab's community group (Step 4.3k; D988, D997): ready-made setups from Azurik-Custom-Content, listed with
// Install and Update (web/content.mjs, the one path the Characters tab's variants use too). An installed pack ticks like
// a pack: ticked, it ticks the built-in packs it names and sets them to its values, their ticks and sliders locked and
// marked as set by it; unticked, those rows go back to what they were. A second pack that sets a locked row otherwise
// can't be ticked: the status line names both. Its game-data edits are its own layer of the build (the engine's:
// sdk._plan), so this page holds only pins: a build, a link and a mods file carry each by id and its pack.json's sha12,
// and the remembered setup by id alone, with the rows as they were before it. The group reads the content source when
// it is first opened, or when a link or the remembered setup ticks a pack; nothing else here touches the network.
// The engine decides what a pack may hold and what it means (sdk.community, content_check, content_install): text only
// (textContent), no eval.
const LINE = "ready-made setups from Azurik-Custom-Content";
const NONE = "No community packs are published yet.";
const FIRST = "Install it first";
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// communityGroup({root, call, shared, say, catalog, settled}): root the Patches tab's list (#packs), which the group
// joins last; call the engine's ask; shared the page's content path; say the status line; catalog the engine's (each
// pack's sliders, their defaults); settled() runs after rows are set or locked by a set(), not by a tick (a tick's change
// reaches the list's own listener).
export function communityGroup({ root, call, shared, say, catalog, settled }) {
  const g = { held: new Map(), ticked: new Map(), owned: new Map(), read: false, asking: 0, why: null, locked: false, asked: 0, reading: false };
  const packOf = (name) => catalog.packs.find((pack) => pack.name === name);
  const rowOf = (name) => root.querySelector(`.pack[data-pack="${name}"]`);
  const titleOf = (id) => shared.state.entries.find((e) => e.id === id)?.title ?? id;
  const tally = el("span", { className: "tally" });
  const rows = el("div"), note = el("p", { className: "note community-note", id: "community-note" });
  const source = el("input", { type: "text", id: "community-source", spellcheck: false, autocomplete: "off",
                               value: shared.state.source });
  const resetSource = el("button", { type: "button", id: "community-source-reset", textContent: "Reset" });
  const group = el("details", { className: "group", id: "community-group" },
    el("summary", {}, el("b", { textContent: "Community" }), tally, el("span", { className: "line", textContent: LINE })),
    rows,
    el("p", { className: "rando-row community-from" }, el("label", { className: "field" }, "Content from ", source), " ",
       resetSource),
    note);
  root.append(group);

  // Each entry the source lists or the content folder holds: a manifest entry with its state, or what is held of it.
  const entries = () => {
    const listed = shared.state.entries.filter((e) => e.kind === "pack");
    const known = new Set(listed.map((e) => e.id));
    return [...listed, ...[...g.held.values()].filter((h) => !known.has(h.id)).map((h) => ({
      id: h.id, kind: "pack", title: h.id, version: h.version, installed: h.version, state: "installed", gone: true }))];
  };

  const values = (pack, params) => Object.fromEntries(pack.sliders.map((s) => [s.name, params[s.name] ?? s.default]));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  // The row's tick and settings as they are now, to go back to (each setting whose value isn't its default, as the
  // remembered setup keeps them).
  const taken = (item, pack) => ({
    checked: item.querySelector("input[data-pack]").checked,
    fields: [...item.querySelectorAll("input[data-slider]")].map((field) => [field, field.type === "checkbox"
      ? field.checked : field.value]),
    values: Object.fromEntries(pack.sliders.flatMap((s) => {
      const field = item.querySelector(`input[data-slider="${s.name}"]`);
      const value = !field ? s.default : field.type === "checkbox" ? Number(field.checked) : Number(field.value);
      return Number.isFinite(value) && value !== s.default ? [[s.name, value]] : [];
    })),
  });

  const setRow = (item, params, pack) => {
    item.querySelector("input[data-pack]").checked = true;
    for (const [slider, value] of Object.entries(values(pack, params))) {
      const field = item.querySelector(`input[data-slider="${slider}"]`);
      if (!field) continue;
      if (field.type === "checkbox") field.checked = String(value) === "1";
      else field.value = String(value);
      field.closest(".slider").fit();
    }
  };

  const mark = (item, by) => {
    item.classList.toggle("owned", Boolean(by));
    item.querySelector(".owned-line")?.remove();
    if (by) {
      item.querySelector("label > span:last-child").append(el("span", { className: "owned-line",
        textContent: `Set by ${by} (community): untick it to change these` }));
    }
  };

  // The packs a tick would set otherwise than another ticked pack sets them: the first, named, or null.
  const clash = (pick) => {
    for (const [name, params] of Object.entries(pick.packs)) {
      const held = g.owned.get(name);
      if (held && !same(held.params, params)) return `${titleOf(pick.id)} and ${titleOf(held.by[0])} set ${name} `
        + "differently: untick one";
    }
    return null;
  };

  const tick = (pick) => {
    g.ticked.set(pick.id, pick);
    for (const [name, params] of Object.entries(pick.packs)) {
      const item = rowOf(name), pack = packOf(name);
      if (!item || !pack) continue;
      const held = g.owned.get(name);
      if (held) held.by.push(pick.id);
      else {
        g.owned.set(name, { by: [pick.id], params, was: taken(item, pack) });
        setRow(item, params, pack);
        mark(item, titleOf(pick.id));
      }
    }
  };

  const untick = (id, back = true) => {
    g.ticked.delete(id);
    for (const [name, held] of [...g.owned]) {
      held.by = held.by.filter((by) => by !== id);
      if (held.by.length) {
        mark(rowOf(name), titleOf(held.by[0]));
        continue;
      }
      g.owned.delete(name);
      const item = rowOf(name);
      mark(item, null);
      if (!back) continue;
      item.querySelector("input[data-pack]").checked = held.was.checked;
      for (const [field, value] of held.was.fields) {
        if (field.type === "checkbox") field.checked = value;
        else field.value = value;
        field.closest(".slider").fit();
      }
    }
  };

  const count = () => {
    const on = entries().filter((e) => g.ticked.has(e.id)).length;
    tally.textContent = `${on} of ${entries().length} on`;
  };

  const contents = (pick) => el("ul", { hidden: true },
    ...Object.entries(pick.packs).map(([name, params]) => el("li", { textContent: `${name}: ${
      Object.entries(params).map(([slider, value]) => `${slider} ${value}`).join(", ") || "on"}` })),
    ...pick.ops.map((op) => el("li", { textContent: op })));

  const draw = () => {
    note.textContent = g.why ?? (!entries().length && !g.reading ? NONE : "");
    rows.replaceChildren(...entries().map((e) => {
      const pick = g.held.get(e.id), usable = Boolean(pick && !pick.refused);
      const box = el("input", { type: "checkbox", checked: g.ticked.has(e.id), disabled: !usable || g.locked,
                                title: usable ? "" : pick?.refused ?? FIRST });
      box.dataset.community = e.id;
      box.addEventListener("change", (event) => toggled(event, pick, box));
      const item = el("div", { className: "cpack" }, el("label", {}, box, el("span", { className: "name", textContent:
        e.title }), el("span", { className: "by", textContent: `community · ${[e.author, e.licence, `v${e.version}`]
        .filter(Boolean).join(" · ")}` })));
      item.dataset.community = e.id;
      if (e.state !== "installed" || !usable) {
        const action = el("button", { type: "button", disabled: Boolean(shared.state.installing) || g.locked,
          textContent: e.state === "update" ? `Update to v${e.version}` : "Install" });
        action.addEventListener("click", () => install(e));
        if (!e.gone) item.append(action);
      } else {
        item.append(el("span", { className: "by", textContent: `installed v${e.installed}` }));
      }
      if (usable) {
        const list = contents(pick);
        const n = Object.keys(pick.packs).length + pick.ops.length;
        const opener = el("button", { type: "button", className: "toggle", textContent: `Contents · ${n}` });
        opener.setAttribute("aria-expanded", "false");
        opener.addEventListener("click", () => {
          list.hidden = !list.hidden;
          opener.setAttribute("aria-expanded", String(!list.hidden));
        });
        item.append(opener);
        if (e.description) item.append(el("p", { className: "what", textContent: e.description }));
        item.append(list);
      } else {
        const why = pick?.refused ?? (e.description ? `${e.description} ${FIRST}.` : `${FIRST}.`);
        item.append(el("p", { className: "what", textContent: why }));
      }
      return item;
    }));
    count();
  };

  const toggled = (event, pick, box) => {
    if (!box.checked) {
      untick(pick.id);
      draw();
      return;
    }
    const why = clash(pick);
    if (why) {
      box.checked = false;
      event.stopPropagation();   // nothing changed
      return say(why, true);
    }
    tick(pick);
    draw();
  };

  // What the content folder holds, as the engine reads it (a local read: no network).
  const held = async () => {
    const mine = ++g.asked;
    const reply = await call("community", {});
    if (mine !== g.asked) return;   // a later ask answers for now
    if ("refused" in reply) {
      g.why = reply.refused;
      return;
    }
    g.held = new Map(reply.packs.map((pick) => [pick.id, pick]));
    for (const [id, pick] of [...g.ticked]) {   // an Update under a tick: a pack set anew
      const now = g.held.get(id);
      if (!same(now, pick)) {
        untick(id);
        if (now && !now.refused) tick(now);
      }
    }
  };

  const reading = async (asked = shared.read) => {
    g.reading = true;
    g.why = null;
    draw();
    await asked();
    await held();
    g.reading = false;
    g.why ??= shared.state.why;
    draw();
  };

  const install = async (entry) => {
    g.why = null;
    try {
      await shared.install(entry, (done, total) => {
        note.textContent = `Installing ${entry.title}: ${done} of ${total} files…`;
      });
      await held();
      say(`Installed ${entry.title} v${entry.version}: tick it to use it`);
    } catch (error) {
      say(`${entry.title}: nothing was installed: ${error.message}`, true);
    }
    draw();
    settled();
  };

  group.addEventListener("toggle", () => {
    if (group.open && !g.read) {
      g.read = true;
      reading();
    }
  });
  const from = (url) => {
    g.read = true;
    reading(() => shared.source(url));
  };
  source.addEventListener("change", () => from(source.value.trim() || shared.fallback));
  resetSource.addEventListener("click", () => from(shared.fallback));
  shared.on(() => {   // Content from is one setting, shown in both tabs
    source.value = shared.state.source;
    if (!g.reading) draw();
  });
  draw();

  return {
    // The pins a build's recipe and a link carry.
    pins: () => [...g.ticked.values()].map(({ id, sha }) => ({ id, sha })),
    // The page's remembered setup with the rows a ticked pack holds as they were before it, and the packs by id alone.
    kept: (setup) => {
      if (!g.ticked.size) return setup;
      const on = new Set(setup.ticked), values = { ...setup.values };
      for (const [name, { was }] of g.owned) {
        if (was.checked) on.add(name);
        else on.delete(name);
        delete values[name];
        if (Object.keys(was.values).length) values[name] = was.values;
      }
      return { ...setup, ticked: catalog.packs.map((pack) => pack.name).filter((name) => on.has(name)), values,
               community: [...g.ticked.keys()].map((id) => ({ id })) };
    },
    // Whether a built-in pack's row is held by a ticked pack.
    owns: (name) => g.owned.has(name),
    lock: (building) => {
      if (g.locked === building) return;
      g.locked = building;
      draw();
    },
    waiting: () => g.asking > 0,
    // Every tick dropped, the rows left as they are: the page sets them next (a link, the remembered setup, Reset).
    clear: () => {
      for (const id of [...g.ticked.keys()]) untick(id, false);
      draw();
    },
    // Tick the packs a link, a recipe or the remembered setup names, read from the content folder (the engine checked
    // each is installed at its pin); one it can't tick is said by name.
    set: async (pins) => {
      if (!pins?.length) return;
      g.asking += 1;
      try {
        await held();
        if (!g.read) {
          g.read = true;
          group.open = true;   // its toggle reads the source once; it would see g.read, so read here
          reading();
        }
        for (const { id } of pins) {
          const pick = g.held.get(id);
          const why = !pick || pick.refused ? pick?.refused ?? `${id}: not installed` : clash(pick);
          if (why) say(why, true);
          else tick(pick);
        }
        draw();
        settled();
      } finally {
        g.asking -= 1;
      }
    },
    ready: shared.ready,
    state: g,
  };
}
