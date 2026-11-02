// D1008's warm-up on the site (Step 4.3x): the twin of src/azurkit/app/warm.py. What the page's next asks will
// read, asked of the worker ahead while the page asks nothing (D1007: background work, dropped on a change), in two
// phases: phase A (phaseA), at ready, on intent only (Randomize on in the remembered setup, a tracked plan
// remembered, or the Randomizer tab opened): the randomizer's logic and the world map, the Randomizer tab's answer
// for the remembered setup and the remembered plan's tracker view, each answer kept (memo.mjs; the remembered seed's
// plan is the plan ahead's, AM-HUB-D's B: one ask of the one worker that a change couldn't drop); phase B (phaseB),
// after the first pick of an image: its check and the Characters tab's pickers. A dress is a heavy ask of the page's
// engine (one heavy job at a time, in the worker the page grew), not this queue's. The species' and the tracker's
// pictures ship with the page: nothing to warm for them.
//
// Warm runs one item at a time, each one ask of the worker (item.run()), started only while the page has no ask in
// flight (call()), so a page's ask waits behind at most one item in the worker's queue. An item in flight can't be
// stopped (no interrupt without D1013's isolation): a change (put of an item of the same name for other inputs, drop)
// drops the queued ones and marks the one in flight dropped, so its answer counts for nothing (it is still the right
// answer to its own ask). A page's ask that needs an item (need) moves it to the front and waits for it. A tab opened
// moves its items first (first). status() is the bottom bar's quiet row; `done` is true once nothing is queued or in
// flight (the perf gate's Driver.warmed waits on azurkit.warm.done); changed(status) hears each change of the row.

export const QUEUED = "queued", RUNNING = "running", DONE = "done", FAILED = "failed", DROPPED = "dropped";

// An item: {name, stage, label, run: () => Promise (its ask), key (what it is worked out for: an item of its name and
// key is the same item)}; its state is the queue's.
export const item = (name, stage, label, run, key = null) => ({ name, stage, label, run, key, state: QUEUED });
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

export class Warm {
  constructor({ changed = () => {} } = {}) {
    this.changed = changed;
    this.queued = [];
    this.running = null;
    this.ended = new Map();   // each name's item that ended last
    this.round = [];          // the items since the queue was last idle: the row's "k of n"
    this.calls = 0;
    this.waiting = 0;
    this.waiters = new Set();
  }

  get done() {
    return !this.running && !this.queued.length;
  }

