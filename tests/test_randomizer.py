"""The randomizer against Modkit (``tests/oracle/rando/``): its planner
(Step 4.2a; ``rando_plans.json``: seed 2 under the strict, default and max
settings gives Modkit's attempt and plan sha256, and the default plan file
is Modkit's byte for byte, on CPython and under Pyodide, the site's runtime)
and its generator layer (Step 4.2b): G3's seed cases build Modkit's files
and image on both releases (``pipelines.json``, ``rando_iso.json``) and the
default case's spoiler is Modkit's ``--spoiler`` file of its plan, a
later layer over a placement is a conflict and any other difference a
failure, and movement sliders plan on the logic re-checked under them;
the Randomizer tab's settings (Step 4.2c1); the item tracker's verdicts
(Step 4.2c2), Modkit's at several states."""

from __future__ import annotations

import functools
import hashlib
import json
import math
import struct

import pytest

from azurkit import cli, sdk
from azurkit.core import iso
from azurkit.tools import mods, randomizer
from azurkit.tools.randomizer import generator, layer, tracking, writer
from azurkit.tools.randomizer.planner.fill import settings_table
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.settings import (
    Settings, picks, settings_from_table, share_decode, share_encode, turnable)
from scripts.oracle_sync import ORACLE

RANDO = ORACLE / "rando"
PLANS = json.loads((RANDO / "tests/goldens/rando_plans.json").read_text(encoding="utf-8"))
CASES = json.loads((RANDO / "cases.json").read_text(encoding="utf-8"))
DEFAULT_PLAN = json.dumps(PLANS["default"]["plan"], indent=1, sort_keys=True) + "\n"   # Modkit's plan file
G3 = {"usa": "tests/goldens/pipelines.json", "europe": "tests/goldens/europe/pipelines.json"}
JUMP = {"player_physics": {"jump_speed_scale": 1.3}}


def _golden(rel: str) -> dict:
    return json.loads((RANDO / rel).read_text(encoding="utf-8"))


def _recipe(case: dict) -> dict:
    """An oracle case (Modkit's seed and ``Settings`` fields) as the sdk's
    recipe, its settings as a settings file holds them."""
    st = case["settings"]
    return {"seed": case["seed"], "settings": settings_table(Settings(
        st["skip_ceiling"], st["movement_tier"], st["dark_fire"], st["skip_override"],
        frozenset(st["exclude_categories"]), st["sliders"]))}


@functools.cache
def _profile(name: str) -> dict:
    """Seed 2's plan file's object under the oracle's ``name`` settings (strict, default or max)."""
    return sdk.plan(_recipe(CASES["tests/goldens/rando_plans.json"][name]))


def _share(sliders: dict) -> str:
    skips = {sid: s for sid, (_, s) in kept_logic().db.skips.items()}
    return share_encode(Settings(0, "standard", 1, {}, sliders=sliders), skips)


def test_seed_2s_plan_under_each_profile_is_modkits_and_the_default_plan_file_byte_for_byte(capsys):
    cases = CASES["tests/goldens/rando_plans.json"]
    assert sorted(cases) == ["default", "max", "strict"] and PLANS["seed"] == "2"
    for name in cases:
        doc = _profile(name)
        assert (doc["attempt"], doc["sha256"]) == (PLANS[name]["attempt"], PLANS[name]["sha256"]), name
    assert cli.main(["plan", "--seed", "2"]) == 0        # the database's defaults are the default profile's
    assert capsys.readouterr().out == DEFAULT_PLAN


def test_a_plan_reads_back_into_its_spoiler_and_what_the_randomizer_cant_take_is_refused_by_name():
    """The default plan's spoiler names its share string and each sphere;
    an edited plan, a recipe with both settings and a share string, a build
    recipe's unknown key, settings with a share string, or an obsidian cost
    whose thresholds a float32 can't hold are refused, each by name."""
    lines = sdk.spoiler(PLANS["default"]["plan"])["lines"]
    assert any(PLANS["default"]["plan"]["share"] in line for line in lines)
    assert any(line.lower().startswith("sphere") for line in lines)
    edited = PLANS["default"]["plan"] | {"seed": "3"}
    with pytest.raises(ValueError, match="edited plan"):
        sdk.spoiler(edited)
    with pytest.raises(ValueError, match="settings and share both"):
        sdk.plan({"seed": "2", "settings": {}, "share": "AZR-AAEA"})
    for given, why in (({"seed": "2", "plan": {}}, r"no key 'plan'"), ({"seed": 2}, "seed is a string"),
                       ({"seed": "2", "settings": {}, "share": "AZR-AAEA"}, "settings and share both"),
                       ({"seed": "2", "obsidian_cost": math.nan}, "obsidian_cost nan"),
                       ({"seed": "2", "obsidian_cost": 1e38}, "finite float32s")):
        with pytest.raises(ValueError, match=why):
            sdk.image({"iso": "x.iso", "randomizer": given})


