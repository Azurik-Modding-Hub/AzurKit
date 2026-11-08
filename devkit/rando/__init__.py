"""The randomizer database's tools and benches (dev only): the generated level data from the USA image, the
database's check, the solver's bench, the impact ranking of its unknowns and the seed soak.

:mod:`.db_extract` writes ``data/generated`` (Modkit's ``rando db-extract``: ``levels.extract`` and
``write_generated`` on :mod:`azurkit.tools.randomizer.levels`' rules); :mod:`.check` loads a database with every
check and says what is open (``rando check``); :mod:`.bench`, :mod:`.impact` and :mod:`.soak` are Modkit's
``rando_bench.py``, ``rando_impact.py`` and ``rando_soak.py``. :mod:`.ports` points the imports Modkit's modules
had at AzurKit's engine (Step 4.13b), and ``data/`` holds the fixture databases the tests and the impact ranking
run on. Its verbs: :data:`VERBS`; ``devkit/rando/README.md`` has each one's reference.
"""

VERBS: dict[str, str] = {
    "db-extract": "write the 23 levels' generated data from the vanilla image (--out DIR [--iso IMAGE])",
    "check": "load a randomizer database with every check and print what is open; exit 1 naming each error",
    "bench": "time the solver: the load, the compile, a reach and a plan, on the shipped and a synthetic database",
    "impact": "rank the unproven spots and assumed edges by their effect on the default fill (--out DIR)",
    "soak": "fill many seeds under the fixed profiles and drawn settings, verify, build and cross-check (--out DIR)",
}