  #notify() {
    for (const wake of [...this.waiters]) wake();
    this.changed(this.status());
  }

  // The asks waiting on it (need) hold no item back once it ends or is dropped.
  #release(it, count = it.needed ?? 0) {
    count = Math.min(count, it.needed ?? 0);
    it.needed = (it.needed ?? 0) - count;
    this.waiting -= count;
  }

  #forget(it) {
    if (it.state === QUEUED || it.state === RUNNING) it.state = DROPPED;
    if (it.state === DROPPED && this.running !== it) this.#release(it);
    this.round = this.round.filter((r) => r !== it);
  }

  // Queue items in order, each in place of a queued or running one of its name for another key (that one dropped);
  // one of its name and key that is queued, running or done already stands.
  put(items) {
    if (this.done) this.round = [];
    for (const it of items) {
      const ended = this.ended.get(it.name);
      if (ended?.state === DONE && same(ended.key, it.key)) continue;
      if (this.running?.name === it.name) {
        if (same(this.running.key, it.key) && this.running.state === RUNNING) continue;
        this.#forget(this.running);
      }
      const at = this.queued.findIndex((q) => q.name === it.name);
      if (at >= 0 && same(this.queued[at].key, it.key)) continue;
      if (at >= 0) {
        this.#forget(this.queued[at]);
        this.queued.splice(at, 1, it);
      } else {
        this.queued.push(it);
      }
      this.round.push(it);
    }
    this.#pump();
    this.#notify();
  }

  // A change (D1007): drop the queued items of names (none: every one); the one in flight, if named, counts for
  // nothing.
  drop(...names) {
    const named = (it) => !names.length || names.includes(it.name);
    for (const it of this.queued.filter(named)) this.#forget(it);
    this.queued = this.queued.filter((it) => !named(it));
    if (this.running && named(this.running)) this.#forget(this.running);
    this.#notify();
  }

  // Move the queued items of names to the front, in that order (a tab opened).
  first(...names) {
    const ahead = names.flatMap((n) => this.queued.filter((q) => q.name === n));
    this.queued = [...ahead, ...this.queued.filter((q) => !ahead.includes(q))];
  }

  // The page's own ask: fn() (a promise), no item started while it is in flight; begin() and end() bracket one the
  // page tracks itself (its asks' registry).
  async call(fn) {
    this.begin();
    try {
      return await fn();
    } finally {
      this.end();
    }
  }

  begin() {
    this.calls += 1;
  }

  end() {
    this.calls -= 1;
    this.#pump();
  }

  // Wait for the item name, moved to the front: whether it ended done (false: none queued or running and none done,
  // or it failed or was dropped: the ask does the work itself). onstart(item) hears the item waited on (its line).
  async need(name, onstart = () => {}) {
    const it = this.running?.name === name ? this.running : this.queued.find((q) => q.name === name);
    if (!it) return this.ended.get(name)?.state === DONE;
    this.first(name);
    onstart(it);
    it.needed = (it.needed ?? 0) + 1;
    this.waiting += 1;
    this.#pump();
    try {
      while (it.state === QUEUED || it.state === RUNNING) await new Promise((wake) => {
        const woken = () => { this.waiters.delete(woken); wake(); };
        this.waiters.add(woken);
      });
      return it.state === DONE;
    } finally {
      this.#release(it, 1);
    }
  }

  #pump() {
    if (this.running || !this.queued.length || this.calls > this.waiting) return;
    const it = this.running = this.queued.shift();
    it.state = RUNNING;
    this.#notify();
    Promise.resolve().then(() => it.run()).then(
      () => { if (it.state === RUNNING) it.state = DONE; },
      () => { if (it.state === RUNNING) it.state = FAILED; },   // a refusal: the page's own ask names it
    ).finally(() => {
      this.#release(it);
      if (it.state !== DROPPED) this.ended.set(it.name, it);
      if (this.running === it) this.running = null;
      this.#pump();
      this.#notify();
    });
  }

  // The bottom bar's row: {done, total, stage, label, ready} over the items since the queue was last idle.
  status() {
    return { done: this.round.filter((it) => it.state === DONE || it.state === FAILED).length,
             total: this.round.length, stage: this.running?.stage ?? null, label: this.running?.label ?? "",
             ready: this.done };
  }

  // A promise that resolves once nothing is queued or in flight.
  async idle() {
    while (!this.done) await new Promise((wake) => {
      const woken = () => { this.waiters.delete(woken); wake(); };
      this.waiters.add(woken);
    });
  }
}

// Whether phase A starts: Randomize on in setup (the remembered setup), a plan in tracked (the tracker kept), or the
// Randomizer tab opened.
export function intent({ setup, tracked, opened = false } = {}) {
  return Boolean(opened || setup?.randomizer?.on === true || (tracked?.plan && typeof tracked.plan === "object"));
}

// Phase A's items (none without intent), each one ask through ask(type, fields) (the page's call to the worker:
// its reply), its answer kept in memo under space (memo.mjs): the logic and the world map ({type: "warm"}), with
// tab (the Randomizer tab's ask for the remembered setup, as the page makes it) the tab's answer; with tracked the
// plan last tracked's view, as the page asks it on reopening.
export function phaseA({ memo, space, ask, setup, tracked, tab, opened = false }) {
  if (!intent({ setup, tracked, opened })) return [];
  const kept = async (call, args, fields) => {   // a refusal fails the item (the page's own ask names it)
    const got = await memo.answer(call, args, () => ask(call, fields), space);
    if (got.answer && typeof got.answer === "object" && "refused" in got.answer) throw new Error(got.answer.refused);
    return got;
  };
  const items = [item("logic", "plan", "Reading the randomizer's logic", () => ask("warm", { what: "logic" })),
                 item("world", "plan", "Reading the world map", () => ask("warm", { what: "world" }))];
  const plan = tracked?.plan;
  if (plan && typeof plan === "object" && typeof plan.sha256 === "string") {
    const given = { plan, marks: tracked.marks?.[plan.sha256] ?? null, gems: Boolean(tracked.gems) };
    items.push(item("tracker", "plan", "Reading the seed's logic", () => kept("tracker", given, { given }),
                    [plan.sha256, given.marks, given.gems]));
  }
  if (tab && typeof tab === "object") {
    items.push(item("tab", "plan", "Reading the randomizer's settings", () => kept("randomizer", tab, { given: tab }),
                    tab));
  }
  return items;
}

// Phase B's items, after the first pick of `file` (a File): its check (the engine's prime, once a File) and the
// Characters tab's pickers.
export function phaseB({ ask, file }) {
  return [item("image", "check", "Checking your image", () => ask("pickers", { file, given: {} }),
               [file.name, file.size, file.lastModified])];
}
