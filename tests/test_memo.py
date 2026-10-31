"""Kept answers (Step 4.3x, D1008): the app's ``azurkit.app.memo`` and the
site's ``web/memo.mjs`` keep the engine's small answers under the sha256 of
the code, the randomizer database's key, the call, its canonical arguments
and installed.json, so a kept answer is the engine's own, any change to an
input misses, and nothing is kept with Live on or for a click that marks."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.app import memo
from azurkit.tools.characters import content as kit
from azurkit.tools.randomizer import tracking
from scripts import record_goldens

ROOT = Path(__file__).resolve().parent.parent
TRACKER = {key: row["view"] for key, row in record_goldens.recorded(record_goldens.TRACKER).items()}
PLANS = record_goldens.recorded(record_goldens.PLANS)
SETUP = {"ticked": ["fps_unlock"], "values": {}, "xbr": []}


def test_a_kept_answer_is_the_engines_byte_for_byte_and_any_change_to_its_key_misses(monkeypatch, tmp_path):
    """Each call's answer, worked out once, comes back kept for the same
    inputs, serializing to the engine's bytes (the tracker's view is
    tracker.json's), the page's tracker ask and the warm-up's sharing one
    key; another code, database, installed.json, argument or call is
    another key, and Live on, a click that marks or resets, or Live's kit
    (any kit given, a falsy one the tracker refuses too) has none."""
    monkeypatch.setattr(kit, "ROOT", tmp_path)
    doc = record_goldens.profile("default")
    asked = {"plan": doc, "marks": {}, "spoiler": False, "gems": False}   # web/tracker.mjs's ask on reopening
    warmed = {"plan": doc, "marks": None}                                  # the warm-up's (host.json's tracker)
    kept = memo.Memo()
    for call, first, again, work in (("tracker", warmed, asked, sdk.tracker), ("restore", SETUP, SETUP, sdk.restore),
                                     ("randomizer", {"share": doc["share"]}, {"share": doc["share"]},
                                      sdk.randomizer_settings),
                                     ("plan", {"seed": "2"}, {"seed": "2"}, lambda _: PLANS["default"]["plan"])):
        fresh, was = kept.answer(call, first, lambda: work(first))
        got, hit = kept.answer(call, again, lambda: pytest.fail(f"{call}: worked out again"))
        assert (was, hit) == (False, True), call
        assert memo._text(got, False) == memo._text(fresh, False), call
    assert hashlib.sha256(tracking.digest(got := kept.get("tracker", asked)).encode()).hexdigest()[:32] == TRACKER[
        "default/none/plain"]
    assert got["head"]["sha256"] == doc["sha256"]
    key = kept.key("restore", SETUP)
    (tmp_path / kit.INSTALLED).write_text(json.dumps({"booblord": {"version": "1", "files": {}}}), encoding="utf-8")
    assert kept.key("restore", SETUP) != key
    (tmp_path / kit.INSTALLED).unlink()
    assert kept.key("restore", SETUP) == key
    for part in ("code", "database"):
        with monkeypatch.context() as m:
            m.setattr(memo, part, lambda: "another")
            assert kept.key("restore", SETUP) != key, part
    assert len({key, kept.key("restore", SETUP | {"ticked": []}), kept.key("randomizer", SETUP)}) == 3
    assert [kept.key("tracker", asked | extra) for extra in ({"toggle": "x"}, {"reset": True}, {"kit": {"air": 3}},
                                                             {"kit": 0}, {"kit": []}, {"held": {"x": 1}},
                                                             {"what": 1})] == [None] * 7
    assert kept.key("restore", SETUP, live=True) is None and kept.key("spoiler", {}) is None
    assert kept.get("tracker", asked, live=True) is None


def test_a_kept_answer_the_engine_contradicts_is_logged_and_replaced_and_a_torn_entry_is_a_miss():
    """A confirm that works out another answer than the one kept logs both
    digests (never the answer) and keeps the engine's; one that agrees logs
    nothing. An entry cut short, or another key's, is a miss."""
    lines = []
    kept = memo.Memo(log=lines.append)
    kept.put("restore", SETUP, {"ticked": []})
    fresh = sdk.restore(SETUP)
    assert kept.confirm("restore", SETUP, kept.get("restore", SETUP), lambda: fresh) == fresh
    assert lines == [f"azurkit: a kept restore answer ({memo.digest({'ticked': []})[:12]}) differs from the engine's "
                     f"({memo.digest(fresh)[:12]}): a bug, the engine's is kept"]
    assert kept.get("restore", SETUP) == fresh
    kept.confirm("restore", SETUP, fresh, lambda: fresh)
    assert len(lines) == 1
    key, other = kept.key("restore", SETUP), kept.key("restore", SETUP | {"ticked": []})
    whole = kept.store.get(key)
    kept.store.put(key, whole[:-1])
    assert kept.get("restore", SETUP) is None
    kept.store.put(other, whole)
    assert kept.get("restore", SETUP | {"ticked": []}) is None


