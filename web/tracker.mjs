// The item tracker (Step 4.2c2, D189, D249): the Randomizer tab's Tracker view, on the site and in the app. It opens on
// a plan (a randomized build's, the tab's seed planned by Track this seed, or a plan file) and shows what the player
// marked collected and what the solver says is reachable now: the world map (each level with its spots reachable now,
// amber where only a skip reaches them, R1.41), a level's spots (a click marks one collected, or no longer), and the
// Table (each kind's and level's collected, reachable now, left and total). Spoiler shows the item at each spot; off,
// nothing names an item not yet collected. The maps (Step 4.2c3) are drawn from the player's own image the first time
// the tracker opens with one (web/art.mjs: kept for the next visit) and shown by web/mapview.mjs, Modkit's map view;
// until a map is drawn, the world map is a grid of the levels and a level's spots are chips. Gems (R1.43, D928, off
// by default and remembered) draws each gem spot as a tiny dot on its level's map, gone once Live sees it taken. The engine (sdk.tracker, Modkit's tracker) decides every verdict: this page
// sends the plan, the marks, a click, and draws what comes back. The marks are kept per plan, the last KEEP plans
// (the site in this browser's storage, the app in its config), with the plan last tracked; the tracker's Reset clears
// a plan's marks. Live (the app's alone, D882) marks what a running xemu shows taken and follows the player.
import { artStore } from "./art.mjs";
import { MapView } from "./mapview.mjs";

const $ = (id) => document.getElementById(id);
const KEEP = 20;
const STORE = "azurkit.tracker";
const CLASSES = [["major", "Item spots"], ["obsidian", "Obsidian spots"], ["consumable", "Fuel or health spots"]];
const SPOT = { major: "Item spot", obsidian: "Obsidian spot", consumable: "Fuel or health spot" };
const STATES = { got: "collected", live: "collected (live)", near: "reachable now", skip: "reachable now with a skip",
                 far: "not reachable yet" };
const COLUMNS = { got: "Got", now: "Now", left: "Left", total: "Total", game: "In game", where: "Where" };
// Live's status (the app's): its dot, and what the levels row says while xemu runs another seed or build (R1.41)
const DOTS = { connecting: "○", waiting: "○", live: "●", warn: "▲", lost: "▲", other: "■", stopped: "" };
const POLL_MS = 700;

const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

