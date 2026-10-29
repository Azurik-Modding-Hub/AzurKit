"""The randomizer's planner (Step 4.2a) against Modkit's plans
(``tests/oracle/rando/``'s ``rando_plans.json``): seed 2 under the strict,
default and max settings gives Modkit's attempt and plan sha256, and the
default plan file is Modkit's byte for byte, on CPython and under Pyodide
(the site's runtime). Pure tier: the database is our own logic data."""

from __future__ import annotations

import json

import pytest

from azurkit import cli, sdk
from azurkit.tools.randomizer.planner.fill import settings_table
from azurkit.tools.randomizer.planner.loader import kept_logic
from azurkit.tools.randomizer.planner.settings import Settings, share_encode
from scripts.oracle_sync import ORACLE

PLANS = json.loads((ORACLE / "rando/tests/goldens/rando_plans.json").read_text(encoding="utf-8"))
CASES = json.loads((ORACLE / "rando/cases.json").read_text(encoding="utf-8"))["tests/goldens/rando_plans.json"]
DEFAULT_PLAN = json.dumps(PLANS["default"]["plan"], indent=1, sort_keys=True) + "\n"   # Modkit's plan file


def _recipe(case: dict) -> dict:
    """An oracle case (Modkit's seed and ``Settings`` fields) as the sdk's
    recipe, its settings as a settings file holds them."""
    st = case["settings"]
    return {"seed": case["seed"], "settings": settings_table(Settings(
        st["skip_ceiling"], st["movement_tier"], st["dark_fire"], st["skip_override"],
        frozenset(st["exclude_categories"]), st["sliders"]))}


def test_seed_2s_plan_under_each_profile_is_modkits_and_the_default_plan_file_byte_for_byte(capsys):
    assert sorted(CASES) == ["default", "max", "strict"] and PLANS["seed"] == "2"
    for name, case in CASES.items():
        doc = sdk.plan(_recipe(case))
        assert (doc["attempt"], doc["sha256"]) == (PLANS[name]["attempt"], PLANS[name]["sha256"]), name
    assert cli.main(["plan", "--seed", "2"]) == 0        # the database's defaults are the default profile's
    assert capsys.readouterr().out == DEFAULT_PLAN


def test_a_plan_reads_back_into_its_spoiler_and_what_the_planner_cant_take_is_refused_by_name():
    """The default plan's spoiler names its share string and each sphere;
    an edited plan, a recipe with both settings and a share string, and a
    share string with movement sliders (their logic re-check comes with
    Step 4.2b) are refused, each by name."""
    lines = sdk.spoiler(PLANS["default"]["plan"])["lines"]
    assert any(PLANS["default"]["plan"]["share"] in line for line in lines)
    assert any(line.lower().startswith("sphere") for line in lines)
    edited = PLANS["default"]["plan"] | {"seed": "3"}
    with pytest.raises(ValueError, match="edited plan"):
        sdk.spoiler(edited)
    with pytest.raises(ValueError, match="settings and share both"):
        sdk.plan({"seed": "2", "settings": {}, "share": "AZR-AAEA"})
    skips = {sid: s for sid, (_, s) in kept_logic().db.skips.items()}
    share = share_encode(Settings(0, "standard", 1, {}, sliders={"player_physics": {"gravity": 2.0}}), skips)
    with pytest.raises(ValueError, match=r"movement sliders \(player_physics\.gravity\).*Step 4\.2b"):
        sdk.plan({"seed": "2", "share": share})


def test_the_default_plan_file_is_modkits_byte_for_byte_under_pyodide(pyodide):
    got = pyodide("plan", "--seed", "2")
    assert (got["code"], got["stderr"]) == (0, ""), got["stderr"][-2000:]
    assert got["stdout"] == DEFAULT_PLAN
