"""The randomizer against Modkit (``tests/oracle/rando/``): its planner
(Step 4.2a; ``rando_plans.json``: seed 2 under the strict, default and max
settings gives Modkit's attempt and plan sha256, and the default plan file
is Modkit's byte for byte, on CPython and under Pyodide, the site's runtime)
and its generator layer (Step 4.2b): G3's seed cases build Modkit's files
and image on both releases (``pipelines.json``, ``rando_iso.json``), a
later layer over a placement is a conflict and any other difference a
failure, and movement sliders plan on the logic re-checked under them."""

from __future__ import annotations

import hashlib
import json
import math
import struct

import pytest

from azurkit import cli, sdk
from azurkit.core import iso
from azurkit.tools import mods
from azurkit.tools.randomizer import generator, layer, writer
from azurkit.tools.randomizer.planner.fill import settings_table
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.settings import Settings, share_encode
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


def _share(sliders: dict) -> str:
    skips = {sid: s for sid, (_, s) in kept_logic().db.skips.items()}
    return share_encode(Settings(0, "standard", 1, {}, sliders=sliders), skips)


def test_seed_2s_plan_under_each_profile_is_modkits_and_the_default_plan_file_byte_for_byte(capsys):
    cases = CASES["tests/goldens/rando_plans.json"]
    assert sorted(cases) == ["default", "max", "strict"] and PLANS["seed"] == "2"
    for name, case in cases.items():
        doc = sdk.plan(_recipe(case))
        assert (doc["attempt"], doc["sha256"]) == (PLANS[name]["attempt"], PLANS[name]["sha256"]), name
    assert cli.main(["plan", "--seed", "2"]) == 0        # the database's defaults are the default profile's
    assert capsys.readouterr().out == DEFAULT_PLAN


def test_a_plan_reads_back_into_its_spoiler_and_what_the_randomizer_cant_take_is_refused_by_name():
    """The default plan's spoiler names its share string and each sphere;
    an edited plan, a recipe with both settings and a share string, a build
    recipe's unknown key, settings with a share string, or an obsidian cost
    whose thresholds a float32 can't hold, and a share link of a randomized
    recipe (its tab reads one, Step 4.2c) are refused, each by name."""
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
    with pytest.raises(ValueError, match="share link doesn't carry a randomizer"):
        sdk.preset_encode({"packs": {}, "randomizer": {"seed": "2"}})


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
    its logic verified, and the build opens back into its recipe."""
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
