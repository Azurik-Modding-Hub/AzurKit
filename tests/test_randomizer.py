"""The randomizer against its goldens (``tests/goldens/``, which
``scripts/record_goldens.py`` records from AzurKit's own planner; the first
recording, Step 4.12b, was Modkit's at oracle-rando-6): its planner (Step
4.2a; ``rando_plans.json``: seed 2 under the strict, default and max
settings gives its attempt, plan sha256 and spoiler, and the default plan
file byte for byte, on CPython and under Pyodide, the site's runtime, the
same in two processes under two hash seeds) and its generator layer (Step 4.2b): G3's seed cases build their files
and image on both releases (``pipelines.json``) and the default case's
spoiler is the ``--spoiler`` file of its plan, a later layer over a
placement is a conflict and any other difference a failure, and moved
movement sliders plan their tier's seed (D1066); the Randomizer tab's
settings (Step 4.2c1); the item tracker's verdicts (Step 4.2c2) at
several states and the maps' model of each (``tracker.json``); the
checked database the wheel and the app ship (Step 4.3g); R2.1's solver
(Step 4.3u): RS1's 80 plans as the solver before it made them, the
grammar's monotone rules it rests on, the fill's counted notes and the
wait on a fill another thread is making; Seed difficulty's levels in order
by its measures, its share strings and files, and v1.0.0's levels."""

from __future__ import annotations

import base64
import collections
import concurrent.futures
import dataclasses
import functools
import gc
import hashlib
import io
import json
import math
import os
import random
import re
import struct
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path

import pytest

from azurkit import cli, sdk
from azurkit.core import iso, native, progress
from azurkit.core.xbr import nodes
from azurkit.edits import manifest as edits
from azurkit.tools import mods, randomizer
from azurkit.tools.randomizer import dbcache, generator, layer, needs, tracking, writer
from azurkit.tools.randomizer.planner import difficulty, fill, loader, solver
from azurkit.tools.randomizer.planner.grammar import ParseError, parse
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.plan import PlanError, load_plan, plan_doc
from azurkit.tools.randomizer.planner.settings import (
    Settings, picks, picks_on, settings_from_table, share_decode, share_encode, share_sliders, turnable)
from azurkit.tools.randomizer.planner.solver import Logic
from scripts import record_goldens, web_tools

PLANS = record_goldens.recorded(record_goldens.PLANS)
DEFAULT_PLAN = json.dumps(PLANS["default"]["plan"], indent=1, sort_keys=True) + "\n"   # its plan file
G3 = {"usa": "pipelines.json", "europe": "europe/pipelines.json"}
JUMP = {"player_physics": {"jump_speed_scale": 1.3}}
# tracker.json (Step 4.2c2, 4.2c3): by <plan>/<state>/<plain|spoiler>, the sha256[:32] of the tracker's view
# (tracking.digest) and of the maps' model the page draws of it (web/mapview.mjs, tests/test_site.py's MAP_MODEL)
TRACKER = {key: row["view"] for key, row in record_goldens.recorded(record_goldens.TRACKER).items()}
TRACKER_MAP = {key: row["map"] for key, row in record_goldens.recorded(record_goldens.TRACKER).items()}
# A level's map as the page draws it with no plan (Step 4.4u3): its level, the picker's, whether every floor's picture
# is in, and its spots' marks (web/mapview.mjs's marks()) and their tips with whether a click on one does anything
BROWSED = """async () => {
    const { marks } = await import("./mapview.mjs");
    const m = azurkit.tracker.map, view = m.hooks.view(), names = new Set(Object.values(view.spots).map((s) => s.name));
    return [m.level, document.getElementById("track-pick").value, m.pictures.every((p) => p.bitmap),
            marks(view, m.level, () => true).spots,
            m.hits.filter((h) => names.has(h.tip?.split(" · ")[0])).map((h) => [h.tip, Boolean(h.act)])];
}"""
# the hosts' tests (test_site, test_hosts) take these from here: seed 2's plan by case, and tracker.json's states
_profile, tracker_states, shows_gems = record_goldens.profile, record_goldens.tracker_states, record_goldens.shows_gems
# RS1's 80 plans (round 2's R2.1, Step 4.3u): seeds 1 to 20 under four option sets (skip ceiling, movement tier;
# the goldens' strict, default and max and a skip ceiling of 2), each "attempt, the plan's sha256[:12], its
# spoiler lines' sha256[:12]" as the solver before R2.1 made them (AzurKit 3cd8a44, RS1's proof20-A), less the seed
# difficulty lines every spoiler gained after (D1157: rando_plans.json's spoilers hold them)
OPTIONS80 = {"strict": (0, "safe"), "default": (0, "standard"), "max": (4, "frame_perfect"), "ceiling2": (2, "standard")}
PLANS80 = {
    "strict": (
        "0 329ecaca3e86 56b8f90d6db0",
        "1 42f64b314152 284357947518",
        "0 7180891bd7da a29820fbdf14",
        "1 1e0b3427c5f5 87e972b414f5",
        "1 67f3d3958552 b66c769ec7c9",
        "0 e0bfc568a1ae e6a10b9fb2b5",
        "1 d9db4051bad5 7cc549652434",
        "0 148961baad6a cf07e65527fb",
        "0 6a295c6396b0 34a141289098",
        "0 f88761c309d2 9dceedd7e1b0",
        "1 17d94dd6f03e de0746453885",
        "0 18297ff7d13c 059407f99787",
        "0 c4325ba4c5d5 1fdca6341b64",
        "0 2492075fefb1 40c7ba590220",
        "0 77028a62f9d3 189a6ba2bd03",
        "0 5c239627cb14 95947e082cd2",
        "0 1fe8f2520d69 588d47e8c703",
        "2 4736ffbf9349 b1ecc168be36",
        "0 2cfb19022260 d1a696e23b83",
        "1 2937bec750a9 a82b93c335e9",
    ),
    "default": (
        "0 ea41d8df6d67 45f92dc9acdb",
        "0 aa53a70eff1b 4b45b2b18acc",
        "1 df0581cea90a bb71abb95649",
        "1 930f7a2d59d0 2f1d73e97253",
        "1 c399c28257bf b0f3f09d6bc7",
        "0 83d3a5516a51 3983122f8cb8",
        "0 39ab8c765d04 ad97ab301f25",
        "0 ea3fdcc11b2c 9bec35782029",
        "0 be05ee602619 f34c679fe95b",
        "0 47e404a7adbb 3cedb92e1a22",
        "0 5b84b0b6b3af b1f5ac1106dc",
        "0 8dd9990a0262 54482baeb1f7",
        "0 f50c622ce41a eadb47f3062b",
        "0 f58a86869e7a 33658fc44ffa",
        "0 71e7a3eedc3c 69cb48cee128",
        "1 9945748459c1 e63e3c938d40",
        "0 19aaab9966e2 fcebb65dccb8",
        "0 f1488d060230 577376eb5e8b",
        "1 6f2c12611755 8cab8a82160c",
        "0 89a6480485e3 965d9dce1425",
    ),
    "max": (
        "0 8b1366d9ee3f 4ad4ba11115f",
        "0 33e1c79d103a ebf3d99c54de",
        "0 fd53f193a51c e78614e773ff",
        "0 c2717335d41d 061be9299a60",
        "0 3109934038fb e321f0e8718f",
        "0 440f4b6646d0 dc3365f09c61",
        "0 e0913b752b78 3440d55ff005",
        "0 215449d6cd9e 13d42a8af91f",
        "0 a2d7bf760c61 9a13a4db1992",
        "0 1e2b75c1e7ff 4ed887f9d71c",
        "0 23a6c946d04f 72ec87f24d83",
        "1 403adfcea844 48cf254201ce",
        "0 72bdafb66ae5 69f9eb85ad72",
        "0 a931897bb961 7e86214fba90",
        "0 afccf3279721 b2454910544c",
        "0 befeab2b9301 47a9f5432915",
        "0 2babeb6f84d7 1b16081c3510",
        "0 239a99a30d89 697aed884195",
        "0 5afa8b34298e 74ec2bb6234c",
        "0 4ec9acb0bf28 c14a14a56e06",
    ),
    "ceiling2": (
        "0 2de91e522823 163467646dc6",
        "0 2298cb7a480a 19efa3094c1f",
        "0 b61e7ee525b2 b5687f8ce8e7",
        "0 d35d07810ad1 e30b3720398a",
        "0 fe18105cb669 2d0fee4f2364",
        "0 9c0c281ec0b4 83f240e18d31",
        "0 a52a7c5f5cae c37d299ea325",
        "0 bf155384a5a1 04015e096268",
        "0 1229cdd4dd8f 6c3aa0ec7f23",
        "0 01db9aeb6d87 d6e32939b80f",
        "0 e4f53ceade3f fe19523da9db",
        "0 44d0ad3852fa 02a4cbec0df0",
        "0 8c90c73c9492 dcafa4bb94a9",
        "0 0d9998be3380 06d6f99b060d",
        "0 42fe7036a97b 17255b6042ed",
        "0 61926eb93dfe 8c0539fbe1f6",
        "0 38ecf2543787 5f9247051a84",
        "0 edf454c107b2 b33ce16ef3cb",
        "0 9e207265d974 5b415ce2d4de",
        "0 bdc762689e11 73d6722e00a9",
    ),
}
_PLANS80 = """
import hashlib, json, sys
from azurkit import sdk
from azurkit.tools.randomizer.planner.fill import settings_table
from azurkit.tools.randomizer.planner.settings import Settings
st = settings_table(Settings(*json.loads(sys.argv[1]), {}))
for seed in range(1, 21):
    doc = sdk.plan({"seed": str(seed), "settings": st})
    lines = [x for x in sdk.spoiler(doc)["lines"] if not x.startswith(("seed difficulty: ", "step-up "))]
    print(doc["attempt"], doc["sha256"][:12], hashlib.sha256("\\n".join(lines).encode()).hexdigest()[:12])
"""


# Seed difficulty (D1157) at Hard movement and Hard skips: each level's plans of seeds "0".."3", each "attempt
# sha256[:12] steps off step-ups" (its key-item steps, key items off the path and play_r's step-ups at each rating from
# 2 to Hard), recorded under PYTHONHASHSEED=0 by this test's own script.
LEVELED = {
    "Easy": ("1 9e13c510c568 13 11 0", "1 32e3cb8f18e7 12 11 0", "2 457bcd21525c 12 11 0", "0 295e38372f7f 11 12 0"),
    "Normal": ("0 ef3cd32577c1 15 16 1", "0 8a127a341bd9 17 12 0", "0 4a4654c998f8 14 13 0", "0 0a761368c8ef 18 15 4"),
    "Hard": ("0 14cc892a950f 19 19 1", "0 b0132b3dbb8f 23 17 2", "0 9434dd2bbbd8 17 17 1", "0 b6d868d64336 17 16 1"),
    "Expert": ("6 7c937709c6a1 19 20 4", "5 3de596999d73 21 18 3", "6 7ba462fedc48 21 19 3", "1 ef164b6cd297 19 19 4"),
}
LEVELED_TABLE = {"format": "azurik-rando-settings/2", "skip_ceiling": 3, "movement_tier": "hard", "dark_fire": 1,
                 "exclude_categories": [], "skip_override": {}}
_LEVELED_ROWS = """
import json, sys
from azurkit import sdk
from azurkit.tools.randomizer.planner import difficulty, fill
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.plan import load_plan
base, logic, out = json.loads(sys.argv[1]), kept_logic(), {}
for level in ("Easy", "Normal", "Hard", "Expert"):
    out[level] = []
    for seed in "0123":
        doc = sdk.plan({"seed": seed, "settings": base | ({"seed_difficulty": level} if level != "Normal" else {})})
        plan = load_plan(doc, logic.db)
        st = plan.settings
        assert not fill.verify(logic, st, plan.placement)
        prof = difficulty.profile(logic, st, plan.placement)
        judge = difficulty.Judge(logic, st, fill.key_spots(logic, st), difficulty.detours(logic, st))
        ups = sum(judge.step_ups(plan.placement, r) for r in range(2, judge.top + 1))
        assert judge.score(plan.placement) == prof["steps"] + prof["off"] + 2 * ups
        head = sdk.tracker({"plan": doc})["head"]["difficulty"]
        assert (head["level"], head["steps"], head["off"], head["points"], head["text"]) == (
            level, prof["steps"], prof["off"], prof["points"], difficulty.line(prof)), head
        if seed == "0":
            line = next(x for x in sdk.spoiler(doc)["lines"] if x.startswith("seed difficulty: "))
            assert line.startswith(f"seed difficulty: {level}: {prof['steps']} key-item steps, {prof['off']} off the "
                                   "path, ") and ("no trick needed" in line) == (not prof["points"]), line
        out[level].append(f"{doc['attempt']} {doc['sha256'][:12]} {prof['steps']} {prof['off']} {ups}")
print(json.dumps(out))
"""


def test_seed_difficulty_levels_lean_chains_off_path_and_tricks_in_order(monkeypatch):
    """D1157: at Hard movement and skips each level's plans pass the verify; over seeds "0".."3" their key-item steps
    and key items off the path rise Easy < Normal < Hard <= Expert, their step-ups Easy <= Normal <= Hard <= Expert with
    Expert's above Normal's; the tracker's head and the spoiler's line give the measures the fill's score reads; the
    plans are pinned in two processes under two hash seeds; an Easy and an Expert fill keep the same plan with their
    attempts beside each other at width 3 as one at a time."""
    from azurkit.app import procpool

    def rows(hashseed: int) -> dict:
        done = subprocess.run([sys.executable, "-c", _LEVELED_ROWS, json.dumps(LEVELED_TABLE)], text=True,
                              env=os.environ | {"PYTHONHASHSEED": str(hashseed)}, capture_output=True, timeout=1800)
        assert done.returncode == 0, done.stderr[-2000:]
        return json.loads(done.stdout)

    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        got = list(pool.map(rows, (0, 1)))
    assert got[0] == got[1] == {level: list(pins) for level, pins in LEVELED.items()}
    sums = {level: [sum(int(row.split()[i]) for row in pins) for i in (2, 3, 4)] for level, pins in LEVELED.items()}
    (easy, normal, hard, expert) = (sums[level] for level in ("Easy", "Normal", "Hard", "Expert"))
    for i in (0, 1):
        assert easy[i] < normal[i] < hard[i] <= expert[i], sums
    assert easy[2] <= normal[2] <= hard[2] <= expert[2] and expert[2] > normal[2], sums

    logic = kept_logic()
    shaped = [Settings(3, "hard", {}, seed_difficulty=level) for level in (1, 3)]
    one = [fill._fill(logic, seed, st).placement for st in shaped for seed in "01"]
    monkeypatch.setattr(fill, "WIDTH", 3)
    monkeypatch.setattr(fill, "BESIDE", procpool.Beside)                   # the app's engine's
    assert [fill._fill(logic, seed, st).placement for st in shaped for seed in "01"] == one


def test_easy_with_the_elemental_powers_kept_plans_from_its_lean_no_deeper_than_normal_and_below_its_score_with_no_trick():
    """D1157, D1160 with the elemental powers kept vanilla: Easy's lean put every key item early, so a realm's last
    fragment opened it long before the kept power that gets the player back out (new trick-free traps), and the trap
    gate's repair had no key item after them to swap. Easy's repair moves that fragment past the kept power, to the
    earliest and closest spot first, so over seeds "0".."3" at Hard movement and skips and "0".."7" at Standard and no
    skips each Easy plan comes from a leaning attempt, passes the verify, needs no trick and scores below Normal's, and
    at Standard its key-item steps are no more than Normal's (drawn at random among every later spot, seeds "2" and "4"
    took more)."""
    logic = kept_logic()
    for (ceiling, tier), seeds in (((3, "hard"), "0123"), ((0, "standard"), "01234567")):
        easy, normal = (Settings(ceiling, tier, {}, frozenset({"powers"}), seed_difficulty=level) for level in (1, 0))
        judge = difficulty.Judge(logic, easy, fill.key_spots(logic, easy), difficulty.detours(logic, easy))
        for seed in seeds:
            made, today = fill._fill(logic, seed, easy), fill._fill(logic, seed, normal)
            assert made.attempt < difficulty.LEANED and not fill.verify(logic, easy, made.placement), (tier, seed)
            assert not judge._need(made.placement, 2), (tier, seed)
            assert judge.score(made.placement) < judge.score(today.placement), (tier, seed)
            assert tier == "hard" or (difficulty.chain(logic, easy, made.placement)
                                      <= difficulty.chain(logic, normal, today.placement)), seed


def test_easy_keeps_normals_own_plan_only_where_it_scores_below_each_of_easys_so_no_easy_plan_scores_above_normals(
        monkeypatch):
    """D1160: Easy's candidates end with Normal's own plan for the seed and settings (``fill._Run.normal_plan``), kept
    only where it scores below every one of Easy's, a tie keeping Easy's: at Standard and Safe movement with no skips,
    seeds "7" and "72", where Normal's draw scored below each of Easy's 3, Easy's plan is Normal's; at seeds "0" and
    "1" it is the one Easy's own 3 give, below Normal's. Every plan passes the verify."""
    logic = kept_logic()
    for tier, seeds in (("standard", {"7": True, "0": False}), ("safe", {"72": True, "1": False})):
        easy, normal = (Settings(0, tier, {}, seed_difficulty=level) for level in (1, 0))
        judge = difficulty.Judge(logic, easy, fill.key_spots(logic, easy), difficulty.detours(logic, easy))
        for seed, taken in seeds.items():
            made, today = fill._fill(logic, seed, easy), fill._fill(logic, seed, normal)
            with monkeypatch.context() as m:
                m.setattr(fill._Run, "normal_plan", lambda run, seed: None)
                own = fill._fill(logic, seed, easy)
            assert not fill.verify(logic, easy, made.placement), (tier, seed)
            assert made.placement == (today if taken else own).placement, (tier, seed)
            assert (judge.score(own.placement) > judge.score(today.placement)) == taken, (tier, seed)


