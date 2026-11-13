"""The randomizer database's dev tools (``devkit/rando``, Step 4.13b: Modkit's ``rando db-extract``, ``rando check``,
``rando_bench.py``, ``rando_impact.py`` and ``rando_soak.py``) and the fixture databases they and the solver's
corpus run on (``devkit/rando/data``: ``toydb``, ``reachdb``, ``escapedb``, ``guardiandb``, ``impactdb`` and the
committed plans in ``plans/valid`` and ``plans/invalid``); and the database itself (Step 4.28e): the loader's
refusals and the planner's mechanisms on those fixtures, and the shipped database's confirmed facts."""

from __future__ import annotations

import argparse
import base64
import dataclasses
import functools
import gzip
import itertools
import json
import random
import shutil
from pathlib import Path

import pytest

from azurkit.core import gate
from azurkit.tools.randomizer import layer
from azurkit.tools.randomizer.planner.fill import FillError, _Slots, fill
from azurkit.tools.randomizer.planner.grammar import parse
from azurkit.tools.randomizer.planner.loader import (
    DATA_DIR,
    REALMS,
    DatabaseError,
    check_database,
    kept_logic,
    load_database,
)
from azurkit.tools.randomizer.planner.settings import (
    MOVEMENT_TIERS,
    SETTINGS_FORMAT,
    Settings,
    SettingsError,
    picks,
    registry_tag,
    settings_from_table,
    share_decode,
    share_encode,
    skips_on,
)
from azurkit.tools.randomizer.planner.solver import Logic
from devkit.rando import bench, check, db_extract, impact, soak
from devkit.rando.draft.author import dnf, term_text

DATA = Path(db_extract.__file__).resolve().parent / "data"
TOYDB = DATA / "toydb"
PLANS = sorted(p for verdict in ("valid", "invalid") for p in (DATA / "plans" / verdict).glob("*.json"))
RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]


def _edit(root: Path, rel: str, old: str | None, new: str) -> None:
    """Replace the one ``old`` in ``rel`` with ``new``; ``old`` None appends ``new`` (making the file if need be)."""
    path = root / rel
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    assert old is None or text.count(old) == 1, (rel, old)
    path.write_text(text + new if old is None else text.replace(old, new), encoding="utf-8")


