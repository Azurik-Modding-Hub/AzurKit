"""The randomizer against its goldens (``tests/goldens/``, which
``scripts/record_goldens.py`` records from AzurKit's own planner; the first
recording, Step 4.12b, was Modkit's at oracle-rando-6): its planner (Step
4.2a; ``rando_plans.json``: seed 2 under the strict, default and max
settings gives its attempt, plan sha256 and spoiler, and the default plan
file byte for byte, on CPython and under Pyodide, the site's runtime, the
same in two processes under two hash seeds) and its generator layer (Step 4.2b): G3's seed cases build their files
and image on both releases (``pipelines.json``) and the default case's
spoiler is the ``--spoiler`` file of its plan, a later layer over a
placement is a conflict and any other difference a failure, and movement
sliders plan on the logic re-checked under them; the Randomizer tab's
settings (Step 4.2c1); the item tracker's verdicts (Step 4.2c2) at
several states and the maps' model of each (``tracker.json``); the
checked database the wheel and the app ship (Step 4.3g); R2.1's solver
(Step 4.3u): RS1's 80 plans as the solver before it made them and the
grammar's monotone rules it rests on."""

from __future__ import annotations

import functools
import gc
import hashlib
import json
import math
import os
import random
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from azurkit import cli, sdk
from azurkit.core import iso
from azurkit.tools import mods, randomizer
from azurkit.tools.randomizer import dbcache, generator, layer, tracking, writer
from azurkit.tools.randomizer.planner import fill, loader
from azurkit.tools.randomizer.planner.grammar import ParseError, parse
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.settings import (
    Settings, picks, settings_from_table, share_decode, share_encode, turnable)
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
# the hosts' tests (test_site, test_hosts) take these from here: seed 2's plan by case, and tracker.json's states
_profile, tracker_states, shows_gems = record_goldens.profile, record_goldens.tracker_states, record_goldens.shows_gems
# RS1's 80 plans (round 2's R2.1, Step 4.3u): seeds 1 to 20 under four option sets (skip ceiling, movement tier,
# dark_fire; the goldens' strict, default and max and a skip ceiling of 2), each "attempt, the plan's sha256[:12], its
# spoiler lines' sha256[:12]" as the solver before R2.1 made them (AzurKit 3cd8a44, RS1's proof20-A)
OPTIONS80 = {"strict": (0, "safe", 2), "default": (0, "standard", 1), "max": (4, "frame_perfect", 1),
             "ceiling2": (2, "standard", 1)}