def test_with_the_elemental_powers_kept_each_level_plans_a_seed_whose_attempts_of_today_all_meet_the_trap_gate():
    """D1160: with the elemental powers kept at Hard movement and skips, each of seed "52"'s 20 attempts of today (and
    seed "2"'s with the upgrades kept too) opens a realm before the kept power that gets the player back out, with no
    key item after the new trick-free traps to swap, so Normal found no plan (D35). Its 20 more attempts let the trap
    gate's repair move the realm's opener past the kept power, as each level's attempts do, so each level plans both
    seeds, Normal from an attempt past today's, and every plan passes the verify."""
    logic = kept_logic()
    for kept, seed in ((frozenset({"powers"}), "52"), (frozenset({"powers", "upgrades"}), "2")):
        for level in range(4):
            st = Settings(3, "hard", {}, kept, seed_difficulty=level)
            made = fill._fill(logic, seed, st)
            assert not fill.verify(logic, st, made.placement), (seed, level)
            assert level or made.attempt >= fill.MAX_ATTEMPTS, seed


def test_a_shaped_plans_openers_worked_out_ahead_answer_its_spoiler_with_no_reach_of_their_own(monkeypatch):
    """The app's job ahead of the spoiler's View: the View takes its answer, in one Logic's kept openers."""
    logic, settings = kept_logic(), Settings(3, "hard", {}, seed_difficulty=3)
    doc = plan_doc(fill.fill(logic, "1", settings), logic.db)
    randomizer.openers_ahead(doc)
    assert kept_logic() is logic      # their keep is a memo: it doesn't make the View read a new Logic
    monkeypatch.setattr(Logic, "reach", lambda *_, **__: pytest.fail("a reach the job ahead already made"))
    assert difficulty.openers(logic, settings, load_plan(doc, logic.db).placement)


def test_a_shaped_plans_first_tracker_view_compiles_no_option_set_the_trackers_work_ahead_compiled(monkeypatch):
    """The app's server compiles what a seed's first view reaches under while its engine fills (``tracking.ahead``),
    as those compiles were most of a Hard plan's view after its click: the view, of a tracker built anew, compiles
    none."""
    from azurkit.tools.randomizer.planner import solver

    logic, settings = kept_logic(), Settings(3, "hard", {}, seed_difficulty=3)
    doc = plan_doc(fill.fill(logic, "1", settings), logic.db)
    tracking.world()   # once a process, before any view (the tracker tab's own)
    for memo, empty in (("_native", {}), ("_compiled", {}), ("_KEPT", collections.OrderedDict())):
        monkeypatch.setattr(tracking if memo == "_KEPT" else logic, memo, empty)
    tracking.ahead(load_plan(doc, logic.db).settings)
    made, init = [], solver._Rules.__init__
    monkeypatch.setattr(solver._Rules, "__init__", lambda self, *a, **k: made.append(a) or init(self, *a, **k))
    assert tracking.view({"plan": doc})["head"]["difficulty"]["level"] == "Expert" and made == []


def test_the_trackers_work_ahead_waits_for_a_logic_its_process_read_and_never_reads_it(monkeypatch):
    """Its 87.6 MB read at low priority held the app server's GIL from the calls a launch and a Build wait on (Step
    4.4ci56's first A/B: A02 to 9.2 s, A80's median 1.58 -> 2.77 s): it waits until a call has read it, or it stops."""
    asked = iter([False, False, True])
    monkeypatch.setattr(loader, "logic_read", lambda root=loader.DATA_DIR: False)
    monkeypatch.setattr(randomizer, "kept_logic", lambda *_: pytest.fail("the logic read by work ahead"))
    randomizer.tracker_ahead({"seed": "1"}, lambda: next(asked))
    assert next(asked, None) is None


def test_a_shaped_fills_attempts_at_once_follow_its_priority_and_a_cancel_stops_them_at_their_next_note(monkeypatch):
    """A click raises a job ahead's fill: its threads too. A change stops it: they end there, not at a batch's end.
    Each attempt's kernel beside the fill waits until the fill's first note after the click, so no attempt ends
    before the click and the fill waits (and notes) until its threads have heard it: no race on two clocks."""
    from azurkit.app import procpool

    class Gone(Exception):
        pass

    lowered, heard, after = [True], [], threading.Event()

    def report(_step: dict) -> None:
        if (False, True) in {(on, name.startswith("azurkit-attempt")) for on, name in heard}:
            after.set()            # what still waits ends at its next note
            raise Gone             # the change
        if not lowered[0]:
            after.set()            # a note after the click: the threads go on, at the fill's priority now
        elif any((True, name) in heard for name in attempts()):
            lowered[0] = False     # the click

    def attempts() -> set[str]:
        return {t.name for t in threading.enumerate() if t.name.startswith("azurkit-attempt")}

    def low():
        name = threading.current_thread().name
        return lambda on: heard.append((on, name))

    def held(*a):
        if threading.current_thread().name.startswith("azurkit-attempt"):
            assert after.wait(60), "an attempt waited 60 s for the click"   # a deadlock guard only
        return kernel(*a)

    monkeypatch.setattr(fill, "WIDTH", 4)
    monkeypatch.setattr(fill, "BESIDE", procpool.Beside)
    monkeypatch.setattr(procpool, "lowered", lambda: lowered[0])
    monkeypatch.setattr(procpool, "Low", low)
    kernel = native.attempt
    monkeypatch.setattr(native, "attempt", held)
    with pytest.raises(Gone), progress.noting(progress.Steps(report)) as steps:
        steps("plan")
        fill._fill(kept_logic(), "31", Settings(3, "hard", {}, frozenset({"fragments"}), seed_difficulty=3))
    after.set()
    for thread in threading.enumerate():
        if thread.name.startswith("azurkit-attempt"):
            thread.join(5)
    assert not attempts()


def test_a_beside_job_hears_the_priority_its_fill_took_between_two_waits(monkeypatch):
    """A Build clicked while a Hard seed is planned ahead raises the fill at its next note, which may be a
    candidate's, between two waits that never time out: what it hands out next runs at its new priority, not at
    background priority to the fill's end."""
    from azurkit.app import procpool

    lowered, heard = [True], []
    monkeypatch.setattr(procpool, "lowered", lambda: lowered[0])
    monkeypatch.setattr(procpool, "Low", lambda: heard.append)
    with procpool.Beside(1, lambda: None) as beside:
        beside.answer(beside.submit(lambda _: None, 0))
        lowered[0] = False         # the click, at a note between two answers
        beside.answer(beside.submit(lambda _: None, 1))
    assert heard == [True, False]


def test_a_logic_handed_another_database_works_its_openers_out_again(monkeypatch):
    """As the kept fill does (``loader.kept_logic``'s stated way to hand a Logic another database)."""
    logic, settings = kept_logic(), Settings(3, "hard", {}, seed_difficulty=3)
    placement = fill.fill(logic, "1", settings).placement
    first = difficulty.openers(logic, settings, placement)
    monkeypatch.setattr(logic, "db", dataclasses.replace(logic.db))
    again = difficulty.openers(logic, settings, placement)
    assert again == first and again is not first


def test_a_shaped_plans_openers_read_one_switchable_option_set_a_tier_each_mix_the_settings_own_answer(monkeypatch):
    """Each removal is a reach of the settings' switchable set (``off``), the answer of the settings with those picks
    off; a seed with a "one of" round compiled about 70 option sets for its openers (4-5 s at the spoiler's View, A75),
    now at most one a tier, and the answer is the same (seed 2's below)."""
    from azurkit.tools.randomizer.planner import solver

    logic, st = kept_logic(), Settings(3, "hard", {}, seed_difficulty=3)
    placement = fill.fill(logic, "7", st).placement     # its openers hold a "one of" round
    on = picks_on(st, logic.skip_tables)
    for pid in list(on)[::4]:
        alone = dataclasses.replace(st, skip_override={pid: False})
        assert logic.reach(st, placement, traps=False, off=on[pid]).locations \
            == logic.reach(alone, placement, traps=False).locations, pid
    made, init = [], solver._Rules.__init__
    monkeypatch.setattr(solver._Rules, "__init__", lambda self, *a, **k: made.append(a) or init(self, *a, **k))
    assert any(o["one_of"] for o in difficulty.openers(logic, st, placement)) and len(made) <= 4


def test_the_openers_ahead_wait_out_a_plan_in_flight_so_a_tracks_fill_has_the_gil(monkeypatch):
    from azurkit.app import engine

    doc = {"settings": {"seed_difficulty": 3}}
    planning, noted = threading.Event(), threading.Event()

    def work(_doc):
        assert planning.wait(30)
        progress.note("reading")
        noted.set()

    def plan(*_, **__):
        planning.set()
        assert not noted.wait(1)   # a note in flight doesn't return while this plan runs
        return dict(doc)           # the same plan, another object: its openers aren't stale

    monkeypatch.setattr(randomizer, "openers_ahead", work)
    monkeypatch.setattr(engine.sdk, "plan", plan)
    monkeypatch.setattr(engine, "_NEWEST", [doc])
    ahead = threading.Thread(target=engine._openers_ahead, args=(doc,), daemon=True)
    ahead.start()
    engine._plan({})
    ahead.join(30)
    assert noted.is_set()


def test_a_plan_with_another_answer_ends_the_openers_ahead_of_the_last_and_keeps_what_they_compiled_for_the_drop(monkeypatch):
    """Engine's: each change's plan left a thread no stop reached; a stale one could run last and evict the newest's.
    The fresh plan lands while the stale one's openers hold their first compile, on a Logic's memos of the test's own: a
    test before it in the process may have kept that plan's openers (the tracker server's spoiler plans it too), and
    then they end at once, before a look at the threads could find them (1.0.1's gate). Let go, the stale ones' work
    never returns: their next note ends them, so a stale thread the engine doesn't end fails, however the two race."""
    from azurkit.app import engine
    from azurkit.tools.randomizer.planner import solver

    logic, off = kept_logic(), {"a6.rjump_platforms": False}
    for memo, empty in (("_compiled", {}), ("_native", {}), ("_opener_sets", None)):
        monkeypatch.setattr(logic, memo, empty, raising=False)
    plans = [plan_doc(fill.fill(logic, "1", settings), logic.db)
             for settings in (Settings(3, "hard", {}, seed_difficulty=3), Settings(3, "hard", off, seed_difficulty=3))]
    answered = iter(plans)
    monkeypatch.setattr(engine.sdk, "plan", lambda *_, **__: next(answered))
    monkeypatch.setattr(engine, "_NEWEST", [None])
    compiling, planned, init = threading.Event(), threading.Event(), solver._Rules.__init__
    ended, work = [], difficulty._worked_out

    def compiled(self, *args, **kwargs) -> None:
        init(self, *args, **kwargs)
        if self.switchable and threading.current_thread().name == "azurkit-openers" and not compiling.is_set():
            compiling.set()
            planned.wait(60)   # the stale plan's openers at work until the fresh plan is made

    def worked_out(*args) -> list[dict]:
        got = work(*args)
        ended.append(threading.current_thread())
        return got

    monkeypatch.setattr(solver._Rules, "__init__", compiled)
    monkeypatch.setattr(difficulty, "_worked_out", worked_out)

    def running() -> list[threading.Thread]:
        return [t for t in threading.enumerate() if t.name == "azurkit-openers"]

    try:
        stale = engine._plan({})
        assert compiling.wait(60)
        first = running()
        fresh = engine._plan({})
    finally:
        planned.set()
    assert stale is plans[0] and fresh is plans[1] and len(first) == 1
    first[0].join(120)
    assert not first[0].is_alive()
    for thread in running():
        thread.join(120)
    assert first[0] not in ended and len(ended) == 1   # the stale ones' next note ended them; the fresh ones answered
    held = logic._opener_sets
    assert dict(held[0][2]) == off and held[3][0][1] == tuple(sorted(load_plan(fresh, logic.db).placement.items()))


def test_a_step_up_a_pick_or_the_movement_tier_opens_names_only_that_pick_and_the_tier():
    """Expert at Hard/Hard, seed 2's last step-up opens with Hard movement and no pick, or with the tier lowered by one
    pick: its "one of" names those two, not every pick rated high enough, and the spoiler's line names them short."""
    logic = kept_logic()
    st = Settings(3, "hard", {}, seed_difficulty=3)
    opened = difficulty.openers(logic, st, fill.fill(logic, "2", st).placement)
    assert opened[-1] == {"picks": ["f6.mound_climb_air1 (Hard)", difficulty.MOVEMENT], "one_of": True}
    assert difficulty.needs(logic, st, opened)[-1] == ["one of Air flutter or Hard movement"]


@pytest.mark.web
def test_a_shaped_plan_is_the_same_under_pyodide(pyodide):
    """Under Pyodide, by the compiled reach's side module, an Expert plan is the one CPython makes."""
    assert pyodide(python=_SHAPED_UNDER_PYODIDE)["sha12"] == LEVELED["Expert"][0].split()[1]


_SHAPED_UNDER_PYODIDE = """
import json
from azurkit.tools.randomizer import plan
json.dumps({"sha12": plan({"seed": "0", "settings": {
    "format": "azurik-rando-settings/2", "skip_ceiling": 3, "movement_tier": "hard", "dark_fire": 1,
    "seed_difficulty": "Expert", "exclude_categories": [], "skip_override": {}}})["sha256"][:12]})
"""


def test_seed_difficulty_rides_strings_and_files_and_v1_levels_load_at_the_nearest():
    """D1157: share version 4 round trips Easy, Hard and Expert at any settings (Safe movement and no skip too), with
    toggles, sliders and none, its literal category mask through a plan file, and :func:`share_sliders` reads its
    sliders; versions 0-3 decode to Normal and encode as before. A file names the level, only above Normal. v1.0.0's
    levels (a fill 1 byte, a file's or a plan file's integer) load at the nearest one now, Standard as Hard, Hard and
    Frame-perfect as Expert, a string canonical against its own byte and the tab saying so; a byte of another fill or
    level, a plan of another fill and a file's 1, "2", true or "Medium" are refused by name."""
    logic = kept_logic()
    skips = {sid: s for sid, (_, s) in logic.db.skips.items()}
    pick = next(p for p, ids in picks(skips).items() if turnable(skips[ids[0]]) and skips[ids[0]]["difficulty"] == 2)
    for level in (1, 2, 3):
        for st in (Settings(4, "frame_perfect", {pick: True}, seed_difficulty=level, sliders=JUMP),
                   Settings(0, "safe", {}, seed_difficulty=level)):
            text = share_encode(st, skips)
            assert base64.b32decode(text[4:] + "=" * (-len(text[4:]) % 8))[0] == 4
            assert share_decode(text, skips) == st and share_sliders(text, skips) == st.sliders
    for kept in ({"powers", "upgrades"}, {"powers"}, {"upgrades"}):
        st = Settings(3, "hard", {}, frozenset(kept), seed_difficulty=2)
        assert share_decode(share_encode(st, skips), skips) == st
        back = load_plan(plan_doc(fill.Fill("1", st, 0, {}), logic.db), logic.db).settings
        assert back.exclude_categories == kept and back.seed_difficulty == 2
    assert share_encode(logic.db.defaults, skips) == "AZR-AAEA"
    for old in ("AZR-AAEA", _share(JUMP), share_encode(Settings(3, "hard", {}, frozenset({"powers"})), skips)):
        assert share_decode(old, skips).seed_difficulty == 0
        assert share_encode(share_decode(old, skips), skips) == old

    def raw(last: int, head: int = 0x13) -> str:   # hard, ceiling 3
        return "AZR-" + base64.b32encode(bytes([4, head, 0, 0, last])).decode().rstrip("=")

    for old, level in ((2, 2), (3, 3), (4, 3)):   # v1.0.0's Standard, Hard, Frame-perfect
        told = []
        assert share_decode(raw(1 << 3 | old), skips, told).seed_difficulty == level and told == [old]
    assert sdk.randomizer_settings({"share": raw(1 << 3 | 2)})["note"].startswith(
        "Made with the older Seed difficulty Standard: it loads as Hard, the nearest level now")
    for text, why in ((raw(2 << 3), "seed difficulty 0 is not"), (raw(2 << 3 | 5), "seed difficulty 5 is not"),
                      (raw(1 << 3 | 1), "fill 1; this AzurKit plans with fill 2"),
                      (raw(3 << 3 | 3), "fill 3; this AzurKit plans with fill 2")):
        with pytest.raises(ValueError, match=why):
            share_decode(text, skips)
    doc = plan_doc(fill.Fill("1", Settings(3, "hard", {}, seed_difficulty=3), 0, {}), logic.db)
    assert doc["settings"]["seed_difficulty"] == "Expert" and doc["settings"]["seed_difficulty_fill"] == 2

    def edited(**settings) -> dict:
        body = {k: v for k, v in doc.items() if k != "sha256"} | {"settings": doc["settings"] | settings}
        return body | {"sha256": hashlib.sha256(fill.canonical(body)).hexdigest()}
    with pytest.raises(PlanError, match="fill 1; this AzurKit plans with fill 2"):
        load_plan(edited(seed_difficulty_fill=1), logic.db)
    assert load_plan(edited(seed_difficulty=4, seed_difficulty_fill=1), logic.db).settings.seed_difficulty == 3

    table = {"format": "azurik-rando-settings/1", "skip_ceiling": 0, "movement_tier": "safe", "dark_fire": 1}
    assert settings_from_table(table, skips).seed_difficulty == 0
    assert "seed_difficulty" not in layer.settings_text(settings_from_table(table, skips))
    assert "seed_difficulty" not in layer.settings_doc(settings_from_table(table | {"seed_difficulty": "Normal"}, skips))
    for level, name in enumerate(("Easy", "Hard", "Expert"), 1):
        st = settings_from_table(table | {"seed_difficulty": name}, skips)
        assert st.seed_difficulty == level and f'seed_difficulty = "{name}"\n' in layer.settings_text(st)
        assert settings_from_table(tomllib.loads(layer.settings_text(st)), skips) == st
    for old, level in ((0, 0), (2, 2), (3, 3), (4, 3)):
        told = []
        assert settings_from_table(table | {"seed_difficulty": old}, skips, told=told).seed_difficulty == level
        assert told == ([old] if old else [])
    text = layer.settings_text(settings_from_table(table, skips)).replace("exclude", "seed_difficulty = 3\nexclude")
    note = sdk.randomizer_settings({"file": text})["note"]
    assert note.startswith("Made with the older Seed difficulty Hard: it loads as Expert")
    for level, why in ((1, "1 is not one of"), ("2", "'2' is not one of"), (True, "True is not one of"),
                       ("Medium", "'Medium' is not one of Normal, Easy, Hard, Expert")):
        with pytest.raises(ValueError, match=why):
            settings_from_table(table | {"seed_difficulty": level}, skips)