def test_the_tab_reads_its_settings_and_share_strings_flags_what_a_build_leaves_unverified_and_a_link_carries_it():
    """Step 4.2c1: the Randomizer tab starts at D144's defaults (the
    database's), whose share string is Modkit's; the settings it holds
    (format /2: each category as it is) give back the same settings and a
    share string that decodes to them, each skip a setting can turn on (by
    pick, D275) with the ceiling's state and its toggle, and the picks held.
    A share string made with other movement sliders is named; keeping the
    obsidians vanilla is the preflight's refusal (AZ-454); a roll slider
    the logic doesn't model and an obsidian cost above vanilla's leave a
    build unverified (D83(c)). A share link carries the randomizer and a
    page's remembered setup keeps it (D915), each refused by name when a
    setting is. Step 4.2c2: each item row counts what the base game places
    (Modkit 3befd6336's ``rando_view.base_counts``, the step's evidence);
    every skip of the database has its D258 group (a new one needs its
    group, Modkit's ``SKIP_GROUP``); the tab's settings file (D144's Save
    settings) loads back to its settings, and a file that isn't one is
    refused by name."""
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
    starved = options["defaults"] | {"exclude_categories": ["obsidians"]}
    assert sdk.randomizer_settings({"settings": starved})["preflight"].startswith("exclude_categories keeps")
    flagged = sdk.randomizer_settings({"settings": options["defaults"], "obsidian_cost": 20,
                                       "packs": {"player_physics": {"roll_speed_scale": 0.5}}})["why_not"]
    assert flagged == [generator.movement_reasons({"player_physics": {"roll_speed_scale": 0.5}},
                                                  sdk.catalog()["packs"])[0], layer.obsidian_reason(20.0)]

    rando = {"seed": "2", "settings": given, "obsidian_cost": 20.0}
    found = sdk.preset_decode(sdk.preset_encode({"packs": {}, "randomizer": rando}))
    assert found["layers"][0] == {"tool": "randomizer", "kind": "plan", "recipe": rando}
    assert sdk.read_mods(sdk.preset_encode({"packs": {}, "randomizer": rando}))["randomizer"] == rando
    kept = {"on": True, "seed": "2", "settings": given, "obsidian_cost": 20.0}
    assert sdk.restore({"ticked": [], "randomizer": kept})["randomizer"] == kept
    bad = given | {"dark_fire": 9}
    for refused in (lambda: sdk.preset_encode({"packs": {}, "randomizer": {"seed": "2", "settings": bad}}),
                    lambda: sdk.randomizer_settings({"settings": bad})):
        with pytest.raises(ValueError, match="dark_fire: 9 is not 1-3"):
            refused()
    assert sdk.restore({"ticked": [], "randomizer": kept | {"settings": bad}})["dropped"] == [
        "the randomizer's settings (settings: dark_fire: 9 is not 1-3)"]


def test_movement_sliders_plan_on_the_logic_rechecked_under_them_and_the_packs_catalog_flags_the_rest():
    """A share string's movement sliders (AZ-383) plan on the logic
    re-checked under them, and its plan reads back into its spoiler; a build
    with those sliders plans the same, its logic unverified where what the
    nodes stand on breaks, and refuses a share string made for other
    sliders. The packs' catalog gives each slider's ``logic_floor``: past
    it, a slider the logic doesn't model leaves the logic unverified, as
    does a speed slider at 0 or less (D83(c))."""
    share = _share(JUMP)
    doc = sdk.plan({"seed": "2", "share": share})
    assert doc["share"] == share and doc["sha256"] != PLANS["default"]["sha256"]
    assert any(share in line for line in sdk.spoiler(doc)["lines"])
    built = generator.prepare({"seed": "2"}, JUMP)
    assert (built.plan.doc["sha256"], built.recipe) == (doc["sha256"], {"seed": "2", "share": share})
    assert built.why_not and all(why.startswith("node ") for why in built.why_not)
    with pytest.raises(layer.LayerError, match="holds the movement sliders player_physics jump_speed_scale 1.3"):
        generator.prepare({"seed": "2", "share": share}, {})
    packs = {"player_physics": {"roll_speed_scale": 0.5, "climb_speed_scale": 0.0} | JUMP["player_physics"],
             "enemy_scaling": {"boss_health_scale": 2.0}}
    assert generator.movement_reasons(packs, sdk.catalog()["packs"]) == [
        "player_physics roll_speed_scale 0.5 is below vanilla's 1, movement the logic doesn't model (D83(c))",
        "player_physics climb_speed_scale 0 is a lock, not a speed: " + layer.LOCKS["player_physics",
                                                                                    "climb_speed_scale"],
        "enemy_scaling boss_health_scale 2 is above vanilla's 1, enemy strength the logic doesn't model (D83(c))"]