PLANS80 = {
    "strict": (
        "0 560d55211d25 af25adac2ba2",
        "0 2c1114ccb4de ccdd50baffda",
        "0 72b01f69ea38 28a6a241d31e",
        "0 65059ebe749a 03f3db9e5ed7",
        "1 9deb3b38e26c f699536f1576",
        "1 8daa3c542547 95cb81521efb",
        "0 0a64449cc22f 4fff5580cf04",
        "0 7505c33a8657 394f9e0d6ead",
        "1 c53fca681a63 c77bed991c87",
        "0 d184d4c6e6e6 1ed182570359",
        "0 d7a1549d9fc7 91670887951b",
        "1 f32d0eb20a56 cd21f987f1f4",
        "0 99c7210abd49 5ccbef2c8839",
        "0 dfd3bc168487 dcc0db762873",
        "0 d24fd97d0d67 9cd83797a4b4",
        "1 bcc1e234892a a855d3573b4f",
        "0 7caabd6060d1 203c732545b3",
        "3 e4ce7987187e a968c8bda3e5",
        "1 dfd573c60472 868fa3c7a9c9",
        "0 201ec9c1acc9 3b91f83d5d75",
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
    lines = sdk.spoiler(doc)["lines"]
    print(doc["attempt"], doc["sha256"][:12], hashlib.sha256("\\n".join(lines).encode()).hexdigest()[:12])
"""


def _share(sliders: dict) -> str:
    skips = {sid: s for sid, (_, s) in kept_logic().db.skips.items()}
    return share_encode(Settings(0, "standard", 1, {}, sliders=sliders), skips)


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
def test_g3s_seed_cases_build_their_goldens_files_and_image_and_open_back_into_their_recipe(release, case, request):
    """G3's seed cases (J1's model-free seed case on both releases): the
    packs on by default and the plan of the case's seed and options,
    through the CLI's recipe, change each file the golden names to its
    sha256 and no other (Europe's golden names its own files; its XBRs are
    the USA case's), the image less its root entries is the golden's (the
    default case's of ``rando_plans.json``'s default plan), the image reads
    back to the plan with its logic verified, its report carrying the plan
    (the tracker's), and the build opens back into its recipe."""
    path = request.getfixturevalue(f"{release}_iso")
    args = record_goldens.cases(G3[release])[case]["args"]
    options = {k: args[k] for k in ("skip_ceiling", "movement_tier", "dark_fire") if args[k] is not None}
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


def test_the_default_plan_file_is_its_goldens_byte_for_byte_under_pyodide(pyodide):
    got = pyodide("plan", "--seed", "2")
    assert (got["code"], got["stderr"]) == (0, ""), got["stderr"][-2000:]
    assert got["stdout"] == DEFAULT_PLAN


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
    got = [(p.wait(timeout=600), *p.communicate()) for p in procs]   # four cold plans at once
    assert got[0] == got[1] and got[0][:2] == (0, DEFAULT_PLAN), got[0][2][-2000:]
    assert got[2] == got[3] and got[2][0] == 0, got[2][2][-2000:]
    assert json.loads(got[2][1])["sha256"] == PLANS["max"]["sha256"]


def test_twenty_seeds_under_four_option_sets_plan_and_spoil_as_the_solver_before_r21_made_them():
    """Step 4.3u (round 2's R2.1): the solver's resumed escapes, its grown
    forward reach and the fill's kept reaches and known traps change no
    plan: each of :data:`PLANS80`'s 80 plans (an option set's 20 seeds in
    a process of its own, the four at once) has its attempt, sha256 and
    spoiler."""
    procs = {name: subprocess.Popen([sys.executable, "-c", _PLANS80, json.dumps(st)], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE) for name, st in OPTIONS80.items()}
    for name, proc in procs.items():
        out, err = proc.communicate(timeout=1800)
        assert proc.returncode == 0, err[-2000:]
        assert tuple(out.splitlines()) == PLANS80[name], name


def test_the_grammar_has_no_negation_and_each_rule_the_solver_compiles_holds_at_any_larger_state():
    """R2.1's exactness rests on monotone rules (a failed escape resumes from
    its fixpoint at a later, larger state; the forward reach grows rather
    than searching again): the grammar refuses a negation however it is
    spelled, and every rule of the default and max options' graphs, logic
    and physical (edges, teleports, locations, credits, victory), that
    holds at a random state holds at any larger one (more of each counter,
    more flags)."""
    for text in ("not water1", "!water1", "~water1", "-water1", "water1 & !fire1", "!(water1)", "water<1",
                 "water<=1", "water!=1", "water==0", "water1 & not(fire1)"):
        with pytest.raises(ParseError):
            parse(text)
    logic, rng = kept_logic(), random.Random(0)
    counters = sorted({c for cs in logic.items.values() for c in cs})
    for st in (logic.db.defaults, Settings(4, "frame_perfect", 1, {})):
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


def test_the_shipped_database_is_a_fresh_checks_holds_no_absolute_path_and_is_the_planners_kept_logic_unwalked(
        tmp_path, monkeypatch):
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
    shipped = web_tools.ship_database(tmp_path)
    blob = shipped.read_bytes()
    assert (shipped.stem, b"pathlib" in blob, str(Path(web_tools.ROOT)).encode() in blob,
            str(Path.home()).encode() in blob) == (dbcache.entry(loader.DATA_DIR).name, False, False, False)
    monkeypatch.setattr(dbcache, "SHIPPED", tmp_path)
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


def test_a_seeds_plan_and_its_first_tracker_view_report_their_stages_and_answer_as_without_them(monkeypatch):
    """Step 4.3 train (D980): Track's bar on both hosts follows the engine's
    work. ``sdk.plan`` reports the logic read, the fill and the placements
    written (``core.progress``'s ``plan``, done of 3), the fill's items
    placed counted inside its step, so the app's bar, polled every 250 ms,
    moves through the seconds the fill takes once the shipped Logic is read
    at once (train B2); the tracker's first view of the plan its tracker
    built and the world map read (done of 2), and a view of a kept plan
    nothing, so a click on a spot shows no bar. Each answers as it does
    without ``progress``."""
    seen = []
    monkeypatch.setattr(fill, "_LAST_FILL", [None])   # the seed's fill not kept from another test: it fills now
    doc = sdk.plan({"seed": "2"}, progress=seen.append)
    assert doc == PLANS["default"]["plan"]
    placing = [r for r in seen if r["label"].startswith("Filling the seed (")]
    ks = [tuple(map(int, r["label"].removeprefix("Filling the seed (placing the items, ").removesuffix(")").split(
        " of "))) for r in placing]
    n = ks[-1][1]
    assert len(ks) > 20 and ks[0] == (1, n) and ks[-1] == (n, n) and all(a < b for (a, _), (b, _) in zip(ks, ks[1:]))
    assert [r["percent"] for r in placing] == sorted(r["percent"] for r in placing) and {
        placing[0]["percent"], placing[-1]["percent"]} == {33, 66}
    seen = [r for r in seen if r not in placing]
    world = tracking.world()
    monkeypatch.setattr(tracking, "world", functools.cache(lambda: world))   # a process's first view reads it
    monkeypatch.setattr(tracking, "_KEPT", type(tracking._KEPT)())
    first, again = (sdk.tracker({"plan": doc}, progress=seen.append) for _ in range(2))
    assert [(r["stage"], r["label"], r["percent"]) for r in seen] == [
        ("plan", "Reading the randomizer's logic", 0), ("plan", "Filling the seed", 33),
        ("plan", "Writing the placements", 66), ("plan", "Reading the seed's logic", 0),
        ("plan", "Reading the world map", 50)]
    assert tracking.digest(first) == tracking.digest(again) == tracking.digest(sdk.tracker({"plan": doc}))


@pytest.mark.web
def test_the_recorder_writes_the_trackers_golden_from_azurkits_own_tracker_and_map_view():
    """``tracker.json`` is what ``scripts/record_goldens.py`` records: each
    state's view from the tracker on CPython and the maps' model the page's
    ``web/mapview.mjs`` draws of it, under Node (the test is ``web``)."""
    made = record_goldens.record(record_goldens.TRACKER, record_goldens.Images())
    assert record_goldens.text(made) == (record_goldens.GOLDENS / record_goldens.TRACKER).read_text(encoding="utf-8")