def test_the_save_warp_counted_frees_the_traps_a_save_platform_leaves_and_rides_in_its_share_string_and_build():
    """D1154 (RANDOMIZER_PLAN R2.14): the warp's sources are the shim's 41 rows, every save point but town's, each
    with a node an edge to town's platform's (the five with none get no edge); it changes no flag forced on entry and
    no region. Counted, the vanilla placement's a3 and a5 platform rooms are no traps; a plan of it verifies, names
    it in its spoiler and reads back; share version 5 and a file carry it (written only when on), its options byte
    refused when unknown; a build applying qol_save_warp plans with it, settings counting it without the pack are
    refused, and the tracker reads it. Off, plans are as before (the goldens; the eighty plans' test). D169 holds
    under it: the warp gives power_water's hose-pool spot a way out at water 0, so, a term of its route mark's
    unless (AZ-725), counted it holds that spot for water alone below the firewall skip's ceiling."""
    logic = kept_logic()
    skips = {sid: s for sid, (_, s) in logic.db.skips.items()}
    shim = (Path(mods.__file__).parent / "shims" / "qol_save_warp.c").read_text(encoding="utf-8")
    rows = re.findall(r'\{"levels/(?:\w+/)?(\w+)", "(\w+)"\}', shim.split("ROWS[][2]")[1].split("};")[0])
    saves = {(lvl, name): node for lvl, name, node in solver.save_points(logic.db).values()}
    assert len(rows) == 41 and set(saves) - set(rows) == {solver.WARP_TOWN} and set(rows) <= set(saves)
    town = saves[solver.WARP_TOWN]
    assert logic.warps == tuple(sorted({(saves[r], town) for r in rows if saves[r]}))
    assert sum(saves[r] is None for r in rows) == 5
    warp = dataclasses.replace(solver.TRICK_FREE, save_warp=True)
    assert logic._forced_on_entry(logic.rules(warp)) == logic.forced and logic._regions(logic.rules(warp)) == logic.regions
    assert logic._forced_on_entry(logic.rules(warp, physical=True)) == logic.forced_phys
    on = dataclasses.replace(logic.db.defaults, save_warp=True)
    vanilla = logic.vanilla_placement()
    assert {"a3_z002", "a5_z021"} <= logic.reach(logic.db.defaults, vanilla).traps - logic.reach(on, vanilla).traps
    pool, pv = "w2/g0/r1346", logic.location_rows["w2/g0/r1346"]["proven"]
    _, kin, kout = logic.route_walks({pool})[pool]
    lenient = dataclasses.replace(logic.without(pv["unless"]), save_warp=True)
    assert "holding water 0" in logic.kit_short(pool, kin, kout, lenient)[1]
    slots = fill._Slots(logic, dataclasses.replace(on, skip_ceiling=2))
    assert slots.holds(pool, "power_water") and not slots.holds(pool, "power_earth")

    table ={"format": "azurik-rando-settings/1", "skip_ceiling": 0, "movement_tier": "standard", "dark_fire": 1}
    doc = randomizer.plan({"seed": "2", "settings": table | {"save_warp": True}})
    plan = load_plan(doc, logic.db)
    assert doc["settings"]["save_warp"] is True and plan.settings == on and not fill.verify(logic, on, plan.placement)
    assert any(line.startswith("the save-point warp is counted") for line in randomizer.spoiler(doc))
    assert tracking.tracker_of(doc).settings.save_warp
    pick = next(p for p, ids in picks(skips).items() if turnable(skips[ids[0]]) and skips[ids[0]]["difficulty"] == 2)
    for st in (on, Settings(4, "frame_perfect", {pick: True}, frozenset({"powers"}), JUMP, 3, True)):
        text = share_encode(st, skips)
        assert base64.b32decode(text[4:] + "=" * (-len(text[4:]) % 8))[0] == 5 and share_decode(text, skips) == st
    bad = "AZR-" + base64.b32encode(bytes([5, 0x08, 0, 0, 0, 2])).decode().rstrip("=")
    with pytest.raises(ValueError, match="an option this AzurKit doesn't know"):
        share_decode(bad, skips)
    assert "save_warp" not in layer.settings_text(logic.db.defaults) and "save_warp" not in PLANS["default"]["plan"]["settings"]
    assert settings_from_table(tomllib.loads(layer.settings_text(on)), skips) == on
    with pytest.raises(ValueError, match="save_warp: 1 is not true or false"):
        settings_from_table(table | {"save_warp": 1}, skips)
    built = generator.prepare({"seed": "2"}, {generator.WARP_PACK: {}})
    assert built.plan.settings.save_warp and built.plan.doc["sha256"] == doc["sha256"]
    with pytest.raises(ValueError, match="doesn't apply qol_save_warp"):
        generator.prepare({"seed": "2", "share": doc["share"]}, {})
    with pytest.raises(ValueError, match="the plan's settings count the save-point warp"):
        generator.prepare({"plan": doc}, {})
    assert generator.prepare({"plan": doc}, {generator.WARP_PACK: {}}).recipe == {"plan": doc}


def _share(sliders: dict) -> str:
    skips = {sid: s for sid, (_, s) in kept_logic().db.skips.items()}
    return share_encode(Settings(0, "standard", {}, sliders=sliders), skips)


def test_seed_2s_plan_under_each_profile_is_its_goldens_and_the_default_plan_file_byte_for_byte(capsys, tmp_path):
    """Each profile's attempt, plan sha256 and spoiler file's sha256; the
    CLI's plan at the database's defaults (the default profile's) and its
    spoiler of that file, byte for byte."""
    cases = record_goldens.cases(record_goldens.PLANS)
    assert sorted(cases) == ["default", "max", "strict"] and {c["seed"] for c in cases.values()} == {"2"}
    for name in cases:
        doc, lines = _profile(name), sdk.spoiler(_profile(name))["lines"]
        assert (doc["attempt"], doc["sha256"], hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()) == (
            PLANS[name]["attempt"], PLANS[name]["sha256"], PLANS[name]["spoiler"]), name
    assert cli.main(["plan", "--seed", "2"]) == 0        # the database's defaults are the default profile's
    assert capsys.readouterr().out == DEFAULT_PLAN
    (tmp_path / "plan.json").write_text(DEFAULT_PLAN, encoding="utf-8")
    assert cli.main(["spoiler", str(tmp_path / "plan.json")]) == 0
    assert hashlib.sha256(capsys.readouterr().out.encode()).hexdigest() == PLANS["default"]["spoiler"]


def test_a_plan_reads_back_into_its_spoiler_and_what_the_randomizer_cant_take_is_refused_by_name(tmp_path, capsys):
    """The default plan's spoiler names its share string and each sphere;
    an edited plan, a recipe with both settings and a share string, a build
    recipe's unknown key, settings with a share string, or an obsidian cost
    whose thresholds a float32 can't hold are refused, each by name. A build
    recipe's plan file (Modkit's ``randomize-full --plan``, P31) carries its
    own seed and settings, and one edited, from another database, typed
    otherwise or not beatable under its settings (its sha256 made again:
    anyone can) is refused by name before any image is read, as ``build
    --plan`` with ``--seed``, or a file that isn't JSON, is."""
    lines = sdk.spoiler(PLANS["default"]["plan"])["lines"]
    assert any(PLANS["default"]["plan"]["share"] in line for line in lines)
    assert any(line.lower().startswith("sphere") for line in lines)
    edited = PLANS["default"]["plan"] | {"seed": "3"}
    with pytest.raises(ValueError, match="edited plan"):
        sdk.spoiler(edited)
    with pytest.raises(ValueError, match="settings and share both"):
        sdk.plan({"seed": "2", "settings": {}, "share": "AZR-AAEA"})

    def signed(doc):
        body = {k: v for k, v in doc.items() if k != "sha256"}
        return body | {"sha256": hashlib.sha256(fill.canonical(body)).hexdigest()}
    doc = PLANS["default"]["plan"]
    fragment = next(lid for lid, item in doc["placement"].items() if item.startswith("frag"))
    unbeatable = signed(doc | {"placement": doc["placement"] | {fragment: "obsidian"}})
    for given, why in (({"seed": "2", "plan": doc}, "a plan carries its own seed and settings, so it takes no seed$"),
                       ({"plan": "plan.json"}, "plan is a plan file's object"), ({"plan": edited}, "edited plan"),
                       ({"plan": signed(doc | {"db_digest": "0" * 64})}, "made from another database"),
                       ({"plan": signed(doc | {"placement": [fragment]})}, "its placement maps location ids to items"),
                       ({"plan": signed(doc | {"settings": []})}, "its settings a table"),
                       ({"plan": signed(doc | {"db_digest": 5})}, "its share and db_digest are strings"),
                       ({"plan": unbeatable}, fr"^plan {unbeatable['sha256'][:12]} isn't beatable under its settings: "
                                              r"victory \(flag:d1\.spideyzar\.killed\) does not hold; \d+ locations"),
                       ({"seed": 2}, "seed is a string"),
                       ({"seed": "2", "settings": {}, "share": "AZR-AAEA"}, "settings and share both"),
                       ({"seed": "2", "obsidian_cost": math.nan}, "obsidian_cost nan"),
                       ({"seed": "2", "obsidian_cost": 1e38}, "finite float32s")):
        with pytest.raises(ValueError, match=why):
            sdk.image({"iso": "x.iso", "randomizer": given})
    (tmp_path / "plan.json").write_text(DEFAULT_PLAN, encoding="utf-8")
    (tmp_path / "settings.toml").write_text("skip_ceiling = 0\n", encoding="utf-8")
    capsys.readouterr()
    for flags, said in ((["--plan", str(tmp_path / "plan.json"), "--seed", "2"],
                         "randomizer: a plan carries its own seed and settings, so it takes no seed"),
                        (["--plan", str(tmp_path / "settings.toml")],
                         f"--plan {tmp_path / 'settings.toml'}: not a plan file (not JSON: Expecting value")):
        assert cli.main(["build", "--iso", "x.iso", "--out", str(tmp_path / "out.iso"), *flags]) == 1
        assert capsys.readouterr().err.startswith(f"azurkit: {said}")


def test_a_randomized_builds_spoiler_and_settings_file_are_written_beside_it_or_refused_by_name(tmp_path, capsys,
                                                                                                monkeypatch):
    """Step 4.24a (Modkit's ``randomize-full --spoiler`` and ``--save-settings``): ``azurkit build`` writes the
    build's spoiler (its report's) and its settings as the app's Save settings writes them
    (``randomizer.settings_file``), which load back to its settings; each is refused by name before the build when
    the build isn't randomized, or the file is the output, an input or the other's file; one not written keeps no
    image (D35)."""
    plan, out = PLANS["default"]["plan"], tmp_path / "out.iso"
    built = {"layers": [], "conflicts": [], "out": str(out), "label": "USA", "size": 1, "sha256": "0" * 64,
             "spoiler": "the spoiler\n", "randomizer": {"seed": "2", "share": plan["share"], "plan": plan["sha256"],
                                                        "settings": plan["settings"], "logic_verified": True,
                                                        "conflicts": [], "why_not": []}}

    def build(made, target, picked=None):
        Path(target).write_bytes(b"image")
        return built
    monkeypatch.setattr(sdk, "build", build)
    spoiler, settings, iso_ = tmp_path / "spoiler.txt", tmp_path / "settings.toml", str(tmp_path / "in.iso")
    base = ["build", "--iso", iso_, "--out", str(out), "--seed", "2"]
    assert cli.main([*base, "--spoiler", str(spoiler), "--save-settings", str(settings)]) == 0
    assert capsys.readouterr().out.splitlines()[-2:] == [f"spoiler: {spoiler}", f"settings file: {settings}"]
    text = settings.read_text(encoding="utf-8")
    assert spoiler.read_text(encoding="utf-8") == "the spoiler\n" and text == randomizer.settings_file(plan["settings"])
    assert layer.settings_doc(randomizer.settings_from_table(tomllib.loads(text), randomizer._skips(), "x")) == \
           layer.settings_doc(randomizer.settings_from_table(plan["settings"], randomizer._skips(), "x"))
    for flags, why in (
            (["--iso", iso_, "--out", str(out), "--spoiler", str(spoiler)],
             "--spoiler: a randomized build's files: give --seed or --plan"),
            ([*base[1:], "--spoiler", str(out), "--save-settings", iso_],
             f"--spoiler {out}: it is the image it writes (--out); --save-settings {iso_}: it is the image it reads "
             "(--iso)"),
            ([*base[1:], "--spoiler", str(spoiler), "--save-settings", str(spoiler)],
             f"--spoiler and --save-settings name the same file ({spoiler})")):
        out.unlink(missing_ok=True)
        assert cli.main(["build", *flags]) == 1 and not out.exists()
        assert capsys.readouterr().err == f"azurkit: {why}\n"
    monkeypatch.setattr(randomizer, "settings_file", lambda table: (_ for _ in ()).throw(ValueError("no settings")))
    spoiler.unlink()
    assert cli.main([*base, "--spoiler", str(spoiler), "--save-settings", str(settings)]) == 1
    assert capsys.readouterr().err == "azurkit: no settings\n" and not out.exists() and not spoiler.exists()


def test_the_tab_reads_its_settings_and_share_strings_flags_what_a_build_leaves_unverified_and_a_link_carries_it(
        monkeypatch):
    """Step 4.2c1: the Randomizer tab starts at D144's defaults (the
    database's), whose share string is Modkit's; the settings it holds
    (format /2: each category as it is) give back the same settings and a
    share string that decodes to them, each skip a setting can turn on (by
    pick, D275) with the ceiling's state and its toggle, and the picks held.
    A share string made with other movement sliders is named; keeping the
    obsidians vanilla is the preflight's refusal (AZ-454), a plan's too,
    in plain words naming the row whose tick is enough and the other way,
    the progression items' rows unticked too, which plans (Step 4.4u1); a roll slider
    the logic doesn't model and an obsidian cost above vanilla's leave a
    build unverified (D83(c)). A share link carries the randomizer and a
    page's remembered setup keeps it (D915), each refused by name when a
    setting is. Step 4.2c2: each item row counts what the base game places
    (Modkit 3befd6336's ``rando_view.base_counts``, the step's evidence);
    every skip of the database has its D258 group (a new one needs its
    group, Modkit's ``SKIP_GROUP``); the tab's settings file (D144's Save
    settings) loads back to its settings, and a file that isn't one is
    refused by name. A plan file (Open a plan…, P31) gives its own settings
    and the build's flags on them: a roll a skip it has on was proven at,
    and (Modkit's ``plan_for``) each problem its placement has at the tier
    the build's movement sliders pick, when they aren't the plan's; a link
    carries it whole."""
    logic = kept_logic()
    skips = {sid: s for sid, (_, s) in logic.db.skips.items()}
    options = sdk.catalog()["randomizer"]
    assert options["defaults"] == randomizer.literal(logic.db.defaults)
    assert [row[3] for row in options["items"]] == [20, 12, 8, 39, 1215, 100, 22, 34, 42, 23, 3, 6]
    assert set(randomizer.SKIP_GROUP) == set(skips) and set(randomizer.SKIP_GROUP.values()) == set(randomizer.SKIP_GROUPS)
    saved = sdk.randomizer_settings({"settings": options["defaults"] | {"skip_ceiling": 3}})
    assert sdk.randomizer_settings({"file": saved["file"]})["settings"] == saved["settings"]
    with pytest.raises(ValueError, match="settings file: not TOML"):
        sdk.randomizer_settings({"file": "skip_ceiling = ["})
    view = sdk.randomizer_settings({"settings": options["defaults"]})
    assert (view["settings"], view["share"], view["preflight"], view["why_not"], view["note"]) == (
        options["defaults"], share_encode(logic.db.defaults, skips), None, [], None)
    pick = view["skips"][0]["id"]
    every = picks(skips)
    assert [s["id"] for s in view["skips"]] == [p for p, ids in every.items() if any(turnable(skips[v]) for v in ids)]
    assert view["held"] == len(every) - len(view["skips"]) and not any(s["ceiling"] for s in view["skips"])
    given = options["defaults"] | {"skip_ceiling": 3, "exclude_categories": ["powers"], "skip_override": {pick: True}}
    view = sdk.randomizer_settings({"settings": given})
    assert view["settings"] == given and next(s for s in view["skips"] if s["id"] == pick)["toggle"] is True
    assert share_decode(view["share"], skips) == settings_from_table(given, skips)
    assert sdk.randomizer_settings({"share": view["share"]})["settings"] == given
    assert sdk.randomizer_settings({"share": _share(JUMP)})["note"].startswith(
        "the share string was made with the movement sliders player_physics jump_speed_scale 1.3")
    starved = options["defaults"] | {"exclude_categories": ["obsidians"]}   # 32 of the 40 proven spots are theirs
    view = sdk.randomizer_settings({"settings": starved})
    assert (view["preflight"], view["preflight_tick"]) == (
        "keeping obsidians vanilla leaves 8 spots for the 27 disc fragments and elemental powers, which go only on "
        "spots whose way there and back is proven; of the 40 such spots, 32 hold obsidians. Tick Obsidians, or "
        "untick Disc fragments and Elemental powers too", "Tick Obsidians")
    with pytest.raises(ValueError, match=f"^no plan: {re.escape(view['preflight'])}$"):
        sdk.plan({"seed": "2", "settings": starved})
    both = options["defaults"] | {"exclude_categories": ["fragments", "obsidians"]}   # its tick names the one enough
    assert sdk.randomizer_settings({"settings": both})["preflight"].endswith(
        "32 hold obsidians and 5 hold disc fragments. Tick Obsidians, or untick Elemental powers too")
    other = options["defaults"] | {"exclude_categories": ["fragments", "powers", "obsidians"]}   # nothing to place
    assert sdk.randomizer_settings({"settings": other})["preflight"] is None and sdk.plan({"seed": "2", "settings": other})
    flagged = sdk.randomizer_settings({"settings": options["defaults"], "obsidian_cost": 20,
                                       "packs": {"player_physics": {"roll_speed_scale": 0.5}}})["why_not"]
    assert flagged == [*generator.movement_reasons({"player_physics": {"roll_speed_scale": 0.5}},
                                                   sdk.catalog()["packs"]), layer.obsidian_reason(20.0)]
    doc, roll = _profile("max"), {"player_physics": {"roll_speed_scale": 0.5}}
    planned, plan = sdk.randomizer_settings({"plan": doc, "packs": roll}), layer.checked_plan(doc, logic)
    rolled = layer.roll_reasons(plan.asked, logic.db, generator.sliders(roll))
    assert rolled and (planned["settings"], planned["why_not"]) == (
        randomizer.literal(plan.asked), [*generator.movement_reasons(roll, sdk.catalog()["packs"]), *rolled])
    with pytest.raises(ValueError, match="give settings, share, file or plan"):
        sdk.randomizer_settings({"plan": doc, "share": "AZR-AAEA"})
    assert sdk.read_mods(sdk.preset_encode({"packs": {}, "randomizer": {"plan": doc}}))["randomizer"] == {"plan": doc}
    monkeypatch.setattr(fill, "verify", lambda lg, st, placement, known=None: ["x"] * (st.movement_tier == "safe"))
    assert layer.plan_reasons(plan, logic, generator.sliders({"player_physics": {"jump_speed_scale": 0.5}})) == [
        "the plan verifies at the movement it was planned for but not at this build's: x"]
    monkeypatch.undo()

    rando = {"seed": "2", "settings": given, "obsidian_cost": 20.0}
    found = sdk.preset_decode(sdk.preset_encode({"packs": {}, "randomizer": rando}))
    assert found["layers"][0] == {"tool": "randomizer", "kind": "plan", "recipe": rando}
    assert sdk.read_mods(sdk.preset_encode({"packs": {}, "randomizer": rando}))["randomizer"] == rando
    kept = {"on": True, "seed": "2", "settings": given, "obsidian_cost": 20.0}
    assert sdk.restore({"ticked": [], "randomizer": kept})["randomizer"] == kept
    bad = given | {"dark_fire": 2}
    for refused in (lambda: sdk.preset_encode({"packs": {}, "randomizer": {"seed": "2", "settings": bad}}),
                    lambda: sdk.randomizer_settings({"settings": bad})):
        with pytest.raises(ValueError, match="dark_fire: 2: dark areas always need Fire 1 now"):
            refused()
    assert sdk.restore({"ticked": [], "randomizer": kept | {"settings": bad}})["dropped"] == [
        "the randomizer's settings (settings: dark_fire: 2: dark areas always need Fire 1 now; this seed can't be remade)"]