@pytest.mark.parametrize("release", RELEASES)
def test_db_extract_writes_the_committed_generated_data_byte_for_byte_from_either_image(release, request, tmp_path,
                                                                                         capsys):
    """The extract of either vanilla image is byte for byte the committed data (``data/generated``, the frozen
    set's sha12 caa2dad865c8): each level's file, and no file more or less (Europe's ``default.xbe`` registers the
    same node types at its own addresses, and its level files are USA's). A difference names the level and its
    first differing line (names, ids and numbers only)."""
    image = request.getfixturevalue(f"{release.name}_iso")
    assert db_extract.main(["--out", str(tmp_path / "out"), "--iso", str(image)]) == 0
    assert capsys.readouterr().out == f"23 levels written to {tmp_path / 'out'}\n"
    fresh = {p.stem: p.read_text(encoding="utf-8") for p in sorted((tmp_path / "out").glob("*.json"))}
    committed = {p.stem: p.read_text(encoding="utf-8") for p in sorted((DATA_DIR / "generated").glob("*.json"))}
    assert sorted(fresh) == sorted(committed) == sorted(db_extract.LEVELS)
    differ = {}
    for lvl, text in fresh.items():
        if text != committed[lvl]:
            a, b = text.splitlines(), committed[lvl].splitlines()
            k = next((n for n, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            differ[lvl] = (k + 1, a[k:k + 1], b[k:k + 1])
    assert differ == {}


def test_db_extract_refuses_what_it_cannot_do_and_writes_nothing(tmp_path, capsys):
    """D36, D35: db-extract checks where it writes before it reads the image. With the vanilla image's folder as
    ``--out`` (the 23 files would land beside ``usa.iso``) or with an ``--out`` that is a file, it exits 1 with an
    ``ERROR:`` line naming why, not a traceback, and writes nothing. The image here is never read."""
    image = tmp_path / "isodir" / "usa.iso"
    image.parent.mkdir()
    image.write_bytes(b"")
    (tmp_path / "afile").write_text("x", encoding="utf-8")
    before = sorted(tmp_path.rglob("*"))
    for out_name, refusal in (("isodir", "the vanilla ISO's folder"), ("afile", "is not a folder")):
        code = db_extract.main(["--out", str(tmp_path / out_name), "--iso", str(image)])
        err = capsys.readouterr().err
        assert (code, err.startswith("ERROR: "), refusal in err) == (1, True, True), (out_name, err)
        assert sorted(tmp_path.rglob("*")) == before, out_name


def test_check_counts_the_shipped_database_as_at_modkits_freeze_and_names_each_error(tmp_path, capsys):
    """``check`` on the shipped database passes every load check and counts what Modkit's ``rando check`` counted
    at its freeze (the same JSON summary): every level authored but training_room (no level file), nothing open,
    the proven spots by kind and the non-gem ones by realm, the 21 proof records, the skips by status and
    confirmation and their registry, and defaults.toml turning none on (share AZR-AAEA). On the toy database it
    prints what is open and exits 0; with a requirement naming an unknown counter it exits 1 naming the file, the
    object and the field."""
    assert check.main(["--json"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["errors"] == []
    assert (s["levels"]["stubs"], s["levels"]["authored"], s["levels"]["without_a_level_file"]) == (
        [], ["a1", "a3", "a5", "a6", "airship", "d1", "d2", "e2", "e5", "e6", "e7", "f1", "f2", "f3", "f4", "f6",
             "life", "town", "w1", "w2", "w3", "w4"], ["training_room"])
    assert (s["todo_fields_total"], s["pool_locations_without_a_node_total"], s["undecoded_gates_open"]) == (0, 0, 0)
    assert s["locations_proven"] == {"data": 51, "l3": 11, "route": 2, "xemu": 2}
    assert s["nongem_proven_by_realm"] == {"air": 2, "earth": 10, "fire": 15, "life_death": 0, "town_water": 23}
    assert s["proofs"] == {"records": 21, "by_kind": {"edge": 5, "location": 11, "skip": 5}} \
        and s["edges_by_confidence"]["probed"] == 20
    assert (s["route"]["status"], len(s["route"]["open"])) == ("draft", 0)
    assert (s["skips"]["by_status"], s["skips"]["by_confirmed"], s["skip_registry"]) == (
        {"held": 2, "in_logic": 41, "manual": 2}, {"l3": 3, "no": 2, "owner": 7, "xemu": 33},
        {"picks": 40, "batches": 5, "tag": "67741703"})
    assert (s["settings"]["defaults"]["skips_on"], s["settings"]["defaults"]["share"]) == (0, "AZR-AAEA")

    assert check.main(["--db", str(TOYDB)]) == 0
    out = capsys.readouterr().out
    assert "open: 3 TODO fields (edge.from 1, node.anchors 1, level.route 1)\n" in out
    assert "skips on at skip_ceiling 0, 1, 2, 3, 4 (no toggles): 0, 0, 1, 1, 1\n" \
           "time-savers (D145: no logic edge, toggle or ceiling count): 1 (t1 1)\n" in out
    assert out.endswith("errors: 0\n")
    root = tmp_path / "db"
    shutil.copytree(TOYDB, root)
    _edit(root, "levels/t1.toml", 'requires = "water1"', 'requires = "water1 & fire9 | lava>=1"')
    assert check.main(["--db", str(root)]) == 1
    assert capsys.readouterr().out.endswith(
        "errors: 1\n  levels/t1.toml: event[t1.boss.killed].requires: unknown_counter (lava)\n")


@functools.cache
def _logic(root: Path) -> Logic:
    return Logic(load_database(root))


def test_committed_valid_plans_solve_and_invalid_plans_do_not():
    """RANDOMIZER_PLAN §3.7's corpus (Randovania's committed seeds): each plan in ``plans/valid`` reaches victory and
    each in ``plans/invalid`` doesn't, and a plan that names its traps has exactly those. A plan names its database
    (``db``: reachdb's plans pin the reach one mechanism each, escapedb's the escape and its counter-examples,
    guardiandb's the no-return region), the behaviour it pins (``pins``), the spots that differ from vanilla
    (``placement``), the options that differ from the database's defaults (``settings``), the items and flags held
    from the start, and the traps it expects (``traps``, ``after_completion``). A failure names each plan whose
    verdict is wrong, with what the solver gave."""
    wrong = {}
    for path in PLANS:
        case = json.loads(path.read_text(encoding="utf-8"))
        assert set(case) <= {"db", "pins", "placement", "settings", "items", "flags", "traps", "after_completion"} \
            and case["pins"], path.name
        logic = _logic(DATA / case["db"])
        d = logic.db.defaults
        table = {"format": SETTINGS_FORMAT, "skip_ceiling": d.skip_ceiling, "movement_tier": d.movement_tier,
                 "dark_fire": 1, "skip_override": {}, **case.get("settings", {})}
        settings = settings_from_table(table, logic.skip_tables, path.name)
        reach = logic.reach(settings, {**logic.vanilla_placement(), **case.get("placement", {})},
                            case.get("items", ()), case.get("flags", ()))
        if (reach.victory is not (path.parent.name == "valid")
                or ("traps" in case and reach.traps != set(case["traps"]))
                or ("after_completion" in case and reach.after_completion != set(case["after_completion"]))):
            wrong[f"{path.parent.name}/{path.stem}"] = (reach.victory, sorted(reach.traps),
                                                        sorted(reach.after_completion))
    assert len(PLANS) == 68 and wrong == {}


def test_impact_ranking_orders_spots_by_fill_gain_and_edges_by_what_their_removal_breaks(tmp_path):
    """``impact`` on ``impactdb``, where four powers compete for three proven spots, so no seed fills. Proven alone,
    the grotto's spot (open from the start) or the ledge's (behind air) lets every seed fill, as fill() itself
    agrees, and the tower's (behind all four powers) none: fill() gets past its preflight (four spots for four
    powers) and fails after its 40 attempts (Normal's 20 and its 20 more past a kept way out, D1160), naming the
    stuck powers and the four spots. The grotto's ranks first (in more stuck reaches, and a first-sphere spot) and
    is the greedy set's one proof. Of the assumed edges, removing town > cave breaks vanilla (the fire), town >
    ledge cuts the ledge's spot, beach > hill only delays the hill (its proven spot leaves the opening) and the
    second beach > town changes nothing: they rank in that order."""
    seeds = ["0", "1", "2", "3"]
    doc = impact.analyse(DATA / "impactdb", seeds, jobs=1, singles=5, width=5, edge_fills=5, rounds=3)
    assert doc["baseline"]["fills"] == 0
    assert [(s["id"], s["fills"]) for s in doc["spots"]] == [("i1/g0/r4", 4), ("i1/g0/r5", 4), ("i1/g0/r6", 0)]
    assert [p["spot"] for p in doc["greedy"]["proofs"]] == ["i1/g0/r4"] and doc["greedy"]["reached"]
    assert [(e["from"], e["to"], e["tier"]) for e in doc["edges"]] == [
        ("i1_town", "i1_cave", "breaks vanilla"), ("i1_town", "i1_ledge", "cuts locations"),
        ("i1_beach", "i1_hill", "changes the playthrough"), ("i1_beach", "i1_town", "no effect")]
    root = tmp_path / "impactdb"
    shutil.copytree(DATA / "impactdb", root)
    level = root / "levels" / "i1.toml"
    toml = level.read_text(encoding="utf-8")
    level.write_text(toml + '\n[[location]]\nid = "i1/g0/r4"\nproven = { by = "data", ref = "toy" }\n',
                     encoding="utf-8")
    proven = Logic(load_database(root))
    assert all(fill(proven, seed).placement for seed in seeds)
    level.write_text(toml + '\n[[location]]\nid = "i1/g0/r6"\nproven = { by = "data", ref = "toy" }\n',
                     encoding="utf-8")
    with pytest.raises(FillError, match=r"40 attempts failed; the last: attempt 39: no safe proven spot") as failed:
        fill(Logic(load_database(root)), "0")
    assert failed.value.items == ["power_air", "power_earth", "power_fire", "power_water"]
    assert failed.value.proven == ["i1/g0/r1", "i1/g0/r2", "i1/g0/r3", "i1/g0/r6"]


def test_the_bench_and_the_soak_make_only_databases_and_settings_the_planner_accepts(tmp_path):
    """What the two benches make for the planner passes its checks: ``bench``'s synthetic database at its default
    size (one authored level of 600 rooms, 3,200 edges, powers and buttons) loads with no error and its vanilla
    placement wins, and every settings table ``soak`` draws from a seed is a valid one (it holds ``dark_fire`` 1,
    as every setting must since dark areas always need Fire 1), as are its three profiles, each with its own share
    string."""
    bench.synthetic(tmp_path, 600, 3200, 1)
    report = check_database(tmp_path)
    assert [str(i) for i in report.issues] == []
    assert Logic(report.database).reach().victory
    skips = {sid: s for sid, (_, s) in load_database().skips.items()}
    drawn = [soak.drawn_settings(seed, skips) for seed in random.Random(4132).sample(range(10 ** 6), 200)]
    assert {s.movement_tier for s in drawn} == {"safe", "standard", "hard", "frame_perfect"} \
        and any(s.skip_override for s in drawn) and any(s.exclude_categories for s in drawn)
    assert len({soak.share_encode(st, skips) for st in soak.PROFILES.values()}) == 3


# --- Step 4.28c: Modkit's randomizer-data test no AzurKit test pinned (the test census's lane C).

def test_every_prefetch_neighbour_without_a_stanza_is_a_level_cut_from_the_disc(usa_iso):
    """AZ-290's prefetch side (Modkit's ``test_assets_manifest.py``): the game's ``prefetch-lists.txt`` still
    names ``f7`` as f1's neighbour, a level cut from the game with no stanza of its own and no
    ``gamedata/f7.xbr``, so the exit table leaves f1's ``levelSwitch3`` to it out (``levels.py``); every
    neighbour with no stanza is such a level."""
    from azurkit.core import iso

    with iso.Reader(usa_iso) as r:
        text = bytes(r.read("prefetch-lists.txt")).decode("utf-8")
    stanzas: dict[str, list[str]] = {}
    for line in text.splitlines():
        key, _, value = line.strip().partition("=")
        if key == "tag":
            neighbours = stanzas.setdefault(value, [])
        elif key == "neighbor":
            neighbours.append(value)
    dangling = {name for names in stanzas.values() for name in names if name not in stanzas}
    assert dangling == {"f7"} and not {f"gamedata/{name}.xbr" for name in dangling} & set(gate.USA.files)


# Step 4.28e: Modkit's planner tests no AzurKit test pinned (the test census's lanes L2 and L3): the shipped
# database's owner- and xemu-confirmed facts as one table of reach queries, then the loader's refusals and the
# planner's mechanisms on the fixture databases and the shipped one.

@functools.cache
def _shipped() -> Logic:
    return kept_logic()


def _toy(tmp_path: Path) -> Path:
    return shutil.copytree(TOYDB, tmp_path / "db")


def _issues(root: Path) -> list[tuple[str, str]]:
    return [(i.code, i.where) for i in check_database(root).issues]


def test_the_shipped_databases_owner_and_xemu_confirmed_facts_hold():
    """Each fact the owner's demos, xemu by real input or L3 confirmed of the shipped database is one row of reach
    queries on it (the plan goldens' database digest freezes its files, not what these queries read of them), its
    comment naming the source: a failure names each row whose answer moved, with its answer and the fact's."""
    logic = _shipped()
    db, vanilla = logic.db, logic.vanilla_placement()
    full = {"air": 3, "water": 3, "fire": 3, "earth": 3}

    def at(tier: str, **options) -> Settings:
        return dataclasses.replace(db.defaults, movement_tier=tier, **options)
    facts = {}
    # AZ-512: frag_fire_3's requirement takes e5.frag_fire3_earth1 for earth 2, so a player holding every pool item
    # but two of the three earth powers reaches it only with the skip on; its gates name both acid blocks
    earth = {loc for loc, item in vanilla.items() if item == "power_earth"}
    kit = set(vanilla) - (earth - {"e5/g0/r4260"}) - {"e5/g0/r4263"}
    facts["e5: frag_fire_3 at earth 1 by frag_fire3_earth1 alone"] = (
        (["e5/g0/r4263" in logic.reach(Settings(0, "standard", {"e5.frag_fire3_earth1": on}), vanilla,
                                       collected=kit).locations for on in (False, True)],
         logic.skip_tables["e5.frag_fire3_earth1"]["gates"]),
        ([False, True], ["e5.AcidBlock_02", "e5.AcidBlock_03"]))
    # Step R1.31b (X.35's and rjc5's runs): f6's batch f6.terraces crosses the courtyard to the walkway, so with
    # every pool item but the water powers (no block melts) the fire power is reached only with it on, and at one air
    # power only from the Hard ceiling, its air-1 variant's tier (the air-2 sibling, Standard, asks air 2)
    water = {loc for loc, item in vanilla.items() if item in ("power_water", "power_water_a3")}
    one_air = set(vanilla) - water - set(sorted(loc for loc, item in vanilla.items() if item == "power_air")[1:]) \
        - {"f6/g0/r865"}

    def fire_power(ceiling: int, toggles: dict, kit: set) -> bool:
        return "f6/g0/r865" in logic.reach(Settings(ceiling, "standard", toggles), vanilla, collected=kit).locations
    facts["f6: the fire power with no water by the terraces, at air 1 from Hard"] = (
        ([fire_power(0, {"f6.terraces": on}, set(vanilla) - water - {"f6/g0/r865"}) for on in (False, True)],
         [fire_power(c, {}, one_air) for c in (2, 3)], fire_power(3, {"f6.terraces": False}, one_air)),
        ([False, True], [False, True], False))
    # Step R2.17b (D629; Hard by the owner's rating, D659): d1's elevator bounce from floor 8's shaft ring onto
    # floor 9, which by the elevator needs the three diamond batteries' keylocks
    no_batteries = {loc for loc, item in vanilla.items() if item != "key_diamondbattery"}
    facts["d1: Spideyzar with no diamond battery by the elevator bounce, from Hard"] = (
        [logic.reach(Settings(c, "standard", toggles), vanilla, collected=no_batteries).victory
         for c, toggles in ((2, {}), (3, {}), (3, {"d1.elevator_bounce": False}))], [False, True, False])
    # AZ-515, AZ-532, AZ-533 (a sitting measured the archway door's deck out of reach; the owner's demo: the door is
    # closed until its button is pressed): with no fire key used the pit is all a player below air 3 reaches at any
    # tier, the keys' lift (toggle5) takes him up, and the lock's node is entered only from f3_core and f3_z038
    no_key = {pending: 0 for key, pending in logic.refund.values() if key == "key.fire1"}
    facts["f3: the keylock pit holds anyone below air 3 but for its keylocks' lift"] = (
        ([sorted(logic.within("f3", ["f3_z028"], {**no_key, "air": air}, [], at(tier)))
          for tier in MOVEMENT_TIERS for air in (0, 1, 2)],
         {"f3_z012", "f3_core"} <= logic.within("f3", ["f3_z028"], {"key.fire1": 3}, []),
         sorted((e["from"], e["confidence"]) for e in db.levels["f3"]["edge"] if e["to"] == "f3_z028")),
        ([["f3_z028", "f3_z031", "f3_z038"]] * 12, True, [("f3_core", "data"), ("f3_z038", "probed")]))
    # AZ-714 (D656, the owner: no way out of the ring of fire walls without water 2): at water 1 the hub reaches only
    # its teleporter's side at any tier and ceiling, at water 2 the ring's far side too
    ring = {"a5_z012", "a5_z098", "a5_z101", "a5_z107", "a5_z129"}

    def hub(water: int, tier: str) -> set[str]:
        return logic.within("a5", ["a5_z052"], {**full, "water": water}, [], at(tier, skip_ceiling=4))
    facts["a5: the hub's ring of fire walls is left below water 2 only by its teleporter"] = (
        ([sorted(hub(1, tier)) for tier in MOVEMENT_TIERS], [ring <= hub(2, tier) for tier in MOVEMENT_TIERS]),
        ([["a5_dock", "a5_z000", "a5_z020", "a5_z043", "a5_z052", "a5_z144"]] * 4, [True] * 4))
    # AZ-585, AZ-386 (the owner's demo): e5.Z581 lies inside the entrance gear's exit trigger, so it is no node and
    # no spot hangs on it; e5's way back to e2 is the gear room's fall, and the arrival's drop into e2's valley is
    # the owner's walk (probed by xemu)
    spots = [f"e5/g0/r{n}" for n in (4263, 4266, 4268, 4758, 4760, 4762, 4764, 4766, 4779, 4782, 4785, 4814, 4817,
                                     4820, 4849, 4852, 4855)]
    facts["e5: the gear room falls into the exit to e2, no spot on the floor inside its trigger"] = (
        ("e5_z580" in db.nodes, sorted({db.node_of[x] for x in spots}),
         [(e["from"], e["to"], e["requires"]) for e in db.levels["e5"]["edge"] if e.get("exit") == "e5/g0/r5684"],
         [(e["confidence"], e["proven"]["by"]) for e in db.levels["e2"]["edge"]
          if (e["from"], e["to"]) == ("e2_z156", "e2_core")]),
        (False, ["e5_z006", "e5_z014"], [("e5_z014", "e2_z156", "true")], [("probed", "xemu")]))
    # AZ-586 (the owner's demo): from the garden he dropped onto e6.Z048 at kit 0 and the gear's exit loaded e2
    facts["e6: the gear's exit leaves from the pocket the owner dropped into at kit 0"] = (
        ([(e["from"], e["to"]) for e in db.levels["e6"]["edge"] if e.get("exit") == "e6/g0/r3471"],
         [(e["confidence"], e["proven"]["by"]) for e in db.levels["e6"]["edge"]
          if (e["from"], e["to"]) == ("e6_core", "e6_z048")], "e6_z048" in logic.within("e6", ["e6_core"], {}, [])),
        ([("e6_z048", "e2_core")], [("probed", "xemu")], True))
    # AZ-726 (the owner's demo: falling into lava is an instant death): the river's ground is the platform f2's
    # volcano raises, so only F2_F4a, the lava ride, reaches it, and the save ledge doesn't at every element 3
    facts["f4: the lava river only by f2's lava ride, not the ledge's drop"] = (
        (sorted((e["from"], e.get("exit")) for lv in db.levels.values() for e in lv["edge"]
                if e["to"] == "f4_lava_river" and e.get("logic", True)),
         "f4_lava_river" in logic.within("f4", ["f4_z013"], full, [])),
        ([("f2_entrance", "f2/g0/r2918")], False))
    # AZ-476, AZ-736, AZ-700 (the owner's demo): floor 6 only once death_keylock is used, even at full kit; the beam
    # walkway from walkway generator 2 asks air 3 (at kit 0 it is his only by the save warp back); d2's door back to
    # d1 asks the six lens keylocks
    no_battery = {p: 0 for k, p in logic.refund.values() if k == "key.diamondbattery"}

    def floor6(*flags: str) -> bool:
        return "d1_z121" in logic.within("d1", ["d1_core", "d1_z125"], {**no_battery, **full},
                                         ["d1.seal.open", "d2.lab.reached", *flags])

    def walkway(air: int, *flags: str) -> bool:
        return "d1_z025" in logic.within("d1", ["d1_z056"], {"air": air},
                                         ["d1.walkwayGenerator2_PressurePlateShape.touch", *flags])
    facts["d1: floor 6 past death_keylock, the beam walkway at air 3, d2's door back by six lens keylocks"] = (
        (floor6(), floor6("d1.death_keylock.open"), walkway(2, "d2.lab.reached"), walkway(3, "d2.lab.reached"),
         walkway(3), [e["requires"] for e in db.levels["d2"]["edge"] if e.get("exit") == "d2/g0/r3840"]),
        (False, True, False, True, False, [" & ".join(f"button:d2.death_keylock{n}" for n in ("", 1, 2, 3, 4, 5))]))
    # AZ-738 (D745, the owner: the sewer is left with air 1, not water 1; e6's lake by the vines on a tree stump)
    facts["town: the sewer is left at air 1, not water 1; e6: the lake up the stump's vines at kit 0"] = (
        ([["town_central" in logic.within("town", ["town_z003"], k, [], at(tier))
           for k in ({}, {"water": 1}, {"air": 1})] for tier in MOVEMENT_TIERS],
         "e6_core" in logic.within("e6", ["e6_z003"], {}, [])),
        ([[False, False, True]] * 4, True))
    # AZ-820 (xemu by real input from w3_2's save): no jump or flight from the save ledge's side reaches the
    # centre's top (a rise caps at 2.4 m over the takeoff), so its one way up in logic is the NW walkway's foot
    w3 = db.levels["w3"]["edge"]
    facts["w3: the centre's top only from its NW walkway's foot, never from the save ledge's side"] = (
        ({e["from"]: e["requires"] for e in w3 if e["to"] == "w3_z116" and e.get("logic", True)},
         {e["to"]: e["requires"] for e in w3 if e["from"] == "w3_z127"},
         sorted({"w3_z116", "w3_z135", "w3_z150"}
                & logic.within("w3", ["w3_z127"], {"earth": 3, "fire": 3, "water": 3}, []))),
        ({"w3_z135": "air>=1"}, {"w3_z077": "true", "w3_z096": "flag:w3.polySurfaceShape1.destroyed"}, []))
    # Step R1.40d (xemu by real input, its no-store controls shut): with smash stored, LT let go at the ledge's end
    # breaks the shrine's near wall at any kit, so w3.pstorage_smash_shield credits the wall at every kit the
    # generated smash requirement (earth, air and fire 1) misses, none with the skip off, and at kit 0 the ledge
    # then reaches the shrine and the shield's front
    on = dataclasses.replace(db.defaults, skip_ceiling=2)
    off = dataclasses.replace(on, skip_override={"w3.pstorage_smash_shield": False})
    missed = [k for k in itertools.product(range(4), repeat=4) if min(k[:3]) == 0]

    def credited(st: Settings) -> list[tuple]:
        wall = next(r for f, n, _, r in logic.rules(st).credits
                    if (f, n) == ("w3.polySurfaceShape1.destroyed", "w3_z127"))
        return [k for k in missed if wall(dict(zip(("earth", "air", "fire", "water"), k)), set())]
    facts["w3: the stored smash breaks the shrine's near wall from w3_2's ledge at any kit"] = (
        (credited(on) == missed, credited(off),
         sorted({"w3_z096", "w3_z150"} & logic.within("w3", ["w3_z127"], {}, [], on))),
        (True, [], ["w3_z096", "w3_z150"]))
    # AZ-809 (xemu by real input from frag_fire_1's ledge): walking off its lake side drops into the lake alive, a
    # Hard edge, so from Hard up the ledge is no dead end without the frost and the ice climb takes frag_fire_1 in
    # round 5 of the vanilla placement under the max settings, where with the skip off it waits for the frost's, 7
    frost = ("w3.LightShape_g1r23.action", "w3.LightShape_g1r29.action", "w3.snow_blowers.on")

    def rounds(on: bool) -> tuple[int, int]:
        trace = []
        logic.reach(Settings(4, "frame_perfect", {"w3.iceclimb_frag_fire1": on}), vanilla, trace=trace)
        return (next(i for i, sp in enumerate(trace) if "w3/g1/r2018" in sp.locations),
                next(i for i, sp in enumerate(trace) if all(f in sp.flags for f in frost)))
    facts["w3: the ice climb takes frag_fire_1 before the frost, its ledge dropping into the lake from Hard"] = (
        (["w3_core" in logic.within("w3", ["w3_z078"], {}, [], at(tier)) for tier in MOVEMENT_TIERS],
         rounds(True), rounds(False)),
        ([False, False, True, True], (5, 7), (7, 7)))
    # Step R1.11b (D123): f6's fight platforms are entered only through the Jaw, which the seal opens with 3 fire
    # fragments (the Jaw, its stairs and the boss door are held rigs), so without frag_fire_2 neither the guardian's
    # phases nor its 4th fragment's slot are reached
    marks = ("f6.seal.open", "f6.guard_fire1.killed", "f6.guard_fire3.killed")
    facts["f6: the fire guardian's platforms and slot only past the seal"] = (
        [[m in r.flags for m in marks] + ["characters/g21/r154" in r.locations]
         for r in (logic.reach(), logic.reach(placement={**vanilla, "f4/g0/r1289": None}))], [[True] * 4, [False] * 4])
    # AZ-468 (Step R1.28): MineCarRide2's car moves only once both circuitboard locks are in, so the ice cave's
    # high-ledge obsidian past it waits for both locks' flags while the valley's water-1 way reaches both boards
    no_boards = {**vanilla, "e2/g0/r733": None, "e2/g0/r735": None}
    locks = ("e2.earth_keylock.open", "e2.earth_keylock1.open")
    facts["e2: the minecart rides only once both circuitboard locks are in"] = (
        [(r.locations >= {"e2/g0/r733", "e2/g0/r735"}, "e2/g0/r4402" in r.locations)
         for r in (logic.reach(placement=no_boards, flags=locks[:n]) for n in (0, 1, 2))],
        [(True, False), (True, False), (True, True)])
    # Steps R1.8f-R1.8q (the decoded wiring, the owner's routes and demos, D209, D210, D218): each progression
    # minigame's requirement as the game sets it, and only the toppled tower or the Torpedo Skips enter w1's dark
    # cave and town's waterfall ledge behind it
    events = {oid: o["requires"] for oid, (_, kind, o) in db.hand.items() if kind == "event"}
    exits = {e["exit"]: e["requires"] for doc in db.levels.values() for e in doc["edge"] if "exit" in e}
    edges = {(e["from"], e["to"]): e["requires"] for doc in db.levels.values() for e in doc["edge"]}
    locs = {o["id"]: o["requires"] for doc in db.levels.values() for o in doc["location"] if "requires" in o}
    crystals = ("flag:e2.crystal_lightning.hit & flag:e7.crystal_fire.hit & flag:e5.crystal_whirlwind.hit"
                " & flag:e5.crystal_pulse.hit")
    melted = "event:a5.ice_block1.melted | event:a5.ice_block2.melted | event:a5.ice_block3.melted"
    games = {"e6 tree song": (events["e6.tree_song.played"], f"{crystals} & earth>=1 & air>=1 & fire>=1 & water>=1"),
             "e6 crystal door": (edges["e6_core", "e6_z021"], "event:e6.tree_song.played | skip:e6.tree_song_skip"),
             "e6 E6_A1": (exits["e6/g0/r3467"], "true"),
             "life cores": (events["life.filament_cores.won"], "event:life.final_joystick.armed"),
             "life Movie_levelSwitch": (exits["life/g0/r1692"], "event:life.filament_cores.won"),
             "life Town_levelSwitch": (exits["life/g0/r1707"], "event:life.filament_cores.won"),
             "life frag_life_4": (locs["life/g0/r259"],
                                  "event:life.filament_cores.won & air>=3 & water>=3 & fire>=3 & earth>=3"),
             "life armed joystick": (events["life.final_joystick.armed"],
                                     "event:life.BlockerShape_g0r243.action & event:life.Blocker2Shape.action"),
             "life climb to Lock_B": (edges["life_core", "life_lock_b"], "air>=2"),
             "life Lock_B to pad B": (edges["life_lock_b", "life_pad_b"], "button:life.life_keylock"),
             "life east key": (locs["life/g0/r332"], "air>=2"),
             "life west key": (locs["life/g0/r334"], "air>=2"),
             "a6 arena lift": (edges["a6_field_foot", "a6_arena"], "air>=3 & earth>=3 & fire>=3 & water>=3"
                               " & button:a6.air_keylock & button:a6.air_keylock1 & button:a6.air_keylock2"),
             "w1 torpedo tower": (events["w1.torpedo_tower.toppled"], "event:w1.pCubeShape7.joystick"),
             "a5 final fan": (events["a5.final_fan.on"], "event:a5.ice_block1.melted & event:a5.ice_block2.melted"
                              " & event:a5.ice_block3.melted"),
             "a5 power_air": (locs["a5/g0/r733"], f"event:a5.final_fan.on | (skip:a5.one_island_air2 & ({melted}))"),
             "w1 bay onto the fallen tower": (edges["w1_bay", "w1_dark_cave"], "event:w1.torpedo_tower.toppled"),
             "w1 into the station": (edges["w1_bay", "w1_z090"], "air>=1 & fire>=1 | skip:w1.pstorage_electric_arch"),
             "w1 out of the station": (edges["w1_z090", "w1_bay"],
                                       "air>=1 & fire>=1 | skip:w1.pstorage_electric_arch"),
             "e6 red machine": (events["e6.red_machine.on"],
                                "event:e6.Light4Shape.joystick & event:e6.Light6Shape.joystick"),
             "e6 blue machine": (events["e6.blue_machine.on"], "event:e6.Light6Shape.joystick & ((event:e6.red_machine.on"
                                 " & event:e6.Light5Shape.joystick) | skip:e6.slide_flight)"),
             "e6 frag_earth_3": (locs["e6/g0/r2755"], "event:e6.blue_machine.on"),
             "e6 upper ring gems": (locs["e6/g0/r2767"], "event:e6.red_machine.on | skip:e6.slide_flight"
                                    " | skip:e6.upper_ring_flutter_air2 | skip:e6.upper_ring_flutter_air1"),
             "w2 hose console": (events["w2.hose.on"], "true"),
             "w2 hose joystick": (events["w2.hose.won"], "event:w2.hose.on"),
             "w2 power_water behind the hose": (locs["w2/g0/r1346"], "event:w2.hose.won")}
    opens, pocket = {"event:w1.torpedo_tower.toppled", "skip:w1.torpedo_skip"}, {"w1_dark_cave", "town_z045"}
    into = [(e["from"], term_text(t)) for doc in db.levels.values() for e in doc["edge"]
            if e["to"] in pocket and e["from"] not in pocket for t in dnf(e.get("requires", "true"))]
    facts["each progression minigame gates its reward by what the game needs"] = (
        ({k: have for k, (have, want) in games.items() if parse(have) != parse(want)},
         [x for x in into if not opens & set(x[1].split(" & "))], len(into) > 0), ({}, [], True))
    assert {fact: answers for fact, answers in facts.items() if answers[0] != answers[1]} == {}


_SKIP_CONFIRMED = 'status = "in_logic"\nconfirmed = { by = "owner", ref = "toy" }'

# The loader's refusals (docs/RANDOMIZER_DB.md's rules): each case is the database it copies, its edits (_edit's)
# and the issues check_database names, in order.
_REFUSALS = {
    "rules 3, 9, 16 (§4.2): an id that doesn't resolve (a zone too), an authored level's open field, a location "
    "without a node": (
        "toydb",
        (("levels/t1.toml", 'to = "t1_start"\nkind = "walk"', 'to = "t1_nowhere"\nkind = "walk"'),
         ("levels/t1.toml", 'locations = ["t1/g0/r1", "t1/g0/r3"]', 'locations = ["t1/g0/r1"]'),
         ("levels/t1.toml", 'anchors = ["t1/g0/r20"]', 'anchors = []'),
         ("generated/t1.json", '"touch": "t1/g0/r52"', '"touch": "t2/g0/r52"'),
         ("generated/t1.json", '"to": "t1/g0/r51"', '"to": "t1/g0/r59"'),
         ("levels/t1.toml", 'anchors = ["cell:Vault"]',
          'anchors = ["cell:Vault", "zone:t1.Z001", "zone:t1.Z001"]\ndark = "t1.nothing"'),
         ("levels/t1.toml", 'confidence = "data"', 'confidence = "data"\ndark = "t1.wall_skip"'),
         ("generated/t1.json", '"item": "sapphire",\n   "pool": true', '"item": "sapphyre",\n   "pool": true')),
        [("bad_generated_id", "generated/t1.json: teleporters[t1/g0/r50]: routes[0].touch"),
         ("unresolved_generated", "generated/t1.json: teleporters[t1/g0/r50]: routes[1].to"),
         ("open_field", "levels/t1.toml: node[t1_start].anchors"),
         ("unresolved_skip", "levels/t1.toml: node[t1_vault].dark"),
         ("unresolved_zone", "levels/t1.toml: node[t1_vault].anchors"),
         ("unresolved_zone", "levels/t1.toml: node[t1_vault].anchors"),
         ("zone_in_two_nodes", "levels/t1.toml: node.anchors"),
         ("dark_skip_not_nolight", "levels/t1.toml: edge[t1_start->t1_vault].dark"),
         ("unresolved_node", "levels/t1.toml: edge[t1_vault->t1_nowhere].to"),
         ("location_without_node", "levels/t1.toml: location[t1/g0/r3]"),
         ("unknown_item", "generated/t1.json: locations[t1/g0/r3].item")]),
    "§4.2: a dark skip of another dark area or another level": (
        "reachdb",
        (("levels/r1.toml", 'Crypt"]\ndark = true', 'Crypt"]\ndark = "r1.cave_nolight"'),
         ("levels/r2.toml", 'hub = true', 'hub = true\ndark = "r1.cave_nolight"')),
        [("dark_skip_other_area", "levels/r1.toml: node[r1_crypt].dark"),
         ("dark_skip_other_level", "levels/r2.toml: node[r2_yard].dark")]),
    "rules 7, 8, 14 (plan §3.1): a cart lock, toggle or respawn with no declared mechanism; a toggle gating an edge": (
        "toydb",
        (("levels/t1.toml", 'kind = "exit"\nexit', 'kind = "cart"\nlock = "t1_minecart"\nexit'),
         ("levels/t1.toml", 'mode = "latch"', 'mode = "toggle"'),
         ("levels/t1.toml", 'destroy_from = ["t1_start"]',
          'destroy_from = ["t1_start"]\npersist = "timed"\npersist_reason = "toy"')),
        [("cart_lock_undeclared", "levels/t1.toml: edge[t1_start->t2_hub].lock"),
         ("undeclared_mechanism", "world.toml: mechanism"),
         ("toggle_gates_edge", "levels/t1.toml: edge[t1_start->t1_vault]"),
         ("undeclared_mechanism", "levels/t1.toml: edge[t1_start->t1_vault].through")]),
    "§2.9: a disc teleport without its one_shot_teleport mechanism and the one guardian slot that spends it": (
        "guardiandb",
        (("world.toml", 'kind = "one_shot_teleport"', 'kind = "cycle"'),
         ("generated/g1.json", '"guardian_slot": true', '"guardian_slot": false')),
        [("undeclared_mechanism", "levels/g1.toml: edge[g1_altar->g1_town].disc"),
         ("disc_teleport_slot", "levels/g1.toml: edge[g1_altar->g1_town].disc")]),
    "rule 10 (plan §2.13 rule 1): a hub that isn't safe with every item, no skip and the safe tier": (
        "toydb",
        (("levels/t2.toml", 'to = "t1_start"\nkind = "exit"', 'to = "t1_start"\nkind = "exit"\ndifficulty = 3'),),
        [("start_hub_apart", "world.toml: hub")]),
    "rule 21 (plan §2.13 rule 4, D76): a terminal event read by an edge, a drop's assumes or its boss's location": (
        "reachdb",
        (("levels/r1.toml", 'at = "r1_arena"\nrequires = "fire>=1"',
          'at = "r1_arena"\nrequires = "fire>=1"\nterminal = true'),
         ("levels/r1.toml", 'from = "r1_arena"\nto = "r1_start"\nkind = "walk"',
          'from = "r1_arena"\nto = "r1_start"\nkind = "walk"\nrequires = "event:r1.boss.slain"'),
         ("levels/r1.toml", 'assumes = ["r1.olock.open"]', 'assumes = ["r1.boss.slain"]')),
        [("terminal_event_read", "levels/r1.toml: edge[r1_arena->r1_start].requires"),
         ("terminal_event_read", "levels/r1.toml: edge[r1_start->r1_pit].assumes"),
         ("terminal_event_read", "generated/r1.json: locations[r1/g0/r19].gated_by")]),
    "rules 4, 15: a gate or live exit bound by nothing, an undecoded barrier with no override_requires": (
        "toydb",
        (("generated/t1.json", '"barriers": [\n  {',
          '"barriers": [\n  {"id": "t1/g0/r11", "kind": "other", "persist": "permanent", "requires": "true"},\n  {'),
         ("generated/t1.json", '"exits": [\n  {',
          '"exits": [\n  {"dest_level": "t2", "id": "t1/g0/r21", "kind": "exit", "live": true},\n  {'),
         ("generated/t1.json", '"requires": "water>=1"', '"requires": null')),
        [("gate_undecoded", "levels/t1.toml: barrier[t1.wall].override_requires"),
         ("undecoded_gate_in_logic", "levels/t1.toml: edge[t1_start->t1_vault].through"),
         ("gate_unexplained", "generated/t1.json: barriers[t1/g0/r11]"),
         ("exit_unexplained", "generated/t1.json: exits[t1/g0/r21]")]),
    "D122, D143, D170: a proven mark that is malformed, off the pool, on an edge not probed, with no record or with "
    "another claim's; the toy L3 proofs (a spot's, an edge's) load": (
        "toydb",
        (("levels/t1.toml", 'proven = { by = "data", ref = "toy" }',
          'proven = { by = "l3", ref = "toy/aaaaaaaaaaaa@bbbbbbbbbbbb" }'),
         ("levels/t1.toml", 'confidence = "data"\n',
          'confidence = "probed"\nproven = { by = "l3", ref = "toy/cccccccccccc@bbbbbbbbbbbb" }\n'),
         ("generated/t1.json", '"item": "sapphire",\n   "pool": true', '"item": "sapphire",\n   "pool": false'),
         ("levels/t1.toml", None, '\n[[location]]\nid = "t1/g0/r3"\nproven = { by = "xemu", ref = "toy/A1" }\n'
                                  '\n[[location]]\nid = "t1/g0/r1"\nproven = { by = "l3", ref = '
                                  '"toy/aaaaaaaaaaaa@bbbbbbbbbbbb" }\n'
                                  '\n[[location]]\nid = "t1/g0/r4"\nproven = { by = "l3", ref = "x7/not-a-string" }\n'),
         ("levels/t1.toml", 'to = "t1_start"\nkind = "walk"\n',
          'to = "t1_start"\nkind = "walk"\nconfidence = "probed"\n'
          'proven = { by = "l3", ref = "x7/0123456789ab@ba9876543210" }\n')),
        [("bad_proven", "levels/t1.toml: edge[t1_vault->t1_start].proven"),
         ("bad_proven", "levels/t1.toml: location[t1/g0/r3].proven"),
         ("bad_proven", "levels/t1.toml: location[t1/g0/r1].proven"),
         ("unresolved_generated", "levels/t1.toml: location[t1/g0/r4]"),
         ("bad_proven", "levels/t1.toml: location[t1/g0/r4].proven")]),
    "D170: a spot's proof record without the way back is refused, and its mark then resolves to nothing": (
        "toydb",
        (("levels/t1.toml", 'proven = { by = "data", ref = "toy" }',
          'proven = { by = "l3", ref = "toy/aaaaaaaaaaaa@bbbbbbbbbbbb" }'),
         ("proofs.jsonl", '"returned":true', '"returned":false')),
        [("bad_proof", "proofs.jsonl:1"), ("bad_proven", "levels/t1.toml: location[t1/g0/r2].proven")]),
    "D277: a skip's L3 record owes no xemu replay (the shipped e2.steam_group_air1's), a spot's still does": (
        "toydb",
        (("proofs.jsonl", '"ref":"toy/aaaaaaaaaaaa@bbbbbbbbbbbb","replay":{"equal":true',
          '"ref":"toy/aaaaaaaaaaaa@bbbbbbbbbbbb","replay":{"rule":"D277","equal":null'),),
        [("bad_proof", "proofs.jsonl:1")]),
    "D169: a route mark where the logic opens the spot with less than the route held (r1: left without the water the "
    "route left with), not where it doesn't (r2, once the vault's way back needs its red key)": (
        "toydb",
        (("levels/t1.toml", 'proven = { by = "data", ref = "toy" }', 'proven = { by = "route", ref = "toy" }'),
         ("levels/t1.toml", 'from = "t1_vault"\nto = "t1_start"\nkind = "walk"',
          'from = "t1_vault"\nto = "t1_start"\nkind = "walk"\nrequires = "key.red>=1"'),
         ("levels/t1.toml", None, '\n[[location]]\nid = "t1/g0/r1"\nproven = { by = "route", ref = "toy" }\n')),
        [("bad_proven", "levels/t1.toml: location[t1/g0/r1].proven")]),
    **{f"D114: an in-logic skip confirmed {case}, in its level and in tricks.toml": (
        "toydb",
        tuple((rel, _SKIP_CONFIRMED, f'status = "in_logic"\nconfirmed = {confirmed}')
              for rel in ("levels/t1.toml", "tricks.toml")),
        [(code, "levels/t1.toml: skip[t1.wall_skip].confirmed"), (code, "tricks.toml: skip[t1.wall_skip].confirmed")])
       for case, confirmed, code in (("no", '"no"', "skip_in_logic_unconfirmed"),
                                     ("by an owner ref owner_refs doesn't list",
                                      '{ by = "owner", ref = "a heading nobody wrote" }', "bad_confirmed"),
                                     ("malformed", "5", "bad_confirmed"),
                                     ("by an L3 record that claims a location, not the skip (D177)",
                                      '{ by = "l3", ref = "toy/aaaaaaaaaaaa@bbbbbbbbbbbb" }', "bad_confirmed"))},
    "§4.8: a level skip that differs from its tricks.toml row": (
        "toydb", (("tricks.toml", "difficulty = 2\n", "difficulty = 3\n"),),
        [("skip_projection_differs", "levels/t1.toml: skip[t1.wall_skip].difficulty")]),
    "rules 1, 20: an unknown key or enum value, a repeated key or a non-integer in a generated file, a triple": (
        "toydb",
        (("levels/t1.toml", 'confidence = "data"', 'confidence = "sure"\nflavour = "toy"'),
         ("levels/t2.toml", 'kind = "exit"', 'kind = "exit"  # at [1.0, -2.5, 3.25]'),
         ("generated/t3.json", None, '{"level": "t3", "level": "t3"}'),
         ("generated/t4.json", None, '{"level": "t4", "records": 1.5}')),
        [("generated_duplicate_key", "generated/t3.json"),
         ("generated_non_integer_number", "generated/t4.json"),
         ("bad_enum_value", "levels/t1.toml: edge[t1_start->t1_vault].confidence"),
         ("unknown_key", "levels/t1.toml: edge[t1_start->t1_vault].flavour"),
         ("coordinate_like_triple", "levels/t2.toml")]),
    "AZ-290: an exit of draft 0's kind dead_dest, which v1 drops": (
        "toydb", (("generated/t1.json", '"kind": "exit",\n   "live": true', '"kind": "dead_dest",\n   "live": true'),),
        [("bad_enum_value", "generated/t1.json: exits[t1/g0/r20].kind"),
         ("unresolved_generated", "levels/t1.toml: node[t1_start].anchors"),
         ("unresolved_generated", "levels/t1.toml: edge[t1_start->t2_hub].exit")]),
    "§13: a draft route's step that contradicts the data or malformed entry, but not its unresolved reference": (
        "toydb",
        (("route.toml", 'status = "authored"', 'status = "draft"'),
         ("route.toml", 'requires = "flag:t1.boss.killed"', 'requires = "flag:t1.boss.missed"'),
         ("route.toml", 'item = "power_water"', 'item = "key_red"'),
         ("route.toml", None, '\n[area_to_level]\n"Toy Town" = { level = ["t1"], evidence = "toy" }\n')),
        [("bad_area_to_level", "route.toml: area_to_level[Toy Town]"),
         ("route_step_differs", "route.toml: step[1]")]),
}


def test_loader_refuses_each_rule_a_database_breaks_naming_where(tmp_path):
    """The loader fails closed (docs/RANDOMIZER_DB.md, format v1): the toy database loads clean, its pool locations
    get a node (by a node's locations, a cell anchor or default_node) and its stub's node-less ones are counted, not
    refused; each case in _REFUSALS breaks a copy and check_database names exactly its issues (load_database raises
    them). The authoring's texts stand in for its level and movement files, and a derived file needs gzip, its
    format, a stamp and a playable level."""
    report = check_database(TOYDB)
    assert report.issues == []
    assert [(i.code, i.where) for i in check_database(TOYDB, {"movement/t1.json": "{"}).issues] == [
        ("unreadable_file", "movement/t1.json")]
    assert report.database.node_of == {"t1/g0/r1": "t1_start", "t1/g0/r3": "t1_start", "t1/g0/r2": "t1_vault"}
    assert report.summary["pool_locations_without_a_node"] == {"t2": 2}
    wrong = {}
    for n, (case, (db, edits, want)) in enumerate(_REFUSALS.items()):
        root = shutil.copytree(DATA / db, tmp_path / str(n))
        for edit in edits:
            _edit(root, *edit)
        if (got := _issues(root)) != want:
            wrong[case] = got
    assert wrong == {}
    with pytest.raises(DatabaseError, match="route_step_differs"):
        load_database(root)
    derived = _toy(tmp_path / "derived")
    (derived / "derived").mkdir()
    (derived / "derived" / "t1.json.gz").write_bytes(gzip.compress(
        b'{"_meta": {"format": "azurik-rando-derived/0", "level": "t1"}, "level": "t1"}'))
    (derived / "derived" / "t9.json.gz").write_bytes(gzip.compress(json.dumps(
        {"_meta": {"format": "azurik-rando-derived/1", "level": "t9", "stamp": "0" * 64}, "level": "t9"}).encode()))
    (derived / "derived" / "t1.json").write_text("{}", encoding="utf-8")
    assert _issues(derived) == [
        ("unknown_file", "derived/t1.json"), ("unknown_format", "derived/t1.json.gz: _meta.format"),
        ("derived_no_stamp", "derived/t1.json.gz"), ("derived_unknown_level", "derived/t9.json.gz")]


def test_a_spots_l3_proof_at_more_of_an_element_than_the_logic_asks_there_is_refused_and_as_much_or_less_loads(
        tmp_path):
    """AZ-543 (D169's rule, as the route's marks): an L3 record's kit is what its string held from a new game, so its
    mark loads only where the logic never collects the spot holding less. t1/g0/r3 lies at the start: a string at
    water 1 doesn't back it, one at none does, and a kit naming no counter or holding no count is refused, never read
    as kit 0. t1/g0/r2's boss asks water 1: a string at water 1 or none backs it, its key needed nowhere on the way
    back (a prefilled spot leaves holding its own item alone)."""
    got = {}
    for n, (loc, kit) in enumerate((("t1/g0/r3", '{"water":1}'), ("t1/g0/r3", "{}"), ("t1/g0/r3", '{"Water":1}'),
                                    ("t1/g0/r3", '{"water":"1"}'), ("t1/g0/r2", '{"water":1}'), ("t1/g0/r2", "{}"))):
        root = _toy(tmp_path / str(n))
        _edit(root, "proofs.jsonl", '"claim":{"id":"t1/g0/r2","kind":"location","kit":{}',
              f'"claim":{{"id":"{loc}","kind":"location","kit":{kit}')
        mark = 'proven = { by = "l3", ref = "toy/aaaaaaaaaaaa@bbbbbbbbbbbb" }'
        if loc == "t1/g0/r2":
            _edit(root, "levels/t1.toml", 'proven = { by = "data", ref = "toy" }', mark)
        else:
            _edit(root, "levels/t1.toml", None, f'\n[[location]]\nid = "{loc}"\n{mark}\n')
        got[loc, kit] = [(i.code, i.where, i.detail.split(";")[0]) for i in check_database(root).issues]
    where = "levels/t1.toml: location[t1/g0/r3].proven"
    assert got == {
        ("t1/g0/r3", '{"water":1}'): [
            ("bad_proven", where, "by l3: the logic collects it holding water 0 (every other counter in full) with "
                                  "nothing on it")],
        ("t1/g0/r3", "{}"): [],
        ("t1/g0/r3", '{"Water":1}'): [("bad_proven", where, "by l3: its record's kit names no counter: Water")],
        ("t1/g0/r3", '{"water":"1"}'): [
            ("bad_proof", "proofs.jsonl:1", "a claim's kit maps counters to non-negative integers"),
            ("bad_proven", where, "no record in proofs.jsonl for toy/aaaaaaaaaaaa@bbbbbbbbbbbb")],
        ("t1/g0/r2", '{"water":1}'): [], ("t1/g0/r2", "{}"): []}


def test_vanilla_placement_is_beatable_and_fully_accessible_without_tricks():
    """§4.3's check 1 on the shipped database: with the vanilla placement and the default options (no skip) every
    pool location is collected and victory holds. A stub holds its own items free (§4.1), so this checks the authored
    realms: a too-strict edge, a gate left closed, or a lock whose worst-case key count waits on a level the realm
    can't reach first misses a location. AZ-345: the torpedo needs w1's water keylock (the periscope's joystick reads
    it), and the key rule opens the keylock before life's two key_life1 are taken, since they lie in life's hub
    ahead of its two locks; the worst case alone made this unbeatable."""
    logic, trace = _shipped(), []
    reach = logic.reach(trace=trace)
    assert ([loc for loc in sorted(logic.pool) if loc not in reach.locations], reach.victory) == ([], True)
    assert logic.db.hand["w1.pCubeShape7.joystick"][2]["requires"] == "button:w1.water_keylock"
    opened = next(sp for sp in trace if "w1.water_keylock.open" in sp.flags)
    assert (opened.counters["key.life1"], {"life/g0/r332", "life/g0/r334"} & opened.got) == (1, set())


def test_the_vanilla_route_replays_in_order_in_every_realm():
    """§4.3's check 2: route.toml's steps in the realms' levels, replayed in order under the default options at the
    safe movement tier (D156: every jump vanilla's own route needs is safe, so every tier replays it). Each location
    step is collected, and each action step's flag credited, when the placement holds the vanilla items of the
    route's steps so far and every later spot is empty (a guardian slot keeps its fragment, D81, and a key its key:
    the fill pre-fills both; the stubs hold theirs). A step the logic reaches only later names logic stricter than
    the vanilla run, in a specific place."""
    logic = _shipped()
    safe = dataclasses.replace(logic.db.defaults, movement_tier="safe")
    realms = {lvl for levels in REALMS.values() for lvl in levels}
    vanilla, placed, reaches, late = logic.vanilla_placement(), {}, {}, []
    for step in logic.db.route["step"]:
        if step["kind"] == "location" and step["id"] in vanilla:
            placed[step["id"]] = vanilla[step["id"]]
        if step["level"] not in realms:
            continue
        if len(placed) not in reaches:
            reaches[len(placed)] = logic.reach(safe, placement={
                loc: placed.get(loc, item if loc in logic.guardian or item.startswith("key_") else None)
                for loc, item in vanilla.items()})
        reach = reaches[len(placed)]
        if step["kind"] == "location":
            got = step["id"] in reach.locations
        else:
            atom = parse(step["sets"])
            got = atom[1] + (".open" if atom[0] == "button" else "") in reach.flags
        if not got:
            late.append((step["step"], step.get("id") or step["sets"]))
    assert late == [] and reaches


def test_physical_reach_takes_the_edges_out_of_logic_and_only_the_skips_that_are_on():
    """§2.10, §2.13, §15: R_phys, where a player can physically get with the items held, also takes an edge with
    logic = false (r1_secret), one that a toggle opens (r1_attic), a cart whose lock isn't harmless (r1_shaft), one
    above the movement tier (r1_ledge, hard, at safe) or of the phys tier (r1_gap), a drop whose assumes flag isn't
    credited (r1_pit: one obsidian, so no r1.olock), and a lock with one key whatever its worst-case count (r1_hall
    and r1_inner, one red key); it takes a skip only when the options turn it on (r1_vault through r1.wall_skip, with
    no water to destroy r1.wall). A trap's escape walks the physical graph, so r1_secret, whose ways in and out are
    both logic = false, is no trap."""
    logic = _logic(DATA / "reachdb")
    placement = {**logic.vanilla_placement(), "r1/g0/r2": "sapphire", "r1/g0/r5": "sapphire", "r1/g0/r43": "sapphire"}
    off = logic.reach(Settings(0, "safe", {}), placement, ["power_air"])
    on = logic.reach(Settings(2, "safe", {}), placement, ["power_air"])
    plain = logic.reach()
    assert (off.phys - off.nodes, on.phys - off.phys, on.nodes - off.nodes) == (
        {"r1_secret", "r1_attic", "r1_shaft", "r1_ledge", "r1_gap", "r1_pit", "r1_hall", "r1_inner"}, {"r1_vault"},
        {"r1_vault"})
    assert ("r1_secret" in plain.phys - plain.nodes, "r1_secret" in plain.traps) == (True, False)


def test_a_route_mark_a_skip_outdoes_holds_below_the_skips_tier_and_above_it_for_the_walks_own_way_out():
    """AZ-725 (D169 under the options): w2.firewall02_air3 (Hard) leaves w2's main body at air 3 with no water, so
    with it on the logic collects w2/g0/r1346 (power_water in the hose pool) holding less water than the route's walk
    left with. The mark names the skip (``unless``) and the items whose water gives that walk's way out (``only``):
    options that leave the skip off take any progression item there, options that turn it on only those, and the
    mark without its ``unless`` is short of the walk."""
    logic, loc = _shipped(), "w2/g0/r1346"
    pv, walk = logic.location_rows[loc]["proven"], logic.route_walks({loc})[loc]
    slots = [_Slots(logic, Settings(c, "standard", {})) for c in (2, 3)]
    bare = {"by": "route", "ref": pv["ref"]}
    assert ((pv["unless"], pv["only"]), [(s.holds(loc, "power_water"), s.holds(loc, "power_air")) for s in slots],
            logic.mark_short(loc, pv, walk), logic.mark_short(loc, bare, walk).split(" (")[0]) == (
        (["w2.firewall02_air3"], ["power_water", "power_water_a3"]), [(True, True), (True, False)], None,
        "the logic collects it holding water 0")


# --- Step 4.28f and 4.42b: the settings' and share strings' rules on the toy database (moved here from
# test_randomizer.py by Step 4.52c, so a change to the toy database alone runs them) ----------------------------

def test_settings_refuse_a_toggle_that_turns_on_a_held_or_manual_skip(tmp_path):
    """D144: a toggle wins over the ceiling, but never turns on a held or a
    manual skip, in a settings file or a share string; a string's toggles
    count only against the skip registry it was made for (§7.3)."""
    root = tmp_path / "db"
    shutil.copytree(TOYDB, root)
    (root / "settings" / "mine.toml").write_text(
        'format = "azurik-rando-settings/1"\nskip_ceiling = 4\nmovement_tier = "safe"\ndark_fire = 1\n\n'
        '[skip_override]\n"t1.wall_skip" = false\n"t1.held_skip" = true\n"t1.manual_skip" = true\n',
        encoding="utf-8")
    assert [(i.code, i.where) for i in check_database(root).issues] == [
        ("settings_enables_held_or_manual_skip", "settings/mine.toml: skip_override.t1.held_skip"),
        ("settings_enables_held_or_manual_skip", "settings/mine.toml: skip_override.t1.manual_skip")]
    skips = {sid: s for sid, (_, s) in load_database(TOYDB).skips.items()}
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
    skips = {sid: s for sid, (_, s) in load_database(TOYDB).skips.items()}
    for run in (5, 200_000):
        raw = bytes([0, 0x80]) + registry_tag(picks(skips)) + b"\xff" * run
        with pytest.raises(SettingsError, match="share: a toggle index past the registry$"):
            share_decode("AZR-" + base64.b32encode(raw).decode().rstrip("="), skips)


def test_a_settings_refusal_names_its_first_20_problems_and_counts_the_rest():
    """Step 4.42b: a settings table refused for many reasons (a handed file
    of a million unknown toggles) says the first 20 and how many more, as
    the writer's refusals do, not a line as large as the table; its
    ``problems`` keep every one."""
    skips = {sid: s for sid, (_, s) in load_database(TOYDB).skips.items()}
    with pytest.raises(SettingsError) as refused:
        settings_from_table(layer.settings_doc(Settings(0, "hard", {})) | {
            "skip_override": {f"t1.none_{k:02}": True for k in range(25)}}, skips, "settings file")
    said = str(refused.value)
    assert (len(refused.value.problems), said.count("the database has no such skip"), said.endswith(
        "; ... and 5 more"), "t1.none_19" in said, "t1.none_20" in said) == (25, 20, True, True, False), said


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
    db = load_database(root)
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
    assert [(i.code, i.detail) for i in check_database(root).issues if i.code == "bad_batch"] == [
        ("bad_batch", "its variants' gates differ")]
