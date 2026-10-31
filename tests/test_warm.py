"""The warm-up (Step 4.3x, D1008, D1007): the app's ``azurkit.app.warm``
and the site's ``web/warm.mjs`` work out ahead, one item at a time, what
the page's next calls read, never while a call is in flight, dropped on a
change, a call that needs an item served first; after it a plan, a tracker
view, the Randomizer tab's answer and a seed build are the cold run's."""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from azurkit import cli, sdk
from azurkit.app import memo, warm
from azurkit.core.progress import record
from azurkit.tools.characters import content as kit
from azurkit.tools.randomizer import tracking
from scripts import record_goldens

ROOT = Path(__file__).resolve().parent.parent
TRACKER = {key: row["view"] for key, row in record_goldens.recorded(record_goldens.TRACKER).items()}
PLANS = record_goldens.recorded(record_goldens.PLANS)
QUIET = 0.3   # how long a test watches for what must not happen


def _item(name: str, log: list, steps: int = 2, hold: threading.Event | None = None, key=None, pooled=False):
    """An item that reports ``steps`` records, logging ``(name, k)`` after
    each, waiting on ``hold`` after its first."""
    def run(progress):
        for k in range(steps):
            progress(record("plan", name, k, steps))
            if k == 0 and hold is not None:
                log.append((name, "held"))
                assert hold.wait(10)
            log.append((name, k))
    return warm.Item(name, "plan", f"Warming {name}", run, key=key, pooled=pooled)


def _until(test, timeout: float = 10) -> None:
    end = time.monotonic() + timeout
    while not test():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.01)


def test_the_warm_up_yields_to_any_call_drops_on_a_change_and_serves_first_what_a_call_needs():
    """No item starts while a call is in flight, and the running one waits
    at its next record until no call is (a pooled one, a dress, runs on);
    an item of the same name for other inputs stops the running one at its
    next record and runs in its place, one for the same inputs stands; a
    call that needs an item has it run first even while that call is in
    flight, hearing its line and records, then the rest waits for the
    call; a tab moves its items first; the row counts the round."""
    q, log = warm.Queue(), []
    with q.call():
        q.put([_item("a", log)])
        time.sleep(QUIET)
        assert log == [] and q.status()["label"] == ""
    assert q.idle(10) and log == [("a", 0), ("a", 1)]

    log.clear()
    hold = threading.Event()
    q.put([_item("b", log, hold=hold)])
    _until(lambda: ("b", "held") in log)
    with q.call():
        hold.set()
        time.sleep(QUIET)
        assert log == [("b", "held"), ("b", 0)]   # paused at its second record
    assert q.idle(10) and log[-1] == ("b", 1)

    log.clear()
    hold = threading.Event()
    q.put([pooled := _item("d", log, hold=hold, pooled=True)])
    _until(lambda: ("d", "held") in log)
    with q.call():
        q.drop("d")
        hold.set()
        _until(lambda: ("d", 1) in log)   # never paused, nor stopped once it runs
    assert q.idle(10) and pooled.state == warm.DONE

    log.clear()
    hold = threading.Event()
    q.put([old := _item("c", log, hold=hold, key=1)])
    _until(lambda: ("c", "held") in log)
    q.put([new := _item("c", log, key=2)])
    hold.set()
    assert q.idle(10) and (old.state, new.state) == (warm.DROPPED, warm.DONE)
    assert log == [("c", "held"), ("c", 0), ("c", 0), ("c", 1)]   # the old one stopped at its second record
    q.put([_item("c", log, key=2)])
    assert q.idle(10) and len(log) == 4   # done for those inputs: it stands

    log.clear()
    seen = []
    with q.call():
        q.put([x := _item("x", log), _item("y", log), _item("z", log)])
        q.first("z")
        assert q.need("y", seen.append)
        assert log == [("y", 0), ("y", 1)] and x.state == warm.QUEUED
        assert seen[0]["label"] == "Warming y" and {s["label"] for s in seen[1:]} <= {"y"}
        assert q.status() == {"done": 1, "total": 3, "stage": None, "label": "", "percent": None, "ready": False}
    assert q.idle(10) and [name for name, _ in log[2:]] == ["z", "z", "x", "x"]
    failed = warm.Item("f", "plan", "Failing", lambda progress: 1 / 0)
    q.put([failed])
    assert q.idle(10) and not q.need("f") and not q.need("nothing") and q.need("x")
    assert q.status()["ready"]
    q.close()


def test_after_phase_a_a_seeds_plan_its_tracker_view_and_the_tabs_answer_are_the_cold_runs(monkeypatch, tmp_path):
    """With Randomize on and a tracked plan remembered, phase A reads the
    logic and world map and keeps the tab's answer, the tracked plan's view
    as the page asks it on reopening (tracker.json's; under the host's
    tracker lock) and the remembered
    seed's plan at the tab's share string (rando_plans.json's default plan);
    without intent it has no item."""
    monkeypatch.setattr(kit, "ROOT", tmp_path)
    doc = record_goldens.profile("default")
    kept, tab = memo.Memo(), {"share": doc["share"]}
    setup = {"randomizer": {"on": True, "seed": "2", "settings": {}}}
    assert warm.phase_a(kept, {"randomizer": setup["randomizer"] | {"on": False}}, None, tab) == []
    q = warm.Queue()
    q.put(items := warm.phase_a(kept, setup, {"plan": doc, "marks": {doc["sha256"]: {}}}, tab,
                                guard=threading.Lock()))
    assert q.idle(900)
    assert [(i.name, i.state) for i in items] == [(n, warm.DONE) for n in ("logic", "world", "tracker", "tab", "plan")]
    assert kept.get("plan", {"seed": "2", "share": doc["share"]}) == PLANS["default"]["plan"]
    view = kept.get("tracker", {"plan": doc, "marks": {}, "spoiler": False, "gems": False})
    assert hashlib.sha256(tracking.digest(view).encode()).hexdigest()[:32] == TRACKER["default/none/plain"]
    assert memo.digest(kept.get("randomizer", tab)) == memo.digest(sdk.randomizer_settings(tab))
    q.close()