def test_dark_areas_always_need_fire_1_so_an_old_fire_2_or_3_is_refused_by_name():
    """D1061: the option is gone, its key stays at 1 in every table (every seed's digest holds it). A settings table, a
    share string or a plan file made at Fire 2 or 3 is refused by name: read as Fire 1 it would give another seed under
    the same string. A dark area needs Fire 1 unless its own nolight skip is on."""
    logic = kept_logic()
    skips = logic.skip_tables
    assert fill.settings_table(logic.db.defaults)["dark_fire"] == 1 and share_encode(logic.db.defaults, skips) == "AZR-AAEA"
    table = fill.settings_table(logic.db.defaults)
    for fire, share in ((2, "AZR-AAUA"), (3, "AZR-ABEA")):
        with pytest.raises(ValueError, match=f"dark_fire: {fire}: dark areas always need Fire 1 now"):
            settings_from_table(table | {"dark_fire": fire}, skips)
        with pytest.raises(ValueError, match=f"dark_fire: {fire}: dark areas always need Fire 1 now"):
            share_decode(share, skips)
    doc = sdk.plan({"seed": "2"})
    old = {**doc, "settings": {**doc["settings"], "dark_fire": 2}}
    old["sha256"] = hashlib.sha256(fill.canonical({k: v for k, v in old.items() if k != "sha256"})).hexdigest()
    with pytest.raises(PlanError, match="dark_fire: 2: dark areas always need Fire 1 now"):
        load_plan(old, logic.db)
    dark = next(n for n in logic.db.nodes if logic.db.nodes[n][1].get("dark") == "e7.dark_room_nolight")
    for override, fire, lit in (({}, 0, False), ({}, 1, True), ({"e7.dark_room_nolight": True}, 0, True)):
        rule = logic.rules(dataclasses.replace(logic.db.defaults, skip_override=override)).light_at(dark)
        assert rule({"fire": fire}, frozenset()) is lit, (override, fire)


def test_the_tab_folds_the_worn_bodys_size_in_as_its_build_does_so_a_seed_planned_there_is_the_builds(usa_iso):
    """A build that wears a body folds its size into player_physics' walk
    and roll before it plans (Modkit's size_params); the Randomizer tab
    folds the Characters tab's body in the same way on the picked image, so
    its share string, and the plan Track this seed makes of it, are the
    character build's, with no slider set by hand; with no image it says
    the plan stands on garret4's. Loaded without the body, the build's
    share string names the bodies of that size to wear, and a note's
    sliders read as typing them gives them back."""
    defaults, worn, iso_path = sdk.catalog()["randomizer"]["defaults"], {"species": "balthazar"}, str(usa_iso)
    built = sdk._plan({"iso": iso_path, "packs": {}, "character": worn,
                       "randomizer": {"seed": "2", "settings": defaults}})[4]
    view = sdk.randomizer_settings({"settings": defaults, "character": worn, "iso": iso_path})
    assert (view["share"], view["note"], view["body"]) == (built.recipe["share"], None, None)
    assert sdk.plan({"seed": "2", "share": view["share"]})["sha256"] == built.plan.doc["sha256"]
    assert sdk.randomizer_settings({"share": view["share"], "character": worn, "iso": iso_path})["note"] is None
    bare = sdk.randomizer_settings({"share": view["share"]})
    assert bare["share"] == sdk.randomizer_settings({"settings": defaults})["share"] != view["share"]
    assert bare["note"] == ("the share string was made for a character build: its walk and roll are x1.02897 the "
                            "Patches tab's, the size of balthazar or beamlord: wear it on the Characters tab for the "
                            "same plan")
    assert sdk.randomizer_settings({"settings": defaults, "character": worn})["body"] == (
        "Pick your vanilla image (1.) to fold balthazar's size into the walk and roll, as its build does: until then "
        "the share string and Track this seed stand on garret4's")
    assert layer.sliders_text({"player_physics": {"walk_speed_scale": 1.028966903909119, "jump_speed_scale": 1.3}}) \
        == "player_physics jump_speed_scale 1.3, player_physics walk_speed_scale 1.028966903909119"


def test_moved_movement_sliders_plan_the_nearest_tiers_seed_by_the_physics_table_and_no_moved_slider_is_promised():
    """D1064, D1066: a share string's movement sliders (AZ-383) pick the
    tier its seed is filled at, the one whose reach is nearest the asked
    tier's times their travel factor k, read from the shipped table, which
    is the physics' (the point below vanilla of each row worked out again;
    ``scripts/slider_tiers.py --check`` the whole): jump 1.3 makes Standard
    Frame-perfect, air control 1.1 Hard, no flap on the first shield Safe,
    and a roll none. Its plan is that tier's seed, digest and all, its file
    holding the share string as given, its spoiler, tracker and tab saying
    so and that it isn't promised beatable; a build with those sliders
    plans the same and refuses a share string made for other sliders, its
    first reason naming each gameplay slider moved (a non-movement one's
    too, whose plan is the default's; not a QoL one's), then those the tier
    doesn't read past their ``logic_floor`` and a speed slider at 0 or less
    (D83(c))."""
    from azurkit.tools.randomizer import movement, physics
    from scripts import slider_tiers

    table = movement.table()
    assert table["reach"] == {tier: m.reach for tier, m in physics.tier_margins().items()}
    for key, row in table["sliders"].items():
        pack, name = key.split(" ")
        v, k = [point for point in row["points"] if point[0] < slider_tiers._vanilla(pack, name)][-1]
        assert math.isclose(slider_tiers.k(pack, name, v), k, abs_tol=1e-4), key   # D1016: close on any host
    assert [movement.tier_of(Settings(0, "standard", {}, sliders=sliders)) for sliders in (
        JUMP, {"player_physics": {"air_control_scale": 1.1}}, {"air_shield_flaps": {"air_shield_1_flaps": 0}},
        {"player_physics": {"roll_speed_scale": 2.0}})] == ["frame_perfect", "hard", "safe", "standard"]

    skips = kept_logic().skip_tables
    share, line = _share(JUMP), "your movement sliders make Standard play like Frame-perfect, so the seed is Frame-perfect's"
    doc = sdk.plan({"seed": "2", "share": share})
    tier = sdk.plan({"seed": "2", "share": share_encode(Settings(0, "frame_perfect", {}), skips)})
    assert {key: doc[key] for key in ("attempt", "settings_digest", "placement")} == {
        key: tier[key] for key in ("attempt", "settings_digest", "placement")}
    assert (doc["share"], doc["settings"]["movement_tier"]) == (share, "standard")
    assert f"movement sliders: player_physics jump_speed_scale 1.3; {line}; {movement.PROMISE}" in sdk.spoiler(doc)["lines"]
    assert "movement standard played as frame-perfect (your sliders)" in sdk.tracker({"plan": doc})["head"]["text"]
    weak = sdk.plan({"seed": "2", "share": _share({"air_shield_flaps": {"air_shield_1_flaps": 0}})})
    assert weak["placement"] == sdk.plan({"seed": "2", "share": share_encode(Settings(0, "safe", {}), skips)})["placement"]
    built = generator.prepare({"seed": "2"}, JUMP)
    assert (built.plan.doc, built.recipe, built.why_not) == (doc, {"seed": "2", "share": share}, [])
    with pytest.raises(layer.LayerError, match="holds the movement sliders player_physics jump_speed_scale 1.3"):
        generator.prepare({"seed": "2", "share": share}, {})
    assert generator.prepare({"seed": "2"}, {"enemy_scaling": {"boss_health_scale": 2.0}}).plan.doc == PLANS["default"]["plan"]
    moved = f"you moved sliders (player_physics jump_speed_scale 1.3), and {movement.PROMISE}"
    view = sdk.randomizer_settings({"settings": sdk.catalog()["randomizer"]["defaults"], "packs": JUMP})
    assert (view["share"], view["why_not"]) == (share, [moved, line])
    packs = {"player_physics": {"roll_speed_scale": 0.5, "roll_time_scale": 0.0, "climb_speed_scale": 0.0}
             | JUMP["player_physics"], "enemy_scaling": {"boss_health_scale": 2.0}, "qol_photo_mode": {"fly_speed": 2.0}}
    assert generator.movement_reasons(packs, sdk.catalog()["packs"]) == [
        "you moved sliders (enemy_scaling boss_health_scale 2, player_physics climb_speed_scale 0, player_physics "
        "jump_speed_scale 1.3, player_physics roll_speed_scale 0.5, player_physics roll_time_scale 0), and "
        f"{movement.PROMISE}",
        "player_physics roll_speed_scale 0.5 is below vanilla's 1, movement the logic doesn't model (D83(c))",
        "player_physics roll_time_scale 0 is a lock, not a speed: a roll played at a rate of 0 or less never ends, so"
        " the first RB press holds the player in it",   # D1153: the modern pad's name
        "player_physics climb_speed_scale 0 is a lock, not a speed: " + layer.LOCKS["player_physics",
                                                                                    "climb_speed_scale"],
        "enemy_scaling boss_health_scale 2 is above vanilla's 1, enemy strength the logic doesn't model (D83(c))"]


@pytest.mark.parametrize("release, case, twin", [
    pytest.param("usa", "randomize-full:seed=2,default", False, marks=pytest.mark.vanilla),
    pytest.param("usa", "randomize-full:seed=2,ceiling2", True, marks=pytest.mark.vanilla),
    pytest.param("europe", "randomize-full:seed=2,default", False, marks=[pytest.mark.vanilla, pytest.mark.europe])])
def test_g3s_seed_cases_build_their_goldens_files_and_image_and_open_back_into_their_recipe(release, case, twin, request,
                                                                                             monkeypatch):
    """G3's seed cases (J1's model-free seed case on both releases): the
    packs on by default and the plan of the case's seed and options,
    through the CLI's recipe, change each file the golden names to its
    sha256 and no other (the default case's plan file, built as it is
    with no seed, too: Modkit's ``randomize-full --plan``) (Europe's golden names its own files; its XBRs are
    the USA case's), the image less its root entries is the golden's (the
    default case's of ``rando_plans.json``'s default plan), the image reads
    back to the plan with its logic verified, its report carrying the plan
    (the tracker's), and the build opens back into its recipe. The ceiling2
    case's fill reaches by the compiled reach's Python twin
    (``AZURKIT_NATIVE=0``), the others by its kernel."""
    path = request.getfixturevalue(f"{release}_iso")
    kernels, twins = [], []
    if twin:
        monkeypatch.setenv("AZURKIT_NATIVE", "0")
        monkeypatch.setattr(native, "_LIB", None)
    monkeypatch.setattr(fill, "_LAST_FILL", [None])   # no fill kept from an earlier test
    monkeypatch.setattr(native, "_native", lambda *a, real=native._native, **k: kernels.append(1) or real(*a, **k))
    monkeypatch.setattr(native, "_twin", lambda *a, real=native._twin, **k: twins.append(1) or real(*a, **k))
    args = record_goldens.cases(G3[release])[case]["args"]
    options = {k: args[k] for k in ("skip_ceiling", "movement_tier") if args[k] is not None}
    settings = layer.settings_doc(kept_logic().db.defaults) | options
    given = {"seed": args["seed"]} | ({"settings": settings} if options else {})
    made, report = sdk.image(cli.recipe(str(path), [], [], True, randomizer=given))
    golden = record_goldens.recorded(G3[release])[case]
    want = {f: sha for f, sha in (record_goldens.recorded(G3["usa"])[case] | golden).items() if f != "ISO"}
    assert report["result"] == want and report["conflicts"] == []
    plan = report["randomizer"]
    assert (plan["seed"], plan["logic_verified"], plan["why_not"], plan["conflicts"]) == ("2", True, [], [])
    with iso.Reader(made) as r:
        files = {file: r.read(file) for file in report["result"] if file != "filelist.txt"}
    assert iso.read(path, files).sha256() == golden["ISO"]
    if (release, case) == ("usa", "randomize-full:seed=2,default"):
        assert plan["plan"] == PLANS["default"]["sha256"]
        lines = sdk.spoiler(PLANS["default"]["plan"])["lines"]   # the default plan file: its --spoiler file
        assert report["spoiler"] == "\n".join([lines[0], "logic_verified: true", *lines[1:]]) + "\n"
        assert report["plan"] == PLANS["default"]["plan"]   # the tracker's (Step 4.2c2)
    found = sdk.read_mods(sdk.open_build(made, whole=False))
    assert found == {"packs": mods.normalize({n: {} for n, p in mods.PACKS.items() if p.default_on}),
                     "randomizer": {"seed": "2", "share": plan["share"]}}
    assert (native.report()["loaded"], bool(kernels), bool(twins)) == (not twin, not twin, twin)
    if (release, case) == ("usa", "randomize-full:seed=2,default"):   # its plan file (P31: build --plan), as it is
        doc = PLANS["default"]["plan"]
        again, built = sdk.image(cli.recipe(str(path), [], [], True, randomizer={"plan": doc}))
        assert (built["result"], built["randomizer"], built["plan"], built["spoiler"]) == (
            report["result"], plan, doc, report["spoiler"])
        with iso.Reader(again) as r:
            assert iso.read(path, {file: r.read(file) for file in files}).sha256() == golden["ISO"]
        assert sdk.read_mods(sdk.open_build(again, whole=False))["randomizer"] == {"plan": doc}


@pytest.mark.parametrize("release, recipe", [
    pytest.param("usa", {"randomizer": {"seed": "2"}}, marks=pytest.mark.vanilla),
    pytest.param("usa", {"randomizer": {"seed": "2", "obsidian_cost": 20.0}, "packs": {"qol_alloc_race": {}}},
                 marks=pytest.mark.vanilla),
    pytest.param("europe", {"randomizer": {"seed": "2"}}, marks=[pytest.mark.vanilla, pytest.mark.europe])])