SITE = """
import { Memo, MemStore, text } from %s;
let input = "";
for await (const chunk of process.stdin) input += chunk;
const given = JSON.parse(input);
const lines = [], memo = new Memo({ log: (line) => lines.push(line) });
const space = { code: "wheel-sha384", entry: "db", installed: {} };
const out = {};
let worked = 0;
const work = (answer) => async () => (worked += 1, answer);
const first = await memo.answer("tracker", given.warmed, work(given.view), space);
const again = await memo.answer("tracker", given.asked, work(null), space);
out.tracker = [first.kept, again.kept, text(again.answer) === text(given.view), worked];
const key = await memo.key("restore", given.setup, space);
out.misses = await Promise.all([{ ...space, code: "other" }, { ...space, entry: "other" },
  { ...space, installed: { booblord: { version: "1" } } }, { ...space, live: true }]
  .map((s) => memo.key("restore", given.setup, s)).concat([memo.key("restore", { ...given.setup, ticked: [] }, space),
  memo.key("randomizer", given.setup, space)]));
out.misses = out.misses.map((k) => k === key ? "same" : k === null ? null : "other");
out.never = await Promise.all([{ toggle: "x" }, { reset: true }, { kit: { air: 3 } }, { kit: 0 }, { kit: [] },
  { what: 1 }]
  .map((extra) => memo.key("tracker", { ...given.asked, ...extra }, space)));
await memo.put("restore", given.setup, { ticked: [] }, space);
out.confirmed = [await memo.confirm("restore", given.setup, { ticked: [] }, given.view, space),
                 await memo.confirm("restore", given.setup, given.view, given.view, space)];
out.replaced = text(await memo.get("restore", given.setup, space)) === text(given.view);
out.lines = lines.length;
const whole = await memo.store.get(key);
await memo.store.put(key, whole.slice(0, -1));
out.torn = await memo.get("restore", given.setup, space);
await memo.put("plan", { seed: "2" }, { refused: "no" }, space);
out.refused = await memo.get("plan", { seed: "2" }, space);
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.web
def test_the_sites_kept_answers_are_the_workers_and_miss_on_any_change_and_never_with_live_on():
    """``web/memo.mjs`` under Node: the page's tracker ask hits what the
    warm-up's kept, as the worker's bytes; another code key, database key,
    installed record, argument or call misses, and Live on, a click that
    marks or resets, Live's kit (a falsy one too) or a key the tracker doesn't take has no
    key; a contradicted kept answer is logged once and replaced; a torn
    entry and a refusal are never answers."""
    doc = record_goldens.profile("default")
    view = sdk.tracker({"plan": doc})
    given = {"warmed": {"plan": doc, "marks": None}, "view": view, "setup": SETUP,
             "asked": {"plan": doc, "marks": {}, "spoiler": False, "gems": False}}
    script = SITE % json.dumps((ROOT / "web" / "memo.mjs").as_uri())
    run = subprocess.run(["node", "--input-type=module", "--eval", script], input=json.dumps(given),
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    assert json.loads(run.stdout) == {"tracker": [False, True, True, 1],
                                      "misses": ["other"] * 3 + [None] + ["other"] * 2, "never": [None] * 6,
                                      "confirmed": [False, True], "replaced": True, "lines": 1, "torn": None,
                                      "refused": None}