export function tracker({ call, app, say, kept, keep, image = () => null }) {
  const t = { plan: null, marks: {}, view: null, level: null, mode: "map", spoiler: false, gems: false, queue: [],
              running: null,
              kept: kept ?? { plan: null, marks: {} }, live: null };

  // The engine's asks, one at a time and in order (each click is one, sent with the marks the last answer gave;
  // one made after a call waits for it); a plan opened meanwhile drops the asks of the one before it.
  const ask = (extra = {}, after = null) => {
    if (!t.plan) return Promise.resolve();
    t.queue.push({ plan: t.plan, extra, after });
    return t.running ??= (async () => {
      while (t.queue.length) {
        const { plan, extra: next, after: before } = t.queue.shift();
        await before;
        if (plan !== t.plan) continue;
        $("track-status").textContent = "…";
        const reply = await call("tracker", { given: { plan, marks: t.marks, spoiler: t.spoiler, gems: t.gems,
                                                       ...next } });
        $("track-status").textContent = "";
        if (plan !== t.plan) continue;
        if ("refused" in reply) {
          say(`Tracker: ${reply.refused}`, true);
          continue;
        }
        t.view = reply;
        t.marks = reply.marks;
        if (t.live) seeLive(reply.live);
        remember();
        draw();
      }
      t.running = null;
    })();
  };

  // The marks of each plan the page tracked (the last KEEP), and the plan last tracked, which a page opens on again.
  const remember = () => {
    const sha = t.plan.sha256;
    const marks = Object.fromEntries(Object.entries(t.kept.marks).filter(([k]) => k !== sha));
    marks[sha] = t.marks;
    t.kept = { plan: t.plan, marks: Object.fromEntries(Object.entries(marks).slice(-KEEP)),
               ...(t.kept.endpoints ? { endpoints: t.kept.endpoints } : {}), ...(t.gems ? { gems: true } : {}) };
    keep(t.kept);
  };

  // The maps: their pictures (drawn once from the image, then kept) and the canvas that shows them.
  const art = artStore({ app, image, changed: () => {
    artLine();
    if (t.view && t.mode === "map") draw();
  } });
  const map = new MapView({ room: $("map-room"), canvas: $("map-canvas"), back: $("map-back"), fit: $("map-fit"),
                            switches: $("map-switches"), floors: $("map-floors"), key: $("map-key"),
                            note: $("map-note"), hint: $("map-hint"), tip: $("map-tip") }, {
    view: () => t.view, art, spoiler: () => t.spoiler, gems: () => t.gems,
    toggle: (loc) => ask({ toggle: loc }),
    navigated: (level, byHand) => {
      if (byHand && t.live?.followed && level !== t.live.followed) {
        $("track-follow").checked = false;
        t.live.followed = null;
      }
      t.level = level;
      if (byHand) draw();
    },
  });
  const artLine = () => {
    const a = art.status;
    $("track-art").textContent = a.error ? a.error : a.drawing ? `Drawing the maps from your image: ${a.done.length} `
      + `of ${a.total} (${a.drawing})…` : a.total && !a.index && !image() ? "Pick your image and the maps are drawn "
      + "from it (once: they are kept)." : "";
    $("track-art").classList.toggle("error", Boolean(a.error));
  };

  const open = (plan, from = null) => {
    if (!plan || typeof plan !== "object" || typeof plan.sha256 !== "string") {
      return Promise.resolve(say(`${from ?? "That"} isn't a plan file`, true));
    }
    t.plan = plan;
    t.marks = t.kept.marks[plan.sha256] ?? {};
    t.level = null;
    $("track-empty").hidden = true;
    $("track-body").hidden = false;
    if (from) say(`Tracking seed ${plan.seed} (${from}): the Randomizer tab's Tracker`);
    if (t.live) liveOn();   // Live follows the plan shown
    return ask();
  };

  // The counter row, the head line and the levels reached now, then the shown view.
  const draw = () => {
    const v = t.view, s = v.status;
    // the maps: read once the Tracker view shows (a new drawing, or an image picked since), and drawn from the image
    if (!$("tracker").hidden && (art.status.version !== v.world.art.version || image() !== t.artFrom)) {
      t.artFrom = image();
      art.start(v.world.art.version, v.world.art.parts);
    }
    artLine();
    $("track-status").textContent = "";
    $("track-head").textContent = v.head.text;
    $("track-head").title = v.head.skips.join("\n") || "No skip is on.";
    $("track-count").textContent = `Collected ${s.collected} of ${s.total} · Reachable ${s.reachable}`
      + (s.skipped ? ` (${s.skipped} with a skip)` : "") + ` · Sphere ${s.sphere}` + (s.victory ? " · Victory in reach" : "");
    $("track-levels").textContent = `${t.live?.other ? t.live.other : ""}Levels now: ${s.levels.join(", ")}`;
    $("track-levels").classList.toggle("other", Boolean(t.live?.other));
    for (const mode of ["map", "table"]) $(`track-${mode}`).setAttribute("aria-selected", String(t.mode === mode));
    const drawn = t.mode === "map" && map.ready(t.level);   // its picture is drawn: the map view, else the grid or chips
    $("track-maps").hidden = !drawn;
    $("track-world").hidden = t.mode !== "map" || drawn || t.level !== null;
    $("track-level").hidden = t.mode !== "map" || drawn || t.level === null;
    $("track-tables").hidden = t.mode !== "table";
    if (t.mode === "table") return tables();
    if (drawn) {
      if (map.level !== t.level || map.pictures === undefined) map.show(t.level);
      else map.draw();
      map.floorButtons();
      return placed();
    }
    if (t.level === null) return worldMap();
    levelMap();
  };

  // The player on the map view: where Live saw them (grey once it lost xemu); Follow keeps a zoomed map on them.
  const placed = () => {
    const seen = t.live?.seen;
    if (!seen || $("track-maps").hidden) return map.here && map.place(null);
    map.place(seen, !t.live.here);
    const at = map.level === seen.level && map.pixel(seen);
    if (at && $("track-follow").checked && t.live.here) map.see(...at);
  };

  const counts = (level) => {
    const spots = Object.values(t.view.spots).filter((s) => s.level === level);
    const near = spots.filter((s) => s.state === "near").length, skip = spots.filter((s) => s.state === "skip").length;
    return { near, skip, got: spots.filter((s) => s.state === "got" || s.state === "live").length, total: spots.length };
  };

  // Perathia: each level in its place on the grid, with its spots reachable now in a badge (green, amber when only a
  // skip reaches them, R1.41), its collected of its total, and a ring round the level Live sees the player in.
  const worldMap = () => {
    const { grid } = t.view.world, reached = new Set(t.view.status.levels);
    $("track-world").replaceChildren(...Object.entries(grid).map(([level, [col, row]]) => {
      const c = counts(level), n = c.near + c.skip;
      const cell = el("button", { type: "button", className: "cell", title: `${level}: ${n} spots reachable now`
        + (c.skip ? ` (${c.skip} only with a skip)` : "") + `, ${c.got} collected` });
      cell.dataset.level = level;
      cell.style.gridColumn = String(col + 1);
      cell.style.gridRow = String(row + 1);
      cell.classList.toggle("reached", reached.has(level));
      cell.classList.toggle("here", t.live?.level === level);
      const badge = el("span", { className: `badge ${c.near ? "near" : c.skip ? "skip" : ""}`,
                                 textContent: reached.has(level) ? String(n) : "" });
      cell.append(el("b", { textContent: level }), badge, el("span", { className: "tally", textContent: `${c.got}/${c.total}` }));
      return cell;
    }));
  };

  // A level: its spots by class, each a chip ringed by its state, with its item once collected or with Spoiler (else
  // a dot) and a check once collected (blue when Live marked it); the levels its exits lead to; a click marks a spot.
  const levelMap = () => {
    const level = t.level, spots = Object.entries(t.view.spots).filter(([, s]) => s.level === level);
    const c = counts(level);
    const exits = (t.view.world.exits[level] ?? []).map((to) => {
      const go = el("button", { type: "button", className: "exit", textContent: `→ ${to}` });
      go.dataset.level = to;
      return go;
    });
    const back = el("button", { type: "button", className: "back", textContent: "← World map" });
    const top = el("p", { className: "rando-row" }, back, el("b", { textContent: level }),
                   el("span", { className: "note", textContent: `${c.got} of ${c.total} collected · ${c.near + c.skip} reachable now` }),
                   ...(exits.length ? [el("span", { className: "note", textContent: "Exits:" }), ...exits] : []));
    if (t.live?.level === level) top.append(el("span", { className: "you", textContent: "● you are here" }));
    const groups = CLASSES.map(([cls, title]) => {
      const mine = spots.filter(([, s]) => s.class === cls);
      if (!mine.length) return null;
      return el("div", { className: "spots" }, el("h4", { textContent: `${title} · ${mine.length}` }),
                ...mine.map(([loc, s]) => chip(loc, s)));
    }).filter(Boolean);
    $("track-level").replaceChildren(top, ...groups);
  };

  const chip = (loc, s) => {
    const shown = Boolean(s.item), got = s.state === "got" || s.state === "live";
    // A spot not shown is told by what the base game puts there (and its record), never by what the seed put there
    const where = `where vanilla has ${s.vanilla}, ${loc}`;
    const button = el("button", { type: "button", className: `spot ${s.state}`,
                                  title: `${shown ? s.name : SPOT[s.class]}: ${STATES[s.state]} (${where})` });
    button.dataset.loc = loc;
    button.append(el("span", { className: shown ? `glyph ${s.icon}` : "glyph dot" }),
                  el("span", { className: "name", textContent: shown ? s.name : `vanilla: ${s.vanilla} · ${loc.split("/").at(-1)}` }));
    if (got) button.append(el("span", { className: "check", textContent: "✓" }));
    return button;
  };

  // The Table: the items by kind and the spots by level, each with its All row last; Now and Where only with Spoiler,
  // In game while Live reads the game. A click on a level's row shows its map.
  const tables = () => {
    const spoiler = t.spoiler, game = Boolean(t.live?.reading);
    const items = ["got", ...(spoiler ? ["now"] : []), "left", "total", ...(game ? ["game"] : []), ...(spoiler ? ["where"] : [])];
    $("track-items").replaceChildren(...table("Item", items, t.view.table.items));
    $("track-places").replaceChildren(...table("Level", ["got", "now", "left", "total"], t.view.table.levels));
  };

  const table = (head, columns, rows) => {
    const body = el("tbody");
    const add = (row, depth) => {
      const tr = el("tr", { className: row.key === "all" ? "sum" : depth ? "" : "group" });
      tr.dataset.key = row.key;
      const label = el("th", { scope: "row", textContent: row.label });
      label.style.paddingLeft = `${6 + 14 * depth}px`;
      // a Where cut short by its column's width is read whole in its tip
      tr.append(label, ...columns.map((c) => el("td", { className: c, textContent: row[c] ?? "",
                                                         ...(c === "where" && row.where ? { title: row.where } : {}) })));
      body.append(tr);
      for (const child of row.children) add(child, depth + 1);
    };
    for (const row of rows) add(row, 0);
    return [el("thead", {}, el("tr", {}, el("th", { scope: "col", textContent: head }),
                                 ...columns.map((c) => el("th", { scope: "col", className: c, textContent: COLUMNS[c] })))), body];
  };

  // A map shown by hand that isn't the one Follow shows turns Follow off (Modkit's).
  const show = (level, byHand = true) => {
    if (byHand && t.live?.followed && level !== t.live.followed) {
      $("track-follow").checked = false;
      t.live.followed = null;
    }
    t.level = level;
    t.mode = "map";
    draw();
  };

  // ---- Live (the app's, D882): xemu's game read by the app, merged into the marks at each ask, every POLL_MS.
  const liveOn = async () => {
    const reply = await call("live", { on: true, plan: t.plan, marks: t.marks, endpoints: $("track-endpoints").value,
                                       gems: t.gems });
    if ("refused" in reply) {
      $("track-live").checked = false;
      liveOff();
      return say(reply.refused, true);
    }
    t.live ??= { followed: null, seen: null, here: null, other: "" };
    $("track-follow-box").hidden = false;
    clearInterval(t.poll);
    t.poll = setInterval(() => !t.running && !t.queue.length && ask(), POLL_MS);
  };

  const liveOff = () => {
    clearInterval(t.poll);
    t.live = null;
    $("track-follow-box").hidden = true;
    $("track-find").disabled = true;
    $("track-dot").textContent = $("track-line").textContent = "";
    $("track-dot").className = "";
    return ask({}, call("live", { on: false }));   // the reach holds the marks' levels alone, once the feed is gone
  };

  // What the app read: the status's dot and line, the player's level (the world map's ring, a level's "you are
  // here", Follow's map) and the levels row's warning while xemu runs another seed or build. An error that ended
  // the feed turns Live off, the reach back on the marks alone, and says why (Modkit's).
  const seeLive = (live) => {
    if (!live) return;
    if (live.status === "stopped") {
      $("track-live").checked = false;
      liveOff();
      $("track-line").textContent = $("track-line").title = live.text;
      return;
    }
    const was = t.live.here;
    t.live.seen = live.seen;
    t.live.here = live.here ? live.seen.level : null;
    t.live.level = t.live.here;
    t.live.reading = live.status === "live" || live.status === "warn";
    t.live.other = live.status === "other" ? `xemu runs another seed or build: what this shows is seed `
      + `${t.plan.seed}'s, not your game's. ` : "";
    $("track-dot").textContent = DOTS[live.status] ?? "";
    $("track-dot").className = live.status;
    $("track-line").textContent = live.text + (live.unpaired ? ` · ${live.unpaired} pickups seen without the item's `
      + "own change: not marked" : "");
    $("track-line").title = live.text;
    $("track-find").disabled = !live.seen;
    $("track-find").title = live.seen ? `Show ${live.seen.level}, ${live.here ? "the level you're in" : "where Live last "
      + "saw you"} (key: F)` : "Shows the level you're in once Live has seen you in one";
    if ($("track-follow").checked && t.live.here && t.live.here !== was && t.live.here !== t.level) {
      t.live.followed = t.live.here;
      t.level = t.live.here;
      t.mode = "map";
    }
  };

  const findMe = () => {
    if (!t.live?.seen) return;
    show(t.live.seen.level, false);
    const at = map.pixel(t.live.seen);
    if (at && !$("track-maps").hidden) map.see(...at, true);
  };

  $("track-world").addEventListener("click", (e) => {
    const cell = e.target.closest(".cell");
    if (cell) show(cell.dataset.level);
  });
  $("track-level").addEventListener("click", (e) => {
    const spot = e.target.closest(".spot"), exit = e.target.closest(".exit");
    if (spot) return ask({ toggle: spot.dataset.loc });
    if (exit) return show(exit.dataset.level);
    if (e.target.closest(".back")) show(null);
  });
  $("track-places").addEventListener("click", (e) => {
    const key = e.target.closest("tr")?.dataset.key;
    if (key && t.view.world.grid[key]) show(key);
  });
  $("track-spoiler").addEventListener("change", () => {
    t.spoiler = $("track-spoiler").checked;
    ask();
  });
  // Gems (R1.43): off by default, remembered; Live reads the gem spots only while they show, so it starts again
  $("track-gems").checked = t.gems = Boolean(t.kept.gems);
  $("track-gems").addEventListener("change", () => {
    t.gems = $("track-gems").checked;
    if (t.plan) remember();
    if (t.live) liveOn();
    ask();
  });
  $("track-reset").addEventListener("click", () => ask({ reset: true }));
  for (const mode of ["map", "table"]) {
    $(`track-${mode}`).addEventListener("click", () => {
      t.mode = mode;
      if (t.view) draw();
    });
  }
  $("track-open").addEventListener("change", async () => {
    const file = $("track-open").files[0];
    $("track-open").value = "";
    if (!file) return;
    let plan;
    try {
      plan = JSON.parse(await file.text());
    } catch {
      return say(`${file.name} isn't a plan file (not JSON)`, true);
    }
    open(plan, file.name);
  });

  if (app) {
    $("track-live-bar").hidden = false;
    $("track-endpoints").value = t.kept.endpoints ?? "";
    $("track-live").addEventListener("change", () => ($("track-live").checked ? liveOn() : liveOff()));
    $("track-find").addEventListener("click", findMe);
    $("track-follow").addEventListener("change", () => {
      if (t.live) t.live.followed = $("track-follow").checked ? t.live.here : null;
    });
    $("track-endpoints").addEventListener("change", () => {
      t.kept = { ...t.kept, endpoints: $("track-endpoints").value.trim() };
      if (!t.kept.endpoints) delete t.kept.endpoints;
      keep(t.kept);
      if (t.live) liveOn();
    });
    addEventListener("keydown", (e) => {
      if ((e.key === "f" || e.key === "F") && !e.target.closest("input, select, textarea") && !$("tracker").hidden) findMe();
    });
  }
  if (t.kept.plan) open(t.kept.plan);
  return { open, ask, state: t, art, map, draw: () => t.view && draw(), image: () => artLine() };
}