def test_a_seed_build_over_sections_reads_only_its_pages_and_is_the_whole_builds_image_manifest_and_verdict(
        release, recipe, request, monkeypatch):
    """A seed build over ``generator.sections`` (the sparse path, both hosts'):
    the plan's layer planned on the views alone
    is the layer planned on the files, the image and manifest (the verdict in
    it) are the whole build's, byte for byte, with no level's bytes among the
    image's writes but its patches, and every read the host's file sees of it
    (under Python's buffer) but a host's hashes lies in ``generator.pages``,
    each level's TOC in ``generator.heads``."""
    path = str(request.getfixturevalue(f"{release}_iso"))
    stamp, given, layers, _, prepared = sdk._plan({"iso": path, **recipe})
    reasons = generator.movement_reasons(sdk._packs(recipe), sdk.catalog()["packs"])
    with iso.Reader(path) as r:
        base = {file: r.read(file) for file in given}

    def whole_judge(made, manifest):
        return {generator.TOOL: generator.read_back(prepared, made, manifest.layers, manifest.conflicts, reasons)}
    whole, manifest = edits.image(stamp, layers, base, judge=whole_judge, map=sdk._map)
    reads, tracing = [], [True]

    class Traced(io.FileIO):
        def readinto(self, into):
            at, n = self.tell(), super().readinto(into)
            if tracing[0] and n:
                reads.append((at, n))
            return n

    monkeypatch.setattr(iso, "open", lambda name, mode: io.BufferedReader(Traced(name)), raising=False)
    others =[file for file in base if file not in generator.files(prepared)]
    with iso.Reader(stamp.path) as r:
        views = generator.sections(prepared, r, others)
        ahead, spans = generator.heads(prepared, r), generator.pages(prepared, r, others)
        tocs = []
        for stem in writer.graphs(kept_logic().db):
            entry = r.find(f"gamedata/{stem}.xbr")
            toc = nodes.read_toc(functools.partial(r.range, entry))
            tocs.append((r.start(entry), writer.level_spans(toc, entry.size, [])[0][1]))
    given = {file: data for file, data in base.items() if file not in views} | views
    assert generator.plan_layer(prepared, given) == layers[0]

    def sparse_judge(made, manifest):
        return {generator.TOOL: generator.read_back(prepared, made, manifest.layers, manifest.conflicts, reasons,
                                                    sparse=True)}
    run = edits.staged(stamp, layers, given, judge=sparse_judge, map=sdk._map)
    jobs = next(run)
    tracing[0] = False
    hashes = {key: edits._hashes(data) if isinstance(data, iso.Patched) else (hashlib.sha256(data).hexdigest(), None)
              for key, data in jobs.items()}
    tracing[0] = True
    with pytest.raises(StopIteration) as done:
        run.send({key: sha for key, (sha, _) in hashes.items()} | {
            key.replace("file:", "md5:"): md5 for key, (_, md5) in hashes.items() if md5})
    tracing[0] = False
    made, told = done.value.value
    assert told.to_json() == manifest.to_json() and made.sha256() == whole.sha256()
    assert sum(len(data) for _, data in made.writes) < 16 << 20
    patches = sum(isinstance(data, iso.Patched) for data in jobs.values())
    assert patches >= 20 and len(made.writes) <= 3 * patches + 16   # the site's Blob takes a part a write (X5)

    def outside(wanted: list, given: list) -> list:
        return [(at, n) for at, n in wanted if not any(a <= at and at + n <= a + size for a, size in given)]
    assert reads and not outside(reads, spans), (len(reads), outside(reads, spans)[:5])
    assert not outside(tocs, ahead), outside(tocs, ahead)[:5]


def test_a_sparse_read_back_fails_an_image_its_sections_or_lines_dont_hold_though_the_build_hashed_it(usa_iso):
    """The read-back of a build over views reads the image's sections, never
    the patches, and takes a line on trust from nothing but what was hashed: a
    wrong name field in a patched section, a patch gone, a wrong line of a
    patched file and a stray write in a patched level past its sections or in
    a level no patch touches each fail it, by name (D35); the build it stands
    on reads back empty."""
    prepared = generator.prepare({"seed": "2"}, {})
    db, placement = kept_logic().db, prepared.plan.placement
    stamp = sdk._stamp(str(usa_iso))
    with iso.Reader(stamp.path) as r:
        views = generator.sections(prepared, r)
        config = r.read(generator.CONFIG)
        untouched = r.start(r.find("gamedata/training_room.xbr"))
        listing = r.start(r.find("filelist.txt"))
    given = views | {generator.CONFIG: config}
    made, _ = edits.image(stamp, [generator.plan_layer(prepared, given)], given, root=False, map=sdk._map)
    assert writer.read_back(made, placement, db, sparse=True) == []

    key, edit = sorted(prepared.edits.items())[0]
    lid = sorted(edit.repoint)[0]
    field = writer._locations(db)[lid]["name_ref"]["field"]
    level = views[f"gamedata/{edit.file}.xbr"]
    patch = next(w for w in made.writes if w[0] <= level.start + field < w[0] + len(w[1]))
    filelist_write = next(w for w in made.writes if w[0] == listing)
    wrong = filelist_write[1].replace(made.md5s[iso.key(f"gamedata/{edit.file}.xbr")][0].encode(), b"0" * 32)
    assert wrong != filelist_write[1] and not level.holds(level.size - 1, level.size)
    forged = {
        f"^{lid}: the plan has": (*made.writes, (level.start + field, bytes(8))),
        fr"^{lid}: the plan has(?# its patch gone)": tuple(w for w in made.writes if w is not patch),
        fr"^{re.escape(edit.file)}\.xbr: its filelist\.txt line": tuple((at, wrong if at == listing else data)
                                                                       for at, data in made.writes),
        fr"^{re.escape(edit.file)}\.xbr: its filelist\.txt line(?# a stray write past its sections)":
            (*made.writes, (level.start + level.size - 1, bytes([level[-1] ^ 0xff]))),
        r"^training_room\.xbr: its filelist\.txt line": (*made.writes, (untouched + 64, b"\xff"))}
    for pattern, writes in forged.items():
        problems = writer.read_back(dataclasses.replace(made, writes=writes), placement, db, sparse=True)
        assert any(re.search(pattern, problem) for problem in problems), (pattern, problems[:3])


def test_a_later_layer_over_a_placement_is_a_conflict_and_any_other_difference_fails_the_build(usa_iso):
    """The plan's layer is each node graph it edits, whole, the obsidian
    cost's lock thresholds (x1 to x10 in both of town.xbr's tables; above
    vanilla's, the logic is unverified), each contained species' touch
    (AZ-834) and the long-reach spot's own row (AZ-835). An ``xbr`` operation
    over a placement's name field drops its graph, and one over a touch's or
    an own row's cell that group (D28): the build goes on, its logic
    unverified, each changed placement of that graph, the touch and the row
    a conflict naming the later layer. An image that doesn't
    hold the plan (the vanilla one) fails the read-back, by location
    (D35)."""
    prepared = generator.prepare({"seed": "2", "obsidian_cost": 20.0}, {})
    with iso.Reader(usa_iso) as r:
        base = {file: r.read(file) for file in generator.files(prepared)}
    planned = generator.plan_layer(prepared, base)
    groups = {c.group for c in planned.changes}
    (species, _), = generator.contained(prepared.plan.placement, kept_logic().db, base[generator.CONFIG])
    (item, _), = generator.own_rows(prepared.plan.placement, kept_logic().db, base[generator.CONFIG])
    assert groups == {f"randomizer {key}" for key in prepared.edits} | {
        generator.OBSIDIAN_GROUP, f"{generator.CONTAINED_GROUP} {species}", f"{generator.OWN_GROUP} {item}"}
    lock = [c for c in planned.changes if c.group == generator.OBSIDIAN_GROUP]
    assert sorted(c.after for c in lock) == sorted(struct.pack("<f", 20.0 * k) for k in range(1, 11) for _ in range(2))
    assert prepared.why_not == [layer.obsidian_reason(20.0)]
    with pytest.raises(ValueError, match=r"doesn't read back to the plan \(\d+\): \w+/g\d+/r\d+: the plan has"):
        generator.read_back(prepared, usa_iso, [planned], [])

    key, edit = sorted(prepared.edits.items())[0]
    lid = sorted(edit.repoint)[0]
    at, file = writer._locations(kept_logic().db)[lid]["name_ref"]["field"], f"gamedata/{edit.file}.xbr"
    held = base[file][at:at + 8]
    op = {"op": "replace_bytes", "file": file, "offset": at, "value": "00" * 8,
          "expected": {"sha256": hashlib.sha256(held).hexdigest(), "size": 8}}
    cell = {"op": "set", "file": generator.CONFIG, "table": "critters_engine", "entity": species,
            "prop": "collisionRadius", "value": 0.3}
    own = {**cell, "entity": next(iter(writer.OWN_ROW.values()))}
    _, report = sdk.image({"iso": str(usa_iso), "randomizer": {"seed": "2", "obsidian_cost": 20.0},
                           "xbr": [op, cell, own]})
    plan = report["randomizer"]
    assert plan["logic_verified"] is False and plan["why_not"][0] == layer.obsidian_reason(20.0)
    assert plan["why_not"][-3:] == [f"{len(edit.repoint)} placement(s) changed by a later layer",
                                    "1 contained item(s) given another touch by a later layer, so they may be taken "
                                    "through their container",
                                    "1 item(s) in a row of their own changed by a later layer, so they may be out of "
                                    "reach"]
    assert len(plan["conflicts"]) == len(edit.repoint) + 2 and all(
        line.startswith(f"{edit.key}/") and line.endswith("data xbr wrote it after the randomizer (D28)")
        for line in plan["conflicts"][:-2])
    assert plan["conflicts"][-2:] == [
        f"contained touch {species}: config.xbr's critters_engine doesn't hold the plan's cells: data xbr wrote it "
        "after the randomizer (D28)",
        f"own row {item}: config.xbr's tables don't hold the plan's cells: data xbr wrote it after the randomizer "
        "(D28)"]
    for group in (key, f"contained touch {species}", f"own row {item}"):
        assert [c for c in report["conflicts"] if f"whose group randomizer {group} is dropped whole" in c]


