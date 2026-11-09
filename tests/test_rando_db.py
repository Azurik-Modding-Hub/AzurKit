"""The randomizer database's dev tools (``devkit/rando``, Step 4.13b: Modkit's ``rando db-extract``, ``rando check``,
``rando_bench.py``, ``rando_impact.py`` and ``rando_soak.py``) and the fixture databases they and the solver's
corpus run on (``devkit/rando/data``: ``toydb``, ``reachdb``, ``escapedb``, ``guardiandb``, ``impactdb`` and the
committed plans in ``plans/valid`` and ``plans/invalid``)."""

from __future__ import annotations

import functools
import json
import random
import shutil
from pathlib import Path

import pytest

from azurkit.core import gate
from azurkit.tools.randomizer.planner.fill import FillError, fill
from azurkit.tools.randomizer.planner.loader import DATA_DIR, check_database, load_database
from azurkit.tools.randomizer.planner.settings import SETTINGS_FORMAT, settings_from_table
from azurkit.tools.randomizer.planner.solver import Logic
from devkit.rando import bench, check, db_extract, impact, soak

DATA = Path(db_extract.__file__).resolve().parent / "data"
TOYDB = DATA / "toydb"
PLANS = sorted(p for verdict in ("valid", "invalid") for p in (DATA / "plans" / verdict).glob("*.json"))
RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]


def _edit(root: Path, rel: str, old: str, new: str) -> None:
    """Replace the one ``old`` in ``rel`` with ``new``."""
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (rel, old)
    path.write_text(text.replace(old, new), encoding="utf-8")


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
