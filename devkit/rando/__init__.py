"""The randomizer database's tools and benches (dev only): the generated level data from the USA image, the reach
model's derive, the realm authoring, the database's check, the solver's bench, the impact ranking of its unknowns and
the seed soak.

:mod:`.db_extract` writes ``data/generated`` (Modkit's ``rando db-extract``: ``levels.extract`` and
``write_generated`` on :mod:`azurkit.tools.randomizer.levels`' rules); :mod:`.check` loads a database with every
check and says what is open (``rando check``); :mod:`.bench`, :mod:`.impact` and :mod:`.soak` are Modkit's
``rando_bench.py``, ``rando_impact.py`` and ``rando_soak.py``. :mod:`.ports` points the imports Modkit's modules
had at AzurKit's engine (Step 4.13b), and ``data/`` holds the fixture databases the tests and the impact ranking
run on.

:mod:`.draft` is Modkit's ``randomizer/draft`` at its freeze (Step 4.13c): the reach model on a level's collision
(:mod:`.draft.reach`) and its derived data (:mod:`.draft.export`), the authoring that writes the level and movement
files from it (:mod:`.draft.author`), the route graph and the L3 goals the certification searches (:mod:`.draft.route`,
:mod:`.draft.l3_goal`). The shipped half of the draft (the envelope, floors, geometry, wiring and ``tiers.toml``) is the
randomizer's own, in ``src``; :mod:`.physics` restores the parts of Modkit's physics the derive needs. Its verbs:
:data:`VERBS`; ``devkit/rando/README.md`` has each one's reference.
"""

VERBS: dict[str, str] = {
    "db-extract": "write the 23 levels' generated data from the vanilla image (--out DIR [--iso IMAGE])",
    "derive": "run the reach model on levels and write (or --check) their derived data",
    "author": "write (or --check) the level and movement files from the derived data and the authoring",
    "check": "load a randomizer database with every check and print what is open; exit 1 naming each error",
    "restack": "re-derive the stale levels, re-author, check, then record the randomizer's goldens",
    "bench": "time the solver: the load, the compile, a reach and a plan, on the shipped and a synthetic database",
    "impact": "rank the unproven spots and assumed edges by their effect on the default fill (--out DIR)",
    "soak": "fill many seeds under the fixed profiles and drawn settings, verify, build and cross-check (--out DIR)",
}

DEFAULT_SEED = "2"      # the goldens' seed (D185; tests/goldens/cases.json's randomizer cases): the L3 chains plan it