def test_the_item_on_a1s_long_reach_spot_is_taken_with_the_vanilla_items_reach_in_a_row_of_its_own():
    """A wind carries the player past a1's frag_air_1 (6 m) too far from
    anything smaller, and the obsidian there has 99 other copies, so its
    node names a spare row (``writer.OWN_ROW``): that row becomes the item,
    bar its name, with the vanilla item's collision, and nothing else
    changes. The row is free: no location, drop or other cell names it. The
    fill still counts the plan's name (its plans don't move), and the gap
    holds the row's name on top of a longest name per location. In xemu the
    obsidian there is taken at the tick and place frag_air_1 is."""
    from azurkit.core.xbr import Document
    from azurkit.tools import data

    db, config = kept_logic().db, data.vanilla()
    (lid, row), = writer.OWN_ROW.items()
    names, vanilla = writer.Names(db), Document(config)
    assert names.locations[lid]["template"] == "frag_air_1" and row not in {
        loc["template"] for loc in names.locations.values()}
    assert not [(t.name, c.at) for t in vanilla.tables.values() for i, c in enumerate(t.cells)
                if c.value == row and i % len(t.rows)]
    pool = [x for x, loc in names.locations.items() if writer.graph_of(x) == writer.graph_of(lid) and loc["pool"]]
    assert names.budget(writer.graph_of(lid)) >= (len(pool) + 1) * max(map(writer.string_cost, names.items))

    def others(table):   # every cell of the table but the row's
        return [c.value for i, c in enumerate(table.cells) if table.cols[i // len(table.rows)] != row]

    for item in ("obsidian", "all_fuel"):
        assert names.target(lid, item) == item and names.written(lid, item) == row
        assert writer.layout({lid: item}, db)[writer.graph_of(lid)].repoint == {lid: row}
        (species, writes), = generator.own_rows({lid: item}, db, config)
        out = bytearray(config)
        for at, value in writes:
            out[at:at + len(value)] = value
        built = Document(bytes(out))
        engine = built.tables["critters_engine"]
        assert species == item and generator.touch(engine, row) == (6.0, 6.0)
        assert engine.number(row, "useCenterBasis") == engine.number("frag_air_1", "useCenterBasis") == 1.0
        for name, table in built.tables.items():
            if row in table.cols:
                reach = ("collisionRadius", "collisionAspectRatio", "useCenterBasis") if name == "critters_engine" else ()
                assert [p for r, p in enumerate(table.rows) if r and p not in reach and table.find(
                    row, p).value != table.find(item, p).value] == [], name
            assert others(table) == others(vanilla.tables[name]), name
    assert generator.own_rows({lid: "frag_air_1"}, db, config) == [] and names.written(lid, "frag_air_1") is None


# AZ-834 (D1036, D1041): each kind of container that encloses pool spots (derived enclosed_by: the kind of the object
# its gate is bound to, a barrier's own, else a gate's region), how many it encloses, and the widest item (by touch R,
# then Z) the fill can put on one, with that spot: of the species an image holds once, and of those it holds more
# than once whose touch isn't inside the vanilla item's there (None: the fill can put none on that kind)
CONTAINED = {
    "acidblock": (5, ("f1/g0/r2176", "frag_air_1"), ("f1/g0/r2176", "all_fuel")),
    "gate": (40, ("w2/g0/r1346", "frag_air_1"), ("w2/g0/r1346", "all_fuel")),   # a5's smokestacks, w2's hose pool,...
    "geode": (231, None, None),                                                 # the gem rocks: gems, all one touch
    "iceblock": (7, ("w2/g0/r1359", "frag_air_1"), ("w3/g1/r2000", "all_fuel")),
    "keylord": (7, None, None),                                                 # the keylords' fields: their keys
    "obsidian_lock": (10, ("town/g1/r40", "key_obsidian1"), None),              # the temple's vaults: kept, 1.05
}
# The touch (R = Z) a kind's blocks and regions hold in for an item held more than once, which keeps its own touch:
# the investigation's body-centre model held every ice block to 1.8 m, the acid blocks to 1.8 to 2.2 and the gates'
# regions to 3.025 (a3's valve) and up, and a sitting saw all_fuel, power_earth and power_air held in w2's and f1's
# blocks with no touch written (Step 4.3 contained items)
HELD = {"acidblock": 1.8, "iceblock": 1.8, "gate": 3.025}


def test_an_item_in_a_container_is_touched_only_where_its_vanilla_item_was_so_it_waits_for_the_container_to_open():
    """AZ-834 (the owner took w2's air fragment from beside its ice block,
    without melting it): the game takes a pickup when the player's centre
    lies in its touch, an ellipsoid round it through any wall
    (``generator.touch``), and the writer keeps the vanilla point. So the
    widest item the fill can put in each kind of container
    (:data:`CONTAINED`), when the image holds it once, is written the
    vanilla item's collision there, and its touch in the built config.xbr
    lies inside that item's; one it holds more than once keeps its own,
    inside its kind's hold (:data:`HELD`). Seed 110585 under the owner's
    share puts frag_air_3 in w2's IceBlock_01 and seed 2 a fragment in
    IceBlock_02: every contained spot of both holds so, frag_air_3 with
    the obsidian's collision."""
    from azurkit.core.xbr import Document
    from azurkit.tools import data

    lg = kept_logic()
    db, config, slots = lg.db, data.vanilla(), fill._Slots(lg)
    vanilla, budget, locs = Document(config).tables["critters_engine"], fill._Budget(slots.names), slots.names.locations
    copies = collections.Counter(loc["template"] for loc in locs.values())

    def kind(gid: str) -> str:
        gate = next((g for doc in db.derived.values() for g in doc["gates"] if g["id"] == gid), {})
        for bound in gate.get("bound_to") or ():
            what, _, oid = bound.partition(":")
            return db.generated_objects[oid][2]["kind"] if what == "barrier" else what
        return "gate"

    def built(placement: dict):   # the built image's critters_engine: the plan's touches over the vanilla file
        out = bytearray(config)
        for _, writes in generator.contained(placement, db, config):
            for at, value in writes:
                out[at:at + len(value)] = value
        return Document(bytes(out)).tables["critters_engine"]

    def holds(engine, placement: dict, loc: str) -> bool:
        species = slots.names.target(loc, placement[loc]) or locs[loc]["template"]
        got, was = generator.touch(engine, species), generator.touch(vanilla, locs[loc]["template"])
        return generator.inside(got, was) or (copies[species] > 1 and got == generator.touch(vanilla, species) and all(
            generator.inside(got, (HELD.get(k, 0.0),) * 2) for k in enclosed[loc]))

    enclosed = {loc["id"]: {kind(gid) for gid in loc["enclosed_by"]} for doc in db.derived.values()
                for loc in doc["locations"] if loc.get("enclosed_by")}
    count, once, shared = collections.Counter(), {}, {}
    for loc, kinds in sorted(enclosed.items()):
        count.update(kinds)
        offered = {slots.vanilla[x] for x in slots.pool
                   if slots.kind[x] == slots.kind[loc] and x not in slots.prefilled}
        for item in [slots.prefilled[loc]] if loc in slots.prefilled else sorted(offered):
            species = slots.names.target(loc, item) or locs[loc]["template"]
            own = generator.touch(vanilla, species)
            if loc not in slots.prefilled and not slots.ok(loc, item, budget):
                continue
            widest = once if copies[species] == 1 else None if generator.inside(
                own, generator.touch(vanilla, locs[loc]["template"])) else shared
            for k in kinds if widest is not None else ():
                widest[k] = max(widest.get(k, ((0.0, 0.0), "", "")), (own, loc, item))
    assert {k: (n, *(t[k][1:] if k in t else None for t in (once, shared))) for k, n in count.items()} == CONTAINED

    vanilla_spot = {item: loc for loc, item in slots.vanilla.items() if copies[locs[loc]["template"]] == 1}
    for _, loc, item in [*once.values(), *shared.values()]:   # each alone there, swapped with that spot's item
        placement = dict(slots.vanilla) | ({vanilla_spot[item]: slots.vanilla[loc]} if item in vanilla_spot else {})
        placement[loc] = item
        assert holds(built(placement), placement, loc), (loc, item)
    for recipe in ({"seed": "110585", "share": "AZR-AAIA"}, {"seed": "2"}):
        placement = sdk.plan(recipe)["placement"]
        engine = built(placement)
        assert [loc for loc in sorted(enclosed) if not holds(engine, placement, loc)] == [], recipe
        if recipe["seed"] == "110585":
            cr, scale, aspect, _ = generator._cells(engine, "frag_air_3")
            obsidian = generator._cells(vanilla, "obsidian")
            assert (placement["w2/g0/r1359"], cr * scale, aspect) == pytest.approx(
                ("frag_air_3", obsidian[0] * obsidian[1], obsidian[2]))


_PLAN_UNDER_PYODIDE = """
import contextlib, io, json
from azurkit import cli
from azurkit.core import native
out, err, calls = io.StringIO(), io.StringIO(), {"kernel": 0, "twin": 0}
def counted(name, real):
    def call(*a, **k):
        calls[name] += 1
        return real(*a, **k)
    return call
native._native, native._twin = counted("kernel", native._native), counted("twin", native._twin)
attempt = native.attempt
def attempted(*a):
    got = attempt(*a)
    calls["attempt"] = calls.get("attempt", 0) + (got is not None and not isinstance(got, int))
    return got
native.attempt = attempted
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
    code = cli.main(["plan", "--seed", "2"])
json.dumps({"code": code, "stdout": out.getvalue(), "stderr": err.getvalue(), "native": native.report(),
            "calls": calls})
"""


def test_the_default_plan_file_is_its_goldens_byte_for_byte_under_pyodide_by_the_compiled_reach(pyodide):
    """``azurkit plan --seed 2`` under Pyodide, the site's runtime, reaching
    by the compiled reach's side module from the wheel (the kernel answers
    its reaches, never the twin, and the fill's attempt, Step 4.4ci57),
    prints the default plan file byte for byte."""
    got = pyodide(python=_PLAN_UNDER_PYODIDE)
    assert (got["code"], got["stderr"]) == (0, ""), got["stderr"][-2000:]
    assert got["stdout"] == DEFAULT_PLAN
    assert (got["native"]["loaded"], got["native"]["library"]) == (True, "emscripten-wasm32.so"), got["native"]
    assert got["calls"]["kernel"] > 0 and got["calls"]["twin"] == 0 and got["calls"]["attempt"] > 0, got["calls"]


def test_seed_2s_plan_is_the_same_in_two_processes_under_two_hash_seeds():
    """D34, AZ-002, AZ-084 (Modkit's ``test_randomizer_determinism``,
    ported): ``azurkit plan --seed 2``, each in a process of its own under
    PYTHONHASHSEED 0 and 1, at the database's defaults and at the max
    profile's share string, prints the same plan file under both: its
    golden's (the default plan file byte for byte, the max plan's sha256)."""
    share = _profile("max")["share"]
    runs = [(seed, args) for args in ((), ("--share", share)) for seed in (0, 1)]
    procs = [subprocess.Popen([sys.executable, "-m", "azurkit", "plan", "--seed", "2", *args], text=True,
                              env=os.environ | {"PYTHONHASHSEED": str(seed)}, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE) for seed, args in runs]

    def ended(proc: subprocess.Popen) -> tuple:   # its pipes read as it runs: Windows's hold 4 KiB of a plan
        out, err = proc.communicate(timeout=600)
        return proc.returncode, out, err
    got = [ended(p) for p in procs]   # four cold plans at once
    assert got[0] == got[1] and got[0][:2] == (0, DEFAULT_PLAN), got[0][2][-2000:]
    assert got[2] == got[3] and got[2][0] == 0, got[2][2][-2000:]
    assert json.loads(got[2][1])["sha256"] == PLANS["max"]["sha256"]


def test_twenty_seeds_under_four_option_sets_plan_and_spoil_as_the_solver_before_r21_made_them():
    """Step 4.3u (round 2's R2.1) and Step 4.3 native reach: the fill's kept
    reaches and known traps and the compiled reach (its spheres replayed
    from its rounds) change no plan: each of :data:`PLANS80`'s 80 plans (an
    option set's 20 seeds in a process of its own, the four at once) has
    its attempt, sha256 and spoiler."""
    procs = {name: subprocess.Popen([sys.executable, "-c", _PLANS80, json.dumps(st)], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE) for name, st in OPTIONS80.items()}
    for name, proc in procs.items():
        out, err = proc.communicate(timeout=1800)
        assert proc.returncode == 0, err[-2000:]
        assert tuple(out.splitlines()) == PLANS80[name], name


def test_a_reach_refuses_the_first_bad_spot_of_a_placement_and_bad_options_by_name_every_time():
    """Step 4.4bk: a reach checks a placement by whole sets and lists its spots
    only to name a refusal, the first as the placement lists them (an id no
    authored level's pool location, an item items.toml lacks, a guardian
    slot's other item); options it refused once it refuses again."""
    logic = kept_logic()
    st, slot = logic.db.defaults, min(logic.guardian)
    spot = next(loc for loc, lvl in sorted(logic.pool.items()) if lvl not in logic.db.stubs and loc not in logic.guardian)
    for placement, why in (({spot: None, "w1/nowhere": None, slot: None},
                            "placement: w1/nowhere is no pool location of an authored level"),
                           ({spot: "no such item", "w1/nowhere": None},
                            f"placement: {spot} holds 'no such item', which items.toml doesn't define"),
                           ({spot: None, slot: None},
                            f"placement: {slot} is a guardian slot, which keeps its {logic.vanilla[slot][0]} (D81)")):
        with pytest.raises(ValueError, match=f"^{re.escape(why)}$"):
            logic.reach(st, placement, traps=False)
    assert logic.reach(st, {spot: None}, traps=False) == logic.reach(st, {spot: None}, traps=False)
    for _ in range(2):
        with pytest.raises(ValueError, match="movement_tier"):
            logic.reach(Settings(0, "no such tier", {}), {}, traps=False)


def test_the_grammar_has_no_negation_and_each_rule_the_solver_compiles_holds_at_any_larger_state():
    """The reach's escapes rest on monotone rules (a failed escape fails
    every node it saw whose starting flags it held, their escapes inside
    its own): the grammar refuses a negation however it is
    spelled (each time; a text it reads is kept), and every rule of the default and max options' graphs, logic
    and physical (edges, teleports, locations, credits, victory), that
    holds at a random state holds at any larger one (more of each counter,
    more flags)."""
    for text in ("not water1", "!water1", "~water1", "-water1", "water1 & !fire1", "!(water1)", "water<1",
                 "water<=1", "water!=1", "water==0", "water1 & not(fire1)"):
        for _ in range(2):   # refused again: a refusal isn't kept
            with pytest.raises(ParseError):
                parse(text)
    text = "(water1 | fire2) & air>=1"   # Step 4.4bk: a text's AST is kept, the same tuple the next time
    assert parse(text) is parse(text) == ("and", (("or", (("counter", "water", 1), ("counter", "fire", 2))),
                                                   ("counter", "air", 1)))
    logic, rng = kept_logic(), random.Random(0)
    counters = sorted({c for cs in logic.items.values() for c in cs})
    for st in (logic.db.defaults, Settings(4, "frame_perfect", {})):
        for physical in (False, True):
            g = logic.rules(st, physical)
            rules = [r for edges in g.adj.values() for _, r in edges] + [t[2] for t in g.teleports] + [
                r for *_, r in g.locations] + [r for *_, r in g.credits] + [g.victory]
            flags = sorted({f for f, *_ in g.credits})
            top = {c: max(g.reads.get(c, ()), default=0) + 1 for c in counters}
            for _ in range(200):
                low = {c: rng.randint(0, top[c]) for c in counters}
                high = {c: n + rng.randint(0, 2) for c, n in low.items()}
                f_low = {f for f in flags if rng.random() < 0.5}
                f_high = f_low | {f for f in flags if rng.random() < 0.5}
                assert not [r for r in rules if r(low, f_low) and not r(high, f_high)], (st, physical)


def test_a_fill_another_thread_makes_is_waited_on_telling_its_count_and_a_cancelled_one_is_made_by_its_waiter(
        monkeypatch):
    """Step 4.3u (D1007: a host's plan ahead): a fill of the seed and
    settings another thread is making is waited on, the waiter telling the
    maker's count each ``fill.WAIT`` s, so a cancel raised from its host's
    callback stops it there; a maker cancelled at a note keeps nothing
    (D35) and its waiter makes the fill itself, which is the plain one,
    kept for the next call (no note)."""
    monkeypatch.setattr(fill, "_LAST_FILL", [None])
    logic, held, go, waiting = kept_logic(), threading.Event(), threading.Event(), threading.Event()

    class Stop(Exception):
        pass

    def run(hear, out):
        try:
            with progress.noting(progress.Steps(hear)) as steps:
                steps("plan", "Filling the seed")
                out.append(fill.fill(logic, "2"))
        except Stop:
            out.append(Stop)

    def maker(record):   # held at its first count, then cancelled there
        if " of " in record["label"]:
            held.set()
            go.wait(120)
            raise Stop

    def stopped(record):  # a waiter cancelled at its third record
        told.append(record["label"])
        if len(told) == 3:
            raise Stop

    def patient(record):  # a waiter until the maker is cancelled
        told_b.append(record["label"])
        if " of " in record["label"]:
            waiting.set()

    made, cancelled, told, b, told_b = [], [], [], [], []
    first = threading.Thread(target=run, args=(maker, made))
    first.start()
    assert held.wait(120)
    run(stopped, cancelled)
    count = told[1].removeprefix("Filling the seed (").removesuffix(")")
    assert (cancelled, told[0], told[2], re.fullmatch(r"placing the items, 1 of \d+", count) is not None) == (
        [Stop], "Filling the seed", told[1], True)
    second = threading.Thread(target=run, args=(patient, b))
    second.start()
    assert waiting.wait(120)
    go.set()
    first.join(120)
    second.join(120)
    assert (made, fill._MAKING, plan_doc(b[0], logic.db)) == ([Stop], {}, PLANS["default"]["plan"])
    last = re.search(r"(\d+) of (\d+)\)$", told_b[-1])   # it filled, counting to the last spot
    assert last[1] == last[2] == count.rsplit(" ", 1)[1]
    heard, again = [], []
    run(heard.append, again)
    assert ([r["label"] for r in heard], again[0].placement) == (["Filling the seed"], b[0].placement)


def test_an_ask_that_finds_the_fill_kept_after_taking_its_in_flight_slot_ends_it_for_a_thread_waiting_there(
        monkeypatch):
    """Step 4.3u (review F1): an ask whose second look finds the fill kept
    (another maker stored it between its two looks) ends the in-flight slot
    it took with that fill, so a second ask that landed on the slot in that
    window gets the fill too instead of waiting on it for ever."""
    logic, asker, joined, looks, slots, got = kept_logic(), threading.current_thread(), threading.Event(), [], [], []
    kept = fill.Fill("2", logic.db.defaults, 0, {"a spot": "an item"})

    class Slots(dict):   # the fills in flight, telling when the second ask lands on the first's slot
        def setdefault(self, key, value):
            slots.append(slot := super().setdefault(key, value))
            if threading.current_thread() is not asker:
                joined.set()
            return slot

    def looked(of, key):   # the asker's second look finds the fill another maker stored meanwhile
        if threading.current_thread() is not asker:
            return None
        looks.append(key)
        if len(looks) == 1:
            return None
        second.start()
        assert joined.wait(60)
        return kept

    monkeypatch.setattr(fill, "_MAKING", Slots())
    monkeypatch.setattr(fill, "_kept", looked)
    second = threading.Thread(target=lambda: got.append(fill.fill(logic, "2")), daemon=True)
    try:
        first = fill.fill(logic, "2")
        second.join(5)
        assert (second.is_alive(), first.placement, [g.placement for g in got], fill._MAKING) == (
            False, kept.placement, [kept.placement], {})
    finally:
        for slot in slots:   # a waiter left on a slot that never ended stops, taking the kept fill
            slot.made, slot.ended = kept, True
        second.join(5)


@pytest.fixture(scope="module")
def shipped_database(tmp_path_factory) -> Path:
    """The database the wheel and the app ship (``web_tools.ship_database``), written once for this file's tests."""
    return web_tools.ship_database(tmp_path_factory.mktemp("shipped"))


def test_the_databases_key_reads_again_only_a_file_whose_size_or_times_changed_and_follows_it(tmp_path, monkeypatch):
    """``dbcache.entry``, which ``kept_logic`` asks each call (eight a plan's first tracker view): a file as it was is
    not read again, and a changed one, even of the same size, gives another key."""
    root = tmp_path / "data"
    (root / "levels").mkdir(parents=True)
    (root / "levels" / "w1.toml").write_text("a", encoding="utf-8")
    (root / "items.toml").write_text("b", encoding="utf-8")
    first, read, real = dbcache.entry(root, None), [], Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: read.append(self.name) or real(self))
    assert dbcache.entry(root, None) == first and read == []
    (root / "items.toml").write_text("c", encoding="utf-8")
    st = (root / "items.toml").stat()   # a rewrite inside one clock tick keeps its times: move them a whole second,
    os.utime(root / "items.toml", ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))   # which HFS+ keeps too
    assert dbcache.entry(root, None) != first and read == ["items.toml"]


def test_the_shipped_database_is_a_fresh_checks_holds_no_absolute_path_and_is_the_planners_kept_logic_unwalked(
        shipped_database, monkeypatch):
    """The database the wheel and the app ship (``web_tools.ship_database``:
    checked in a child under PYTHONHASHSEED=0, its root dropped) is keyed by
    the data and planner it was made from, holds no path of the checkout
    that made it (no ``pathlib`` object, nor the checkout's or the home
    folder's path), and reads back (``dbcache.shipped_logic``, as the
    frozen app reads it) into the database and the Logic tables a fresh
    ``check_database`` gives, frozen out of the cycle collector's walks
    (train B2: two full walks of it held the app's server 0.8 s); the
    planner's kept Logic is that one, with no database checked and no Logic
    built (the loader's ``SHIPPED`` hook)."""
    shipped = shipped_database
    blob = shipped.read_bytes()
    assert (shipped.stem, b"pathlib" in blob, str(Path(web_tools.ROOT)).encode() in blob,
            str(Path.home()).encode() in blob) == (dbcache.entry(loader.DATA_DIR).name, False, False, False)
    monkeypatch.setattr(dbcache, "SHIPPED", shipped.parent)
    monkeypatch.setattr(dbcache, "FROZEN", True)
    got, fresh = dbcache.shipped_logic(loader.DATA_DIR, Logic), Logic(loader.check_database(loader.DATA_DIR).database)
    assert got.db == fresh.db and not any(o is got.db for o in gc.get_objects())
    assert {k: v for k, v in vars(got).items() if k not in loader._MEMOS} == {
        k: v for k, v in vars(fresh).items() if k not in loader._MEMOS}
    assert {k: v for k, v in vars(got).items() if k in loader._MEMOS - {"db"}} == {
        k: type(v)() for k, v in vars(fresh).items() if k in loader._MEMOS - {"db"}}
    monkeypatch.setattr(loader, "_KEPT", {})
    monkeypatch.setattr(loader, "load_database", lambda root: pytest.fail(f"{root}: checked, not the shipped one"))
    kept = kept_logic()
    assert kept.db == fresh.db and kept_logic() is kept
    gc.unfreeze()   # the rest of this process's tests as they were


def test_a_launchs_restore_checks_the_skip_table_shipped_apart_never_the_logic_whose_read_is_counted(
        shipped_database, monkeypatch):
    """Step 4.4bd: the shipped database's file holds its skip table ahead of
    the database, the logic's own skips, so a launch's restore of a
    remembered randomizer (``sdk.restore``) checks its settings against
    that table, about 14 KB, and never reads the 87.6 MB logic (A02's
    0.4 s). The logic's read is counted:
    the Randomizer tab's first ask hears each twentieth of it, once, and an
    ask once it is read hears nothing, so no bar flashes; two callers at
    once (the app's server: that ask beside the tracker's view) are served
    one read."""
    monkeypatch.setattr(dbcache, "SHIPPED", shipped_database.parent)
    monkeypatch.setattr(dbcache, "FROZEN", True)
    monkeypatch.setattr(loader, "_KEPT", {})
    table, defaults = dbcache.shipped_skips(loader.DATA_DIR), randomizer.options()["defaults"]
    pick = next(sid for sid, s in table.items() if turnable(s))
    kept = {"on": True, "seed": "2", "settings": defaults | {"skip_override": {pick: True}}}
    with monkeypatch.context() as m:
        m.setattr(randomizer, "kept_logic", lambda: pytest.fail("the restore read the logic"))
        restored = sdk.restore({"ticked": [], "randomizer": kept})
    heard, again = [], []
    sdk.randomizer_settings({"settings": defaults}, progress=heard.append)
    sdk.randomizer_settings({"settings": defaults}, progress=again.append)
    assert (restored["randomizer"], restored["dropped"], table) == (
        kept, [], {sid: s for sid, (_, s) in kept_logic().db.skips.items()})
    assert ([r["percent"] for r in heard], again) == (list(range(0, 100, 5)), [])
    monkeypatch.setattr(loader, "_KEPT", {})
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        first, second = pool.map(lambda _: kept_logic(), range(2))
    assert first is second
    gc.unfreeze()   # the rest of this process's tests as they were


def test_the_trackers_verdicts_are_their_goldens_at_each_state_and_a_click_marks_what_it_names():
    """Step 4.2c2 (D189, D249): the item tracker (Modkit's ``Tracker``,
    ported) on seed 2's default and max plans gives its golden's verdicts
    (:data:`TRACKER`, first recorded from Modkit's own) with nothing
    marked, after three rounds of marking every spot reachable now, with
    every power marked
    and with Live's kit at every element 3 (R1.41: the reach holds the
    levels the game holds), with Gems on and Live's gem takes (Step 4.2c3,
    R1.43: each gem spot's gems taken and in all, each level's, the Table's
    gem rows), the spoiler off (no item a spot holds is given until it is
    collected) and on. A click marks a spot and a second takes
    it off; a click on a live mark vetoes it (Live won't mark it again);
    Reset clears both; a spot or plan it doesn't know, or a kit it can't
    hold, is refused by name."""
    def view(doc, marks, spoiler, kit=None):
        return sdk.tracker({"plan": doc, "marks": marks, "kit": kit, "spoiler": spoiler, "gems": shows_gems(marks)})

    for name in ("default", "max"):
        doc = _profile(name)
        for state, marks, kit in tracker_states(view, doc):
            for spoiler in (False, True):
                key = f"{name}/{state}/{'spoiler' if spoiler else 'plain'}"
                got = hashlib.sha256(tracking.digest(view(doc, marks, spoiler, kit)).encode()).hexdigest()
                assert got[:32] == TRACKER[key], key
    doc = _profile("default")
    plain = view(doc, None, False)
    assert {s["item"] for s in plain["spots"].values()} == {None}
    assert plain["head"] == {"seed": "2", "share": doc["share"], "sha256": doc["sha256"], "skips": [], "text": (
        f"Seed 2 · {doc['share']} · skips None, movement standard · 0 skips on"), "difficulty": {   # Normal's line too
        "level": "Normal", "steps": 19, "off": 17, "points": 0,
        "text": "Normal: 19 key-item steps, 17 off the path, no trick needed"}}
    near = sorted(loc for loc, s in plain["spots"].items() if s["state"] == "near")[0]
    marked = sdk.tracker({"plan": doc, "toggle": near})
    assert (marked["marks"], marked["spots"][near]["state"], marked["spots"][near]["item"]) == (
        {"collected": [near]}, "got", doc["placement"].get(near) or kept_logic().vanilla[near][0])
    assert sdk.tracker({"plan": doc, "marks": marked["marks"], "toggle": near})["marks"] == {"collected": []}
    live = sdk.tracker({"plan": doc, "marks": {"collected": [near], "live": {near: 0.5}}, "toggle": near})
    assert live["marks"] == {"collected": [], "veto": [near]}
    assert sdk.tracker({"plan": doc, "marks": live["marks"], "reset": True})["marks"] == {"collected": []}
    for given, why in (({"plan": doc, "toggle": "w1/g0/r1"}, "'w1/g0/r1' is no spot"),
                       ({"plan": doc | {"seed": "3"}}, "edited plan"), ({"plan": doc, "kit": {"air": -1}}, "kit is"),
                       ({"plan": doc, "marks": {"collected": [1]}}, "by their ids"), ({"plan": doc, "x": 1}, "no key 'x'")):
        with pytest.raises(ValueError, match=why):
            sdk.tracker(given)