@pytest.mark.parametrize("release, case", [
    pytest.param("usa", "randomize-full:seed=2,default", marks=pytest.mark.vanilla),
    pytest.param("usa", "randomize-full:seed=2,ceiling2", marks=pytest.mark.vanilla),
    pytest.param("europe", "randomize-full:seed=2,default", marks=[pytest.mark.vanilla, pytest.mark.europe])])
def test_g3s_seed_cases_build_modkits_files_and_image_and_open_back_into_their_recipe(release, case, request):
    """G3's seed cases (J1's model-free seed case on both releases): the
    packs on by default and the plan of Modkit's seed and options, through
    the CLI's recipe, change each file the golden names to its sha256 and
    no other (Europe's golden names its own files; its XBRs are the USA
    case's), the image less its root entries is Modkit's (``rando_iso``:
    the recorded default plan's), the image reads back to the plan with
    its logic verified, its report carrying the plan (the tracker's), and
    the build opens back into its recipe."""
    path = request.getfixturevalue(f"{release}_iso")
    args = CASES[G3[release]][case]["args"]
    options = {k: args[k] for k in ("skip_ceiling", "movement_tier", "dark_fire") if args[k] is not None}
    settings = layer.settings_doc(kept_logic().db.defaults) | options
    given = {"seed": args["seed"]} | ({"settings": settings} if options else {})
    made, report = sdk.image(cli.recipe(str(path), [], [], True, randomizer=given))
    golden = _golden(G3[release])[case]
    want = {f: sha for f, sha in (_golden(G3["usa"])[case] | golden).items() if f != "ISO"}
    assert report["result"] == want and report["conflicts"] == []
    plan = report["randomizer"]
    assert (plan["seed"], plan["logic_verified"], plan["why_not"], plan["conflicts"]) == ("2", True, [], [])
    with iso.Reader(made) as r:
        files = {file: r.read(file) for file in report["result"] if file != "filelist.txt"}
    assert iso.read(path, files).sha256() == golden["ISO"]
    if (release, case) == ("usa", "randomize-full:seed=2,default"):
        assert {"plan": plan["plan"], "usa": golden["ISO"]} == {k: _golden("tests/goldens/rando_iso.json")[k]
                                                                 for k in ("plan", "usa")}
        lines = sdk.spoiler(PLANS["default"]["plan"])["lines"]   # Modkit's default plan file: its --spoiler file
        assert report["spoiler"] == "\n".join([lines[0], "logic_verified: true", *lines[1:]]) + "\n"
        assert report["plan"] == PLANS["default"]["plan"]   # the tracker's (Step 4.2c2)
    found = sdk.read_mods(sdk.open_build(made, whole=False))
    assert found == {"packs": mods.normalize({n: {} for n, p in mods.PACKS.items() if p.default_on}),
                     "randomizer": {"seed": "2", "share": plan["share"]}}


def test_a_later_layer_over_a_placement_is_a_conflict_and_any_other_difference_fails_the_build(usa_iso):
    """The plan's layer is each node graph it edits, whole, and the
    obsidian cost's lock thresholds (x1 to x10 in both of town.xbr's
    tables; above vanilla's, the logic is unverified). An ``xbr`` operation
    over a placement's name field drops its graph (D28): the build goes on,
    its logic unverified, each changed placement of that graph a conflict
    naming the later layer. An image that doesn't hold the plan (the
    vanilla one) fails the read-back, by location (D35)."""
    prepared = generator.prepare({"seed": "2", "obsidian_cost": 20.0}, {})
    with iso.Reader(usa_iso) as r:
        base = {file: r.read(file) for file in generator.files(prepared)}
    planned = generator.plan_layer(prepared, base)
    groups = {c.group for c in planned.changes}
    assert groups == {f"randomizer {key}" for key in prepared.edits} | {generator.OBSIDIAN_GROUP}
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
    _, report = sdk.image({"iso": str(usa_iso), "randomizer": {"seed": "2", "obsidian_cost": 20.0}, "xbr": [op]})
    plan = report["randomizer"]
    assert plan["logic_verified"] is False and plan["why_not"][0] == layer.obsidian_reason(20.0)
    assert plan["why_not"][-1] == f"{len(plan['conflicts'])} placement(s) changed by a later layer"
    assert len(plan["conflicts"]) == sum(1 for loc in edit.repoint) and all(
        line.startswith(f"{edit.key}/") and line.endswith("data xbr wrote it after the randomizer (D28)")
        for line in plan["conflicts"])
    assert [c for c in report["conflicts"] if f"whose group randomizer {key} is dropped whole" in c]