def test_after_both_phases_a_seed_build_is_g3s_golden(usa_iso, monkeypatch, tmp_path):
    """After phase A (Randomize on, seed 2) and phase B on the USA image
    (its read), seed 2's build changes the files G3's default seed case
    names to their sha256 and carries the default plan."""
    monkeypatch.setattr(kit, "ROOT", tmp_path)
    q = warm.Queue()
    q.put(warm.phase_a(memo.Memo(), {"randomizer": {"on": True, "seed": "2", "settings": {}}}, opened=True)
          + warm.phase_b(str(usa_iso), {"character": {"species": "garret4"}}))
    assert q.idle(900) and q.status()["done"] == 3
    _, report = sdk.image(cli.recipe(str(usa_iso), [], [], True, randomizer={"seed": "2"}))
    golden = record_goldens.recorded("pipelines.json")["randomize-full:seed=2,default"]
    assert report["result"] == {f: sha for f, sha in golden.items() if f != "ISO"}
    assert report["randomizer"]["plan"] == PLANS["default"]["sha256"]
    q.close()


SITE = """
import { Warm, item, phaseA, phaseB, DONE, DROPPED, QUEUED } from %s;
import { Memo } from %s;
const tick = () => new Promise((r) => setTimeout(r, 20));
const out = {}, asked = [];
let release;
const ask = async (type, fields) => {
  asked.push(type);
  if (type === "randomizer") return { share: "AZR-AAEA", settings: fields.given };
  if (type === "plan") return { plan: { seed: fields.recipe.seed, share: fields.recipe.share } };
  if (type === "tracker") return { head: { sha256: fields.given.plan.sha256 }, marks: fields.given.marks };
  if (type === "slow") await new Promise((r) => (release = r));
  return {};
};
const w = new Warm();
let hold;
const page = w.call(() => new Promise((r) => (hold = r)));
w.put([item("a", "plan", "A", () => ask("a"))]);
await tick();
out.held = [...asked];
hold();
await page;
await w.idle();
out.after = [...asked];
asked.length = 0;
w.put([item("s", "plan", "S", () => ask("slow"), 1), item("t", "plan", "T", () => ask("t"))]);
await tick();
w.put([item("s", "plan", "S", () => ask("s2"), 2)]);
const dropped = w.running;
w.drop("t");
release();
await w.idle();
out.change = [[...asked], dropped.state];
asked.length = 0;
let inside;
await w.call(async () => {
  w.put([item("x", "plan", "X", () => ask("x")), item("y", "plan", "Y", () => ask("y")),
         item("z", "plan", "Z", () => ask("z"))]);
  w.first("z");
  inside = [await w.need("y"), [...asked], w.queued.map((q) => q.name)];
});
await w.idle();
out.need = [inside, [...asked], await w.need("nothing"), await w.need("y")];
const memo = new Memo(), space = { code: "wheel", installed: {} };
const plan = { sha256: "p" };
out.intent = phaseA({ memo, space, ask, setup: { randomizer: { on: false } } }).length;
asked.length = 0;
w.put(phaseA({ memo, space, ask, setup: { randomizer: { on: true, seed: " 2 " } }, tab: { share: "AZR-AAEA" },
               tracked: { plan, marks: { p: { collected: ["x"] } } } }));
await w.idle();
out.phaseA = [[...asked], await memo.get("plan", { seed: "2", share: "AZR-AAEA" }, space),
              await memo.get("tracker", { plan, marks: { collected: ["x"] }, spoiler: false, gems: false }, space),
              w.status()];
const file = { name: "usa.iso", size: 1, lastModified: 2 };
out.phaseB = phaseB({ ask, file }).map((it) => [it.name, it.stage, it.key]);
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.web
def test_the_sites_warm_up_asks_the_worker_one_item_at_a_time_only_while_the_page_asks_nothing():
    """``web/warm.mjs`` under Node, its worker a stub: no item is asked
    while a page's ask is in flight; a change drops the queued item and
    leaves the one in flight's answer counting for nothing, its new inputs
    asked next; a page's ask that needs an item has it asked first, the rest
    after the ask; phase A, on intent only, keeps the tab's answer, the
    remembered seed's plan at its share string and the tracked plan's
    view; phase B checks the picked image."""
    uri = lambda name: json.dumps((ROOT / "web" / name).as_uri())   # noqa: E731
    run = subprocess.run(["node", "--input-type=module", "--eval", SITE % (uri("warm.mjs"), uri("memo.mjs"))],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert (out["held"], out["after"]) == ([], ["a"])
    assert out["change"] == [["slow", "s2"], "dropped"]
    assert out["need"] == [[True, ["y"], ["z", "x"]], ["y", "z", "x"], False, True]
    assert out["intent"] == 0
    assert out["phaseA"] == [["warm", "warm", "tracker", "randomizer", "plan"],
                             {"plan": {"seed": "2", "share": "AZR-AAEA"}},
                             {"head": {"sha256": "p"}, "marks": {"collected": ["x"]}},
                             {"done": 5, "total": 5, "stage": None, "label": "", "ready": True}]
    assert out["phaseB"] == [["image", "check", ["usa.iso", 1, 2]]]