def test_the_tracker_with_no_plan_gives_each_spot_the_vanilla_games_item_where_its_map_draws_it():
    """Step 4.4u3: with no plan the tracker gives the maps to browse: every
    spot a plan's tracker marks, in its level and class, its state
    ``vanilla`` and its item the one the base game puts there, which is
    the one the shipped maps place on that level's map; the world map as a
    plan's; and the world map's levels by realm in the Table's order (the
    airship, with no spot, last)."""
    from azurkit.tools.randomizer.tracker import realm

    doc = _profile("default")
    plan, bare = sdk.tracker({"plan": doc}), sdk.tracker({})
    assert sdk.tracker({"plan": None, "spoiler": True}) == bare and bare["vanilla"] is True
    assert {loc: (s["level"], s["class"]) for loc, s in bare["spots"].items()} == {
        loc: (s["level"], s["class"]) for loc, s in plan["spots"].items()}
    vanilla = kept_logic().vanilla
    assert all((s["state"], s["item"], s["name"], s["icon"]) == (
        "vanilla", vanilla[loc][0], tracking.item_name(vanilla[loc][0]), tracking.icon(vanilla[loc][0]))
        for loc, s in bare["spots"].items())
    maps = json.loads((Path(web_tools.ROOT) / "web" / "art" / tracking.ART_VERSION / "maps.json").read_text(encoding="utf-8"))
    assert {(lv, i["id"], i["item"]) for lv, e in maps["levels"].items() for i in e["items"] + e["spots"]} == {
        (s["level"], loc, s["item"]) for loc, s in bare["spots"].items()}
    assert bare["world"] == plan["world"]
    assert sorted(lv for _, lvs in bare["levels"] for lv in lvs) == sorted(tracking.GRID)
    assert all(lvs == sorted(lvs) and {realm(lv) for lv in lvs} == {name} for name, lvs in bare["levels"])
    assert [name for name, _ in bare["levels"]] == [r["label"] for r in plan["table"]["levels"][:-1]] + ["Airship"]