def test_the_default_plan_file_is_modkits_byte_for_byte_under_pyodide(pyodide):
    got = pyodide("plan", "--seed", "2")
    assert (got["code"], got["stderr"]) == (0, ""), got["stderr"][-2000:]
    assert got["stdout"] == DEFAULT_PLAN


# Modkit 3befd6336's tracker on seed 2's default and max plans, each state with the spoiler off and on: the
# sha256[:32] of each view (tracking.digest: the marks, the counter row, each spot's state and item, the Table),
# from $EV/azurkit-4.2c2-2026-10-29/verdicts.py on Modkit's own Tracker (results/verdicts-modkit.json)
TRACKER = {
    "default/kit/plain": "ce3571fe88c962f21c7e09d138dac973",
    "default/kit/spoiler": "bf87656a7108cee3227c030710b11feb",
    "default/mid/plain": "855469adebcf58a4d0e99376cf684d07",
    "default/mid/spoiler": "fafe347a9ba2ca1c664f2cd939e516b0",
    "default/none/plain": "41630c81ddcd3ff9c0b1a9955fb979a1",
    "default/none/spoiler": "99feb6f24dc6f54118e0a99c1ebe8cb8",
    "default/powers/plain": "ff16075ece7b8e4ccebe2c341fb1c3c6",
    "default/powers/spoiler": "6ba1171bab858407a9cf0fc226c67517",
    "max/kit/plain": "2a4d9249a20132ded813953bbb9b461b",
    "max/kit/spoiler": "44e5c5bafc8404762f3f772539117991",
    "max/mid/plain": "76d678657e5911f31cfa1f7e182c86c5",
    "max/mid/spoiler": "405647d58558dfc66092980d4350287b",
    "max/none/plain": "cf52424a1d9faa63de7be95f307dec2a",
    "max/none/spoiler": "6d9496c6c8698564fe23472f4877c33e",
    "max/powers/plain": "6dd4c7184fe0aaa17f7c4ca6cbbad22b",
    "max/powers/spoiler": "106b13abcc619b74194430a5a1b8f6e4",
}
KIT = {"air": 3, "water": 3, "fire": 3, "earth": 3}


def tracker_states(view, doc: dict):
    """(state, marks, kit) of :data:`TRACKER`'s states for ``doc``, through
    ``view(doc, marks, spoiler)`` (a host's tracker): none, no mark; mid,
    three rounds of marking every spot reachable now; powers, every spot the
    plan put a power at; kit, no mark and Live's kit at air, water, fire and
    earth 3."""
    mid = []
    for _ in range(3):
        spots = view(doc, {"collected": mid}, False)["spots"]
        mid = sorted(set(mid) | {loc for loc, s in spots.items() if s["state"] in ("near", "skip")})
    powers = sorted(loc for loc, s in view(doc, None, True)["spots"].items() if s["item"].startswith("power_"))
    return [("none", None, None), ("mid", {"collected": mid}, None), ("powers", {"collected": powers}, None),
            ("kit", None, KIT)]


def test_the_trackers_verdicts_are_modkits_at_each_state_and_a_click_marks_what_it_names():
    """Step 4.2c2 (D189, D249): the item tracker (Modkit's ``Tracker``,
    installed by the oracle sync) on seed 2's default and max plans gives
    Modkit's verdicts (:data:`TRACKER`) with nothing marked, after three
    rounds of marking every spot reachable now, with every power marked
    and with Live's kit at every element 3 (R1.41: the reach holds the
    levels the game holds), the spoiler off (no item a spot holds is given
    until it is collected) and on. A click marks a spot and a second takes
    it off; a click on a live mark vetoes it (Live won't mark it again);
    Reset clears both; a spot or plan it doesn't know, or a kit it can't
    hold, is refused by name."""
    def view(doc, marks, spoiler, kit=None):
        return sdk.tracker({"plan": doc, "marks": marks, "kit": kit, "spoiler": spoiler})

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
    assert plain["head"]["text"].startswith(f"Seed 2 · {doc['share']} · skips None, movement standard")
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