def test_a_seeds_plan_and_its_first_tracker_view_report_their_stages_and_answer_as_without_them(monkeypatch):
    """Step 4.3 train (D980): Track's bar on both hosts follows the engine's
    work. ``sdk.plan`` reports the logic read, the fill and the placements
    written (``core.progress``'s ``plan``, done of 3), the fill counting its
    items inside its step (Step 4.3u: "placing the items, k of n", each
    item a reach places a step, each percent of them, never back),
    so the app's bar, polled every 250 ms, moves through the seconds the
    fill takes once the shipped Logic is read at once (train B2); the
    tracker's first view of the plan its tracker built and the world map
    read (done of 2), and a view of a kept plan nothing, so a click on a
    spot shows no bar. Each answers as it does without ``progress``."""
    kept_logic()   # read before: a cold read counts the logic's checks in its first stage too (test_hosts)
    seen = []
    monkeypatch.setattr(fill, "_LAST_FILL", [None])   # the seed's fill not kept from another test: it fills now
    doc = sdk.plan({"seed": "2"}, progress=seen.append)
    assert doc == PLANS["default"]["plan"]
    counts = [re.fullmatch(r"Filling the seed \(placing the items(?:, (\d+) of (\d+))?\)", r["label"]) for r in seen]
    ks = [int(m[1]) for m in counts if m and m[1]]
    n = int(next(m[2] for m in counts if m and m[2]))
    assert (ks == sorted(ks), ks[0], ks[-1], {k * 100 // n for k in ks}) == (True, 1, n, set(range(101)))
    assert [r["done"] / r["total"] for r in seen] == sorted(r["done"] / r["total"] for r in seen)
    seen[:] = [r for r, m in zip(seen, counts) if not m]
    world = tracking.world()
    monkeypatch.setattr(tracking, "world", functools.cache(lambda: world))   # a process's first view reads it
    monkeypatch.setattr(tracking, "_KEPT", type(tracking._KEPT)())
    first, again = (sdk.tracker({"plan": doc}, progress=seen.append) for _ in range(2))
    assert [(r["stage"], r["label"], r["percent"]) for r in seen] == [
        ("plan", "Reading the randomizer's logic", 0), ("plan", "Filling the seed", 33),
        ("plan", "Writing the placements", 66), ("plan", "Reading the seed's logic", 0),
        ("plan", "Reading the world map", 50)]
    assert tracking.digest(first) == tracking.digest(again) == tracking.digest(sdk.tracker({"plan": doc}))


def test_a_retried_fill_counts_on_from_its_stuck_attempt_in_the_one_stream_sdk_plan_and_randomizer_plan_report(
        monkeypatch):
    """Step 4.3 train B3: the fill's notes and the planner's are one stream
    (``core.progress.note``, each folded by the call's ``noting``), so
    ``sdk.plan`` reports ``randomizer.plan``'s records as they are; seed 16,
    whose attempt 0 sticks and attempt 1 passes, counts its items once
    through both attempts (no label names an attempt, the count never
    falls), and no record's done of total is short of the one before it."""
    kept_logic()   # read before: neither call counts the logic's checks
    heard = []
    for plan in (sdk.plan, randomizer.plan):
        monkeypatch.setattr(fill, "_LAST_FILL", [None])   # each fills
        monkeypatch.setattr(fill, "_KNOWN", [None])   # and finds its known traps: both calls tell the same notes
        heard.append([])
        doc = plan({"seed": "16"}, progress=heard[-1].append)
    seen = heard[0]
    counts = [re.fullmatch(r"Filling the seed \(placing the items(?:, (\d+) of (\d+))?\)", r["label"])
              for r in seen if r["label"].startswith("Filling the seed (")]
    ks = [int(m[1]) for m in counts if m[1]]
    assert (doc["attempt"], heard[0] == heard[1], all(counts), ks == sorted(ks), ks[-1]) == (
        1, True, True, True, int(counts[-1][2]))
    assert [r["done"] / r["total"] for r in seen] == sorted(r["done"] / r["total"] for r in seen)


@pytest.mark.web
def test_the_recorder_writes_the_trackers_golden_from_azurkits_own_tracker_and_map_view():
    """``tracker.json`` is what ``scripts/record_goldens.py`` records: each
    state's view from the tracker on CPython and the maps' model the page's
    ``web/mapview.mjs`` draws of it, under Node (the test is ``web``)."""
    made = record_goldens.record(record_goldens.TRACKER, record_goldens.Images())
    assert record_goldens.text(made) == (record_goldens.GOLDENS / record_goldens.TRACKER).read_text(encoding="utf-8")


# ---------------------------------------------------------------- Step 4.28d: Modkit's unpinned Randomizer-page tests
# (the test census's lane D): what the maps say each way needs, and an empty seed refused.

@pytest.mark.parametrize("src, dest, kind, words, per_exit, dashed", [
    ("w1", "w2", "nothing", "needs nothing", {"W1_W2": "needs air 1"}, (False, False)),
    ("w1", "town", "water", "needs water 1", {"W1_Town_Waterfall": "needs air 1 + fire 1 + key life1",
                                              "water_disk_loc": "needs 4 water fragments"}, (False, False)),
    ("f3", "w4", "powers", "needs (earth 1 + water 1) or air 3", {}, (False, False)),
    ("e5", "f2", "key battery", "needs 6 battery keys", {}, (False, False)),
    ("town", "life", "fragments", "needs 3 life fragments", {}, (False, False)),
    ("e2", "e6", "event", "needs earth keylock3 + earth keylock4 + earth keylock5", {}, (False, False)),
    ("a6", "a1", "unreachable", "unreachable", {}, (False, True)),
    ("a1", "a6", "keys", "needs air 3 + earth 2 + fire 3 + key air1 + key air2 + key air3 + water 3 + seal", {},
     (True, True)), ("w1", "airship", "event", "needs guard water killed + guard earth killed", {}, (True, True))])
def test_a_connection_is_coloured_by_what_it_needs_dashed_when_one_way_and_named_on_hover(
        src, dest, kind, words, per_exit, dashed):
    """Modkit's Step 2.33 (M9, M11) and AZ-341: what an exit needs comes
    from the randomizer's level files: its own requirement and what reaching
    its switch from the level's arrivals needs (w1's exit beside town, past
    FireWall_01: water 1; its dark cave's: a life key, the torpedo's water
    keylock, behind the station's electric arch, air 1 + fire 1; its disc
    teleport's: 4 water fragments), and a connection needs the least of its
    exits'. An exit no arrival reaches (a6's A6_A1, out of logic) is
    "unreachable", not "needs false" (R1.14). A need with alternatives names
    each (AZ-432: f3's exit to w4 takes acid or air 3). On its level's map
    (``tracking.world``'s maps, which the page draws) each exit is in its own
    need's colour, on the world map the connection; an exit dashed when no
    exit the logic can use leads back (M9, Step 2.85b: a1 → a6, whose way
    back is out of logic, too), a line when either way is one way, and each
    tip names its levels and need."""
    maps = tracking.world()["maps"]
    need = needs.needs(src, dest)
    assert (needs.need_kind(need), needs.need_words(need)) == (kind, words)
    exits = [e for e in maps["levels"][src]["exits"] if e["to"] == dest]
    assert [(e["tip"].startswith(f"{e['spot']} → {dest}: {per_exit.get(e['spot'], words)}"), e["dashed"],
             e["colour"] == needs.colour(e["kind"])) for e in exits] == [(True, dashed[0], True)] * len(exits) != []
    assert needs.colour(kind) in {e["colour"] for e in exits}
    [line] = [w for w in maps["lines"] if {w["a"], w["b"]} == {src, dest}]
    assert f"{src} → {dest}: {words}" in line["tip"] and line["dashed"] == dashed[1]


def test_a_needs_colour_goes_by_key_or_by_the_barrier_its_spell_breaks_and_an_exit_with_no_place_keeps_its_need():
    """Modkit's AZ-462: a need's colour goes by key (each its own, "keys"
    for several) or by the barrier type its powers' spell breaks, not by the
    power combination, every key's shade apart. The airship's flight to a3
    (W1_A3) has no place on its map: it keeps its need's colour, its dash
    and its tip, which the page draws at the map's right edge (test_site's)."""
    kinds = {req: needs.need_kind(req) for req in (
        "key.battery>=6", "key.red>=1 & water>=1", "key.air1>=1 & key.air2>=1", "fire>=1 & water>=1",
        "earth>=2 & water>=1", "air>=1 & earth>=1 & fire>=1", "air>=1 & fire>=1 & water>=1", "air>=3 & water>=1")}
    assert kinds == {"key.battery>=6": "key battery", "key.red>=1 & water>=1": "key red",
                     "key.air1>=1 & key.air2>=1": "keys", "fire>=1 & water>=1": "ice block",
                     "earth>=2 & water>=1": "acid block", "air>=1 & earth>=1 & fire>=1": "smash wall",
                     "air>=1 & fire>=1 & water>=1": "crystal", "air>=3 & water>=1": "powers"}
    shades = [needs.colour(k) for k in [*needs.NEEDS, *(f"key {n}" for n in needs.key_names())]]
    assert len(set(shades)) == len(shades) == len(needs.NEEDS) + 16
    [flight] = [e for e in tracking.world()["maps"]["levels"]["airship"]["exits"] if e["spot"] == "W1_A3"]
    assert (flight["colour"], flight["dashed"], flight["tip"]) == (
        needs.colour("event"), True, "W1_A3 → a3: needs balthazar killed; one way")


def test_an_empty_seed_is_refused_by_name_by_a_plan_or_build_and_a_link_holding_one_still_loads(tmp_path):
    """Modkit's N9 (Q74): a seed the build couldn't use once silently became
    42. Any text is a seed; one with none (empty, or spaces) is refused by
    name, by a plan (``azurkit plan`` and Track this seed's) and by a build
    (``sdk.image``, a worn body's too, and ``azurkit build --seed``), before
    an image is read. A share link or mods file holding one (v1.0.0's Share
    made them) still loads, its packs with it; its build refuses the seed."""
    said = "the seed is empty: type any text, or draw one (New)"
    iso_path = str(tmp_path / "none.iso")
    for call in (lambda: sdk.plan({"seed": ""}),
                 lambda: sdk.image({"iso": iso_path, "packs": {}, "randomizer": {"seed": "  "}}),
                 lambda: sdk.image({"iso": iso_path, "packs": {}, "character": {"species": "beamlord"},
                                    "randomizer": {"seed": ""}})):
        with pytest.raises(ValueError, match=f": {re.escape(said)}$"):
            call()
    assert cli.main(["plan", "--seed", " "]) == 1
    link = sdk.preset_encode({"iso": iso_path, "packs": {"fps_unlock": {}}, "randomizer": {"seed": ""}})
    assert sdk.read_mods(link) == {"packs": {"fps_unlock": {}}, "randomizer": {"seed": ""}}
    assert [la["recipe"] for la in sdk.preset_decode(link)["layers"] if la["tool"] == generator.TOOL] == [{"seed": ""}]


# --- Step 4.28f: Modkit's unpinned settings, tracker and writer rules, ported ------------------------------------

TOYDB = Path(__file__).resolve().parent.parent / "devkit" / "rando" / "data" / "toydb"   # devkit's toy database


def test_settings_refuse_a_toggle_that_turns_on_a_held_or_manual_skip(tmp_path):
    """D144: a toggle wins over the ceiling, but never turns on a held or a
    manual skip, in a settings file or a share string; a string's toggles
    count only against the skip registry it was made for (§7.3)."""
    import shutil

    from azurkit.tools.randomizer.planner.settings import SettingsError, skips_on

    root = tmp_path / "db"
    shutil.copytree(TOYDB, root)
    (root / "settings" / "mine.toml").write_text(
        'format = "azurik-rando-settings/1"\nskip_ceiling = 4\nmovement_tier = "safe"\ndark_fire = 1\n\n'
        '[skip_override]\n"t1.wall_skip" = false\n"t1.held_skip" = true\n"t1.manual_skip" = true\n',
        encoding="utf-8")
    assert [(i.code, i.where) for i in loader.check_database(root).issues] == [
        ("settings_enables_held_or_manual_skip", "settings/mine.toml: skip_override.t1.held_skip"),
        ("settings_enables_held_or_manual_skip", "settings/mine.toml: skip_override.t1.manual_skip")]
    skips = {sid: s for sid, (_, s) in loader.load_database(TOYDB).skips.items()}
    for sid, status in (("t1.held_skip", "held"), ("t1.manual_skip", "manual")):
        text = share_encode(Settings(0, "hard", {sid: True}), skips)
        with pytest.raises(SettingsError, match=f"skip_override.{sid}: turns on a {status} skip"):
            share_decode(text, skips)
    on = Settings(0, "hard", {"t1.wall_skip": True})
    text = share_encode(on, skips)
    assert share_decode(f" {text.lower()} ", skips) == on
    assert skips_on(on, skips) == ["t1.wall_skip"]
    fewer = {sid: s for sid, s in skips.items() if sid != "t1.held_skip"}
    for text, why in ((text, "made for another skip registry"), ("AZR-AAIB", "not canonical")):
        with pytest.raises(SettingsError, match=why):
            share_decode(text, fewer)


def test_a_share_string_whose_toggle_varint_never_ends_is_refused_at_its_fifth_byte():
    """Step 4.42b: a share string's toggle varint ends by its fifth byte,
    which holds any count or gap a registry has; a longer run (a crafted
    string's, as long as the string) is refused there, so its decoding
    stays linear in its length rather than quadratic, where it read on to
    the string's end and only then said "truncated"."""
    from azurkit.tools.randomizer.planner.settings import SettingsError, registry_tag

    skips = {sid: s for sid, (_, s) in loader.load_database(TOYDB).skips.items()}
    for run in (5, 200_000):
        raw = bytes([0, 0x80]) + registry_tag(picks(skips)) + b"\xff" * run
        with pytest.raises(SettingsError, match="share: a toggle index past the registry$"):
            share_decode("AZR-" + base64.b32encode(raw).decode().rstrip("="), skips)


def test_a_settings_refusal_names_its_first_20_problems_and_counts_the_rest():
    """Step 4.42b: a settings table refused for many reasons (a handed file
    of a million unknown toggles) says the first 20 and how many more, as
    the writer's refusals do, not a line as large as the table; its
    ``problems`` keep every one."""
    from azurkit.tools.randomizer.planner.settings import SettingsError

    skips = {sid: s for sid, (_, s) in loader.load_database(TOYDB).skips.items()}
    with pytest.raises(SettingsError) as refused:
        settings_from_table(layer.settings_doc(Settings(0, "hard", {})) | {
            "skip_override": {f"t1.none_{k:02}": True for k in range(25)}}, skips, "settings file")
    said = str(refused.value)
    assert (len(refused.value.problems), said.count("the database has no such skip"), said.endswith(
        "; ... and 5 more"), "t1.none_19" in said, "t1.none_20" in said) == (25, 20, True, True, False), said


def test_a_settings_file_nested_too_deep_or_too_large_is_refused_by_name(tmp_path, capsys):
    """Step 4.42b (D992): a settings file nested past the TOML parser's
    stack is refused as not TOML, by the file's name, where its
    RecursionError reached no host as a refusal; one past
    ``layer.MAX_SETTINGS`` characters (a file with every toggle is about
    1.4 KB) is refused before it is parsed. The tab's Load settings and the
    command line's --settings both."""
    deep, large = "a = " + "[" * 5000 + "]" * 5000, "#" * (layer.MAX_SETTINGS + 1)
    for text, why in ((deep, "not TOML (nested too deep)"), (large, "more than a settings file holds")):
        with pytest.raises(ValueError, match=f"^settings file: .*{re.escape(why)}"):
            sdk.randomizer_settings({"file": text})
    path = tmp_path / "deep.toml"
    path.write_text(deep, encoding="utf-8")
    assert cli.main(["plan", "--seed", "2", "--settings", str(path)]) == 1
    assert capsys.readouterr().err == f"azurkit: --settings {path}: not TOML (nested too deep)\n"


def test_a_skip_batch_is_one_pick_and_a_variant_id_in_a_file_string_or_flag_stands_for_its_batch(tmp_path):
    """D275 (Step R1.31): skips that cross the same thing and differ only in
    kit are variants of one batch (``batch``, ``batch_name``). A settings
    file, a share string and its registry name the batch; a toggle on it
    turns on its in-logic variants, and the ceiling admits each by its own
    tier. An old per-variant id, in a settings file or a share string made
    for the per-variant registry, loads as its batch, on when any of its
    ids is; a variant's id in ``--skip`` or ``--no-skip`` turns its batch
    over a file's toggle, and both on one batch are refused. A batch whose
    variants cross other things is refused (``bad_batch``)."""
    import argparse
    import shutil

    from azurkit.tools.randomizer.planner.settings import SettingsError, skips_on

    root = tmp_path / "db"
    shutil.copytree(TOYDB, root)
    batch = 'batch = "t1.walls"\nbatch_name = "The wall"\n'
    hard = ('[[skip]]\nid = "t1.wall_skip_hard"\nname = "Wall Skip (hard)"\n{level}tricks = ["jumpy"]\n'
            'requires = "true"\ndifficulty = 3\nstatus = "in_logic"\nconfirmed = {{ by = "owner", ref = "toy" }}\n'
            'from = "t1_start"\nto = "t1_vault"\ngates = ["t1.wall"]\n' + batch + "{tricks}\n")
    for rel, lone, extra in (
            ("levels/t1.toml", 'gates = ["t1.wall"]\n', hard.format(level="", tricks="")),
            ("tricks.toml", 'name = "Wall Skip"\n', hard.format(level='level = "t1"\nbypasses = "the wall"\n', tricks=(
                'difficulty_reason = "toy"\nconfidence = "toy"\nevidence = []\nsource = "toy"\nd145 = "toy"\n')))):
        text = (root / rel).read_text(encoding="utf-8")
        (root / rel).write_text(text.replace(lone, lone + batch, 1) + "\n" + extra, encoding="utf-8")
    db = loader.load_database(root)
    skips = {sid: s for sid, (_, s) in db.skips.items()}
    assert picks(skips) == {"t1.held_skip": ["t1.held_skip"], "t1.manual_skip": ["t1.manual_skip"],
                            "t1.walls": ["t1.wall_skip", "t1.wall_skip_hard"]}
    walls = Settings(0, "hard", {"t1.walls": True})
    assert [skips_on(st, skips) for st in (Settings(2, "hard", {}), walls)] == [
        ["t1.wall_skip"], ["t1.wall_skip", "t1.wall_skip_hard"]]
    assert share_decode(share_encode(walls, skips), skips) == walls
    old = share_encode(Settings(0, "hard", {"t1.wall_skip_hard": True}), list(skips))   # its registry: every id
    path = tmp_path / "old.toml"
    path.write_text(layer.settings_text(walls).replace('"t1.walls" = true', '"t1.wall_skip" = false\n'
                                                       '"t1.wall_skip_hard" = true'), encoding="utf-8")
    assert [share_decode(old, skips), layer.read_settings(path, skips)] == [walls, walls] and old != share_encode(
        walls, skips)
    flags = argparse.Namespace(settings=str(path), no_skip=["t1.wall_skip_hard"])
    assert layer.settings_from_args(flags, db).skip_override == {"t1.walls": False}
    with pytest.raises(SettingsError, match="skip_override.t1.walls: both --skip and --no-skip"):
        layer.settings_from_args(argparse.Namespace(**vars(flags), skip=["t1.wall_skip"]), db)
    (root / "levels/t1.toml").write_text((root / "levels/t1.toml").read_text(encoding="utf-8").replace(
        'gates = ["t1.wall"]\nbatch', 'gates = []\nbatch', 1), encoding="utf-8")
    assert [(i.code, i.detail) for i in loader.check_database(root).issues if i.code == "bad_batch"] == [
        ("bad_batch", "its variants' gates differ")]


def test_the_tracker_table_sums_each_kind_collected_and_left_and_names_no_unseen_item_without_the_spoiler():
    """Step R1.26 (D249, the owner: "a table tab that shows a table of the
    collectibles, summing up how many we collected and how many are
    left"): the items tree sums the golden plan's 203 tracked items by kind
    (the base game's multiset: 20 fragments, 20 powers, 39 keys, 100
    obsidians, 23 fuel, 1 health) and the levels tree its spots by realm
    and level, each with All last; a mark moves its kind's and its level's
    rows by one. With Spoiler off no row says where an item not collected
    lies: no item row's Now or Where, and a level's rows are its spot
    classes (what the maps' tips name), not its items' groups. The game's
    own counts (a live tracker's) fill the item rows they name."""
    from azurkit.tools.randomizer.tracker import Tracker

    def rows(found):
        for row in found:
            yield row
            yield from rows(row.children)

    lg = kept_logic()
    plan = load_plan(PLANS["default"]["plan"], lg.db)
    t = Tracker(lg, plan.settings, plan.placement)
    items, levels = t.table(spoiler=False)
    by = lambda found: {r.key: r for r in rows(found)}
    sums = lambda found, *keys: [(by(found)[k].got, by(found)[k].left, by(found)[k].total) for k in keys]
    assert [r.key for r in items] == ["frag", "power", "key", "obsidian", "consumable", "all"]
    assert sums(items, "frag", *(f"frag/{e}" for e in ("air", "water", "fire", "earth", "life")), "power", "key",
                "obsidian", "consumable/fuel", "consumable/health", "all") == [
        (0, 20, 20), *[(0, 4, 4)] * 5, (0, 20, 20), (0, 39, 39), (0, 100, 100), (0, 23, 23), (0, 1, 1), (0, 203, 203)]
    assert [(r.label, r.total) for r in levels] == [("Air", 37), ("Earth", 45), ("Fire", 46), ("Water", 30),
                                                    ("Death", 14), ("Life", 3), ("Town", 28), ("All", 203)]
    assert {r.now for r in rows(items)} == {None} and {r.where for r in rows(items)} == {""}
    assert [r.label for r in by(levels)["a1"].children] == ["Item spots", "Obsidian spots", "Fuel or health spots"]

    water = next(loc for loc in sorted(t.spots) if t.item(loc) == "power_water")
    t.toggle(water)
    items, levels = t.table(spoiler=False)
    level = lg.pool[water]
    assert sums(items, "power", "power/water", "all") == [(1, 19, 20), (1, 2, 3), (1, 202, 203)]
    assert by(items)["power/water"].label == "Water (level 1)"
    assert sums(levels, level, "all") == [(1, by(levels)[level].total - 1, by(levels)[level].total), (1, 202, 203)]

    items, levels = t.table(spoiler=True, held={"obsidian": 7})
    air = sorted({lg.pool[loc] for loc in t.spots - t.collected if t.item(loc).startswith("frag_air")})
    assert None not in {r.now for r in rows(items)} and by(items)["all"].now == len(t.reachable)
    assert by(items)["frag/air"].where == ", ".join(air) and "Powers" in [r.label for r in by(levels)[level].children]
    assert (by(items)["obsidian"].game, by(items)["key"].game, by(items)["key/lens"].game) == (7, None, None)


def test_a_map_tip_names_each_way_a_spot_is_reached_by_not_one_of_them_as_the_need():
    """AZ-432 (Step 2.85b): what reaching a spot's node from its level's
    arrivals needs kept whichever counters it failed to drop, in
    alphabetical order, so it named one way of several as the need: f3's
    r1002 "needs 3 fire1 keys" though air 3 reaches it with none, and e2's
    r2955 "needs 2 circuitboard keys + water 1" though the golden plan
    collects it holding none. It names each way, a lower threshold of the
    same counter too: f4's r1289 said "needs air 3" though air 2 + water 2
    reaches it. Each level's map names it on each spot (Modkit's map tips,
    ``item_needs``: ``tracking.world``'s maps, which the page draws as the
    spot's tip's second line), from ``spot_needs.json``, which holds what
    ``needs.spot_needs`` says of every spot now (``scripts/spot_needs.py``;
    the reach, the spot's own requirement and its darkness, then its
    gates)."""
    spots = {loc: words for m in tracking.world()["maps"]["levels"].values() for loc, words in m["spots"].items()}
    assert [spots["f3/g0/r1002"], spots["e2/g0/r2955"], spots["f4/g0/r1289"]] == [
        "needs 3 fire1 keys or air 3",
        "needs (2 circuitboard keys + water 1) or (fire 1 + water 1) or (air 1 + 2 circuitboard keys)",
        "needs air 3 or (air 2 + water 2)"]
    shipped = needs.shipped_spot_needs()
    assert spots.items() <= shipped.items() and needs.spot_needs() == shipped


@pytest.mark.parametrize("walk, tier", ((0.995, "standard"), (0.9, "safe")), ids=("walk-0.995", "walk-0.9"))
def test_a_run_under_garret4s_plans_the_tier_its_sliders_play_as_never_refused(walk, tier):
    """AZ-606 (Step 2.133, D35): a run under garret4's 7 m/s (the walk
    slider under 1, a worn body's size folded into it) once found no plan
    from about x0.975, and randomize-full raised "no plan" though movement
    only flags. Since D1066 its sliders pick the tier its seed is filled at
    (x0.995 Standard's, x0.9 Safe's), its share string recording them, and
    the build is flagged by D1064's moved sliders, never refused."""
    from azurkit.tools.randomizer import movement

    sliders = {"player_physics": {"walk_speed_scale": walk}}
    prepared = generator.prepare({"seed": "2"}, sliders)
    shared = share_decode(prepared.recipe["share"], kept_logic().skip_tables)
    assert (shared.sliders, movement.tier_of(shared), prepared.plan.doc["seed"]) == (sliders, tier, "2")
    assert generator.movement_reasons(sliders, sdk.catalog()["packs"])[0] == (
        f"you moved sliders (player_physics walk_speed_scale {walk:g}), and {movement.PROMISE}")


def test_writer_never_writes_an_exit_or_spot_string(usa_iso):
    """Exits stay vanilla in v1 (§5.2 item 9): no byte the writer changes
    lies in a levelSwitch's movie, destination or spot field (+0x18,
    +0x20, +0x28) or in a playerLocation's name (+0x1C), or in the
    strings they name; a placement naming an exit or a spot is refused by
    name. Every byte it changes is a repointed location's name field, a
    new string in its graph's gap or that graph's TOC size: never a town
    vault generator's attributes (AZ-280: the old writer set its
    ``maxGenerated`` to 0.5, so the vault respawned its item). Writing
    the plan again over the written files is refused too (each target is
    checked against vanilla first), and changes nothing. The plan swaps
    across w1 and town (Modkit's sitting's): staff and ammo into two
    power_life vaults, the vaults' own items moved on, key_life1 into town
    and a power_life onto w1's keylord slot (one new string in each graph),
    an obsidian and a sapphire onto each other's spots."""
    placement = {"town/g1/r15": "power_staff1", "town/g1/r65": "power_ammo", "town/g1/r90": "power_life",
                 "town/g1/r240": "key_life1", "town/g1/r1611": "sapphire",
                 "w1/g0/r1717": "power_life", "w1/g0/r1976": "obsidian"}
    db = kept_logic().db

    def strings(data: bytes, lid: str, fields: tuple[int, ...]) -> list[range]:
        """The bytes of a record's (length, ref) string fields and of the strings they name."""
        g, rec = (int(part[1:]) for part in lid.split("/")[1:])
        e = [t for t in nodes.parse_toc(data) if t.tag == "node"][g]
        ro = e.file_offset + nodes.record_offsets(memoryview(data)[e.file_offset:e.file_offset + e.size])[rec]
        out = []
        for f in fields:
            n, ref = struct.unpack_from("<Ii", data, ro + f)
            out += [range(ro + f, ro + f + 8)] + ([range(ro + f + 4 + ref, ro + f + 4 + ref + n + 1)] if n else [])
        return out

    with iso.Reader(usa_iso) as r:
        files = {f"{s}.xbr": bytearray(r.read(f"gamedata/{s}.xbr")) for s in ("w1", "town")}
    vanilla = {name: bytes(buf) for name, buf in files.items()}
    writer.write_plan(files, placement, db)
    locs = writer._locations(db)
    for name, buf in files.items():
        doc = db.generated[name.removesuffix(".xbr")]
        guarded = [r for x in doc["exits"] for r in strings(vanilla[name], x["id"], (0x18, 0x20, 0x28))]
        guarded += [r for x in doc["spots"] for r in strings(vanilla[name], x["id"], (0x1C,))]
        changed = [k + i for k in range(0, len(buf), 4096) if buf[k:k + 4096] != vanilla[name][k:k + 4096]
                   for i, (a, b) in enumerate(zip(buf[k:k + 4096], vanilla[name][k:k + 4096])) if a != b]
        assert guarded and changed and [k for k in changed if any(k in r for r in guarded)] == []
        allowed = set()
        for edit in (e for e in writer.layout(placement, db).values() if f"{e.file}.xbr" == name):
            entry = nodes.parse_toc(vanilla[name])[edit.toc_index]
            at = entry.file_offset + entry.size + (-(entry.file_offset + entry.size)) % 4
            row = nodes.TOC_START + nodes.TOC_ROW_SIZE * edit.toc_index
            allowed |= {*range(at, at + edit.used), *range(row + 4, row + 8)}
            allowed |= {o for lid in edit.repoint for o in range(locs[lid]["name_ref"]["field"],
                                                                 locs[lid]["name_ref"]["field"] + 8)}
        assert set(changed) <= allowed
    doc = db.generated["w1"]
    for lid in (doc["exits"][0]["id"], doc["spots"][0]["id"]):
        with pytest.raises(writer.WriteError, match=f"{lid}: no pool location"):
            writer.write_plan(files, {lid: "power_air"}, db)
    written = {name: bytes(buf) for name, buf in files.items()}
    with pytest.raises(writer.WriteError, match="w1/g0/r1976 is not a vanilla sapphire critterGenerator"):
        writer.write_plan(files, placement, db)
    assert {name: bytes(buf) for name, buf in files.items()} == written


def test_writer_refuses_a_placement_it_cannot_write():
    """Each refusal is named, all at once, before any file is read (D35):
    a location that isn't in the pool, an item ``items.toml`` doesn't
    define, a guardian slot given another item (D81), and a graph whose
    distinct new strings cost more than its gap (f3's 280 B, the smallest:
    the new-string budget, plan §5.2). An item equal to the vanilla one
    costs nothing."""
    db = kept_logic().db
    f3 = [loc for loc in db.generated["f3"]["locations"] if loc["pool"] and loc["id"].startswith("f3/g0/")]
    present = {loc["template"] for loc in f3}
    names = sorted((it["name"] for it in db.items["item"] if it["name"] not in present and "base" not in it),
                   key=lambda n: (-len(n), n))
    flood = {loc["id"]: name for loc, name in zip(f3, names)}
    assert sum(map(writer.string_cost, flood.values())) > 280 > writer.string_cost(names[0])
    placement = {**flood, "e5/g0/r3294": "power_air", "training_room/g2/r230": "obsidian",
                 "w1/g0/r1976": "no_such_item", "w1/g0/r1978": "sapphire"}
    with pytest.raises(writer.WriteError) as err:
        writer.layout(placement, db)
    assert err.value.problems == [
        "e5/g0/r3294: a guardian slot keeps its vanilla frag_earth_4 (D81)",
        "training_room/g2/r230: no pool location (only pool locations are written; never an exit or a spot)",
        "w1/g0/r1976: items.toml defines no 'no_such_item'",
        f"f3/g0: {len(flood)} new strings take {sum(map(writer.string_cost, flood.values()))} B, over its 280 B gap "
        "(the new-string budget, plan §5.2)"]
    assert writer.layout({"w1/g0/r1978": "sapphire"}, db) == {}


def test_obsidian_cost_accepts_a_fractional_cost(tmp_path, monkeypatch):
    """``--obsidian-cost`` was ``type=int`` in Modkit, so argparse refused
    2.5 although the lock thresholds are float cells: ``azurkit build``
    hands 2.5 to the build's randomizer as it is, which takes it (D23)."""
    seen = []

    def build(made, out, picked=None):   # the recipe the flags made; no image is read
        seen.append(made)
        raise ValueError("stopped before the build")
    monkeypatch.setattr(sdk, "build", build)
    assert cli.main(["build", "--iso", "x.iso", "--out", str(tmp_path / "out.iso"), "--seed", "2",
                     "--obsidian-cost", "2.5"]) == 1
    assert seen[0]["randomizer"] == {"seed": "2", "obsidian_cost": 2.5}
    assert generator.normalize(seen[0]["randomizer"])["obsidian_cost"] == 2.5
